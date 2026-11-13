const { createPage } = require('../../../utils/page-mixin');
const { get } = require('../../../utils/request');
const { checkFeatureSwitch } = require('../../../utils/feature-switch');

createPage({
  data: {
    articles: [],
    keyword: '',
    page: 1,
    pageSize: 10,
    loading: false,
    noMore: false,
    totalCount: 0,
    showDetail: false,
    detail: {}
  },

  _searchTimer: null,

  onLoad() {
    checkFeatureSwitch('job', this);
    this.loadArticles();
  },

  // 搜索输入（防抖）
  onSearchInput(e) {
    const keyword = e.detail.value;
    this.setData({ keyword });

    if (this._searchTimer) clearTimeout(this._searchTimer);
    this._searchTimer = setTimeout(() => {
      this.setData({ articles: [], page: 1, noMore: false });
      this.loadArticles();
    }, 500);
  },

  clearSearch() {
    if (this._searchTimer) clearTimeout(this._searchTimer);
    this.setData({ keyword: '', articles: [], page: 1, noMore: false });
    this.loadArticles();
  },

  // 加载文章列表
  async loadArticles() {
    if (this.data.loading || this.data.noMore) return;
    this.setData({ loading: true });

    try {
      const res = await get('/job/list', {
        page: this.data.page,
        page_size: this.data.pageSize,
        keyword: this.data.keyword
      }, { showLoading: false });

      const list = res.list || [];
      const allArticles = this.data.articles.concat(list);
      const noMore = allArticles.length >= res.total;

      this.setData({
        articles: allArticles,
        noMore,
        totalCount: res.total || 0,
        page: this.data.page + 1,
        loading: false
      });
    } catch (err) {
      this.setData({ loading: false });
      if (err.isAuthError) return;
      this.showError(err.message);
    }
  },

  // 点击文章
  async onArticleTap(e) {
    const id = e.currentTarget.dataset.id;
    try {
      const res = await get(`/job/detail/${id}`, {}, {
        showLoading: true,
        loadingTitle: '加载中...'
      });

      // 处理富文本中的图片样式（URL已由后端处理）
      let content = res.content || '';
      content = content.replace(
        /<img([^>]*)>/gi,
        '<img$1 style="max-width:100%;height:auto;display:block;margin:16rpx 0;border-radius:12rpx;">'
      );

      this.setData({
        detail: { ...res, content },
        showDetail: true
      });

      // 更新列表中的浏览量
      const articles = this.data.articles.map(item => {
        if (item.id === id) {
          return { ...item, view_count: res.view_count };
        }
        return item;
      });
      this.setData({ articles });
    } catch (err) {
      if (err.isAuthError) return;
      this.showError(err.message);
    }
  },

  closeDetail() {
    this.setData({ showDetail: false });
  },

  noop() {},

  // 触底加载更多
  onReachBottom() {
    this.loadArticles();
  },

  // 下拉刷新
  onPullDownRefresh() {
    this.setData({ articles: [], page: 1, noMore: false });
    this.loadArticles().finally(() => wx.stopPullDownRefresh());
  }
});
