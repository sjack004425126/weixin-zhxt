const { createPage } = require('../../../utils/page-mixin');
const { get, post } = require('../../../utils/request');

createPage({
  data: {
    // 当前Tab: realtime / history / ranking
    currentTab: 'realtime',
    
    // 实时数据
    activeRequests: 0,
    totalToday: 0,
    avgResponseTime: 0,
    updatedAt: '',
    
    // 图表数据
    minuteData: [],
    
    // 路径统计
    pathStats: [],
    
    // 状态码统计
    statusStats: [],
    
    // 慢请求
    slowRequests: [],
    
    // 趋势图数据
    maxCount: 0,
    halfMaxCount: 0,
    currentMinuteCount: 0,
    avgMinuteCount: 0,
    
    // 历史数据
    historyDays: 7,
    dailyData: [],
    peakHours: [],
    historyMaxCount: 0,
    historyHalfMax: 0,
    historyTotalCount: 0,
    historyAvgCount: 0,
    
    // API排行
    rankingHours: 24,
    apiRanking: [],
    
    // 刷新间隔（秒）
    refreshInterval: 5,
    refreshTimer: null,
    isLoading: false,
    autoRefresh: true,
    
    // 日期排行弹窗
    showDailyRanking: false,
    dailyRankingDate: '',
    dailyRankingTotal: 0,
    dailyRankingApis: 0,
    dailyRankingList: []
  },

  onLoad() {
    // 直接加载数据，认证由 admin-nav 页面统一处理
    this.fetchStats();
    this.startAutoRefresh();
  },

  onUnload() {
    this.stopAutoRefresh();
  },

  onShow() {
    if (this.data.autoRefresh && !this.data.refreshTimer) {
      this.startAutoRefresh();
    }
  },

  onHide() {
    this.stopAutoRefresh();
  },

  startAutoRefresh() {
    if (this.data.refreshTimer) {
      clearInterval(this.data.refreshTimer);
    }
    
    const timer = setInterval(() => {
      if (this.data.autoRefresh) {
        this.fetchStats();
      }
    }, this.data.refreshInterval * 1000);
    
    this.setData({ refreshTimer: timer });
  },

  stopAutoRefresh() {
    if (this.data.refreshTimer) {
      clearInterval(this.data.refreshTimer);
      this.setData({ refreshTimer: null });
    }
  },

  toggleAutoRefresh() {
    const newValue = !this.data.autoRefresh;
    this.setData({ autoRefresh: newValue });
    
    if (newValue) {
      this.startAutoRefresh();
      this.showSuccess('已开启自动刷新');
    } else {
      this.stopAutoRefresh();
      this.showSuccess('已关闭自动刷新');
    }
  },

  async fetchStats() {
    if (this.data.isLoading) return;
    
    this.setData({ isLoading: true });
    
    try {
      const res = await get('/stats/realtime', { showLoading: false });
      
      // 处理路径统计
      const pathStats = Object.entries(res.path_stats || {}).map(([path, count]) => ({
        path: path,
        count: count
      })).sort((a, b) => b.count - a.count);
      
      // 处理状态码统计
      const statusStats = Object.entries(res.status_stats || {}).map(([code, count]) => ({
        code: code,
        count: count,
        type: this.getStatusType(code)
      }));
      
      // 处理分钟数据（取最近30分钟）
      const minuteData = (res.minute_data || []).slice(-30);
      
      // 计算趋势图数据
      const counts = minuteData.map(function(item) { return item.count || 0; });
      const maxCount = Math.max.apply(null, counts.concat([1]));  // 至少为1避免除0
      const totalCount = counts.reduce(function(a, b) { return a + b; }, 0);
      const avgCount = Math.round(totalCount / counts.length);
      const currentCount = counts[counts.length - 1] || 0;
      
      // 计算每个柱子的百分比高度
      const minuteDataWithPercent = minuteData.map(function(item) {
        return {
          time: item.time,
          count: item.count,
          percent: maxCount > 0 ? Math.round((item.count || 0) / maxCount * 100) : 0
        };
      });
      
      this.setData({
        activeRequests: res.active_requests || 0,
        totalToday: res.total_today || 0,
        avgResponseTime: res.avg_response_time_ms || 0,
        updatedAt: this.formatTime(res.updated_at),
        minuteData: minuteDataWithPercent,
        maxCount: maxCount,
        halfMaxCount: Math.floor(maxCount / 2),
        currentMinuteCount: currentCount,
        avgMinuteCount: avgCount,
        pathStats: pathStats.slice(0, 10),
        statusStats: statusStats,
        slowRequests: res.slow_requests || [],
        isLoading: false
      });
      
    } catch (error) {
      console.error('获取统计数据失败', error);
      this.setData({ isLoading: false });
    }
  },

  getStatusType(code) {
    const codeNum = parseInt(code);
    if (codeNum >= 200 && codeNum < 300) return 'success';
    if (codeNum >= 300 && codeNum < 400) return 'redirect';
    if (codeNum >= 400 && codeNum < 500) return 'client-error';
    if (codeNum >= 500) return 'server-error';
    return 'unknown';
  },

  formatTime(isoString) {
    if (!isoString) return '';
    const date = new Date(isoString);
    return `${date.getHours().toString().padStart(2, '0')}:${date.getMinutes().toString().padStart(2, '0')}:${date.getSeconds().toString().padStart(2, '0')}`;
  },

  manualRefresh() {
    this.fetchStats();
  },

  changeInterval(e) {
    const intervals = [3, 5, 10, 30];
    const index = e.detail.value;
    const interval = intervals[index];
    
    this.setData({ refreshInterval: interval });
    
    if (this.data.autoRefresh) {
      this.startAutoRefresh();
    }
    
    this.showSuccess(`刷新间隔已设为 ${interval} 秒`);
  },

  switchTab(e) {
    const tab = e.currentTarget.dataset.tab;
    this.setData({ currentTab: tab });
    
    if (tab === 'history') {
      this.fetchHistory();
    } else if (tab === 'ranking') {
      this.fetchRanking();
    }
  },

  async fetchHistory() {
    this.setData({ isLoading: true });
    
    try {
      const res = await get(`/stats/history?days=${this.data.historyDays}`, { showLoading: false });
      
      const dailyData = res.daily_data || [];
      
      // 计算历史趋势图数据
      const counts = dailyData.map(function(item) { return item.count || 0; });
      const maxCount = Math.max.apply(null, counts.concat([1]));
      const totalCount = counts.reduce(function(a, b) { return a + b; }, 0);
      const avgCount = dailyData.length > 0 ? Math.round(totalCount / dailyData.length) : 0;
      
      // 计算每个柱子的百分比高度，并添加简短日期
      const dailyDataWithPercent = dailyData.map(function(item) {
        return {
          date: item.date,
          count: item.count,
          percent: maxCount > 0 ? Math.round((item.count || 0) / maxCount * 100) : 0,
          shortDate: item.date ? item.date.slice(5) : ''  // 只显示 MM-DD
        };
      });
      
      this.setData({
        dailyData: dailyDataWithPercent,
        peakHours: res.peak_hours || [],
        historyMaxCount: maxCount,
        historyHalfMax: Math.floor(maxCount / 2),
        historyTotalCount: totalCount,
        historyAvgCount: avgCount,
        isLoading: false
      });
    } catch (error) {
      console.error('获取历史数据失败', error);
      this.setData({ isLoading: false });
    }
  },

  async fetchRanking() {
    this.setData({ isLoading: true });
    
    try {
      const res = await get(`/stats/api_ranking?hours=${this.data.rankingHours}`, { showLoading: false });
      
      this.setData({
        apiRanking: res.ranking || [],
        isLoading: false
      });
    } catch (error) {
      console.error('获取API排行失败', error);
      this.setData({ isLoading: false });
    }
  },

  changeHistoryDays(e) {
    const days = [1, 3, 7, 14, 30];
    const index = e.detail.value;
    this.setData({ historyDays: days[index] });
    this.fetchHistory();
  },

  changeRankingHours(e) {
    const hours = [1, 6, 12, 24, 48, 168];
    const index = e.detail.value;
    this.setData({ rankingHours: hours[index] });
    this.fetchRanking();
  },

  clearStats() {
    wx.showModal({
      title: '确认清空',
      content: '确定要清空所有统计数据吗？此操作不可恢复。',
      confirmColor: '#e53935',
      success: async (res) => {
        if (res.confirm) {
          try {
            const { post } = require('../../../utils/request');
            const result = await post('/stats/clear', {}, { showLoading: false });
            this.showSuccess(`已清空 ${result.cleared_count} 条数据`);
            // 刷新数据
            this.fetchStats();
            if (this.data.currentTab === 'history') {
              this.fetchHistory();
            } else if (this.data.currentTab === 'ranking') {
              this.fetchRanking();
            }
          } catch (error) {
            this.showError('清空失败，请重试');
          }
        }
      }
    });
  },

  goBack() {
    wx.navigateBack();
  },

  goHome() {
    wx.switchTab({
      url: '/pages/home/home'
    });
  },

  // 点击每日柱状图
  async onDailyBarTap(e) {
    const { date, count } = e.currentTarget.dataset;
    if (!date || count === 0) {
      this.showError('该日期暂无数据');
      return;
    }
    
    wx.showLoading({ title: '加载中...' });
    try {
      const res = await get('/stats/daily_ranking', { date });
      wx.hideLoading();
      
      this.setData({
        showDailyRanking: true,
        dailyRankingDate: date,
        dailyRankingTotal: res.total_requests || 0,
        dailyRankingApis: res.total_apis || 0,
        dailyRankingList: res.ranking || []
      });
    } catch (error) {
      wx.hideLoading();
      this.showError('获取排行数据失败，请重试');
    }
  },

  // 关闭日期排行弹窗
  closeDailyRanking() {
    this.setData({ showDailyRanking: false });
  }
});
