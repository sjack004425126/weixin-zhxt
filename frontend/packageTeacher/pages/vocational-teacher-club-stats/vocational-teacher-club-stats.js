const { createPage } = require('../../../utils/page-mixin');
const { tokenGet } = require('../../../utils/request');

createPage({
  data: {
    loading: true,
    activeTab: 0,
    courseStats: [],
    classStats: [],
    totalCourses: 0,
    totalSelected: 0,
    showDetail: false,
    detailTitle: '',
    detailList: [],
    detailLoading: false
  },

  onLoad() {
    this.loadStats();
  },

  async loadStats() {
    this.setData({ loading: true });
    try {
      const res = await tokenGet('/vocational_teacher/club_course_stats', {}, { showLoading: false });
      const data = res || {};
      this.setData({
        courseStats: data.course_stats || [],
        classStats: data.class_stats || [],
        totalCourses: data.total_courses || 0,
        totalSelected: data.total_selected || 0,
        loading: false
      });
    } catch (error) {
      this.setData({ loading: false });
      this.showError('获取统计数据失败');
    }
  },

  onTabChange(e) {
    this.setData({ activeTab: e.detail.index });
  },

  async onCourseTap(e) {
    const { id, name } = e.currentTarget.dataset;
    this.setData({ showDetail: true, detailTitle: name + ' 选课学生', detailList: [], detailLoading: true });
    try {
      const res = await tokenGet('/vocational_teacher/club_course_detail', { course_id: id });
      this.setData({ detailList: (res || {}).students || [], detailLoading: false });
    } catch (error) {
      this.setData({ detailLoading: false });
      this.showError('获取详情失败');
    }
  },

  async onClassTap(e) {
    const { id, name } = e.currentTarget.dataset;
    this.setData({ showDetail: true, detailTitle: name + ' 选课情况', detailList: [], detailLoading: true });
    try {
      const res = await tokenGet('/vocational_teacher/club_course_detail', { bj_id: id });
      this.setData({ detailList: (res || {}).students || [], detailLoading: false });
    } catch (error) {
      this.setData({ detailLoading: false });
      this.showError('获取详情失败');
    }
  },

  onCloseDetail() {
    this.setData({ showDetail: false });
  }
}, {
  requireAuth: true,
  userType: 'vocational_teacher'
});