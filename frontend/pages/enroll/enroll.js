const { createPage } = require('../../utils/page-mixin');
const { loadBrochureImages, handleImageError } = require('../../utils/brochure-cache');
const { get, BASE_URL } = require('../../utils/request');

// =====================================================================
// 背景音乐：走 MinIO 私有桶（与 headphoto 同款反向代理预签名方案）
//
// 数据源路径：
//   zhxt/audio/颁奖音乐.mp3
//
// 链路：
//   前端 → GET /audio/url?key=audio/颁奖音乐.mp3 → 后端 sign_object_url()
//        → 返回 Sig V4 预签名 URL（/object/.../?X-Amz-...）
//   InnerAudioContext.play() → /object/<bucket>/audio/颁奖音乐.mp3?X-Amz-...
//        → nginx 反代 → MinIO Sig V4 验签 → 文件
//
// 注意：
//   1. 预签名 URL 默认 5 分钟过期，过期后 InnerAudioContext 拉取会 403。
//      缓存策略：本地缓存 URL 4 分钟，下次进入复用，过期才重拉。
//   2. 音频 URL 由 loadAudio() 异步拉取并预加载；onCanplay 后自动播放。
//   3. 如果音频对象不存在（404），前端降级为不显示/不播放音乐按钮（不报错）。
// =====================================================================
const BGM_KEY = 'audio/Kiss The Rain.mp3';

// MinIO 公共桶：音乐图标
// 完整 URL 由后端 /public-image-proxy 接口返回（或直接拼前缀）
const MUSIC_ICON_KEY = 'images/music.png';

// 音频签名 URL 缓存（避免每次进页面都请求后端）
// 存储在 wx.storage 中；有效期 4 分钟 < 后端 5 分钟过期
const AUDIO_URL_CACHE_KEY = 'enroll_audio_url_cache';

// 音频本地文件缓存：InnerAudioContext 用本地 wxfile:// 路径播放
// 优势：本地文件没有签名过期问题，二次进入秒开（无需下载）
// 存储：{ localPath, remoteUrl, expires, savedAt }
//  - localPath: wxfile://... 路径
//  - remoteUrl: 上次下载时对应的签名 URL（用于对比签名是否变化）
//  - expires: localPath 路径本身的有效期（7 天，远大于单次会话）
//  - savedAt: 下载时间戳（用于诊断）
const AUDIO_LOCAL_CACHE_KEY = 'enroll_audio_local_cache';
const AUDIO_LOCAL_TTL_MS = 7 * 24 * 60 * 60 * 1000; // 7 天

// 后端域名（必须在小程序 downloadFile 合法域名白名单中）
const AUDIO_DOMAIN_WHITELIST_HINT = 'audio';

// =====================================================================
// 返回首页图标：内置 SVG data URL 兜底（保证首屏就有图标，不依赖后端）
// =====================================================================
const HOME_ICON_FALLBACK = 'data:image/svg+xml;utf8,' + encodeURIComponent(
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48">' +
  '<path fill="#ffffff" d="M24 5L2 24h6v18h12V28h8v14h12V24h6z"/>' +
  '</svg>'
);

createPage({
  data: {
    // imageList: [{ url, aspect }] —— aspect: 'landscape' | 'portrait' | undefined
    imageList: [],
    totalCount: 0,
    currentIndex: 0,
    isLoading: true,
    schoolType: 'open',

    // 顶部安全区高度（像素）
    statusBarHeight: 20,
    // 胶囊距右距离（px）
    capsuleRight: 0,
    // 胶囊距顶距离（px）—— 用于标题 vertical align
    capsuleTop: 0,
    // 胶囊高度（px）—— 让标题容器和胶囊同高
    capsuleHeight: 32,
    // 标题 padding-right：胶囊右侧宽度（含胶囊宽 87px + 间距 8px）
    titlePadRight: 100,
    // 标题 padding-left：与第二行 .floating-top padding 一致 (24rpx)，保证两行左对齐
    titlePadLeft: 12,
    // 顶栏 top 偏移（避开胶囊后的位置）
    topBarTop: 0,
    // 音乐
    isPlaying: false,
    musicReady: false,
    musicIconUrl: '',         // 音乐图标（公共桶 → 启动后端 fallback）
    homeIconUrl: HOME_ICON_FALLBACK, // 返回首页图标（兜底 SVG，保证首屏就有图）
    // 操作提示（首次进入展示 4s）
    showHint: false,
    hintText: '单击图片可放大预览',
    // 翻到最后一页：最后一次右滑后回首页（swiper 的 circular=false 是硬限制，需 JS 层回收）
    atLastPage: false
  },

  onLoad(options) {
    const schoolType = options.type || 'open';

    // 状态栏高度（拿到后为 music 按钮预留安全区，避免被胶囊菜单遮挡）
    let statusBarHeight = 20;
    let capsuleRight = 0;  // 胶囊距右边距离（px）
    let capsuleTop = 0;    // 胶囊距顶距离（px）
    let capsuleHeight = 32; // 兜底胶囊高度
    let screenWidth = 375; // 兜底屏幕宽度
    try {
      const winInfo = wx.getWindowInfo ? wx.getWindowInfo() : wx.getSystemInfoSync();
      statusBarHeight = (winInfo && winInfo.statusBarHeight) || 20;
      screenWidth = (winInfo && (winInfo.windowWidth || winInfo.screenWidth)) || 375;
      try {
        const menuRect = wx.getMenuButtonBoundingClientRect && wx.getMenuButtonBoundingClientRect();
        if (menuRect) {
          capsuleRight = Math.max(0, screenWidth - menuRect.right);
          capsuleTop = menuRect.top || 0;
          capsuleHeight = menuRect.height || capsuleHeight;
        }
      } catch (e2) {}
    } catch (e) {}
    if (!statusBarHeight || statusBarHeight < 20) statusBarHeight = 20;
    if (!capsuleRight || capsuleRight < 4) capsuleRight = 90;
    // 标题 padding-right：胶囊宽 87 + 右边距 capsuleRight + 视觉间距 8
    const titlePadRight = 87 + capsuleRight + 8;
    // 标题 padding-left：与第二行 .floating-top padding 一致 (24rpx)，保证两行左对齐
    const rpxToPx = screenWidth / 750;
    const titlePadLeft = 24 * rpxToPx;

    // 顶栏 top：胶囊下边缘 + 16px 安全间距（避开胶囊按钮）
    const btnHeightPx = 72 * rpxToPx;     // 音乐按钮实际像素高度
    const capsuleBottom = capsuleTop + capsuleHeight;
    // 顶栏 top = 胶囊底部 + 16px 安全间距，且至少在 statusBar 之下
    const topBarTop = Math.max(capsuleBottom + 16, statusBarHeight + 16);

    this.setData({ schoolType, statusBarHeight, capsuleRight, capsuleTop, capsuleHeight, titlePadRight, titlePadLeft, topBarTop });

    // 异步加载音乐图标（公共桶，长期有效）
    this._loadMusicIcon();

    // 初始化 audioContext（异步；保留 Promise 供 toggleMusic 兜底等待）
    this._initAudioPromise = this.loadAudio();

    // 加载图片
    loadBrochureImages(schoolType, {
      onInit: (totalCount, urls) => {
        // 把 url 字符串数组包装成 {url, aspect} 对象数组
        // 默认 aspect = 'landscape'（横图常见），避免首帧竖图溢出产生白带
        // 真实横/竖由 onImageLoad 拿到宽高后纠正
        const imageList = urls.map((url) => ({ url: url || '', aspect: 'landscape' }));
        this.setData({
          totalCount,
          imageList
        });
        if (totalCount > 0) {
          this.setData({ showHint: true });
          setTimeout(() => {
            if (this.data.showHint) this.setData({ showHint: false });
          }, 4000);
        }
      },
      onUpdate: (index, path) => {
        // 局部更新：替换该 index 的 url（保留 aspect 字段）
        const imageList = this.data.imageList.slice();
        const item = imageList[index] || { url: '' };
        imageList[index] = { url: path, aspect: item.aspect };
        this.setData({ imageList });
      },
      onLoading: (isLoading) => {
        this.setData({ isLoading });
      },
      onError: (error) => {
        console.error('加载招生简章失败:', error);
        const msg = (error && (error.errMsg || error.message)) || '';
        // 微信域名白名单拦截是最常见的"真机看不到图片"
        if (/url not in domain list/i.test(msg)) {
          wx.showModal({
            title: '图片域名未配置',
            content: '当前使用的图片域名未在微信小程序后台"downloadFile 合法域名"中。\n' +
                     '请到 mp.weixin.qq.com → 开发管理 → 开发设置 → 服务器域名 中添加\n' +
                     `${BASE_URL.replace(/^https?:\/\//, '').split('/')[0]} 到 downloadFile 合法域名。`,
            showCancel: false,
            confirmText: '我知道了'
          });
        } else {
          wx.showToast({ title: '加载失败', icon: 'none' });
        }
      }
    });
  },

  onUnload() {
    if (this._audioTimeoutId) {
      clearTimeout(this._audioTimeoutId);
      this._audioTimeoutId = null;
    }
    if (this._showRetryTimer) {
      clearTimeout(this._showRetryTimer);
      this._showRetryTimer = null;
    }
    if (this._audio) {
      // BackgroundAudioManager 没有 destroy()，仅 stop()
      // InnerAudioContext 有 destroy()
      try {
        this._audio.stop();
        if (typeof this._audio.destroy === 'function') {
          this._audio.destroy();
        }
      } catch (e) {}
      this._audio = null;
    }
  },

  onHide() {
    // 注意：不要在 onHide 暂停音频！
    // wx.previewImage 全屏预览时只触发 onHide（不触发 onUnload），
    // 如果我们暂停音乐，用户预览期间音乐就停了，体验差。
    // 微信小程序的 InnerAudioContext 设计为全局音频，previewImage 不会停它。
  },

  onShow() {
    // 从 wx.previewImage 返回时检查 InnerAudioContext 真实状态
    // 某些真机（特别是 Android）系统会暂停音频或重置 context，需要检测并恢复
    const audio = this._audio;
    if (!audio) return;

    // 拿 audio 真实状态（paused 是只读属性）
    let actuallyPaused = true;
    try {
      actuallyPaused = !!audio.paused;
    } catch (e) {
      actuallyPaused = !this.data.isPlaying;
    }

    // 情况 1: 用户期望播放（isPlaying=true）但实际被系统暂停 → 主动恢复
    if (this.data.isPlaying && actuallyPaused) {
      try {
        audio.play();
      } catch (e) {
        console.warn('[enroll] onShow 恢复播放失败:', e);
      }
    }

    // 情况 2: 音频 context 失效（真机预览返回后偶发）→ 重建
    // 检测标志：musicReady 一直 false 但 audio 对象存在
    // 防止短时间内反复 reload：用 _lastReloadAt 节流
    if (!this.data.musicReady && this._audio) {
      const now = Date.now();
      if (now - (this._lastReloadAt || 0) > 3000) {
        console.warn('[enroll] onShow 检测到 audio 未就绪，尝试重建');
        this._lastReloadAt = now;
        this._reloadAndPlay();
      }
    }

    // 情况 3: 异步延迟恢复（适用于某些系统音频焦点延迟返回）
    // 500ms 后再检查一次
    if (this._showRetryTimer) clearTimeout(this._showRetryTimer);
    this._showRetryTimer = setTimeout(() => {
      this._showRetryTimer = null;
      this._showRetry();
    }, 500);
  },

  // onShow 检查的实际逻辑（延迟 500ms 再试一次）
  _showRetry() {
    const audio = this._audio;
    if (!audio) return;
    if (!this.data.isPlaying) return;

    let actuallyPaused = true;
    try {
      actuallyPaused = !!audio.paused;
    } catch (e) {
      return;
    }

    // 仍然暂停 → 主动 play
    if (actuallyPaused) {
      try { audio.play(); } catch (e) {}
    }
  },

  // ============================================================
  // 音频：本地缓存 + 预加载 + 自动播放
  //
  // 使用 BackgroundAudioManager（而非 InnerAudioContext）的原因：
  //   - InnerAudioContext 在 wx.previewImage / 系统抢占音频焦点时会被强制暂停
  //   - BackgroundAudioManager 是后台音频管理器，系统级保护音频焦点
  //   - previewImage 期间 audio 不会被打断
  //
  // 流程：
  //   1) 拿签名 URL（缓存优先读，4 分钟 TTL）
  //   2) 拿本地缓存路径（7 天 TTL）
  //      - 命中且签名 URL 未变 → 直接用本地路径（秒开）
  //      - 否则用 downloadFile 下载到本地 → 缓存本地路径
  //   3) BackgroundAudioManager.src = 本地路径（无签名过期问题）
  //   4) onCanplay/onPlay：musicReady=true 并自动 play()
  //   5) onError：清掉本地 + 远程缓存，下次重新拉
  //
  // 缓存键：
  //   AUDIO_URL_CACHE_KEY: { url, expires }   （远程签名 URL，4 分钟）
  //   AUDIO_LOCAL_CACHE_KEY: { localPath, remoteUrl, expires, savedAt }
  //                                    （本地文件路径，7 天）
  // ============================================================
  async loadAudio() {
    // 1) 拿签名 URL（缓存优先）
    const cachedUrl = this._getCachedAudioUrl();
    let audioUrl = cachedUrl;

    if (!audioUrl) {
      try {
        const res = await get('/audio/url', { key: BGM_KEY, host: BASE_URL });
        if (res && res.url) {
          audioUrl = res.url;
          this._setCachedAudioUrl(audioUrl);
        }
      } catch (e) {
        console.warn('[enroll] 拿音乐签名 URL 失败:', e);
      }
    }

    if (!audioUrl) {
      console.warn('[enroll] 背景音乐签名 URL 为空，跳过初始化（音频不存在或后端异常）');
      this.setData({ musicReady: false });
      this._audio = null;
      return;
    }

    // 2) 拿本地缓存路径
    let localPath = this._getCachedLocalPath(audioUrl);
    if (localPath) {
      const exists = await this._checkLocalFileExists(localPath);
      if (exists) {
        console.log('[enroll] 命中本地音频缓存，秒开:', localPath);
      } else {
        console.warn('[enroll] 本地缓存路径失效，重新下载');
        this._clearCachedLocalPath();
        localPath = '';
      }
    }
    if (!localPath) {
      localPath = await this._downloadAudioToLocal(audioUrl);
      if (localPath) {
        this._setCachedLocalPath(localPath, audioUrl);
      }
    }

    if (!localPath) {
      console.warn('[enroll] 本地下载失败，兜底用远程 URL');
      localPath = audioUrl;
    }

    // 3) 创建 BackgroundAudioManager
    let audio;
    try {
      audio = wx.getBackgroundAudioManager();
      // 必须设置 title 和 src（title 是必填）
      audio.title = '招生简章背景音乐';
      audio.epname = '招生简章';
      audio.singer = '校方';
      audio.coverImgUrl = ''; // 可选
      audio.src = localPath; // 本地路径优先（无签名过期问题）
      // BackgroundAudioManager 的播放控制
      try { audio.protocol = 'file'; } catch (e) {} // 提示这是文件
      // BackgroundAudioManager 不支持 obeyMuteSwitch（iOS 系统音量设置仍生效）
      // BackgroundAudioManager 默认循环播放需要手动处理（无 loop 属性）
    } catch (e) {
      console.warn('[enroll] 创建 BackgroundAudioManager 失败:', e);
      this._audio = null;
      return;
    }

    this._audio = audio;
    this._audioUrl = audioUrl;
    this._audioLocalPath = localPath;
    this._audioIsBgm = true; // 标记是 BackgroundAudioManager

    // 4) 监听 BackgroundAudioManager 事件
    // 注意：BackgroundAudioManager 用 onCanplay / onPlay / onPause / onError / onStop 等
    audio.onCanplay(() => {
      if (this._canplayFired) return;
      this._canplayFired = true;
      if (this._audioTimeoutId) { clearTimeout(this._audioTimeoutId); this._audioTimeoutId = null; }
      this.setData({ musicReady: true });
      // 自动播放
      try {
        audio.play();
        this.setData({ isPlaying: true });
      } catch (e) {
        console.warn('[enroll] 自动播放失败（待用户点击）:', e);
      }
    });

    audio.onPlay(() => {
      this.setData({ musicReady: true, isPlaying: true });
    });

    audio.onPause(() => {
      this.setData({ isPlaying: false });
    });

    audio.onStop(() => {
      this.setData({ isPlaying: false });
    });

    audio.onEnded(() => {
      // 自然播放结束（不应发生，因为 src 是循环的；兜底重新播放）
      console.log('[enroll] 音频自然结束，重新播放');
      try { audio.src = localPath; audio.play(); } catch (e) {}
    });

    // 加载/播放失败 → 清缓存，下次重新拉
    audio.onError((err) => {
      console.warn('[enroll] 背景音乐加载失败:', err);
      this._canplayFired = true;
      if (this._audioTimeoutId) { clearTimeout(this._audioTimeoutId); this._audioTimeoutId = null; }
      this._clearCachedAudioUrl();
      this._clearCachedLocalPath();
      this.setData({ musicReady: false, isPlaying: false });
    });

    // 5) 超时兜底：5 秒内 onCanplay 没触发
    if (this._audioTimeoutId) clearTimeout(this._audioTimeoutId);
    this._audioTimeoutId = setTimeout(() => {
      this._audioTimeoutId = null;
      if (this._canplayFired || this._audio !== audio) return;
      console.warn('[enroll] 音频 5s 内未 onCanplay，兜底用远程 URL');
      this._canplayFired = true;
      try { audio.stop(); } catch (e) {}
      this._audio = null;
      this._clearCachedLocalPath();
      // 用远程 URL 创建（重新走流程）
      this._loadWithRemoteUrl(audioUrl);
    }, 5000);
  },

  // 用远程 URL 创建 BackgroundAudioManager（兜底）
  _loadWithRemoteUrl(audioUrl) {
    try {
      const audio = wx.getBackgroundAudioManager();
      audio.title = '招生简章背景音乐';
      audio.epname = '招生简章';
      audio.singer = '校方';
      audio.src = audioUrl;
      audio.onCanplay(() => {
        this.setData({ musicReady: true });
        try { audio.play(); this.setData({ isPlaying: true }); } catch (e) {}
      });
      audio.onPlay(() => { this.setData({ isPlaying: true }); });
      audio.onPause(() => { this.setData({ isPlaying: false }); });
      audio.onError(() => { this.setData({ musicReady: false, isPlaying: false }); });
      this._audio = audio;
      this._audioIsBgm = true;
    } catch (e) {
      console.warn('[enroll] 远程 URL 兜底失败:', e);
      this.setData({ musicReady: false });
    }
  },

  // ============================================================
  // 检查本地文件路径是否还存在
  // - wxfile:// 路径在 cold start / 缓存清理后可能失效
  // - 基础库 2.16.0+ 才支持 getFileSystemManager().access()
  // ============================================================
  _checkLocalFileExists(localPath) {
    return new Promise((resolve) => {
      if (!localPath) return resolve(false);
      if (!localPath.startsWith('wxfile://') && !localPath.startsWith('http://tmp/')) {
        // 远程 URL，视为"存在"
        return resolve(true);
      }
      try {
        const fsm = wx.getFileSystemManager && wx.getFileSystemManager();
        if (!fsm || typeof fsm.access !== 'function') return resolve(true); // 老基础库兜底
        fsm.access({
          path: localPath,
          success: () => resolve(true),
          fail: () => resolve(false)
        });
      } catch (e) {
        resolve(true);
      }
    });
  },

  // ============================================================
  // 下载远程音频到本地（wxfile://...）
  // - 返回 tempFilePath，可直接用作 InnerAudioContext.src
  // - 必须配置小程序 downloadFile 合法域名（和图片同一个域名）
  // - tempFilePath 在小程序运行期间有效；冷启动后失效（storage 缓存也只是会话级）
  // ============================================================
  _downloadAudioToLocal(remoteUrl) {
    return new Promise((resolve) => {
      if (!remoteUrl) return resolve('');
      wx.downloadFile({
        url: remoteUrl,
        timeout: 30000,
        success: (res) => {
          if (res.statusCode === 200 && res.tempFilePath) {
            console.log('[enroll] 音频下载完成:', res.tempFilePath);
            // 持久化到本地存储（冷启动后仍可用，二次进入秒开）
            // 优先使用 wx.getFileSystemManager().saveFile，wx.saveFile 已废弃
            try {
              const fsm = wx.getFileSystemManager && wx.getFileSystemManager();
              if (fsm && typeof fsm.saveFile === 'function') {
                fsm.saveFile({
                  tempFilePath: res.tempFilePath,
                  success: (sv) => {
                    console.log('[enroll] 音频已持久化:', sv.savedFilePath);
                    resolve(sv.savedFilePath);
                  },
                  fail: (err) => {
                    console.warn('[enroll] fsm.saveFile 失败（用 tempFilePath）:', err);
                    // 兜底用 wx.saveFile
                    this._saveFileFallback(res.tempFilePath).then(resolve).catch(() => resolve(res.tempFilePath));
                  }
                });
                return;
              }
            } catch (e) {}
            // 老基础库兜底
            this._saveFileFallback(res.tempFilePath).then(resolve).catch(() => resolve(res.tempFilePath));
          } else {
            console.warn('[enroll] downloadFile 状态码异常:', res && res.statusCode);
            resolve('');
          }
        },
        fail: (err) => {
          console.warn('[enroll] downloadFile 失败:', err);
          resolve('');
        }
      });
    });
  },

  _saveFileFallback(tempFilePath) {
    return new Promise((resolve, reject) => {
      wx.saveFile({
        tempFilePath,
        success: (sv) => resolve(sv.savedFilePath),
        fail: reject
      });
    });
  },

  // ---------- URL 缓存 ----------
  _getCachedAudioUrl() {
    try {
      const cache = wx.getStorageSync(AUDIO_URL_CACHE_KEY);
      if (cache && cache.url && cache.expires && cache.expires > Date.now()) {
        return cache.url;
      }
    } catch (e) {}
    return '';
  },

  _setCachedAudioUrl(url) {
    try {
      wx.setStorageSync(AUDIO_URL_CACHE_KEY, {
        url,
        expires: Date.now() + 4 * 60 * 1000 // 4 分钟 < 后端 5 分钟过期
      });
    } catch (e) {}
  },

  _clearCachedAudioUrl() {
    try { wx.removeStorageSync(AUDIO_URL_CACHE_KEY); } catch (e) {}
  },

  // ---------- 本地文件路径缓存 ----------
  _getCachedLocalPath(currentRemoteUrl) {
    try {
      const cache = wx.getStorageSync(AUDIO_LOCAL_CACHE_KEY);
      if (!cache || !cache.localPath) return '';
      // TTL 检查
      if (!cache.expires || cache.expires < Date.now()) return '';
      // 签名 URL 变了 → 缓存失效（远端文件可能已替换）
      if (currentRemoteUrl && cache.remoteUrl && cache.remoteUrl !== currentRemoteUrl) {
        console.log('[enroll] 签名 URL 变了，本地缓存失效，重新下载');
        return '';
      }
      return cache.localPath;
    } catch (e) {}
    return '';
  },

  _setCachedLocalPath(localPath, remoteUrl) {
    try {
      wx.setStorageSync(AUDIO_LOCAL_CACHE_KEY, {
        localPath,
        remoteUrl: remoteUrl || '',
        expires: Date.now() + AUDIO_LOCAL_TTL_MS,
        savedAt: Date.now()
      });
    } catch (e) {}
  },

  _clearCachedLocalPath() {
    try { wx.removeStorageSync(AUDIO_LOCAL_CACHE_KEY); } catch (e) {}
  },

  // ============================================================
  // 切换播放：用户点击音乐按钮
  //  - audio 存在：直接 play/pause（不依赖 musicReady）
  //  - audio 还在加载：忽略（按钮禁用态已防穿透，兜底）
  //  - play 失败：_reloadAndPlay 重新加载
  // ============================================================
  toggleMusic() {
    const audio = this._audio;
    if (!audio) {
      // audio 还在异步加载中：按钮是禁用态，正常不会到这里；兜底不响应
      return;
    }
    if (this.data.isPlaying) {
      try { audio.pause(); } catch (e) {}
      this.setData({ isPlaying: false });
    } else {
      try {
        audio.play();
        this.setData({ isPlaying: true });
      } catch (e) {
        // play 失败（URL 过期 / 上下文失效）→ 重新加载
        console.warn('[enroll] play() 失败，重新加载:', e);
        this._reloadAndPlay();
      }
    }
  },

  // 兜底：URL 过期导致 play() 失败时，重新走一次 loadAudio 流程
  async _reloadAndPlay() {
    this._clearCachedAudioUrl();
    // 销毁旧 audio context（BackgroundAudioManager 无 destroy，仅 stop）
    if (this._audio) {
      try { this._audio.stop(); } catch (e) {}
      try {
        if (typeof this._audio.destroy === 'function') this._audio.destroy();
      } catch (e) {}
      this._audio = null;
    }
    this.setData({ musicReady: false, isPlaying: false });
    this._canplayFired = false;
    await this.loadAudio();
  },

  // ============================================================
  // 翻页：swiper 切换时记录当前页
  // ============================================================
  swiperChange(e) {
    const idx = e.detail.current;
    // 翻页后：计算是否到达最后一页
    const totalCount = this.data.totalCount;
    const atLastPage = totalCount > 0 && idx >= totalCount - 1;
    this.setData({ currentIndex: idx, atLastPage });
  },

  // 用户在最后一页继续右滑 → wechat swiper circular=false 不允许
  // 我们手动处理：捕获触摸事件，右滑超过阈值且在最后一页时切回首页
  // 但更简单且项目内一致：放一个明显的"返回第一页"按钮，让用户主动点击。

  // ============================================================
  // 图片加载完毕：读取宽高比，写入 imageList[index].aspect
  //  - landscape（横图，宽 > 高）：widthFix 宽度铺满 100vw
  //  - portrait（竖图，高 > 宽）：heightFix 高度铺满 100vh
  // ============================================================
  onImageLoad(e) {
    const index = e.currentTarget.dataset.index;
    if (typeof index !== 'number') return;
    const { width, height } = e.detail || {};
    if (!width || !height) return;
    const aspect = width >= height ? 'landscape' : 'portrait';
    const item = this.data.imageList[index];
    if (!item || item.aspect === aspect) return;
    const imageList = this.data.imageList.slice();
    imageList[index] = { ...item, aspect };
    this.setData({ imageList });
  },

  onImageError(e) {
    const index = e.currentTarget.dataset.index;
    handleImageError(this.data.schoolType, index, (i, path) => {
      const imageList = this.data.imageList.slice();
      const item = imageList[i] || { url: '' };
      imageList[i] = { url: path, aspect: item.aspect };
      this.setData({ imageList });
    });
  },

  // ============================================================
  // 点击图片：进入全屏预览（wx.previewImage）
  // ============================================================
  onPreviewImage(e) {
    const index = e.currentTarget.dataset.index;
    if (typeof index !== 'number') return;

    const imageList = this.data.imageList || [];
    if (!imageList[index] || !imageList[index].url) return;

    const urls = imageList.filter((it) => !!it.url).map((it) => it.url);
    if (urls.length === 0) return;

    const current = imageList[index].url;
    wx.previewImage({
      current,
      urls,
      fail: () => {
        if (/^https?:/i.test(current)) {
          wx.previewImage({ current, urls: [current] });
        }
      }
    });
  },

  // ============================================================
  // 加载音乐 / 返回首页 图标（公共桶 → 内联 SVG 兜底）
  //   关掉 loading toast（避免一闪而过），用静默方式请求
  // ============================================================
  async _loadMusicIcon() {
    const loadOne = async (type, dataKey) => {
      try {
        const res = await get('/audio/icon', { type, host: BASE_URL }, { showLoading: false });
        const url = res && res.url;
        if (url) {
          const fullUrl = /^https?:/i.test(url) || /^data:/i.test(url)
            ? url
            : (BASE_URL.replace(/\/$/, '') + url);
          this.setData({ [dataKey]: fullUrl });
          console.log(`[enroll] ${type} 图标就绪:`, fullUrl.slice(0, 80));
        }
      } catch (e) {
        console.warn(`[enroll] 加载 ${type} 图标失败:`, e);
      }
    };
    await loadOne('music', 'musicIconUrl');
    await loadOne('home', 'homeIconUrl');
  },

  // ============================================================
  // 回到第一页（右下角按钮）
  //   swiper 设置 circular=true 后，其实自然环绕；
  //   这里提供按钮让用户快速回到首页（带滚动动画）
  // ============================================================
  goToFirstPage() {
    if (this.data.currentIndex === 0) return;
    this.setData({ currentIndex: 0 });
    // 滚动完成后清 atLastPage
    setTimeout(() => {
      this.setData({ atLastPage: false });
    }, 450);
  },

  goBackToGuide() {
    wx.navigateTo({ url: '/packageEnroll/pages/enroll-guide/enroll-guide' });
  }
});
