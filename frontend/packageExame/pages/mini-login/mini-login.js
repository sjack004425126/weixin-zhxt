/**
 * 小程序登录页（精简版 - 参考 vocational-login）
 * - 删除演示账号快填
 * - 删除装饰光斑/品牌长介绍
 * - 保留：学号密码登录、密码可见切换、协议、记住学号
 * - van-button 替代自绘按钮
 */
const { createPage } = require('../../../utils/page-mixin');
const { post } = require('../../../utils/request');
const { API_EXAME, TOKEN_KEY, USER_KEY, REMEMBER_KEY } = require('../../../utils/api-exame');

createPage({
  data: {
    xh: '',
    password: '',
    loading: false,
    showPwd: false,
    agreed: true,            // 默认勾选
    rememberPassword: false, // 记住学号
  },

  onLoad() {
    // 读取记住的学号 + 密码（30 天有效）
    const remembered = wx.getStorageSync(REMEMBER_KEY);
    if (remembered && remembered.xh) {
      const now = Date.now();
      const expiredAt = remembered.expiredAt || 0;
      if (expiredAt > now) {
        // 未过期：恢复学号 + 密码（密码默认隐藏）
        this.setData({
          xh: remembered.xh,
          password: remembered.password || '',
          rememberPassword: true,
          showPwd: false,
        });
      } else {
        // 已过期：清理
        wx.removeStorageSync(REMEMBER_KEY);
      }
    }
    // 已登录则跳过
    const cached = wx.getStorageSync(TOKEN_KEY);
    if (cached) {
      this._verifyToken(cached);
    }
  },

  async _verifyToken(token) {
    try {
      await post(API_EXAME.ME, {}, {
        header: { Authorization: 'Bearer ' + token },
        showLoading: false,
        timeout: 5000,
      });
      wx.reLaunch({ url: '/packageExame/pages/mini-list/mini-list' });
    } catch (err) {
      wx.removeStorageSync(TOKEN_KEY);
      wx.removeStorageSync(USER_KEY);
    }
  },

  // ---------- 输入 ----------
  onXhChange(e) {
    this.setData({ xh: e.detail.value });
  },

  onPasswordChange(e) {
    this.setData({ password: e.detail.value });
  },

  clearXh() {
    this.setData({ xh: '' });
  },

  togglePwd() {
    // 显式更新，确保小程序 input 组件重新渲染（避免 type 切换无响应）
    this.setData({
      showPwd: !this.data.showPwd,
    });
    console.log('[mini-login] togglePwd →', this.data.showPwd ? '显示密码' : '隐藏密码');
  },

  // ---------- 协议 ----------
  handleAgreeChange(e) {
    this.setData({ agreed: !!(e.detail.value && e.detail.value.length) });
  },

  // ---------- 记住学号 ----------
  handleRememberPasswordChange(e) {
    this.setData({ rememberPassword: !!(e.detail.value && e.detail.value.length) });
  },

  // ---------- 协议链接 ----------
  onAgreementTap(e) {
    const key = e.currentTarget.dataset.key;
    if (key === 'rule') {
      this.showWarn('考场纪律：全程监控，禁止分屏切屏');
    } else if (key === 'privacy') {
      this.showWarn('隐私政策：数据严格用于学业评估存档');
    }
  },



  // ---------- 登录 ----------
  async handleLogin() {
    const { xh, password, agreed, rememberPassword } = this.data;
    if (!xh || !xh.trim()) {
      this.showWarn('请输入学号');
      return;
    }
    if (!password) {
      this.showWarn('请输入密码');
      return;
    }
    if (!agreed) {
      this.showWarn('请先阅读并同意《考场规则与诚信承诺》及《隐私保护政策》');
      return;
    }
    if (this.data.loading) return;

    this.setData({ loading: true });
    try {
      const resp = await post(
        API_EXAME.LOGIN,
        { xh: xh.trim(), password },
        { loadingTitle: '身份校验中...' }
      );

      const data = resp && resp.data ? resp.data : resp;
      const token = data.token || data.access_token;
      const userInfo = data.user_info || {};

      if (!token) {
        throw new Error('登录失败：未拿到 token');
      }

      wx.setStorageSync(TOKEN_KEY, token);
      wx.setStorageSync(USER_KEY, userInfo);

      // 记住学号 + 密码（30天 = 一个月），过期自动失效
      const THIRTY_DAYS_MS = 30 * 24 * 60 * 60 * 1000;
      if (rememberPassword) {
        wx.setStorageSync(REMEMBER_KEY, {
          xh: xh.trim(),
          password: password, // ⚠️ 明文存本地缓存，用户主动选择，30 天后过期
          expiredAt: Date.now() + THIRTY_DAYS_MS,
          savedAt: Date.now(),
        });
      } else {
        wx.removeStorageSync(REMEMBER_KEY);
      }

      // 同步到 globalData
      const app = getApp();
      app.globalData.userInfo = { ...userInfo, token };

      this.showSuccess('身份验证成功');
      setTimeout(() => {
        wx.reLaunch({ url: '/packageExame/pages/mini-list/mini-list' });
      }, 600);
    } catch (err) {
      this.setData({ loading: false });
      this.showError(err.message || '登录失败');
    }
  },
});
