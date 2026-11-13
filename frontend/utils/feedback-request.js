/**
 * feedback-request.js
 *
 * 反馈模块专属 HTTP 工具，与主应用登录体系完全隔离：
 *  - token 只从 feedback_auth_cache 读取，不依赖 app.globalData.userInfo
 *  - 收到 401 时自动用 refresh_token 换新 access_token 并重试（最多 1 次）
 *  - 刷新失败则跳转 feedback-login，不触发主应用 logout
 */

const { BASE_URL } = require('./request');

const FEEDBACK_AUTH_CACHE_KEY = 'feedback_auth_cache';
// 注意：feedback-login 页面注册在 packageAdmin 分包下，必须带 /packageAdmin 前缀，
// 否则 wx.redirectTo 找不到页面会静默失败导致白屏
const FEEDBACK_LOGIN_URL = '/packageAdmin/pages/feedback-login/feedback-login';

// 防止并发刷新：同时只跑一个 refresh 请求
let _refreshingPromise = null;

/**
 * 用 refresh_token 换新 access_token，并更新缓存。
 * 返回新 access_token 字符串，失败则 reject。
 *
 * 失败时主动跳转登录页（refresh_token 过期或无效场景），避免用户被困在死循环里
 */
const refreshFeedbackToken = () => {
  if (_refreshingPromise) return _refreshingPromise;

  const redirectToLogin = () => {
    try {
      wx.removeStorageSync(FEEDBACK_AUTH_CACHE_KEY);
    } catch (e) {}
    wx.showToast({ title: '登录已过期，请重新登录', icon: 'none', duration: 2000 });
    setTimeout(() => {
      wx.redirectTo({ url: FEEDBACK_LOGIN_URL });
    }, 500);
  };

  _refreshingPromise = new Promise((resolve, reject) => {
    const cached = wx.getStorageSync(FEEDBACK_AUTH_CACHE_KEY);
    if (!cached || !cached.refresh_token) {
      _refreshingPromise = null;
      redirectToLogin();
      return reject('无 refresh_token，需重新登录');
    }

    wx.request({
      url: BASE_URL + '/feedback/auth/refresh',
      method: 'POST',
      data: { refresh_token: cached.refresh_token },
      header: { 'Content-Type': 'application/json' },
      timeout: 10000,
      success: (res) => {
        _refreshingPromise = null;
        const d = res.data;
        if (res.statusCode === 200 && d && d.success && d.data && d.data.token) {
          const newCached = { ...cached, token: d.data.token, refresh_token: d.data.refresh_token || cached.refresh_token };
          wx.setStorageSync(FEEDBACK_AUTH_CACHE_KEY, newCached);
          resolve(d.data.token);
        } else {
          redirectToLogin();
          reject((d && d.msg) || 'refresh 失败');
        }
      },
      fail: () => {
        _refreshingPromise = null;
        // 网络错误不主动跳（用户可能瞬时断网，让上层业务决定）
        reject('网络错误，无法刷新 token');
      }
    });
  });

  return _refreshingPromise;
};

/**
 * 核心请求（支持 401 自动刷新重试）
 */
const _redirectToFeedbackLogin = () => {
  try { wx.removeStorageSync(FEEDBACK_AUTH_CACHE_KEY); } catch (e) {}
  wx.showToast({ title: '请先登录', icon: 'none', duration: 2000 });
  setTimeout(() => {
    wx.redirectTo({ url: FEEDBACK_LOGIN_URL });
  }, 500);
};

const _doRequest = (method, url, data, options, isRetry) => {
  return new Promise((resolve, reject) => {
    const cached = wx.getStorageSync(FEEDBACK_AUTH_CACHE_KEY);
    if (!cached || !cached.token) {
      _redirectToFeedbackLogin();
      return reject('Token 不存在，请重新登录');
    }

    const fullUrl = url.startsWith('http') ? url : BASE_URL + url;
    const showLoading = options.showLoading !== false;

    if (showLoading) {
      wx.showLoading({ title: options.loadingTitle || '加载中...', mask: true });
    }

    wx.request({
      url: fullUrl,
      method,
      data,
      header: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + cached.token
      },
      timeout: options.timeout || 15000,
      success: (res) => {
        if (showLoading) wx.hideLoading();

        if (res.statusCode === 401 && !isRetry) {
          refreshFeedbackToken()
            .then(() => _doRequest(method, url, data, options, true))
            .then(resolve)
            .catch(() => {
              // refreshFeedbackToken 内部失败时已跳转登录，这里只需 reject
              reject('登录已过期，请重新登录');
            });
          return;
        }

        if (res.statusCode < 200 || res.statusCode >= 300) {
          return reject(`请求失败，状态码：${res.statusCode}`);
        }

        const d = res.data;
        if (d && typeof d.success === 'boolean') {
          d.success ? resolve(d.data) : reject(d.msg || '请求失败');
        } else {
          resolve(d);
        }
      },
      fail: (err) => {
        if (showLoading) wx.hideLoading();
        const msg = err && err.errMsg;
        if (msg && msg.includes('timeout')) return reject('请求超时，请稍后重试');
        reject('网络请求失败');
      }
    });
  });
};

/**
 * 文件上传（支持 401 自动刷新重试）
 */
const _doUpload = (options, isRetry) => {
  return new Promise((resolve, reject) => {
    const cached = wx.getStorageSync(FEEDBACK_AUTH_CACHE_KEY);
    if (!cached || !cached.token) {
      _redirectToFeedbackLogin();
      return reject('Token 不存在，请重新登录');
    }

    const fullUrl = options.url.startsWith('http') ? options.url : BASE_URL + options.url;
    const showLoading = options.showLoading !== false;

    if (showLoading) {
      wx.showLoading({ title: options.loadingTitle || '上传中...', mask: true });
    }

    wx.uploadFile({
      url: fullUrl,
      filePath: options.filePath,
      name: options.name || 'file',
      formData: options.formData || {},
      header: { 'Authorization': 'Bearer ' + cached.token },
      success: (res) => {
        if (showLoading) wx.hideLoading();

        if (res.statusCode === 401 && !isRetry) {
          refreshFeedbackToken()
            .then(() => _doUpload(options, true))
            .then(resolve)
            .catch(() => {
              // refreshFeedbackToken 内部失败时已跳转登录，这里只需 reject
              reject('登录已过期，请重新登录');
            });
          return;
        }

        if (res.statusCode < 200 || res.statusCode >= 300) {
          return reject(`上传失败，状态码：${res.statusCode}`);
        }

        try {
          const d = typeof res.data === 'string' ? JSON.parse(res.data) : res.data;
          if (d && typeof d.success === 'boolean') {
            d.success ? resolve(d.data) : reject(d.msg || '上传失败');
          } else {
            resolve(d);
          }
        } catch (e) {
          reject('解析响应失败');
        }
      },
      fail: (err) => {
        if (showLoading) wx.hideLoading();
        reject((err && err.errMsg) || '文件上传失败');
      }
    });
  });
};

const feedbackGet = (url, data = {}, options = {}) =>
  _doRequest('GET', url, data, options, false);

const feedbackPost = (url, data = {}, options = {}) =>
  _doRequest('POST', url, data, options, false);

const feedbackUploadFile = (options) => _doUpload(options, false);

module.exports = { feedbackGet, feedbackPost, feedbackUploadFile, refreshFeedbackToken };
