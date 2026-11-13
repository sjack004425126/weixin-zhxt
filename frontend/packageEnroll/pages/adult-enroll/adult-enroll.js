const { createPage } = require('../../../utils/page-mixin');
const { loadBrochureImages, handleImageError } = require('../../../utils/brochure-cache');
const { get, BASE_URL } = require('../../../utils/request');

// =====================================================================
// 背景音乐：与 pages/enroll/enroll 共用同一 BGM
//  - 签名 URL / 本地文件缓存 key 加 "adult" 前缀，避免与 enroll 主页相互覆盖
// =====================================================================
const BGM_KEY = 'audio/Kiss The Rain.mp3';
const MUSIC_ICON_KEY = 'images/music.png';
const AUDIO_URL_CACHE_KEY = 'adult_enroll_audio_url_cache';
const AUDIO_LOCAL_CACHE_KEY = 'adult_enroll_audio_local_cache';
const AUDIO_LOCAL_TTL_MS = 7 * 24 * 60 * 60 * 1000;

const HOME_ICON_FALLBACK = 'data:image/svg+xml;utf8,' + encodeURIComponent(
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48">' +
  '<path fill="#ffffff" d="M24 5L2 24h6v18h12V28h8v14h12V24h6z"/>' +
  '</svg>'
);

createPage({
  data: {
    imageList: [],
    totalCount: 0,
    currentIndex: 0,
    isLoading: true,
    schoolType: 'adult',

    statusBarHeight: 20,
    capsuleRight: 0,
    capsuleTop: 0,
    capsuleHeight: 32,
    titlePadRight: 100,
    titlePadLeft: 12,
    topBarTop: 0,

    isPlaying: false,
    musicReady: false,
    musicIconUrl: '',
    homeIconUrl: HOME_ICON_FALLBACK,

    showHint: false,
    hintText: '单击图片可放大预览',
    atLastPage: false
  },

  onLoad(options) {
    const schoolType = options.type || 'adult';

    let statusBarHeight = 20;
    let capsuleRight = 0;
    let capsuleTop = 0;
    let capsuleHeight = 32;
    let screenWidth = 375;
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

    const titlePadRight = 87 + capsuleRight + 8;
    const rpxToPx = screenWidth / 750;
    const titlePadLeft = 24 * rpxToPx;
    const capsuleBottom = capsuleTop + capsuleHeight;
    const topBarTop = Math.max(capsuleBottom + 16, statusBarHeight + 16);

    this.setData({ schoolType, statusBarHeight, capsuleRight, capsuleTop, capsuleHeight, titlePadRight, titlePadLeft, topBarTop });

    this._loadMusicIcon();
    this._initAudioPromise = this.loadAudio();

    loadBrochureImages(schoolType, {
      onInit: (totalCount, urls) => {
        const imageList = urls.map((url) => ({ url: url || '', aspect: 'landscape' }));
        this.setData({ totalCount, imageList });
        if (totalCount > 0) {
          this.setData({ showHint: true });
          setTimeout(() => {
            if (this.data.showHint) this.setData({ showHint: false });
          }, 4000);
        }
      },
      onUpdate: (index, path) => {
        const imageList = this.data.imageList.slice();
        const item = imageList[index] || { url: '' };
        imageList[index] = { url: path, aspect: item.aspect };
        this.setData({ imageList });
      },
      onLoading: (isLoading) => {
        this.setData({ isLoading });
      },
      onError: (error) => {
        console.error('加载成人高考招生简章失败:', error);
        const msg = (error && (error.errMsg || error.message)) || '';
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
      try {
        this._audio.stop();
        if (typeof this._audio.destroy === 'function') this._audio.destroy();
      } catch (e) {}
      this._audio = null;
    }
  },

  onShow() {
    const audio = this._audio;
    if (!audio) return;
    let actuallyPaused = true;
    try { actuallyPaused = !!audio.paused; } catch (e) { actuallyPaused = !this.data.isPlaying; }
    if (this.data.isPlaying && actuallyPaused) {
      try { audio.play(); } catch (e) { console.warn('[adult-enroll] onShow 恢复播放失败:', e); }
    }
    if (!this.data.musicReady && this._audio) {
      const now = Date.now();
      if (now - (this._lastReloadAt || 0) > 3000) {
        this._lastReloadAt = now;
        this._reloadAndPlay();
      }
    }
    if (this._showRetryTimer) clearTimeout(this._showRetryTimer);
    this._showRetryTimer = setTimeout(() => {
      this._showRetryTimer = null;
      this._showRetry();
    }, 500);
  },

  _showRetry() {
    const audio = this._audio;
    if (!audio || !this.data.isPlaying) return;
    let actuallyPaused = true;
    try { actuallyPaused = !!audio.paused; } catch (e) { return; }
    if (actuallyPaused) { try { audio.play(); } catch (e) {} }
  },

  // ============================================================
  // 音频：本地缓存 + 预加载 + 自动播放（与 enroll 同款 BackgroundAudioManager）
  // ============================================================
  async loadAudio() {
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
        console.warn('[adult-enroll] 拿音乐签名 URL 失败:', e);
      }
    }
    if (!audioUrl) {
      this.setData({ musicReady: false });
      this._audio = null;
      return;
    }

    let localPath = this._getCachedLocalPath(audioUrl);
    if (localPath) {
      const exists = await this._checkLocalFileExists(localPath);
      if (exists) {
        // 命中本地缓存
      } else {
        this._clearCachedLocalPath();
        localPath = '';
      }
    }
    if (!localPath) {
      localPath = await this._downloadAudioToLocal(audioUrl);
      if (localPath) this._setCachedLocalPath(localPath, audioUrl);
    }
    if (!localPath) localPath = audioUrl;

    let audio;
    try {
      audio = wx.getBackgroundAudioManager();
      audio.title = '成人高考招生简章背景音乐';
      audio.epname = '招生简章';
      audio.singer = '校方';
      audio.coverImgUrl = '';
      audio.src = localPath;
      try { audio.protocol = 'file'; } catch (e) {}
    } catch (e) {
      console.warn('[adult-enroll] 创建 BackgroundAudioManager 失败:', e);
      this._audio = null;
      return;
    }

    this._audio = audio;
    this._audioUrl = audioUrl;
    this._audioLocalPath = localPath;

    audio.onCanplay(() => {
      if (this._canplayFired) return;
      this._canplayFired = true;
      if (this._audioTimeoutId) { clearTimeout(this._audioTimeoutId); this._audioTimeoutId = null; }
      this.setData({ musicReady: true });
      try { audio.play(); this.setData({ isPlaying: true }); } catch (e) {}
    });
    audio.onPlay(() => { this.setData({ musicReady: true, isPlaying: true }); });
    audio.onPause(() => { this.setData({ isPlaying: false }); });
    audio.onStop(() => { this.setData({ isPlaying: false }); });
    audio.onEnded(() => {
      try { audio.src = localPath; audio.play(); } catch (e) {}
    });
    audio.onError((err) => {
      console.warn('[adult-enroll] 背景音乐加载失败:', err);
      this._canplayFired = true;
      if (this._audioTimeoutId) { clearTimeout(this._audioTimeoutId); this._audioTimeoutId = null; }
      this._clearCachedAudioUrl();
      this._clearCachedLocalPath();
      this.setData({ musicReady: false, isPlaying: false });
    });

    if (this._audioTimeoutId) clearTimeout(this._audioTimeoutId);
    this._audioTimeoutId = setTimeout(() => {
      this._audioTimeoutId = null;
      if (this._canplayFired || this._audio !== audio) return;
      this._canplayFired = true;
      try { audio.stop(); } catch (e) {}
      this._audio = null;
      this._clearCachedLocalPath();
      this._loadWithRemoteUrl(audioUrl);
    }, 5000);
  },

  _loadWithRemoteUrl(audioUrl) {
    try {
      const audio = wx.getBackgroundAudioManager();
      audio.title = '成人高考招生简章背景音乐';
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
    } catch (e) {
      console.warn('[adult-enroll] 远程 URL 兜底失败:', e);
      this.setData({ musicReady: false });
    }
  },

  _checkLocalFileExists(localPath) {
    return new Promise((resolve) => {
      if (!localPath) return resolve(false);
      if (!localPath.startsWith('wxfile://') && !localPath.startsWith('http://tmp/')) return resolve(true);
      try {
        const fsm = wx.getFileSystemManager && wx.getFileSystemManager();
        if (!fsm || typeof fsm.access !== 'function') return resolve(true);
        fsm.access({ path: localPath, success: () => resolve(true), fail: () => resolve(false) });
      } catch (e) { resolve(true); }
    });
  },

  _downloadAudioToLocal(remoteUrl) {
    return new Promise((resolve) => {
      if (!remoteUrl) return resolve('');
      wx.downloadFile({
        url: remoteUrl,
        timeout: 30000,
        success: (res) => {
          if (res.statusCode === 200 && res.tempFilePath) {
            try {
              const fsm = wx.getFileSystemManager && wx.getFileSystemManager();
              if (fsm && typeof fsm.saveFile === 'function') {
                fsm.saveFile({
                  tempFilePath: res.tempFilePath,
                  success: (sv) => resolve(sv.savedFilePath),
                  fail: () => this._saveFileFallback(res.tempFilePath).then(resolve).catch(() => resolve(res.tempFilePath))
                });
                return;
              }
            } catch (e) {}
            this._saveFileFallback(res.tempFilePath).then(resolve).catch(() => resolve(res.tempFilePath));
          } else {
            resolve('');
          }
        },
        fail: () => resolve('')
      });
    });
  },

  _saveFileFallback(tempFilePath) {
    return new Promise((resolve, reject) => {
      wx.saveFile({ tempFilePath, success: (sv) => resolve(sv.savedFilePath), fail: reject });
    });
  },

  _getCachedAudioUrl() {
    try {
      const cache = wx.getStorageSync(AUDIO_URL_CACHE_KEY);
      if (cache && cache.url && cache.expires && cache.expires > Date.now()) return cache.url;
    } catch (e) {}
    return '';
  },
  _setCachedAudioUrl(url) {
    try {
      wx.setStorageSync(AUDIO_URL_CACHE_KEY, { url, expires: Date.now() + 4 * 60 * 1000 });
    } catch (e) {}
  },
  _clearCachedAudioUrl() { try { wx.removeStorageSync(AUDIO_URL_CACHE_KEY); } catch (e) {} },

  _getCachedLocalPath(currentRemoteUrl) {
    try {
      const cache = wx.getStorageSync(AUDIO_LOCAL_CACHE_KEY);
      if (!cache || !cache.localPath) return '';
      if (!cache.expires || cache.expires < Date.now()) return '';
      if (currentRemoteUrl && cache.remoteUrl && cache.remoteUrl !== currentRemoteUrl) return '';
      return cache.localPath;
    } catch (e) { return ''; }
  },
  _setCachedLocalPath(localPath, remoteUrl) {
    try {
      wx.setStorageSync(AUDIO_LOCAL_CACHE_KEY, {
        localPath, remoteUrl: remoteUrl || '', expires: Date.now() + AUDIO_LOCAL_TTL_MS, savedAt: Date.now()
      });
    } catch (e) {}
  },
  _clearCachedLocalPath() { try { wx.removeStorageSync(AUDIO_LOCAL_CACHE_KEY); } catch (e) {} },

  toggleMusic() {
    const audio = this._audio;
    if (!audio) return;
    if (this.data.isPlaying) {
      try { audio.pause(); } catch (e) {}
      this.setData({ isPlaying: false });
    } else {
      try {
        audio.play();
        this.setData({ isPlaying: true });
      } catch (e) {
        this._reloadAndPlay();
      }
    }
  },

  async _reloadAndPlay() {
    this._clearCachedAudioUrl();
    if (this._audio) {
      try { this._audio.stop(); } catch (e) {}
      try { if (typeof this._audio.destroy === 'function') this._audio.destroy(); } catch (e) {}
      this._audio = null;
    }
    this.setData({ musicReady: false, isPlaying: false });
    this._canplayFired = false;
    await this.loadAudio();
  },

  swiperChange(e) {
    const idx = e.detail.current;
    const totalCount = this.data.totalCount;
    const atLastPage = totalCount > 0 && idx >= totalCount - 1;
    this.setData({ currentIndex: idx, atLastPage });
  },

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

  onPreviewImage(e) {
    const index = e.currentTarget.dataset.index;
    if (typeof index !== 'number') return;
    const imageList = this.data.imageList || [];
    if (!imageList[index] || !imageList[index].url) return;
    const urls = imageList.filter((it) => !!it.url).map((it) => it.url);
    if (urls.length === 0) return;
    const current = imageList[index].url;
    wx.previewImage({
      current, urls,
      fail: () => {
        if (/^https?:/i.test(current)) {
          wx.previewImage({ current, urls: [current] });
        }
      }
    });
  },

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
        }
      } catch (e) {
        console.warn(`[adult-enroll] 加载 ${type} 图标失败:`, e);
      }
    };
    await loadOne('music', 'musicIconUrl');
    await loadOne('home', 'homeIconUrl');
  },

  goToFirstPage() {
    if (this.data.currentIndex === 0) return;
    this.setData({ currentIndex: 0 });
    setTimeout(() => {
      this.setData({ atLastPage: false });
    }, 450);
  },

  goBackToGuide() {
    wx.navigateTo({ url: '/packageEnroll/pages/enroll-guide/enroll-guide' });
  }
});