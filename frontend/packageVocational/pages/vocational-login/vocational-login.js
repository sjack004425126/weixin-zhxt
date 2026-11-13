const { createPage } = require('../../../utils/page-mixin');
const { post, tokenPost } = require('../../../utils/request');
const { handleLoginSuccess } = require('../../../utils/auth-guard');
const commonAuth = require('../../../utils/common-auth');
const app = getApp();

// 独立存储 key（与其他端隔离）
const USER_INFO_KEY = 'vocational_student_userInfo';

createPage({
  data: {
    // 登录方式：password-账号密码登录，openid-微信 openid 快捷登录，quick-手机号快捷登录
    loginType: "openid",
    zz_username: "",
    zz_password: "",
    loading: false,
    isAgree: false,
    rememberPassword: false, // 记住密码选项
  },

  // 切换登录方式
  switchLoginType(e) {
    const type = e.currentTarget.dataset.type;
    this.setData({
      loginType: type,
    });
  },
  onLoad() {
    // 如果已登录，自动跳转到个人中心
    const cached = wx.getStorageSync(USER_INFO_KEY);
    if (cached && cached.user_type === 'vocational_student' && cached.token) {
      app.globalData.userInfo = cached;
      wx.reLaunch({ url: '/packageVocational/pages/vocational-my/vocational-my' });
      return;
    }

    // 尝试从本地存储加载保存的用户名和密码
    const savedUsername = wx.getStorageSync("zz_username_saved");
    const savedPassword = wx.getStorageSync("zz_password_saved");
    const savedTime = wx.getStorageSync("zz_password_saved_time");

    // 检查是否在1个月内（30天）
    const oneMonth = 30 * 24 * 60 * 60 * 1000;
    const now = new Date().getTime();

    if (savedUsername && savedPassword && savedTime && (now - savedTime < oneMonth)) {
      // 仅回填表单，不切换 tab，默认停留在 openid 登录
      this.setData({
        zz_username: savedUsername,
        zz_password: savedPassword,
        rememberPassword: true
      });
    } else {
      // 超过1个月，清除保存的密码
      wx.removeStorageSync("zz_username_saved");
      wx.removeStorageSync("zz_password_saved");
      wx.removeStorageSync("zz_password_saved_time");
    }
  },
  onShow() {

  },
  // 用户名输入
  onUsernameChange(e) {
    this.setData({
      zz_username: e.detail.value,
    });
  },

  // 密码输入
  onPasswordChange(e) {
    this.setData({
      zz_password: e.detail.value,
    });
  },

  // 显示用户协议
  showAgreement() {
    wx.navigateTo({
      url: "/pages/agreement/agreement",
    });
  },

  // 显示隐私政策
  showPrivacy() {
    wx.navigateTo({
      url: "/pages/privacy/privacy",
    });
  },

  // openid 快捷登录（微信一键登录）
  // 前提：用户此前至少通过一次手机号快捷登录，后端已把 openid 绑定到该学生
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
      const res = await post('/vocational_login/quickLogin', { code }, { loadingTitle: '登录中...' });
      const userInfo = res;
      userInfo.is_vocational = true; // 标记为职教学生
      userInfo.user_type = 'vocational_student'; // 统一用户类型标识
      wx.setStorageSync(USER_INFO_KEY, userInfo);
      app.globalData.userInfo = userInfo;

      this.showSuccess('登录成功');
      setTimeout(() => {
        handleLoginSuccess(); // 使用新的认证守卫自动返回原页面
      }, 1500);
    } catch (err) {
      this.showError(err.message || '登录失败');
    }
  },

  // 使用学号和密码登录
  async handlePasswordLogin() {
    if (!this.data.isAgree) {
      this.showError('请先同意用户协议和隐私政策');
      return;
    }

    if (!this.data.zz_username || !this.data.zz_password) {
      this.showError('请输入用户名和密码');
      return;
    }

    try{
      const resquest  = await post('/vocational_login/login_by_username_and_password', { username: this.data.zz_username, password: this.data.zz_password}, { loadingTitle: '登录中...' });
      const userInfo = resquest;
      userInfo.is_vocational = true; // 标记为职教学生
      userInfo.user_type = 'vocational_student'; // 统一用户类型标识
      wx.setStorageSync(USER_INFO_KEY, userInfo);

      // 如果勾选了记住密码，保存用户名和密码，并记录时间
      if (this.data.rememberPassword) {
        wx.setStorageSync("zz_username_saved", this.data.zz_username);
        wx.setStorageSync("zz_password_saved", this.data.zz_password);
        wx.setStorageSync("zz_password_saved_time", new Date().getTime());
      } else {
        // 如果没有勾选，清除保存的密码
        wx.removeStorageSync("zz_username_saved");
        wx.removeStorageSync("zz_password_saved");
        wx.removeStorageSync("zz_password_saved_time");
      }

      app.globalData.userInfo = userInfo;
      this.showSuccess('登录成功');
      // 延迟跳转，使用新的认证守卫处理页面恢复
      setTimeout(() => {
        handleLoginSuccess(); // 使用新的认证守卫自动返回原页面
      }, 1500);

      // 静默采集 openid
      this._collectOpenid();
    }catch(err){
      this.showError(err.message || '登录失败');
    }
  },

  // 手机号快捷登录
  getPhoneNumber(e) {
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

    // 调用后端接口，通过手机号登录
    // 同步传 login_code，让 phone_quick_login 写入 7 天手机号缓存（让其它子系统复用）
    commonAuth.wxLogin()
      .then((loginCode) => post(
        '/vocational_login/phone_quick_login',
        {
          code: code,
          login_code: loginCode,
          subject: commonAuth.SUBJECT.USER_CENTER
        },
        { loadingTitle: '登录中...' }
      ))
      .then((res) => {
        const userInfo = res;
        userInfo.is_vocational = true; // 标记为职教学生
        userInfo.user_type = 'vocational_student'; // 统一用户类型标识
        wx.setStorageSync(USER_INFO_KEY, userInfo);
        app.globalData.userInfo = userInfo;
        this.showSuccess('登录成功');

        setTimeout(() => {
          handleLoginSuccess();
        }, 1500);

        // 静默采集 openid（首次手机号登录后即可用 openid 登录）
        this._collectOpenid();
      })
      .catch((err) => {
        this.showError(err.message || '登录失败，该手机号未绑定学生信息');
      });
  },


  // 切换身份 - 返回用户中心
  goToUserCenter() {
    wx.switchTab({
      url: '/pages/user-center/user-center'
    });
  },
  // 处理协议同意状态变化
  handleAgreeChange(e) {
    this.setData({
      isAgree: e.detail.value.length > 0
    });
  },

  // 跳转到用户协议
  navigateToUserAgreement() {
    wx.navigateTo({
      url: '/pages/user-agreement/user-agreement'
    });
  },

  // 跳转到隐私政策
  navigateToPrivacyPolicy() {
    wx.navigateTo({
      url: '/pages/privacy-policy/privacy-policy'
    });
  },

  // 跳转到中职学生登录
  goToVocationalLogin() {
    wx.redirectTo({
      url: '/pages/login/login'
    });
  },

  // 静默采集 openid（失败不影响业务流程）
  async _collectOpenid() {
    try {
      const code = await app.getOpenid_code();
      if (!code) return;
      // ⭐ 必须用 tokenPost 带 token, /bind_openid/zz 后端需要鉴权
      await tokenPost('/bind_openid/zz', { code }, { showLoading: false, timeout: 8000 });
    } catch (e) {
      console.warn('[openid采集] 失败', e.message || e);
    }
  },
  setVocationalMyPage() {
    wx.setTabBarItem({
      index: 2,
      pagePath: '/pages/vocational-my/vocational-my',
      text: '个人中心'
    });
  },

  // 跳转到开大登录
  goToLogin() {
    wx.redirectTo({
      url: '/pages/login/login'
    });
  },

  // 处理记住密码选项变化
  handleRememberPasswordChange(e) {
    this.setData({
      rememberPassword: e.detail.value.length > 0
    });
  },
});
