const { createPage } = require('../../../utils/page-mixin');
const { tokenGet, tokenPost } = require('../../../utils/request');

createPage({
  data: {
    loading: true,
    detail: {},
    isXsk: false,
    leaveId: null
  },

  onLoad(options) {
    const { id } = options;
    const app = getApp();
    const cached = wx.getStorageSync('vocational_teacher_auth_cache') || {};
    const userInfo = (app.globalData && app.globalData.userInfo) || cached.userInfo || {};
    const isXsk = userInfo.is_xsk || false;
    this.setData({ isXsk, leaveId: id ? parseInt(id) : null });
    if (id) {
      this.loadDetail(id);
    }
  },

  async loadDetail(id) {
    this.setData({ loading: true });
    
    try {
      const res = await tokenGet('/vocational_teacher/leave/detail', { id });
      this.setData({
        detail: res,
        loading: false
      });
    } catch (error) {
      this.setData({ loading: false });
      this.showError('获取请假详情失败，请重试');
    }
  },

  handleApprove() {
    const detail = this.data.detail;
    const isXskApprove = detail.bzr_zt === 1 && detail.xsk_zt === 0 && this.data.isXsk;
    const title = isXskApprove ? '学生科审批' : '班主任审批';

    wx.showModal({
      title,
      content: '确定通过该请假申请吗？',
      success: async (res) => {
        if (res.confirm) {
          try {
            const url = isXskApprove
              ? '/vocational_teacher/leave/xsk_approve'
              : '/vocational_teacher/leave/approve';
            await tokenPost(url, { leave_id: this.data.leaveId, status: 1 });
            this.showSuccess('审批通过');
            this.loadDetail(this.data.leaveId);
          } catch (error) {
            this.showError('审批失败，请重试');
          }
        }
      }
    });
  },

  handleReject() {
    const detail = this.data.detail;
    const isXskApprove = detail.bzr_zt === 1 && detail.xsk_zt === 0 && this.data.isXsk;
    const title = isXskApprove ? '学生科审批' : '班主任审批';

    wx.showModal({
      title,
      content: '确定拒绝该请假申请吗？',
      success: async (res) => {
        if (res.confirm) {
          try {
            const url = isXskApprove
              ? '/vocational_teacher/leave/xsk_approve'
              : '/vocational_teacher/leave/approve';
            await tokenPost(url, { leave_id: this.data.leaveId, status: 2 });
            this.showSuccess('已拒绝');
            this.loadDetail(this.data.leaveId);
          } catch (error) {
            this.showError('操作失败，请重试');
          }
        }
      }
    });
  },

  goBack() {
    wx.navigateBack();
  }
}, {
  requireAuth: true,
  userType: 'vocational_teacher'
});