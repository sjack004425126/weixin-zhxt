const { createPage } = require('../../../utils/page-mixin');
const { tokenGet, tokenPost } = require('../../../utils/request');
const app = getApp();

createPage({
  data: {
    records: [],
    needPay: false,
    showPaidRecords: false,
    pendingInfo: null,           // 待支付信息（后端计算返回）
    pendingInfoDisplay: null,    // 格式化后的待支付信息
    paidRecords: [],            // 已支付记录
    hasPending: false,
    hasPaid: false,
  },

  onLoad() {
    this.getPaymentRecords();
  },

  togglePaidRecords() {
    this.setData({
      showPaidRecords: !this.data.showPaidRecords
    });
  },

  async getPaymentRecords() {
    try{
      const response = await tokenGet('/student/getOrderList',{},{loadingTitle: '获取缴费记录...'});

      const { order_list = [], needPay = false, pending_info = null } = response || {};

      const records = order_list.map((item) => ({
        ...item,
        o_xf_display: ((item.o_xf || 0) / 100).toFixed(2),
        o_sf_display: ((item.o_sf || 0) / 100).toFixed(2),
        o_jm_display: ((item.o_jm || 0) / 100).toFixed(2),
        o_money_display: ((item.o_money || 0) / 100).toFixed(2),
        o_addtime_display: this.formatDateTime(item.o_addtime),
        o_paytime_display: item.o_paytime ? this.formatDateTime(item.o_paytime) : null,
      }));

      // 已支付记录
      const paidRecords = records.filter(item => item.o_status === 1);

      // 待支付信息（后端已计算好欠费金额）
      let pendingInfoDisplay = null;
      if (pending_info && pending_info.money > 0) {
        pendingInfoDisplay = {
          money_display: (pending_info.money / 100).toFixed(2),
          xf_display: (pending_info.xf / 100).toFixed(2),
          sf_display: (pending_info.sf / 100).toFixed(2),
          jm_display: (pending_info.jm / 100).toFixed(2),
          body: pending_info.body || '黔东南开放大学-在线缴费',
        };
      }

      this.setData({
        records: records,
        needPay: needPay,
        pendingInfo: pending_info,
        pendingInfoDisplay: pendingInfoDisplay,
        paidRecords: paidRecords,
        hasPending: !!(pending_info && pending_info.money > 0),
        hasPaid: paidRecords.length > 0,
      });
    }catch(err){
      this.showError(err.errMsg || err.message || "获取缴费记录失败");
    }
  },

  // 处理支付
  async handlePay() {
    try{
      const openid_code = await app.getOpenid_code();
      const response = await tokenGet('/student/payXfByOrderNo',{openid_code: openid_code},{loadingTitle: '获取支付参数...'});
      // 后端返回结构: { success, msg, data: { timeStamp, nonceStr, package, signType, paySign } }
      const payParams = response;
      if (!payParams) {
        this.showError(response.msg || '获取支付参数失败');
        return;
      }
      // 从 package 中提取订单号，格式为 "prepay_id=xxx"
      const orderNo = payParams.package ? payParams.package.replace('prepay_id=', '') : '';
      // 调用微信支付,拉起支付界面
      wx.requestPayment({
        timeStamp: payParams.timeStamp,
        nonceStr: payParams.nonceStr,
        package: payParams.package,
        signType: payParams.signType,
        paySign: payParams.paySign,
        success: () => {
          // 延迟1秒后刷新记录，让回调有时间更新订单状态
          setTimeout(() => {
            this.getPaymentRecords();
          }, 1500);
        },
        fail: (err) => {
          if (err.errMsg && err.errMsg.includes('cancel')) {
            // 用户主动取消，不提示错误
            return;
          }
          this.showError(err.errMsg || "支付失败");
        }
      });

    }catch(err){
      this.showError(err.errMsg || err.message || err || "支付失败，请重试");
    }
  },

  // 更新订单状态
  async updateOrderStatus(orderNo) {
    try{
      await tokenPost('/student/updateOrderStatus',{order_no: orderNo},{loadingTitle: '更新订单状态...'});
      this.showSuccess("已支付且更新成功");
      // 重新获取缴费记录
      this.getPaymentRecords();
    }catch(err){
      this.showError(err.message || "支付成功，单订单状态更新失败");
    }
  },

  // 格式化日期时间
  formatDateTime(dateTimeStr) {
    if (!dateTimeStr) return '';

    try {
      // 处理ISO格式时间 "2025-08-06T16:46:54.353000" 或 "2025-07-14T11:18:02"
      const date = new Date(dateTimeStr);

      if (isNaN(date.getTime())) {
        return dateTimeStr; // 如果解析失败，返回原字符串
      }

      const year = date.getFullYear();
      const month = String(date.getMonth() + 1).padStart(2, '0');
      const day = String(date.getDate()).padStart(2, '0');
      const hours = String(date.getHours()).padStart(2, '0');
      const minutes = String(date.getMinutes()).padStart(2, '0');

      return `${year}-${month}-${day} ${hours}:${minutes}`;
    } catch (error) {
      console.error('时间格式化失败:', error);
      return dateTimeStr;
    }
  },

  // 添加时间格式化方法（保留兼容性）
  formatPayTime(timeStr) {
    // 处理支付时间格式 "20240409111905" -> "2024-04-09 11:19:05"
    if (!timeStr || timeStr.length < 14) return timeStr;

    return `${timeStr.slice(0, 4)}-${timeStr.slice(4, 6)}-${timeStr.slice(6, 8)} ${timeStr.slice(8, 10)}:${timeStr.slice(10, 12)}:${timeStr.slice(12, 14)}`;
  },

  // 去缴费页面（空状态下的按钮）
  goToPayment() {
    this.handlePay();
  },

  // 返回个人中心
  goBack() {
    wx.switchTab({
      url: "/packageStudent/pages/my/my",
    });
  },
},{
  requireAuth: true,
  userType: 'open_student'
});
