const { createPage } = require('../../../utils/page-mixin');
const { tokenGet } = require('../../../utils/request');

createPage({
  data: {
    tuitionData: null,
  },

  onLoad() {
    this.getTuitionInfo();
  },

  // 格式化时间
  formatDate(dateStr) {
    if (!dateStr) return '';
    const date = new Date(dateStr);
    const year = date.getFullYear();
    const month = (date.getMonth() + 1).toString().padStart(2, '0');
    const day = date.getDate().toString().padStart(2, '0');
    return `${year}-${month}-${day}`;
  },

  // 获取学费信息
  async getTuitionInfo() {
    try{
      const resquest = await tokenGet('/student/get_student_tuition',{},{loadingTitle: '获取学费信息...'});
      // 处理退费时间格式
      if (resquest.refund_info && resquest.refund_info.refund_time) {
        resquest.refund_info.refund_time = this.formatDate(resquest.refund_info.refund_time);
      }
      if (resquest.refund_info && resquest.refund_info.o_payment_time) {
        resquest.refund_info.o_payment_time = this.formatDate(resquest.refund_info.o_payment_time);
      }
      this.setData({
        tuitionData: resquest,
      });

    }catch(err){
      this.showError(err.message || "获取学费信息失败");
    }

  },
  goHome(){
    wx.navigateTo({
      url: '/packageStudent/pages/my/my'
    });
  },
  // 去缴费
  async goPay() {
    // 跳转到缴费页面
    wx.navigateTo({
      url: '/packageStudent/pages/payment-records/payment-records',
    });
  },

  // 拉起确认收费的界面，如果用户确认成功，则向后台反馈，并更新单子状态。
  confirmRefund(){
    if (wx.canIUse('requestMerchantTransfer')) {
      wx.requestMerchantTransfer({
        mchId: '1575333221',
        appId: wx.getAccountInfoSync().miniProgram.appId,
        package: this.data.tuitionData.refund_info.package_info,
        success: async (res) => {
          try{
            await tokenGet('/student/update_wxxs_tk_payinfo_complete', {refund_id: this.data.tuitionData.refund_info.refund_id},{loadingTitle: '收款中...'});
            this.showSuccess('收款成功');
            wx.navigateTo({
              url: '/packageStudent/pages/tuition/tuition'
            });
          }catch(err){
            this.showError(err.message || '收款失败');
          }
        },
        fail: (res) => {
          console.log('fail:', res);
        },
      });
    } else {
      wx.showModal({
        content: '你的微信版本过低，请更新至最新版本。',
        showCancel: false,
      });
    }
  },
  // 申请退费
  applyRefund() {
    if (this.data.tuitionData.sys_wxxs_xf_tk_payinfo_switch === 1) {
      wx.navigateTo({
        url: `/packageStudent/pages/refund/refund?amount=${Math.abs(this.data.tuitionData.tuition_info.remaining_payment)}`
      });
    } else {
      this.showError('退费功能还未到期开启');
    }
  }

},{
  requireAuth: true,
  userType: 'open_student'
});
