const { createPage } = require('../../../utils/page-mixin');
const { tokenGet, tokenPost } = require('../../../utils/request');

createPage({
  data: {
    address: '',
    saving: false,
    not_saving: true
  },

  onLoad() {
    this.fetchSite();
  },

  onShow() {
    this.fetchSite();
  },

  async fetchSite() {
    try {
      const data = await tokenGet('/open_teacher/book_pickup_site', {}, { showLoading: false });
      this.setData({ address: (data && data.address) || '' });
    } catch (err) {
      console.error('[book-site] 获取失败:', err);
    }
  },

  onInputChange(e) {
    const v = (e.detail !== undefined && e.detail !== null) ? String(e.detail) : '';
    this.setData({ address: v });
  },

  async onSave() {
    if (this.data.saving) return;
    const address = (this.data.address || '').trim();
    if (address.length > 200) {
      wx.showToast({ title: '地址过长，最多200字', icon: 'none', duration: 2000 });
      return;
    }
    this.setData({ saving: true, not_saving: false });
    try {
      const data = await tokenPost('/open_teacher/book_pickup_site', { address }, { loadingTitle: '保存中...' });
      this.setData({ address: (data && data.address) || '' });
      wx.showToast({ title: '保存成功', icon: 'success', duration: 1500 });
    } catch (err) {
      console.error('[book-site] 保存失败:', err);
      wx.showToast({ title: (err && err.message) || '保存失败', icon: 'none', duration: 2000 });
    } finally {
      this.setData({ saving: false, not_saving: true });
    }
  }
}, {
  requireAuth: true,
  userType: 'open_teacher'
});
