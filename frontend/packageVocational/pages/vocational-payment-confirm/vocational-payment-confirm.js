// 缴费确认页面
const { createPage } = require('../../../utils/page-mixin');
const { tokenGet, tokenPost } = require('../../../utils/request');
const app = getApp();

createPage({
  data: {
    loading: true,
    paymentProcessing: false,
    
    // 页面参数
    termNumber: 1,
    orderNo: '',
    
    // 缴费信息
    paymentInfo: null,
    
    // 错误信息
    errorMsg: ''
  },

  onLoad: function() {
    // 防御：userInfo 可能尚未初始化
    const userInfo = app.globalData && app.globalData.userInfo;
    this.setData({
      current_term: userInfo ? userInfo.current_term : 1
    });
    this.loadPaymentInfo();
  },

  // 加载缴费信息
  loadPaymentInfo: async function() {
    this.setData({ loading: true, errorMsg: '' });
    try {
      const response = await tokenGet('/vocational_tuition/get_old_student_pre_payment');
      console.log(response)

      // 防御：后端返回 success:False 时给出明确提示
      if (response.success === false || response.needPay === false) {
        const reasons = response.no_pay_reasons || [];
        const message = response.message || (reasons.length > 0 ? reasons[0] : '当前无需缴费');
        this.setData({
          loading: false,
          paymentInfo: {
            needPay: false,
            zsf: 0,
            sf: 0,
            totalFee: 0,
            termDesc: `第${this.data.current_term}学期`,
            no_pay_reasons: reasons.length > 0 ? reasons : [message]
          },
          errorMsg: reasons.length > 0 ? reasons.join('；') : message
        });
        return;
      }

      // 处理缴费信息
      const paymentInfo = {
        needPay: response.needPay,
        zsf: (response.zsf || 0) / 100, // 转换为元
        sf: (response.sf || 0) / 100,    // 转换为元
        totalFee: ((response.zsf || 0) + (response.sf || 0)) / 100, // 总费用
        termDesc: `第${this.data.current_term}学期`,
        no_pay_reasons: response.no_pay_reasons || []
      };

      this.setData({
        loading: false,
        paymentInfo: paymentInfo,
        errorMsg: ''
      });

    } catch (error) {
      this.showError(error);
      // 3秒后返回上一页
      clearTimeout(this._backTimer);
      this._backTimer = setTimeout(() => {
        wx.navigateBack({ delta: 1 });
      }, 3000);
    }
  },

  // 确认缴费
  confirmPayment: async function() {
    if (!this.data.paymentInfo || !this.data.paymentInfo.needPay) {
      this.showError('当前无需缴费');
      return;
    }
    if (this.data.paymentInfo.totalFee <= 0) {
      this.showError('缴费金额为 0，无法发起支付');
      return;
    }

    const that = this;
    this.setData({
      paymentProcessing: true
    });

    const openid_code = await app.getOpenid_code();

    try {
      // 获取预支付参数
      const response = await tokenGet('/vocational_tuition/create_old_student_pre_payment', { openid_code: openid_code }, { loadingTitle: '获取支付参数...' });
      // 调用微信支付,拉起支付界面
      wx.requestPayment({
        timeStamp: response.timeStamp,
        nonceStr: response.nonceStr,
        package: response.package,
        signType: response.signType,
        paySign: response.paySign,
        success: (res) => {
          that.showSuccess("支付成功");
          // 返回上一页并刷新
          setTimeout(async () => {
            try {
              await that.updateOrderStatus();
            } catch (error) {
              that.showError(error);
            }
            wx.navigateBack();
          }, 5000);

          that.setData({
            paymentProcessing: false
          });
        },
        fail: (err) => {
          that.showError(err.errMsg || "支付失败");
          that.setData({
            paymentProcessing: false
          });
        }
      });

    } catch (err) {
      this.showError(err);
      this.setData({
        paymentProcessing: false
      });
    }
  },

  // 更新订单状态
  async updateOrderStatus() {
    try {
      await tokenGet('/vocational_tuition/update_old_student_order_status', {}, { loadingTitle: '更新订单状态...' });
      this.showSuccess("已支付且更新成功");
    } catch (err) {
      this.showError(err.message || "支付成功，但订单状态更新失败");
    }
  },

  // 返回上一页
  goBack: function() {
    wx.navigateBack();
  },

  // 重试加载
  retry: function() {
    this.loadPaymentInfo();
  }
}, {
  requireAuth: true,
  userType: 'vocational_student'
});
