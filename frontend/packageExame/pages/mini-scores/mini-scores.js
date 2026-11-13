/**
 * 小程序 - 成绩页（重构版）
 * - 列表模式：/mini-api/exams/records
 * - 详情模式：/mini-api/exams/record/{id}
 * - 英雄得分面板（绿/红渐变）
 * - 对错矩阵 + 筛选
 * - 逐题深度解析（含选项对比）
 */
const { createPage } = require('../../../utils/page-mixin');
const { tokenGet } = require('../../../utils/request');
const { API_EXAME, TOKEN_KEY } = require('../../../utils/api-exame');

const PAGE_SIZE = 10;

createPage({
  data: {
    detailMode: false,
    records: [],
    detail: null,
    loading: true,
    page: 1,
    total: 0,
    loadingMore: false,
    noMore: false,
    // 详情派生
    filteredQuestions: [],
    wrongCount: 0,
    correctCount: 0,
    filterType: 'all',
    accuracyPercent: 0,
  },

  onLoad(query) {
    const token = wx.getStorageSync(TOKEN_KEY);
    if (!token) {
      wx.reLaunch({ url: '/packageExame/pages/mini-login/mini-login' });
      return;
    }

    if (query.record_id) {
      this.setData({ detailMode: true });
      this.loadDetail(query.record_id);
    } else {
      this.setData({ detailMode: false });
      this.loadList(true);
    }
  },

  onShow() {
    if (!this.data.detailMode) {
      this.loadList(true);
    }
  },

  onPullDownRefresh() {
    const p = this.data.detailMode
      ? this.loadDetail(this.data.detail && this.data.detail.id)
      : this.loadList(true);
    Promise.resolve(p).then(() => wx.stopPullDownRefresh()).catch(() => wx.stopPullDownRefresh());
  },

  onReachBottom() {
    if (this.data.detailMode) return;
    if (this.data.loadingMore || this.data.noMore) return;
    this.loadList(false);
  },

  async loadList(reset) {
    if (reset) {
      this.setData({ page: 1, records: [], loading: true, noMore: false });
    } else {
      this.setData({ loadingMore: true });
    }

    try {
      const resp = await tokenGet(
        API_EXAME.RECORDS,
        { page: this.data.page, page_size: PAGE_SIZE },
        { loadingTitle: reset ? '加载中...' : '加载更多...', showLoading: reset }
      );
      const data = resp && resp.data ? resp.data : resp;
      const list = (data && data.list) || [];
      const total = (data && data.total) || 0;

      const merged = reset ? list : this.data.records.concat(list);

      this.setData({
        records: merged,
        total,
        page: this.data.page + 1,
        loading: false,
        loadingMore: false,
        noMore: merged.length >= total,
      });
    } catch (err) {
      this.setData({ loading: false, loadingMore: false });
      if (err.errorType === 'AUTH') {
        wx.removeStorageSync(TOKEN_KEY);
        wx.reLaunch({ url: '/packageExame/pages/mini-login/mini-login' });
        return;
      }
      this.showError(err.message || '加载成绩失败');
    }
  },

  viewDetail(e) {
    const id = e.currentTarget.dataset.id;
    this.setData({ detailMode: true, detail: null, loading: true, filterType: 'all' });
    this.loadDetail(id);
  },

  async loadDetail(recordId) {
    this.setData({ loading: true });
    try {
      const resp = await tokenGet(
        API_EXAME.RECORD_DETAIL(recordId),
        {},
        { loadingTitle: '加载详情...' }
      );
      const data = resp && resp.data ? resp.data : resp;

      // 派生：对错数 + 正确率 + 加 _originalIndex 给逐题卡用
      const qs = (data && data.questions) || [];
      qs.forEach((q, idx) => { q._originalIndex = idx; });
      let wrong = 0, correct = 0;
      qs.forEach(q => { (q.is_correct ? correct++ : wrong++); });
      const accuracy = data && data.total_score > 0
        ? Math.round((data.score / data.total_score) * 100)
        : 0;

      this.setData({
        detail: data,
        filteredQuestions: qs,
        wrongCount: wrong,
        correctCount: correct,
        accuracyPercent: accuracy,
        loading: false,
      });
    } catch (err) {
      this.setData({ loading: false });
      this.showError(err.message || '加载详情失败');
    }
  },

  // ---------- 筛选 ----------
  setFilter(e) {
    const type = e.currentTarget.dataset.type;
    const qs = (this.data.detail && this.data.detail.questions) || [];
    let filtered = qs;
    if (type === 'wrong') filtered = qs.filter(q => !q.is_correct);
    else if (type === 'correct') filtered = qs.filter(q => q.is_correct);
    this.setData({ filterType: type, filteredQuestions: filtered });
  },

  isOptionCorrect(q, label) {
    if (!q.correct_answer) return false;
    return String(q.correct_answer).split(',').includes(String(label));
  },

  isOptionSelected(q, label) {
    if (!q.user_answer) return false;
    return String(q.user_answer).split(',').includes(String(label));
  },

  getTypeLabel(type) {
    return ({ 1: '单选题', 2: '多选题', 3: '判断题', 4: '填空题', 5: '简答题' })[type] || '题目';
  },

  formatDuration(seconds) {
    if (!seconds || seconds < 0) return '0秒';
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    if (m === 0) return `${s}秒`;
    if (s === 0) return `${m}分钟`;
    return `${m}分${s}秒`;
  },

  // ---------- 底部按钮 ----------
  onRetake() {
    const detail = this.data.detail;
    if (!detail || !detail.exam_id) {
      this.showError('无法定位考试信息');
      return;
    }
    wx.redirectTo({
      url: `/packageExame/pages/mini-room/mini-room?exam_id=${detail.exam_id}&exam_title=${encodeURIComponent(detail.exam_title || '考试')}`,
    });
  },

  onShare() {
    this.showSuccess('已复制测评报告链接，可分享给教师或同学');
  },

  goBack() {
    if (this.data.detailMode) {
      this.setData({ detailMode: false, detail: null, filterType: 'all' });
      this.loadList(true);
    } else {
      wx.reLaunch({ url: '/packageExame/pages/mini-list/mini-list' });
    }
  },
});