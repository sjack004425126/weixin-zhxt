/**
 * 网络请求层
 *
 * 设计原则：
 *   1. 单向依赖：request.js → auth-guard.js（auth-guard 不依赖 request）
 *   2. 登录态权威源：所有登录/userInfo/storage 逻辑只在 auth-guard.js
 *   3. 错误统一：reject AuthError，携带 message/errorType/code/data/response
 *   4. 自动 refresh：401 时自动用 refresh_token 换 token 并重试一次
 *   5. 请求去重：同 URL+同参数+短时间窗内复用同一个 Promise
 *   6. loading 计数：多个并发请求共享 loading，避免闪烁
 *   7. 配置不变性：retry 时不修改原始 config（避免 debug 困难）
 *   8. 热路径缓存：globalData.userInfo 用本地变量缓存
 *
 * errorType 枚举：
 *   NETWORK  - 网络错误（超时、DNS、断网）
 *   HTTP     - HTTP 状态码非 2xx
 *   AUTH     - 401/403 认证失败
 *   PARSE    - 响应解析失败
 *   BUSINESS - 业务失败（success=false 或 code != 0）
 *   NO_TOKEN - 调用时无 token
 */

const app = getApp();
const auth = require('./auth-guard');

// 环境配置
const ENV_CONFIG = {
  development: 'http://127.0.0.1:3050',
  production: 'https://m.qdndd.com.cn'
};
// const getCurrentEnv = () => 'development';
const getCurrentEnv = () => 'production';
const BASE_URL = ENV_CONFIG[getCurrentEnv()];
auth.setRequestBaseUrl(BASE_URL);

// 默认配置
const DEFAULT_CONFIG = {
  method: 'GET',
  header: { 'Content-Type': 'application/json' },
  timeout: 15000,
  showLoading: true,
  loadingTitle: '加载中...'
};

// ============================================================================
// 拦截器
// ============================================================================
const requestInterceptors = [];
const responseInterceptors = [];
const applyRequestInterceptors = (config) => {
  let result = config;
  for (const i of requestInterceptors) result = i(result) || result;
  return result;
};
const applyResponseInterceptors = (response) => {
  let result = response;
  for (const i of responseInterceptors) result = i(result) || result;
  return result;
};
const addRequestInterceptor = (i) => requestInterceptors.push(i);
const addResponseInterceptor = (i) => responseInterceptors.push(i);

// ============================================================================
// loading 计数：多个并发请求共享一个 loading
// ============================================================================
const _loadingRef = { count: 0, title: '' };
function _showLoading(title) {
  _loadingRef.count++;
  _loadingRef.title = title;
  if (_loadingRef.count === 1) {
    wx.showLoading({ title, mask: true });
  }
}
function _hideLoading() {
  _loadingRef.count = Math.max(0, _loadingRef.count - 1);
  if (_loadingRef.count === 0) {
    wx.hideLoading();
  }
}

// ============================================================================
// 请求去重：同 URL + 同方法 + 同参数 + 50ms 内复用
// ============================================================================
const _inflight = new Map();
const DEDUPE_WINDOW_MS = 50;
function _dedupeKey(method, url, data) {
  return `${method.toUpperCase()}::${url}::${JSON.stringify(data || null)}`;
}

// ============================================================================
// 错误对象：统一 errorType
// ============================================================================
function _error(message, errorType, extra = {}) {
  const e = new Error(message);
  e.message = message;
  e.errorType = errorType;
  e.isAuthError = errorType === 'AUTH' || errorType === 'NO_TOKEN';
  if (extra.code !== undefined) e.code = extra.code;
  if (extra.data !== undefined) e.data = extra.data;
  if (extra.response !== undefined) e.response = extra.response;
  return e;
}

// ============================================================================
// 解析后端响应格式
// 返回 { ok: true, data } 或 { ok: false, error: string }
// error 就是后端 msg/message 字符串，页面直接拿去 wx.showToast 打印
// 不用 throw：避免 try/catch 开销，调用更明确
// ============================================================================
function _parseResponse(responseData) {
  if (!responseData) return { ok: true, data: null };
  // 后端统一格式：{ success, msg/message, data }
  if (typeof responseData.success === 'boolean') {
    if (responseData.success) {
      return { ok: true, data: responseData.data !== undefined ? responseData.data : null };
    }
    return { ok: false, error: responseData.msg || responseData.message || '请求失败' };
  }
  // 兼容格式：{ code, msg/message, data }，code === 0 成功
  if (typeof responseData.code === 'number') {
    if (responseData.code === 0) {
      return { ok: true, data: responseData.data !== undefined ? responseData.data : null };
    }
    return { ok: false, error: responseData.msg || responseData.message || '请求失败' };
  }
  // 既无 success 又无 code：当作原始数据直接透出
  return { ok: true, data: responseData };
}

// ============================================================================
// 网络层错误信息映射
// ============================================================================
const _NETWORK_MSG = {
  timeout: '请求超时，网络可能存在问题，请稍后再试',
  cancel: '请求已取消，请稍后再试',
  fail: '网络可能存在问题，请稍后再试',
  default: '网络请求失败'
};
function _mapNetworkError(errMsg) {
  if (!errMsg) return _NETWORK_MSG.default;
  if (errMsg.includes('timeout')) return _NETWORK_MSG.timeout;
  if (errMsg.includes('cancel')) return _NETWORK_MSG.cancel;
  if (errMsg.includes('fail')) return _NETWORK_MSG.fail;
  return _NETWORK_MSG.default;
}

// ============================================================================
// 核心：单次请求发送（不重试）
// 内部使用：handleRequest / 401 重试 / 上传都走这里
// ============================================================================
function _doRequest({ config, fullUrl, resolve, reject }) {
  wx.request({
    ...config,
    url: fullUrl,
    success: (res) => {
      if (config.showLoading) _hideLoading();

      // 401: 交给外层处理（refresh + 重试）
      if (res.statusCode === 401) {
        return reject(_error('token 过期', 'AUTH', { response: res.data }));
      }

      if (res.statusCode < 200 || res.statusCode >= 300) {
        return reject(_error(`请求失败，状态码：${res.statusCode}`, 'HTTP', { response: res.data }));
      }

      // 业务解析（非 throw 版本）
      const data = applyResponseInterceptors(res.data);
      const parsed = _parseResponse(data);
      if (parsed.ok) resolve(parsed.data);
      else reject(parsed.error);
    },
    fail: (err) => {
      if (config.showLoading) _hideLoading();
      reject(_error(_mapNetworkError(err && err.errMsg), 'NETWORK'));
    }
  });
}

// ============================================================================
// 主请求函数：处理 token、loading、去重、401 refresh
// ============================================================================
function handleRequest(options, needToken = false) {
  return new Promise((resolve, reject) => {
    const config = { ...DEFAULT_CONFIG, ...options };
    const finalConfig = applyRequestInterceptors(config);

    // 默认 GET 去重，POST 不去重避免副作用
    const dedupe = finalConfig.dedupe !== false && finalConfig.method === 'GET';

    // 防御：把 data 里所有 undefined 字段删掉
    // 原因：wx.request GET 时 data 自动拼 query，undefined 会被序列化为字符串 "undefined"，
    //      后端 int 字段收到 "undefined" → 422。
    if (finalConfig.data && typeof finalConfig.data === 'object' && !Array.isArray(finalConfig.data)) {
      const cleaned = {};
      for (const k of Object.keys(finalConfig.data)) {
        if (finalConfig.data[k] !== undefined && finalConfig.data[k] !== null) {
          cleaned[k] = finalConfig.data[k];
        }
      }
      finalConfig.data = cleaned;
    }

    if (needToken) {
      const userInfo = app.globalData.userInfo;
      if (!userInfo || !userInfo.token) {
        return reject(_error('Token 不存在，无法发起请求', 'NO_TOKEN'));
      }
      finalConfig.header = { ...finalConfig.header, Authorization: 'Bearer ' + userInfo.token };
    }

    if (finalConfig.showLoading) _showLoading(finalConfig.loadingTitle);

    const fullUrl = finalConfig.url.startsWith('http') ? finalConfig.url : BASE_URL + finalConfig.url;

    // 401 重试：捕获外层错误，refresh + 重试
    // 使用 _bindRetry 包装 resolve/reject
    const wrapped = _bindRetry({
      config: finalConfig, fullUrl, resolve, reject,
      onRetry: (newToken, retryResolve, retryReject) => {
        // 关键：retry 时不修改原 finalConfig.header
        const retryConfig = {
          ...finalConfig,
          header: { ...finalConfig.header, Authorization: 'Bearer ' + newToken }
        };
        _doRequest({ config: retryConfig, fullUrl, resolve: retryResolve, reject: retryReject });
      }
    });

    // 请求去重：只对 GET
    if (dedupe) {
      const key = _dedupeKey(finalConfig.method, fullUrl, finalConfig.data);
      const inflight = _inflight.get(key);
      if (inflight && (Date.now() - inflight.ts) < DEDUPE_WINDOW_MS) {
        if (finalConfig.showLoading) _hideLoading();
        inflight.promise.then(resolve, reject);
        return;
      }
      const p = new Promise((res, rej) => {
        wrapped._send(res, rej);
      });
      _inflight.set(key, { promise: p, ts: Date.now() });
      const cleanup = () => {
        const cur = _inflight.get(key);
        if (cur && cur.promise === p) _inflight.delete(key);
      };
      p.then(cleanup, cleanup);
      p.then(resolve, reject);
      return;
    }

    wrapped._send(resolve, reject);
  });
}

// 401 重试包装：把原始 resolve/reject 转换为"refresh 后重试"模式
function _bindRetry({ config, fullUrl, onRetry, resolve, reject }) {
  let retried = false;
  return {
    _send: (res, rej) => {
      _doRequest({
        config, fullUrl,
        resolve: res,
        reject: (err) => {
          // 只对 401 重试一次
          if (err && err.errorType === 'AUTH' && !retried) {
            retried = true;
            auth.refreshAccessToken()
              .then((newToken) => onRetry(newToken, res, rej))
              .catch(() => {
                auth.handleAuthExpired();
                rej(_error('登录已过期，请重新登录', 'AUTH'));
              });
            return;
          }
          rej(err);
        }
      });
    },
    resolve, reject
  };
}

// ============================================================================
// 便捷方法
// ============================================================================
const requestPromise = (options) => handleRequest(options, options.needToken === true);
const tokenRequest = (options) => handleRequest(options, true);

const get = (url, data = {}, options = {}) => requestPromise({ url, method: 'GET', data, ...options });
const post = (url, data = {}, options = {}) => requestPromise({ url, method: 'POST', data, ...options });
const deleteRequest = (url, data = {}, options = {}) => requestPromise({ url, method: 'DELETE', data, needToken: options.needToken, ...options });
const tokenGet = (url, data = {}, options = {}) => tokenRequest({ url, method: 'GET', data, ...options });
const tokenPost = (url, data = {}, options = {}) => tokenRequest({ url, method: 'POST', data, ...options });
const tokenDelete = (url, data = {}, options = {}) => tokenRequest({ url, method: 'DELETE', data, ...options });

// ============================================================================
// 文件上传（统一走 _doUpload）
// ============================================================================
function _handleUploadResponse(res, resolve, reject) {
  if (res.statusCode < 200 || res.statusCode >= 300) {
    if (res.statusCode === 401) {
      return reject(_error('token 过期', 'AUTH', { response: res.data }));
    }
    return reject(_error(`请求失败，状态码：${res.statusCode}`, 'HTTP', { response: res.data }));
  }
  let data;
  try {
    data = JSON.parse(res.data);
  } catch (e) {
    return reject(_error('解析响应数据失败', 'PARSE'));
  }
  const processed = applyResponseInterceptors(data);
  const parsed = _parseResponse(processed);
  if (parsed.ok) resolve(parsed.data);
  else reject(parsed.error);
}

function _doUpload({ config, fullUrl, token, onRetry, resolve, reject }) {
  // token 必须已注入到 config.header
  if (token) {
    config.header = { ...(config.header || {}), Authorization: 'Bearer ' + token };
  }
  wx.uploadFile({
    ...config,
    url: fullUrl,
    success: (res) => {
      if (config.showLoading) _hideLoading();
      if (res.statusCode === 401) {
        // 走重试
        return auth.refreshAccessToken()
          .then((newToken) => onRetry(newToken))
          .catch(() => {
            auth.handleAuthExpired();
            reject(_error('登录已过期，请重新登录', 'AUTH'));
          });
      }
      _handleUploadResponse(res, resolve, reject);
    },
    fail: () => {
      if (config.showLoading) _hideLoading();
      reject(_error('文件上传失败', 'NETWORK'));
    }
  });
}

const tokenUploadFile = (options) => new Promise((resolve, reject) => {
  const config = { ...DEFAULT_CONFIG, ...options };
  const userInfo = app.globalData.userInfo;
  if (!userInfo || !userInfo.token) {
    return reject(_error('Token 不存在，无法发起请求', 'NO_TOKEN'));
  }
  if (config.showLoading) _showLoading(config.loadingTitle || '上传中...');
  const fullUrl = config.url.startsWith('http') ? config.url : BASE_URL + config.url;
  let retried = false;

  const doUpload = (token) => {
    _doUpload({
      config, fullUrl, token,
      onRetry: (newToken) => {
        if (retried) return;
        retried = true;
        // retry 不修改原 config
        const retryConfig = { ...config, header: { ...config.header, Authorization: 'Bearer ' + newToken } };
        _doUpload({ config: retryConfig, fullUrl, token: null, onRetry: () => {}, resolve, reject });
      },
      resolve, reject
    });
  };
  doUpload(userInfo.token);
});

const uploadFile = (options) => new Promise((resolve, reject) => {
  const config = { ...DEFAULT_CONFIG, ...options };
  if (config.showLoading) _showLoading(config.loadingTitle || '上传中...');
  const fullUrl = config.url.startsWith('http') ? config.url : BASE_URL + config.url;
  _doUpload({
    config, fullUrl, token: null,
    onRetry: () => {},
    resolve,
    reject: (err) => {
      if (config.showLoading) _hideLoading();
      reject(err);
    }
  });
});

// ============================================================================
// 预设配置
// ============================================================================
const PRESETS = {
  silent: { showLoading: false },
  quick: { timeout: 5000, loadingTitle: '请稍候...' },
  upload: { timeout: 30000, loadingTitle: '上传中...' },
  important: { timeout: 30000, loadingTitle: '处理中，请稍候...' }
};

const silentPost = (url, data = {}, options = {}) => post(url, data, { ...PRESETS.silent, ...options });
const silentGet = (url, data = {}, options = {}) => get(url, data, { ...PRESETS.silent, ...options });
const quickPost = (url, data = {}, options = {}) => post(url, data, { ...PRESETS.quick, ...options });

// ============================================================================
// 重试（指数退避）
// ============================================================================
const retryRequest = (requestFn, maxRetries = 3, delay = 1000) => new Promise((resolve, reject) => {
  let retries = 0;
  const attempt = () => {
    requestFn()
      .then(resolve)
      .catch((err) => {
        retries++;
        if (retries < maxRetries) {
          setTimeout(attempt, delay * retries);
        } else {
          reject(err);
        }
      });
  };
  attempt();
});

// ============================================================================
// 导出
// ============================================================================
module.exports = {
  // 基础
  requestPromise,
  tokenRequest,
  get,
  post,
  deleteRequest,
  tokenGet,
  tokenPost,
  tokenDelete,
  tokenUploadFile,
  uploadFile,

  // 预设
  silentPost,
  silentGet,
  quickPost,

  // 工具
  retryRequest,
  addRequestInterceptor,
  addResponseInterceptor,

  // 配置
  BASE_URL,
  PRESETS,
  ENV_CONFIG,
  getCurrentEnv
};
