const { createPage } = require('../../../utils/page-mixin');

createPage({
  data: {
    finderUserName: 'sphZ7xkhVEBm6IP', // 视频号ID
    feedId: 'export/UzFfAgtgekIEAQAAAAAAs80X1t2a0gAAAAstQy6ubaLX4KHWvLEZgBPE9aEgBTZ2ZbOJzNPgMJp7E8GoXUAOU9IM_Dfh5HY_', // 视频ID
  },

  onLoad(options) {
    // 直接打开视频号
    wx.openChannelsActivity({
      finderUserName: this.data.finderUserName,
      feedId: this.data.feedId,
      success: () => {
        console.log('视频号打开成功');
        // 打开成功后返回上一页
        wx.navigateBack();
      },
      fail: (err) => {
        console.error('打开视频号失败:', err);
        wx.showToast({
          title: '打开视频号失败',
          icon: 'none'
        });
        wx.navigateBack();
      }
    });
  },

  // 视频播放错误处理
  binderror(e) {
    console.error('视频播放出错', e.detail);
    wx.showToast({
      title: '视频播放出错',
      icon: 'none'
    });
  }
}); 