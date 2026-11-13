const { createPage } = require('../../../utils/page-mixin');
const { tokenGet } = require('../../../utils/request');

createPage({
  data: {
    leaveList: [],
    loading: true,
    canApply: true,
    uncanceledLeaveId: null
  },

  onLoad() {
    this.loadData();
  },
  onShow() {
    this.loadData();
  },

  async loadData() {
    this.setData({ loading: true });
    
    try {
      const checkRes = await tokenGet('/student/leave/check_can_apply');
      this.setData({
        canApply: checkRes.can_apply,
        uncanceledLeaveId: checkRes.leave_id
      });
    } catch (error) {
      this.showError('检查申请状态失败，请重试');
    }

    try {
      const res = await tokenGet('/student/leave/list');
      this.setData({
        leaveList: res,
        loading: false
      });
    } catch (error) {
      this.setData({ loading: false });
      this.showError('获取请假记录失败，请重试');
    }
  },

  goToApply() {
    if (!this.data.canApply) {
      this.showError('您有未销假的请假记录，请先销假');
      return;
    }
    wx.navigateTo({
      url: '/packageAdmin/pages/leave-apply/leave-apply'
    });
  },

  goToDetail(e) {
    const { id } = e.currentTarget.dataset;
    wx.navigateTo({
      url: `/packageAdmin/pages/leave-detail/leave-detail?id=${id}`
    });
  },

  goHome() {
    wx.navigateBack();
  },

  getStatusText(leave) {
    if (leave.xj_zt === 1) {
      return '已销假';
    }
    if (leave.bzr_zt === 2 || leave.xsk_zt === 2) {
      return '审批不通过';
    }
    if (leave.bzr_zt === 1 && leave.xsk_zt === 1) {
      return '审批通过';
    }
    if (leave.bzr_zt === 0 && leave.xsk_zt === 0) {
      return '待审批';
    }
    return '审批中';
  },

  getStatusClass(leave) {
    if (leave.xj_zt === 1) {
      return 'status-completed';
    }
    if (leave.bzr_zt === 2 || leave.xsk_zt === 2) {
      return 'status-rejected';
    }
    if (leave.bzr_zt === 1 && leave.xsk_zt === 1) {
      return 'status-approved';
    }
    return 'status-pending';
  }
}, {
  requireAuth: true
});
