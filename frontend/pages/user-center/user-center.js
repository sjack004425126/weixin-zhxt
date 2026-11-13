const { createPage } = require('../../utils/page-mixin');
const authGuard = require('../../utils/auth-guard');
const app = getApp();

// wxml 的 data-role（带连字符）→ auth-guard 的 userType（带下划线）
// 集中映射，避免在 wxml 里改属性名
const ROLE_TO_USER_TYPE = {
  'open-student': 'open_student',
  'vocational-student': 'vocational_student',
  'vocational-teacher': 'vocational_teacher',
  'open-teacher': 'open_teacher'
};

createPage({
  data: {},

  onLoad: function() {
    // 不再自动跳转，让用户选择身份
  },

  goToRole(e) {
    const role = e.currentTarget.dataset.role;
    const userType = ROLE_TO_USER_TYPE[role];
    if (!userType) return;

    const config = authGuard.getRoleConfig(userType);
    if (!config) return;

    if (authGuard.isUserLoggedIn()
        && app.globalData.userInfo
        && app.globalData.userInfo.user_type === userType) {
      // 当前会话就是该端，直接进入
      wx.reLaunch({ url: config.homePage });
    } else if (authGuard.restoreByUserType(userType)) {
      // 切换端：先恢复该端的会话，再进入
      wx.reLaunch({ url: config.homePage });
    } else {
      // 未登录或不是该端会话，跳登录页
      wx.navigateTo({ url: config.loginPage });
    }
  },

  goToHome() {
    wx.switchTab({ url: '/pages/home/home' });
  }
});