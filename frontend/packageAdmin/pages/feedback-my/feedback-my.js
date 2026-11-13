const { createPage } = require('../../../utils/page-mixin');
const { BASE_URL } = require('../../../utils/request');
const { feedbackGet } = require('../../../utils/feedback-request');

const FEEDBACK_AUTH_CACHE_KEY = 'feedback_auth_cache';

createPage({
  data: {
    baseUrl: BASE_URL,
    tabs: [
      { value: '', label: '全部' },
      { value: 'pending', label: '待受理' },
      { value: 'processing', label: '处理中' },
      { value: 'done', label: '已办结' },
      { value: 'rejected', label: '已驳回' }
    ],
    statusLabels: {
      pending: '待受理',
      processing: '处理中',
      done: '已办结',
      rejected: '已驳回',
      cancelled: '已撤回'
    },
    activeStatus: '',
    items: [],
    page: 1,
    pageSize: 20,
    total: 0,
    loading: false,
    noMore: false
  },

  onLoad() {
    if (!this._ensureLoggedIn()) return;
    this.load(true);
  },

  onShow() {
    // 提交后回来刷新
    if (this.data.items.length > 0) this.load(true);
  },

  /**
   * 检查反馈模块独立登录态；未登录或缓存已过期则清除并跳转 feedback-login
   */
  _ensureLoggedIn() {
    const cached = wx.getStorageSync(FEEDBACK_AUTH_CACHE_KEY);
    if (cached && (cached.token || cached.refresh_token)) {
      if (cached.expireTime && cached.expireTime <= Date.now()) {
        wx.removeStorageSync(FEEDBACK_AUTH_CACHE_KEY);
        this._redirectToLogin();
        return false;
      }
      return true;
    }
    this._redirectToLogin();
    return false;
  },

  /**
   * 跳转到反馈登录页，带回调地址
   */
  _redirectToLogin() {
    const redirect = encodeURIComponent('/packageAdmin/pages/feedback-my/feedback-my');
    wx.redirectTo({ url: `/packageAdmin/pages/feedback-login/feedback-login?redirect=${redirect}` });
  },

  // 2026-09-29：自定义顶部"返回"按钮的回退逻辑。
  // - getCurrentPages() 拿到页面栈，若 >1（navigateTo 进来的）→ 正常 navigateBack
  // - 若 =1（redirectTo 进来的，submit 已被替换）→ 兜底跳到 feedback-submit 主页
  goBack() {
    const pages = getCurrentPages();
    if (pages.length > 1) {
      wx.navigateBack({ delta: 1 });
    } else {
      wx.redirectTo({ url: '/packageAdmin/pages/feedback-submit/feedback-submit' });
    }
  },

  onPullDownRefresh() {
    this.load(true).then(() => wx.stopPullDownRefresh());
  },

  onReachBottom() {
    if (!this.data.noMore && !this.data.loading) {
      this.load(false);
    }
  },

  onTabTap(e) {
    const val = e.currentTarget.dataset.value;
    if (val === this.data.activeStatus) return;
    this.setData({ activeStatus: val });
    this.load(true);
  },

  async load(reset) {
    if (this.data.loading) return;
    this.setData({ loading: true });
    const page = reset ? 1 : this.data.page + 1;
    try {
      const res = await feedbackGet('/feedback/my', {
        status: this.data.activeStatus,
        page,
        page_size: this.data.pageSize
      }, { showLoading: reset });
      const items = reset ? res.items : [...this.data.items, ...res.items];
      this.setData({
        items,
        page,
        total: res.total,
        noMore: items.length >= res.total
      });
    } catch (e) {
      // 登录过期的错误已由 feedback-request 处理跳转，此处仅显示其他错误
      if (typeof e === 'string' && e.includes('过期')) return;
      this.showError(typeof e === 'string' ? e : '加载失败');
    } finally {
      this.setData({ loading: false });
    }
  },

  onTap(e) {
    const id = e.currentTarget.dataset.id;
    wx.navigateTo({ url: `/packageAdmin/pages/feedback-detail/feedback-detail?id=${id}` });
  }
});
