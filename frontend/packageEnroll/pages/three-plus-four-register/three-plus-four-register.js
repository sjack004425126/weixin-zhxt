const { createPage } = require('../../../utils/page-mixin');
const { post, get, uploadFile } = require('../../../utils/request');
const { parseCategoryHeader } = require('../../../utils/category-header');
const { resolveImageUrl } = require('../../../utils/image-url');
const { checkFeatureSwitch } = require('../../../utils/feature-switch');

createPage({
  data: {
    // 缓存相关
    _cacheKey: 'three_plus_four_form_cache',

    // 同意书参考模板图（存放在 MinIO 私有桶 zs/ 下，通过后端代理读取）
    consentTemplateUrl: resolveImageUrl('/photo/zs_image/zqtys.png'),

    // 页面头部（来自后端 zs_category.extra_info）
    headerBadge: '',
    headerTitles: [],
    headerSubtitle: '',

    // 招生简章相关
    showProspectus: true,
    prospectusContent: '',
    processedProspectus: '',
    hasScrolledToBottom: false,
    
    // 表单数据
    formData: {
      name: '',
      admission_ticket_no: '',
      gender: '',
      nation: '',
      id_card: '',
      junior_school_name: '',
      junior_school_county: '',
      is_qdn_graduate: null,
      household_type: '',
      household_province: '',
      household_city: '',
      household_district: '',
      household_address: '',
      residence_province: '',
      residence_city: '',
      residence_district: '',
      residence_address: '',
      phone: '',
      interview_car_plate: '',
      guardian_name: '',
      guardian_phone: '',
      guardian_relation: '',
      id_card_front_url: '',
      id_card_back_url: '',
      photo_url: '',
      consent_letter_url: '',
      is_confirmed: 0,
      signature_base64: ''
    },
    
    // 字典数据
    nationList: [],
    
    // 显示文本
    selectedGenderText: '',
    selectedNationText: '',
    selectedIsQdnGraduateText: '',
    selectedHouseholdTypeText: '',
    selectedGuardianRelationText: '',
    
    // 选择器数据
    genderList: [
      { code: 'male', label: '男' },
      { code: 'female', label: '女' }
    ],
    isQdnGraduateList: [
      { code: 1, label: '是' },
      { code: 0, label: '否' }
    ],
    householdTypeList: [
      { code: 'agricultural', label: '农业户口' },
      { code: 'non_agricultural', label: '非农户口' }
    ],
    guardianRelationList: [
      { code: 'father', label: '父亲' },
      { code: 'mother', label: '母亲' },
      { code: 'other', label: '其他' }
    ],
    
    // 地区选择
    householdRegion: ['贵州省', '黔东南苗族侗族自治州', '凯里市'],
    residenceRegion: ['贵州省', '黔东南苗族侗族自治州', '凯里市'],
    
    // 弹窗控制
    showGenderPopup: false,
    showNationPopup: false,
    showIsQdnGraduatePopup: false,
    showHouseholdTypePopup: false,
    showGuardianRelationPopup: false,
    showSignaturePopup: false,
    
    // 焦点状态
    focusField: '',
    
    // 提交状态
    isSubmitting: false,
    canSubmit: false,
    
    // 报名成功弹窗
    showSuccessModal: false,
    successQueryCode: '',
    successSerialNumber: '',
    
    // 查询码查询
    queryCodeInput: '',
    isQuerying: false,
    showQueryCodePopup: false,
    isEditMode: false,
    editRecordId: null,
    editQueryCode: '',
    errorField: '',
    
    // 进度步骤 (1-4)
    currentStep: 1
  },

  onLoad(options) {
    checkFeatureSwitch('34', this);
    this.restoreFormCache();
    this.loadProspectus();
    this.loadNationList();
  },

  // 缓存相关
  _cacheKey: 'three_plus_four_form_cache',

  saveFormCache() {
    // 编辑模式下不缓存（查询码加载的数据是临时的，不覆盖用户自己填写的缓存）
    if (this.data.isEditMode) return;
    try {
      const cacheData = {
        formData: this.data.formData,
        selectedGenderText: this.data.selectedGenderText,
        selectedNationText: this.data.selectedNationText,
        selectedIsQdnGraduateText: this.data.selectedIsQdnGraduateText,
        selectedHouseholdTypeText: this.data.selectedHouseholdTypeText,
        selectedGuardianRelationText: this.data.selectedGuardianRelationText,
        householdRegion: this.data.householdRegion,
        residenceRegion: this.data.residenceRegion,
        timestamp: Date.now()
      };
      const cacheKey = this._cacheKey || 'three_plus_four_form_cache';
      wx.setStorageSync(cacheKey, cacheData);
    } catch (e) {
      console.error('保存表单缓存失败', e);
    }
  },

  restoreFormCache() {
    try {
      const cacheKey = this._cacheKey || 'three_plus_four_form_cache';
      const cache = wx.getStorageSync(cacheKey);
      if (!cache || !cache.formData) return;
      // 7天过期
      if (Date.now() - cache.timestamp > 7 * 24 * 60 * 60 * 1000) {
        wx.removeStorageSync(this._cacheKey);
        return;
      }
      this.setData({
        formData: cache.formData,
        selectedGenderText: cache.selectedGenderText || '',
        selectedNationText: cache.selectedNationText || '',
        selectedIsQdnGraduateText: cache.selectedIsQdnGraduateText || '',
        selectedHouseholdTypeText: cache.selectedHouseholdTypeText || '',
        selectedGuardianRelationText: cache.selectedGuardianRelationText || '',
        householdRegion: cache.householdRegion || ['贵州省', '黔东南苗族侗族自治州', '凯里市'],
        residenceRegion: cache.residenceRegion || ['贵州省', '黔东南苗族侗族自治州', '凯里市']
      }, () => {
        this.checkCanSubmit();
      });
    } catch (e) {
      console.error('恢复表单缓存失败', e);
    }
  },

  clearFormCache() {
    try {
      const cacheKey = this._cacheKey || 'three_plus_four_form_cache';
      wx.removeStorageSync(cacheKey);
    } catch (e) {}
  },

  // 加载招生简章
  async loadProspectus() {
    try {
      const res = await get('/vocational34/prospectus', {
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
        
        setTimeout(() => {
          this.checkContentHeight();
        }, 500);
      } else {
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

    // 将HTML按<img>标签拆分为文本段和图片段
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

    // 返回完整处理后的HTML作为备用，把 <img src> 里的相对路径也拼上 BASE_URL
    processed = this._styleHtml(processed);
    processed = processed.replace(
      /<img([^>]*)>/gi,
      '<img$1 style="max-width:100%;height:auto;display:block;margin:20rpx 0;border-radius:12rpx;">'
    );
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
    
    const query = wx.createSelectorQuery();
    query.select('.modal-body').boundingClientRect();
    query.exec((res) => {
      if (res[0]) {
        const clientHeight = res[0].height;
        const isBottom = scrollTop + clientHeight >= scrollHeight - 25;
        
        if (isBottom && !this.data.hasScrolledToBottom) {
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

  // 加载民族列表
  async loadNationList() {
    try {
      const res = await get('/vocational34/dict_list?type=nation', {
        showLoading: false
      });
      this.setData({ nationList: res });
    } catch (error) {
      console.error('加载民族列表失败', error);
    }
  },

  // 户籍地址选择
  onHouseholdRegionChange(e) {
    const region = e.detail.value;
    this.setData({
      householdRegion: [region[0], region[1], region[2]],
      'formData.household_province': region[0] || '',
      'formData.household_city': region[1] || '',
      'formData.household_district': region[2] || ''
    }, () => {
      this.checkCanSubmit();
    });
  },

  // 实际居住地址选择
  onResidenceRegionChange(e) {
    const region = e.detail.value;
    this.setData({
      residenceRegion: [region[0], region[1], region[2]],
      'formData.residence_province': region[0] || '',
      'formData.residence_city': region[1] || '',
      'formData.residence_district': region[2] || ''
    }, () => {
      this.checkCanSubmit();
    });
  },

  // 性别选择
  showGenderPopup() {
    this.setData({ showGenderPopup: true });
  },

  closeGenderPopup() {
    this.setData({ showGenderPopup: false });
  },

  onGenderSelect(e) {
    const code = e.detail;
    const item = this.data.genderList.find(i => i.code === code);
    if (item) {
      this.setData({
        'formData.gender': code,
        selectedGenderText: item.label,
        showGenderPopup: false
      }, () => {
        this.checkCanSubmit();
      });
    }
  },

  onGenderCellClick(e) {
    const code = e.currentTarget.dataset.code;
    this.onGenderSelect({ detail: code });
  },

  // 民族选择
  showNationPopup() {
    this.setData({ showNationPopup: true });
  },

  closeNationPopup() {
    this.setData({ showNationPopup: false });
  },

  onNationSelect(e) {
    const code = e.detail;
    const item = this.data.nationList.find(i => i.code === code);
    if (item) {
      this.setData({
        'formData.nation': code,
        selectedNationText: item.label,
        showNationPopup: false
      }, () => {
        this.checkCanSubmit();
      });
    }
  },

  onNationCellClick(e) {
    const code = e.currentTarget.dataset.code;
    this.onNationSelect({ detail: code });
  },

  // 是否黔东南州应届毕业生选择
  showIsQdnGraduatePopup() {
    this.setData({ showIsQdnGraduatePopup: true });
  },

  closeIsQdnGraduatePopup() {
    this.setData({ showIsQdnGraduatePopup: false });
  },

  onIsQdnGraduateSelect(e) {
    const code = e.detail;
    const item = this.data.isQdnGraduateList.find(i => i.code === code);
    if (item) {
      this.setData({
        'formData.is_qdn_graduate': code,
        selectedIsQdnGraduateText: item.label,
        showIsQdnGraduatePopup: false
      }, () => {
        this.checkCanSubmit();
      });
    }
  },

  onIsQdnGraduateCellClick(e) {
    const code = e.currentTarget.dataset.code;
    this.onIsQdnGraduateSelect({ detail: code });
  },

  // 户口性质选择
  showHouseholdTypePopup() {
    this.setData({ showHouseholdTypePopup: true });
  },

  closeHouseholdTypePopup() {
    this.setData({ showHouseholdTypePopup: false });
  },

  onHouseholdTypeSelect(e) {
    const code = e.detail;
    const item = this.data.householdTypeList.find(i => i.code === code);
    if (item) {
      this.setData({
        'formData.household_type': code,
        selectedHouseholdTypeText: item.label,
        showHouseholdTypePopup: false
      }, () => {
        this.checkCanSubmit();
      });
    }
  },

  onHouseholdTypeCellClick(e) {
    const code = e.currentTarget.dataset.code;
    this.onHouseholdTypeSelect({ detail: code });
  },

  // 监护人身份选择
  showGuardianRelationPopup() {
    this.setData({ showGuardianRelationPopup: true });
  },

  closeGuardianRelationPopup() {
    this.setData({ showGuardianRelationPopup: false });
  },

  onGuardianRelationSelect(e) {
    const code = e.detail;
    const item = this.data.guardianRelationList.find(i => i.code === code);
    if (item) {
      this.setData({
        'formData.guardian_relation': code,
        selectedGuardianRelationText: item.label,
        showGuardianRelationPopup: false
      }, () => {
        this.checkCanSubmit();
      });
    }
  },

  onGuardianRelationCellClick(e) {
    const code = e.currentTarget.dataset.code;
    this.onGuardianRelationSelect({ detail: code });
  },

  // 输入框焦点控制
  onInputFocus(e) {
    const field = e.currentTarget.dataset.field;
    this.setData({ focusField: field });
  },

  onInputBlur() {
    this.setData({ focusField: '' });
  },

  // 输入框处理
  onInputChange(e) {
    const field = e.currentTarget.dataset.field;
    this.setData({
      [`formData.${field}`]: e.detail.value
    }, () => {
      this.checkCanSubmit();
    });
  },

  // 图片上传
  async chooseImage(e) {
    const field = e.currentTarget.dataset.field;
    
    try {
      const res = await wx.chooseImage({
        count: 1,
        sizeType: ['compressed'],
        sourceType: ['album', 'camera']
      });
      
      const tempFilePath = res.tempFilePaths[0];
      
      const data = await uploadFile({
        url: '/vocational34/upload_image',
        filePath: tempFilePath,
        name: 'file',
        showLoading: true,
        loadingTitle: '上传中...'
      });

      if (data && data.url) {
        // 后端返回相对路径（如 /photo/zs_image/xxx.jpg），在此拼接 BASE_URL，
        // 使内网用户/公网用户都走各自的 nginx 入口
        const fullUrl = resolveImageUrl(data.url);
        this.setData({
          [`formData.${field}`]: fullUrl
        }, () => {
          this.checkCanSubmit();
        });
        this.showSuccess('上传成功');
      } else {
        throw new Error('上传失败');
      }
    } catch (error) {
      console.error('上传失败', error);
      this.showError(error.errMsg || error.message || error || '上传失败');
    }
  },

  // 删除已上传图片
  deleteImage(e) {
    const field = e.currentTarget.dataset.field;
    wx.showModal({
      title: '提示',
      content: '确定要删除这张图片吗？',
      success: (res) => {
        if (res.confirm) {
          this.setData({
            [`formData.${field}`]: ''
          }, () => {
            this.checkCanSubmit();
          });
        }
      }
    });
  },

  // 预览模板图片
  previewTemplate(e) {
    const src = e.currentTarget.dataset.src;
    wx.previewImage({
      current: src,
      urls: [src]
    });
  },

  // 预览已上传的图片（全屏可放大）
  previewUploadedImage(e) {
    const src = e.currentTarget.dataset.src;
    if (!src) return;
    // 收集所有已上传的图片URL
    const f = this.data.formData;
    const allUrls = [f.id_card_front_url, f.id_card_back_url, f.photo_url, f.consent_letter_url].filter(Boolean);
    wx.previewImage({
      current: src,
      urls: allUrls.length > 0 ? allUrls : [src]
    });
  },

  // 删除签名
  deleteSignature() {
    wx.showModal({
      title: '提示',
      content: '确定要删除签名吗？',
      success: (res) => {
        if (res.confirm) {
          this.setData({
            'formData.signature_base64': ''
          }, () => {
            this.checkCanSubmit();
          });
        }
      }
    });
  },

  // 打开签名页面
  openSignature() {
    wx.navigateTo({
      url: '/packageOther/pages/signature-page/signature-page',
      events: {
        signatureDone: (data) => {
          this.setData({
            'formData.signature_base64': data.base64
          }, () => {
            this.checkCanSubmit();
            this.showSuccess('签名已保存');
          });
        }
      }
    });
  },

  noop() {},

  // 检查是否可以提交（所有字段均为必填）
  checkCanSubmit() {
    const f = this.data.formData;

    // 编辑模式下：所有数据已从后端加载，直接允许提交
    if (this.data.isEditMode) {
      const basicDone = !!(f.name && f.id_card && f.phone);
      this.setData({ canSubmit: basicDone });
      return;
    }

    // 基本信息（卡片1）
    const basicDone = !!(
      f.name && f.admission_ticket_no && f.gender && f.nation && f.id_card &&
      f.junior_school_name && f.junior_school_county && (f.is_qdn_graduate === 0 || f.is_qdn_graduate === 1)
    );
    // 籍贯与联系（卡片2）
    const contactDone = basicDone && !!(
      f.household_type &&
      f.household_province && f.household_city && f.household_district && f.household_address &&
      f.residence_province && f.residence_city && f.residence_district && f.residence_address &&
      f.phone && f.interview_car_plate
    );
    // 监护人信息（卡片3）
    const guardianDone = contactDone && !!(f.guardian_name && f.guardian_phone && f.guardian_relation);
    // 证件照片（卡片4）
    const photoDone = guardianDone && !!(f.id_card_front_url && f.id_card_back_url && f.photo_url && f.consent_letter_url);
    // 确认与签名（卡片5）
    const finalDone = photoDone && !!(f.is_confirmed && f.signature_base64);

    const canSubmit = finalDone;

    // 计算进度步骤
    let step = 1;
    if (finalDone) step = 4;
    else if (photoDone) step = 4;
    else if (guardianDone) step = 4;
    else if (contactDone) step = 3;
    else if (basicDone) step = 2;
    else step = 1;

    this.setData({ canSubmit, currentStep: step });
    this.saveFormCache();
  },

  // 知情确认
  onConfirmChange(e) {
    const checked = typeof e.detail === 'boolean' ? e.detail : !!e.detail.value;
    this.setData({
      'formData.is_confirmed': checked ? 1 : 0
    }, () => {
      this.checkCanSubmit();
    });
  },

  // 验证身份证号
  validateIdCard(idCard) {
    const reg = /(^\d{15}$)|(^\d{18}$)|(^\d{17}(\d|X|x)$)/;
    return reg.test(idCard);
  },

  // 验证手机号
  validatePhone(phone) {
    const reg = /^1[3-9]\d{9}$/;
    return reg.test(phone);
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
      
      if (res.form_type !== 'vocational_34') {
        this.showError('该查询码不属于3+4报名，请在对应页面查询');
        return;
      }
      
      // 关闭弹窗
      this.closeQueryCodePopup();
      
      // 加载历史数据到表单
      const record = res.record;
      this.setData({
        isEditMode: true,
        editRecordId: res.record_id,
        editQueryCode: code,
        'formData.name': record.name || '',
        'formData.admission_ticket_no': record.admission_ticket_no || '',
        'formData.gender': record.gender || '',
        'formData.nation': record.nation || '',
        'formData.id_card': record.id_card || '',
        'formData.junior_school_name': record.junior_school_name || '',
        'formData.junior_school_county': record.junior_school_county || '',
        'formData.is_qdn_graduate': record.is_qdn_graduate,
        'formData.household_type': record.household_type || '',
        'formData.household_province': record.household_province || '',
        'formData.household_city': record.household_city || '',
        'formData.household_district': record.household_district || '',
        'formData.household_address': record.household_address || '',
        'formData.residence_province': record.residence_province || '',
        'formData.residence_city': record.residence_city || '',
        'formData.residence_district': record.residence_district || '',
        'formData.residence_address': record.residence_address || '',
        'formData.phone': record.phone || '',
        'formData.interview_car_plate': record.interview_car_plate || '',
        'formData.guardian_name': record.guardian_name || '',
        'formData.guardian_phone': record.guardian_phone || '',
        'formData.guardian_relation': record.guardian_relation || '',
        'formData.id_card_front_url': record.id_card_front_url || '',
        'formData.id_card_back_url': record.id_card_back_url || '',
        'formData.photo_url': record.photo_url || '',
        'formData.consent_letter_url': record.consent_letter_url || '',
        'formData.signature_base64': record.signature_base64 || '',
        'formData.is_confirmed': record.is_confirmed || 1,
      });
      
      // 触发表单完整性检查，更新进度条和canSubmit状态
      this.checkCanSubmit();
      // 编辑模式跳到最后一步确认
      this.setData({ currentStep: 4 });
      
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
    if (!this.data.isEditMode && !this.data.canSubmit) {
      return;
    }
    if (this.data.isSubmitting) {
      return;
    }

    const formData = this.data.formData;

    // 验证必填项（所有字段均为必填）
    const trim = (v) => (typeof v === 'string' ? v.trim() : v);
    const requiredText = [
      ['name', '请输入学生姓名'],
      ['admission_ticket_no', '请输入准考证号'],
      ['gender', '请选择性别'],
      ['nation', '请选择民族'],
      ['id_card', '请输入身份证号'],
      ['junior_school_name', '请输入原初中毕业学校全称'],
      ['junior_school_county', '请输入原初中毕业学校所在县份'],
      ['household_type', '请选择户口性质'],
      ['household_province', '请选择户籍地址'],
      ['household_city', '请选择户籍地址'],
      ['household_district', '请选择户籍地址'],
      ['household_address', '请输入户籍详细地址'],
      ['residence_province', '请选择实际居住地址'],
      ['residence_city', '请选择实际居住地址'],
      ['residence_district', '请选择实际居住地址'],
      ['residence_address', '请输入实际居住详细地址'],
      ['phone', '请输入手机号'],
      ['interview_car_plate', '请填写面试当天是否驾车及车牌信息（不驾车请填“无”）'],
      ['guardian_name', '请输入监护人姓名'],
      ['guardian_phone', '请输入监护人手机号'],
      ['guardian_relation', '请选择监护人身份'],
      ['id_card_front_url', '请上传身份证正面照'],
      ['id_card_back_url', '请上传身份证反面照'],
      ['photo_url', '请上传标准证件照'],
      ['consent_letter_url', '请上传监护人知情同意书'],
      ['signature_base64', '请完成考生签名']
    ];
    for (const [key, msg] of requiredText) {
      const v = trim(formData[key]);
      if (v === '' || v === null || v === undefined) {
        // 编辑模式下，图片和签名字段如果为空则跳过（用户可能没重新上传）
        if (this.data.isEditMode && ['id_card_front_url', 'id_card_back_url', 'photo_url', 'consent_letter_url', 'signature_base64'].includes(key)) {
          continue;
        }
        this.setData({ errorField: key });
        this.showError(msg);
        return;
      }
    }
    this.setData({ errorField: '' });
    if (formData.is_qdn_graduate === null || formData.is_qdn_graduate === undefined || formData.is_qdn_graduate === '') {
      this.setData({ errorField: 'is_qdn_graduate' });
      this.showError('请选择是否黔东南州应届初中毕业生');
      return;
    }

    if (!this.validateIdCard(formData.id_card)) {
      this.showError('请输入正确的身份证号');
      return;
    }

    if (!this.validatePhone(formData.phone)) {
      this.showError('请输入正确的手机号');
      return;
    }

    if (!this.validatePhone(formData.guardian_phone)) {
      this.showError('请输入正确的监护人手机号');
      return;
    }

    if (!this.data.isEditMode && !formData.is_confirmed) {
      this.showError('请确认已阅读知情确认');
      return;
    }

    this.setData({ isSubmitting: true });

    try {
      // 编辑模式：调用更新接口
      if (this.data.isEditMode && this.data.editRecordId) {
        const updateData = { ...formData };
        // 编辑模式不需要重新上传图片和签名（如果用户没改）
        const updateRes = await post('/enrollment_query/update/vocational_34', {
          query_code: this.data.editQueryCode,
          record_id: this.data.editRecordId,
          form_data: updateData
        }, { loadingTitle: '保存中...' });
        
        wx.hideLoading();
        this.setData({ isSubmitting: false });
        this.showSuccess('修改成功');
        this.clearFormCache();
        setTimeout(() => { wx.navigateBack(); }, 1500);
        return;
      }

      // 新报名模式
      const wxUserInfo = await this.getWxUserInfo();
      
      const submitData = {
        ...formData,
        name: formData.name.trim(),
        wx_openid: wxUserInfo.openid || '',
        wx_nickname: wxUserInfo.nickname || '',
        wx_headimgurl: wxUserInfo.headimgurl || ''
      };

      const res = await post('/vocational34/submit', submitData, {
        loadingTitle: '提交中...'
      });

      this.setData({ isSubmitting: false });
      this.clearFormCache();
      
      // 报名成功，展示查询码
      const queryCode = res && res.query_code ? res.query_code : '';
      wx.hideLoading();
      this.setData({
        showSuccessModal: true,
        successQueryCode: queryCode,
        successSerialNumber: res && res.serial_number ? res.serial_number : ''
      });
      
      // 重置表单
      this.setData({
        formData: {
          name: '', admission_ticket_no: '', gender: '', nation: '',
          id_card: '', junior_school_name: '', junior_school_county: '',
          is_qdn_graduate: null, household_type: '',
          household_province: '', household_city: '', household_district: '',
          household_address: '', residence_province: '', residence_city: '',
          residence_district: '', residence_address: '', phone: '',
          interview_car_plate: '',
          guardian_name: '', guardian_phone: '', guardian_relation: '',
          id_card_front_url: '', id_card_back_url: '', photo_url: '',
          consent_letter_url: '', is_confirmed: 0, signature_base64: ''
        },
        selectedGenderText: '',
        selectedNationText: '',
        selectedIsQdnGraduateText: '',
        selectedHouseholdTypeText: '',
        selectedGuardianRelationText: '',
        canSubmit: false
      });
    } catch (error) {
      this.setData({ isSubmitting: false });
      this.showError(error);
    }
  },

  // 获取微信用户信息
  async getWxUserInfo() {
    try {
      const app = getApp();
      if (app.globalData.userInfo) {
        return app.globalData.userInfo;
      }

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
  },

  // ==================== 成功弹窗操作 ====================

  copySuccessQueryCode() {
    if (this.data.successQueryCode) {
      wx.setClipboardData({
        data: this.data.successQueryCode,
        success: () => {
          wx.showToast({ title: '已复制', icon: 'success' });
          setTimeout(() => {
            this.setData({ showSuccessModal: false });
            wx.reLaunch({ url: '/pages/home/home' });
          }, 800);
        }
      });
    }
  },

  closeSuccessModal() {
    this.setData({ showSuccessModal: false });
  }
});
