// 中职老生缴费页面
const { createPage } = require('../../../utils/page-mixin');
const { tokenGet } = require('../../../utils/request');
const app = getApp();

createPage({
  data: {
    loading: true,
    paymentProcessing: false,
    showPayConfirm: false,

    // 学生信息
    studentInfo: null,

    // 学期缴费信息
    currentTerm: 0,
    semesterPayments: [],
    totalTerms: 6,

    // 错误信息
    errorMsg: '',

    // 选中的学期信息（用于支付确认）
    selectedSemester: null
  },

  onLoad: function() {
    this.loadTuitionInfo();
  },

  onShow: function() {
    // 页面显示时刷新数据
    if (!this.data.loading) {
      this.loadTuitionInfo();
    }
  },

  onUnload: function() {
    clearTimeout(this._backTimer);
  },


  // 加载学费信息
  loadTuitionInfo: async function() {
    try {
      this.setData({
        loading: true,
        errorMsg: ''
      });

      const response = await tokenGet('/vocational_tuition/old_student_tuition_info');
      const data = response || {};

      // 从全局数据获取学生信息
      const userInfo = app.globalData.userInfo;

      // 生成完整的学期列表（1-6学期）
      const currentTerm = userInfo.current_term;

      // 将后端数据转换为以学期号为 key 的对象（有无支付订单以 o_order_no 判断；最后一条为当前学期）
      const paymentMap = {};
      const rawList = data.semester_payments || [];
      rawList.forEach((payment, index) => {
        const termNumber = payment.term_number;
        const hasOrder = !!(payment.o_order_no != null && payment.o_order_no !== '');
        // 有订单：用 o_zsf/o_sf/o_money（分→元）；无订单：用 zsf/sf（分→元），总价=zsf+sf
        const zsfYuan = hasOrder
          ? Number(payment.o_zsf != null ? payment.o_zsf : 0) / 100
          : Number(payment.zsf != null ? payment.zsf : 0) / 100;
        const sfYuan = hasOrder
          ? Number(payment.o_sf != null ? payment.o_sf : 0) / 100
          : Number(payment.sf != null ? payment.sf : 0) / 100;
        const totalFee = hasOrder
          ? Number(payment.o_money != null ? payment.o_money : 0) / 100
          : (zsfYuan + sfYuan);
        const status = (payment.o_status === 1) ? 'paid' : 'unpaid';
        const needPay = payment.needPay === true;
        const noPayReasons = payment.no_pay_reasons || [];

        paymentMap[termNumber] = {
          term_number: termNumber,
          term_desc: `第${termNumber}学期`,
          zsf: zsfYuan,
          sf: sfYuan,
          total_fee: totalFee,
          status,
          needPay,
          no_pay_reasons: noPayReasons,
          pay_time: payment.o_paytime ? this.formatPayTime(payment.o_paytime) : null,
          order_no: payment.o_order_no || '',
          o_id: payment.o_id,
          o_status: payment.o_status
        };
      });

      // 生成 1 到 currentTerm 的学期列表，当前学期根据 needPay / 订单状态决定是否展示缴费按钮
      const allSemesters = [];
      for (let term = 1; term <= 6; term++) {
        if (term > currentTerm) break;
        if (paymentMap[term]) {
          const payment = paymentMap[term];
          payment.is_current_term = term === currentTerm;
          // needPay 为 true 且未支付 → 展示缴费按钮；needPay 为 false → 不展示按钮，展示 no_pay_reasons
          payment.can_pay = payment.is_current_term && payment.needPay && (payment.status !== 'paid');
          allSemesters.push(payment);
        } else {
          // 历史学期无记录时仅展示占位，不可缴费
          allSemesters.push({
            term_number: term,
            term_desc: `第${term}学期`,
            zsf: 0,
            sf: 0,
            total_fee: 0,
            status: 'unknown',
            needPay: false,
            no_pay_reasons: ['暂无缴费信息'],
            pay_time: null,
            can_pay: false,
            is_current_term: term === currentTerm,
            order_no: ''
          });
        }
      }

      const processedPayments = allSemesters;

      this.setData({
        loading: false,
        studentInfo: {
          xm: userInfo.xs_xm,
          xh: userInfo.xs_xh,
          bj_mc: userInfo.class_name,
          zy_mc: userInfo.class_name // 暂时用班级名称
        },
        currentTerm: userInfo.current_term,
        semesterPayments: processedPayments,
        totalTerms: 6,
        errorMsg: ''
      });

    } catch (error) {
      this.showError(error);
    }
  },

  // 格式化支付时间
  // payTime 可能是两种格式：
  //   1. ISO 格式: "2026-09-01T10:16:26"（微信回调的 success_time）
  //   2. 14位数字: "20251014090650"（原始存储格式 YYYYMMDDHHmmss）
  formatPayTime: function(payTime) {
    if (!payTime) return null;

    // 优先按 ISO 格式解析（有 T 分隔符）
    if (typeof payTime === 'string' && payTime.includes('T')) {
      const parts = payTime.split('T');
      if (parts.length === 2) {
        const datePart = parts[0]; // "2026-09-01"
        const timePart = parts[1]; // "10:16:26"
        // datePart 格式已是 "YYYY-MM-DD"，timePart 格式已是 "HH:mm:ss"
        return `${datePart} ${timePart}`;
      }
    }

    // 14位纯数字格式: "20251014090650"
    if (typeof payTime === 'string' && payTime.length === 14) {
      const year = payTime.substring(0, 4);
      const month = payTime.substring(4, 6);
      const day = payTime.substring(6, 8);
      const hour = payTime.substring(8, 10);
      const minute = payTime.substring(10, 12);
      const second = payTime.substring(12, 14);
      return `${year}-${month}-${day} ${hour}:${minute}:${second}`;
    }

    // 兜底：直接返回原值
    return payTime;
  },




  // 重试加载
  retry: function() {
    this.loadTuitionInfo();
  },

  // 创建当前学期订单并跳转到确认页面
  createCurrentSemesterOrder: async function(e) {
    const termNumber = parseInt(e.currentTarget.dataset.term);

    // 直接跳转到缴费确认页面
    wx.navigateTo({
      url: `/packageVocational/pages/vocational-payment-confirm/vocational-payment-confirm?term=${termNumber}`
    });
  },

  // 支付当前学期 - 跳转到确认页面
  payCurrentSemester: async function(e) {
    const termNumber = parseInt(e.currentTarget.dataset.term);
    const orderNo = e.currentTarget.dataset.order || '';

    // 跳转到缴费确认页面
    wx.navigateTo({
      url: `/packageVocational/pages/vocational-payment-confirm/vocational-payment-confirm?term=${termNumber}&order_no=${orderNo}`
    });
  },


  // 阻止事件冒泡
  stopPropagation: function() {
    // 阻止事件冒泡
  },

},{
  requireAuth: true,
  userType: 'vocational_student'
});