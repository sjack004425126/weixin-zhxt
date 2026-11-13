const { createPage } = require('../../../utils/page-mixin');
const { get, post } = require('../../../utils/request');
const { checkFeatureSwitch } = require('../../../utils/feature-switch');
const { drawWatermarkImage, buildWatermarkText } = require('../../../utils/watermark');
const app = getApp();

createPage({
  data: {
    // ===== 查询模式 =====
    queryMode: 'code',
    queryCode: '',
    // 微信手机号验证
    verifiedPhoneToken: '',
    verifiedPhoneMasked: '',
    // 界面状态
    showResult: false,
    payorder_xx: null,
    paidTip: false,
    isShowPayBtn: false,
    showPayConfirm: false,
    o_id: null,
    // 报名信息
    zyxx: null,
    jfxx: null,
    // ===== 防伪相关 =====
    watermarkPath: '',
    watermarkName: '',
    watermarkTime: '',
    phoneTail: '',
    schoolPhone: '',
    // ===== 家长通知 =====
    parentNotifySent: false,
    parentNotifyMsg: '',
    // ===== 查询模式 UI 展示 =====
    queryModeIcon: 'description',
    queryModeTitle: '查询码查询',
    queryModeDesc: '输入报名成功后收到的查询码',
  },

  onLoad(options) {
    checkFeatureSwitch('kfpay_query', this);

    // 缓存的查询码自动填充
    const cachedCode = wx.getStorageSync('kfxf_last_query_code') || '';
    if (cachedCode) {
      this.setData({ queryCode: cachedCode });
    }

    // 外部直接带入查询码（优先）
    const queryCode = options.queryCode || '';
    if (queryCode) {
      this.setData({ queryMode: 'code', queryCode });
      this.onCheckPayment();
    }
  },

  onReady() {
    if (this.data.showResult && this.data.watermarkName) {
      setTimeout(() => this.drawWatermark(), 100);
    }
  },

  // ============================================================
  // 查询模式切换（仅查询码和本人手机号）
  // ============================================================
  onSwitchQueryMode(e) {
    const mode = e.currentTarget.dataset.mode;
    if (!mode || mode === this.data.queryMode) return;

    const modeMap = {
      code:        { icon: 'description', title: '查询码查询',      desc: '输入报名成功后收到的查询码' },
      phone_self:  { icon: 'phone-o',    title: '本人手机号验证',  desc: '需本人微信绑定手机号与报名预留手机号一致' },
    };
    const info = modeMap[mode] || modeMap.code;

    this.setData({
      queryMode: mode,
      queryModeIcon: info.icon,
      queryModeTitle: info.title,
      queryModeDesc: info.desc,
      verifiedPhoneToken: '',
      verifiedPhoneMasked: '',
      showResult: false,
      payorder_xx: null,
      zyxx: null,
      jfxx: null,
      paidTip: false,
    });
  },

  onQueryCodeInput(e) {
    this.setData({ queryCode: e.detail.value });
  },

  // ============================================================
  // 微信手机号快捷登录验证
  // ============================================================
  onVerifyByPhone(e) {
    if (!e || !e.detail) {
      this.showError('获取手机号失败，请重试');
      return;
    }
    if (e.detail.errMsg !== 'getPhoneNumber:ok') {
      this.showError('获取手机号失败，请重试');
      return;
    }
    const code = e.detail.code;
    if (!code) {
      this.showError('获取手机号失败，请重试');
      return;
    }

    post(
      '/freshman_tuition/verify_phone_for_payment',
      { code },
      { loadingTitle: '正在校验身份...' }
    )
      .then((data) => {
        const token = (data && (data.verify_token || data.token)) || '';
        const masked = (data && (data.masked_phone || data.phone)) || '';
        if (!token) {
          this.showError('手机号校验失败，请确认是报名预留的手机号');
          return;
        }
        this.setData({
          verifiedPhoneToken: token,
          verifiedPhoneMasked: masked,
        });
        this.showSuccess('身份验证通过');
      })
      .catch((err) => {
        this.showError(err.message || '身份校验失败');
      });
  },

  clearVerifiedPhone() {
    this.setData({
      verifiedPhoneToken: '',
      verifiedPhoneMasked: '',
    });
  },

  // ============================================================
  // 查询入口
  // ============================================================
  async onCheckPayment() {
    const mode = this.data.queryMode;

    if (mode === 'code') {
      const code = this.data.queryCode.trim();
      if (!code || code.length < 4) {
        this.showError('请输入有效的查询码');
        return;
      }
    } else {
      if (!this.data.verifiedPhoneToken) {
        this.showError('请先完成微信身份验证');
        return;
      }
    }

    try {
      const params = mode === 'code'
        ? { queryCode: this.data.queryCode.trim() }
        : { verify_token: this.data.verifiedPhoneToken };

      const result = await get(
        '/freshman_tuition/new-student-checkPayment',
        params,
        { loadingTitle: '正在查询报名信息...' }
      );
      const { jfxx, payorder_xx, zyxx, student_name, verified_name, school_phone } = result;

      // 后端已计算好 xfStr 等，这里做兜底
      if (jfxx && !jfxx.xfStr) {
        const xf  = jfxx.xf  || 0;
        const sf  = jfxx.sf  || 0;
        const zsf = jfxx.zsf || 0;
        jfxx.xfStr    = (xf  / 100).toFixed(2);
        jfxx.sfStr    = (sf  / 100).toFixed(2);
        jfxx.zsfStr   = (zsf / 100).toFixed(2);
        jfxx.totalStr = ((xf + sf + zsf) / 100).toFixed(2);
      }
      if (payorder_xx && !payorder_xx.moneyStr) {
        payorder_xx.moneyStr = payorder_xx.o_money
          ? (payorder_xx.o_money / 100).toFixed(2)
          : '0.00';
      }

      const displayName = student_name || verified_name || '';
      const now = new Date();
      const pad = (n) => String(n).padStart(2, '0');
      const timeStr = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())} ` +
        `${pad(now.getHours())}:${pad(now.getMinutes())}`;

      const masked = (this.data.verifiedPhoneMasked || '').trim();
      const phoneTail = masked ? `****${masked.slice(-4)}` : '';

      this.setData({
        showResult: true,
        jfxx: jfxx || null,
        zyxx: zyxx || null,
        payorder_xx: payorder_xx || null,
        paidTip: !!(payorder_xx && payorder_xx.o_status == 1),
        isShowPayBtn: !(payorder_xx && payorder_xx.o_status == 1),
        watermarkName: displayName,
        watermarkTime: timeStr,
        phoneTail,
        schoolPhone: school_phone || '',
      });

      // 查询成功后缓存查询码
      if (this.data.queryMode === 'code' && this.data.queryCode) {
        wx.setStorageSync('kfxf_last_query_code', this.data.queryCode);
      }

      setTimeout(() => this.drawWatermark(), 300);
      setTimeout(() => this.drawWatermark(), 800);
      setTimeout(() => this.drawWatermark(), 1500);
    } catch (err) {
      console.warn('onCheckPayment error', err);
      this.showError(err);
    }
  },

  // ============================================================
  // 重新查询 → 返回查询界面
  // ============================================================
  onReQuery() {
    this.clearWatermark();
    this.setData({
      showResult: false,
      payorder_xx: null,
      zyxx: null,
      jfxx: null,
      paidTip: false,
      watermarkPath: '',
      watermarkName: '',
      watermarkTime: '',
      phoneTail: '',
      parentNotifySent: false,
      parentNotifyMsg: '',
    });
  },

  // ============================================================
  // 清空水印 canvas
  // ============================================================
  clearWatermark() {
    const query = wx.createSelectorQuery().in(this);
    query
      .select('#page-watermark')
      .fields({ node: true, size: true })
      .exec((res) => {
        if (!res || !res[0] || !res[0].node) return;
        const canvas = res[0].node;
        const ctx = canvas.getContext('2d');
        const sys = wx.getSystemInfoSync();
        const dpr = sys.pixelRatio || 2;
        const w = res[0].width || sys.windowWidth;
        const h = res[0].height || sys.windowHeight;
        canvas.width = w * dpr;
        canvas.height = h * dpr;
        ctx.clearRect(0, 0, w * dpr, h * dpr);
      });
  },

  // ============================================================
  // 渲染水印
  // ============================================================
  drawWatermark(retryCount = 0) {
    if (!this.data.showResult) return;

    const name =
      this.data.watermarkName ||
      (this.data.zyxx && this.data.zyxx.xm) ||
      '';

    if (!name) return;

    const phoneTail = (this.data.phoneTail || '').trim();
    const time = this.data.watermarkTime || '';
    const text = buildWatermarkText({
      name,
      idNumber: phoneTail.replace(/\*/g, ''),
      timestamp: time,
    });

    const sys = wx.getSystemInfoSync();
    const query = wx.createSelectorQuery().in(this);
    query
      .select('#page-watermark')
      .fields({ node: true, size: true })
      .exec((res) => {
        if (!res || !res[0] || !res[0].node) {
          if (retryCount < 5) {
            setTimeout(() => this.drawWatermark(retryCount + 1), 300);
          }
          return;
        }
        const width = res[0].width || sys.windowWidth;
        const height = res[0].height || sys.windowHeight;
        drawWatermarkImage({
          selector: '#page-watermark',
          text,
          width,
          height,
          opacity: 0.08,
          color: '#000000',
          fontSize: 22,
          rotate: -22,
          density: 4,
          component: this,
        }).catch(() => {
          if (retryCount < 3) {
            setTimeout(() => this.drawWatermark(retryCount + 1), 300);
          }
        });
      });
  },

  // ============================================================
  // 缴费确认
  // ============================================================
  showPayConfirmBox() {
    if (!this.data.jfxx || this.data.paidTip) return;
    this.setData({ showPayConfirm: true, isShowPayBtn: false });
  },

  hidePayConfirmBox() {
    this.setData({ showPayConfirm: false, isShowPayBtn: true });
  },

  // ============================================================
  // 发起支付
  // ============================================================
  async onStartPayment() {
    this.setData({ showPayConfirm: false });
    const that = this;

    if (this.data.queryMode === 'code' && !this.data.queryCode) {
      this.showError('查询码已失效，请重新查询');
      return;
    }
    if (this.data.queryMode === 'phone_self' && !this.data.verifiedPhoneToken) {
      this.showError('身份验证已失效，请重新验证');
      return;
    }

    const openid_code = await app.getOpenid_code();
    if (!openid_code) {
      this.showError('获取 openid_code 失败，请重试');
      return;
    }

    try {
      const payParams = this.data.queryMode === 'code'
        ? { queryCode: this.data.queryCode, openid_code }
        : { openid_code, verify_token: this.data.verifiedPhoneToken };

      const resquest = await get(
        '/freshman_tuition/get_pre_payment_info',
        payParams,
        { loadingTitle: '正在生成支付参数...' }
      );

      if (!resquest || !resquest.timeStamp) {
        this.showError(resquest && resquest.msg ? resquest.msg : '支付参数获取失败');
        return;
      }

      wx.requestPayment({
        timeStamp: resquest.timeStamp,
        nonceStr: resquest.nonceStr,
        package: resquest.package,
        signType: resquest.signType,
        paySign: resquest.paySign,
        orderNo: resquest.orderNo,
        success() {
          setTimeout(async () => {
            try {
              await get(
                '/freshman_tuition/update_pre_payment_order_status',
                { o_order_no: resquest.orderNo },
                { showLoading: false }
              );

              post(
                '/freshman_tuition/notify_parent_after_payment',
                { o_order_no: resquest.orderNo },
                { showLoading: false }
              )
                .then((notifyRes) => {
                  that.setData({
                    parentNotifySent: true,
                    parentNotifyMsg: (notifyRes && notifyRes.msg) || '已通知',
                  });
                })
                .catch((notifyErr) => {
                  that.setData({
                    parentNotifySent: false,
                    parentNotifyMsg: (notifyErr && notifyErr.msg) || '通知发送失败',
                  });
                });

              that.showSuccess('支付成功');
              that.onCheckPayment();
            } catch (e) {
              console.warn(e);
            }
          }, 1000);
        },
        fail(err) {
          that.showError(err.errMsg || '支付取消');
        },
      });
    } catch (err) {
      this.showError(err);
      this.setData({ showResult: false });
    }
  },

  onShareAppMessage() {
    return {
      title: '开放新生报名情况查询',
      path: '/packageEnroll/pages/enrollment-query/enrollment-query',
    };
  },
}, {
  requireAuth: false,
});
