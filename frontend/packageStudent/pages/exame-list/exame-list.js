const { createPage } = require('../../../utils/page-mixin');
const { tokenGet } = require('../../../utils/request');
const { API } = require('../../../utils/api');
const app = getApp();

/**
 * 考试列表页（exame 考试系统，中职学生专用）
 *
 * 数据源：exame 后端 /api/v1/student/exams（由 zhpt-new /exame/exams 代理到 102:8086）
 * 入口：packageVocational/pages/vocational-my（考试管理 → 在线考试）
 * 开放学生不走这里（开放走自研 /student_exam/*），my 页已隐藏该入口。
 * 适配：每个 exam → 一张卡片，显示标题/时长/及格分/状态
 *
 * 兼容：保留原"形考/终考"老系统入口的视觉风格，但数据全走 exame 新接口。
 */
createPage({
  data: {
    exams: [],
    loading: true,
    activeTab: 0,        // 0=全部 1=在线考试 2=模拟考试
    timeStatusText: {
      open: '进行中',
      not_started: '未开始',
      ended: '已结束',
    },
  },

  onLoad() {
    this.loadExams();
  },

  onShow() {
    // 每次进入刷新一次（可能有刚交卷的情况）
    this.loadExams();
  },

  onPullDownRefresh() {
    this.loadExams().then(() => wx.stopPullDownRefresh());
  },

  async loadExams() {
    this.setData({ loading: true });
    try {
      const type = this.data.activeTab === 0 ? undefined : this.data.activeTab;
      const resp = await tokenGet(
        API.EXAM_LIST.GET_EXAME_EXAMS,
        { page: 1, page_size: 100, type },
        { loadingTitle: '获取考试列表...' }
      );
      // 后端统一响应：{success, msg, data: {list, total, page, page_size}}
      const data = resp && resp.data ? resp.data : resp;
      const list = (data && data.list) || [];
      this.setData({ exams: list, loading: false });
    } catch (err) {
      this.setData({ loading: false });
      this.showError(err.message || '获取考试列表失败');
    }
  },

  onTabChange(e) {
    const idx = Number(e.currentTarget.dataset.idx);
    if (idx === this.data.activeTab) return;
    this.setData({ activeTab: idx }, () => this.loadExams());
  },

  goToDetail(e) {
    const id = e.currentTarget.dataset.id;
    const canAttempt = e.currentTarget.dataset.canattempt;
    const timeStatus = e.currentTarget.dataset.timestatus;
    const activeRecordId = e.currentTarget.dataset.activerecord;
    wx.redirectTo({
      url: `/packageStudent/pages/exame-info/exame-info?exam_id=${id}&can_attempt=${canAttempt ? 1 : 0}&time_status=${timeStatus}&active_record_id=${activeRecordId || 0}`
    });
  },

  goToRecords() {
    wx.redirectTo({
      url: '/packageStudent/pages/score/score?source=exame'
    });
  },

  goToMyCenter() {
    wx.redirectTo({
      url: '/packageStudent/pages/my/my'
    });
  },
}, {
  requireAuth: true,
  userType: 'vocational_student'
})
