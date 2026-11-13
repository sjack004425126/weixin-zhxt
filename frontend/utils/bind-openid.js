/**
 * 静默补采 openid。
 *
 * 设计原则:
 *   1. 登录成功之后调用,失败一律吞掉,不阻塞登录流程
 *   2. 通过当前用户态(user_type)决定后端端点,调用方无需关心
 *   3. 用 lazy require 引 auth-guard,避免 require 循环
 */

const ENDPOINTS = {
  vocational_student: '/bind_openid/zz',
  open_student: '/bind_openid/zs',
};

/**
 * 静默绑定 openid。失败/异常一律吞掉。
 *
 * @param {string} code - 小程序 wx.login 拿到的 code
 * @returns {Promise<{bound:boolean, already?:boolean, skipped?:string}>}
 */
async function bindOpenIdSilent(code) {
  if (!code) return { bound: false, skipped: 'no_code' };

  // 延迟 require:防循环依赖
  let auth, tokenPost;
  try {
    auth = require('./auth-guard');
    tokenPost = require('./request').tokenPost;
  } catch (e) {
    console.warn('[bindOpenIdSilent] require 失败:', e && e.message);
    return { bound: false, skipped: 'require_error' };
  }

  const ui = auth.getUserInfo();
  const ep = ui && ENDPOINTS[ui.user_type];
  if (!ep) return { bound: false, skipped: 'unknown_user_type' };

  try {
    const data = await tokenPost(ep, { code }, { showLoading: false, timeout: 8000 });
    return {
      bound: !!(data && data.bound),
      already: !!(data && data.already),
    };
  } catch (e) {
    console.warn('[bindOpenIdSilent] 静默失败:', e && e.message);
    return { bound: false, skipped: 'error' };
  }
}

/**
 * 一站式"拿 code + 绑定",给登录成功处一行调用。
 * 失败/无 wx.login 环境都安全返回。
 */
async function bindOpenIdWithLogin() {
  let auth;
  try { auth = require('./auth-guard'); } catch (e) { return { bound: false }; }
  let code = null;
  try {
    code = await auth.getOpenidCode();
  } catch (e) {
    return { bound: false, skipped: 'wx_login_failed' };
  }
  return bindOpenIdSilent(code);
}

module.exports = {
  bindOpenIdSilent,
  bindOpenIdWithLogin,
  ENDPOINTS,
};
