const { createPage } = require('../../../utils/page-mixin');
const { tokenGet } = require('../../../utils/request');

createPage({
  data: {
    diplomaInfo: null,
  },

  onLoad() {
    this.getDiplomaStatus();
  },

  async getDiplomaStatus() {
    try {
      const res = await tokenGet('/student/get_diploma_status', {}, { loadingTitle: '获取毕业证状态...' });
      this.setData({ diplomaInfo: res });
    } catch (err) {
      this.showError(err.message || '获取毕业证状态失败');
    }
  },

  goHome() {
    wx.switchTab({ url: '/pages/home/home' });
  },

  onPullDownRefresh() {
    this.getDiplomaStatus().then(() => wx.stopPullDownRefresh());
  },
}, {
  requireAuth: true
});
