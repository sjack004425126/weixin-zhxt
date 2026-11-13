var pageMixin = require('../../../utils/page-mixin');
var request = require('../../../utils/request');
var createPage = pageMixin.createPage;
var post = request.post;
var checkFeatureSwitch = require('../../../utils/feature-switch').checkFeatureSwitch;

// 认证缓存有效期（7天，单位毫秒）
var AUTH_CACHE_DURATION = 7 * 24 * 60 * 60 * 1000;
var AUTH_CACHE_KEY = 'admin_auth_cache';

createPage({
  data: {
    isAuthorized: false
  },

  onLoad: function() {
    // 二次判断：防止通过路径直接进入
    var self = this;
    checkFeatureSwitch('admin', this);

    // 检查本地缓存的认证状态
    var cached = wx.getStorageSync(AUTH_CACHE_KEY);
    if (cached && cached.expireTime > Date.now()) {
      this.setData({ isAuthorized: true });
      getApp().globalData.adminAuthorized = true;
      return;
    }
    
    // 检查全局认证状态
    var app = getApp();
    if (app.globalData.adminAuthorized) {
      this.setData({ isAuthorized: true });
    }
  },

  getPhoneNumber: function(e) {
    var that = this;
    if (e.detail.errMsg !== 'getPhoneNumber:ok') {
      this.showError('获取手机号失败，请重试');
      return;
    }

    var code = e.detail.code;
    if (!code) {
      this.showError('获取手机号失败，请重试');
      return;
    }

    // 调用后端认证接口，由后端验证手机号是否在白名单中
    post('/stats/auth', { code: code }, { loadingTitle: '验证中...' }).then(function(res) {
      if (res.authorized) {
        that.setData({ isAuthorized: true });
        getApp().globalData.adminAuthorized = true;
        // 缓存认证状态，7天有效
        wx.setStorageSync(AUTH_CACHE_KEY, {
          authorized: true,
          expireTime: Date.now() + AUTH_CACHE_DURATION
        });
        that.showSuccess('认证成功');
      } else {
        that.showError('您没有访问权限');
      }
    }).catch(function() {
      that.showError('认证失败，请重试');
    });
  },

  goToMonitor: function() {
    wx.navigateTo({
      url: '/packageAdmin/pages/monitor/monitor?fromAdmin=true'
    });
  },

  goToMajorManage: function() {
    wx.navigateTo({
      url: '/packageAdmin/pages/major-manage/major-manage?fromAdmin=true'
    });
  },

  logout: function() {
    var that = this;
    wx.showModal({
      title: '退出确认',
      content: '确定要退出管理中心吗？',
      success: function(res) {
        if (res.confirm) {
          that.setData({ isAuthorized: false });
          getApp().globalData.adminAuthorized = false;
          // 清除认证缓存
          wx.removeStorageSync(AUTH_CACHE_KEY);
        }
      }
    });
  }
});
