const { createPage } = require('../../../utils/page-mixin');
const { post, get } = require('../../../utils/request');
const commonAuth = require('../../../utils/common-auth');

createPage({
  data: {
    // 微信手机号快捷登录验证
    verifiedPhoneToken: '',
    verifiedSfzh: '',
    verifiedStudentName: '',
    verifiedPhoneMasked: '',
    // 界面状态
    showResult: false,
    studentInfo: null,
    showEmpty: false,
    // 7 天手机号缓存命中标记
    cacheHit: false,
  },

  onLoad() {
    wx.setNavigationBarTitle({ title: '中职迎新查询' });
  },

  onShow() {
    // 7 天缓存命中 → 直接展示"已登录"，让用户跳过 wx.getPhoneNumber 授权
    this.tryAutoVerifyFromCache();
  },

  // ============================================================
  // 缓存命中检测：onShow / 重新查询 时调用
  // ============================================================
  tryAutoVerifyFromCache() {
    if (this.data.verifiedPhoneToken) {
      // 已有 token（用户已通过 wx.getPhoneNumber），无需再查缓存
      return;
    }
    commonAuth.fetchCachedVerify(commonAuth.SUBJECT.STUDENT_INFO)
      .then((cached) => {
        if (!cached || !cached.cached) {
          return;
        }
        // 命中：用缓存手机号换业务 verify_token
        return commonAuth.wxLogin().then((loginCode) => {
          return post(
            '/auth/issue_verify_token_by_cache',
            {
              login_code: loginCode,
              subject: commonAuth.SUBJECT.STUDENT_INFO,
              role: 'self'
            },
            { loadingTitle: '正在校验身份...' }
          );
        }).then((res) => {
          // post() 在 _parseResponse 里已剥过 success 层 → res 本身就是 data
          if (!res || !res.verify_token) {
            return;
          }
          this.setData({
            verifiedPhoneToken: res.verify_token,
            verifiedSfzh: res.sfzh || '',
            verifiedStudentName: res.student_name || '',
            verifiedPhoneMasked: res.masked_phone || cached.masked_phone || '',
            cacheHit: true,
          });
          this.showSuccess('身份验证通过（来自缓存，7 天内免授权）');
        });
      })
      .catch((err) => {
        // 缓存未命中或异常 → 静默回退到正常授权流程
      });
  },

  // ============================================================
  // 微信手机号快捷登录验证
  // 说明：复用后端已有的 /vocational_tuition/verify_phone_for_payment，
  //       通过本人手机号反查报名记录（ZzBmxs），拿到身份证号 sfzh，
  //       再用 sfzh 去 /zzbm/query_student_class_info 查询班级信息。
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

    // 1) 调原 verify_phone_for_payment（业务 token）
    //    同步拿 wx.login 的 code，让后端内部换 openid 并写入 7 天缓存
    commonAuth.wxLogin()
      .then((loginCode) => post(
        '/vocational_tuition/verify_phone_for_payment',
        {
          code,
          role: 'self',
          openid_code: '',
          login_code: loginCode,
          subject: commonAuth.SUBJECT.STUDENT_INFO
        },
        { loadingTitle: '正在校验身份...' }
      ))
      .then((res) => {
        const token = (res && (res.verify_token || res.token)) || '';
        const sfzh = (res && res.sfzh) || '';
        const masked = (res && (res.masked_phone || res.phone)) || '';
        const studentName = (res && res.student_name) || '';
        if (!token || !sfzh) {
          this.showError('手机号校验失败，请确认是报名预留的手机号');
          return;
        }
        this.setData({
          verifiedPhoneToken: token,
          verifiedSfzh: sfzh,
          verifiedStudentName: studentName,
          verifiedPhoneMasked: masked,
          cacheHit: false,
        });
        this.showSuccess('身份验证通过');
        // 7 天缓存由后端在 verify_phone_for_payment 内部写入（res.cache_written）
      })
      .catch((err) => {
        this.showError(err.message || '身份校验失败');
      });
  },

  // ============================================================
  // 重选身份：清除 7 天缓存 + 清空本地状态
  // ============================================================
  clearVerifiedPhone() {
    this.setData({
      verifiedPhoneToken: '',
      verifiedSfzh: '',
      verifiedStudentName: '',
      verifiedPhoneMasked: '',
      cacheHit: false,
    });
    // 通知后端清缓存（不影响本地操作，但保证多子系统一致）
    commonAuth.clearCache().catch(() => {});
  },

  // ============================================================
  // 查询班级信息
  // 说明：后端 /zzbm/query_student_class_info 仅接收身份证号 sfzh，
  //       因此依赖已校验拿到的 sfzh 进行查询。
  // ============================================================
  async onCheckStudentInfo() {
    if (!this.data.verifiedSfzh) {
      this.showError('请先完成微信身份验证');
      return;
    }

    try {
      const result = await get(
        '/zzbm/query_student_class_info',
        { sfzh: this.data.verifiedSfzh },
        { loadingTitle: '正在查询班级信息...' }
      );

      const studentInfoRaw = result && (result.student_info || result);
      if (studentInfoRaw && studentInfoRaw.xm) {
        const studentInfo = {
          name: studentInfoRaw.xm,
          student_no: studentInfoRaw.xh,
          id_card: studentInfoRaw.sfzh,
          class_name: studentInfoRaw.bj_mc,
          teacher_name: studentInfoRaw.t_xm,
          teacher_phone: studentInfoRaw.t_dh,
          jss: studentInfoRaw.jss || '',  // 教室
          dorm_info: studentInfoRaw.dorm_info || null  // 寝室信息
        };

        this.setData({
          studentInfo,
          showResult: true,
          showEmpty: false,
        });
        this.showSuccess('查询成功');
      } else {
        this.setData({
          showResult: false,
          showEmpty: true,
          studentInfo: null,
        });
      }
    } catch (err) {
      console.warn('onCheckStudentInfo error', err);
      this.setData({
        showResult: false,
        showEmpty: true,
        studentInfo: null,
      });
      this.showError(err.message || '查询失败，请稍后重试');
    }
  },

  // ============================================================
  // 重新查询
  // ============================================================
  onReQuery() {
    this.setData({
      showResult: false,
      showEmpty: false,
      studentInfo: null,
    });
  },

  // ============================================================
  // 拨打班主任电话
  // ============================================================
  callTeacher() {
    const phone = this.data.studentInfo && this.data.studentInfo.teacher_phone;
    if (!phone) {
      this.showError('班主任电话号码不可用');
      return;
    }

    wx.showModal({
      title: '拨打电话',
      content: `确定要拨打班主任电话 ${phone} 吗？`,
      confirmText: '拨打',
      cancelText: '取消',
      success: (res) => {
        if (res.confirm) {
          wx.makePhoneCall({
            phoneNumber: phone,
            fail: () => this.showError('拨打电话失败'),
          });
        }
      },
    });
  },
}, {
  requireAuth: false,
});