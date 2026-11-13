const { createPage } = require('../../../utils/page-mixin');
const { BASE_URL } = require('../../../utils/request');
// 反馈模块有自己的登录体系，必须用 feedback-request（读 feedback_auth_cache）
// 否则 tokenGet 会去找 app.globalData.userInfo，本模块登录后的用户没有 → "Token 不存在"
const { feedbackGet, feedbackPost, feedbackUploadFile } = require('../../../utils/feedback-request');
const Dialog = require('@vant/weapp/dialog/dialog').default;

// 反馈模块独立登录缓存 key（与 feedback-login 页面、feedback-request.js、feedback-admin.js 保持一致）
const FEEDBACK_AUTH_CACHE_KEY = 'feedback_auth_cache';
const FEEDBACK_LOGIN_URL = '/packageAdmin/pages/feedback-login/feedback-login';

createPage({
  data: {
    baseUrl: BASE_URL,
    id: 0,
    ticket: null,
    timeline: [],
    submitting: false,
    statusLabels: {
      pending: '待受理', processing: '处理中', done: '已办结',
      rejected: '已驳回', cancelled: '已撤回'
    },
    actionLabels: {
      submit: '提交反馈', process: '开始处理', done: '处理完成',
      reject: '已驳回', cancel: '用户撤回', comment: '补充', delete: '管理员删除'
    },
    userTypeLabels: {
      open_student: '开放学生', vocational_student: '中职学生',
      open_teacher: '开放教师', vocational_teacher: '中职教师'
    },
    form: {
      remark: '',
      images: [],
      send_sms: true
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
    const redirect = encodeURIComponent(`/packageAdmin/pages/feedback-admin-detail/feedback-admin-detail?id=${this.data.id || ''}`);
    wx.redirectTo({ url: `${FEEDBACK_LOGIN_URL}?redirect=${redirect}` });
  },

  async load() {
    try {
      const res = await feedbackGet(`/feedback/detail/${this.data.id}`);
      this.setData({
        ticket: res.ticket,
        timeline: res.timeline,
        'form.remark': res.ticket.handle_remark || '',
        'form.images': res.ticket.handle_images || [],
      });
    } catch (e) {
      this.showError(typeof e === 'string' ? e : '加载失败');
    }
  },

  previewImage(e) {
    const list = e.currentTarget.dataset.list === 'handle' ? this.data.ticket.handle_images : this.data.ticket.images;
    const i = e.currentTarget.dataset.index;
    const sources = list.map(it => ({
      url: this.data.baseUrl + it.url,
      type: it.type === 'video' ? 'video' : 'image'
    }));
    wx.previewMedia({ sources, current: i });
  },

  onPreviewHandle(e) {
    const i = e.currentTarget.dataset.index;
    const sources = this.data.form.images.map(it => ({
      url: this.data.baseUrl + it.url,
      type: it.type === 'video' ? 'video' : 'image'
    }));
    wx.previewMedia({ sources, current: i });
  },

  callReporter() {
    if (this.data.ticket.reporter_phone) {
      wx.makePhoneCall({ phoneNumber: this.data.ticket.reporter_phone });
    }
  },

  onRemarkInput(e) {
    this.setData({ 'form.remark': e.detail.value });
  },

  onSmsChange(e) {
    this.setData({ 'form.send_sms': e.detail });
  },

  async onChooseImage() {
    const remain = 6 - this.data.form.images.length;
    if (remain <= 0) return;
    try {
      const res = await wx.chooseMedia({
        count: remain, mediaType: ['image', 'video'],
        sizeType: ['compressed'], sourceType: ['album', 'camera'],
        maxDuration: 60, camera: 'back'
      });
      const images = [...this.data.form.images];
      for (const f of res.tempFiles) {
        const isVideo = f.fileType === 'video';
        if (isVideo) {
          if (f.size && f.size > 30 * 1024 * 1024) {
            this.showError('视频不能超过30MB'); continue;
          }
          if (f.duration && f.duration > 60) {
            this.showError('视频时长不能超过60秒'); continue;
          }
        }
        try {
          const data = await feedbackUploadFile({
            url: '/feedback/upload', filePath: f.tempFilePath, name: 'file',
            loadingTitle: isVideo ? '视频上传中...' : '上传中...'
          });
          if (data && data.key) {
            const media = {
              key: data.key, url: data.url,
              type: data.type || (isVideo ? 'video' : 'image')
            };
            if (isVideo && f.thumbTempFilePath) {
              try {
                const poster = await feedbackUploadFile({
                  url: '/feedback/upload_poster',
                  filePath: f.thumbTempFilePath, name: 'file',
                  formData: { video_key: data.key },
                  showLoading: false
                });
                if (poster && poster.url) media.poster = poster.url;
              } catch (err) { /* 封面失败不阻塞 */ }
            }
            images.push(media);
          }
        } catch (err) {
          this.showError(err.message || (isVideo ? '视频上传失败' : '上传失败'));
        }
      }
      this.setData({ 'form.images': images });
    } catch (e) {}
  },

  async onRemoveImage(e) {
    const i = e.currentTarget.dataset.index;
    const item = this.data.form.images[i];
    if (!item) return;
    try {
      await feedbackPost('/feedback/delete_image', { key: item.key }, { showLoading: false });
    } catch (err) {}
    const arr = [...this.data.form.images];
    arr.splice(i, 1);
    this.setData({ 'form.images': arr });
  },

  async _submitHandle(status) {
    if (!this.data.form.remark.trim()) {
      this.showError('请填写处理意见');
      return;
    }
    this.setData({ submitting: true });
    try {
      const res = await feedbackPost('/feedback/admin/handle', {
        ticket_id: this.data.id,
        status,
        remark: this.data.form.remark,
        images: this.data.form.images.map(it => it.key || it),
        send_sms: this.data.form.send_sms
      }, { loadingTitle: status === 'done' ? '办结中...' : '提交中...' });
      const smsTip = (status === 'done' && this.data.form.send_sms && res && res.sms && res.sms.success)
        ? ' · 短信已提交' : '';
      this.showSuccess((status === 'done' ? '已办结' : '已标记处理中') + smsTip);
      setTimeout(() => this.load(), 600);
    } catch (e) {
      this.showError(typeof e === 'string' ? e : '操作失败');
    } finally {
      this.setData({ submitting: false });
    }
  },

  onProcess() { this._submitHandle('processing'); },
  onDone() {
    Dialog.confirm({
      title: '确认办结',
      message: this.data.form.send_sms && !this.data.ticket.is_anonymous
        ? '办结后将向反馈人发送短信通知,确认?'
        : '确认完成办结?'
    }).then(() => this._submitHandle('done')).catch(() => {});
  },

  onReject() {
    wx.showModal({
      title: '驳回反馈',
      editable: true,
      placeholderText: '请填写驳回原因(至少2字)',
      confirmText: '确认驳回',
      confirmColor: '#FF4D4F',
      success: (m) => {
        if (m.confirm) {
          const reason = (m.content || '').trim();
          if (reason.length < 2) {
            this.showError('请填写驳回原因');
            return;
          }
          this._doReject(reason);
        }
      }
    });
  },

  async _doReject(reason) {
    try {
      await feedbackPost('/feedback/admin/reject', {
        ticket_id: this.data.id, reason
      }, { loadingTitle: '提交中...' });
      this.showSuccess('已驳回');
      setTimeout(() => this.load(), 600);
    } catch (e) {
      this.showError(typeof e === 'string' ? e : '操作失败');
    }
  },

  onDelete() {
    wx.showModal({
      title: '删除此反馈',
      content: '删除后将从所有列表和统计中移除,数据库保留备查。确定继续?',
      confirmText: '确认删除',
      confirmColor: '#FF4D4F',
      editable: true,
      placeholderText: '可填删除原因(选填)',
      success: (m) => {
        if (m.confirm) this._doDelete((m.content || '').trim());
      }
    });
  },

  async _doDelete(reason) {
    try {
      await feedbackPost('/feedback/admin/delete', {
        ticket_id: this.data.id, reason
      }, { loadingTitle: '删除中...' });
      this.showSuccess('已删除');
      setTimeout(() => wx.navigateBack(), 600);
    } catch (e) {
      this.showError(typeof e === 'string' ? e : '删除失败');
    }
  }
});
