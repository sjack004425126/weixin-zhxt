const app = getApp();
const { createPage } = require('../../../utils/page-mixin');
const { STATIC_IMAGES } = require('../../../utils/static-images');
const { avatarMixin, avatarMixinData } = require('../../../utils/avatar-mixin');

createPage({
  ...avatarMixin,

  data: {
    defaultAvatar: STATIC_IMAGES.defaultAvatar,
    userInfo: null,
    avatarUrl: '',
    version:'',
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
    this.setData({
      userInfo: app.globalData.userInfo,
      version:app.globalData.version
    });
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
   * 生命周期函数--监听页面显示
   */
  onShow() {
    // 从独立存储恢复用户信息
    const cachedUserInfo = wx.getStorageSync('open_student_userInfo');
    if (cachedUserInfo && cachedUserInfo.user_type === 'open_student') {
      app.globalData.userInfo = cachedUserInfo;
      this.setData({
        userInfo: cachedUserInfo
      });
      this.loadAvatar();
      return;
    }

    // 未登录则跳转登录页
    wx.redirectTo({
      url: '/pages/login/login'
    });
  },


  // 退出登录
  handleLogout() {
    wx.showModal({
      title: '提示',
      content: '确定要退出登录吗？',
      success: (res) => {
        if (res.confirm) {
          app.logoutOpenStudent();
          // 重置页面数据
          this.setData({
            userInfo: null
          });
          wx.redirectTo({
            url: '/pages/login/login'
          });
        }
      }
    });
  },

  navigateToExamNotice() {
    wx.navigateTo({
      url: '/packageStudent/pages/exam-notice/exam-notice'
    });
  },

  // 页面跳转方法
  navigateTo(e) {
    const url = e.currentTarget.dataset.url;
    if (url) {
      wx.navigateTo({
        url: url
      });
    }
  },



  // 获取用户的信息
  getWx_UserInfo() {
    return new Promise((resolve, reject) => {
      wx.getUserProfile({
        desc: "用于完善用户资料",
        success: (res) => {
          resolve(res);
        },
        fail: err => reject(err)
      });
    });
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
  userType: 'open_student'
})