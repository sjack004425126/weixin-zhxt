const { createPage } = require('../../../utils/page-mixin');
const { tokenGet, tokenPost } = require('../../../utils/request');

createPage({
  data: {
    stayList: [],
    loading: true,
    canApply: true,
    statusMap: { 0: '待审批', 1: '已批准', 2: '已拒绝', 3: '已过期', 4: '已取消' },
    // 申请表单
    showForm: false,
    formData: { ls_type: 'weekend', ls_reason: '', start_date: '', end_date: '' },
    typeText: '周末',
    dateDisplay: '',
    submitting: false,
    showTypePicker: false,
    showCalendar: false,
    typeColumns: ['周末', '假期', '其他'],
    minDate: new Date().getTime(),
    maxDate: new Date(new Date().getFullYear(), 11, 31).getTime()
  },

  onLoad() { this.loadData(); },
  onShow() { this.loadData(); },

  async loadData() {
    this.setData({ loading: true });
    try {
      const [checkRes, listRes] = await Promise.all([
        tokenGet('/student/stay/check_can_apply'),
        tokenGet('/student/stay/list')
      ]);
      this.setData({
        canApply: checkRes.can_apply,
        stayList: listRes || [],
        loading: false
      });
    } catch (e) {
      this.setData({ loading: false });
      this.showError('加载失败');
    }
  },

  showApplyForm() { this.setData({ showForm: true, formData: { ls_type: 'weekend', ls_reason: '', start_date: '', end_date: '' }, typeText: '周末', dateDisplay: '' }); },
  hideApplyForm() { this.setData({ showForm: false }); },
  showTypePicker() { this.setData({ showTypePicker: true }); },
  hideTypePicker() { this.setData({ showTypePicker: false }); },
  showCalendar() { this.setData({ showCalendar: true }); },
  hideCalendar() { this.setData({ showCalendar: false }); },

  onTypeConfirm(e) {
    const val = e.detail.value;
    const map = { '周末': 'weekend', '假期': 'holiday', '其他': 'other' };
    this.setData({ 'formData.ls_type': map[val] || 'weekend', typeText: val, showTypePicker: false });
  },

  onCalendarConfirm(e) {
    const [start, end] = e.detail;
    const fmt = d => `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
    this.setData({
      'formData.start_date': fmt(start),
      'formData.end_date': fmt(end),
      dateDisplay: `${fmt(start)} 至 ${fmt(end)}`,
      showCalendar: false
    });
  },

  onReasonChange(e) { this.setData({ 'formData.ls_reason': e.detail }); },

  async submitApply() {
    const { formData } = this.data;
    if (!formData.start_date || !formData.end_date) { this.showError('请选择留宿日期'); return; }
    if (!formData.ls_reason.trim()) { this.showError('请填写留宿原因'); return; }
    this.setData({ submitting: true });
    try {
      await tokenPost('/student/stay/apply', formData);
      this.showSuccess('申请成功');
      this.setData({ showForm: false, submitting: false });
      this.loadData();
    } catch (e) {
      this.setData({ submitting: false });
      this.showError(e || '申请失败');
    }
  },

  cancelStay(e) {
    const id = e.currentTarget.dataset.id;
    wx.showModal({
      title: '提示', content: '确定取消此留宿申请吗？',
      success: async (res) => {
        if (res.confirm) {
          try {
            await tokenPost('/student/stay/cancel', { id });
            this.showSuccess('已取消');
            this.loadData();
          } catch (e) { this.showError(e || '取消失败'); }
        }
      }
    });
  },

  goBack() { wx.navigateBack(); }
}, {
  requireAuth: true,
  userType: 'vocational_student'
});
