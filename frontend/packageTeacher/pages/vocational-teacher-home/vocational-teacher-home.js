const { createPage } = require('../../../utils/page-mixin');
const { tokenGet } = require('../../../utils/request');
const { STATIC_IMAGES } = require('../../../utils/static-images');
const { avatarMixin, avatarMixinData } = require('../../../utils/avatar-mixin');
const app = getApp();

const AUTH_CACHE_KEY = 'vocational_teacher_auth_cache';

createPage({
  ...avatarMixin,

  data: {
    defaultAvatar: STATIC_IMAGES.defaultAvatar,
    userInfo: {},
    canCounsel: false,
    pendingLeaveCount: 0,
    pendingPhotoCount: 0,
    ...avatarMixinData()
  },

  onLoad() {
    this.loadUserInfo();
  },

  onShow() {
    // 先尝试从缓存恢复用户信息
    const cached = wx.getStorageSync(AUTH_CACHE_KEY);
    if (cached && cached.expireTime > Date.now()) {
      const userInfo = cached.userInfo;
      app.globalData.userInfo = userInfo;
      this.setData({ userInfo, canCounsel: this._hasCounsel(userInfo) });
      this.loadStats();
      this.loadAvatar();
      return;
    }

    // 缓存无效时跳转到登录页
    wx.redirectTo({
      url: '/packageTeacher/pages/vocational-teacher-login/vocational-teacher-login'
    });
  },

  loadUserInfo() {
    const cached = wx.getStorageSync(AUTH_CACHE_KEY);
    if (cached && cached.expireTime > Date.now()) {
      const userInfo = cached.userInfo;
      app.globalData.userInfo = userInfo;
      this.setData({ userInfo, canCounsel: this._hasCounsel(userInfo) });
      return;
    }
    
    wx.redirectTo({
      url: '/packageTeacher/pages/vocational-teacher-login/vocational-teacher-login'
    });
  },

  async loadStats() {
    try {
      const res = await tokenGet('/vocational_teacher/stats');
      const canCounsel = !!(res && res.is_counsel) || this._hasCounsel(this.data.userInfo);
      this.setData({
        pendingLeaveCount: res.pending_leave_count || 0,
        pendingPhotoCount: res.pending_photo_count || 0,
        canCounsel
      });
      // 同步回缓存，避免下次 onShow 闪现
      try {
        const cached = wx.getStorageSync(AUTH_CACHE_KEY);
        if (cached && cached.userInfo) {
          cached.userInfo.is_counsel = canCounsel;
          wx.setStorageSync(AUTH_CACHE_KEY, cached);
        }
      } catch (e) {}
    } catch (error) {
      console.log('获取统计数据失败');
    }
  },

  // t_js_id 是逗号分隔的角色 id 字符串，包含 26 才有心理咨询管理权限
  _hasCounsel(userInfo) {
    if (!userInfo) return false;
    if (userInfo.is_counsel === true) return true;
    const raw = userInfo.t_js_id;
    if (raw === undefined || raw === null || raw === '') return false;
    try {
      const ids = String(raw).split(',').map(s => s.trim()).filter(s => s !== '');
      return ids.indexOf('26') >= 0;
    } catch (e) {
      return false;
    }
  },

  navigateTo(e) {
    const { url } = e.currentTarget.dataset;
    wx.navigateTo({ url });
  },

  handleLogout() {
    wx.showModal({
      title: '提示',
      content: '确定要退出登录吗？',
      success: (res) => {
        if (res.confirm) {
          wx.removeStorageSync(AUTH_CACHE_KEY);
          app.logoutVocationalTeacher();
          wx.reLaunch({
            url: '/pages/user-center/user-center'
          });
        }
      }
    });
  }
}, {
  requireAuth: true,
  userType: 'vocational_teacher'
});
