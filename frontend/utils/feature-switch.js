/**
 * 功能开关检查工具
 * 封装统一的开关校验逻辑，避免各页面重复代码
 */
const { get } = require('../utils/request');

/**
 * 检查功能是否开启，未开启则弹窗并返回上一页
 * @param {string} code - lw_feature_switch.code
 * @param {object} pageInstance - 页面 this 实例
 * @returns {Promise<boolean>} - true=已开启，false=已关闭
 */
async function checkFeatureSwitch(code, pageInstance) {
  try {
    const res = await get('/feature_switch/check/' + code, {}, { showLoading: false });
    // 兼容旧格式（直接返回 boolean）和新格式（{is_enabled, tip_message}）
    const data = (typeof res === 'object' && res !== null)
      ? res
      : { is_enabled: res === true, tip_message: '' };
    const isEnabled = data.is_enabled === true;
    if (!isEnabled) {
      const tipMsg = data.tip_message || '该功能目前暂停使用，请联系管理员开启';
      wx.showModal({
        title: '功能已关闭',
        content: tipMsg,
        showCancel: false,
        confirmText: '我知道了',
        success() {
          const pages = getCurrentPages();
          if (pages.length > 1) {
            wx.navigateBack();
          } else {
            wx.switchTab({ url: '/pages/home/home' });
          }
        }
      });
    }
    return isEnabled;
  } catch (e) {
    console.warn('[checkFeatureSwitch] 检查失败，默认放行:', code, e);
    return true;
  }
}

/**
 * 获取功能开关状态（同步，从首页缓存读取）
 * @param {string} code
 * @param {object} pageInstance - 页面 this 实例
 * @returns {boolean|null} - true/false 或 null（未缓存）
 */
function getCachedSwitch(code, pageInstance) {
  const switches = pageInstance.data._featureSwitches || {};
  if (switches[code] === undefined) return null;
  return switches[code];
}

module.exports = { checkFeatureSwitch, getCachedSwitch };
