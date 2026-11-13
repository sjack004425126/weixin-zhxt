const { createPage } = require('../../../utils/page-mixin');
const { post } = require('../../../utils/request');
const commonAuth = require('../../../utils/common-auth');
const app = getApp();

// 反馈模块独立的登录缓存键，与其他登录态隔离
const FEEDBACK_AUTH_CACHE_KEY = 'feedback_auth_cache';
const AUTH_CACHE_DURATION = 7 * 24 * 60 * 60 * 1000; // 7 天

// 身份展示
const USER_TYPE_LABELS = {
  staff: { label: '工作人员', icon: 'manager-o' },
  open_teacher: { label: '开放教师', icon: 'manager-o' },
  vocational_teacher: { label: '中职教师', icon: 'manager-o' },
  open_student: { label: '开放学生', icon: 'friends-o' },
  vocational_student: { label: '中职学生', icon: 'friends-o' }
};

createPage({
  data: {
    isAgree: false,
    submitting: false,
    redirectUrl: '/packageAdmin/pages/feedback-submit/feedback-submit'
  },

  onLoad(options) {
    // 支持登录后跳转回原始页面
    if (options && options.redirect) {
      try {
        this.setData({ redirectUrl: decodeURIComponent(options.redirect) });
      } catch (e) {
        console.warn('[feedback-login.onLoad] decode redirect fail', e);
      }
    }

    // 复用缓存（未过期则直接进入）—— 用 setTimeout 推迟到下一帧，避免 onLoad 中 redirect 与页面渲染竞争导致白屏
    const cached = wx.getStorageSync(FEEDBACK_AUTH_CACHE_KEY);
    if (cached && cached.expireTime > Date.now() && cached.token) {
      this._applyToGlobal(cached);
      setTimeout(() => {
        wx.redirectTo({ url: this.data.redirectUrl });
      }, 50);
    }
  },

  handleAgreeChange(e) {
    this.setData({ isAgree: e.detail.value.length > 0 });
  },

  async onGetPhoneNumber(e) {
    if (!this.data.isAgree) {
      this.showError('请先同意用户协议和隐私政策');
      return;
    }
    if (e.detail.errMsg !== 'getPhoneNumber:ok') {
      this.showError('已取消授权');
      return;
    }
    const code = e.detail.code;
    if (!code) {
      this.showError('获取手机号失败，请重试');
      return;
    }

    this.setData({ submitting: true });
    try {
      // 同步拿 wx.login 的 code，让后端 phone-login 内部写入 7 天手机号缓存
      const loginCode = await commonAuth.wxLogin();
      const data = await post('/feedback/auth/phone-login',
        { code, login_code: loginCode, subject: commonAuth.SUBJECT.FEEDBACK },
        { loadingTitle: '验证中...' }
      );

      if (!data || !data.authorized) {
        this.showError(data && data.msg ? data.msg : '该手机号未在系统注册，请联系管理员');
        return;
      }

      // 缓存登录态（含 refresh_token）
      const identity = data.identity || {};
      const cached = {
        token: data.token,
        refresh_token: data.refresh_token || '',
        identity,
        is_admin: !!data.is_admin,
        admin_role: data.admin_role || '',
        admin_role_label: data.admin_role_label || '',
        admin_scope: data.admin_scope || '',
        admin_department: data.admin_department || '',
        expireTime: Date.now() + AUTH_CACHE_DURATION
      };
      wx.setStorageSync(FEEDBACK_AUTH_CACHE_KEY, cached);
      this._applyToGlobal(cached);

      // 7 天手机号缓存由后端 phone-login 内部写入（res.cache_written）
      // 这里不再需要前端 writeCache（避免 wx.getPhoneNumber 的 code 二次使用）

      this.showSuccess('登录成功');
      setTimeout(() => {
        wx.redirectTo({ url: this.data.redirectUrl });
      }, 600);
    } catch (err) {
      this.showError(typeof err === 'string' ? err : '登录失败，请重试');
    } finally {
      this.setData({ submitting: false });
    }
  },

  /**
   * 把反馈登录态同步到全局，复用项目通用的 userInfo 协议：
   * - token 注入 app.globalData 与 storage('token')
   * - userInfo 字段映射，让 feedback-submit 等页面无缝识别身份
   */
  _applyToGlobal(cached) {
    const identity = cached.identity || {};
    const labelMap = USER_TYPE_LABELS[identity.user_type] || { label: '用户', icon: 'user-o' };
    const userInfo = {
      token: cached.token,
      user_type: identity.user_type,
      name: identity.name,
      phone: identity.phone,
      department: identity.department,
      // 兼容旧字段
      t_xm: identity.name,
      xs_xm: identity.name,
      is_open_teacher: identity.user_type === 'open_teacher',
      is_admin: cached.is_admin,
      admin_role: cached.admin_role,
      admin_role_label: cached.admin_role_label,
      userTypeLabel: labelMap.label,
      userTypeIcon: labelMap.icon
    };
    app.globalData.userInfo = userInfo;
    app.globalData.token = cached.token;
    wx.setStorageSync('token', cached.token);
    wx.setStorageSync('userInfo', userInfo);
  },

  navigateToUserAgreement() {
    wx.navigateTo({ url: '/pages/user-agreement/user-agreement' });
  },

  navigateToPrivacyPolicy() {
    wx.navigateTo({ url: '/pages/privacy-policy/privacy-policy' });
  }
});
