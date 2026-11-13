const { createPage } = require('../../../utils/page-mixin');
const { tokenPost, tokenGet } = require('../../../utils/request');
const app = getApp();

createPage({
  data: {
    selectedCourses: [],
    totalFee: 0,
    studentInfo: {},
    paymentInfo: {},
    loading: true
  },

  onLoad: function () {
    this.loadPaymentInfo();
  },

  // 加载支付信息
  async loadPaymentInfo() {
    try {
      this.setData({ loading: true });

      const response = await tokenGet('/student/bk_payment_info', {}, {
        loadingTitle: '加载支付信息...'
      });

      if (response.courses && response.courses.length > 0) {
        this.setData({
          selectedCourses: response.courses,
          totalFee: response.total_amount,
          studentInfo: response.student_info,
          paymentInfo: response.payment_info,
          loading: false
        });
      } else {
        this.setData({ loading: false });
        this.showError('没有待支付的报考科目');
        setTimeout(() => {
          wx.navigateBack();
        }, 2000);
      }
    } catch (err) {
      this.setData({ loading: false });
      this.showError(err.message || '加载支付信息失败');
      setTimeout(() => {
        wx.navigateBack();
      }, 2000);
    }
  },

  calculateTotal: function () {
    // 使用每门课程的fee计算总费用
    const totalFee = this.data.selectedCourses.reduce(
      (sum, course) => sum + (parseFloat(course.fee) || 0),
      0
    );
    this.setData({ totalFee });
  },

  handleDelete: function (e) {
    const that = this;
    const { index } = e.currentTarget.dataset;
    const selectedCourses = [...this.data.selectedCourses];
    selectedCourses.splice(index, 1);

    this.setData({ selectedCourses }, () => {
      this.calculateTotal();
      if (selectedCourses.length === 0) {
        that.showSuccess("已清空选择的课程");
        setTimeout(() => {
          wx.navigateBack();
        }, 1500);
      }
    });
  },

  handleCancel: function () {
    // 清空全局变量
    wx.navigateBack();
  },

  // 返回首页
  goHome(){
    wx.navigateTo({
      url: '/packageStudent/pages/my/my'
    });
  },
  handleConfirm: async function () {
    const that = this;
    if (this.data.selectedCourses.length === 0) {
      that.showError("请选择需要报考的课程");
      return;
    }

    // 获取openid_code
    const openid_code = await app.getOpenid_code();
    if (!openid_code) {
      this.showError('获取openid_code失败，请重试');
      return;
    }


    
    // 生成缴费订单，获取支付参数，更新订单状态，跳转到报考页面
    try{
      const request = await tokenPost('/student/courses/preBkPay',{courses: this.data.selectedCourses,openid_code:openid_code},{loadingTitle: '生成缴费订单...'});

      // 检查是否为免费课程
      if (request.is_free) {
        this.showSuccess(request.message || "免费课程报考成功");
        setTimeout(() => {
          wx.navigateTo({
            url: "/packageStudent/pages/payment-bukao/payment-bukao",
          });
        }, 2000);
        return;
      }

      const payParams = request;
      // 调用微信支付
      wx.requestPayment({
        timeStamp: payParams.timeStamp,
        nonceStr: payParams.nonceStr,
        package: payParams.package,
        signType: payParams.signType,
        paySign: payParams.paySign,
        orderNo: payParams.orderNo,
        success: () => {
          // 更新订单状态
          try{
            // 更新订单状态,延迟1秒再更新，避免支付成功后立即查询，导致订单状态未更新
            setTimeout(async () => {
              await tokenPost('/student/updateBkPayStatus',{order_no: payParams.orderNo},{loadingTitle: '更新订单状态...'});
            }, 1000);

            this.showSuccess("支付成功");
            // 跳转到报考页面
            setTimeout(() => {
              wx.navigateTo({
                url: "/packageStudent/pages/payment-bukao/payment-bukao",
              });
            }, 2000);

          }catch(err){
            this.showError(err.message || "更新订单状态失败");
          }
        },
        fail: (err) => {
          this.showError(err.errMsg || "支付失败");
        }
      });

    }catch(err){
      this.showError(err.message || "生成缴费订单失败");
    }

  }
},{
  requireAuth: true,
  userType: 'open_student'
});
