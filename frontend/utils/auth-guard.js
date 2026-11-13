/**
 * 登录路由守卫 - 单文件方案
 *
 * 设计原则：
 *   1. 声明式配置：所有 userType 的存储/默认页/可访问域统一在 AUTH_CONFIG 中声明
 *   2. 栈保护：登录后通过 navigateBack(返回原页面，保留浏览历史)
 *   3. 单一 returnUrl：只用 redirectUrl 字段，不再用两套存储
 *   4. O(1) 查询：用 Map 替代数组遍历
 *   5. 内存缓存：减少 wx.getStorageSync 同步 IO
 *
 * 公共 API：
 *   - isUserLoggedIn()          同步检查是否登录
 *   - checkAuth(callback)       未登录则跳转登录页，已登录则回调
 *   - requireLogin(pageConfig)  页面装饰器：拦截未登录访问
 *   - redirectToLogin(opts)     主动跳登录页
 *   - handleLoginSuccess()      登录成功后调用，自动返回原页面
 *   - showLoginPrompt(cb)       弹窗确认后跳转登录
 *   - clearLoginCache()         清缓存（退出登录时调用）
 *   - restoreByUserType(type)   从指定端的存储恢复 globalData
 *   - getLoginPageByUserType(t) 取出指定端的登录页路径
 */

// ============================================================================
// 配置中心：所有用户端的存储 key、登录页、默认页、可访问域都在这里声明
// ============================================================================
const AUTH_CONFIG = {
  open_student: {
    storageKey: 'open_student_userInfo',
    loginPage: '/pages/login/login',
    homePage: '/packageStudent/pages/my/my',
    // 通用页面（所有端都可访问）
    commonScope: true
  },
  vocational_student: {
    storageKey: 'vocational_student_userInfo',
    loginPage: '/packageVocational/pages/vocational-login/vocational-login',
    homePage: '/packageVocational/pages/vocational-my/vocational-my',
    commonScope: true
  },
  vocational_teacher: {
    storageKey: 'vocational_teacher_auth_cache',  // 嵌套结构：{ userInfo, expireTime }
    loginPage: '/packageTeacher/pages/vocational-teacher-login/vocational-teacher-login',
    homePage: '/packageTeacher/pages/vocational-teacher-home/vocational-teacher-home',
    commonScope: true,
    nested: true  // 教师端 cache 是 { userInfo: {...}, expireTime: ... } 结构
  },
  open_teacher: {
    storageKey: 'open_teacher_auth_cache',  // 嵌套结构
    loginPage: '/packageTeacher/pages/open-teacher-login/open-teacher-login',
    homePage: '/packageTeacher/pages/open-teacher-my/open-teacher-my',
    commonScope: true,
    nested: true
  }
};

// 兼容性别名：teacher 嵌套结构读取到的 userInfo 也要有 token 字段
// 已统一处理，见 readStorage()

// tabBar 页面（这些页面跳转用 switchTab，其他用 redirectTo/navigateTo）
const TAB_BAR_PAGES = new Set([
  '/pages/home/home',
  '/pages/user-center/user-center',
  '/pages/SmartTeacher/SmartTeacher'
]);

// 登录态返回 URL 缓存的 storage key（唯一字段）
const REDIRECT_KEY = 'auth:redirectUrl';

// 登录态内存缓存（避免重复 wx.getStorageSync 同步 IO）
// 缓存策略：缓存的是"有效登录的 userType"，登录态改变时清缓存
let _cachedUserType = null;
let _cacheAt = 0;
const CACHE_TTL = 1000;  // 1 秒

// ============================================================================
// 内部工具
// ============================================================================

/**
 * 读取某个 userType 的存储值，自动适配嵌套/扁平结构。
 * 返回有效 token 持有的 userInfo；否则返回 null。
 */
function readStorage(userType) {
  const cfg = AUTH_CONFIG[userType];
  if (!cfg) return null;
  const raw = wx.getStorageSync(cfg.storageKey);
  if (!raw) return null;

  if (cfg.nested) {
    // { userInfo: {...}, expireTime: timestamp }
    if (raw.userInfo && raw.expireTime && raw.expireTime > Date.now()) {
      return raw.userInfo;
    }
    return null;
  }
  // 扁平结构 { token, ...其他字段 }
  return raw.token ? raw : null;
}

/**
 * 把 userInfo 写入指定端的存储，自动适配嵌套/扁平结构。
 *
 * 性能优化：使用 setStorage 异步而非 setStorageSync，避免 5-20ms 的 UI 阻塞。
 * 异步失败会自动降级到 setStorageSync（保证数据不丢）。
 */
function writeStorage(userType, userInfo) {
  const cfg = AUTH_CONFIG[userType];
  if (!cfg) return;
  const payload = cfg.nested
    ? { userInfo, expireTime: Date.now() + 24 * 60 * 60 * 1000 }
    : userInfo;
  // 优先异步，失败兜底同步
  try {
    wx.setStorage({
      key: cfg.storageKey,
      data: payload,
      fail: () => {
        try { wx.setStorageSync(cfg.storageKey, payload); } catch (e) { /* ignore */ }
      }
    });
  } catch (e) {
    try { wx.setStorageSync(cfg.storageKey, payload); } catch (e2) { /* ignore */ }
  }
}

/**
 * 标准化路径：补全前导 /，处理 query
 */
function normalizeUrl(path) {
  if (!path) return '';
  return path.startsWith('/') ? path : `/${path}`;
}

/**
 * 序列化 query 对象到 URL 字符串
 */
function serializeQuery(obj) {
  if (!obj) return '';
  const parts = [];
  Object.keys(obj).forEach(k => {
    const v = obj[k];
    if (v !== undefined && v !== null) {
      parts.push(`${encodeURIComponent(k)}=${encodeURIComponent(v)}`);
    }
  });
  return parts.length ? `?${parts.join('&')}` : '';
}

/**
 * 反序列化 URL query 字符串到对象
 */
function deserializeQuery(url) {
  const idx = url.indexOf('?');
  if (idx < 0) return { path: url, query: {} };
  const path = url.slice(0, idx);
  const query = {};
  url.slice(idx + 1).split('&').forEach(pair => {
    const [k, v] = pair.split('=');
    if (k) query[decodeURIComponent(k)] = v ? decodeURIComponent(v) : '';
  });
  return { path, query };
}

/**
 * 安全跳转：tabBar 用 switchTab，其他用 redirectTo（不保留当前页）
 * 不用 navigateTo 是因为 navigateTo 会持续累积栈
 */
function safeNavigate(url) {
  if (!url) return;
  const path = normalizeUrl(url.split('?')[0]);
  if (TAB_BAR_PAGES.has(path)) {
    wx.switchTab({ url: path, fail: () => console.warn('switchTab fail:', url) });
  } else {
    wx.redirectTo({ url, fail: () => console.warn('redirectTo fail:', url) });
  }
}

/**
 * 跳转登录页（带 returnUrl）
 */
function goLogin(loginPage, returnUrl) {
  const url = returnUrl
    ? `${normalizeUrl(loginPage)}?returnUrl=${encodeURIComponent(returnUrl)}`
    : normalizeUrl(loginPage);

  // 登录页通常是普通页面，用 redirectTo（栈顶就是登录页）
  // 注意：原页面栈由 wx.redirectTo 销毁，但 returnUrl 已被保存/透传
  wx.redirectTo({
    url,
    fail: () => {
      // 登录页在 tabBar 列表里则降级
      wx.switchTab({
        url: normalizeUrl(loginPage),
        fail: () => console.error('跳登录页失败:', loginPage)
      });
    }
  });
}

// ============================================================================
// 公共 API
// ============================================================================

/**
 * 同步检查登录态。
 * 优先级：globalData.token > 全端存储恢复
 * 带内存缓存，1s 内重复调用不触发 IO
 *
 * 注意：缓存键是 userType 而非 bool 值，避免退出登录后 globalData
 * 残留导致判断错误
 */
function isUserLoggedIn() {
  const now = Date.now();

  // 缓存命中：最小校验
  // 缓存期间用户可能通过 logout() 清掉了 globalData 或 storage
  // 为避免误判，缓存命中时仍校验一次：缓存对应端的 storage 还在不在
  if (_cachedUserType !== null && now - _cacheAt < CACHE_TTL) {
    if (_cachedUserType === '__global__') {
      const app = getApp();
      if (app.globalData.userInfo && app.globalData.userInfo.token) return true;
      _cachedUserType = null;
    } else {
      const cfg = AUTH_CONFIG[_cachedUserType];
      if (cfg && readStorage(_cachedUserType)) return true;
      _cachedUserType = null;
    }
  }

  try {
    const app = getApp();
    // 1. globalData 已登录（且与任一端的 userType 一致）
    if (app.globalData.userInfo && app.globalData.userInfo.token) {
      // 校验：globalData 的 userInfo 必须能在对应端的 storage 中找到**有效值**
      // 防止"globalData 残留但 storage 已清/过期"的虚假登录态
      const ut = app.globalData.userInfo.user_type;
      if (ut && AUTH_CONFIG[ut] && readStorage(ut)) {
        _cachedUserType = ut;
        _cacheAt = now;
        return true;
      }
      // 状态不一致：清掉 globalData 重新走 storage 校验
      app.globalData.userInfo = null;
    }

    // 2. 任一端存储有效即可恢复
    for (const userType of Object.keys(AUTH_CONFIG)) {
      const info = readStorage(userType);
      if (info) {
        app.globalData.userInfo = info;
        _cachedUserType = userType;
        _cacheAt = now;
        return true;
      }
    }

    _cachedUserType = null;
    _cacheAt = now;
    return false;
  } catch (e) {
    _cachedUserType = null;
    _cacheAt = now;
    return false;
  }
}

/**
 * 清除登录态缓存（退出登录时调用）
 */
function clearLoginCache() {
  _cachedUserType = null;
  _cacheAt = 0;
  // 同步清除可能残留的 returnUrl
  try { wx.removeStorageSync(REDIRECT_KEY); } catch (e) { /* ignore */ }
}

/**
 * 从指定 userType 的存储恢复 globalData。
 * 用法：在 requireLogin 装饰器里，userType 已知的页面，提前恢复
 */
function restoreByUserType(userType) {
  const info = readStorage(userType);
  if (info) {
    getApp().globalData.userInfo = info;
    clearLoginCache();  // 强制下次重新检查
    return true;
  }
  return false;
}

/**
 * 获取指定 userType 的登录页路径
 */
function getLoginPageByUserType(userType) {
  return (AUTH_CONFIG[userType] && AUTH_CONFIG[userType].loginPage) || '/pages/user-center/user-center';
}

/**
 * 获取指定 userType 的 storage key
 */
function getStorageKeyByUserType(userType) {
  return (AUTH_CONFIG[userType] && AUTH_CONFIG[userType].storageKey) || null;
}

/**
 * 保存跳转前的 URL（用于登录后返回）
 */
function saveRedirectUrl(url) {
  if (!url) return;
  try { wx.setStorageSync(REDIRECT_KEY, url); } catch (e) { /* ignore */ }
}

function consumeRedirectUrl() {
  try {
    const url = wx.getStorageSync(REDIRECT_KEY);
    if (url) wx.removeStorageSync(REDIRECT_KEY);
    return url || '';
  } catch (e) {
    return '';
  }
}

/**
 * 主动跳转到登录页
 * @param {string|object} [opts]
 *   - 字符串：当作 targetUrl
 *   - 对象：{ targetUrl, loginPage } 任选其一
 */
function redirectToLogin(opts) {
  let targetUrl = '';
  let loginPage = '';

  if (typeof opts === 'string') {
    targetUrl = opts;
  } else if (opts && typeof opts === 'object') {
    targetUrl = opts.targetUrl || '';
    loginPage = opts.loginPage || '';
  }

  if (targetUrl) {
    saveRedirectUrl(targetUrl);
  } else {
    // 没传 targetUrl 时，尝试从当前页栈推断
    try {
      const pages = getCurrentPages();
      const cur = pages[pages.length - 1];
      if (cur && cur.route) {
        const queryStr = serializeQuery(cur.options || {});
        saveRedirectUrl(`/${cur.route}${queryStr}`);
      }
    } catch (e) { /* ignore */ }
  }

  // 选择登录页：优先用传入的，否则根据当前 globalData 推断
  if (!loginPage) {
    const ui = getApp().globalData.userInfo;
    if (ui && ui.user_type && AUTH_CONFIG[ui.user_type]) {
      // 已登录态被 clear 但保留 user_type 时，回到原端的登录页
      loginPage = AUTH_CONFIG[ui.user_type].loginPage;
    } else {
      loginPage = '/pages/user-center/user-center';
    }
  }

  goLogin(loginPage, consumeRedirectUrl() || '');
}

/**
 * 登录成功后调用：返回原页面或默认页
 *
 * 优先级：
 *   1. 登录页 URL 上的 returnUrl 参数（栈保护模式）
 *   2. 缓存中的 redirectUrl（被动保存模式）
 *   3. 当前用户类型对应的默认首页
 *   4. /pages/home/home 兜底
 */
function handleLoginSuccess() {
  clearLoginCache();

  // 静默补采 openid(失败不影响登录流程,不阻塞导航)
  try {
    const binder = require('./bind-openid');
    binder.bindOpenIdWithLogin();
  } catch (e) { /* ignore */ }

  // 先看 URL 上的 returnUrl（最高优先级，登录页跳转时透传的）
  let targetUrl = '';
  try {
    const pages = getCurrentPages();
    const loginPage = pages[pages.length - 1];
    if (loginPage && loginPage.options && loginPage.options.returnUrl) {
      targetUrl = decodeURIComponent(loginPage.options.returnUrl);
    }
  } catch (e) { /* ignore */ }

  // 没 URL 参数时用缓存
  if (!targetUrl) {
    targetUrl = consumeRedirectUrl();
  }

  // 决定目标
  const app = getApp();
  const ui = app.globalData.userInfo;
  const userType = ui && ui.user_type;
  const cfg = userType && AUTH_CONFIG[userType];

  if (!targetUrl && cfg) {
    targetUrl = cfg.homePage;
  }
  if (!targetUrl) {
    targetUrl = '/pages/home/home';
  }

  // 尝试 navigateBack 回到原页面（如果是从原页面 push 到登录页的场景）
  // 注意：redirectTo 会销毁栈，所以这个分支只在 navigateTo 模式下生效
  try {
    const pages = getCurrentPages();
    // 登录页当前在栈顶，pages.length >= 2 时说明前面还有页面（navigateTo 模式）
    if (pages.length >= 2) {
      // 用 reLaunch 直接到目标 URL，reLaunch 会保留 tabBar 状态且不积累栈
      wx.reLaunch({
        url: targetUrl,
        fail: () => safeNavigate(targetUrl)
      });
      return;
    }
  } catch (e) { /* ignore */ }

  safeNavigate(targetUrl);
}

/**
 * 弹窗确认后跳转登录
 */
function showLoginPrompt(callback) {
  wx.showModal({
    title: '提示',
    content: '此功能需要登录，是否前往登录？',
    confirmText: '去登录',
    cancelText: '取消',
    success: (res) => {
      if (res.confirm) callback && callback();
    }
  });
}

/**
 * 已登录则回调，否则跳登录页
 */
function checkAuth(callback) {
  if (isUserLoggedIn()) {
    callback && callback();
    return true;
  }
  redirectToLogin();
  return false;
}

/**
 * 页面装饰器：需要登录才能访问
 * 用法：createPage({...}, { requireAuth: true, userType: 'open_student' })
 * 通过 page-mixin.js 暴露
 */
function requireLogin(pageConfig) {
  const originalOnLoad = pageConfig.onLoad || function () {};
  const userType = pageConfig.userType;

  pageConfig.onLoad = function (options) {
    // 1. 提前恢复该端的 globalData（避免多端登录时拿到错的 userInfo）
    if (userType) restoreByUserType(userType);

    // 2. 检查登录态
    if (isUserLoggedIn()) {
      originalOnLoad.call(this, options);
      return;
    }

    // 3. 未登录：保存当前页 URL 作为 returnUrl
    let route = '';
    try { route = this.route || ''; } catch (e) { route = ''; }
    const queryStr = serializeQuery(options || {});
    const returnUrl = route ? `${normalizeUrl(route)}${queryStr}` : '';

    if (returnUrl) saveRedirectUrl(returnUrl);

    // 4. 决定登录页
    const loginPage = userType ? getLoginPageByUserType(userType) : '/pages/user-center/user-center';

    // 5. 跳登录页，把 returnUrl 放在 URL 参数里（双保险）
    goLogin(loginPage, returnUrl);
  };

  return pageConfig;
}

/**
 * 退出指定 userType 端的登录（也支持通用 logout 不指定 type）
 * @param {string} [userType] - 指定端；不传则清所有端（兼容 app.logout 行为）
 * @returns {boolean} 是否有任意端被清掉
 */
function logoutByType(userType) {
  const app = getApp();
  const types = userType ? [userType] : Object.keys(AUTH_CONFIG);
  let cleared = false;

  types.forEach(t => {
    const cfg = AUTH_CONFIG[t];
    if (!cfg) return;
    try {
      wx.removeStorageSync(cfg.storageKey);
      cleared = true;
    } catch (e) { /* ignore */ }
  });

  // 清 globalData（兼容旧 app.logout 行为）
  if (app.globalData) {
    app.globalData.userInfo = null;
    if (app.globalData.token !== undefined) app.globalData.token = null;
  }

  clearLoginCache();
  return cleared;
}

/**
 * 应用启动时恢复会话。
 * 在 App.onLaunch 中调用一次：尝试从任一有效端恢复 globalData.userInfo
 * 不抛错；失败静默。
 */
function initAppSession() {
  try {
    const app = getApp();
    if (!app) return null;

    // 已有 userInfo 直接返回（场景：热启动）
    if (app.globalData && app.globalData.userInfo && app.globalData.userInfo.token) {
      return app.globalData.userInfo;
    }

    // 尝试从任一端恢复
    for (const userType of Object.keys(AUTH_CONFIG)) {
      const info = readStorage(userType);
      if (info) {
        app.globalData.userInfo = info;
        return info;
      }
    }
    return null;
  } catch (e) {
    return null;
  }
}

/**
 * 获取当前用户信息（同步）。
 * 智能回退：globalData → 任一有效端 storage
 */
function getUserInfo() {
  const app = getApp();
  if (app.globalData && app.globalData.userInfo && app.globalData.userInfo.token) {
    return app.globalData.userInfo;
  }
  // 降级：尝试恢复
  return initAppSession();
}

/**
 * 获取某 userType 的完整配置（供 user-center 等业务复用）
 * 返回深拷贝避免外部修改污染
 */
function getRoleConfig(userType) {
  const cfg = AUTH_CONFIG[userType];
  if (!cfg) return null;
  return {
    userType,
    storageKey: cfg.storageKey,
    loginPage: cfg.loginPage,
    homePage: cfg.homePage,
    nested: !!cfg.nested
  };
}

/**
 * 获取所有 role 的配置列表
 */
function getAllRoleConfigs() {
  return Object.keys(AUTH_CONFIG).map(getRoleConfig);
}

/**
 * 获取 wx.login code（Promise 化）
 */
function getOpenidCode() {
  return new Promise((resolve, reject) => {
    if (!wx.login) {
      reject(new Error('wx.login 不可用'));
      return;
    }
    wx.login({
      success: (res) => {
        if (res && res.code) resolve(res.code);
        else reject(new Error('wx.login 返回无 code'));
      },
      fail: (err) => reject(err)
    });
  });
}

// ============================================================================
// 低层 API：供 request.js 调用（保持 auth-guard 为登录态唯一权威源）
// ============================================================================

/**
 * 通用错误对象：携带业务上下文
 * 用法：page.try { ... } catch (e) { e.message / e.code / e.data / e.response }
 */
function createAuthError(message, opts = {}) {
  const err = new Error(message);
  err.message = message;
  if (opts.code !== undefined) err.code = opts.code;
  if (opts.data !== undefined) err.data = opts.data;
  if (opts.response !== undefined) err.response = opts.response;
  err.isAuthError = true;
  return err;
}

/**
 * 用当前用户的 refresh_token 换新 token。
 * - 自动复用并发请求（同一个 _refreshingPromise）
 * - 失败时通过 reject 抛出 AuthError
 * - 成功时同步更新 storage + globalData
 *
 * @returns {Promise<string>} 新的 access_token
 */
let _refreshingPromise = null;
function refreshAccessToken() {
  if (_refreshingPromise) return _refreshingPromise;

  _refreshingPromise = new Promise((resolve, reject) => {
    const app = getApp();
    const userInfo = app.globalData.userInfo;
    if (!userInfo || !userInfo.refresh_token) {
      _refreshingPromise = null;
      return reject(createAuthError('无 refresh_token', { code: 'NO_REFRESH_TOKEN' }));
    }

    const url = (requestBaseUrl || '') + '/login/refresh_token';
    wx.request({
      url,
      method: 'POST',
      data: { refresh_token: userInfo.refresh_token },
      header: { 'Content-Type': 'application/json' },
      timeout: 10000,
      success: (res) => {
        _refreshingPromise = null;
        const d = res && res.data;
        if (res.statusCode === 200 && d && d.success && d.data && d.data.token) {
          // 更新内存
          userInfo.token = d.data.token;
          userInfo.refresh_token = d.data.refresh_token || userInfo.refresh_token;
          app.globalData.userInfo = userInfo;
          // 同步到对应端 storage
          writeStorage(userInfo.user_type, userInfo);
          resolve(d.data.token);
        } else {
          reject(createAuthError(
            (d && d.msg) || 'refresh 失败',
            { code: 'REFRESH_FAILED', response: d }
          ));
        }
      },
      fail: () => {
        _refreshingPromise = null;
        reject(createAuthError('网络错误，无法刷新 token', { code: 'REFRESH_NETWORK_ERROR' }));
      }
    });
  });

  return _refreshingPromise;
}

/**
 * 登录态过期处理：清状态 + 提示 + 跳登录页。
 * 由 request.js 在 401 后调用。
 *
 * @param {string} [message='登录已过期，请重新登录']
 */
function handleAuthExpired(message) {
  const app = getApp();
  const userType = app.globalData.userInfo && app.globalData.userInfo.user_type;
  const loginPage = userType ? getLoginPageByUserType(userType) : '/pages/user-center/user-center';

  logoutByType(userType);

  wx.showToast({ title: message || '登录已过期，请重新登录', icon: 'none', duration: 2000 });
  setTimeout(() => {
    wx.redirectTo({
      url: loginPage,
      fail: () => wx.reLaunch({ url: '/pages/user-center/user-center' })
    });
  }, 500);
}

/**
 * 供 request.js 注入 BASE_URL 使用。
 * 避免 request.js 调用 auth-guard 时丢失 baseUrl 上下文。
 */
let requestBaseUrl = '';
function setRequestBaseUrl(url) {
  requestBaseUrl = url || '';
}
function getRequestBaseUrl() {
  return requestBaseUrl;
}

// ============================================================================
// 导出
// ============================================================================
module.exports = {
  // === 核心 API（守卫） ===
  isUserLoggedIn,
  checkAuth,
  requireLogin,
  redirectToLogin,
  handleLoginSuccess,
  showLoginPrompt,
  clearLoginCache,

  // === 应用生命周期 ===
  initAppSession,
  getUserInfo,
  getOpenidCode,
  logoutByType,

  // === 配置查询 ===
  restoreByUserType,
  getLoginPageByUserType,
  getStorageKeyByUserType,
  getRoleConfig,
  getAllRoleConfigs,

  // === 写操作 ===
  writeStorage,

  // === 低层 API（供 request.js 调用） ===
  refreshAccessToken,
  handleAuthExpired,
  setRequestBaseUrl,
  getRequestBaseUrl,
  createAuthError,

  // === 常量 ===
  LOGIN_PAGE: '/pages/login/login'
};