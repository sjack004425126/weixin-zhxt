const { createPage } = require('../../../utils/page-mixin');
const { tokenGet, tokenPost } = require('../../../utils/request');
const { resolveImageUrl } = require('../../../utils/image-url');

createPage({
  data: {
    studentList: [],
    loading: true,
    loadingMore: false,
    noMore: false,
    selectedClassId: '',
    classOptions: [],
    xjztFilter: '',
    xjztOptions: [],
    totalCount: 0,
    allCount: 0,
    page: 1,
    pageSize: 80,
    xjztMap: {'1': '在籍', '2': '未注册', '3': '转出', '4': '休学', '5': '退学', '6': '开除', '7': '毕业', '8': '异动中', '9': '超期清退'},
    searchKeyword: '',
    // 详情弹窗
    showDetail: false,
    detailStudent: null,
    detailLoading: false,
    // 卡片选择
    selectedMap: {},
    selectedCount: 0,
    // 短信弹窗
    showSmsPopup: false,
    smsContent: '',
    smsSending: false,
    // 违禁词
    bannedWords: [],
    foundBannedWords: [],
    smsHasBanned: false,
    smsHighlightParts: [],
    bannedHandleList: [],
    // 修改电话弹窗
    showPhonePopup: false,
    phoneEditId: null,
    phoneEditName: '',
    phoneEditOriginal: '',
    phoneEditValue: '',
    phoneSaving: false
  },

  onLoad(options) {
    if (options && options.bj_id) {
      this._initClassId = parseInt(options.bj_id);
    }
    this.loadClassList();
  },

  async loadClassList() {
    try {
      const res = await tokenGet('/open_teacher/classes');
      const classList = res || [];
      const classOptions = [
        { text: '全部', value: '' },
        ...classList.map(c => ({ text: c.name, value: c.id }))
      ];
      const initClassId = this._initClassId || '';
      this.setData({ classOptions, selectedClassId: initClassId ? String(initClassId) : '' });
      this._initClassId = null;
      this.loadStudents(true);
    } catch (error) {
      this.setData({ loading: false });
      this.showError('获取班级列表失败');
    }
  },

  onClassChange(e) {
    const newClassId = e.detail;
    this.setData({ selectedClassId: newClassId });
    this.loadStudents(true, true);
  },

  onXjztFilterChange(e) {
    this.setData({ xjztFilter: e.detail });
    this.loadStudents(true);
  },

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

  async loadStudents(reset = false, fromClassChange = false) {
    if (reset) {
      this.setData({ page: 1, studentList: [], noMore: false, loading: true });
    } else {
      this.setData({ loadingMore: true });
    }
    try {
      const params = { page: this.data.page, page_size: this.data.pageSize };
      if (this.data.selectedClassId) params.bj_id = this.data.selectedClassId;
      if (this.data.xjztFilter) params.xjzt_filter = this.data.xjztFilter;
      if (this.data.searchKeyword) params.keyword = this.data.searchKeyword;

      const res = await tokenGet('/open_teacher/students', params, { showLoading: false });
      const data = res || {};
      const newStudents = (data.students || []).map(s => ({
        ...s,
        photo_url: s.photo_url ? resolveImageUrl(s.photo_url) : ''
      }));
      const allCount = data.all_count || 0;
      const xjztStats = data.xjzt_stats || {};
      const xjztMap = this.data.xjztMap;

      // 构建学籍状态筛选选项
      const xjztOptions = [{ text: '全部', value: '' }];
      Object.keys(xjztStats).sort().forEach(key => {
        if (xjztStats[key] > 0) {
          const label = xjztMap[key] || key;
          xjztOptions.push({ text: `${label} (${xjztStats[key]})`, value: key });
        }
      });

      // 如果是班级切换，检查当前状态筛选是否仍然有效
      let currentFilter = this.data.xjztFilter;
      if (fromClassChange && currentFilter) {
        const filterExists = xjztOptions.some(opt => opt.value === currentFilter);
        if (!filterExists) {
          currentFilter = '';
          this.setData({ xjztFilter: '' });
          // 需要重新加载不带筛选的数据
          this.setData({ xjztOptions, loading: false });
          this.loadStudents(true);
          return;
        }
      }

      const merged = reset ? newStudents : [...this.data.studentList, ...newStudents];
      const noMore = merged.length >= data.total;

      this.setData({
        studentList: merged,
        totalCount: data.total,
        allCount,
        xjztOptions,
        loading: false,
        loadingMore: false,
        noMore,
        selectedMap: reset ? {} : this.data.selectedMap,
        selectedCount: reset ? 0 : this.data.selectedCount
      });
    } catch (error) {
      this.setData({ loading: false, loadingMore: false });
      this.showError('获取学生列表失败');
    }
  },

  onReachBottom() {
    if (this.data.loadingMore || this.data.noMore) return;
    this.setData({ page: this.data.page + 1 });
    this.loadStudents(false);
  },

  // 卡片选择切换
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

  callStudent(e) {
    const { phone, name } = e.currentTarget.dataset;
    if (!phone) { this.showError(`${name}暂无联系电话`); return; }
    wx.makePhoneCall({ phoneNumber: phone });
  },

  copyCredentials(e) {
    const { xh, sfzh, name } = e.currentTarget.dataset;
    if (!xh || !sfzh || sfzh.length < 14) {
      this.showError(`${name}信息不完整，无法生成账号密码`);
      return;
    }
    const birthday = sfzh.substring(6, 14);
    const text = '学号: ' + xh + '\n密码: Ouchn@' + birthday;
    wx.setClipboardData({ data: text, success: () => this.showSuccess('已复制账号密码') });
  },

  // 照片全屏预览
  previewPhoto(e) {
    const { url } = e.currentTarget.dataset;
    if (!url) return;
    wx.previewImage({ current: url, urls: [url] });
  },

  viewDetail(e) {
    const { id } = e.currentTarget.dataset;
    this.setData({ showDetail: true, detailLoading: true, detailStudent: null });
    this.loadStudentDetail(id);
  },

  async loadStudentDetail(studentId) {
    try {
      const res = await tokenGet('/open_teacher/student/detail', { student_id: studentId }, { showLoading: false });
      const detailStudent = res
        ? { ...res, photo_url: res.photo_url ? resolveImageUrl(res.photo_url) : '' }
        : null;
      this.setData({ detailStudent, detailLoading: false });
    } catch (error) {
      this.setData({ detailLoading: false });
      this.showError('获取学生详情失败');
    }
  },

  closeDetail() { this.setData({ showDetail: false, detailStudent: null }); },

  // ========== 短信功能 ==========
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

  // 构建高亮分段：将文本按违禁词拆分为 [{text, banned}] 数组
  buildHighlightParts(content, bannedWords) {
    if (!bannedWords.length) return [{ text: content, banned: false }];
    // 按长度降序排列，优先匹配长词
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
      const res = await tokenPost('/open_teacher/send_sms', {
        student_ids: Object.keys(this.data.selectedMap),
        content: content
      });
      this.showSuccess(res.msg || '发送完成');
      this.setData({ showSmsPopup: false, smsSending: false });
    } catch (error) {
      this.setData({ smsSending: false });
      this.showError(error.message || '发送失败');
    }
  },

  // ========== 修改学生电话 ==========
  editStudentPhone(e) {
    const { id, name, phone } = e.currentTarget.dataset;
    this.setData({
      showPhonePopup: true,
      phoneEditId: id,
      phoneEditName: name || '',
      phoneEditOriginal: phone || '',
      phoneEditValue: phone || '',
      phoneSaving: false
    });
  },

  closePhonePopup() {
    if (this.data.phoneSaving) return;
    this.setData({
      showPhonePopup: false,
      phoneEditId: null,
      phoneEditName: '',
      phoneEditOriginal: '',
      phoneEditValue: '',
      phoneSaving: false
    });
  },

  onPhoneInput(e) {
    // 只允许数字，最长 11 位
    const v = (e.detail.value || '').replace(/\D/g, '').slice(0, 11);
    this.setData({ phoneEditValue: v });
  },

  async saveStudentPhone() {
    const { phoneEditId, phoneEditValue, phoneEditOriginal, phoneSaving } = this.data;
    if (phoneSaving) return;
    if (!phoneEditId) { this.showError('学生信息缺失'); return; }
    if (!phoneEditValue || !/^1[3-9]\d{9}$/.test(phoneEditValue)) {
      this.showError('请输入正确的 11 位手机号');
      return;
    }
    if (phoneEditValue === phoneEditOriginal) {
      this.showError('手机号未变更');
      return;
    }
    this.setData({ phoneSaving: true });
    try {
      const res = await tokenPost('/open_teacher/student/update_phone', {
        student_id: phoneEditId,
        new_phone: phoneEditValue
      }, { showLoading: false });
      this.showSuccess(res.msg || '已保存');
      // 回写本地列表
      const list = this.data.studentList.map(s => s.id === phoneEditId ? { ...s, dh: phoneEditValue } : s);
      // 若详情弹窗打开的是该学生，也要同步
      const detail = this.data.detailStudent && this.data.detailStudent.id === phoneEditId
        ? { ...this.data.detailStudent, dh: phoneEditValue }
        : this.data.detailStudent;
      this.setData({
        studentList: list,
        detailStudent: detail,
        showPhonePopup: false,
        phoneSaving: false,
        phoneEditId: null,
        phoneEditName: '',
        phoneEditOriginal: '',
        phoneEditValue: ''
      });
    } catch (error) {
      this.setData({ phoneSaving: false });
      this.showError(error.message || '保存失败');
    }
  },

  goBack() { wx.navigateBack(); }
}, {
  requireAuth: true,
  userType: 'open_teacher'
});
