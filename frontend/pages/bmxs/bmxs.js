const { createPage } = require('../../utils/page-mixin');
const { tokenGet, tokenPost } = require('../../utils/request');

const ERROR_MESSAGES = {
  LOAD: '获取报名信息失败',
  SUBMIT: '提交失败',
};

// 自助报名相关 endpoint（临时直接用路径，后续可提取到 utils/api.js）
const ENDPOINT = {
  INFO: 'http://localhost:443/zzbm/get_new_zzbm_info',
  SUBMIT: '/api/bmxs/submit',
};

createPage({
  data: {
    bmxs: {
      bdzy: null,
      byxxmc: "",
      byxxssx1: "",
      byxxssx2: "",
      byxxssx3: "",
      hkxz: "",
      id: null,
      jtxxdz: "",
      jzdh: "",
      jzdlx: null,
      jzgx: null,
      jzxm: "",
      mz: "",
      pc: null,
      qd: null,
      qdjs: "",
      sfjdlk: 0,
      sflset: 0,
      sftwjrzn: 0,
      sfzh: "",
      tjsj: null,
      xb: "",
      xm: "",
      xsdh: "",
      xsly: "",
      zsdx: null,
      zzmm: null
    },
    options: {},
    showGender: false,
    showZzmm: false,
    showJzgx: false,
    showJzdlx: false,
    showZsdx: false,
    showQd: false
  },

  onLoad() {
    this.getBmxsInfo()
  },

  // 获取报名信息
  async getBmxsInfo() {
    try {
      // request.js 自动解 success/code，业务数据在 res.data
      const data = await tokenGet(ENDPOINT.INFO);
      this.setData({
        bmxs: data.bmxs || {},
        options: data.options || {},
      });
    } catch (err) {
      if (err.isAuthError) return;
      console.error('获取报名信息失败：', err);
      this.showError(err.message || ERROR_MESSAGES.LOAD);
    }
  },

  // 表单项变化
  onFieldChange(e) {
    const { name } = e.currentTarget.dataset
    const { value } = e.detail
    this.setData({
      [`bmxs.${name}`]: value
    })
  },

  // 显示性别选择器
  showGenderPicker() {
    this.setData({ showGender: true })
  },

  // 关闭性别选择器
  onGenderClose() {
    this.setData({ showGender: false })
  },

  // 确认性别选择
  onGenderConfirm(e) {
    this.setData({
      'bmxs.xb': e.detail.value,
      showGender: false
    })
  },

  // 显示政治面貌选择器
  showZzmmPicker() {
    this.setData({ showZzmm: true })
  },

  // 关闭政治面貌选择器
  onZzmmClose() {
    this.setData({ showZzmm: false })
  },

  // 确认政治面貌选择
  onZzmmConfirm(e) {
    this.setData({
      'bmxs.zzmm': e.detail.value.id,
      showZzmm: false
    })
  },

  // 显示与家长关系选择器
  showJzgxPicker() {
    this.setData({ showJzgx: true })
  },

  // 关闭与家长关系选择器
  onJzgxClose() {
    this.setData({ showJzgx: false })
  },

  // 确认与家长关系选择
  onJzgxConfirm(e) {
    this.setData({
      'bmxs.jzgx': e.detail.value.id,
      showJzgx: false
    })
  },

  // 显示家庭地址类型选择器
  showJzdlxPicker() {
    this.setData({ showJzdlx: true })
  },

  // 关闭家庭地址类型选择器
  onJzdlxClose() {
    this.setData({ showJzdlx: false })
  },

  // 确认家庭地址类型选择
  onJzdlxConfirm(e) {
    this.setData({
      'bmxs.jzdlx': e.detail.value.id,
      showJzdlx: false
    })
  },

  // 显示招生对象选择器
  showZsdxPicker() {
    this.setData({ showZsdx: true })
  },

  // 关闭招生对象选择器
  onZsdxClose() {
    this.setData({ showZsdx: false })
  },

  // 确认招生对象选择
  onZsdxConfirm(e) {
    this.setData({
      'bmxs.zsdx': e.detail.value.id,
      showZsdx: false
    })
  },

  // 显示渠道选择器
  showQdPicker() {
    this.setData({ showQd: true })
  },

  // 关闭渠道选择器
  onQdClose() {
    this.setData({ showQd: false })
  },

  // 确认渠道选择
  onQdConfirm(e) {
    this.setData({
      'bmxs.qd': e.detail.value.id,
      showQd: false
    })
  },

  // 提交表单
  async onSubmit() {
    try {
      await tokenPost(ENDPOINT.SUBMIT, this.data.bmxs);
      this.showSuccess('提交成功');
      setTimeout(() => wx.navigateBack(), 1500);
    } catch (err) {
      if (err.isAuthError) return;
      console.error('提交失败：', err);
      this.showError(err.message || ERROR_MESSAGES.SUBMIT);
    }
  }
});