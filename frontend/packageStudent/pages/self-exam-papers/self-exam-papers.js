const { createPage } = require('../../../utils/page-mixin');
const { tokenGet, tokenPost } = require('../../../utils/request');
const { API } = require('../../../utils/api');

/**
 * 自测试卷列表（开放学生自研）
 * GET /student_exam/get_sj_list?kc_id=
 * 返回 { sj_list: [{sj_id, sj_type_mc, sj_zt, sj_dt, dt_num...}], sys_zcks_switch, statistics }
 */
createPage({
  data: {
    loading: true,
    kcId: null,
    kcmc: '',
    papers: [],
    statistics: null,
  },

  onLoad(options) {
    const kcId = Number(options.kc_id);
    if (!kcId) { this.showError('缺少课程参数'); return; }
    this.setData({ kcId, kcmc: decodeURIComponent(options.kcmc || '') });
    this.loadPapers();
  },

  onPullDownRefresh() {
    this.loadPapers().then(() => wx.stopPullDownRefresh());
  },

  async loadPapers() {
    this.setData({ loading: true });
    try {
      const data = await tokenGet(
        API.EXAM_INFO.GET_SJ_LIST,
        { kc_id: this.data.kcId },
        { loadingTitle: '获取试卷列表...' }
      );
      const list = (data && data.sj_list) || [];
      this.setData({ papers: list, statistics: (data && data.statistics) || null, loading: false });
    } catch (err) {
      this.setData({ loading: false });
      this.showError(err.message || err.msg || '获取试卷列表失败');
    }
  },

  async goToAnswer(e) {
    const sjId = e.currentTarget.dataset.sjid;
    const sjZt = Number(e.currentTarget.dataset.sjzt);
    if (sjZt !== 1) { this.showWarn('该试卷尚未开启'); return; }
    if (!sjId) return;
    try {
      const data = await tokenPost(
        API.SELF_EXAM.CREATE_RECORD,
        { kc_id: this.data.kcId, sj_id: sjId },
        { loadingTitle: '创建答题记录...' }
      );
      const jlId = (data && data.jl_id) || (data && data.data && data.data.jl_id);
      if (!jlId) throw new Error((data && data.msg) || '创建记录失败');
      wx.navigateTo({
        url: `/packageStudent/pages/self-exam-answer/self-exam-answer?kc_id=${this.data.kcId}&sj_id=${sjId}&jl_id=${jlId}`
      });
    } catch (err) {
      this.showError(err.message || err.msg || '创建记录失败');
    }
  },

  goBack() {
    wx.navigateBack({ fail: () => wx.redirectTo({ url: '/packageStudent/pages/self-exam-list/self-exam-list' }) });
  },
}, {
  requireAuth: true,
  userType: 'open_student'
});
