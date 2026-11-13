const { createPage } = require('../../../utils/page-mixin');
const { tokenGet, BASE_URL } = require('../../../utils/request');
const { resolveImageUrl } = require('../../../utils/image-url');

// 任务轮询配置
const POLL_MAX_RETRIES = 60;   // 最多轮询次数(60 * 2s = 120s)
const POLL_INTERVAL_MS = 2000; // 每次间隔 2 秒

// 工具：读教师 token(直接从教师专用 storage 嵌套结构读取,不受其他角色覆盖)
function _readTeacherToken() {
  try {
    // 教师端 storage 是嵌套结构: { userInfo: { token, ... }, expireTime }
    const cache = wx.getStorageSync('vocational_teacher_auth_cache');
    if (cache && cache.userInfo && cache.userInfo.token &&
        cache.expireTime && cache.expireTime > Date.now()) {
      console.log('[vocational-teacher-photo] token 来自 vocational_teacher_auth_cache');
      return cache.userInfo.token;
    }
  } catch (e) {}
  // 兜底:同时检查 globalData,以及扁平 storage (兼容老版本)
  const app = getApp();
  if (app && app.globalData && app.globalData.userInfo &&
      app.globalData.userInfo.user_type === 'vocational_teacher' &&
      app.globalData.userInfo.token) {
    console.log('[vocational-teacher-photo] token 来自 globalData.userInfo');
    return app.globalData.userInfo.token;
  }
  try {
    const userInfo = wx.getStorageSync('userInfo');
    if (userInfo && userInfo.user_type === 'vocational_teacher' && userInfo.token) {
      console.log('[vocational-teacher-photo] token 来自 userInfo storage');
      return userInfo.token;
    }
  } catch (e) {}
  console.warn('[vocational-teacher-photo] 未找到任何教师 token');
  return '';
}

// 工具：原生 wx.uploadFile 封装,自动注入教师 token
function _rawUpload({ url, filePath, name = 'photo', formData = {} }) {
  return new Promise((resolve, reject) => {
    const token = _readTeacherToken();
    if (!token) {
      return reject({ msg: '未登录或登录已过期,请重新登录后再上传', noToken: true });
    }
    // [debug] 打印实际请求头
    console.log('[vocational-teacher-photo] upload token head:', token.slice(0, 30) + '...',
      'formData:', JSON.stringify(formData));
    const fullUrl = url.startsWith('http') ? url : BASE_URL + url;
    wx.uploadFile({
      url: fullUrl,
      filePath,
      name,
      formData,
      header: { Authorization: 'Bearer ' + token },
      success: (res) => {
        let body;
        try {
          body = typeof res.data === 'string' ? JSON.parse(res.data) : res.data;
        } catch (e) {
          return reject({ msg: '返回数据解析失败: ' + res.data });
        }
        if (res.statusCode === 401) {
          return reject({ msg: '登录已过期,请重新登录', unauthorized: true });
        }
        if (res.statusCode < 200 || res.statusCode >= 300) {
          return reject({ msg: (body && body.msg) || ('HTTP ' + res.statusCode) });
        }
        if (body && body.success === false) {
          return reject({ msg: body.msg || '上传失败' });
        }
        resolve(body && body.data ? body.data : body);
      },
      fail: (err) => reject({ msg: (err && (err.errMsg || err.message)) || '网络异常,上传失败' })
    });
  });
}

// 工具:原生 wx.request GET,自动注入教师 token
function _rawGet(path) {
  return new Promise((resolve, reject) => {
    const token = _readTeacherToken();
    if (!token) {
      return reject({ msg: '未登录或登录已过期,请重新登录' });
    }
    const fullUrl = path.startsWith('http') ? path : BASE_URL + path;
    wx.request({
      url: fullUrl,
      method: 'GET',
      header: { Authorization: 'Bearer ' + token },
      success: (res) => {
        if (res.statusCode === 401) {
          return reject({ msg: '登录已过期,请重新登录', unauthorized: true });
        }
        const body = res.data || {};
        if (body.success === false) {
          return reject({ msg: body.msg || '查询失败' });
        }
        resolve(body.data !== undefined ? body.data : body);
      },
      fail: (err) => reject({ msg: (err && (err.errMsg || err.message)) || '网络异常,查询失败' })
    });
  });
}

createPage({
  data: {
    studentList: [],
    loading: true,
    filterType: 'all',
    selectedClassId: '',
    classOptions: [],
    classList: [],
    totalCount: 0,
    hasPhotoCount: 0,
    noPhotoCount: 0,
    // 照片上传相关
    uploadingStudentId: null,
    isProcessing: false,
    isUploading: false,
    // 学籍状态筛选
    xjztFilter: 'all',
    xjztOptions: [],
    xjztList: [],
    xjztMap: {},
    xjztStats: {},
    filteredStudentList: [],
    // 抠图处理遮罩层
    processingOverlay: {
      show: false,
      title: '照片处理中',
      step: '',
      progress: -1,
      tip: '请稍候，预计需要 10-60 秒'
    },
  },

  onLoad() {
    this.loadClassList();
  },

  async loadClassList() {
    try {
      const res = await tokenGet('/vocational_teacher/classes');
      const classList = res || [];
      
      const classOptions = classList.map(c => ({
        text: c.name,
        value: c.id
      }));
      
      this.setData({
        classList: classList,
        classOptions: classOptions,
        selectedClassId: classList.length > 0 ? classList[0].id : ''
      });
      
      if (classList.length > 0) {
        this.loadStudentList();
      } else {
        this.setData({ loading: false });
      }
    } catch (error) {
      this.setData({ loading: false });
      this.showError('获取班级列表失败，请重试');
    }
  },

  onClassChange(e) {
    this.setData({
      selectedClassId: e.detail
    });
    this.loadStudentList();
  },

  onFilterChange(e) {
    this.setData({
      filterType: e.detail
    });
    this.loadStudentList();
  },

  onXjztFilterChange(e) {
    this.setData({
      xjztFilter: e.detail
    });
    this.filterStudentsByXjzt();
  },

  filterStudentsByXjzt() {
    const { xjztFilter, studentList } = this.data;
    
    let filtered;
    if (xjztFilter === 'all') {
      filtered = studentList;
    } else {
      filtered = studentList.filter(s => s.xjzt === xjztFilter);
    }
    
    const filteredWithIndex = filtered.map((s, index) => ({
      ...s,
      displayIndex: index + 1
    }));
    
    this.setData({
      filteredStudentList: filteredWithIndex
    });
  },

  async loadStudentList() {
    if (!this.data.selectedClassId) {
      this.setData({ 
        studentList: [], 
        filteredStudentList: [],
        loading: false, 
        totalCount: 0, 
        hasPhotoCount: 0, 
        noPhotoCount: 0,
        xjztMap: {},
        xjztStats: {},
        xjztOptions: [{ text: '全部状态', value: 'all' }]
      });
      return;
    }
    
    this.setData({ loading: true });
    
    try {
      const res = await tokenGet('/vocational_teacher/photo/list', {
        filter: this.data.filterType,
        bj_id: this.data.selectedClassId
      });
      
      const data = res || { students: [], xjzt_map: {} };
      const rawList = Array.isArray(data) ? data : (data.students || []);
      const studentList = rawList.map(s => ({
        ...s,
        photo_url: s.photo_url ? resolveImageUrl(s.photo_url) : ''
      }));
      const xjztMap = data.xjzt_map || {};
      
      const totalCount = studentList.length;
      const hasPhotoCount = studentList.filter(s => s.headphoto === 1).length;
      const noPhotoCount = totalCount - hasPhotoCount;
      
      const xjztStats = {};
      studentList.forEach(s => {
        const xjzt = s.xjzt || 'unknown';
        xjztStats[xjzt] = (xjztStats[xjzt] || 0) + 1;
      });
      
      const xjztOptions = [
        { text: `全部状态 (${totalCount})`, value: 'all' }
      ];
      
      if (Object.keys(xjztMap).length > 0) {
        const sortedIds = Object.keys(xjztMap)
          .map(id => parseInt(id))
          .sort((a, b) => a - b);
        
        sortedIds.forEach(id => {
          const count = xjztStats[id] || 0;
          if (count > 0) {
            xjztOptions.push({
              text: `${xjztMap[id]} (${count})`,
              value: id
            });
          }
        });
      }
      
      this.setData({
        studentList: studentList,
        filteredStudentList: studentList,
        xjztMap: xjztMap,
        xjztStats: xjztStats,
        xjztOptions: xjztOptions,
        loading: false,
        totalCount: totalCount,
        hasPhotoCount: hasPhotoCount,
        noPhotoCount: noPhotoCount,
        xjztFilter: 'all'
      });
      
      this.filterStudentsByXjzt();
    } catch (error) {
      this.setData({ loading: false });
      this.showError('获取学生列表失败，请重试');
    }
  },

  previewPhoto(e) {
    const { url, name } = e.currentTarget.dataset;
    if (url) {
      wx.previewImage({
        current: url,
        urls: [url]
      });
    } else {
      this.showError(`${name}暂无照片`);
    }
  },

  // 选择上传方式
  chooseUploadMethod(e) {
    const { studentId, studentName } = e.currentTarget.dataset;
    
    wx.showActionSheet({
      itemList: ['拍照', '从相册选择'],
      success: (res) => {
        if (res.tapIndex === 0) {
          this.takePhoto(studentId, studentName);
        } else {
          this.chooseFromAlbum(studentId, studentName);
        }
      }
    });
  },

  // 拍照
  takePhoto(studentId, studentName) {
    wx.chooseMedia({
      count: 1,
      mediaType: ['image'],
      sourceType: ['camera'],
      camera: 'front',
      success: (res) => {
        const tempFilePath = res.tempFiles[0].tempFilePath;
        this._submitAndPoll(tempFilePath, studentId, studentName);
      },
      fail: () => {
        this.showError('拍照失败，请重试');
      }
    });
  },

  // 从相册选择
  chooseFromAlbum(studentId, studentName) {
    wx.chooseMedia({
      count: 1,
      mediaType: ['image'],
      sourceType: ['album'],
      success: (res) => {
        const tempFilePath = res.tempFiles[0].tempFilePath;
        this._submitAndPoll(tempFilePath, studentId, studentName);
      },
      fail: () => {
        this.showError('选择照片失败，请重试');
      }
    });
  },

  // 核心：一体化上传 → 后端自动 AI 抠图+MinIO+海康同步
  // 直接用原生 wx.uploadFile + wx.request,自己注入教师 token,避免未登录上传风险
  async _submitAndPoll(filePath, studentId, studentName) {
    // 前置校验:教师必须登录
    const teacherToken = _readTeacherToken();
    if (!teacherToken) {
      this.showError('请先登录教师账号再上传');
      return;
    }

    // 从 studentList 获取身份证号(兼容多种后端字段命名)
    const student = this.data.studentList.find(s => s.id === studentId);
    const sfzh = student && (student.sfzh || student.id_card || student.sfzjh);
    if (!sfzh) {
      this.showError('无法获取学生身份证号');
      return;
    }

    this.setData({
      uploadingStudentId: studentId,
      isProcessing: true
    });

    this._showProcessingOverlay({
      title: '照片处理中',
      step: '正在提交任务...',
      progress: 0,
      tip: '请稍候，预计需要 10-60 秒'
    });

    let taskId;
    try {
      // 一体化接口：一次提交，后端自动完成 AI抠图→MinIO→DB→海康同步
      const submitRes = await _rawUpload({
        url: '/photo/process_photo_async',
        filePath: filePath,
        name: 'photo',
        formData: {
          sfzh: sfzh,
          user_type: 'vocational',
          size_name: 'two_inch',
          bg_color_name: 'blue',
          uploaded_by_teacher: 'true',
        },
      });
      taskId = submitRes.task_id;
      if (!taskId) throw new Error('创建任务失败');
    } catch (err) {
      this._hideProcessingOverlay();
      this.setData({
        isProcessing: false,
        uploadingStudentId: null
      });
      this.showError(this._errMsg(err) || '上传失败，请重试');
      return;
    }

    // ---- 轮询任务状态 ----
    try {
      const result = await this._pollTask(taskId);
      const photoUrl = result.photo_url || '';

      // 更新本地数据：直接用后端返回的 MinIO 路径
      const studentList = this.data.studentList.map(s => {
        if (s.id === studentId) {
          return {
            ...s,
            headphoto: 1,
            photo_url: resolveImageUrl(photoUrl)
          };
        }
        return s;
      });
      const hasPhotoCount = studentList.filter(s => s.headphoto === 1).length;
      const noPhotoCount = studentList.length - hasPhotoCount;

      this.setData({
        studentList,
        hasPhotoCount,
        noPhotoCount,
        isProcessing: false,
        uploadingStudentId: null
      });
      this.filterStudentsByXjzt();

      // 完成提示
      this._updateProcessingOverlay({
        title: '上传成功',
        step: '照片已上传到 MinIO 并同步海康',
        progress: 100,
        tip: '点击任意位置关闭',
      });
      setTimeout(() => {
        this._hideProcessingOverlay();
        this.showSuccess(`已为 ${studentName} 上传照片`);
      }, 1500);
    } catch (err) {
      this._hideProcessingOverlay();
      this.setData({
        isProcessing: false,
        uploadingStudentId: null
      });
      this.showError(this._errMsg(err) || '处理失败，请重试');
    }
  },

  // 原生 wx.request 轮询任务状态
  async _pollTask(taskId) {
    for (let i = 0; i < POLL_MAX_RETRIES; i++) {
      try {
        const res = await _rawGet(`/photo/task_status/${taskId}`);

        // 实时更新进度条
        if (res && typeof res.progress === 'number') {
          this._updateProcessingOverlay({
            step: res.step || this.data.processingOverlay.step,
            progress: res.progress,
          });
        }

        if (res.status === 'completed') {
          return res.result || {};
        }
        if (res.status === 'failed') {
          throw new Error(res.error || '处理失败');
        }

        await new Promise(r => setTimeout(r, POLL_INTERVAL_MS));
      } catch (err) {
        // 401 直接退出轮询
        if (err && err.unauthorized) throw err;
        // 网络抖动继续重试;最后一次失败才抛
        if (i >= POLL_MAX_RETRIES - 1) throw err;
        await new Promise(r => setTimeout(r, POLL_INTERVAL_MS));
      }
    }
    throw new Error('处理超时，请重试');
  },

  _errMsg(err) {
    if (!err) return '';
    if (err.noToken || err.unauthorized) {
      return '登录已过期,请重新登录';
    }
    return err.msg || err.errorMsg || (err.responseData && err.responseData.msg) || err.message || '操作失败';
  },

  // ─── 抠图处理遮罩层 ───────────────────────────────────────────
  _showProcessingOverlay(opts = {}) {
    this.setData({
      processingOverlay: {
        show: true,
        title: opts.title || '照片处理中',
        step: opts.step || '',
        progress: opts.progress !== undefined ? opts.progress : -1,
        tip: opts.tip || '请稍候，预计需要 10-60 秒'
      }
    });
  },

  _updateProcessingOverlay(opts = {}) {
    this.setData({
      processingOverlay: {
        ...this.data.processingOverlay,
        ...opts
      }
    });
  },

  _hideProcessingOverlay() {
    this.setData({ 'processingOverlay.show': false });
  },

  goBack() {
    wx.navigateBack();
  }
}, {
  requireAuth: true,
  userType: 'vocational_teacher'
});
