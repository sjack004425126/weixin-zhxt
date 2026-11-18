const { createPage } = require('../../../utils/page-mixin');
const { tokenGet } = require('../../../utils/request');
const { API } = require('../../../utils/api');

/**
 * 考试详情页（exame 考试系统，中职学生专用）
 *
 * 从列表跳过来，单一考试视图：
 *  - 显示考试元信息（时长/及格分/总分/起止时间/次数限制）
 *  - 显示历史成绩（如有）
 *  - 按钮：开始考试 / 继续考试 / 查看成绩
 */
createPage({
  data: {
    exam: null,
    records: [],
    loading: true,
    examId: null,
    timeStatusText: {
      open: '进行中',
      not_started: '未开始',
      ended: '已结束',
    },
  },

  onLoad(options) {
    if (!options || !options.exam_id) {
      this.showError('缺少参数');
      return;
    }
    this.setData({ examId: Number(options.exam_id) });
    this.loadDetail();
    this.loadRecords();
  },

  onShow() {
    if (this.data.examId) {
      this.loadDetail();
      this.loadRecords();
    }
  },

  async loadDetail() {
    try {
      const resp = await tokenGet(
        API.EXAM_INFO.GET_EXAME_DETAIL(this.data.examId),
        {},
        { showLoading: false }
      );
      const data = resp && resp.data ? resp.data : resp;
      const fmt = (s) => {
        if (!s) return '';
        const d = new Date(s);
        if (isNaN(d.getTime())) return s;
        const p = (n) => (n < 10 ? '0' + n : '' + n);
        return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
      };
      if (data) {
        if (data.start_date) data.start_date = fmt(data.start_date);
        if (data.end_date) data.end_date = fmt(data.end_date);
      }
      this.setData({ exam: data, loading: false });
    } catch (err) {
      this.setData({ loading: false });
      this.showError(err.message || '获取考试详情失败');
    }
  },

  async loadRecords() {
    try {
      const resp = await tokenGet(
        API.EXAME_SCORE.LIST,
        { page: 1, page_size: 50 },
        { showLoading: false }
      );
      const data = resp && resp.data ? resp.data : resp;
      const list = (data && data.list) || [];
      const fmt = (s) => {
        if (!s) return '';
        const d = new Date(s);
        if (isNaN(d.getTime())) return s;
        const p = (n) => (n < 10 ? '0' + n : '' + n);
        return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
      };
      this.setData({
        records: list
          .filter(r => r.exam_id === this.data.examId)
          .map(r => ({ ...r, submitted_at: fmt(r.submitted_at || r.started_at), started_at: fmt(r.started_at) })),
      });
    } catch (e) {
      // 静默失败，不影响详情加载
      this.setData({ records: [] });
    }
  },

  goToStart(e) {
    const examId = e.currentTarget.dataset.id;
    wx.redirectTo({
      url: `/packageStudent/pages/exame-paper/exame-paper?exam_id=${examId}`
    });
  },

  goToResume(e) {
    const examId = e.currentTarget.dataset.id;
    const recordId = e.currentTarget.dataset.record;
    wx.redirectTo({
      url: `/packageStudent/pages/exame-paper/exame-paper?exam_id=${examId}&record_id=${recordId}`
    });
  },

  goToRecord(e) {
    const recordId = e.currentTarget.dataset.record;
    wx.redirectTo({
      url: `/packageStudent/pages/score/score?source=exame&record_id=${recordId}`
    });
  },

  goToExameList() {
    wx.redirectTo({
      url: '/packageStudent/pages/exame-list/exame-list'
    });
  },
}, {
  requireAuth: true,
  userType: 'vocational_student'
})
