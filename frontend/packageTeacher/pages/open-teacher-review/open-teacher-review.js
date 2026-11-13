const { createPage } = require('../../../utils/page-mixin');
const { tokenGet, tokenPost } = require('../../../utils/request');

const app = getApp();

createPage({
  data: {
    view: 'courses',
    courseList: [],
    loadingCourses: true,
    currentCourse: null,
    questionList: [],
    loadingQuestions: false,
  },

  onLoad() {
    this.loadCourses();
  },

  onShow() {
    // 从评阅页面返回时，刷新当前视图的数据
    if (this.data.view === 'courses') {
      this.loadCourses();
    } else if (this.data.view === 'questions' && this.data.currentCourse) {
      this.loadQuestionList();
    }
  },

  async loadQuestionList() {
    if (!this.data.currentCourse) return;
    this.setData({ loadingQuestions: true });
    try {
      const list = await tokenGet('/open_teacher/review/questions', {
        kc_id: this.data.currentCourse.kc_id,
      }, { showLoading: false }) || [];
      this.setData({ questionList: list, loadingQuestions: false, 'currentCourse.pending': this._calcCoursePending(list) });
    } catch (e) {
      this.setData({ loadingQuestions: false });
      this.showError('刷新题目列表失败');
    }
  },

  _calcCoursePending(questionList) {
    // 计算课程总待评人数
    return questionList.reduce((sum, q) => sum + (q.pending || 0), 0);
  },

  async loadCourses() {
    this.setData({ loadingCourses: true });
    try {
      const list = await tokenGet('/open_teacher/review/courses') || [];
      this.setData({ courseList: list, loadingCourses: false });
    } catch (e) {
      this.setData({ loadingCourses: false });
      this.showError('获取课程列表失败');
    }
  },

  // 点击课程 → 进入题目列表
  async onCourseClick(e) {
    const course = e.currentTarget.dataset.course;
    this.setData({ currentCourse: course, view: 'questions', loadingQuestions: true, questionList: [] });
    try {
      const list = await tokenGet('/open_teacher/review/questions', {
        kc_id: course.kc_id,
      }, { showLoading: false }) || [];
      this.setData({
        questionList: list,
        loadingQuestions: false,
        'currentCourse.pending': this._calcCoursePending(list)
      });
    } catch (e) {
      this.setData({ loadingQuestions: false });
      this.showError('获取题目列表失败');
    }
  },

  // 点击题目 → 跳转到逐题评阅页面
  onQuestionClick(e) {
    const index = e.currentTarget.dataset.index;
    const { currentCourse, questionList } = this.data;
    const kc_id = currentCourse.kc_id;
    // 把题目列表暂存到 globalData，避免 URL 参数过长导致 navigateTo 失败
    app.globalData._reviewGradeCache = app.globalData._reviewGradeCache || {};
    app.globalData._reviewGradeCache[kc_id] = questionList;
    wx.navigateTo({
      url: `/packageTeacher/pages/open-teacher-review-grade/open-teacher-review-grade?kc_id=${kc_id}&kcmc=${encodeURIComponent(currentCourse.kcmc)}&start_index=${index}`
    });
  },

  goBack() {
    if (this.data.view === 'questions') {
      this.setData({ view: 'courses', questionList: [] });
      // 返回课程列表时刷新数据（更新待评人数）
      this.loadCourses();
    } else {
      wx.navigateBack();
    }
  },

  requireAuth: true,
  userType: 'open_teacher'
});
