const { createPage } = require('../../../utils/page-mixin');
const { tokenGet } = require('../../../utils/request');
const { STATIC_IMAGES } = require('../../../utils/static-images');
const { avatarMixin, avatarMixinData } = require('../../../utils/avatar-mixin');
const app = getApp();
createPage({
  ...avatarMixin,

  /**
   * 页面的初始数据
   */
  data: {
    defaultAvatar: STATIC_IMAGES.defaultAvatar,
    userInfo: null,
    avatarUrl: '',
    dormInfo: '',
    serviceBtnX: 0,
    serviceBtnY: 0,
    screenWidth: 0,
    screenHeight: 0,
    ...avatarMixinData()
  },

  /**
   * 生命周期函数--监听页面加载
   */
  onLoad() {
    const userInfo = app.getUserInfo();
    this.setData({
      userInfo: userInfo
    });
    
    const { windowWidth, windowHeight } = wx.getWindowInfo();
    const screenWidth = windowWidth;
    const screenHeight = windowHeight;
    const btnWidth = 120 * (screenWidth / 750);
    
    this.setData({
      screenWidth: screenWidth,
      screenHeight: screenHeight,
      serviceBtnX: screenWidth - btnWidth,
      serviceBtnY: screenHeight - 300
    });
  },

  /**
   * 生命周期函数--监听页面初次渲染完成
   */
  onReady() {

  },

  /**
   * 生命周期函数--监听页面显示
   */
  onShow() {
    // 从独立存储恢复用户信息
    const cachedUserInfo = wx.getStorageSync('vocational_student_userInfo');
    if (cachedUserInfo && cachedUserInfo.user_type === 'vocational_student') {
      app.globalData.userInfo = cachedUserInfo;
      this.setData({
        userInfo: cachedUserInfo
      });
      this.loadDormInfo();
      this.loadAvatar();
      return;
    }

    // 未登录则跳转登录页
    wx.redirectTo({
      url: '/packageVocational/pages/vocational-login/vocational-login'
    });
  },

  async loadDormInfo() {
    try {
      const res = await tokenGet('/student/stay/dorm_info');
      if (res) {
        this.setData({ dormInfo: res.full_name || '' });
      }
    } catch (e) {}
  },

  // 退出登录
  handleLogout() {
    wx.showModal({
      title: '提示',
      content: '确定要退出登录吗？',
      success: (res) => {
        if (res.confirm) {
          app.logoutVocationalStudent();
          // 重置页面数据
          this.setData({
            userInfo: null
          });
          wx.redirectTo({
            url: '/packageVocational/pages/vocational-login/vocational-login'
          });
        }
      }
    });
  },

  // 页面跳转方法（学籍异常时除退出登录外不可用）
  navigateTo(e) {
    const userInfo = this.data.userInfo;
    if (userInfo && userInfo.xs_xjzt != 1) {
      wx.showToast({ title: '学籍异常，暂无法使用该功能', icon: 'none' });
      return;
    }
    const url = e.currentTarget.dataset.url;
    if (url) {
      wx.navigateTo({
        url: url
      });
    }
  },



  handleServiceBtnChange(e) {
    this.currentBtnX = e.detail.x;
    this.currentBtnY = e.detail.y;
  },

  handleServiceBtnTouchEnd() {
    const x = this.currentBtnX || this.data.serviceBtnX;
    const y = this.currentBtnY || this.data.serviceBtnY;
    const { screenWidth } = this.data;
    const centerX = screenWidth / 2;
    
    const btnWidth = 120 * (screenWidth / 750);
    
    let targetX;
    if (x < centerX) {
      targetX = 0;
    } else {
      targetX = screenWidth - btnWidth;
    }
    
    this.setData({
      serviceBtnX: targetX,
      serviceBtnY: y
    });
  },

  handleServiceBtnTap() {
    wx.navigateTo({
      url: '/pages/kf-chat/kf-chat'
    });
  },

}, {
  requireAuth: true,
  userType: 'vocational_student'
})