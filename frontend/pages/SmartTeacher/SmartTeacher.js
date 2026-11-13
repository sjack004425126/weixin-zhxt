const { createPage } = require('../../utils/page-mixin');
const { get } = require('../../utils/request');

createPage({
  data: {
    vrUrl: ''  // 从数据库获取，默认为空
  },

  onLoad() {
    this.loadVrUrl();
  },

  async loadVrUrl() {
    try {
      const data = await get('/config/vr_url');
      if (data && data.value) {
        this.setData({ vrUrl: data.value });
      }
    } catch (err) {
      // 配置获取失败不打扰用户，留默认值
      if (err.isAuthError) return;
      console.error('获取VR配置失败:', err);
    }
  },

  backToHome() {
    wx.navigateBack()
  }
})
