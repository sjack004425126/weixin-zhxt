const { createPage } = require('../../../utils/page-mixin');
const { tokenGet, tokenPost } = require('../../../utils/request');

createPage({
  data: {
    studentList: [], loading: false, loadingMore: false, noMore: false,
    hasLoaded: false, searchKeyword: '',
    selectedClassId: '', classOptions: [],
    statusFilter: '', statusOptions: [],
    totalCount: 0, stats: {},
    page: 1, pageSize: 80,
    selectedMap: {},
    selectedCount: 0,
    showSmsPopup: false, smsContent: '', smsSending: false,
    bannedWords: [], foundBannedWords: [], smsHasBanned: false, smsHighlightParts: [],
    bannedHandleList: []
  },

  onLoad() { this.loadClassList(); },

  async loadClassList() {
    try {
      const res = await tokenGet('/open_teacher/classes');
      const classList = res || [];
      const classOptions = [{ text: '全部', value: '' }, ...classList.map(c => ({ text: c.name, value: c.id }))];
      this.setData({ classOptions, selectedClassId: '' });
      // 默认不加载初始数据，等待用户筛选
    } catch (error) { this.setData({ loading: false }); this.showError('获取班级列表失败'); }
  },

  onSearchInput(e) {
    const val = e.detail.value;
    this.setData({ searchKeyword: val });
    if (this._searchTimer) clearTimeout(this._searchTimer);
    this._searchTimer = setTimeout(() => { this.loadStudents(true); }, 400);
  },

  clearSearch() {
    this.setData({ searchKeyword: '' });
    this.loadStudents(true);
  },

  onClassChange(e) {
    this.setData({ selectedClassId: e.detail });
    this.loadStudents(true, true);
  },
  onStatusFilterChange(e) { this.setData({ statusFilter: e.detail }); this.loadStudents(true); },

  async loadStudents(reset = false, fromClassChange = false) {
    if (reset) { this.setData({ page: 1, studentList: [], noMore: false, loading: true }); }
    else { this.setData({ loadingMore: true }); }
    try {
      const params = { page: this.data.page, page_size: this.data.pageSize };
      if (this.data.selectedClassId) params.bj_id = this.data.selectedClassId;
      if (this.data.statusFilter !== '') params.status_filter = parseInt(this.data.statusFilter);
      if (this.data.searchKeyword) params.keyword = this.data.searchKeyword;

      const res = await tokenGet('/open_teacher/refund/list', params, { showLoading: false });
      const data = res || {};
      const newStudents = data.students || [];
      const stats = data.stats || {};

      const statusOptions = [
        { text: '全部', value: '' },
        { text: `已完成 (${stats.s3 || 0})`, value: '3' },
        { text: `已申请 (${stats.s1 || 0})`, value: '1' },
        { text: `待确认 (${stats.s2 || 0})`, value: '2' },
        { text: `未申请 (${stats.s0 || 0})`, value: '0' },
        { text: `无记录 (${stats.no_record || 0})`, value: '-2' }
      ];

      let currentFilter = this.data.statusFilter;
      if (fromClassChange && currentFilter !== '') {
        const filterExists = statusOptions.some(opt => opt.value === currentFilter);
        if (!filterExists) { this.setData({ statusFilter: '', statusOptions }); this.loadStudents(true); return; }
      }

      const merged = reset ? newStudents : [...this.data.studentList, ...newStudents];
      const noMore = merged.length >= data.total;
      this.setData({
        studentList: merged, totalCount: data.total, stats,
        statusOptions, loading: false, loadingMore: false, noMore, hasLoaded: true,
        selectedMap: reset ? {} : this.data.selectedMap,
        selectedCount: reset ? 0 : this.data.selectedCount
      });
    } catch (error) { this.setData({ loading: false, loadingMore: false }); this.showError('获取列表失败'); }
  },

  onReachBottom() {
    if (this.data.loadingMore || this.data.noMore) return;
    this.setData({ page: this.data.page + 1 }); this.loadStudents(false);
  },

  toggleSelect(e) {
    const id = '' + e.currentTarget.dataset.id;
    const map = Object.assign({}, this.data.selectedMap);
    if (map[id]) { delete map[id]; } else { map[id] = true; }
    this.setData({ selectedMap: map, selectedCount: Object.keys(map).length });
  },

  selectAll() {
    const map = {};
    this.data.studentList.forEach(s => { map['' + s.id] = true; });
    this.setData({ selectedMap: map, selectedCount: Object.keys(map).length });
  },

  deselectAll() {
    this.setData({ selectedMap: {}, selectedCount: 0 });
  },

  openSmsPopup() {
    if (this.data.selectedCount === 0) {
      this.showError('请先选择学生');
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
      content: '确定向 ' + count + ' 名学生发送此短信？',
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
      const res = await tokenPost('/open_teacher/send_sms', { student_ids: Object.keys(this.data.selectedMap), content });
      this.showSuccess(res.msg || '发送完成');
      this.setData({ showSmsPopup: false, smsSending: false });
    } catch (error) { this.setData({ smsSending: false }); this.showError(error.message || '发送失败'); }
  },

  goBack() { wx.navigateBack(); }
}, {
  requireAuth: true,
  userType: 'open_teacher'
});
