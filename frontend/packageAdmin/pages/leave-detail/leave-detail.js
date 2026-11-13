const { createPage } = require('../../../utils/page-mixin');
const { tokenGet, tokenPost } = require('../../../utils/request');

createPage({
  data: {
    leaveId: null,
    leaveDetail: null,
    loading: true,
    showCancelModal: false,
    cancelForm: {
      xsfxxl: '',
      xsfxjtgj: ''
    },
    cancelLoading: false,
    accessCheckLoading: false,
    accessCheckResult: null
  },

  onLoad(options) {
    if (options.id) {
      this.setData({ leaveId: parseInt(options.id) });
      this.loadLeaveDetail();
    }
  },

  onShow() {
    if (this.data.leaveId) {
      this.loadLeaveDetail();
    }
  },

  async loadLeaveDetail() {
    this.setData({ loading: true });
    
    try {
      const res = await tokenGet(`/student/leave/detail/${this.data.leaveId}`);
      this.setData({
        leaveDetail: res,
        loading: false
      });
    } catch (error) {
      this.setData({ loading: false });
      this.showError('获取请假详情失败，请重试');
    }
  },

  goToEdit() {
    const { leaveDetail } = this.data;
    if (leaveDetail.bzr_zt !== 0 || leaveDetail.xsk_zt !== 0) {
      this.showError('请假申请已有审批记录，无法修改');
      return;
    }
    wx.navigateTo({
      url: `/pages/leave-apply/leave-apply?id=${this.data.leaveId}`
    });
  },

  async showCancelModal() {
    const { leaveDetail } = this.data;
    
    if (leaveDetail.xj_zt === 1) {
      this.showError('该请假记录已销假');
      return;
    }
    
    if (leaveDetail.bzr_zt !== 1 || leaveDetail.xsk_zt !== 1) {
      this.showError('请假申请尚未全部审批通过，无法销假');
      return;
    }
    
    // 先打开弹窗,显示加载状态
    this.setData({ 
      showCancelModal: true,
      accessCheckLoading: true,
      accessCheckResult: null
    });
    
    // 查询门禁记录
    try {
      const res = await tokenGet(`/student/leave/check_access_record/${leaveDetail.id}`);
      const accessCheck = res.access_check || {};
      this.setData({
        accessCheckLoading: false,
        accessCheckResult: accessCheck
      });
    } catch (error) {
      this.setData({
        accessCheckLoading: false,
        accessCheckResult: {
          has_return: false,
          message: '查询门禁记录失败，请重试'
        }
      });
    }
  },

  hideCancelModal() {
    this.setData({ 
      showCancelModal: false,
      cancelForm: {
        xsfxxl: '',
        xsfxjtgj: ''
      }
    });
  },

  onCancelFormChange(e) {
    const { field } = e.currentTarget.dataset;
    this.setData({
      [`cancelForm.${field}`]: e.detail
    });
  },

  async submitCancel() {
    const { cancelForm, leaveId } = this.data;
    
    if (!cancelForm.xsfxxl || cancelForm.xsfxxl.trim() === '') {
      this.showError('请填写返校线路');
      return;
    }
    if (!cancelForm.xsfxjtgj || cancelForm.xsfxjtgj.trim() === '') {
      this.showError('请填写返校交通工具');
      return;
    }

    this.setData({ cancelLoading: true });

    try {
      await tokenPost('/student/leave/cancel', {
        leave_id: leaveId,
        xsfxxl: cancelForm.xsfxxl,
        xsfxjtgj: cancelForm.xsfxjtgj
      });
      this.showSuccess('销假成功');
      this.hideCancelModal();
      this.loadLeaveDetail();
    } catch (error) {
      this.showError('销假失败，请重试');
    }

    this.setData({ cancelLoading: false });
  },

  getApprovalStatusText(status) {
    switch (status) {
      case 0: return '待审批';
      case 1: return '审批通过';
      case 2: return '审批不通过';
      default: return '未知';
    }
  },

  getApprovalStatusClass(status) {
    switch (status) {
      case 0: return 'status-pending';
      case 1: return 'status-approved';
      case 2: return 'status-rejected';
      default: return '';
    }
  },

  goBack() {
    wx.navigateBack();
  }
}, {
  requireAuth: true
});
