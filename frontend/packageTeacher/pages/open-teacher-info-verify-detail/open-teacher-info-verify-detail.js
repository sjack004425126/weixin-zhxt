const { createPage } = require('../../../utils/page-mixin');
const { tokenGet, tokenPost } = require('../../../utils/request');

createPage({
  data: {
    loading: false,
    xsId: null,
    detail: {
      student_name: '',
      student_no: '',
      status: 'pending',
      status_text: '',
      submitted_at: '',
      diffs: [],
      history: [],
      field_labels: {}
    },
    changedCount: 0
  },

  onLoad(query) {
    const xsId = (query && query.xs_id) ? parseInt(query.xs_id, 10) : null;
    if (!xsId) {
      this.showError('参数缺失');
      return;
    }
    this.setData({ xsId });
    this.fetchDetail();
  },

  async fetchDetail() {
    this.setData({ loading: true });
    try {
      const res = await tokenGet('/open_teacher/info_verify/detail', { xs_id: this.data.xsId });
      const data = res || {};
      const diffs = data.diffs || [];
      // 给 history 的 modified 字段也加上 labels 列表，便于前端展示修改项
      const history = (data.history || []).map(h => ({
        ...h,
        modified_keys: h.modified ? Object.keys(h.modified) : []
      }));
      const changedCount = diffs.filter(d => d.changed).length;

      this.setData({
        detail: Object.assign({}, data, { history }),
        changedCount,
        loading: false
      });
    } catch (err) {
      this.setData({ loading: false });
      this.showError((err && err.message) || '获取详情失败');
    }
  },

  onReset() {
    const { detail } = this.data;
    if (detail.status === 'pending') {
      wx.showToast({ title: '该学生已是待核对状态', icon: 'none', duration: 1500 });
      return;
    }
    wx.showModal({
      title: '重置核对',
      content: `确定要重置「${detail.student_name}」的核对状态吗？重置后学生可以重新提交。`,
      confirmText: '确认重置',
      confirmColor: '#ef4444',
      success: async (r) => {
        if (!r.confirm) return;
        await this._doReset();
      }
    });
  },

  async _doReset() {
    try {
      await tokenPost('/open_teacher/info_verify/reset', { xs_id: this.data.xsId });
      wx.showToast({ title: '已重置，学生可重新提交', icon: 'success', duration: 1500 });
      // 刷新详情数据（使 status/history 等字段更新）
      await this.fetchDetail();
      // 同时把当前页 data 中 detail.status 同步更新，避免用户不退出就看到旧状态
      this.setData({
        'detail.status': 'pending',
        'detail.status_text': '待核对',
        'detail.modified': {},
        changedCount: 0
      });
    } catch (err) {
      this.showError((err && err.message) || '重置失败');
    }
  },

  goBack() { wx.navigateBack(); }
}, {
  requireAuth: true,
  userType: 'open_teacher'
});