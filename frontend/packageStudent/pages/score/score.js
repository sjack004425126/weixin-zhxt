const { createPage } = require('../../../utils/page-mixin');
const { tokenGet } = require('../../../utils/request');
const { API } = require('../../../utils/api');

/**
 * 成绩页（exame 考试系统）
 *
 * 两种模式：
 *  1. 无 record_id：显示所有成绩列表
 *  2. 有 record_id：显示单次考试详情（含题目 + 对错）
 */
createPage({
  data: {
    mode: 'list',           // 'list' | 'detail'
    loading: true,
    records: [],
    detail: null,           // 单次成绩详情（含 questions）
    recordId: null,
  },

  onLoad(options) {
    if (options && options.record_id) {
      this.setData({ mode: 'detail', recordId: Number(options.record_id) });
      this.loadDetail();
    } else {
      this.setData({ mode: 'list' });
      this.loadList();
    }
  },

  onShow() {
    if (this.data.mode === 'list') this.loadList();
    if (this.data.mode === 'detail' && this.data.recordId) this.loadDetail();
  },

  onPullDownRefresh() {
    const task = this.data.mode === 'detail' ? this.loadDetail() : this.loadList();
    task.then(() => wx.stopPullDownRefresh());
  },

  async loadList() {
    this.setData({ loading: true });
    try {
      const resp = await tokenGet(
        API.EXAME_SCORE.LIST,
        { page: 1, page_size: 50 },
        { loadingTitle: '获取成绩列表...' }
      );
      const data = resp && resp.data ? resp.data : resp;
      this.setData({ records: (data && data.list) || [], loading: false });
    } catch (err) {
      this.setData({ loading: false });
      this.showError(err.message || '获取成绩列表失败');
    }
  },

  async loadDetail() {
    this.setData({ loading: true });
    try {
      const resp = await tokenGet(
        API.EXAME_SCORE.PAPER(this.data.recordId),
        {},
        { loadingTitle: '获取成绩详情...' }
      );
      const data = resp && resp.data ? resp.data : resp;
      this.setData({ detail: data, loading: false });
    } catch (err) {
      // 退化到 /record/{id} 接口（不含正确答案）
      try {
        const resp2 = await tokenGet(
          API.EXAME_SCORE.DETAIL(this.data.recordId),
          {},
          { loadingTitle: '获取成绩详情...' }
        );
        const data = resp2 && resp2.data ? resp2.data : resp2;
        this.setData({ detail: data, loading: false });
      } catch (err2) {
        this.setData({ loading: false });
        this.showError(err2.message || '获取成绩详情失败');
      }
    }
  },

  goToDetail(e) {
    const recordId = e.currentTarget.dataset.record;
    wx.redirectTo({
      url: `/packageStudent/pages/score/score?record_id=${recordId}`
    });
  },

  goToExameList() {
    wx.redirectTo({
      url: '/packageStudent/pages/exame-list/exame-list'
    });
  },
}, {
  requireAuth: true,
  userType: 'open_student'
})
