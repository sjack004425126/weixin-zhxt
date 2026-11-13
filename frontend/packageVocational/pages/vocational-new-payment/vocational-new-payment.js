const { createPage } = require('../../../utils/page-mixin');
const { get, post } = require('../../../utils/request');
const { checkFeatureSwitch } = require('../../../utils/feature-switch');
const { drawWatermarkImage, buildWatermarkText } = require('../../../utils/watermark');
const commonAuth = require('../../../utils/common-auth');
const app = getApp();

createPage({
  data: {
    // ===== 查询模式 =====
    queryMode: 'code',
    queryCode: '',
    // 微信手机号快捷登录验证
    verifiedPhoneToken: '',
    verifiedPhone: '',
    verifiedPhoneMasked: '',
    // 界面状态
    showResult: false,
    payorder_xx: null,
    zyxx: null,
    jfxx: null,
    isShowPayBtn: false,
    showPayConfirm: false,
    paidTip: false,
    downloadingPdf: false,
    o_id: null,
    // ===== 防伪相关（仅保留水印） =====
    watermarkPath: '',
    // 水印横幅展示所需字段（showResult=true 时才有值）
    watermarkName: '',
    watermarkTime: '',
    phoneTail: '',
    schoolPhone: '',
    // ===== 家长通知 =====
    parentNotifySent: false,
    parentNotifyMsg: '',
    // ===== 查询模式 UI 展示（避免依赖 computed） =====
    queryModeIcon: 'description',
    queryModeTitle: '查询码查询（推荐）',
    queryModeDesc: '直接输入查询码，无需任何验证',
  },

  onLoad(options) {
    checkFeatureSwitch('zzpay', this);

    // 外部直接带入查询码（家长扫码进入场景）
    const queryCode = options.queryCode || '';
    if (queryCode) {
      this.setData({ queryMode: 'code', queryCode });
      this.onCheckPayment();
    }
  },

  onShow() {
    // 7 天缓存命中：仅在 phone_self / phone_parent 模式下尝试自动校验
    const mode = this.data.queryMode;
    if (mode === 'phone_self' || mode === 'phone_parent') {
      this.tryAutoVerifyFromCache();
    }
  },

  // ============================================================
  // 缓存命中检测：命中后直接换 verify_token，跳过 wx.getPhoneNumber
  // ============================================================
  tryAutoVerifyFromCache() {
    if (this.data.verifiedPhoneToken) return; // 已有 token，跳过

    const role = this.data.queryMode === 'phone_self' ? 'self' : 'parent';
    commonAuth.fetchCachedVerify(commonAuth.SUBJECT.VOCATIONAL_PAYMENT)
      .then((cached) => {
        if (!cached || !cached.cached) return null;
        // 检查缓存中的 role 与当前 mode 是否一致
        if (cached.role && cached.role !== role) return null;
        return commonAuth.wxLogin().then((loginCode) => {
          return post(
            '/auth/issue_verify_token_by_cache',
            { login_code: loginCode, subject: commonAuth.SUBJECT.VOCATIONAL_PAYMENT, role },
            { loadingTitle: '正在校验身份...' }
          );
        });
      })
      .then((res) => {
        // res 已经是 responseData.data（post() 在 _parseResponse 里剥过层）
        if (!res || !res.verify_token) return;
        this.setData({
          verifiedPhone: res.verify_token,
          verifiedPhoneToken: res.verify_token,
          verifiedPhoneMasked: res.masked_phone || '',
        });
        this.showSuccess('身份验证通过（来自缓存，7 天内免授权）');
      })
      .catch(() => {
        // 缓存未命中或异常 → 静默回退到正常授权流程
      });
  },

  onReady() {
    // 首次就绪后再尝试绘制水印（canvas 节点确定 ready）
    if (this.data.showResult && this.data.watermarkName) {
      setTimeout(() => this.drawWatermark(), 100);
    }
  },

  // ============================================================
  // 查询模式切换
  // ============================================================
  onSwitchQueryMode(e) {
    const mode = e.currentTarget.dataset.mode;
    if (!mode || mode === this.data.queryMode) return;

    const modeMap = {
      code:          { icon: 'description', title: '查询码查询（推荐）',   desc: '直接输入查询码，无需任何验证' },
      phone_self:    { icon: 'phone-o', title: '本人手机号验证',  desc: '需本人微信绑定手机号与报名预留手机号一致' },
      phone_parent:  { icon: 'contact', title: '家长手机号验证',  desc: '需家长微信绑定手机号与报名预留家长手机号一致' },
    };
    const info = modeMap[mode] || modeMap.code;

    this.setData({
      queryMode: mode,
      queryModeIcon: info.icon,
      queryModeTitle: info.title,
      queryModeDesc: info.desc,
      // 切换时清空已验证状态
      verifiedPhone: '',
      verifiedPhoneToken: '',
      verifiedPhoneMasked: '',
      // 切回查询视图
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

    const role = this.data.queryMode === 'phone_self' ? 'self' : 'parent';

    // 同时获取 wx.login 的 code，让后端 verify_phone_for_payment
    // 内部换 openid 并写入 7 天缓存（让其它子系统也可复用）
    commonAuth.wxLogin()
      .then((loginCode) => post(
        '/vocational_tuition/verify_phone_for_payment',
        {
          code,
          role,
          openid_code: '',
          login_code: loginCode,
          subject: commonAuth.SUBJECT.VOCATIONAL_PAYMENT
        },
        { loadingTitle: '正在校验身份...' }
      ))
      .then((res) => {
        const token = (res && (res.verify_token || res.token)) || '';
        const masked = (res && (res.masked_phone || res.phone)) || '';
        if (!token) {
          this.showError('手机号校验失败，请确认是报名预留的手机号');
          return;
        }
        this.setData({
          verifiedPhone: token,
          verifiedPhoneToken: token,
          verifiedPhoneMasked: masked,
        });
        this.showSuccess('身份验证通过');
        // 7 天缓存由后端在 verify_phone_for_payment 内部写入（res.cache_written）
      })
      .catch((err) => {
        this.showError(err.message || '身份校验失败');
      });
  },

  clearVerifiedPhone() {
    this.setData({
      verifiedPhone: '',
      verifiedPhoneToken: '',
      verifiedPhoneMasked: '',
    });
    // 主动清缓存（"重选身份"）
    commonAuth.clearCache().catch(() => {});
  },

  // ============================================================
  // 查询入口
  // ============================================================
  async onCheckPayment() {
    const mode = this.data.queryMode;

    // 参数校验
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
        : {
            verify_token: this.data.verifiedPhoneToken,
            role: mode === 'phone_self' ? 'self' : 'parent',
          };

      const result = await get(
        '/vocational_tuition/new-student-checkPayment',
        params,
        { loadingTitle: '正在查询报名信息...' }
      );

      const {
        jfxx, payorder_xx, zyxx,
        student_name, verified_name, school_phone,
      } = result;

      // 金额字符串化
      if (jfxx) {
        jfxx.xfStr    = jfxx.xf   ? (jfxx.xf   / 100).toFixed(2) : '0.00';
        jfxx.zsfStr   = jfxx.zsf  ? (jfxx.zsf  / 100).toFixed(2) : '0.00';
        jfxx.sfStr    = jfxx.sf   ? (jfxx.sf   / 100).toFixed(2) : '0.00';
        const totalFen = (Number(jfxx.xf || 0) + Number(jfxx.zsf || 0) + Number(jfxx.sf || 0));
        jfxx.totalStr = (totalFen / 100).toFixed(2);
      }
      if (payorder_xx) {
        payorder_xx.moneyStr = payorder_xx.o_money
          ? (payorder_xx.o_money / 100).toFixed(2)
          : '0.00';
      }

      // 水印横幅元数据
      const displayName = student_name || verified_name || '';
      const now = new Date();
      const pad = (n) => String(n).padStart(2, '0');
      const timeStr = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())} ` +
        `${pad(now.getHours())}:${pad(now.getMinutes())}`;

      // 取手机号尾号用于水印
      const masked = (this.data.verifiedPhoneMasked || '').trim();
      const phoneTail = masked ? `****${masked.slice(-4)}` : '';

      this.setData({
        showResult: true,
        jfxx,
        zyxx,
        payorder_xx,
        isShowPayBtn: !payorder_xx || payorder_xx.o_status == 0,
        paidTip: !!(payorder_xx && payorder_xx.o_status == 1),
        watermarkName: displayName,
        watermarkTime: timeStr,
        phoneTail,
        schoolPhone: school_phone || '',
      });

      console.log('[watermark] onCheckPayment setData:', {
        student_name, verified_name, displayName, phoneTail, timeStr,
        zyxx_xm: jfxx ? null : (zyxx && zyxx.xm),
      });

      // 渲染水印（查询成功后才有，onCheckPayment 后必定调用）
      // 多次重试确保 canvas 节点就绪
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
    // 清空水印 canvas 上的像素残留
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
    });
  },

  // ============================================================
  // 清空水印 canvas（clearRect，避免像素残留）
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
        console.log('[watermark] cleared canvas');
      });
  },

  // ============================================================
  // 渲染水印（仅在查询成功后调用）
  // ============================================================
  drawWatermark(retryCount = 0) {
    console.log('[watermark] drawWatermark called, showResult=', this.data.showResult, 'name=', this.data.watermarkName, 'retry=', retryCount);

    if (!this.data.showResult) {
      console.log('[watermark] showResult is false, skip');
      return;
    }

    // 取姓名（后端接口实际姓名字段为 zyxx.xm）
    const name =
      this.data.watermarkName ||
      (this.data.zyxx && (this.data.zyxx.xm || this.data.zyxx.student_name)) ||
      (this.data.jfxx && this.data.jfxx.student_name) ||
      '';

    if (!name) {
      console.log('[watermark] no student name found, skip drawing');
      return;
    }

    const phoneTail = (this.data.phoneTail || '').trim();
    const time = this.data.watermarkTime || '';
    const text = `黔东南中等职业技术学校 · ${name}${phoneTail ? ' · ' + phoneTail : ''}${time ? ' · ' + time : ''}`;

    console.log('[watermark] drawing text:', text);

    const query = wx.createSelectorQuery().in(this);
    query
      .select('#page-watermark')
      .fields({ node: true, size: true })
      .exec((res) => {
        console.log('[watermark] selector result:', JSON.stringify({
          found: !!(res && res[0] && res[0].node),
          size: res && res[0] ? { w: res[0].width, h: res[0].height } : null,
        }));
        if (!res || !res[0] || !res[0].node) {
          console.warn('[watermark] canvas node not found, retry in 300ms');
          if (retryCount < 5) {
            setTimeout(() => this.drawWatermark(retryCount + 1), 300);
          }
          return;
        }

        const canvas = res[0].node;
        const ctx = canvas.getContext('2d');
        const sys = wx.getSystemInfoSync();
        const dpr = sys.pixelRatio || 2;
        const w = res[0].width || sys.windowWidth;
        const h = res[0].height || sys.windowHeight;

        canvas.width = w * dpr;
        canvas.height = h * dpr;
        ctx.scale(dpr, dpr);

        ctx.clearRect(0, 0, w, h);
        ctx.fillStyle = 'rgba(0, 0, 0, 0.14)';
        ctx.font = '14px "PingFang SC","Helvetica Neue",sans-serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';

        const rotateDeg = -20;
        const colWidth = 240;
        const rowHeight = 80;
        const cols = Math.ceil(w / colWidth) + 2;
        const rows = Math.ceil(h / rowHeight) + 2;
        const angle = (rotateDeg * Math.PI) / 180;

        for (let i = -1; i < cols; i++) {
          for (let j = -1; j < rows; j++) {
            const x = i * colWidth;
            const y = j * rowHeight;
            const xOff = (j % 2 === 0) ? 0 : colWidth / 2;
            ctx.save();
            ctx.translate(x + xOff, y);
            ctx.rotate(angle);
            ctx.fillText(text, 0, 0);
            ctx.restore();
          }
        }

        console.log('[watermark] draw done:', { cols, rows, w, h, dpr, text });
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
    if (this.data.queryMode !== 'code' && !this.data.verifiedPhoneToken) {
      this.showError('身份验证已失效，请重新验证');
      return;
    }

    const openid_code = await app.getOpenid_code();
    if (!openid_code) {
      this.showError('获取openid_code失败，请重试');
      return;
    }

    try {
      const payParams = this.data.queryMode === 'code'
        ? { queryCode: this.data.queryCode, openid_code }
        : { openid_code, verify_token: this.data.verifiedPhoneToken };

      const resquest = await get(
        '/vocational_tuition/get_pre_payment_info',
        payParams,
        { loadingTitle: '正在生成支付参数...' }
      );

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
                '/vocational_tuition/update_pre_payment_order_status',
                { o_order_no: resquest.orderNo },
                { showLoading: false }
              );

              // 通知家长
              post(
                '/vocational_tuition/notify_parent_after_payment',
                { o_order_no: resquest.orderNo },
                { showLoading: false }
              )
                .then((notifyRes) => {
                  that.setData({
                    parentNotifySent: true,
                    parentNotifyMsg: (notifyRes && notifyRes.msg) || '已通知家长',
                  });
                })
                .catch((notifyErr) => {
                  that.setData({
                    parentNotifySent: false,
                    parentNotifyMsg: (notifyErr && notifyErr.msg) || '通知发送失败，请联系学校',
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

  // ============================================================
  // 录取通知书下载
  // ============================================================
  async downloadAdmissionNotice() {
    if (this.data.downloadingPdf) {
      this.showError('正在下载中，请稍后再试');
      return;
    }
    if (!this.data.paidTip) {
      this.showError('请先完成缴费');
      return;
    }
    this.setData({ downloadingPdf: true });
    try {
      const result = await get(
        '/zzbm/generate_admission_notice_pdf_data',
        { o_id: this.data.payorder_xx && this.data.payorder_xx.o_id },
        { timeout: 60000, loadingTitle: '正在生成通知书...' }
      );
      this.saveAndShowSuccessDialog(result);
    } catch (err) {
      this.setData({ downloadingPdf: false });
      this.showError(err.message || '通知书生成失败');
    }
  },

  saveAndShowSuccessDialog(responseData) {
    const fs = wx.getFileSystemManager();
    const safeName = `录取通知书_${Date.now()}.pdf`;
    const filePath = `${wx.env.USER_DATA_PATH}/${safeName}`;
    const fileSizeKB = responseData.pdf_base64
      ? (responseData.pdf_base64.length * 0.75 / 1024).toFixed(2)
      : '0';

    fs.writeFile({
      filePath,
      data: responseData.pdf_base64,
      encoding: 'base64',
      success: () => {
        this.setData({ downloadingPdf: false });
        this.showFileActionSheet(filePath, safeName, fileSizeKB);
      },
      fail: (err) => {
        this.setData({ downloadingPdf: false });
        console.error('writeFile failed', err);
        wx.showToast({ title: '文件保存失败', icon: 'error' });
      },
    });
  },

  showFileActionSheet(filePath, fileName, fileSizeKB) {
    wx.showActionSheet({
      itemList: ['查看 PDF', '分享文件', '复制路径'],
      success: (res) => {
        switch (res.tapIndex) {
          case 0: this.openPdfFile(filePath); break;
          case 1: this.sharePdfFile(filePath, fileName); break;
          case 2: this.copyFilePath(filePath); break;
        }
      },
      fail: () => this.openPdfFile(filePath),
    });
  },

  openPdfFile(filePath) {
    wx.openDocument({
      filePath,
      fileType: 'pdf',
      fail: (err) => {
        console.error('openDocument failed', err);
        wx.showModal({ title: '提示', content: '文件打开失败', showCancel: false });
      },
    });
  },

  copyFilePath(filePath) {
    wx.setClipboardData({ data: filePath, success: () => wx.showToast({ title: '已复制', icon: 'success' }) });
  },

  sharePdfFile(filePath, fileName) {
    wx.shareFileMessage({
      filePath,
      fileName,
      fail: (err) => {
        console.error('shareFileMessage failed', err);
        wx.showModal({ title: '分享失败', content: '无法分享，是否直接查看？', success: (r) => r.confirm && this.openPdfFile(filePath) });
      },
    });
  },

  onShareAppMessage() {
    return {
      title: '中职新生缴费',
      path: '/packageVocational/pages/vocational-new-payment/vocational-new-payment',
    };
  },
}, {
  requireAuth: false,
});