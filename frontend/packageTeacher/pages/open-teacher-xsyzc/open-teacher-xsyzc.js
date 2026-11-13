const { createPage } = require('../../../utils/page-mixin');
const { tokenGet, tokenPost } = require('../../../utils/request');

const XJZT_MAP = {'1':'在籍','2':'未注册','3':'转出','4':'休学','5':'退学','6':'开除','7':'毕业','8':'异动中','9':'超期清退'};

createPage({
  data: {
    studentList: [],
    filteredList: [],
    loading: false,
    hasLoaded: false,
    noMore: false,
    selectedClassId: '',
    classOptions: [],
    // 及格次数多选，用 map 方便 WXML 判断选中状态
    selectedCounts: [],
    selectedCountsMap: {},  // { '0': true, '4': true } 供 WXML 判断
    countOptions: [
      { label: '不限', value: -1 },
      { label: '0次', value: 0 },
      { label: '1次', value: 1 },
      { label: '2次', value: 2 },
      { label: '3次', value: 3 },
      { label: '4次', value: 4 },
      { label: '5次及以上', value: 5 },
    ],
    // 学籍状态筛选，默认在籍
    xjztFilter: '1',
    xjztOptions: [],
    xjztMap: XJZT_MAP,
    searchKeyword: '',
    totalCount: 0,
    allCount: 0,
    stats: {},
    page: 1,
    pageSize: 50,
    selectedMap: {},
    selectedCount: 0,
    showSmsPopup: false,
    smsContent: '',
    smsSending: false,
    bannedWords: [],
    foundBannedWords: [],
    smsHasBanned: false,
    smsHighlightParts: [],
    bannedHandleList: [],
  },

  onLoad() {
    this.loadClassList();
  },

  async loadClassList() {
    try {
      const classList = await tokenGet('/open_teacher/classes') || [];
      const classOptions = [{ text: '全部班级', value: '' }, ...classList.map(c => ({ text: c.name, value: c.id }))];
      this.setData({ classOptions, selectedClassId: '' });
      // 默认不加载初始数据，等待用户筛选
    } catch (e) {
      this.setData({ loading: false });
      this.showError('获取班级列表失败');
    }
  },

  onClassChange(e) {
    this.setData({ selectedClassId: e.detail, page: 1 });
    this.loadStudents(true);
  },

  // 及格次数多选（-1=不限，选不限则清空其他）
  toggleCountFilter(e) {
    const val = Number(e.currentTarget.dataset.value);
    if (val === -1) {
      this.setData({ selectedCounts: [], selectedCountsMap: {}, page: 1 });
      this.loadStudents(true);
      return;
    }
    const selected = [...this.data.selectedCounts];
    const idx = selected.indexOf(val);
    if (idx >= 0) {
      selected.splice(idx, 1);
    } else {
      selected.push(val);
    }
    // 同步更新 map，key 用字符串
    const map = {};
    selected.forEach(v => { map[String(v)] = true; });
    this.setData({ selectedCounts: selected, selectedCountsMap: map, page: 1 });
    this.loadStudents(true);
  },

  onXjztFilterChange(e) {
    this.setData({ xjztFilter: e.detail, page: 1 });
    this.loadStudents(true);
  },

  async loadStudents(reset = false) {
    if (reset) {
      this.setData({ page: 1, studentList: [], filteredList: [], noMore: false, loading: true, selectedMap: {}, selectedCount: 0 });
    }
    try {
      const params = { page: this.data.page, page_size: this.data.pageSize };
      if (this.data.selectedClassId) params.bj_id = this.data.selectedClassId;
      if (this.data.selectedCounts.length > 0) params.pass_counts = this.data.selectedCounts.join(',');
      if (this.data.xjztFilter) params.xjzt_filter = this.data.xjztFilter;
      if (this.data.searchKeyword) params.keyword = this.data.searchKeyword;

      const data = await tokenGet('/open_teacher/xsyzc/list', params, { showLoading: false });
      const newStudents = data.students || [];
      const merged = reset ? newStudents : [...this.data.studentList, ...newStudents];
      const noMore = merged.length >= (data.total || 0);

      // 构建学籍状态筛选选项（从返回的 xjzt_stats 构建）
      const xjztStats = data.xjzt_stats || {};
      const xjztOptions = [{ text: '全部学籍', value: '' }];
      Object.keys(xjztStats).sort().forEach(key => {
        if (xjztStats[key] > 0) {
          xjztOptions.push({ text: `${XJZT_MAP[key] || key}(${xjztStats[key]})`, value: key });
        }
      });

      // 若当前筛选值不在选项里则回退到全部
      const currentXjzt = this.data.xjztFilter;
      const xjztValid = xjztOptions.some(o => o.value === currentXjzt);
      if (!xjztValid) {
        this.setData({ xjztFilter: '' });
      }

      this.setData({
        studentList: merged,
        filteredList: merged,
        totalCount: data.total || 0,
        allCount: data.all_count || 0,
        stats: data.stats || {},
        xjztOptions,
        loading: false,
        noMore,
        hasLoaded: true,
      });
    } catch (e) {
      this.setData({ loading: false });
      this.showError('获取列表失败');
    }
  },

  onReachBottom() {
    if (this.data.noMore || this.data.loading) return;
    this.setData({ page: this.data.page + 1 });
    this.loadStudents(false);
  },

  // 搜索输入（防抖 400ms，调用后端 keyword 参数）
  onSearchInput(e) {
    const val = e.detail.value;
    this.setData({ searchKeyword: val });
    if (this._searchTimer) clearTimeout(this._searchTimer);
    this._searchTimer = setTimeout(() => {
      this.loadStudents(true);
    }, 400);
  },

  clearSearch() {
    this.setData({ searchKeyword: '' });
    this.loadStudents(true);
  },

  toggleSelect(e) {
    const id = '' + e.currentTarget.dataset.id;
    const map = Object.assign({}, this.data.selectedMap);
    if (map[id]) { delete map[id]; } else { map[id] = true; }
    this.setData({ selectedMap: map, selectedCount: Object.keys(map).length });
  },

  selectAll() {
    const map = {};
    this.data.filteredList.forEach(s => { map['' + s.id] = true; });
    this.setData({ selectedMap: map, selectedCount: Object.keys(map).length });
  },

  deselectAll() {
    this.setData({ selectedMap: {}, selectedCount: 0 });
  },

  openSmsPopup() {
    if (this.data.selectedCount === 0) { this.showError('请先选择学生'); return; }
    this.setData({ showSmsPopup: true, smsContent: '', smsSending: false, smsHasBanned: false, smsHighlightParts: [], foundBannedWords: [], bannedHandleList: [] });
    this.loadBannedWords();
  },

  closeSmsPopup() { this.setData({ showSmsPopup: false }); },

  onSmsInput(e) { this.setData({ smsContent: e.detail.value }); },

  async loadBannedWords() {
    try {
      const list = await tokenGet('/open_teacher/banned_words', {}, { showLoading: false }) || [];
      this.setData({ bannedWords: list.map(w => w.word) });
    } catch (e) { this.setData({ bannedWords: [] }); }
  },

  checkBannedWords(content) {
    const found = [];
    this.data.bannedWords.forEach(w => { if (content.includes(w)) found.push(w); });
    return found;
  },

  buildHighlightParts(content, bannedWords) {
    if (!bannedWords.length) return [{ text: content, banned: false }];
    const escaped = [...bannedWords].sort((a, b) => b.length - a.length).map(w => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
    const regex = new RegExp('(' + escaped.join('|') + ')', 'g');
    const parts = [];
    let lastIdx = 0, match;
    while ((match = regex.exec(content)) !== null) {
      if (match.index > lastIdx) parts.push({ text: content.slice(lastIdx, match.index), banned: false });
      parts.push({ text: match[1], banned: true });
      lastIdx = regex.lastIndex;
    }
    if (lastIdx < content.length) parts.push({ text: content.slice(lastIdx), banned: false });
    return parts;
  },

  async sendSms() {
    const content = this.data.smsContent.trim();
    if (!content) { this.showError('请输入短信内容'); return; }
    const found = this.checkBannedWords(content);
    if (found.length > 0) {
      this.setData({ foundBannedWords: found, bannedHandleList: found.map(w => ({ word: w, action: 'delete', replacement: '' })), smsHasBanned: true, smsHighlightParts: this.buildHighlightParts(content, found) });
      return;
    }
    this._confirmAndSend(content);
  },

  _confirmAndSend(content) {
    wx.showModal({
      title: '确认发送',
      content: `确定向 ${this.data.selectedCount} 名学生发送此短信？`,
      confirmText: '确认发送',
      confirmColor: '#1890FF',
      success: (res) => { if (res.confirm) this._doSendSms(content); }
    });
  },

  onBannedActionChange(e) {
    const { idx } = e.currentTarget.dataset;
    const list = this.data.bannedHandleList.map((item, i) => i === idx ? { ...item, action: item.action === 'delete' ? 'replace' : 'delete' } : item);
    this.setData({ bannedHandleList: list });
  },

  onBannedReplacementInput(e) {
    const { idx } = e.currentTarget.dataset;
    const list = this.data.bannedHandleList.map((item, i) => i === idx ? { ...item, replacement: e.detail.value } : item);
    this.setData({ bannedHandleList: list });
  },

  applyBannedHandle() {
    let content = this.data.smsContent;
    this.data.bannedHandleList.forEach(item => {
      content = item.action === 'delete' ? content.split(item.word).join('') : (item.replacement ? content.split(item.word).join(item.replacement) : content);
    });
    this.setData({ smsContent: content });
    const found = this.checkBannedWords(content);
    if (found.length > 0) {
      this.setData({ foundBannedWords: found, bannedHandleList: found.map(w => ({ word: w, action: 'delete', replacement: '' })), smsHasBanned: true, smsHighlightParts: this.buildHighlightParts(content, found) });
      this.showError('仍有违禁词，请继续处理');
    } else {
      this.setData({ smsHasBanned: false, smsHighlightParts: [], foundBannedWords: [], bannedHandleList: [] });
      this.showSuccess('违禁词已处理完毕，可以发送');
    }
  },

  onBackToEdit() {
    this.setData({ smsHasBanned: false, smsHighlightParts: [], foundBannedWords: [], bannedHandleList: [] });
  },

  async _doSendSms(content) {
    this.setData({ smsSending: true });
    try {
      const res = await tokenPost('/open_teacher/send_sms', { student_ids: Object.keys(this.data.selectedMap), content });
      this.showSuccess((res && res.msg) ? res.msg : '发送完成');
      this.setData({ showSmsPopup: false, smsSending: false });
    } catch (e) {
      this.setData({ smsSending: false });
      this.showError(e.message || '发送失败');
    }
  },

  goBack() { wx.navigateBack(); }
}, {
  requireAuth: true,
  userType: 'open_teacher'
});
