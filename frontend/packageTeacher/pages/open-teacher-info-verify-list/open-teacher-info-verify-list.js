const { createPage } = require('../../../utils/page-mixin');
const { tokenGet, tokenPost } = require('../../../utils/request');
const { getRequestBaseUrl } = require('../../../utils/auth-guard');

const STATUS_LABELS = {
  '': '全部',
  pending: '待核对',
  verified: '已核对无误',
  modified: '已修改'
};

createPage({
  data: {
    studentList: [], loading: false, loadingMore: false, noMore: false,
    hasLoaded: false, searchKeyword: '',
    selectedClassId: '', classOptions: [],
    statusFilter: '', statusOptions: [],
    allCount: 0, pendingCount: 0, verifiedCount: 0, modifiedCount: 0,
    page: 1, pageSize: 80,
    exporting: false
  },

  onLoad() {
    this.loadClassList();
  },

  onShow() {
    // 班主任从详情页回来需要刷新
    if (this.data.hasLoaded) this.loadStudents(true);
  },

  async loadClassList() {
    try {
      const res = await tokenGet('/open_teacher/classes', {}, { showLoading: false });
      const classList = (Array.isArray(res) ? res : (res && res.data)) || [];
      const classOptions = [{ text: '全部班级', value: '' }, ...classList.map(c => ({ text: c.name, value: c.id }))];
      this.setData({ classOptions, selectedClassId: '' });
      this.loadStudents(true);
    } catch (error) {
      this.setData({ loading: false });
      this.showError('获取班级列表失败');
    }
  },

  onSearchInput(e) {
    const val = e.detail.value;
    this.setData({ searchKeyword: val });
    if (this._searchTimer) clearTimeout(this._searchTimer);
    this._searchTimer = setTimeout(() => this.loadStudents(true), 400);
  },

  clearSearch() {
    this.setData({ searchKeyword: '' });
    this.loadStudents(true);
  },

  onClassChange(e) {
    this.setData({ selectedClassId: e.detail });
    this.loadStudents(true, true);
  },

  onStatusFilterChange(e) {
    this.setData({ statusFilter: e.detail });
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
      if (this.data.statusFilter) params.status_filter = this.data.statusFilter;
      if (this.data.searchKeyword) params.keyword = this.data.searchKeyword;

      const res = await tokenGet('/open_teacher/info_verify/list', params, { showLoading: false });
      const data = res || {};
      const newStudents = data.students || [];

      // 状态筛选下拉项（带计数）
      const statusOptions = [
        { text: '全部', value: '' },
        { text: `待核对 (${data.pending_count || 0})`, value: 'pending' },
        { text: `已核对无误 (${data.verified_count || 0})`, value: 'verified' },
        { text: `有修改 (${data.modified_count || 0})`, value: 'modified' }
      ];

      let currentFilter = this.data.statusFilter;
      if (fromClassChange && currentFilter) {
        const filterExists = statusOptions.some(opt => opt.value === currentFilter);
        if (!filterExists) {
          this.setData({ statusFilter: '', statusOptions });
          this.loadStudents(true);
          return;
        }
      }

      const merged = reset ? newStudents : [...this.data.studentList, ...newStudents];
      const noMore = merged.length >= (data.total || 0);

      this.setData({
        studentList: merged,
        totalCount: data.total,
        allCount: data.all_count || 0,
        pendingCount: data.pending_count || 0,
        verifiedCount: data.verified_count || 0,
        modifiedCount: data.modified_count || 0,
        statusOptions,
        loading: false,
        loadingMore: false,
        noMore,
        hasLoaded: true
      });
    } catch (error) {
      this.setData({ loading: false, loadingMore: false });
      this.showError('获取列表失败');
    }
  },

  onReachBottom() {
    if (this.data.loadingMore || this.data.noMore) return;
    this.setData({ page: this.data.page + 1 });
    this.loadStudents(false);
  },

  onCardTap(e) {
    const id = e.currentTarget.dataset.id;
    if (!id) return;
    wx.navigateTo({
      url: `/packageTeacher/pages/open-teacher-info-verify-detail/open-teacher-info-verify-detail?xs_id=${id}`
    });
  },

  async onExport() {
    if (this.data.exporting) return;

    wx.showModal({
      title: '导出修改记录',
      content: '将导出有修改记录的学生为 CSV 文件，可保存到本地。是否继续？',
      confirmText: '开始导出',
      success: async (r) => {
        if (!r.confirm) return;
        await this._doExport();
      }
    });
  },

  async _doExport() {
    this.setData({ exporting: true });
    try {
      const params = {};
      if (this.data.selectedClassId) params.bj_id = this.data.selectedClassId;

      // 后端 csv 走流式响应，tokenGet 拿不到原始 blob；改用 wx.request 自行处理
      const app = getApp();
      const token = (app.globalData.userInfo && app.globalData.userInfo.token) || '';
      const baseUrl = getRequestBaseUrl();
      const qs = Object.keys(params).map(k => `${encodeURIComponent(k)}=${encodeURIComponent(params[k])}`).join('&');
      const url = `${baseUrl}/open_teacher/info_verify/export${qs ? '?' + qs : ''}`;

      // 1) 先请求拿到二进制数据
      const fileRes = await new Promise((resolve, reject) => {
        wx.request({
          url,
          method: 'GET',
          header: { Authorization: 'Bearer ' + token, 'Accept': 'text/csv' },
          responseType: 'arraybuffer',
          success: (res) => {
            if (res.statusCode === 401) return reject(new Error('登录已过期，请重新登录'));
            if (res.statusCode < 200 || res.statusCode >= 300) {
              return reject(new Error(`下载失败，状态码 ${res.statusCode}`));
            }
            resolve(res);
          },
          fail: (err) => reject(new Error(err.errMsg || '网络异常'))
        });
      });

      const exportedCount = parseInt(fileRes.header['X-Exported-Count'] || '0', 10) || 0;

      if (!fileRes.data || exportedCount === 0) {
        wx.showToast({ title: '没有可导出的修改记录', icon: 'none', duration: 1800 });
        this.setData({ exporting: false });
        return;
      }

      // 2) 从响应头解析文件名（含 .csv 后缀）
      const fallbackName = `info_verify_export_${Date.now()}.csv`;
      let fileName = fallbackName;
      const disposition = fileRes.header['Content-Disposition'] || fileRes.header['content-disposition'] || '';
      const fnMatch = disposition.match(/filename\*?=(?:UTF-8'')?["']?([^"';]+)["']?/i);
      if (fnMatch && fnMatch[1]) {
        try { fileName = decodeURIComponent(fnMatch[1]); } catch (e) { fileName = fnMatch[1]; }
      }
      // 保证有 .csv 后缀
      if (!/\.csv$/i.test(fileName)) fileName += '.csv';

      // 优先写到带扩展名的临时路径；并同时得到一个 tmp 路径，兼容部分客户端识别后缀
      const fileManager = wx.getFileSystemManager();
      const userFilePath = `${wx.env.USER_DATA_PATH}/${fileName}`;
      const tmpFilePath = `${wx.env.USER_DATA_PATH}/tmp_${Date.now()}.csv`;

      await new Promise((resolve, reject) => {
        fileManager.writeFile({
          filePath: userFilePath,
          data: fileRes.data,
          encoding: 'binary',
          success: resolve,
          fail: (err) => reject(new Error('写入本地文件失败'))
        });
      });

      // 复制一份到 tmp（部分客户端需要"无空格无中文路径"以正确识别文件类型）
      let sharePath = userFilePath;
      try {
        await new Promise((resolve, reject) => {
          fileManager.copyFile({
            srcPath: userFilePath,
            destPath: tmpFilePath,
            success: resolve,
            fail: () => resolve()
          });
        });
        const stat = fileManager.statSync(tmpFilePath, false);
        if (stat && stat.size > 0) sharePath = tmpFilePath;
      } catch (e) {
        sharePath = userFilePath;
      }

      // 3) 弹窗询问保存方式
      this._showSaveOptions(userFilePath, sharePath, exportedCount, fileName);
    } catch (error) {
      this.showError(error.message || '导出失败');
    } finally {
      this.setData({ exporting: false });
    }
  },

  _showSaveOptions(filePath, sharePath, count, fileName) {
    wx.showActionSheet({
      itemList: ['分享给微信好友', '保存到我的电脑/手机', '复制文件路径', '打开文件预览'],
      success: (res) => {
        if (res.tapIndex === 0) {
          this._shareToWechat(sharePath, fileName, count);
        } else if (res.tapIndex === 1) {
          this._saveFile(filePath, fileName, count);
        } else if (res.tapIndex === 2) {
          wx.setClipboardData({
            data: filePath,
            success: () => wx.showToast({ title: '路径已复制', icon: 'success', duration: 1200 })
          });
        } else if (res.tapIndex === 3) {
          this._openDoc(filePath, fileName, count);
        }
      },
      fail: () => {}
    });
  },

  _openDoc(filePath, fileName, count) {
    // 复制到更干净的临时路径（部分旧客户端对 USER_DATA_PATH 后缀识别不稳）
    const fileManager = wx.getFileSystemManager();
    const tmpPath = `${wx.env.USER_DATA_PATH}/preview_${Date.now()}.csv`;
    try {
      fileManager.copyFileSync(filePath, tmpPath);
      const realPath = fileManager.existsSync(tmpPath, false) ? tmpPath : filePath;
      wx.openDocument({
        filePath: realPath,
        showMenu: true,
        success: () => wx.showToast({ title: '已打开文件', icon: 'success', duration: 1200 }),
        fail: (e) => this.showError('打开文件失败：' + (e.errMsg || ''))
      });
    } catch (err) {
      wx.openDocument({
        filePath,
        showMenu: true,
        success: () => wx.showToast({ title: '已打开文件', icon: 'success', duration: 1200 }),
        fail: (e) => this.showError('打开文件失败：' + (e.errMsg || ''))
      });
    }
  },

  _shareToWechat(filePath, fileName, count) {
    if (typeof wx.shareFileMessage !== 'function') {
      wx.showToast({ title: '当前微信版本不支持转发文件，请先打开预览再分享', icon: 'none', duration: 2200 });
      return;
    }
    if (!filePath || !/\.csv$/i.test(filePath)) {
      // 兜底重写一次确保后缀
      this._openDoc(filePath, fileName, count);
      return;
    }
    wx.shareFileMessage({
      filePath,
      fileName: fileName || `信息核对修改记录-${count}条.csv`,
      success: () => wx.showToast({ title: '已调起微信转发', icon: 'success', duration: 1200 }),
      fail: (e) => {
        const msg = (e && e.errMsg) || '';
        if (/cancel/i.test(msg)) return;
        if (/no permission|forwarding not allowed/i.test(msg)) {
          wx.showModal({ title: '请先打开预览', content: '在文件预览页面点击右上角可分享给好友', showCancel: false });
          return;
        }
        wx.showModal({ title: '转发失败', content: msg || '请尝试"打开文件预览"后再分享', showCancel: false });
      }
    });
  },

  _saveFile(filePath, fileName, count) {
    // 部分客户端 saveFile 会丢失扩展名，先复制到带 .csv 后缀的临时路径
    const fileManager = wx.getFileSystemManager();
    const name = (fileName && /\.csv$/i.test(fileName)) ? fileName : (fileName || `info_verify_${Date.now()}.csv`);
    const safeTmpPath = `${wx.env.USER_DATA_PATH}/save_${Date.now()}_${name}`;
    let realInput = filePath;
    try {
      if (fileManager.statSync(filePath, false)) {
        try { fileManager.copyFileSync(filePath, safeTmpPath); realInput = safeTmpPath; } catch (e) {}
      }
    } catch (e) {}

    wx.saveFile({
      tempFilePath: realInput,
      success: (res) => {
        const savedPath = res.savedFilePath;
        wx.showModal({
          title: '已保存',
          content: `已导出 ${count} 条修改记录。\n文件名：${name}\n文件保存在：\n${savedPath}`,
          confirmText: '我知道了',
          showCancel: false
        });
      },
      fail: (e) => {
        // saveFile 失败（部分客户端限制），降级为 setClipboardData + 提示用户从聊天窗口下载
        wx.setClipboardData({
          data: filePath,
          success: () => wx.showModal({
            title: '文件已生成',
            content: `小程序无法直接保存到磁盘，已将文件路径复制到剪贴板。可让电脑端访问或稍后从本地路径打开。\n文件名：${name}\n共 ${count} 条记录。`,
            confirmText: '我知道了',
            showCancel: false
          })
        });
      }
    });
  },

  onResetStudent(e) {
    const id = e.currentTarget.dataset.id;
    const name = e.currentTarget.dataset.name;
    if (!id) return;
    wx.showModal({
      title: '重置核对',
      content: `确定要重置「${name}」的核对状态吗？重置后学生可以重新提交修改。`,
      confirmText: '确认重置',
      confirmColor: '#ef4444',
      success: async (r) => {
        if (!r.confirm) return;
        await this._doResetStudent(id);
      }
    });
  },

  async _doResetStudent(id) {
    try {
      await tokenPost('/open_teacher/info_verify/reset', { xs_id: id });
      wx.showToast({ title: '已重置，学生可重新提交', icon: 'success', duration: 1500 });
      // 列表中直接更新该学生状态，无需重新请求整页
      const list = this.data.studentList.map(s =>
        s.id === id
          ? { ...s, status: 'pending', status_text: '待核对', modification_count: 0, submitted_at: '' }
          : s
      );
      // 同步更新顶部统计
      const pendingCount = this.data.pendingCount + 1;
      const verifiedCount = Math.max(0, this.data.verifiedCount - 1);
      this.setData({ studentList: list, pendingCount, verifiedCount });
    } catch (err) {
      this.showError((err && err.message) || '重置失败');
    }
  },

  goBack() { wx.navigateBack(); }
}, {
  requireAuth: true,
  userType: 'open_teacher'
});