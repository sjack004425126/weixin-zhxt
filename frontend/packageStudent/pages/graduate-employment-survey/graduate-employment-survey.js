const { createPage } = require('../../../utils/page-mixin');
const { post, get, uploadFile } = require('../../../utils/request');
const { areaList } = require('../../../utils/area-data');
const { parseCategoryHeader } = require('../../../utils/category-header');
const { resolveImageUrl } = require('../../../utils/image-url');
const { checkFeatureSwitch } = require('../../../utils/feature-switch');

// ===== 本地缓存 / 分页 常量（放模块作用域，避免 page-mixin 丢弃顶层非方法属性）=====
const FORM_CACHE_KEY = 'grad_emp_survey_form_cache';
const DICT_CACHE_KEY = 'grad_emp_survey_dict_cache_v1';
const DICT_CACHE_TTL = 6 * 60 * 60 * 1000; // 6 小时
const LIST_PAGE_SIZE = 50;

// ===== 静态选项数据 =====
const DESTINATION_OPTIONS = [
  { value: '1', label: '签订合同或就业协议就业' },
  { value: '2', label: '应征义务兵' },
  { value: '3', label: '自主创业' },
  { value: '4', label: '灵活就业' },
  { value: '5', label: '普通高考升学' },
  { value: '6', label: '职教高考升学' },
  { value: '7', label: '出国、出境升学' },
  { value: '8', label: '贯通培养升学' },
  { value: '9', label: '待就业' },
  { value: '10', label: '不就业拟升学' },
  { value: '11', label: '其他暂不就业' }
];

const YESNO_OPTIONS = [
  { value: '1', label: '是' },
  { value: '2', label: '否' }
];

const EDU_LEVEL_OPTIONS = [
  { value: '1', label: '本科' },
  { value: '2', label: '专科' }
];

const CONTRACT_OPTIONS = [
  { value: '1', label: '1年及以内' },
  { value: '2', label: '1-2（含）年' },
  { value: '3', label: '2-3（含）年' },
  { value: '4', label: '3年以上' }
];

const CHANNEL_OPTIONS = [
  { value: '1', label: '学校推荐' },
  { value: '2', label: '中介介绍' },
  { value: '3', label: '其他渠道' }
];

const NATURE_OPTIONS = [
  { value: '1', label: '机关' },
  { value: '2', label: '事业单位' },
  { value: '3', label: '国企' },
  { value: '4', label: '民企' },
  { value: '5', label: '其它' }
];

const INDUSTRY_OPTIONS = [
  '制造业','建筑业','物流交通','教育/培训','互联网','计算机/软件','批发和零售',
  '住宿餐饮业','金融业','房地产业','出租/租赁','专业服务（如法律/咨询服务）',
  '科学研究','生活服务（如家政/美发类服务）','医疗卫生/社会保障','文化娱乐',
  '政府事业单位','农、林、牧、渔业','水利环境公共设施管理','电力燃气','采矿业','国际组织'
].map((label, i) => ({ value: String(i + 1), label }));

const SATISFACTION_OPTIONS = [
  { value: '1', label: '非常满意' },
  { value: '2', label: '满意' },
  { value: '3', label: '比较满意' },
  { value: '4', label: '不满意' },
  { value: '5', label: '无法评估' }
];

createPage({
  data: {
    // 页面头部（来自后端 zs_category.extra_info）
    headerBadge: '',
    headerTitles: [],
    headerSubtitle: '',

    // 选项
    destinationOptions: DESTINATION_OPTIONS,
    yesnoOptions: YESNO_OPTIONS,
    eduLevelOptions: EDU_LEVEL_OPTIONS,
    contractOptions: CONTRACT_OPTIONS,
    channelOptions: CHANNEL_OPTIONS,
    natureOptions: NATURE_OPTIONS,
    industryOptions: INDUSTRY_OPTIONS,
    satisfactionOptions: SATISFACTION_OPTIONS,

    // 字典（全量数据挂在实例变量，不进 data；data 里只放当前要渲染的切片）
    collegeGrouped: [],       // 要渲染的高校（根据 collegePage*pageSize 切片后再按省分组）
    collegePage: 1,
    collegeHasMore: false,
    collegeTotal: 0,
    majorListFiltered: [],    // 要渲染的专业切片
    majorPage: 1,
    majorHasMore: false,
    majorTotal: 0,
    collegeKeyword: '',
    majorKeyword: '',
    collegeCustomInput: '',
    majorCustomInput: '',

    // 省/市/区 地址选择
    areaList: areaList,
    areaCode: '',
    showAreaPopup: false,

    // 学生列表：全量数组挂在实例变量 this._studentListAll（不进 setData，避免大对象同步到渲染层）；
    // studentList 仅放当前要渲染的切片（page*pageSize 条），滑到底追加下一页
    studentList: [],
    studentPage: 1,
    studentHasMore: false,
    studentTotal: 0,
    studentLoading: false,
    studentKeyword: '',
    // 选中某一条后拉取的详情（姓名/性别/班级/班主任等）。为空时弹层处于"搜索列表"模式，非空时为"确认本人"模式
    studentDetail: null,
    studentDetailLoading: false,

    // 表单数据
    formData: {
      student_no: '',
      student_name: '',
      id_card: '',
      phone: '',
      precise_service: '',
      destination: '',
      military_office: '',
      education_level: '',
      college_code: '',
      college_name: '',
      major_code: '',
      major_name: '',
      admission_score: '',
      contract_type: '',
      employment_channel: '',
      company_name: '',
      work_province_city: '',
      work_address: '',
      company_nature: '',
      industry: '',
      position: '',
      position_name: '',
      monthly_salary: '',
      // 就业凭证：
      //   certificate_local_path: 本地临时路径（用户选了还没上传），用于即时预览
      //   certificate_url:         已上传后的 DB key（形如 zs/<uuid>.jpg，不带桶名），
      //                            提交时由 _uploadCertificateIfNeeded() 写入
      certificate_local_path: '',
      certificate_url: '',
      certificateUrlDisplay: '',   // 给 wxml <image src> 用的可直接渲染的 URL（本地或签名）
      satisfaction: '',
      need_recommendation: '',
      feedback: ''
    },

    selectedStudentText: '',
    selectedDestinationText: '',
    selectedEduLevelText: '',
    selectedCollegeText: '',
    selectedMajorText: '',
    selectedContractText: '',
    selectedChannelText: '',
    selectedNatureText: '',
    selectedIndustryText: '',
    selectedSatisfactionText: '',

    // 弹窗控制
    showStudentPopup: false,
    showCollegePopup: false,
    showMajorPopup: false,

    // 提交状态
    isSubmitting: false,
    canSubmit: false,
    
    // 报名成功弹窗
    showSuccessModal: false,
    successQueryCode: '',
    
    focusField: ''
  },

  // 全量数据与当前过滤后的集合（运行时会赋值）：仅挂实例，不进 setData。
  // 注：这里不能依赖页面顶层字段被 page-mixin 保留，需要在 onLoad/赋值时从 this 创建。

  onLoad() {
    checkFeatureSwitch('graduate', this);
    // 实例变量初始化（避免 page-mixin 丢掉顶层非方法属性）
    this._studentListAll = [];
    this._studentFiltered = [];
    this._collegeListAll = [];
    this._collegeFiltered = [];
    this._majorListAll = [];
    this._majorFiltered = [];
    this.restoreFormCache();
    this.loadInfo();
    // 学生 / 高校 / 专业 字典：优先从本地缓存加载，未命中才走网络。
    this.loadDictsWithCache(false);
  },

  // 读本地字典缓存。过期或不存在返回 null。
  _readDictCache() {
    try {
      const obj = wx.getStorageSync(DICT_CACHE_KEY);
      if (!obj || typeof obj !== 'object') return null;
      if (!obj.savedAt || (Date.now() - obj.savedAt) > DICT_CACHE_TTL) return null;
      return obj;
    } catch (e) { return null; }
  },
  _writeDictCache(payload) {
    try {
      wx.setStorageSync(DICT_CACHE_KEY, Object.assign({ savedAt: Date.now() }, payload));
    } catch (e) {}
  },

  // forceRefresh=true 时忽略缓存重拉全部
  async loadDictsWithCache(forceRefresh) {
    if (!forceRefresh) {
      const cache = this._readDictCache();
      if (cache && Array.isArray(cache.studentListAll) && Array.isArray(cache.collegeList) && Array.isArray(cache.majorList)) {
        // 全量只挂实例，不进 data；渲染数组初始为空（弹层打开时再切片）
        this._studentListAll = cache.studentListAll;
        this._collegeListAll = cache.collegeList;
        this._majorListAll = cache.majorList;
        this.setData({
          studentTotal: cache.studentListAll.length,
          collegeTotal: cache.collegeList.length,
          majorTotal: cache.majorList.length
        });
        return;
      }
    }
    // 拉取最新
    if (forceRefresh) {
      wx.showLoading({ title: '正在刷新...', mask: true });
    }
    try {
      await Promise.all([
        this.loadStudents(),
        this.loadDict('college'),
        this.loadDict('major')
      ]);
      // 全部拉取成功后写入本地缓存
      this._writeDictCache({
        studentListAll: this._studentListAll || [],
        collegeList: this._collegeListAll || [],
        majorList: this._majorListAll || []
      });
      if (forceRefresh) {
        wx.showToast({ title: '已刷新最新数据', icon: 'success' });
      }
    } catch (e) {
      if (forceRefresh) {
        wx.showToast({ title: '刷新失败，请重试', icon: 'none' });
      }
    } finally {
      if (forceRefresh) wx.hideLoading();
    }
  },

  // 页面「刷新字典」按钮点击入口
  refreshDicts() {
    this.loadDictsWithCache(true);
  },

  // 加载调查类别信息（页面头部）
  async loadInfo() {
    try {
      const res = await get('/grad_emp_survey/info', { showLoading: false });
      const header = parseCategoryHeader(res && res.extra_info);
      this.setData({
        headerBadge: header.headerBadge,
        headerTitles: header.headerTitles,
        headerSubtitle: header.headerSubtitle
      });
    } catch (e) {
      console.error('加载调查信息头部失败', e);
    }
  },

  // ========== 缓存 ==========
  saveFormCache() {
    try {
      wx.setStorageSync(FORM_CACHE_KEY, {
        formData: this.data.formData,
        selectedStudentText: this.data.selectedStudentText,
        selectedDestinationText: this.data.selectedDestinationText,
        selectedEduLevelText: this.data.selectedEduLevelText,
        selectedCollegeText: this.data.selectedCollegeText,
        selectedMajorText: this.data.selectedMajorText,
        selectedContractText: this.data.selectedContractText,
        selectedChannelText: this.data.selectedChannelText,
        selectedNatureText: this.data.selectedNatureText,
        selectedIndustryText: this.data.selectedIndustryText,
        selectedSatisfactionText: this.data.selectedSatisfactionText,
        timestamp: Date.now()
      });
    } catch (e) {}
  },

  restoreFormCache() {
    try {
      const cache = wx.getStorageSync(FORM_CACHE_KEY);
      if (!cache || !cache.formData) return;
      if (Date.now() - cache.timestamp > 7 * 24 * 60 * 60 * 1000) {
        wx.removeStorageSync(FORM_CACHE_KEY);
        return;
      }
      // 恢复时临时路径失效，display URL 走已上传 key 的签名
      const fd = Object.assign({}, cache.formData, {
        certificate_local_path: '' // 本地路径跨生命周期无效，丢弃
      });
      const displayUrl = fd.certificate_url
        ? resolveImageUrl('/object/' + fd.certificate_url.replace(/^\/+/, ''))
        : '';
      this.setData({
        formData: fd,
        certificateUrlDisplay: displayUrl,
        selectedStudentText: cache.selectedStudentText || '',
        selectedDestinationText: cache.selectedDestinationText || '',
        selectedEduLevelText: cache.selectedEduLevelText || '',
        selectedCollegeText: cache.selectedCollegeText || '',
        selectedMajorText: cache.selectedMajorText || '',
        selectedContractText: cache.selectedContractText || '',
        selectedChannelText: cache.selectedChannelText || '',
        selectedNatureText: cache.selectedNatureText || '',
        selectedIndustryText: cache.selectedIndustryText || '',
        selectedSatisfactionText: cache.selectedSatisfactionText || ''
      }, () => this.checkCanSubmit());
    } catch (e) {}
  },

  clearFormCache() {
    try { wx.removeStorageSync(FORM_CACHE_KEY); } catch (e) {}
  },

  // ========== 数据加载 ==========
  // 一次性拉全部学生字典：放在实例变量 _studentListAll，不进 data
  async loadStudents() {
    this.setData({ studentLoading: true });
    try {
      const res = await get('/grad_emp_survey/students', {}, { showLoading: false });
      const list = res || [];
      this._studentListAll = list;
      this.setData({ studentTotal: list.length });
    } catch (e) {
      this.showError('加载学生列表失败');
    } finally {
      this.setData({ studentLoading: false });
    }
  },

  // 本地过滤：按姓名或学号包含关键词；过滤后重置到第 1 页
  filterStudentsLocal(keyword) {
    const kw = (keyword || '').trim().toLowerCase();
    const all = this._studentListAll || [];
    this._studentFiltered = kw
      ? all.filter(it => (it.xs_xm || '').toLowerCase().indexOf(kw) >= 0
                     || (it.xs_xh || '').toLowerCase().indexOf(kw) >= 0)
      : all;
    this._renderStudents(1);
  },
  // 运算并 setData 第 page 页的切片
  _renderStudents(page) {
    const size = LIST_PAGE_SIZE;
    const total = this._studentFiltered.length;
    const limit = Math.min(page * size, total);
    this.setData({
      studentList: this._studentFiltered.slice(0, limit),
      studentPage: page,
      studentHasMore: total > limit
    });
  },
  onStudentScrollLower() {
    this._tryLoadMore('student');
  },

  // ========== 统一的"快到底就预加载"兜底 ==========
  // 由 scroll-view bindscroll 触发；距离底部 < 300px 即提前加载下一页。
  // _viewportH 缓存视口高度（首次触发时通过 boundingClientRect 获取，后续复用）。
  onListScroll(e) {
    const which = e.currentTarget.dataset.list; // 'student' | 'college' | 'major'
    const detail = e.detail || {};
    const scrollTop = detail.scrollTop || 0;
    const scrollHeight = detail.scrollHeight || 0;
    // 拿一次视口高度，缓存到实例
    if (!this._viewportH) {
      const q = wx.createSelectorQuery().in(this);
      q.select('.popup-list').boundingClientRect(rect => {
        if (rect && rect.height) this._viewportH = rect.height;
      }).exec();
    }
    const vh = this._viewportH || 600; // 兜底 600px
    // 距底部小于 300px 预加载
    if (scrollHeight - scrollTop - vh < 300) {
      this._tryLoadMore(which);
    }
  },

  // 节流：同一弹层一次只允许一个加载操作进行；setData 完成后才允许下一次
  _tryLoadMore(which) {
    if (this._loadingMore) return;
    if (which === 'student') {
      if (!this.data.studentHasMore) return;
      this._loadingMore = true;
      this._renderStudents(this.data.studentPage + 1);
    } else if (which === 'college') {
      if (!this.data.collegeHasMore) return;
      this._loadingMore = true;
      this._renderCollegeGrouped(this.data.collegePage + 1);
    } else if (which === 'major') {
      if (!this.data.majorHasMore) return;
      this._loadingMore = true;
      this._renderMajor(this.data.majorPage + 1);
    } else {
      return;
    }
    // 给渲染一点时间再放开锁，避免一次滚动疯狂连发
    setTimeout(() => { this._loadingMore = false; }, 80);
  },

  async loadDict(type) {
    try {
      const res = await get('/grad_emp_survey/dict', { type }, { showLoading: false });
      const list = res || [];
      if (type === 'college') {
        // 解析 remark="省|层次" 为 province / level 字段；全量不进 data
        const enriched = list.map(it => {
          const remark = it.remark || '';
          const parts = remark.split('|');
          return Object.assign({}, it, {
            province: parts[0] || '',
            level: parts[1] || ''
          });
        });
        this._collegeListAll = enriched;
        this.setData({ collegeTotal: enriched.length });
      } else {
        this._majorListAll = list;
        this.setData({ majorTotal: list.length });
      }
    } catch (e) {
      console.error('加载字典失败', type, e);
    }
  },

  // ========== 高校：按省分组 + 搜索 + 分页 ==========
  // 过滤 → 存到 _collegeFiltered → 重置到第 1 页渲染
  rebuildCollegeGrouped() {
    const kw = (this.data.collegeKeyword || '').trim().toLowerCase();
    const list = this._collegeListAll || [];
    this._collegeFiltered = kw
      ? list.filter(it =>
          (it.label || '').toLowerCase().indexOf(kw) >= 0 ||
          (it.province || '').toLowerCase().indexOf(kw) >= 0 ||
          (it.code || '').toLowerCase().indexOf(kw) >= 0
        )
      : list;
    this._renderCollegeGrouped(1);
  },
  // 取 _collegeFiltered 前 page*pageSize 条，再按省分组后渲染
  _renderCollegeGrouped(page) {
    const size = LIST_PAGE_SIZE;
    const total = this._collegeFiltered.length;
    const limit = Math.min(page * size, total);
    const prefix = this._collegeFiltered.slice(0, limit);
    const groupMap = {};
    const order = [];
    prefix.forEach(it => {
      const p = it.province || '其他';
      if (!groupMap[p]) { groupMap[p] = []; order.push(p); }
      groupMap[p].push(it);
    });
    const grouped = order.map(p => ({ province: p, items: groupMap[p] }));
    this.setData({
      collegeGrouped: grouped,
      collegePage: page,
      collegeHasMore: total > limit
    });
  },
  onCollegeScrollLower() { this._tryLoadMore('college'); },

  onCollegeSearch(e) {
    this.setData({ collegeKeyword: e.detail.value }, () => this.rebuildCollegeGrouped());
  },

  onCollegeCustomInput(e) {
    this.setData({ collegeCustomInput: e.detail.value });
  },

  confirmCustomCollege() {
    const v = (this.data.collegeCustomInput || '').trim();
    if (!v) { this.showError('请输入高校名称'); return; }
    this.setData({
      'formData.college_code': 'CUSTOM',
      'formData.college_name': v,
      selectedCollegeText: v + '（手动输入）',
      showCollegePopup: false,
      collegeCustomInput: ''
    }, () => this.checkCanSubmit());
  },

  // ========== 专业：搜索 + 分页 ==========
  rebuildMajorFiltered() {
    const kw = (this.data.majorKeyword || '').trim().toLowerCase();
    const list = this._majorListAll || [];
    this._majorFiltered = kw
      ? list.filter(it =>
          (it.label || '').toLowerCase().indexOf(kw) >= 0 ||
          (it.code || '').toLowerCase().indexOf(kw) >= 0
        )
      : list;
    this._renderMajor(1);
  },
  _renderMajor(page) {
    const size = LIST_PAGE_SIZE;
    const total = this._majorFiltered.length;
    const limit = Math.min(page * size, total);
    this.setData({
      majorListFiltered: this._majorFiltered.slice(0, limit),
      majorPage: page,
      majorHasMore: total > limit
    });
  },
  onMajorScrollLower() { this._tryLoadMore('major'); },

  onMajorSearch(e) {
    this.setData({ majorKeyword: e.detail.value }, () => this.rebuildMajorFiltered());
  },

  onMajorCustomInput(e) {
    this.setData({ majorCustomInput: e.detail.value });
  },

  confirmCustomMajor() {
    const v = (this.data.majorCustomInput || '').trim();
    if (!v) { this.showError('请输入专业名称'); return; }
    this.setData({
      'formData.major_code': 'CUSTOM',
      'formData.major_name': v,
      selectedMajorText: v + '（手动输入）',
      showMajorPopup: false,
      majorCustomInput: ''
    }, () => this.checkCanSubmit());
  },

  // ========== 通用焦点 ==========
  onInputFocus(e) { this.setData({ focusField: e.currentTarget.dataset.field }); },
  onInputBlur() { this.setData({ focusField: '' }); },

  // ========== 学生选择 ==========
  // 打开弹层：先以最小代价显示弹层（不立即 setData 大数组），下一帧再切片渲染
  showStudentPopup() {
    // 先打开外壳，保证弹层动画流畅
    this.setData({
      showStudentPopup: true,
      studentKeyword: '',
      studentDetail: null,
      studentDetailLoading: false,
      studentList: [] // 清空旧渲染，避免大列表残留
    });
    // 全集为空（首载失败）则重拉
    if (!(this._studentListAll && this._studentListAll.length)) {
      this.loadStudents().then(() => {
        wx.nextTick(() => this.filterStudentsLocal(''));
      });
      return;
    }
    // 让弹层先完成挂载/动画，再异步填充列表，消除点击瞬间的卡顿
    wx.nextTick(() => this.filterStudentsLocal(''));
  },
  closeStudentPopup() {
    this.setData({
      showStudentPopup: false,
      studentDetail: null,
      studentDetailLoading: false
    });
  },
  // 输入 → 本地过滤（无需请求、无需防抖）
  onStudentSearch(e) {
    const kw = e.detail.value;
    this.setData({ studentKeyword: kw });
    this.filterStudentsLocal(kw);
  },
  // 点选一条 → 按学号拉取该学生详情，进入确认本人面板
  async selectStudent(e) {
    const xh = e.currentTarget.dataset.xh;
    if (!xh) return;
    this.setData({ studentDetailLoading: true });
    try {
      // request.js 在 success=true 时已自动解包 data，这里拿到的就是 detail 对象
      const detail = await get('/grad_emp_survey/students/detail', { student_no: xh }, { showLoading: false });
      if (!detail) {
        this.setData({ studentDetailLoading: false });
        this.showError('未找到该学生信息');
        return;
      }
      this.setData({ studentDetail: detail, studentDetailLoading: false });
    } catch (err) {
      this.setData({ studentDetailLoading: false });
      this.showError(typeof err === 'string' ? err : '获取学生详情失败');
    }
  },
  // 返回搜索列表
  backStudentList() {
    this.setData({ studentDetail: null });
  },
  // 确认本人 → 回填表单并关闭弹层
  confirmStudent() {
    const stu = this.data.studentDetail;
    if (!stu) return;
    this.setData({
      'formData.student_no': stu.xs_xh,
      'formData.student_name': stu.xs_xm,
      'formData.id_card': stu.xs_sfzh,
      selectedStudentText: `${stu.xs_xh} - ${stu.xs_xm} - ${stu.bj_mc}`,
      showStudentPopup: false,
      studentDetail: null
    }, () => this.checkCanSubmit());
  },

  // ========== 输入字段 ==========
  // 防抖触发 checkCanSubmit（含 saveFormCache 同步落盘），避免快速输入时丢字
  _debouncedCheck() {
    if (this._checkTimer) clearTimeout(this._checkTimer);
    this._checkTimer = setTimeout(() => {
      this._checkTimer = null;
      this.checkCanSubmit();
    }, 300);
  },
  onPhoneInput(e) {
    // 仅写入 formData，不触发同步 setStorage；校验延迟到停止输入后
    this.setData({ 'formData.phone': e.detail.value });
    this._debouncedCheck();
  },
  onTextInput(e) {
    const field = e.currentTarget.dataset.field;
    this.setData({ [`formData.${field}`]: e.detail.value });
    this._debouncedCheck();
  },

  // ========== 单选弹窗-通用 ==========
  // 通用 picker：在主页面用 picker
  bindPicker(e) {
    const field = e.currentTarget.dataset.field;
    const optionsName = e.currentTarget.dataset.options;
    const textField = e.currentTarget.dataset.textfield;
    const idx = parseInt(e.detail.value);
    const list = this.data[optionsName] || [];
    const item = list[idx];
    if (!item) return;
    const update = { [`formData.${field}`]: item.value };
    if (textField) update[textField] = item.label;
    this.setData(update, () => this.checkCanSubmit());
  },

  // ========== 高校 / 专业弹窗 ==========
  showCollegePopup() {
    this.setData({ showCollegePopup: true, collegeGrouped: [] });
    wx.nextTick(() => this.rebuildCollegeGrouped());
  },
  closeCollegePopup() { this.setData({ showCollegePopup: false }); },
  selectCollege(e) {
    const code = e.currentTarget.dataset.code;
    const item = (this._collegeListAll || []).find(c => c.code === code);
    if (!item) return;
    this.setData({
      'formData.college_code': code,
      'formData.college_name': item.label,
      selectedCollegeText: item.label,
      showCollegePopup: false
    }, () => this.checkCanSubmit());
  },

  showMajorPopup() {
    this.setData({ showMajorPopup: true, majorListFiltered: [] });
    wx.nextTick(() => this.rebuildMajorFiltered());
  },
  closeMajorPopup() { this.setData({ showMajorPopup: false }); },
  selectMajor(e) {
    const code = e.currentTarget.dataset.code;
    const item = (this._majorListAll || []).find(m => m.code === code);
    if (!item) return;
    this.setData({
      'formData.major_code': code,
      'formData.major_name': item.label,
      selectedMajorText: item.label,
      showMajorPopup: false
    }, () => this.checkCanSubmit());
  },

  // ========== 文件选择（只缓存本地路径，不上传） ==========
  // 旧逻辑：选完图立即 uploadFile → formData.certificate_url 拿到的是 MinIO key。
  // 新逻辑：选完图只存本地 tempFilePath，等提交时（submitForm）才统一上传。
  //        DB 最终存的 certificate_url 形如 zs/<uuid>.jpg（不带桶名）—— 与 minio_service.put_zs_image 实际写入的 object_key 一致。
  async chooseFile() {
    try {
      const res = await wx.chooseImage({ count: 1, sizeType: ['compressed'], sourceType: ['album', 'camera'] });
      const tempFile = res.tempFilePaths[0];
      if (!tempFile) return;
      // 本地临时路径可直接用于 <image src>，无需签名
      this.setData({
        'formData.certificate_local_path': tempFile,
        'formData.certificate_url': '',   // 选新图后清掉旧 key（旧图届时已提交或从未上传）
        certificateUrlDisplay: tempFile,
      }, () => {
        this.saveFormCache();
        this.checkCanSubmit();
      });
    } catch (e) {
      if (e && e.errMsg && e.errMsg.indexOf('cancel') !== -1) return;
      console.error('选择图片失败', e);
      this.showError(e && (e.errMsg || e.message) || '选择图片失败');
    }
  },

  deleteFile() {
    wx.showModal({
      title: '提示',
      content: '确定要删除这张图片吗？',
      success: (res) => {
        if (res.confirm) {
          // 仅清掉本地状态；如果之前有上传过的 key，提交失败时由 _rollbackUploadedCertificate 删除 MinIO 孤儿对象
          this.setData({
            'formData.certificate_local_path': '',
            'formData.certificate_url': '',
            certificateUrlDisplay: '',
          }, () => {
            this.saveFormCache();
            this.checkCanSubmit();
          });
        }
      }
    });
  },

  previewUploadedImage(e) {
    const src = e.currentTarget.dataset.src;
    if (!src) return;
    wx.previewImage({ current: src, urls: [src] });
  },

  // ========== 就业凭证：提交时统一上传 ==========
  /**
   * 把 formData.certificate_local_path 上传到 MinIO（zs/<uuid>.jpg），
   * 写入 formData.certificate_url。返回最终写入的 DB key（用于失败回滚）。
   *
   * - 若本地路径为空：跳过上传，沿用现有的 certificate_url（不应发生，提交校验已守住）。
   * - 若本地路径为空 + certificate_url 也为空：返回 null（前端校验已阻止）。
   */
  async _uploadCertificateIfNeeded() {
    const localPath = this.data.formData.certificate_local_path;
    if (!localPath) {
      // 已是上传过的 key 或为空；不重新上传
      return this.data.formData.certificate_url || null;
    }
    const data = await uploadFile({
      url: '/vocational34/upload_image',
      filePath: localPath,
      name: 'file',
      showLoading: true,
      loadingTitle: '上传凭证中...'
    });
    if (!data || !data.key) {
      throw new Error('就业凭证上传失败');
    }
    // 后端 put_zs_image 返回 <bucket>/<uuid>.<ext>；DB 规范要求只存纯 key zs/<uuid>.<ext>
    const rawKey = String(data.key).replace(/^\/+/, '');
    // 硬编码桶名（统一桶 zhxt；历史桶名 guizhou-zhpt-prod-private 等同样兼容），不依赖后端常量。
    const _BUCKET_NAMES = ['zhxt', 'guizhou-zhpt-prod-private', 'guizhou-zhpt-prod-public', 'headphoto'];
    let dbKey = rawKey;
    for (const _b of _BUCKET_NAMES) {
      if (dbKey.startsWith(_b + '/')) { dbKey = dbKey.slice(_b.length + 1); break; }
    }
    this.setData({ 'formData.certificate_url': dbKey });
    return dbKey;
  },

  /**
   * 提交失败/回滚：删除刚上传但没绑工单的 MinIO 对象（孤儿）。
   * 仅在 _uploadCertificateIfNeeded 真的产生新上传时调用，避免误删历史数据。
   */
  async _rollbackUploadedCertificate(justUploadedKey) {
    if (!justUploadedKey) return;
    // best-effort：失败不抛出也不阻塞主流程
    try {
      const { silentPost } = require('../../../utils/request');
      await silentPost('/vocational34/delete_image', { key: justUploadedKey });
    } catch (e) {
      // 静默：孤儿可由后台清理脚本处理
      console.warn('[rollback certificate] failed:', e);
    }
  },

  // ========== 省/市/区 地址选择 ==========
  openAreaPopup() {
    this.setData({ showAreaPopup: true });
  },
  closeAreaPopup() {
    this.setData({ showAreaPopup: false });
  },
  onAreaConfirm(e) {
    // values: [{code, name}, {code, name}, {code, name}]
    const values = (e.detail && e.detail.values) || [];
    const names = values.map(v => v && v.name).filter(Boolean);
    const last = values[values.length - 1];
    const code = last && last.code ? last.code : '';
    this.setData({
      areaCode: code,
      showAreaPopup: false,
      'formData.work_province_city': names.join(' ')
    }, () => {
      this.saveFormCache();
      this.checkCanSubmit();
    });
  },

  // ========== 校验 / 提交（按分支全部必填） ==========
  checkCanSubmit() {
    const f = this.data.formData;
    const nonEmpty = (v) => v !== undefined && v !== null && String(v).trim() !== '';
    const baseOk = !!(nonEmpty(f.student_name) && nonEmpty(f.phone) && /^1[3-9]\d{9}$/.test(f.phone) &&
                      nonEmpty(f.precise_service) && nonEmpty(f.destination));
    let branchOk = true;
    if (f.destination === '1') {
      // Q10→Q18 全部
      branchOk = !!(nonEmpty(f.contract_type) && nonEmpty(f.employment_channel) && nonEmpty(f.company_name) &&
                    nonEmpty(f.work_province_city) && nonEmpty(f.work_address) && nonEmpty(f.company_nature) &&
                    nonEmpty(f.industry) && nonEmpty(f.position_name) && nonEmpty(f.monthly_salary));
    } else if (f.destination === '2') {
      branchOk = nonEmpty(f.military_office);
    } else if (f.destination === '3') {
      branchOk = !!(nonEmpty(f.company_name) && nonEmpty(f.work_province_city) && nonEmpty(f.work_address) &&
                    nonEmpty(f.company_nature) && nonEmpty(f.industry) && nonEmpty(f.position_name) && nonEmpty(f.monthly_salary));
    } else if (f.destination === '4') {
      branchOk = !!(nonEmpty(f.industry) && nonEmpty(f.position_name) && nonEmpty(f.monthly_salary));
    } else if (['5','6','7','8'].indexOf(f.destination) >= 0) {
      branchOk = !!(nonEmpty(f.education_level) && nonEmpty(f.college_code) && nonEmpty(f.major_code) && nonEmpty(f.admission_score));
    }
    // 就业凭证：destination 1-8 必传，9/10/11 不需
    // 凭证只要"已上传的 key"或"本地临时路径"任一存在即算 OK。
    // 新逻辑：选完图只存本地路径，等提交时才统一上传。
    let certOk = true;
    if (['1','2','3','4','5','6','7','8'].indexOf(f.destination) >= 0) {
      certOk = nonEmpty(f.certificate_url) || nonEmpty(f.certificate_local_path);
    }
    // 尾部：满意度+推荐
    let tailOk = true;
    if (['1','2','3','4','5','6','7','8'].indexOf(f.destination) >= 0) {
      tailOk = !!(nonEmpty(f.satisfaction) && nonEmpty(f.need_recommendation));
    } else if (f.destination === '9' || f.destination === '11') {
      tailOk = nonEmpty(f.need_recommendation);
    }
    // 其他意见或建议：所有分支都必填（无则填“无”）
    const feedbackOk = nonEmpty(f.feedback);
    this.setData({ canSubmit: baseOk && branchOk && certOk && tailOk && feedbackOk });
    this.saveFormCache();
  },

  async submitForm() {
    if (this.data.isSubmitting) return;
    // 防抖期可能尚未刷新 canSubmit，提交前强制同步校验一次
    if (this._checkTimer) { clearTimeout(this._checkTimer); this._checkTimer = null; }
    this.checkCanSubmit();
    const f = this.data.formData;
    const nonEmpty = (v) => v !== undefined && v !== null && String(v).trim() !== '';
    // 逐项提示
    if (!nonEmpty(f.student_name)) { this.showError('请选择本人姓名'); return; }
    if (!/^1[3-9]\d{9}$/.test(f.phone || '')) { this.showError('请输入正确的手机号'); return; }
    if (!nonEmpty(f.precise_service)) { this.showError('请选择是否精准服务'); return; }
    if (!nonEmpty(f.destination)) { this.showError('请选择毕业去向'); return; }
    const d = f.destination;
    if (d === '1') {
      if (!nonEmpty(f.contract_type)) { this.showError('请选择合同/协议签订情况'); return; }
      if (!nonEmpty(f.employment_channel)) { this.showError('请选择就业渠道'); return; }
      if (!nonEmpty(f.company_name)) { this.showError('请输入工作单位名称'); return; }
      if (!nonEmpty(f.work_province_city)) { this.showError('请选择单位所在省份/城市'); return; }
      if (!nonEmpty(f.work_address)) { this.showError('请输入单位详细地址'); return; }
      if (!nonEmpty(f.company_nature)) { this.showError('请选择单位性质'); return; }
      if (!nonEmpty(f.industry)) { this.showError('请选择所处行业'); return; }
      if (!nonEmpty(f.position_name)) { this.showError('请输入工作岗位'); return; }
      if (!nonEmpty(f.monthly_salary)) { this.showError('请填写当前月薪'); return; }
    } else if (d === '2') {
      if (!nonEmpty(f.military_office)) { this.showError('请输入征兵办公室全称'); return; }
    } else if (d === '3') {
      if (!nonEmpty(f.company_name)) { this.showError('请输入工作单位名称'); return; }
      if (!nonEmpty(f.work_province_city)) { this.showError('请选择单位所在省份/城市'); return; }
      if (!nonEmpty(f.work_address)) { this.showError('请输入单位详细地址'); return; }
      if (!nonEmpty(f.company_nature)) { this.showError('请选择单位性质'); return; }
      if (!nonEmpty(f.industry)) { this.showError('请选择所处行业'); return; }
      if (!nonEmpty(f.position_name)) { this.showError('请输入工作岗位'); return; }
      if (!nonEmpty(f.monthly_salary)) { this.showError('请填写当前月薪'); return; }
    } else if (d === '4') {
      if (!nonEmpty(f.industry)) { this.showError('请选择所处行业'); return; }
      if (!nonEmpty(f.position_name)) { this.showError('请输入工作岗位'); return; }
      if (!nonEmpty(f.monthly_salary)) { this.showError('请填写当前月薪'); return; }
    } else if (['5','6','7','8'].indexOf(d) >= 0) {
      if (!nonEmpty(f.education_level)) { this.showError('请选择升学层次'); return; }
      if (!nonEmpty(f.college_code)) { this.showError('请选择录取高校'); return; }
      if (!nonEmpty(f.major_code)) { this.showError('请选择录取专业'); return; }
      if (!nonEmpty(f.admission_score)) { this.showError('请输入录取分数'); return; }
    }
    if (['1','2','3','4','5','6','7','8'].indexOf(d) >= 0) {
      if (!nonEmpty(f.certificate_url) && !nonEmpty(f.certificate_local_path)) {
        this.showError('请上传就业凭证'); return;
      }
      if (!nonEmpty(f.satisfaction)) { this.showError('请选择对当前就业现状是否满意'); return; }
    }
    if (d !== '10') {
      if (!nonEmpty(f.need_recommendation)) { this.showError('请选择是否需要学校就业推荐'); return; }
    }
    if (!nonEmpty(f.feedback)) { this.showError('请填写其他意见或建议，如无请填“无”'); return; }
    if (!this.data.canSubmit) return;
    this.setData({ isSubmitting: true });

    // ★★ 新逻辑：先上传就业凭证，再提交表单；提交失败回滚刚上传的对象，避免 MinIO 孤儿。
    let justUploadedCertificateKey = null;
    try {
      // 只有当存在本地路径（即用户选了图但还没上传）时才走 upload；否则直接用已有 key。
      justUploadedCertificateKey = await this._uploadCertificateIfNeeded();
      // 二次确认：上传完成后 certificate_url 必须非空
      if (!nonEmpty(this.data.formData.certificate_url)) {
        this.setData({ isSubmitting: false });
        this.showError('请上传就业凭证');
        return;
      }
    } catch (uploadErr) {
      this.setData({ isSubmitting: false });
      this.showError(typeof uploadErr === 'string' ? uploadErr : (uploadErr && uploadErr.message) || '凭证上传失败');
      return;
    }

    try {
      // 只发后端需要的字段：剥离 certificate_local_path（前端预览用，不入库）。
      const payload = Object.assign({}, this.data.formData);
      delete payload.certificate_local_path;
      const res = await post('/grad_emp_survey/submit', payload, { loadingTitle: '提交中...' });
      if (res && res.success === false) {
        // 提交失败：回滚刚上传的凭证（best-effort）
        this._rollbackUploadedCertificate(justUploadedCertificateKey);
        this.setData({ isSubmitting: false });
        this.showError(res.msg || '提交失败');
        return;
      }
      this.setData({ isSubmitting: false });
      this.clearFormCache();

      // 提交成功，用自定义弹窗展示查询码
      const queryCode = res && res.query_code ? res.query_code : '';
      wx.hideLoading();
      this.setData({
        showSuccessModal: true,
        successQueryCode: queryCode
      });
    } catch (e) {
      // 提交失败：回滚刚上传的凭证（best-effort）
      this._rollbackUploadedCertificate(justUploadedCertificateKey);
      this.setData({ isSubmitting: false });
      this.showError(e || '提交失败');
    }
  },

  // ==================== 成功弹窗操作 ====================

  copySuccessQueryCode() {
    if (this.data.successQueryCode) {
      wx.setClipboardData({
        data: this.data.successQueryCode,
        success: () => {
          wx.showToast({ title: '已复制', icon: 'success' });
        }
      });
    }
  },

  closeSuccessModal() {
    this.setData({ showSuccessModal: false });
    wx.navigateBack();
  },

});
