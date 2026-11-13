/**
 * 小程序 - 考试列表页（重构版）
 * - 调用 /mini-api/exams
 * - tab 切换：全部 / 在线 / 模拟
 * - 下拉刷新 + 触底加载更多
 * - 顶部用户卡 + 3 快捷按钮
 *
 * ⚠️ 后端 page_success 返回格式（已由 request.js 拆掉 success/msg）：
 *   { list: [...], total, page, page_size }
 *   列表项字段：id/title/description/type/duration/pass_score/total_score/
 *              max_attempts/attempt_count/can_attempt/...
 */
const { createPage } = require('../../../utils/page-mixin');
const { tokenGet } = require('../../../utils/request');
const { API_EXAME, TOKEN_KEY, USER_KEY } = require('../../../utils/api-exame');

const PAGE_SIZE = 10;
const NOTICE_KEY = 'mini_exam_notice_dismissed';

createPage({
  data: {
    // 原始列表（来自后端）
    exams: [],
    // 当前 tab 过滤后的列表（直接渲染）
    filteredExams: [],
    loading: true,
    loadingMore: false,
    activeTab: 0,
    page: 1,
    total: 0,
    noMore: false,
    showNotice: false,
    dontShowAgain: false,
    isRefreshing: false,
    userInfo: {},
    userNameFirst: '',
    // Tab 配置（0=全部 1=在线=type=1 2=模拟=type=2）
    tabs: [
      { id: 0, label: '全部考试测评' },
      { id: 1, label: '期末统考 (正式)' },
      { id: 2, label: '全真模拟自测' },
    ],
  },

  onLoad() {
    const token = wx.getStorageSync(TOKEN_KEY);
    if (!token) {
      wx.reLaunch({ url: '/packageExame/pages/mini-login/mini-login' });
      return;
    }

    // 加载用户信息（顶部头）
    // 后端登录返回字段：{ xs_id, xh(学号), xm(姓名), xb(性别), bj_id(班级id) }
    const user = wx.getStorageSync(USER_KEY) || {};
    const name = user.xm || user.name || user.username || '考生';
    this.setData({
      userInfo: {
        name,
        studentId: user.xh || user.studentId || '',
        className: user.bj_mc || user.className || user.class_name || '',
        major: user.major || '',
      },
      userNameFirst: name.slice(0, 1),
    });

    // 是否显示考试须知
    const dismissed = wx.getStorageSync(NOTICE_KEY);
    if (!dismissed) {
      this.setData({ showNotice: true });
    }
    this.loadExams(true);
  },

  toggleDontShowAgain() {
    this.setData({ dontShowAgain: !this.data.dontShowAgain });
  },

  hideNotice() {
    if (this.data.dontShowAgain) {
      wx.setStorageSync(NOTICE_KEY, true);
    }
    this.setData({ showNotice: false });
  },

  showNoticeAgain() {
    this.setData({ showNotice: true, dontShowAgain: false });
  },

  onShow() {
    // 每次进入刷新第一页（可能提交了）
    if (this.data.exams.length > 0) {
      this.loadExams(true);
    }
  },

  onPullDownRefresh() {
    this.loadExams(true).then(() => wx.stopPullDownRefresh());
  },

  onReachBottom() {
    if (this.data.loadingMore || this.data.noMore) return;
    this.loadExams(false);
  },

  async loadExams(reset) {
    if (reset) {
      this.setData({ page: 1, exams: [], filteredExams: [], loading: true, noMore: false });
    } else {
      this.setData({ loadingMore: true });
    }

    const page = this.data.page;
    // 按 tab 决定 type（0=全部=不传，1=在线=1，2=模拟=2）
    let type;
    if (this.data.activeTab === 1) type = 1;
    else if (this.data.activeTab === 2) type = 2;
    const params = { page, page_size: PAGE_SIZE };
    if (type != null) params.type = type;

    try {
      const resp = await tokenGet(
        API_EXAME.LIST,
        params,
        { loadingTitle: reset ? '加载中...' : '加载更多...', showLoading: reset }
      );

      // ✅ request.js 已拆 success/msg，resp 直接就是 {list, total, page, page_size}
      // 兼容旧写法：万一 resp 是 {success, data}，再剥一层
      const data = (resp && resp.list) ? resp
                   : (resp && resp.data && resp.data.list) ? resp.data
                   : resp;
      const list = (data && data.list) || [];
      const total = (data && data.total) || 0;

      console.log('[mini-list] loaded:', { count: list.length, total, firstId: list[0] && list[0].id });

      const merged = reset ? list : this.data.exams.concat(list);
      const filtered = this._filterByTab(merged, this.data.activeTab);

      this.setData({
        exams: merged,
        filteredExams: filtered,
        total,
        page: page + 1,
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
      this.showError(err.message || '获取考试列表失败');
    }
  },

  // 按 tab 过滤
  _filterByTab(exams, tab) {
    if (!exams) return [];
    if (tab === 1) return exams.filter(e => Number(e.type) === 1);
    if (tab === 2) return exams.filter(e => Number(e.type) === 2);
    return exams;
  },

  onTabChange(e) {
    const idx = Number(e.currentTarget.dataset.idx);
    if (idx === this.data.activeTab) return;
    this.setData({ activeTab: idx });
    this.loadExams(true);
  },

  handleRefresh() {
    if (this.data.isRefreshing) return;
    this.setData({ isRefreshing: true });
    this.loadExams(true).then(() => {
      setTimeout(() => this.setData({ isRefreshing: false }), 400);
      this.showSuccess('已同步最新考务数据');
    });
  },

  goToExam(e) {
    const { id, title } = e.currentTarget.dataset;
    wx.navigateTo({
      url: `/packageExame/pages/mini-room/mini-room?exam_id=${id}&exam_title=${encodeURIComponent(title)}`,
    });
  },

  goToScores() {
    wx.navigateTo({ url: '/packageExame/pages/mini-scores/mini-scores' });
  },

  handleLogout() {
    wx.showModal({
      title: '提示',
      content: '确定退出登录？',
      success: (res) => {
        if (res.confirm) {
          wx.removeStorageSync(TOKEN_KEY);
          wx.removeStorageSync(USER_KEY);
          wx.removeStorageSync('mini_exam_user');
          const app = getApp();
          app.globalData.userInfo = null;
          wx.reLaunch({ url: '/packageExame/pages/mini-login/mini-login' });
        }
      },
    });
  },

  noop() {},
});