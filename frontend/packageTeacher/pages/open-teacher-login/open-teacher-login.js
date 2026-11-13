const { createPage } = require('../../../utils/page-mixin');
const { post } = require('../../../utils/request');
const commonAuth = require('../../../utils/common-auth');
const app = getApp();

const AUTH_CACHE_KEY = 'open_teacher_auth_cache';
const AUTH_CACHE_DURATION = 7 * 24 * 60 * 60 * 1000;

createPage({
  data: {
    // 登录方式：openid-微信一键登录（默认），quick-手机号快捷登录
    loginType: 'openid',
    isAgree: false
  },

  onLoad() {
    // 检查缓存登录
    const cached = wx.getStorageSync(AUTH_CACHE_KEY);
    if (cached && cached.expireTime > Date.now()) {
      app.globalData.userInfo = cached.userInfo;
      wx.redirectTo({
        url: '/packageTeacher/pages/open-teacher-my/open-teacher-my'
      });
    }
  },

  // 切换登录方式
  switchLoginType(e) {
    this.setData({ loginType: e.currentTarget.dataset.type });
  },

  // 微信一键登录（openid）
  // 前提：用户此前至少通过一次手机号快捷登录，后端已把 openid 绑定到该教师
  async handleOpenidLogin() {
    if (!this.data.isAgree) {
      this.showError('请先同意用户协议和隐私政策');
      return;
    }

    let code = '';
    try {
      code = await app.getOpenid_code();
    } catch (e) {
      this.showError('获取微信登录凭证失败，请重试');
      return;
    }
    if (!code) {
      this.showError('获取微信登录凭证失败，请重试');
      return;
    }

    try {
      const res = await post('/open_teacher/quick_login_openid', { code }, { loadingTitle: '登录中...' });

      if (res && res.authorized) {
        const userInfo = res.userInfo || {};
        userInfo.is_open_teacher = true;
        userInfo.user_type = 'open_teacher';
        userInfo.token = res.token;
        userInfo.refresh_token = res.refresh_token;

        app.globalData.userInfo = userInfo;
        // 教师 token 存 auth_cache，不写 userInfo
        wx.setStorageSync(AUTH_CACHE_KEY, {
          authorized: true,
          userInfo: userInfo,
          expireTime: Date.now() + AUTH_CACHE_DURATION
        });

        this.showSuccess('登录成功');
        setTimeout(() => {
          wx.redirectTo({
            url: '/packageTeacher/pages/open-teacher-my/open-teacher-my'
          });
        }, 1000);
      } else {
        this.showError((res && res.msg) || '当前微信还未绑定教师信息，请先使用「手机号快捷登录」完成一次登录');
      }
    } catch (error) {
      this.showError(error.message || '登录失败，请重试');
    }
  },

  async onGetPhoneNumber(e) {
    if (!this.data.isAgree) {
      this.showError('请先同意用户协议和隐私政策');
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

    try {
      // 同步传 login_code + subject，让后端写入 7 天手机号缓存并绑定 openid
      const loginCode = await commonAuth.wxLogin();
      const res = await post('/open_teacher/quick_login',
        { code, login_code: loginCode, subject: commonAuth.SUBJECT.USER_CENTER },
        { loadingTitle: '验证中...' }
      );

      if (res.authorized) {
        const userInfo = res.userInfo || {};
        userInfo.is_open_teacher = true;
        userInfo.user_type = 'open_teacher';
        userInfo.token = res.token;
        userInfo.refresh_token = res.refresh_token;

        app.globalData.userInfo = userInfo;
        // 教师 token 存 auth_cache，不写 userInfo
        wx.setStorageSync(AUTH_CACHE_KEY, {
          authorized: true,
          userInfo: userInfo,
          expireTime: Date.now() + AUTH_CACHE_DURATION
        });

        this.showSuccess('登录成功');
        setTimeout(() => {
          wx.redirectTo({
            url: '/packageTeacher/pages/open-teacher-my/open-teacher-my'
          });
        }, 1000);
      } else {
        this.showError(res.msg || '您没有访问权限');
      }
    } catch (error) {
      this.showError('登录失败，请重试');
    }
  },

  goToUserCenter() {
    wx.switchTab({
      url: '/pages/user-center/user-center'
    });
  },

  handleAgreeChange(e) {
    this.setData({
      isAgree: e.detail.value.length > 0
    });
  },

  navigateToUserAgreement() {
    wx.navigateTo({ url: '/pages/user-agreement/user-agreement' });
  },

  navigateToPrivacyPolicy() {
    wx.navigateTo({ url: '/pages/privacy-policy/privacy-policy' });
  }
});
