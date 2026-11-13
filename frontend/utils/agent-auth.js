/**
 * Agent Token Manager (智能客服认证管理)
 *
 * 本模块与登录守卫 (utils/auth-guard.js) **职责正交，互不依赖**：
 *   - auth-guard.js：管理 4 端业务登录态（open_student / vocational_student /
 *     vocational_teacher / open_teacher），token 与用户身份绑定，存到各端独立 storage
 *   - agent-auth.js（当前文件）：管理"智能客服"子系统的应用级 OAuth 凭证。
 *     不依赖业务登录态，所有用户共用一对 app_key/app_secret，token 与小程序绑定。
 *
 * 使用范围：仅 pages/kf-chat/kf-chat.js（智能客服页面）使用。
 * 设计要点：
 *   1. 双 token 体系（OAuth client_credentials 风格）
 *      - App Token：小程序共享一个，向 /agent/auth/app-token 申请
 *      - User Token：每个用户一份，向 /agent/auth/user-token 申请（依赖 App Token）
 *   2. 三级缓存 + 提前续期（避免临界过期）
 *      - 内存缓存 → wx.storageSync 持久化 → 网络请求
 *      - App Token 在过期前 300s 主动续期；User Token 在过期前 60s 主动续期
 *   3. 401 自动 refresh + retry 1 次（指数退避风格的简单实现）
 *   4. 退出业务登录不会清空 agent token（两套体系独立）
 *
 * 为何不合并到 auth-guard：
 *   - 概念混淆（业务 token vs 应用 token）
 *   - 存储位置不同
 *   - clearLoginCache() 等操作不应误清 agent token
 *
 * All requests go directly to weixin.qdndd.com.cn
 */

// TODO: 上线前改回 'https://weixin.qdndd.com.cn/api/v1'
// var AGENT_API_BASE = 'http://172.16.100.102:3088/api/v1';
var AGENT_API_BASE = 'https://weixin.qdndd.com.cn/api/v1';
var APP_KEY = 'wxapp_student_service_2026';
var APP_SECRET = 'A8F3D9E2C7B4F1A6E5D9C3B8A7F2E1D4';

var _appToken = null;
var _appTokenExpireTime = 0;
var _userTokenCache = {};

// Get App Token
function getAppToken() {
  return new Promise(function(resolve, reject) {
    var now = Date.now();
    if (_appToken && now < _appTokenExpireTime) return resolve(_appToken);

    var cached = wx.getStorageSync('agent_app_token');
    var cachedExpire = wx.getStorageSync('agent_app_token_expire');
    if (cached && cachedExpire && now < cachedExpire) {
      _appToken = cached;
      _appTokenExpireTime = cachedExpire;
      return resolve(cached);
    }

    wx.request({
      url: AGENT_API_BASE + '/agent/auth/app-token',
      method: 'POST',
      data: { app_key: APP_KEY, app_secret: APP_SECRET },
      header: { 'Content-Type': 'application/json' },
      success: function(res) {
        if (res.statusCode === 200 && res.data && res.data.success) {
          _appToken = res.data.app_token;
          _appTokenExpireTime = now + (res.data.expires_in - 300) * 1000;
          wx.setStorageSync('agent_app_token', _appToken);
          wx.setStorageSync('agent_app_token_expire', _appTokenExpireTime);
          resolve(_appToken);
        } else {
          reject((res.data && res.data.message) || 'App Token failed');
        }
      },
      fail: function(err) { reject(err.errMsg || 'network error'); }
    });
  });
}

// Get User Token
function getUserToken(userId) {
  return new Promise(function(resolve, reject) {
    var now = Date.now();

    var cached = _userTokenCache[userId];
    if (cached && now < cached.expireTime) return resolve(cached.accessToken);

    var storageKey = 'agent_user_token_' + userId;
    try {
      var stored = wx.getStorageSync(storageKey);
      if (stored && stored.accessToken && now < stored.expireTime) {
        _userTokenCache[userId] = stored;
        return resolve(stored.accessToken);
      }
    } catch (e) {}

    // Get fresh user token via app token
    getAppToken().then(function(appToken) {
      wx.request({
        url: AGENT_API_BASE + '/agent/auth/user-token',
        method: 'POST',
        header: { 'Content-Type': 'application/json', 'X-App-Token': appToken },
        data: { user_id: userId },
        success: function(res) {
          if (res.statusCode === 200 && res.data && res.data.success) {
            var tokenData = {
              accessToken: res.data.access_token,
              refreshToken: res.data.refresh_token,
              expireTime: now + (res.data.expires_in - 60) * 1000
            };
            _userTokenCache[userId] = tokenData;
            wx.setStorageSync(storageKey, tokenData);
            resolve(tokenData.accessToken);
          } else {
            reject((res.data && res.data.message) || 'User Token failed');
          }
        },
        fail: function(err) { reject(err.errMsg || 'network error'); }
      });
    }).catch(reject);
  });
}

// Refresh user token
function _refreshUserToken(userId) {
  var stored = _userTokenCache[userId];
  if (!stored || !stored.refreshToken) {
    // No refresh token, get new one
    delete _userTokenCache[userId];
    wx.removeStorageSync('agent_user_token_' + userId);
    return getUserToken(userId);
  }

  return new Promise(function(resolve, reject) {
    getAppToken().then(function(appToken) {
      wx.request({
        url: AGENT_API_BASE + '/agent/auth/refresh-token',
        method: 'POST',
        header: { 'Content-Type': 'application/json', 'X-App-Token': appToken },
        data: { user_id: userId, refresh_token: stored.refreshToken },
        success: function(res) {
          if (res.statusCode === 200 && res.data && res.data.success) {
            var now = Date.now();
            var tokenData = {
              accessToken: res.data.access_token,
              refreshToken: stored.refreshToken,
              expireTime: now + (res.data.expires_in - 60) * 1000
            };
            _userTokenCache[userId] = tokenData;
            wx.setStorageSync('agent_user_token_' + userId, tokenData);
            resolve(tokenData.accessToken);
          } else {
            // Refresh failed, get new token
            delete _userTokenCache[userId];
            wx.removeStorageSync('agent_user_token_' + userId);
            getUserToken(userId).then(resolve).catch(reject);
          }
        },
        fail: function() {
          delete _userTokenCache[userId];
          wx.removeStorageSync('agent_user_token_' + userId);
          getUserToken(userId).then(resolve).catch(reject);
        }
      });
    }).catch(reject);
  });
}

// Request with auto token + 401 retry (max 1 retry)
function agentRequest(userId, options) {
  return new Promise(function(resolve, reject) {
    getUserToken(userId).then(function(accessToken) {
      wx.request({
        url: options.url,
        method: options.method || 'GET',
        data: options.data,
        header: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + accessToken },
        success: function(res) {
          if (res.statusCode === 401) {
            // Token expired, refresh and retry once
            _refreshUserToken(userId).then(function(newToken) {
              wx.request({
                url: options.url,
                method: options.method || 'GET',
                data: options.data,
                header: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + newToken },
                success: function(retryRes) {
                  if (retryRes.statusCode >= 200 && retryRes.statusCode < 300) {
                    resolve(retryRes.data);
                  } else {
                    reject(retryRes.data || 'HTTP ' + retryRes.statusCode);
                  }
                },
                fail: function(err) { reject(err.errMsg || 'request failed'); }
              });
            }).catch(function() { reject('auth expired'); });
          } else if (res.statusCode >= 200 && res.statusCode < 300) {
            resolve(res.data);
          } else {
            reject(res.data || 'HTTP ' + res.statusCode);
          }
        },
        fail: function(err) { reject(err.errMsg || 'network error'); }
      });
    }).catch(reject);
  });
}

module.exports = {
  getUserToken: getUserToken,
  agentRequest: agentRequest,
  AGENT_API_BASE: AGENT_API_BASE
};
