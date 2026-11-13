const { createPage } = require('../../../utils/page-mixin');
const { tokenGet, tokenPost } = require('../../../utils/request');
const app = getApp();

createPage({
  data: {
    examInfo: { start_time: '', end_time: '' },
    userInfo: null,
    inList: false,
    hasPaid: false,
    paying: false,
    order: null,
    bkspzt: '',
    bkspztStep: 0,
    bkspztNodeClass: 'pending',
    bkspztNodeIcon: '3',
    bkspztNodeLabel: '审批状态'
  },

  onLoad() {
    this.setData({ userInfo: app.globalData.userInfo });
    this.getExamInfo();
  },

  async getExamInfo() {
    try {
      const res = await tokenGet('/degree/degree_english_info', {}, { loadingTitle: '获取考试信息...' });
      const { start_time, end_time, in_list, has_paid, order, bkspzt } = res;
      const bkspztInfo = this.calcBkspztNode(bkspzt, has_paid);
      this.setData({
        examInfo: { start_time, end_time },
        inList: in_list,
        hasPaid: has_paid,
        order: order,
        bkspzt: bkspzt || '',
        bkspztStep: this.calcBkspztStep(bkspzt),
        bkspztNodeClass: bkspztInfo.cls,
        bkspztNodeIcon: bkspztInfo.icon,
        bkspztNodeLabel: bkspztInfo.label
      });
    } catch (err) {
      this.showError(err.message || '获取考试信息失败');
    }
  },

  // bkspzt → 步骤数值（保留备用）
  calcBkspztStep(bkspzt) {
    if (!bkspzt) return 0;
    if (bkspzt.includes('二级审批通过')) return 3;
    if (bkspzt.includes('二级审批不通过')) return -2;
    if (bkspzt.includes('一级审批通过')) return 2;
    if (bkspzt.includes('一级审批不通过')) return -1;
    return 0;
  },

  // bkspzt → 步骤3节点的样式/图标/文字
  calcBkspztNode(bkspzt, hasPaid) {
    if (!hasPaid) return { cls: 'pending', icon: '3', label: '审批状态' };
    if (!bkspzt || bkspzt.includes('待审批')) return { cls: 'active', icon: '3', label: '待审批' };
    if (bkspzt.includes('二级审批通过')) return { cls: 'done', icon: '✓', label: '二级审批通过' };
    if (bkspzt.includes('一级审批通过')) return { cls: 'active', icon: '3', label: '一级通过' };
    if (bkspzt.includes('一级审批不通过')) return { cls: 'fail', icon: '✗', label: '一级不通过' };
    if (bkspzt.includes('二级审批不通过')) return { cls: 'fail', icon: '✗', label: '二级不通过' };
    return { cls: 'active', icon: '3', label: bkspzt };
  },

  goHome() {
    wx.navigateTo({ url: '/packageStudent/pages/my/my' });
  },

  // 缴费（若无订单则先自动创建）
  async prePay() {
    if (this.data.paying) return;
    const that = this;
    const fee = this.data.order ? this.data.order.money / 100 : 45;
    wx.showModal({
      title: '确认缴费',
      content: `确定要缴纳考试费用 ${fee} 元吗？`,
      success: async (res) => {
        if (!res.confirm) return;
        that.setData({ paying: true });
        try {
          // 若无订单，先自动创建
          let order_no = that.data.order && that.data.order.order_no;
          if (!order_no) {
            await tokenGet('/degree/create_degree_english_order', {}, { loadingTitle: '提交报名中...' });
            await that.getExamInfo();
            order_no = that.data.order && that.data.order.order_no;
          }
          if (!order_no) {
            that.showError('创建订单失败，请重试');
            that.setData({ paying: false });
            return;
          }
          // 获取openid
          const openid_code = await app.getOpenid_code();
          if (!openid_code) {
            that.showError('获取openid失败，请重试');
            that.setData({ paying: false });
            return;
          }
          // 获取支付参数
          const payParams = await tokenPost('/degree/prepay_degree_english', { order_no, openid_code }, { loadingTitle: '获取支付参数...' });
          // 调用微信支付
          wx.requestPayment({
            ...payParams,
            success: async () => {
              that.showSuccess('缴费成功');
              setTimeout(async () => {
                await tokenPost('/degree/update_degree_english_order', { order_no }, { loadingTitle: '更新订单状态...' });
                that.setData({ paying: false });
                that.getExamInfo();
              }, 1000);
            },
            fail: (err) => {
              that.showError(err.errMsg || '支付失败');
              that.setData({ paying: false });
            }
          });
        } catch (err) {
          that.showError(err.message || '缴费失败');
          that.setData({ paying: false });
        }
      }
    });
  },

  viewDetail() {
    wx.navigateTo({ url: '/pages/degree-english-detail/degree-english-detail' });
  }
}, {
  requireAuth: true,
  userType: 'open_student'
});
