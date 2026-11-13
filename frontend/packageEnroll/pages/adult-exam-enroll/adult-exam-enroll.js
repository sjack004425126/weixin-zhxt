const { createPage } = require('../../../utils/page-mixin');
const { post, get } = require('../../../utils/request');
const { parseCategoryHeader } = require('../../../utils/category-header');
const { resolveImageUrl } = require('../../../utils/image-url');
const { checkFeatureSwitch } = require('../../../utils/feature-switch');

createPage({
  data: {
    // 页面头部（来自后端 zs_category.extra_info）
    headerBadge: '',
    headerTitles: [],
    headerSubtitle: '',

    // 招生简章相关
    showProspectus: true,
    prospectusContent: '',
    processedProspectus: '',
    hasScrolledToBottom: false,
    scrollTop: 0,

    // 表单数据
    formData: {
      name: '',
      phone: '',
      major_code: '',
      learning_center_code: '',
      recruiter: ''
    },

    // 选择器数据
    majorList: [],
    majorIndex: -1,
    selectedMajorText: '',

    learningCenterList: [],
    learningCenterIndex: -1,
    selectedLearningCenterText: '',

    // 弹窗控制
    showMajorPopup: false,
    showLearningCenterPopup: false,
    showRecruiterPopup: false,

    // 招生老师选择
    recruiterList: [],
    filteredRecruiters: [],
    recruiterSearchKeyword: '',
    selectedAlphabet: '全部',
    alphabetList: ['全部','A','B','C','D','E','F','G','H','I','J','K','L','M','N','O','P','Q','R','S','T','U','V','W','X','Y','Z'],

    // 提交状态
    isSubmitting: false,
    canSubmit: false,

    // 查询码查询
    queryCodeInput: '',
    isQuerying: false,
    showQueryCodePopup: false,
    isEditMode: false,
    editRecordId: null,

    // 报名成功弹窗
    showSuccessModal: false,
    successQueryCode: '',

    // 焦点状态
    focusField: '',

    // 缓存 key 常量
    _cacheKey: 'adult_exam_enroll_form_cache'
  },

  onLoad(options) {
    checkFeatureSwitch('adult', this);
    this.restoreFormCache();
    this.loadProspectus();
    this.loadMajorList();
    this.loadLearningCenterList();
    this.loadRecruiterList();
  },

    // 缓存相关

  saveFormCache() {
    // 编辑模式下不缓存（查询码加载的数据是临时的）
    if (this.data.isEditMode) return;
    try {
      const cacheData = {
        formData: this.data.formData,
        selectedMajorText: this.data.selectedMajorText,
        selectedLearningCenterText: this.data.selectedLearningCenterText,
        timestamp: Date.now()
      };
      wx.setStorageSync(this.data._cacheKey, cacheData);
    } catch (e) {
      console.error('保存表单缓存失败', e);
    }
  },

  restoreFormCache() {
    try {
      const cache = wx.getStorageSync(this.data._cacheKey);
      if (!cache || !cache.formData) return;
      if (Date.now() - cache.timestamp > 7 * 24 * 60 * 60 * 1000) {
        wx.removeStorageSync(this.data._cacheKey);
        return;
      }
      this.setData({
        formData: cache.formData,
        selectedMajorText: cache.selectedMajorText || '',
        selectedLearningCenterText: cache.selectedLearningCenterText || ''
      }, () => {
        this.checkCanSubmit();
      });
    } catch (e) {
      console.error('恢复表单缓存失败', e);
    }
  },

  clearFormCache() {
    try {
      wx.removeStorageSync(this.data._cacheKey);
    } catch (e) {}
  },

  // 加载招生简章
  async loadProspectus() {
    try {
      const res = await get('/enrollment/prospectus?code=adult_exam', {
        showLoading: true,
        loadingTitle: '加载中...'
      });

      // 解析后端 extra_info 作为页面头部数据
      const header = parseCategoryHeader(res && res.extra_info);
      this.setData({
        headerBadge: header.headerBadge,
        headerTitles: header.headerTitles,
        headerSubtitle: header.headerSubtitle
      });

      if (res.prospectus) {
        const processedContent = this.processProspectusImages(res.prospectus);
        this.setData({
          prospectusContent: res.prospectus,
          processedProspectus: processedContent
        });
        
        // 延迟检查内容高度，如果内容不需要滚动则直接允许点击
        setTimeout(() => {
          this.checkContentHeight();
        }, 500);
      } else {
        // 如果没有招生简章，直接关闭弹窗
        this.setData({ showProspectus: false });
      }
    } catch (error) {
      this.showError(error);
      this.setData({ showProspectus: false });
    }
  },

  // 检查内容高度
  checkContentHeight() {
    const query = wx.createSelectorQuery();
    query.select('.modal-body').boundingClientRect();
    query.select('.prospectus-content').boundingClientRect();
    query.exec((res) => {
      if (res[0] && res[1]) {
        const containerHeight = res[0].height;
        const contentHeight = res[1].height;
        
        console.log('内容高度检查', {
          containerHeight,
          contentHeight,
          needScroll: contentHeight > containerHeight
        });
        
        // 如果内容高度小于等于容器高度，说明不需要滚动，直接允许点击
        if (contentHeight <= containerHeight) {
          this.setData({ hasScrolledToBottom: true });
        }
      }
    });
  },

  // 处理招生简章中的图片
  processProspectusImages(html) {
    if (!html) return '';
    
    let processed = html;

    // 提取所有图片URL用于预览
    const imgUrls = [];
    const imgRegex = /<img[^>]+src="([^"]+)"[^>]*>/gi;
    let match;
    while ((match = imgRegex.exec(html)) !== null) {
      imgUrls.push(resolveImageUrl(match[1]));
    }

    // 将HTML按<img>标签拆分为文本段和图片段，用于分段渲染（图片可点击预览）
    const segments = [];
    let lastIndex = 0;
    const imgSplitRegex = /<img[^>]+src="([^"]+)"[^>]*>/gi;
    let m;
    while ((m = imgSplitRegex.exec(html)) !== null) {
      if (m.index > lastIndex) {
        segments.push({ type: 'html', content: this._styleHtml(html.substring(lastIndex, m.index)) });
      }
      segments.push({ type: 'image', src: resolveImageUrl(m[1]) });
      lastIndex = m.index + m[0].length;
    }
    if (lastIndex < html.length) {
      segments.push({ type: 'html', content: this._styleHtml(html.substring(lastIndex)) });
    }

    this.setData({ prospectusImages: imgUrls, prospectusSegments: segments });

    // 返回完整处理后的HTML作为备用
    processed = this._styleHtml(processed);
    processed = processed.replace(
      /<img([^>]*)>/gi,
      '<img$1 style="max-width:100%;height:auto;display:block;margin:20rpx 0;border-radius:12rpx;">'
    );
    // 把所有 src 通过 resolveImageUrl 拼成完整 URL（已是绝对 URL 的会原样返回）
    processed = processed.replace(
      /src="([^"]*)"/gi,
      (_, p1) => `src="${resolveImageUrl(p1)}"`
    );
    return processed;
  },

  _styleHtml(html) {
    let p = html;
    p = p.replace(/<h1([^>]*)>/gi, '<h1$1 style="margin:32rpx 0 20rpx;font-weight:600;color:#333;font-size:34rpx;word-break:break-word;line-height:1.6;">');
    p = p.replace(/<h2([^>]*)>/gi, '<h2$1 style="margin:32rpx 0 20rpx;font-weight:600;color:#333;font-size:32rpx;word-break:break-word;line-height:1.6;">');
    p = p.replace(/<h3([^>]*)>/gi, '<h3$1 style="margin:32rpx 0 20rpx;font-weight:600;color:#333;font-size:30rpx;word-break:break-word;">');
    p = p.replace(/<p([^>]*)>/gi, '<p$1 style="margin:16rpx 0;text-indent:2em;line-height:1.8;">');
    p = p.replace(/<ul([^>]*)>/gi, '<ul$1 style="padding-left:40rpx;margin:16rpx 0;">');
    p = p.replace(/<ol([^>]*)>/gi, '<ol$1 style="padding-left:40rpx;margin:16rpx 0;">');
    p = p.replace(/<li([^>]*)>/gi, '<li$1 style="margin:8rpx 0;">');
    // 移除img标签（图片由原生image组件渲染）
    p = p.replace(/<img[^>]*>/gi, '');
    return '<div style="padding:0;overflow:hidden;word-break:break-word;">' + p + '</div>';
  },

  // 预览招生简章中的图片（点击图片全屏查看）
  onProspectusImageTap(e) {
    const src = e.currentTarget.dataset.src;
    const urls = this.data.prospectusImages || [];
    if (urls.length === 0) return;
    wx.previewImage({ current: src || urls[0], urls });
  },

  // 监听招生简章滚动
  onProspectusScroll(e) {
    const { scrollTop, scrollHeight } = e.detail;
    
    // 获取可视区域高度
    const query = wx.createSelectorQuery();
    query.select('.modal-body').boundingClientRect();
    query.exec((res) => {
      if (res[0]) {
        const clientHeight = res[0].height;
        // 判断是否滚动到底部（留25px容差，更宽松的判断）
        const isBottom = scrollTop + clientHeight >= scrollHeight - 25;
        
        if (isBottom && !this.data.hasScrolledToBottom) {
          console.log('已滚动到底部', {
            scrollTop,
            clientHeight,
            scrollHeight,
            total: scrollTop + clientHeight
          });
          this.setData({ hasScrolledToBottom: true });
        }
      }
    });
  },

  // 关闭招生简章弹窗
  closeProspectus() {
    if (!this.data.hasScrolledToBottom) {
      this.showError('请先阅读完整的招生简章');
      return;
    }
    this.setData({ showProspectus: false });
  },

  // 加载专业列表
  async loadMajorList() {
    try {
      const res = await get('/enrollment/dict_list?category_code=adult_exam&type=zyyx', {
        showLoading: false
      });

      // 按类型分组：高起专 / 专升本
      // 类型从专业名称末尾提取（"xxx高起专" 或 "xxx专升本"）
      const groupMap = {};
      res.forEach(item => {
        let extraData = {};
        try {
          extraData = item.extra_data ? JSON.parse(item.extra_data) : {};
        } catch (e) {
          console.error('解析专业扩展数据失败', e);
        }
        // 名称里包含"高起专"或"专升本"作为分类关键字
        let typeKey = '专升本';
        if (item.label.includes('高起专')) typeKey = '高起专';
        else if (item.label.includes('专升本')) typeKey = '专升本';
        else if (extraData.type === '高起专' || extraData.type === '专升本') typeKey = extraData.type;

        // 清洗后的纯专业名（去掉高起专/专升本后缀）
        const cleanName = item.label
          .replace(/(高起专|专升本)\s*$/, '')
          .trim();

        // 学制 + 费用 描述
        let displayText = item.label;
        if (extraData.tuition) {
          displayText += `（学制${extraData.duration || '2.5年'}，每年${extraData.tuition}元）`;
        }

        if (!groupMap[typeKey]) groupMap[typeKey] = [];
        groupMap[typeKey].push({
          ...item,
          label: cleanName,
          raw_label: item.label,
          display_text: displayText,
          remark: item.remark || extraData.remark || '',
          extra_data_obj: extraData
        });
      });

      // 排序：先高起专后专升本
      const ORDER = ['高起专', '专升本'];
      const groupedList = ORDER
        .filter(k => groupMap[k])
        .map(key => ({ label: key, majors: groupMap[key] }));

      this.setData({ majorList: groupedList });
    } catch (error) {
      this.showError(error);
    }
  },

  // 加载学习中心列表
  async loadLearningCenterList() {
    try {
      const res = await get('/enrollment/dict_list?category_code=adult_exam&type=xxzx', {
        showLoading: false
      });
      this.setData({ learningCenterList: res });
    } catch (error) {
      this.showError(error);
    }
  },

  // 输入框焦点控制
  onInputFocus(e) {
    const field = e.currentTarget.dataset.field;
    this.setData({ focusField: field });
  },

  onInputBlur() {
    this.setData({ focusField: '' });
  },

  // 姓名输入
  onNameInput(e) {
    this.setData({
      'formData.name': e.detail.value
    }, () => {
      this.checkCanSubmit();
    });
  },

  // 手机号输入
  onPhoneInput(e) {
    this.setData({
      'formData.phone': e.detail.value
    }, () => {
      this.checkCanSubmit();
    });
  },

  // 专业选择
  showMajorPopup() {
    this.setData({ showMajorPopup: true });
  },

  closeMajorPopup() {
    this.setData({ showMajorPopup: false });
  },

  onMajorSelect(e) {
    const code = e.detail;
    // majorList 是分组结构 [{label:'高起专', majors:[...]}, ...]，
    // 真正含 code 的是 group.majors，需要遍历分组找到对应专业
    let selectedMajor = null;
    for (const group of this.data.majorList) {
      const found = group.majors.find(m => m.code === code);
      if (found) {
        selectedMajor = found;
        break;
      }
    }

    if (selectedMajor) {
      this.setData({
        'formData.major_code': code,
        selectedMajorText: selectedMajor.display_text,
        showMajorPopup: false
      }, () => {
        this.checkCanSubmit();
      });
    }
  },

  onMajorCellClick(e) {
    const code = e.currentTarget.dataset.code;
    this.onMajorSelect({ detail: code });
  },

  // 学习中心选择
  showLearningCenterPopup() {
    this.setData({ showLearningCenterPopup: true });
  },

  closeLearningCenterPopup() {
    this.setData({ showLearningCenterPopup: false });
  },

  onLearningCenterSelect(e) {
    const code = e.detail;
    const center = this.data.learningCenterList.find(item => item.code === code);
    
    if (center) {
      this.setData({
        'formData.learning_center_code': code,
        selectedLearningCenterText: center.label,
        showLearningCenterPopup: false
      }, () => {
        this.checkCanSubmit();
      });
    }
  },

  onLearningCenterCellClick(e) {
    const code = e.currentTarget.dataset.code;
    this.onLearningCenterSelect({ detail: code });
  },

  // 检查是否可以提交（必填项）
  checkCanSubmit() {
    const { name, phone, major_code, learning_center_code } = this.data.formData;
    const canSubmit = !!(name && phone && major_code && learning_center_code);
    this.setData({ canSubmit });
    this.saveFormCache();
  },

  // 验证手机号
  validatePhone(phone) {
    const reg = /^1[3-9]\d{9}$/;
    return reg.test(phone);
  },

  // 招生老师输入
  onRecruiterInput(e) {
    this.setData({ 'formData.recruiter': e.detail.value }, () => this.checkCanSubmit());
  },

  // 加载招生老师列表
  async loadRecruiterList() {
    try {
      const res = await get('/enrollment/recruiter_list', { showLoading: false });
      this.setData({ recruiterList: res || [], filteredRecruiters: res || [] });
    } catch (e) {
      console.error('加载招生老师列表失败', e);
    }
  },

  showRecruiterPopup() {
    this.setData({ showRecruiterPopup: true, recruiterSearchKeyword: '', selectedAlphabet: '全部' });
    this.filterRecruiters();
  },

  closeRecruiterPopup() {
    this.setData({ showRecruiterPopup: false });
  },

  onRecruiterSearch(e) {
    this.setData({ recruiterSearchKeyword: e.detail.value, selectedAlphabet: '全部' });
    this.filterRecruiters();
  },

  clearRecruiterSearch() {
    this.setData({ recruiterSearchKeyword: '', selectedAlphabet: '全部' });
    this.filterRecruiters();
  },

  selectAlphabet(e) {
    this.setData({ selectedAlphabet: e.currentTarget.dataset.alphabet, recruiterSearchKeyword: '' });
    this.filterRecruiters();
  },

  filterRecruiters() {
    let list = this.data.recruiterList;
    if (this.data.selectedAlphabet !== '全部') {
      list = list.filter(t => t.firstLetter === this.data.selectedAlphabet);
    }
    if (this.data.recruiterSearchKeyword) {
      const kw = this.data.recruiterSearchKeyword.toLowerCase();
      list = list.filter(t => t.name.includes(kw) || t.pinyin.toLowerCase().includes(kw));
    }
    this.setData({ filteredRecruiters: list });
  },

  selectRecruiter(e) {
    const name = e.currentTarget.dataset.name;
    this.setData({ 'formData.recruiter': name, showRecruiterPopup: false }, () => this.checkCanSubmit());
  },

  // ==================== 查询码查询 ====================

  onQueryCodeInput(e) {
    this.setData({ queryCodeInput: (e.detail.value || '').toUpperCase() });
  },

  // 打开查询码弹窗
  openQueryCodePopup() {
    this.setData({
      showQueryCodePopup: true,
      queryCodeInput: '' // 清空上次的输入
    });
  },

  // 关闭查询码弹窗
  closeQueryCodePopup() {
    this.setData({
      showQueryCodePopup: false,
      queryCodeInput: '' // 关闭时清空输入
    });
  },

  async verifyQueryCode() {
    const code = this.data.queryCodeInput.trim();
    if (!code || code.length < 8) {
      this.showError('请输入至少8位查询码');
      return;
    }
    
    this.setData({ isQuerying: true });
    try {
      const res = await post('/enrollment_query/verify', { query_code: code }, { loadingTitle: '查询中...' });
      
      // 检查是否是本页面对应的表单类型
      if (res.form_type !== 'adult_exam') {
        this.showError('该查询码不属于成人教育报名，请在对应页面查询');
        return;
      }
      
      // 关闭弹窗
      this.closeQueryCodePopup();
      
      // 加载历史数据到表单
      const record = res.record;
      this.setData({
        isEditMode: true,
        editRecordId: res.record_id,
        showQueryInput: false,
        'formData.name': record.name || '',
        'formData.phone': record.phone || '',
        'formData.major_code': record.major_code || '',
        'formData.learning_center_code': record.learning_center_code || '',
        'formData.recruiter': record.recruiter || '',
      });
      
      // 尝试匹配选择器的显示文本
      if (record.major_code) {
        const major = this.data.majorList.find(item => {
          const fullCode = item.code;
          return record.major_code.includes(fullCode);
        });
        if (major) this.setData({ selectedMajorText: major.display_text, 'formData.major_code': major.code });
      }
      if (record.learning_center_code) {
        const center = this.data.learningCenterList.find(item => {
          return record.learning_center_code.includes(item.code);
        });
        if (center) this.setData({ selectedLearningCenterText: center.label, 'formData.learning_center_code': center.code });
      }
      
      this.checkCanSubmit();
      this.showSuccess('已加载报名信息，查询后仍可修改信息并重新提交');
    } catch (error) {
      this.showError(error);
    } finally {
      this.setData({ isQuerying: false });
    }
  },

  // ==================== 提交表单 ====================

  // 提交表单
  async submitForm() {
    if (!this.data.canSubmit || this.data.isSubmitting) {
      return;
    }

    const { name, phone, major_code, learning_center_code } = this.data.formData;

    // 验证姓名
    if (!name || name.trim().length === 0) {
      this.showError('请输入姓名');
      return;
    }

    // 验证手机号
    if (!this.validatePhone(phone)) {
      this.showError('请输入正确的手机号');
      return;
    }

    // 验证专业
    if (!major_code) {
      this.showError('请选择意向专业');
      return;
    }

    // 验证学习中心
    if (!learning_center_code) {
      this.showError('请选择学习中心');
      return;
    }

    this.setData({ isSubmitting: true });

    try {
      // 编辑模式：调用更新接口
      if (this.data.isEditMode && this.data.editRecordId) {
        const updateRes = await post('/enrollment_query/update/adult_exam', {
          query_code: this.data.queryCodeInput.trim().toUpperCase(),
          record_id: this.data.editRecordId,
          form_data: {
            name: name.trim(),
            phone: phone,
            major_code: major_code,
            learning_center_code: learning_center_code,
            recruiter: (this.data.formData.recruiter || '').trim(),
          }
        }, { loadingTitle: '保存中...' });
        
        this.setData({ isSubmitting: false });
        this.showSuccess('修改成功');
        this.clearFormCache();
        setTimeout(() => { wx.navigateBack(); }, 1500);
        return;
      }
      
      // 新报名模式
      // 获取微信用户信息
      const wxUserInfo = await this.getWxUserInfo();
      
      const submitData = {
        name: name.trim(),
        phone: phone,
        major_code: major_code,
        learning_center_code: learning_center_code,
        recruiter: (this.data.formData.recruiter || '').trim(),
        wx_openid: wxUserInfo.openid || '',
        wx_nickname: wxUserInfo.nickname || '',
        wx_headimgurl: wxUserInfo.headimgurl || ''
      };

      const res = await post('/enrollment/adult_submit', submitData, {
        loadingTitle: '提交中...'
      });

      this.setData({ isSubmitting: false });
      this.clearFormCache();
      
      // 报名成功，用自定义弹窗展示查询码（避免wx.showModal和wx.hideLoading时序冲突）
      const queryCode = res && res.query_code ? res.query_code : '';
      wx.hideLoading();
      this.setData({
        showSuccessModal: true,
        successQueryCode: queryCode
      });
    } catch (error) {
      this.setData({ isSubmitting: false });
      this.showError(error);
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

  // 获取微信用户信息
  async getWxUserInfo() {
    try {
      // 尝试从全局数据获取
      const app = getApp();
      if (app.globalData.userInfo) {
        return app.globalData.userInfo;
      }

      // 尝试从缓存获取
      const cachedInfo = wx.getStorageSync('wx_user_info');
      if (cachedInfo) {
        return cachedInfo;
      }

      return {
        openid: '',
        nickname: '',
        headimgurl: ''
      };
    } catch (e) {
      console.error('获取微信用户信息失败', e);
      return {
        openid: '',
        nickname: '',
        headimgurl: ''
      };
    }
  }
});
