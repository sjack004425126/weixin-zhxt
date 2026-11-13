// packageAdmin/pages/grad-emp-survey-detail/grad-emp-survey-detail.js
const { createPage } = require('../../../utils/page-mixin');
const { feedbackGet } = require('../../../utils/feedback-request');
const { resolveImageUrl } = require('../../../utils/image-url');

const FEEDBACK_AUTH_CACHE_KEY = 'feedback_auth_cache';

// 毕业去向字典（与后端 _DESTINATION_LABELS 对齐，避免再去拉一次 dict 接口）
const DESTINATION_LABELS = {
  '1': '已签订就业协议（合同）',
  '2': '应征义务兵',
  '3': '其他录用形式就业',
  '4': '创业',
  '5': '国内升学',
  '6': '出国（境）',
  '7': '专科升普通本科',
  '8': '专科升普通本科（师范）',
  '9': '待就业',
  '10': '暂不就业',
  '11': '灵活就业',
};

const EDUCATION_LEVEL_LABELS = {
  '1': '专科',
  '2': '本科',
  '3': '研究生',
  '4': '博士',
};

createPage({
  data: {
    recordId: null,
    detail: null,
    loading: false,
    error: '',

    // 派生展示字段
    destinationLabel: '',
    educationLevelLabel: '',
    isStudy: false,
    isEmployed: false,
    certificateUrl: '',
  },

  onLoad(options) {
    if (!this._ensureLoggedIn()) return;
    const id = options && options.id;
    if (!id) {
      this.setData({ error: '缺少记录 id' });
      return;
    }
    this.setData({ recordId: id, loading: true });
    this.loadDetail(id);
  },

  _ensureLoggedIn() {
    const cached = wx.getStorageSync(FEEDBACK_AUTH_CACHE_KEY);
    if (cached && (cached.token || cached.refresh_token)) {
      if (cached.expireTime && cached.expireTime <= Date.now()) {
        wx.removeStorageSync(FEEDBACK_AUTH_CACHE_KEY);
      } else {
        return true;
      }
    }
    wx.showToast({ title: '请先登录', icon: 'none' });
    setTimeout(() => {
      wx.redirectTo({ url: '/packageAdmin/pages/feedback-login/feedback-login' });
    }, 600);
    return false;
  },

  async loadDetail(id) {
    try {
      const detail = await feedbackGet(`/grad_emp_survey/admin/detail/${id}`);
      // feedbackGet 已经把 data.data 解出来了；后端 detail 返回的是 dict 对象
      const normalized = this._normalizeDetail(detail || {});
      this.setData({
        detail: normalized,
        ...this._deriveDisplay(normalized),
        loading: false,
      });
    } catch (err) {
      console.error('加载详情失败', err);
      this.setData({
        loading: false,
        error: typeof err === 'string' ? err : '加载详情失败',
      });
    }
  },

  _normalizeDetail(d) {
    // 后端 submit_time 是 ISO（带 T 和毫秒），展示只要 'YYYY-MM-DD HH:mm:ss'
    if (d && d.submit_time) {
      d.submit_time = String(d.submit_time).replace('T', ' ').substring(0, 19);
    }
    return d;
  },

  _deriveDisplay(d) {
    const dest = (d && d.destination) || '';
    const destLabel = dest
      ? (d.destination_label || DESTINATION_LABELS[dest] || dest)
      : '-';
    const eduLevelLabel = d.education_level
      ? EDUCATION_LEVEL_LABELS[d.education_level] || d.education_level
      : '-';

    return {
      destinationLabel: destLabel,
      educationLevelLabel: eduLevelLabel,
      isStudy: ['5', '6', '7', '8'].includes(dest),
      isEmployed: ['1', '3', '4'].includes(dest),
      // 后端已重签：/object/private/zs/<uuid>.<ext>?t=&s=
      // 拼上 BASE_URL，小程序 <image> 即可直接加载
      certificateUrl: d.certificate_url ? resolveImageUrl(d.certificate_url) : '',
    };
  },

  onPreviewCert(e) {
    const url = (e && e.currentTarget && e.currentTarget.dataset && e.currentTarget.dataset.url)
      || (e && e.target && e.target.dataset && e.target.dataset.url)
      || this.data.certificateUrl;
    if (!url) return;
    wx.previewImage({ urls: [url], current: url });
  },

  onCertImageError() {
    wx.showToast({ title: '凭证加载失败', icon: 'none' });
  },

  onCopyCode() {
    const code = this.data.detail && this.data.detail.query_code;
    if (!code) return;
    wx.setClipboardData({
      data: code,
      success: () => wx.showToast({ title: '已复制', icon: 'success' }),
    });
  },
});