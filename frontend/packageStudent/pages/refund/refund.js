const { tokenGet, tokenPost } = require('../../../utils/request');
const { createPage } = require('../../../utils/page-mixin');
const app = getApp();
createPage({
  data: {
    phone: '',
    code: '',
    countdown: 0,
    canSendCode: false,
    canSubmit: false,
    amount: 0
  },

  onLoad(options) {
    if (options.amount) {
      this.setData({
        amount: options.amount
      });
    }
    this.setData({
      phone: app.globalData.userInfo.xs_dh
    });
    if(this.data.phone){
      this.setData({
        canSendCode: true
      });
    }
  },

  // 手机号输入
  onPhoneInput(e) {
    const phone = e.detail.value;
    this.setData({
      phone,
      canSendCode: this.isValidPhone(phone),
      canSubmit: this.isValidPhone(phone) && this.data.code.length === 6
    });
  },

  // 验证码输入
  onCodeInput(e) {
    const code = e.detail.value;
    this.setData({
      code,
      canSubmit: this.isValidPhone(this.data.phone) && code.length === 6
    });
  },

  // 验证手机号
  isValidPhone(phone) {
    return /^1[3-9]\d{9}$/.test(phone);
  },

  // 发送验证码
  async sendCode() {
    if (!this.isValidPhone(this.data.phone)) {
      this.showError('请输入正确的手机号');
      return;
    }

    try{
      await tokenGet('/login/xwyy_get_phone_code', {phone: this.data.phone});
      this.showSuccess('验证码已发送,请注意查收');
      this.startCountdown();
    }catch(err){
      this.showError(err.message || '发送失败');
    }
  },

  // 开始倒计时
  startCountdown() {
    this.setData({
      countdown: 60,
      canSendCode: false
    });

    const timer = setInterval(() => {
      if (this.data.countdown <= 1) {
        clearInterval(timer);
        this.setData({
          countdown: 0,
          canSendCode: this.isValidPhone(this.data.phone)
        });
      } else {
        this.setData({
          countdown: this.data.countdown - 1
        });
      }
    }, 1000);
  },

  // 提交退费申请
  async submitRefund() {
    if (!this.isValidPhone(this.data.phone)) {
      this.showError('请输入正确的手机号');
      return;
    }

    if (this.data.code.length !== 6) {
      this.showError('请输入6位验证码');
      return;
    }

    const openid_code = await app.getOpenid_code();

    try{
      await tokenPost('/student/wxxs_checkPhoneCode_BindOpenid_genOrder', {phone: this.data.phone,verify_code: this.data.code,openid_code: openid_code},{loadingTitle: '提交中...'});
      this.showSuccess('申请成功,请等待审核,审核通过后，请立即点击收款');
      // 延迟跳转到个人中心
      setTimeout(() => {
        wx.reLaunch({
          url: '/packageStudent/pages/tuition/tuition'
        });
      }, 3000);
    }catch(err){
      this.showError(err.message || '申请失败');
    }
  }
},{
  requireAuth: true // 🔑 方式1：通过选项指定需要登录
}); 