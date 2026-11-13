/**
 * 问卷列表页 - survey-list
 * 设计风格: zhpt-new/design 精准线性风格 (Linear/Typeform)
 * 数据源:   GET /survey-fill/list
 */
const { createPage } = require('../../../utils/page-mixin');
const { get } = require('../../../utils/request');

createPage({
  data: {
    // 加载状态
    loading: true,
    refreshing: false,
    retrying: false,

    // 列表数据
    surveys: [],

    // 搜索
    keyword: '',
    searchInput: '',

    // 筛选: all / SURVEY / REGISTRATION / VOTE / EXAM
    filterType: 'all',

    // 筛选 Tab 配置
    _filterCategories: [
      { type: 'all',         label: '全部' },
      { type: 'SURVEY',      label: '问卷' },
      { type: 'REGISTRATION', label: '报名' },
      { type: 'VOTE',        label: '投票' },
      { type: 'EXAM',        label: '测评' },
    ],

    // 公告 Banner
    showNoticeBanner: true,

    error_msg: '',

    // 返回顶部按钮显示
    _showBackToTop: false,
  },

  onLoad() {
    this._fetchList();
  },

  onShow() {
    // 从填写页返回时刷新"已答过"状态
    if (!this.data.loading) {
      this._fetchList({ silent: true });
    }
  },

  onPullDownRefresh() {
    this.setData({ refreshing: true });
    this._fetchList().finally(() => {
      wx.stopPullDownRefresh();
      this.setData({ refreshing: false });
    });
  },

  onPageScroll(e) {
    const scrollTop = e.scrollTop;
    // 返回顶部按钮：超过 500rpx 就显示
    if (scrollTop > 500 && !this.data._showBackToTop) {
      this.setData({ _showBackToTop: true });
    } else if (scrollTop <= 500 && this.data._showBackToTop) {
      this.setData({ _showBackToTop: false });
    }
  },

  _scrollToTop() {
    wx.pageScrollTo({ scrollTop: 0, duration: 250 });
  },

  // ================================================================
  // 数据加载
  // ================================================================
  async _fetchList(opts = {}) {
    const silent = !!opts.silent;
    if (!silent) this.setData({ loading: true, error_msg: '' });

    try {
      const params = {};
      if (this.data.keyword) params.keyword = this.data.keyword;
      if (this.data.filterType && this.data.filterType !== 'all') {
        params.survey_type = this.data.filterType;
      }
      // request.js 已将后端 {success, data} 解包，res 直接是 {total, list}
      const res = await get('/survey-fill/list', params, { showLoading: !silent });
      const list = (res.list || []).map(item => this._formatItem(item));

      this.setData({
        loading: false,
        surveys: list,
        error_msg: '',
      });
    } catch (err) {
      console.error('survey list fetch error', err);
      this.setData({
        loading: false,
        error_msg: err.message || '加载失败',
      });
    }
  },

  _formatItem(raw) {
    const typeMeta = {
      SURVEY:       { icon: 'orders-o',  label: '问卷',   color: '#2563EB', bg: 'rgba(37,99,235,0.08)' },
      REGISTRATION: { icon: 'edit',       label: '报名',   color: '#10B981', bg: 'rgba(16,185,129,0.08)' },
      VOTE:         { icon: 'like-o',     label: '投票',   color: '#F59E0B', bg: 'rgba(245,158,11,0.08)' },
      EXAM:         { icon: 'medal-o',    label: '测评',   color: '#722ED1', bg: 'rgba(114,46,209,0.08)' },
    };
    const meta = typeMeta[raw.survey_type] || typeMeta.SURVEY;

    return {
      ...raw,
      _typeMeta: meta,
      _startText: raw.start_at ? this._fmtDate(raw.start_at) : '',
      _endText: raw.end_at ? this._fmtDate(raw.end_at) : '',
      _lastSubmitText: raw.last_submit_time ? this._fmtDate(raw.last_submit_time) : '',
      // 设计稿需要的字段（后端暂无，兜底）
      dept_name: raw.dept_name || '',
    };
  },

  _fmtDate(iso) {
    try {
      const d = new Date(iso);
      if (isNaN(d.getTime())) return '';
      const pad = n => String(n).padStart(2, '0');
      return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
    } catch (_) {
      return '';
    }
  },

  // ================================================================
  // 交互
  // ================================================================

  // 关键词输入（微信 input 事件 e.detail 在高版本下为 {value, cursor} 对象，必须取 .value）
  onKeywordInput(e) {
    const raw = e && e.detail;
    const val = (raw && typeof raw === 'object') ? raw.value : raw;
    this.setData({ searchInput: val == null ? '' : String(val) });
  },

  // 点击搜索按钮
  onSearchTap() {
    const v = (this.data.searchInput && typeof this.data.searchInput === 'object')
      ? (this.data.searchInput.value || '')
      : (this.data.searchInput || '');
    this.setData({ keyword: v.trim() });
    this._fetchList();
  },

  // 清空搜索
  onClearKeyword() {
    this.setData({ keyword: '', searchInput: '' });
    this._fetchList();
  },

  // 切换类型筛选
  onFilterTap(e) {
    const { type } = e.currentTarget.dataset;
    if (type === this.data.filterType) return;
    this.setData({ filterType: type });
    this._fetchList();
  },

  // 公告 Banner 点击 → 进入第一个问卷
  onNoticeBannerTap() {
    if (this.data.surveys.length > 0) {
      const first = this.data.surveys[0];
      this._navigateTo(first);
    }
  },

  // 关闭公告 Banner
  onCloseNoticeBanner() {
    this.setData({ showNoticeBanner: false });
  },

  // 点击卡片 → 进入填写页
  onItemTap(e) {
    const item = e.currentTarget.dataset;
    this._navigateTo(item);
  },

  _navigateTo(item) {
    const { sid, code, answered } = item;
    let url;
    if (answered) {
      url = `/packageSurvey/pages/survey-fill/survey-fill?sid=${sid}`;
    } else if (code) {
      url = `/packageSurvey/pages/survey-fill/survey-fill?code=${encodeURIComponent(code)}`;
    } else {
      url = `/packageSurvey/pages/survey-fill/survey-fill?sid=${sid}`;
    }
    wx.navigateTo({ url });
  },

  // 重试
  onRetryTap() {
    this.setData({ retrying: true });
    this._fetchList().finally(() => {
      this.setData({ retrying: false });
    });
  },

  // 返回首页
  onBackTap() {
    wx.navigateBack();
  },
}, {
  requireAuth: false,
  autoRegisterComponents: false,
});
