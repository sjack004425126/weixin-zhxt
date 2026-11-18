const { createPage } = require('../../../utils/page-mixin');
const { tokenGet } = require('../../../utils/request');
const { API } = require('../../../utils/api');

/**
 * 自测科目列表（开放学生自研，不走 102 exame）
 * 后端：GET /student_exam/subjectsList
 * 返回：{ subjects: [{kc_id,kcid,kcmc,kccc,ksdw,issj,ctjs...}], deadline, statistics, notice }
 */
createPage({
  data: {
    loading: true,
    subjects: [],
    deadline: '',
    statistics: null,
    notice: null,
  },

  onLoad() {
    this.loadSubjects();
  },

  onShow() {
    if (this.data.subjects.length > 0) this.loadSubjects();
  },

  onPullDownRefresh() {
    this.loadSubjects().then(() => wx.stopPullDownRefresh());
  },

  async loadSubjects() {
    this.setData({ loading: true });
    try {
      const resp = await tokenGet(
        API.EXAM_LIST.GET_EXAM_LIST,
        {},
        { loadingTitle: '获取自测科目...' }
      );
      const data = resp && resp.data ? resp.data : resp;
      const payload = data && data.data ? data.data : data;
      const subjects = (payload && payload.subjects) || (data && data.subjects) || [];
      this.setData({
        subjects,
        deadline: (payload && payload.deadline) || (data && data.deadline) || '',
        statistics: (payload && payload.statistics) || null,
        notice: (payload && payload.notice) || null,
        loading: false,
      });
    } catch (err) {
      this.setData({ loading: false });
      this.showError(err.message || err.msg || '获取自测科目失败');
    }
  },

  goToPapers(e) {
    const kcId = e.currentTarget.dataset.kcid;
    const kcmc = e.currentTarget.dataset.kcmc || '';
    if (!kcId) return;
    wx.navigateTo({
      url: `/packageStudent/pages/self-exam-papers/self-exam-papers?kc_id=${kcId}&kcmc=${encodeURIComponent(kcmc)}`
    });
  },

  goToMy() {
    wx.redirectTo({ url: '/packageStudent/pages/my/my' });
  },
}, {
  requireAuth: true,
  userType: 'open_student'
});
