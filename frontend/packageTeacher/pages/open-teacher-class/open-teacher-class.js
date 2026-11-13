const { createPage } = require('../../../utils/page-mixin');
const { tokenGet, tokenPost } = require('../../../utils/request');

createPage({
  data: {
    classList: [],
    loading: true,
    selectedMap: {},
    selectedCount: 0,
    // 短信
    showSmsPopup: false,
    smsContent: '',
    smsSending: false,
    bannedWords: [],
    foundBannedWords: [],
    smsHasBanned: false,
    smsHighlightParts: [],
    bannedHandleList: []
  },

  onLoad() { this.loadClasses(); },

  async loadClasses() {
    this.setData({ loading: true });
    try {
      const res = await tokenGet('/open_teacher/class/list', {}, { showLoading: false });
      this.setData({ classList: res || [], loading: false, selectedMap: {}, selectedCount: 0 });
    } catch (error) {
      this.setData({ loading: false });
      this.showError('获取班级列表失败');
    }
  },

  toggleSelect(e) {
    const id = '' + e.currentTarget.dataset.id;
    const map = Object.assign({}, this.data.selectedMap);
    if (map[id]) { delete map[id]; } else { map[id] = true; }
    this.setData({ selectedMap: map, selectedCount: Object.keys(map).length });
  },

  selectAll() {
    const map = {};
    this.data.classList.forEach(c => { map['' + c.id] = true; });
    this.setData({ selectedMap: map, selectedCount: Object.keys(map).length });
  },

  deselectAll() {
    this.setData({ selectedMap: {}, selectedCount: 0 });
  },

  // ========== 短信功能 ==========
  openSmsPopup() {
    if (this.data.selectedCount === 0) {
      this.showError('请先选择班级');
      return;
    }
    this.setData({
      showSmsPopup: true, smsContent: '', smsSending: false,
      smsHasBanned: false, smsHighlightParts: [],
      foundBannedWords: [], bannedHandleList: []
    });
    this.loadBannedWords();
  },

  closeSmsPopup() { this.setData({ showSmsPopup: false }); },

  onSmsInput(e) { this.setData({ smsContent: e.detail.value }); },

  async loadBannedWords() {
    try {
      const res = await tokenGet('/open_teacher/banned_words', {}, { showLoading: false });
      this.setData({ bannedWords: (res || []).map(w => w.word) });
    } catch (e) {
      this.setData({ bannedWords: [] });
    }
  },

  checkBannedWords(content) {
    const words = this.data.bannedWords;
    const found = [];
    words.forEach(w => { if (content.includes(w)) found.push(w); });
    return found;
  },

  buildHighlightParts(content, bannedWords) {
    if (!bannedWords.length) return [{ text: content, banned: false }];
    const sorted = [...bannedWords].sort((a, b) => b.length - a.length);
    const escaped = sorted.map(w => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
    const regex = new RegExp('(' + escaped.join('|') + ')', 'g');
    const parts = [];
    let lastIdx = 0;
    let match;
    while ((match = regex.exec(content)) !== null) {
      if (match.index > lastIdx) {
        parts.push({ text: content.slice(lastIdx, match.index), banned: false });
      }
      parts.push({ text: match[1], banned: true });
      lastIdx = regex.lastIndex;
    }
    if (lastIdx < content.length) {
      parts.push({ text: content.slice(lastIdx), banned: false });
    }
    return parts;
  },

  async sendSms() {
    const content = this.data.smsContent.trim();
    if (!content) { this.showError('请输入短信内容'); return; }
    const found = this.checkBannedWords(content);
    if (found.length > 0) {
      const parts = this.buildHighlightParts(content, found);
      const handleList = found.map(w => ({ word: w, action: 'delete', replacement: '' }));
      this.setData({
        foundBannedWords: found, bannedHandleList: handleList,
        smsHasBanned: true, smsHighlightParts: parts
      });
      return;
    }
    this._confirmAndSend(content);
  },

  _confirmAndSend(content) {
    const count = this.data.selectedCount;
    wx.showModal({
      title: '确认发送',
      content: '确定向 ' + count + ' 个班级的学生发送此短信？',
      confirmText: '确认发送',
      confirmColor: '#E86433',
      success: (res) => {
        if (res.confirm) this._doSendSms(content);
      }
    });
  },

  onBannedActionChange(e) {
    const { idx } = e.currentTarget.dataset;
    const list = this.data.bannedHandleList.map((item, i) => {
      if (i === idx) return { ...item, action: item.action === 'delete' ? 'replace' : 'delete' };
      return item;
    });
    this.setData({ bannedHandleList: list });
  },

  onBannedReplacementInput(e) {
    const { idx } = e.currentTarget.dataset;
    const list = this.data.bannedHandleList.map((item, i) => {
      if (i === idx) return { ...item, replacement: e.detail.value };
      return item;
    });
    this.setData({ bannedHandleList: list });
  },

  applyBannedHandle() {
    let content = this.data.smsContent;
    this.data.bannedHandleList.forEach(item => {
      if (item.action === 'delete') {
        content = content.split(item.word).join('');
      } else if (item.action === 'replace' && item.replacement) {
        content = content.split(item.word).join(item.replacement);
      }
    });
    this.setData({ smsContent: content });
    const found = this.checkBannedWords(content);
    if (found.length > 0) {
      const parts = this.buildHighlightParts(content, found);
      const handleList = found.map(w => ({ word: w, action: 'delete', replacement: '' }));
      this.setData({
        foundBannedWords: found, bannedHandleList: handleList,
        smsHasBanned: true, smsHighlightParts: parts
      });
      this.showError('仍有违禁词，请继续处理');
    } else {
      this.setData({
        smsHasBanned: false, smsHighlightParts: [],
        foundBannedWords: [], bannedHandleList: []
      });
      this.showSuccess('违禁词已处理完毕，可以发送');
    }
  },

  onBackToEdit() {
    this.setData({
      smsHasBanned: false, smsHighlightParts: [],
      foundBannedWords: [], bannedHandleList: []
    });
  },

  async _doSendSms(content) {
    this.setData({ smsSending: true });
    try {
      const res = await tokenPost('/open_teacher/class/send_sms', {
        class_ids: Object.keys(this.data.selectedMap),
        content
      });
      this.showSuccess(res.msg || '发送完成');
      this.setData({ showSmsPopup: false, smsSending: false });
    } catch (error) {
      this.setData({ smsSending: false });
      this.showError(error.message || '发送失败');
    }
  },

  getSelectedStudentCount() {
    let count = 0;
    const map = this.data.selectedMap;
    this.data.classList.forEach(c => {
      if (map['' + c.id]) count += c.total;
    });
    return count;
  },

  goToStudents(e) {
    const { id, name } = e.currentTarget.dataset;
    wx.navigateTo({
      url: `/packageTeacher/pages/open-teacher-student/open-teacher-student?bj_id=${id}&bj_name=${encodeURIComponent(name)}`
    });
  },

  goBack() { wx.navigateBack(); }
}, {
  requireAuth: true,
  userType: 'open_teacher'
});
