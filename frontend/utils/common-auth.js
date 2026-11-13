/**
 * 通用手机号快捷认证工具（zhpt-new 全子系统共享）
 *
 * 设计目标：
 *   - 任意子系统（vocational-new-payment / student-info / feedback-login /
 *     user-center）的页面在 onLoad / onShow 时调用 tryAutoVerify()
 *   - 命中 7 天缓存 → 直接走"已登录"分支（0 点击）
 *   - 未命中 → 走原 verifyAndLogin() 流程，验证成功后自动写缓存
 *   - 用户点"重选身份"按钮 → 调用 clearCache()
 *
 * 依赖：
 *   - utils/request.js 提供 post()
 *   - 业务 subject 字符串与服务端 ALL_SUBJECTS 保持一致
 */

const request = require('./request');

// ============================================================================
// 业务身份（subject）常量。后端 common/phone_cache.py 中的 ALL_SUBJECTS 同步。
// ============================================================================
const SUBJECT = {
  VOCATIONAL_PAYMENT: 'vocational_new_payment',
  STUDENT_INFO:       'student_info',
  FEEDBACK:           'feedback',
  USER_CENTER:        'user_center'
};

// 缓存有效状态（前端内存；与服务端 Redis 同步）
let _memCachedPhone = null;   // { pure_phone, masked_phone, role, subject, sfzh, xm, verified_at, expires_in }

// ============================================================================
// 内部工具
// ============================================================================

/**
 * 调用 wx.login() 拿 code。
 * 注意：每次都现拿，不要缓存（code 一次有效）。
 */
function wxLogin() {
  return new Promise((resolve, reject) => {
    if (typeof wx === 'undefined' || !wx.login) {
      reject(new Error('当前环境不支持 wx.login'));
      return;
    }
    wx.login({
      success: (res) => {
        if (res && res.code) {
          resolve(res.code);
        } else {
          reject(new Error('wx.login 未返回 code'));
        }
      },
      fail: (err) => reject(err)
    });
  });
}

/**
 * 检查后端缓存。
 * 返回：
 *   - 命中：{ cached: true, pure_phone, masked_phone, role, ... }
 *   - 未命中：{ cached: false }
 *   - 异常：reject
 */
function fetchCachedVerify(subject) {
  return wxLogin()
    .then((loginCode) => request.post('/auth/get_cached_verify', {
      login_code: loginCode,
      subject: subject
    }))
    .then((resp) => {
      if (resp && resp.success && resp.data && resp.data.cached) {
        _memCachedPhone = resp.data;
        return resp.data;
      }
      _memCachedPhone = null;
      return { cached: false };
    });
}

/**
 * 把手机号授权写入后端 7 天缓存（不返回业务 token）。
 * 典型用法：在用户完成 wx.getPhoneNumber 后调用。
 *
 * 参数：
 *   subject:   业务身份
 *   phoneCode: <button open-type="getPhoneNumber"> 返回的 e.detail.code
 *   role:      'self' | 'parent'
 */
function writeCache(subject, phoneCode, role = 'self') {
  return wxLogin()
    .then((loginCode) => request.post('/auth/verify_phone', {
      login_code: loginCode,
      phone_code: phoneCode,
      subject: subject,
      role: role
    }))
    .then((resp) => {
      if (resp && resp.success) {
        _memCachedPhone = resp.data || null;
      }
      return resp;
    });
}

/**
 * 主动清除缓存（"重选身份"按钮调用）。
 */
function clearCache() {
  return wxLogin()
    .then((loginCode) => request.post('/auth/clear_cached_verify', {
      login_code: loginCode
    }))
    .then((resp) => {
      _memCachedPhone = null;
      try {
        wx.setStorageSync('phone_cache_local_marker', '');
      } catch (e) { /* ignore */ }
      return resp;
    });
}

/**
 * 同步获取内存中的缓存（最近一次 fetchCachedVerify / writeCache 结果）。
 * 适用：UI 立即渲染"已登录：138****1234"卡片。
 */
function getMemCachedPhone() {
  return _memCachedPhone;
}

function isCached() {
  return !!(_memCachedPhone && _memCachedPhone.cached);
}

// ============================================================================
// 导出
// ============================================================================
module.exports = {
  SUBJECT,
  wxLogin,
  fetchCachedVerify,
  writeCache,
  clearCache,
  getMemCachedPhone,
  isCached
};
