/**
 * 招生简章图片缓存工具
 * 
 * 策略：渐进式加载 + 本地持久缓存
 * - 一开始就确定总数，用占位符填充，逐张替换
 * - 有缓存：秒开展示，后台静默检查更新
 * - 无缓存：请求列表后先展示占位，逐张下载替换
 * - 缓存有效期30分钟
 */

const { get } = require('./request');
const { resolveImageUrl } = require('./image-url');

const CACHE_EXPIRE = 30 * 60 * 1000;
const CACHE_KEY_PREFIX = 'brochure_cache_';
const FILE_CACHE_KEY_PREFIX = 'brochure_files_';

function getCache(type) {
  try {
    const data = wx.getStorageSync(CACHE_KEY_PREFIX + type);
    if (data && data.urls && data.timestamp) return data;
  } catch (e) {}
  return null;
}

function setCache(type, urls) {
  try { wx.setStorageSync(CACHE_KEY_PREFIX + type, { urls, timestamp: Date.now() }); }
  catch (e) {}
}

function getFileCache(type) {
  try { return wx.getStorageSync(FILE_CACHE_KEY_PREFIX + type) || {}; }
  catch (e) { return {}; }
}

function setFileCache(type, map) {
  try { wx.setStorageSync(FILE_CACHE_KEY_PREFIX + type, map); }
  catch (e) {}
}

function downloadToLocal(url) {
  return new Promise((resolve) => {
    wx.downloadFile({
      url,
      success: (res) => {
        if (res.statusCode === 200 && res.tempFilePath) {
          const fs = wx.getFileSystemManager();
          const ext = url.match(/\.(jpg|jpeg|png|gif)/i);
          const suffix = ext ? ext[0] : '.jpg';
          const localPath = `${wx.env.USER_DATA_PATH}/br_${Date.now()}_${Math.random().toString(36).slice(2, 6)}${suffix}`;
          try {
            fs.saveFileSync(res.tempFilePath, localPath);
            resolve(localPath);
            return;
          } catch (e) {}
        }
        resolve(null);
      },
      fail: () => resolve(null)
    });
  });
}

/**
 * 构建固定长度的图片数组，已缓存的填本地路径，未缓存的填空字符串
 * 同时清理已失效的文件缓存条目
 */
function buildImageArray(type, urls) {
  const fileCache = getFileCache(type);
  const fs = wx.getFileSystemManager();
  const result = [];
  let cacheChanged = false;

  for (const url of urls) {
    const localPath = fileCache[url];
    if (localPath) {
      try {
        fs.accessSync(localPath);
        result.push(localPath);
        continue;
      } catch (e) {
        // 本地文件丢失，清除无效缓存条目
        delete fileCache[url];
        cacheChanged = true;
      }
    }
    result.push(''); // 占位
  }

  // 有失效条目则更新缓存
  if (cacheChanged) {
    setFileCache(type, fileCache);
  }
  return result;
}

async function fetchRemoteList(type) {
  const res = await get(`/brochure/list/${type}`);
  // 后端返回相对路径（/brochure/image/...?t=&s=），统一拼 BASE_URL
  return (res || []).map(img => resolveImageUrl(img.url));
}

function cleanOldFiles(type, keepUrls) {
  const fileCache = getFileCache(type);
  const fs = wx.getFileSystemManager();
  const keepSet = new Set(keepUrls);
  const newCache = {};
  Object.keys(fileCache).forEach(url => {
    if (keepSet.has(url)) {
      newCache[url] = fileCache[url];
    } else {
      try { fs.unlinkSync(fileCache[url]); } catch (e) {}
    }
  });
  setFileCache(type, newCache);
}

/**
 * 逐张下载未缓存的图片，每完成一张回调
 */
async function downloadMissing(type, urls, images, onUpdate) {
  const fileCache = getFileCache(type);

  for (let i = 0; i < urls.length; i++) {
    if (images[i]) continue; // 已有本地路径，跳过

    const localPath = await downloadToLocal(urls[i]);
    if (localPath) {
      fileCache[urls[i]] = localPath;
      setFileCache(type, fileCache);
      onUpdate(i, localPath);
    } else {
      onUpdate(i, urls[i]); // 下载失败用远程URL兜底
    }
  }
}

/**
 * 核心方法
 * 
 * @param {string} type - open / vocational / adult
 * @param {object} callbacks
 *   onInit(totalCount, images) - 初始化：总数 + 图片数组（空字符串为占位）
 *   onUpdate(index, path) - 某张图片下载完成，替换占位
 *   onLoading(isLoading) - 首屏加载状态（第一张图片就绪前）
 *   onError(error) - 错误
 */
async function loadBrochureImages(type, { onInit, onUpdate, onLoading, onError }) {
  const cache = getCache(type);
  const isExpired = !cache || (Date.now() - cache.timestamp > CACHE_EXPIRE);

  // 有缓存：立即构建数组展示
  if (cache && cache.urls.length > 0) {
    const images = buildImageArray(type, cache.urls);
    onInit(cache.urls.length, images);

    // 检查第一张是否就绪
    const firstReady = images[0] !== '';
    onLoading && onLoading(!firstReady);

    // 下载缺失的图片
    const hasMissing = images.some(img => img === '');
    if (hasMissing) {
      await downloadMissing(type, cache.urls, images, (index, path) => {
        if (index === 0) onLoading && onLoading(false);
        onUpdate(index, path);
      });
    }

    // 缓存过期则后台静默刷新
    if (isExpired) {
      silentRefresh(type, cache.urls);
    }
    return;
  }

  // 无缓存：请求API
  onLoading && onLoading(true);

  try {
    const remoteUrls = await fetchRemoteList(type);
    setCache(type, remoteUrls);

    if (remoteUrls.length === 0) {
      onInit(0, []);
      onLoading && onLoading(false);
      return;
    }

    // 初始化固定长度占位数组
    const images = new Array(remoteUrls.length).fill('');
    onInit(remoteUrls.length, images);

    // 逐张下载，第一张完成后关闭loading
    await downloadMissing(type, remoteUrls, images, (index, path) => {
      if (index === 0) onLoading && onLoading(false);
      onUpdate(index, path);
    });
  } catch (error) {
    onLoading && onLoading(false);
    onError && onError(error);
  }
}

async function silentRefresh(type, oldUrls) {
  try {
    const remoteUrls = await fetchRemoteList(type);
    setCache(type, remoteUrls);
    if (oldUrls.join('|') !== remoteUrls.join('|') && remoteUrls.length > 0) {
      cleanOldFiles(type, remoteUrls);
    }
  } catch (e) {}
}

/**
 * 处理图片加载失败（binderror回调）
 * 当本地缓存图片损坏或不可用时，清除该缓存并回退到远程URL重新下载
 * 
 * @param {string} type - open / vocational / adult
 * @param {number} index - 图片索引
 * @param {function} onUpdate - 更新回调 (index, path)
 */
function handleImageError(type, index, onUpdate) {
  const cache = getCache(type);
  if (!cache || !cache.urls || !cache.urls[index]) return;

  const remoteUrl = cache.urls[index];
  const fileCache = getFileCache(type);

  // 清除失效的本地缓存
  if (fileCache[remoteUrl]) {
    const fs = wx.getFileSystemManager();
    try { fs.unlinkSync(fileCache[remoteUrl]); } catch (e) {}
    delete fileCache[remoteUrl];
    setFileCache(type, fileCache);
  }

  // 重新下载
  downloadToLocal(remoteUrl).then(localPath => {
    if (localPath) {
      fileCache[remoteUrl] = localPath;
      setFileCache(type, fileCache);
      onUpdate(index, localPath);
    } else {
      // 下载也失败，直接用远程URL兜底
      onUpdate(index, remoteUrl);
    }
  });
}

module.exports = { loadBrochureImages, handleImageError };