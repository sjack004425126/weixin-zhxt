const { createPage } = require('../../../utils/page-mixin');
const { tokenGet } = require('../../../utils/request');

// 心理咨询预约（纯预约制）
// 上半部分：可预约场次；下半部分：我的预约记录（默认只显示近期 5 条，可展开）
const HISTORY_LIMIT = 5;

createPage({
  data: {
    loading: true,
    list: [],
    historyAll: [],
    history: [],
    historyShort: [],
    historyTotal: 0,
    historyLimit: HISTORY_LIMIT,
    historyExpanded: false,
    historyHasMore: false,
    historyCanToggle: false,
    historyToggleText: '',
    historyTipShow: false,
    historyTipText: ''
  },

  onLoad() { this._loadSeq = 0; this.loadList(); },
  onShow() { this.loadList(); },

  // 折叠/展开只做本地数组替换：history 永远是新数组（全量 copy / 前5 copy），
  // 不依赖下标显隐，WXML 单列表渲染即可收起。后端一次最多返回 10 条
  _applyHistory(expanded) {
    const all = this.data.historyAll || [];
    const total = this.data.historyTotal || all.length;
    const shown = all.length;
    const hasMore = shown > HISTORY_LIMIT;
    const showAll = expanded && hasMore;
    this.setData({
      historyExpanded: !!showAll,
      historyLimit: showAll ? shown : HISTORY_LIMIT,
      history: showAll ? all.slice() : all.slice(0, HISTORY_LIMIT),
      historyShort: all.slice(0, HISTORY_LIMIT),
      historyHasMore: hasMore,
      historyCanToggle: hasMore,
      // 后端最多只给 10 条：按钮按实际拿到的条数显示，避免"展开全部 N 条"与实际不符
      historyToggleText: hasMore ? (showAll ? '收起' : ('展开全部' + shown + '条')) : ('共' + total + '条'),
      historyTipShow: !!showAll,
      historyTipText: '仅显示最近' + shown + '条'
    });
  },

  async loadList() {
    const seq = ++this._loadSeq;
    this.setData({ loading: true });
    try {
      const [list, hist] = await Promise.all([
        tokenGet('/counsel/open_list', {}, { showLoading: false }),
        tokenGet('/counsel/my_history', { limit: 10 }, { showLoading: false })
      ]);
      // 请求期间用户可能点了展开/收起：丢弃过期回包，避免把新状态覆盖回旧状态
      if (seq !== this._loadSeq) return;
      const expanded = this.data.historyExpanded;
      const rows = list || [];
      rows.forEach(item => {
        item.slots = item.slots || [];
      });

      const h = hist || {};
      const all = h.list || [];
      const total = h.total || all.length;
      const shown = all.length;
      const hasMore = shown > HISTORY_LIMIT;
      const showAll = expanded && hasMore;
      // 一次 setData 写完，避免连续两次 setData 竞态导致切片丢失（收不起来）
      // history 是新数组：展开=全量 copy，收起=前5 copy
      this.setData({
        list: rows,
        historyAll: all,
        historyTotal: total,
        historyExpanded: !!showAll,
        historyLimit: showAll ? shown : HISTORY_LIMIT,
        history: showAll ? all.slice() : all.slice(0, HISTORY_LIMIT),
        historyShort: all.slice(0, HISTORY_LIMIT),
        historyHasMore: hasMore,
        historyCanToggle: hasMore,
        historyToggleText: hasMore ? (showAll ? '收起' : ('展开全部' + shown + '条')) : ('共' + total + '条'),
        historyTipShow: !!showAll,
        historyTipText: '仅显示最近' + shown + '条',
        loading: false
      });
    } catch (e) {
      this.setData({ loading: false });
      this.showError((typeof e === 'string' ? e : (e && e.message)) || '加载失败');
    }
  },

  toggleHistory() {
    // 条数不够时不处理，避免 expanded 空翻
    if (!this.data.historyCanToggle) return;
    // 纯本地切换：秒收起/秒展开，不再请求后端
    this._applyHistory(!this.data.historyExpanded);
  },

  goDetail(e) {
    const { id } = e.currentTarget.dataset;
    wx.navigateTo({ url: `/packageVocational/pages/vocational-counsel-detail/vocational-counsel-detail?id=${id}` });
  },
  goBack() { wx.navigateBack(); }
}, { requireAuth: true, userType: 'vocational_student' });
