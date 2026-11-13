const { createPage } = require('../../../utils/page-mixin');
const { tokenGet } = require('../../../utils/request');
const app = getApp();

createPage({
  data: {
    coursesList: []
  },

  onLoad() {
    this.getCoursesList();
  },

  onShow() {
    const isLoggedIn = app.checkLogin();
    if (!isLoggedIn) {
      wx.navigateTo({
        url: '/pages/login/login'
      });
      return;
    }
  },

  // 获取课程列表
  async getCoursesList() {
    try{
      const resquest = await tokenGet('/course_management/get_course_list',{},{loadingTitle: '获取课程列表...'});
      this.setData({
        coursesList: resquest
      });
    }catch(err){
      this.showError(err.message || "获取课程列表失败");
    }
  },

  // 下拉刷新
  onPullDownRefresh() {
    this.getCoursesList();
    wx.stopPullDownRefresh();
  }
},{
  requireAuth: true // 🔑 方式1：通过选项指定需要登录
}); 