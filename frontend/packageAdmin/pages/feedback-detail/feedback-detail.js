const { createPage } = require('../../../utils/page-mixin');
const { BASE_URL } = require('../../../utils/request');
// 反馈模块有自己的登录体系，必须用 feedback-request（读 feedback_auth_cache）
// 否则 tokenGet 会去找 app.globalData.userInfo，本模块登录后的用户没有 → "Token 不存在"
const { feedbackGet, feedbackPost } = require('../../../utils/feedback-request');
const Dialog = require('@vant/weapp/dialog/dialog').default;

// 反馈模块独立登录缓存 key（与 feedback-login 页面、feedback-request.js 保持一致）
const FEEDBACK_AUTH_CACHE_KEY = 'feedback_auth_cache';
const FEEDBACK_LOGIN_URL = '/packageAdmin/pages/feedback-login/feedback-login';

// 2026-09-27 重构：scene/scene_custom 已废弃，前端不再展示场景
const ITEM_MAP = {
  meal: '饭菜质量', water_power: '水电', desk: '桌椅板凳',
  banbantong: '班班通', training_eq: '实训设备', facility: '校园设施',
  service: '服务态度', safety: '安全卫生', custom: '自定义'
};

createPage({
  data: {
    baseUrl: BASE_URL,
    id: 0,
    ticket: null,
    timeline: [],
    isOwner: true,
    statusLabels: {
      pending: '待受理', processing: '处理中', done: '已办结',
      rejected: '已驳回', cancelled: '已撤回'
    },
    statusIcon: {
      pending: 'clock-o', processing: 'play-circle-o',
      done: 'checked', rejected: 'close', cancelled: 'revoke'
    },
    actionLabels: {
      submit: '提交反馈', process: '开始处理',
      done: '处理完成', reject: '已驳回',
      cancel: '用户撤回', comment: '补充'
    }
  },

  onLoad(options) {
    if (!this._ensureLoggedIn()) return;
    this.setData({ id: parseInt(options.id, 10) });
    this.load();
  },

  /**
   * 检查反馈模块独立登录态；未登录或缓存已过期则清除并跳转 feedback-login
   * （与 feedback-admin.js 保持一致）
   */
  _ensureLoggedIn() {
    const cached = wx.getStorageSync(FEEDBACK_AUTH_CACHE_KEY);
    if (cached && (cached.token || cached.refresh_token)) {
      if (cached.expireTime && cached.expireTime <= Date.now()) {
        wx.removeStorageSync(FEEDBACK_AUTH_CACHE_KEY);
        this._redirectToLogin();
        return false;
      }
      return true;
    }
    this._redirectToLogin();
    return false;
  },

  _redirectToLogin() {
    const redirect = encodeURIComponent(`/packageAdmin/pages/feedback-detail/feedback-detail?id=${this.data.id || ''}`);
    wx.redirectTo({ url: `${FEEDBACK_LOGIN_URL}?redirect=${redirect}` });
  },

  async load() {
    try {
      const res = await feedbackGet(`/feedback/detail/${this.data.id}`);
      const t = res.ticket;
      // 2026-09-27 重构：item_type/item_custom/scene/scene_custom 已废弃；
      // 后端接口不再返回 scene_label/item_label，前端改为读 repair_type_text
      t.item_label = t.repair_type_text || '';
      this.setData({ ticket: t, timeline: res.timeline });
    } catch (e) {
      this.showError(typeof e === 'string' ? e : '加载失败');
    }
  },

  previewImage(e) {
    const list = e.currentTarget.dataset.list === 'handle'
      ? this.data.ticket.handle_images
      : this.data.ticket.images;
    const i = e.currentTarget.dataset.index;
    const sources = list.map(it => ({
      url: this.data.baseUrl + it.url,
      type: it.type === 'video' ? 'video' : 'image'
    }));
    wx.previewMedia({ sources, current: i });
  },

  onCancel() {
    Dialog.confirm({
      title: '确认撤回',
      message: '撤回后将无法恢复,确定继续?'
    }).then(async () => {
      try {
        await feedbackPost(`/feedback/cancel/${this.data.id}`);
        this.showSuccess('已撤回');
        setTimeout(() => this.load(), 600);
      } catch (e) {
        this.showError(typeof e === 'string' ? e : '操作失败');
      }
    }).catch(() => {});
  }
});
