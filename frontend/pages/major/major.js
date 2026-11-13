const { createPage } = require('../../utils/page-mixin');
const { API } = require('../../utils/api');
const { silentGet } = require('../../utils/request');

createPage({
  data: {
    loading: true,
    undergraduate: [], // 本科专业
    specialist: [],    // 专科专业
    showFeeToast: false, // 费用提示显示状态
    selectedMajor: null  // 当前选中的专业
  },

  onLoad() {
    this.fetchMajors();
  },

  // 显示费用信息
  showFeeInfo(e) {
    const major = e.currentTarget.dataset.major;
    this.setData({
      selectedMajor: major,
      showFeeToast: true
    });
  },

  async fetchMajors() {
    this.setData({ loading: true });
    try {
      // request.js 自动解 success/code，业务数据直接用
      const data = await silentGet(API.MAJOR.GET_ALL);

      // 分类处理专业数据
      const undergraduate = [];
      const specialist = [];

      const flatten = (level, bucket) => {
        if (level.level !== '本科' && level.level !== '专科') return;
        (level.types || []).forEach(type => {
          (type.majors || []).forEach(major => {
            bucket.push({
              ...major,
              type: type.id,
              tuition: major.tuition * 100,
              books: major.books * 100
            });
          });
        });
      };

      (Array.isArray(data) ? data : []).forEach(level => {
        flatten(level, level.level === '本科' ? undergraduate : specialist);
      });

      // 按名称排序
      undergraduate.sort((a, b) => (a.name || '').localeCompare(b.name || ''));
      specialist.sort((a, b) => (a.name || '').localeCompare(b.name || ''));

      this.setData({ undergraduate, specialist });
    } catch (err) {
      if (err.isAuthError) return;
      this.showError(err.message || '获取专业信息失败，请稍后重试');
    } finally {
      this.setData({ loading: false });
    }
  },

  onPullDownRefresh() {
    this.fetchMajors().finally(() => wx.stopPullDownRefresh());
  }
}); // 专业目录公开页，无需 requireAuth 