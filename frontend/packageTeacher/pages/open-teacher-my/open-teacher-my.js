const app = getApp();
const { createPage } = require('../../../utils/page-mixin');
const { tokenGet } = require('../../../utils/request');
const { STATIC_IMAGES } = require('../../../utils/static-images');
const { avatarMixin, avatarMixinData } = require('../../../utils/avatar-mixin');

const AUTH_CACHE_KEY = 'open_teacher_auth_cache';

createPage({
  ...avatarMixin,

  data: {
    userInfo: null,
    defaultAvatar: STATIC_IMAGES.defaultAvatar,
    version: '',
    ...avatarMixinData()
  },

  onLoad() {
    this.setData({ version: app.globalData.version });
  },

  onShow() {
    // 从缓存恢复
    const cached = wx.getStorageSync(AUTH_CACHE_KEY);
    if (cached && cached.expireTime > Date.now() && cached.userInfo) {
      app.globalData.userInfo = cached.userInfo;
      this.setData({ userInfo: cached.userInfo });
      this.loadAvatar();
      return;
    }

    // 未登录则跳转
    wx.redirectTo({
      url: '/packageTeacher/pages/open-teacher-login/open-teacher-login'
    });
  },
  // 注：校园反馈管理入口已迁移至 feedback-submit 顶部（依据 FeedbackAdmin 表权限显示），
  //     此处不再展示反馈管理菜单；其它身份（学生 / 中职教师 / 工作人员）也可
  //     通过 feedback-submit 进入管理后台

  handleLogout() {
    wx.showModal({
      title: '提示',
      content: '确定要退出登录吗？',
      success: (res) => {
        if (res.confirm) {
          wx.removeStorageSync(AUTH_CACHE_KEY);
          app.logoutOpenTeacher();
          this.setData({ userInfo: null });
          wx.redirectTo({
            url: '/packageTeacher/pages/open-teacher-login/open-teacher-login'
          });
        }
      }
    });
  },

  navigateTo(e) {
    const url = e.currentTarget.dataset.url;
    if (url) {
      wx.navigateTo({ url });
    }
  }
});
