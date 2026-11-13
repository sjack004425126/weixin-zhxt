const { createPage } = require('../../../utils/page-mixin');
const { BASE_URL } = require('../../../utils/request');
const { feedbackGet } = require('../../../utils/feedback-request');

const FEEDBACK_AUTH_CACHE_KEY = 'feedback_auth_cache';

createPage({
  data: {
    baseUrl: BASE_URL,
    list: [],
    total: 0,
    page: 1,
    pageSize: 20,
    loading: false,
    noMore: false,

    // 过滤
    keyword: '',
    activeDestination: '',
    activeBatch: '',
    hasCertificate: '',          // ''=全部 / '1'=有图 / '0'=无图

    // 字典
    destinations: [],
    batches: [],

    // 统计
    stats: { total: 0, with_certificate: 0, without_certificate: 0, by_destination: [] },
  },

  onLoad() {
    if (!this._ensureLoggedIn()) return;
    this.loadDictsAndStats();
    this.load(true);
  },

  onShow() {
    if (this.data.list.length > 0) this.loadStats();
  },

  // 与 feedback-admin 保持一致的反馈登录态校验
  _ensureLoggedIn() {
    const cached = wx.getStorageSync(FEEDBACK_AUTH_CACHE_KEY);
    if (cached && (cached.token || cached.refresh_token)) {
      if (cached.expireTime && cached.expireTime <= Date.now()) {
        wx.removeStorageSync(FEEDBACK_AUTH_CACHE_KEY);
      } else {
        return true;
      }
    }
    wx.showToast({ title: '请先登录', icon: 'none' });
    setTimeout(() => {
      wx.redirectTo({ url: '/packageAdmin/pages/feedback-login/feedback-login' });
    }, 600);
    return false;
  },

  async loadDictsAndStats() {
    try {
      const res = await feedbackGet('/grad_emp_survey/admin/list', { page: 1, page_size: 1 });
      if (res && res.destinations) this.setData({ destinations: res.destinations });
      if (res && res.batches) this.setData({ batches: res.batches });
    } catch (err) {
      console.warn('加载字典失败', err);
    }
    this.loadStats();
  },

  async loadStats() {
    try {
      const res = await feedbackGet('/grad_emp_survey/admin/stats');
      if (res) this.setData({ stats: res });
    } catch (err) { /* ignore */ }
  },

  async load(reset) {
    if (this.data.loading) return;
    const page = reset ? 1 : this.data.page;
    this.setData({ loading: true });

    const params = {
      page,
      page_size: this.data.pageSize,
    };
    if (this.data.keyword) params.keyword = this.data.keyword;
    if (this.data.activeDestination) params.destination = this.data.activeDestination;
    if (this.data.activeBatch) params.batch = this.data.activeBatch;
    if (this.data.hasCertificate !== '') params.has_certificate = this.data.activeBatch ? this.data.activeBatch : this.data.hasCertificate;

    // 注意：has_certificate 单独处理（activeBatch 不影响）
    if (this.data.hasCertificate !== '') {
      params.has_certificate = this.data.hasCertificate;
    } else {
      delete params.has_certificate;
    }
    if (!this.data.activeDestination) delete params.destination;
    if (!this.data.activeBatch) delete params.batch;

    try {
      const res = await feedbackGet('/grad_emp_survey/admin/list', params, { showLoading: false });
      const list = (res && res.list) || [];
      const merged = reset ? list : this.data.list.concat(list);
      this.setData({
        list: merged,
        total: (res && res.total) || 0,
        page: page + 1,
        noMore: merged.length >= ((res && res.total) || 0),
        loading: false,
      });
      if (res && res.destinations) this.setData({ destinations: res.destinations });
      if (res && res.batches) this.setData({ batches: res.batches });
    } catch (err) {
      this.setData({ loading: false });
      this.showError(typeof err === 'string' ? err : '加载失败');
    }
  },

  onReachBottom() {
    if (this.data.noMore || this.data.loading) return;
    this.load(false);
  },

  onSearchInput(e) {
    this.setData({ keyword: e.detail.value });
  },

  onSearchConfirm() {
    this.load(true);
  },

  onClearSearch() {
    this.setData({ keyword: '' });
    this.load(true);
  },

  onFilterDestination(e) {
    const value = e.currentTarget.dataset.value || '';
    this.setData({ activeDestination: value }, () => this.load(true));
  },

  onFilterBatch(e) {
    const value = e.currentTarget.dataset.value || '';
    this.setData({ activeBatch: value }, () => this.load(true));
  },

  onFilterCert(e) {
    const value = e.currentTarget.dataset.value || '';
    this.setData({ hasCertificate: value }, () => this.load(true));
  },

  onTapItem(e) {
    const { id } = e.currentTarget.dataset;
    if (!id) return;
    wx.navigateTo({
      url: `/packageAdmin/pages/grad-emp-survey-detail/grad-emp-survey-detail?id=${id}`,
    });
  },

  goBack() {
    wx.navigateBack();
  },
});
