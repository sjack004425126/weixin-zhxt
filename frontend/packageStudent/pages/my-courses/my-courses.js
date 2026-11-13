// ============================================================
// 路由常量：从 utils/api 导入，避免硬编码路径
// ============================================================
const { createPage } = require('../../../utils/page-mixin');
const { API } = require('../../../utils/api');
const { tokenGet } = require('../../../utils/request');

// ============================================================
// 业务常量
// ============================================================
const PASS_SCORE = 60;                       // 及格线
const ERROR_MESSAGES = {
  LOAD_FAILED: '获取课程列表失败',
};
const LOADING_TITLE = '获取课程列表...';

// ============================================================
// 页面
// ============================================================
createPage({
  data: {
    loading: true,                           // 控制 wxml 布局（loading-wrap / list-view）
    coursesList: [],
    stats: { total: 0, learned: 0, passed: 0, failed: 0 },
    showPassed: false,
    failedCourses: [],
    passedCourses: [],
    unlearnedCourses: [],
  },

  // ---------- 内部状态（不写进 data，避免无意义重渲染） ----------
  _loadingCount: 0,                          // 页面级 loading 引用计数

  // ---------- 页面级 loading 工具 ----------
  // 用途：wxml 里 wx:if="{{loading}}" 的整页 loading 占位
  // 注意：与 request.js 内部的 wx.showLoading 是两套独立机制：
  //   - this.loading* 控制 **布局层**（loading-wrap + 列表互斥）
  //   - request.js 控制 **系统层**（wx.showLoading 全屏遮罩）
  // 两者分别独立计数，但通常同步出现。
  _startLoading() {
    this._loadingCount++;
    this.setData({ loading: true });
  },
  _stopLoading() {
    this._loadingCount = Math.max(0, this._loadingCount - 1);
    if (this._loadingCount === 0) this.setData({ loading: false });
  },

  onLoad() {
    this.getCoursesList();
  },

  onShow() {
    // 每次回到页面都刷新（业务需要）
    if (this.isLoggedIn()) this.getCoursesList();
  },

  onPullDownRefresh() {
    this.getCoursesList().finally(() => wx.stopPullDownRefresh());
  },

  // ----------------------------------------------------------
  // 拉取课程并分类统计
  // ----------------------------------------------------------
  async getCoursesList() {
    this._startLoading();
    try {
      // 走统一 HTTP 层：自动加 token / 401 refresh / 请求去重 / loading toast / 业务错误归一
      const res = await tokenGet(
        API.MY_COURSES.MANAGEMENT_LIST,
        {},
        { loadingTitle: LOADING_TITLE }
      );
      const courses = (Array.isArray(res) ? res : (res && res.courses)) || [];

      // ---------- 业务：分类统计（同步代码，可见性最强） ----------
      const failed = [];
      const passed = [];
      const unlearned = [];
      let learned = 0;

      for (const c of courses) {
        const score = parseFloat(c.zh_score);
        if (Number.isNaN(score)) {
          unlearned.push(c);
        } else {
          learned++;
          (score >= PASS_SCORE ? passed : failed).push(c);
        }
      }

      this.setData({
        coursesList: courses,
        failedCourses: failed,
        passedCourses: passed,
        unlearnedCourses: unlearned,
        stats: {
          total: courses.length,
          learned,
          passed: passed.length,
          failed: failed.length,
        },
      });
    } catch (err) {
      // isAuthError（401 / 403 / NO_TOKEN）已被 requireAuth 守卫接管，
      // 表现为页面跳转到登录页，所以这里直接静默、不再弹 toast
      if (err.isAuthError) return;
      this.showError(err.message || ERROR_MESSAGES.LOAD_FAILED);
    } finally {
      this._stopLoading();
    }
  },

  // ----------------------------------------------------------
  // UI 交互
  // ----------------------------------------------------------
  togglePassed() {
    this.setData({ showPassed: !this.data.showPassed });
  },

  goHome() {
    wx.switchTab({ url: '/pages/home/home' });
  },
}, {
  requireAuth: true,                         // 未登录自动跳登录页（auth-guard.js）
  userType: 'open_student',                  // 单端限制，避免跨端拿到错的 userInfo
});
