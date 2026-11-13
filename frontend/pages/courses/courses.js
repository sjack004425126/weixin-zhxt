const { createPage } = require('../../utils/page-mixin');
const { API } = require('../../utils/api');

createPage({
  data: {
    loading: true,
    courses: []
  },

  onLoad() {
    this.fetchCourses();
  },

  onShow() {
    // 已登录态由 createPage({requireAuth:true}) 守卫，这里只负责刷新
    if (this.isLoggedIn()) {
      this.fetchCourses();
    }
  },

  // 下拉刷新
  onPullDownRefresh() {
    this.fetchCourses().finally(() => wx.stopPullDownRefresh());
  },

  // 获取课程信息
  async fetchCourses() {
    // 走统一 HTTP 层：自动加 token / 401 refresh / 请求去重 / loading 计数 / 业务错误归一
    try {
      const data = await this.http.tokenGet(API.COURSES.GET_LIST);
      const list = (data && data.courses) || [];
      this.setData({ courses: list });
    } catch (err) {
      if (err.isAuthError) return; // 401 已被守卫接管
      this.showError(err.message || '获取课程失败');
      this.setData({ courses: [] });
    } finally {
      this.setData({ loading: false });
    }
  }
}, {
  requireAuth: true,
  userType: null // 共享页面，遍历所有存储恢复
});