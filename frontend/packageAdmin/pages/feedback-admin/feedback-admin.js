const { createPage } = require('../../../utils/page-mixin');
const { BASE_URL } = require('../../../utils/request');
const { feedbackGet, feedbackPost, feedbackUploadFile } = require('../../../utils/feedback-request');
const Dialog = require('@vant/weapp/dialog/dialog').default;

const FEEDBACK_AUTH_CACHE_KEY = 'feedback_auth_cache';

createPage({
  data: {
    baseUrl: BASE_URL,
    stats: {},
    statusLabels: {
      pending: '待受理', processing: '处理中', done: '已办结',
      rejected: '已驳回', cancelled: '已撤回'
    },
    userTypeLabels: {
      open_student: '开放学生', vocational_student: '中职学生',
      open_teacher: '开放教师', vocational_teacher: '中职教师',
      staff: '校内员工'
    },
    // 反馈人类型筛选选项
    reporterUserTypeOptions: [
      { value: 'open_student',       label: '开放学生' },
      { value: 'vocational_student', label: '中职学生' },
      { value: 'open_teacher',       label: '开放教师' },
      { value: 'vocational_teacher', label: '中职教师' },
      { value: 'staff',              label: '校内员工' }
    ],
    // ----- 主筛选（粘顶） -----
    activeStatus: 'pending',     // 状态Tab
    keyword: '',                 // 搜索框（标题/工单号/反馈人）
    // ----- 弹窗筛选（多选，点亮即选中） -----
    filterPanelVisible: false,
    // 2026-09-29：默认进入"维修地点"（常用放前面）
    fpActiveNav: 'location',     // 当前右侧内容：location | repairType
    fpNav: [
      { key: 'location',   label: '维修地点' },
      { key: 'repairType', label: '维修类型' }
    ],
    fpContentScrollTop: 0,        // 切换 nav 时把右侧 scroll 滚回顶部
    fpRepairTypeCodes: [],       // 多选（数组：提交后端用）
    fpRepairTypeSet: {},         // 多选（对象：渲染判定用，code -> true）
    fpRepairTypeCodesStr: '',    // 调试：拼接成字符串渲染
    fpRepairTypeSetStr: '',
    // 2026-09-29：地点筛选按 type_code 分组，组内 OR / 组间 AND
    //   - fpLocationByType: { '楼栋': ['宿舍A栋', '综合楼'], '楼层': ['1楼', '3楼'] }
    //   - fpLocationSet    : 渲染高亮用扁平 map: name -> true
    //   - fpLocationKwFlat : 后端用扁平字符串 '宿舍A栋,综合楼,1楼'（保兼容）
    //   - fpLocationKwsByType: 后端用结构化字符串 '楼栋:宿舍A栋,综合楼|楼层:1楼,3楼'
    fpLocationByType: {},        // {type_code: [name,...]}
    fpLocationSet: {},           // {name: true}
    fpLocationKwFlat: '',
    fpLocationKwsByType: '',
    fpLocationTotalCount: 0,     // 所有组选项总数（用于右上角 badge）
    fpLocationTypeCount: 0,      // 已选 type_code 个数（用于左侧 nav 高亮）
    fpLocationTypeSet: {},       // {type_code: true} 已选 type_code（仅展示用）
    fpFilterCount: 0,            // 已选筛选条件总数（Tab 行筛选按钮上的角标）
    // ----- 旧字段保留兼容（不渲染但 data 留着不报错） -----
    activeCategory: '',
    activeUrgency: '',
    activeRepairType: '',
    activeLocationId: null,
    activeLocationLabel: '',
    myParticipation: false,
    repairTypes: [],
    locationTypes: [],
    locationValuesByType: {},
    locationPickerVisible: false,
    locPickerType: '',
    locPickerOptions: [],
    items: [],
    page: 1,
    pageSize: 20,
    total: 0,
    loading: false,
    noMore: false,
    canViewSuggestion: false,   // 是否有权查看意见建议类工单

    // ---- 详情弹出层 ----
    detailShow: false,
    detailId: 0,
    detail: null,
    detailTimeline: [],
    detailSubmitting: false,
    detailForm: { remark: '', images: [], send_sms: true },
    actionLabels: {
      submit: '提交反馈', process: '开始处理', done: '处理完成',
      reject: '已驳回', cancel: '用户撤回', comment: '补充', delete: '管理员删除'
    },
  },

  onLoad() {
    if (!this._ensureLoggedIn()) return;
    // 校验权限
    feedbackGet('/feedback/admin/whitelist_check', {}, { showLoading: false })
      .then(res => {
        if (!res || !res.is_admin) {
          this.showError('无管理权限');
          setTimeout(() => wx.navigateBack(), 800);
          return;
        }
        this.setData({ canViewSuggestion: !!res.can_view_suggestion });
        this.loadStats();
        this.load(true);
        // 加载维修类型 + 地点树（供筛选使用，静默）
        this._loadFilters();
      })
      .catch((err) => {
        // 登录过期已由 feedback-request 处理跳转
        if (typeof err === 'string' && err.includes('过期')) return;
        this.showError('身份验证失败,请重新登录');
        setTimeout(() => wx.navigateBack(), 800);
      });
  },

  onShow() {
    // 仅静默刷新统计数字，不重置列表和滚动位置
    if (this.data.items.length > 0) this.loadStats();
  },

  /**
   * 检查反馈模块独立登录态；未登录或缓存已过期则清除并跳转 feedback-login
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

  /**
   * 跳转到反馈登录页，带回调地址
   */
  _redirectToLogin() {
    const redirect = encodeURIComponent('/packageAdmin/pages/feedback-admin/feedback-admin');
    wx.redirectTo({ url: `/packageAdmin/pages/feedback-login/feedback-login?redirect=${redirect}` });
  },

  onPullDownRefresh() {
    Promise.all([this.loadStats(), this.load(true)]).then(() => wx.stopPullDownRefresh());
  },

  // 趋势图已移除（后端 /feedback/admin/trend 接口仍保留，后台需要时再启用）

  onReachBottom() {
    if (!this.data.noMore && !this.data.loading) this.load(false);
  },

  async loadStats() {
    try {
      const r = await feedbackGet('/feedback/admin/stats', {}, { showLoading: false });
      this.setData({ stats: r });
    } catch (e) {}
  },

  onTabTap(e) {
    const v = e.currentTarget.dataset.value;
    if (v === this.data.activeStatus) return;
    this.setData({ activeStatus: v });
    this.load(true);
  },

  // ===== 弹窗筛选：仅维修类型 + 地点（多选，点亮即选中） =====
  openFilterPanel() {
    // 2026-09-29：默认进入"维修地点"
    this.setData({ filterPanelVisible: true, fpActiveNav: 'location', fpContentScrollTop: 0 });
  },
  closeFilterPanel() {
    this.setData({ filterPanelVisible: false });
  },
  resetFilterPanel() {
    this.setData({
      fpRepairTypeCodes: [],
      fpRepairTypeSet: {},
      fpRepairTypeCodesStr: '',
      fpRepairTypeSetStr: '',
      fpLocationByType: {},
      fpLocationSet: {},
      fpLocationKwFlat: '',
      fpLocationKwsByType: '',
      fpLocationTypeSet: {},
      fpLocationTotalCount: 0,
      fpLocationTypeCount: 0,
      fpFilterCount: 0,
      fpContentScrollTop: 0
    });
  },

  // 2026-09-29：筛选按钮上一键清除（不进入弹窗）。
  // - 清空所有筛选数据 + 重新拉列表
  // - catchtap 已阻断 openFilterPanel，不会打开弹窗
  clearFilterQuick() {
    this.resetFilterPanel();
    this.load(true);
  },
  onFpNavTap(e) {
    const key = e.currentTarget.dataset.key;
    if (!key || key === this.data.fpActiveNav) return;
    this.setData({ fpActiveNav: key, fpContentScrollTop: 0 });
  },

  // 多选 toggle：点亮即选中（12306 风格：实色高亮 + ✓）
  onFpRepairTypeToggle(e) {
    const code = e.currentTarget.dataset.code;
    const label = e.currentTarget.dataset.label;
    if (!code) return;
    const cur = this.data.fpRepairTypeCodes;
    const curSet = Object.assign({}, this.data.fpRepairTypeSet);
    const idx = cur.indexOf(code);
    if (idx >= 0) {
      const next = cur.filter(c => c !== code);
      delete curSet[code];
      this.setData({ fpRepairTypeCodes: next, fpRepairTypeSet: curSet, fpRepairTypeCodesStr: next.join('|'), fpRepairTypeSetStr: Object.keys(curSet).join('|'), fpFilterCount: next.length + this.data.fpLocationTotalCount });
    } else {
      const next = [...cur, code];
      curSet[code] = true;
      this.setData({ fpRepairTypeCodes: next, fpRepairTypeSet: curSet, fpRepairTypeCodesStr: next.join('|'), fpRepairTypeSetStr: Object.keys(curSet).join('|'), fpFilterCount: next.length + this.data.fpLocationTotalCount });
    }
  },
  onFpLocationToggle(e) {
    const type = e.currentTarget.dataset.type;
    const name = e.currentTarget.dataset.name;
    if (!name || !type) return;
    const byType = Object.assign({}, this.data.fpLocationByType || {});
    const set = Object.assign({}, this.data.fpLocationSet || {});
    const list = (byType[type] || []).slice();
    const idx = list.indexOf(name);
    if (idx >= 0) {
      list.splice(idx, 1);
      delete set[name];
    } else {
      list.push(name);
      set[name] = true;
    }
    if (list.length) byType[type] = list; else delete byType[type];
    // 重新派生
    const typeSet = {};
    let total = 0;
    Object.keys(byType).forEach(tc => { typeSet[tc] = true; total += byType[tc].length; });
    const kwFlat = [];
    Object.keys(byType).forEach(tc => { kwFlat.push(...byType[tc]); });
    const kwsByType = Object.keys(byType).map(tc => `${tc}:${byType[tc].join(',')}`).join('|');
    const filterCount = total + this.data.fpRepairTypeCodes.length;
    this.setData({
      fpLocationByType: byType,
      fpLocationSet: set,
      fpLocationTypeSet: typeSet,
      fpLocationTotalCount: total,
      fpLocationTypeCount: Object.keys(byType).length,
      fpLocationKwFlat: kwFlat.join(','),
      fpLocationKwsByType: kwsByType,
      fpFilterCount: filterCount
    });
  },

  // 应用筛选：合并到主查询 + 重新拉列表
  applyFilterPanel() {
    this.setData({ filterPanelVisible: false });
    this.load(true);
  },

  onMyParticipationTap() {
    this.setData({ myParticipation: !this.data.myParticipation });
    this.load(true);
  },

  // 拼装 query 给后端（弹窗筛选：仅 维修类型 + 地点）
  _buildFilterQuery() {
    const q = {
      status: this.data.activeStatus || '',
      keyword: this.data.keyword || ''
    };
    if (this.data.fpRepairTypeCodes.length) q.repair_type_codes = this.data.fpRepairTypeCodes.join(',');
    // 2026-09-29：按 type_code 分组的结构化串，'楼栋:宿舍A栋,综合楼|楼层:1楼,3楼'
    if (this.data.fpLocationKwsByType) q.location_dict_kws_by_type = this.data.fpLocationKwsByType;
    // 兼容旧后端：保留 location_dict_kws（仅名字段，组间 OR）。新后端优先用 by_type。
    if (this.data.fpLocationKwFlat) q.location_dict_kws = this.data.fpLocationKwFlat;
    return q;
  },

  onCatTap(e) {
    const cat = e.currentTarget.dataset.cat;
    // 无权限时禁止切换到意见建议 tab
    if (cat === 'suggestion' && !this.data.canViewSuggestion) {
      wx.showToast({ title: '暂无查看意见建议的权限', icon: 'none' });
      return;
    }
    // 已废弃：类型筛选改到弹窗（2026-09-28 v2）
    wx.showToast({ title: '请使用右上角"筛选"面板', icon: 'none' });
  },

  onUrgTap(e) {
    // 已废弃：紧急筛选改到弹窗
    wx.showToast({ title: '请使用右上角"筛选"面板', icon: 'none' });
  },

  // ===== 维修类型筛选（已废弃：改到弹窗） =====
  onRepairTypeTap(e) {
    wx.showToast({ title: '请使用右上角"筛选"面板', icon: 'none' });
  },

  // ===== 维修地点筛选（按 type_code 任意组合，2026-09-27 重构） =====
  openLocationPicker() {
    this.setData({ locationPickerVisible: true, locPickerType: '', locPickerOptions: [] });
  },
  closeLocationPicker() {
    this.setData({ locationPickerVisible: false });
  },
  onLocTypeTap(e) {
    const type_code = e.currentTarget.dataset.type;
    this.setData({
      locPickerType: type_code,
      locPickerOptions: this.data.locationValuesByType[type_code] || []
    });
  },
  onLocPickerSelect(e) {
    const name = e.currentTarget.dataset.name;
    if (!name) return;
    this.setData({ activeLocationLabel: name });
    this.closeLocationPicker();
    this._applyLocationFilter(name);
  },

  _applyLocationFilter(name) {
    // 2026-09-27 重构：后端不再按 location_id 精确筛选，统一写入 keyword 模糊匹配
    this.setData({ activeLocationLabel: name });
    // 把地点名合并进 keyword（如果 keyword 已有其他内容则覆盖，避免污染）
    this.setData({ keyword: name, activeLocationId: null });
    if (this._kwTimer) { clearTimeout(this._kwTimer); this._kwTimer = null; }
    this.load(true);
  },
  clearLocationFilter() {
    this.setData({ activeLocationId: null, activeLocationLabel: '', keyword: '' });
    this.load(true);
  },
  clearRepairTypeFilter() {
    this.setData({ activeRepairType: '' });
    this.load(true);
  },

  // ===== 加载维修类型 + 地点（按 type_code 分组） =====
  async _loadFilters() {
    // 两个字典接口独立加载，单个失败不影响另一个
    let repairTypes = [];
    let locationTypes = [];
    let locationValuesByType = {};

    // 1) 维修类型
    try {
      const bundle = await feedbackGet('/feedback/dict/bundle', {}, { showLoading: false, showError: false });
      repairTypes = (bundle && bundle.repair_types) || [];
      repairTypes.sort((a, b) => (a.sort_order || 0) - (b.sort_order || 0));
      // 调试：完整打印
      console.log('[filters] repair_types raw=', JSON.stringify(repairTypes));
    } catch (e) {
      console.warn('[filters] 维修类型字典加载失败:', e);
    }

    // 2) 地点
    try {
      const locBundle = await feedbackGet('/feedback/location/bundle', {}, { showLoading: false, showError: false });
      locationTypes = (locBundle && locBundle.types) || [];
      locationValuesByType = (locBundle && locBundle.values) || {};
      // 兜底：确保 values 里的值都是数组（避免 wxml .length 报错）
      locationTypes.forEach(t => {
        if (!Array.isArray(locationValuesByType[t.type_code])) {
          locationValuesByType[t.type_code] = [];
        }
      });
      // 2026-09-29：后端已按 sort_order 排序，前端只需尊重顺序（无需再手动 sort）
    } catch (e) {
      console.warn('[filters] 地点字典加载失败:', e);
    }

    this.setData({ repairTypes, locationTypes, locationValuesByType });
  },

  onKeywordChange(e) {
    const kw = e.detail || '';
    this.setData({ keyword: kw });
    // 防抖 400ms：输入停顿后自动搜索；空字符串也触发，等价于"清空筛选"
    if (this._kwTimer) clearTimeout(this._kwTimer);
    this._kwTimer = setTimeout(() => {
      this._kwTimer = null;
      this.load(true);
    }, 400);
  },

  // 兼容键盘"搜索"按钮：立即触发，清掉防抖
  onSearch() {
    if (this._kwTimer) { clearTimeout(this._kwTimer); this._kwTimer = null; }
    this.load(true);
  },

  async load(reset) {
    if (this.data.loading) return;
    this.setData({ loading: true });
    const page = reset ? 1 : this.data.page + 1;
    try {
      // 弹窗筛选：仅 维修类型 + 地点（多选）
      const q = this._buildFilterQuery();
      q.page = page;
      q.page_size = this.data.pageSize;
      const res = await feedbackGet('/feedback/admin/list', q, { showLoading: reset });
      const items = reset ? res.items : [...this.data.items, ...res.items];
      this.setData({
        items, page, total: res.total,
        noMore: items.length >= res.total
      });
    } catch (e) {
      this.showError(typeof e === 'string' ? e : '加载失败');
    } finally {
      this.setData({ loading: false });
    }
  },

  onTap(e) {
    const id = e.currentTarget.dataset.id;
    this.setData({
      detailId: id,
      detailShow: true,
      detail: null,
      detailTimeline: [],
      detailForm: { remark: '', images: [], send_sms: true }
    });
    this.loadDetail(id);
  },

  closeDetail() {
    this.setData({ detailShow: false });
  },

  async loadDetail(id) {
    try {
      const res = await feedbackGet(`/feedback/detail/${id}`);
      this.setData({
        detail: res.ticket,
        detailTimeline: res.timeline,
        'detailForm.remark': res.ticket.handle_remark || '',
        'detailForm.images': res.ticket.handle_images || []
      });
    } catch (e) {
      this.showError(typeof e === 'string' ? e : '加载失败');
    }
  },

  previewDetailImage(e) {
    const d = this.data.detail;
    const list = e.currentTarget.dataset.list === 'handle' ? d.handle_images : d.images;
    const i = e.currentTarget.dataset.index;
    wx.previewMedia({
      sources: list.map(it => ({ url: this.data.baseUrl + it.url, type: it.type === 'video' ? 'video' : 'image' })),
      current: i
    });
  },

  onPreviewDetailHandle(e) {
    const i = e.currentTarget.dataset.index;
    wx.previewMedia({
      sources: this.data.detailForm.images.map(it => ({ url: this.data.baseUrl + it.url, type: it.type === 'video' ? 'video' : 'image' })),
      current: i
    });
  },

  callDetailReporter() {
    const phone = this.data.detail && this.data.detail.reporter_phone;
    if (phone) wx.makePhoneCall({ phoneNumber: String(phone) });
  },

  onDetailRemarkInput(e) { this.setData({ 'detailForm.remark': e.detail.value }); },
  onDetailSmsChange(e) { this.setData({ 'detailForm.send_sms': e.detail }); },

  async onChooseDetailImage() {
    const remain = 6 - this.data.detailForm.images.length;
    if (remain <= 0) return;
    try {
      const res = await wx.chooseMedia({
        count: remain, mediaType: ['image', 'video'],
        sizeType: ['compressed'], sourceType: ['album', 'camera'],
        maxDuration: 60, camera: 'back'
      });
      const images = [...this.data.detailForm.images];
      for (const f of res.tempFiles) {
        const isVideo = f.fileType === 'video';
        if (isVideo && f.size > 30 * 1024 * 1024) { this.showError('视频不能超过30MB'); continue; }
        if (isVideo && f.duration > 60) { this.showError('视频时长不能超过60秒'); continue; }
        try {
          const data = await feedbackUploadFile({ url: '/feedback/upload', filePath: f.tempFilePath, name: 'file', loadingTitle: isVideo ? '视频上传中...' : '上传中...' });
          if (data && data.key) {
            const media = { key: data.key, url: data.url, type: data.type || (isVideo ? 'video' : 'image') };
            if (isVideo && f.thumbTempFilePath) {
              try {
                const poster = await feedbackUploadFile({ url: '/feedback/upload_poster', filePath: f.thumbTempFilePath, name: 'file', formData: { video_key: data.key }, showLoading: false });
                if (poster && poster.url) media.poster = poster.url;
              } catch (_) {}
            }
            images.push(media);
          }
        } catch (err) { this.showError(err.message || '上传失败'); }
      }
      this.setData({ 'detailForm.images': images });
    } catch (_) {}
  },

  async onRemoveDetailImage(e) {
    const i = e.currentTarget.dataset.index;
    const item = this.data.detailForm.images[i];
    if (!item) return;
    try { await feedbackPost('/feedback/delete_image', { key: item.key }, { showLoading: false }); } catch (_) {}
    const arr = [...this.data.detailForm.images];
    arr.splice(i, 1);
    this.setData({ 'detailForm.images': arr });
  },

  async _submitDetailHandle(status) {
    if (!this.data.detailForm.remark.trim()) { this.showError('请填写处理意见'); return; }
    this.setData({ detailSubmitting: true });
    try {
      const res = await feedbackPost('/feedback/admin/handle', {
        ticket_id: this.data.detailId, status,
        remark: this.data.detailForm.remark,
        images: this.data.detailForm.images.map(it => it.key || it),
        send_sms: this.data.detailForm.send_sms
      }, { loadingTitle: status === 'done' ? '办结中...' : '提交中...' });
      const smsTip = (status === 'done' && this.data.detailForm.send_sms && res && res.sms && res.sms.success) ? ' · 短信已提交' : '';
      this.showSuccess((status === 'done' ? '已办结' : '已标记处理中') + smsTip);
      this._updateListItemStatus(this.data.detailId, status);
      this.loadStats();
      setTimeout(() => this.loadDetail(this.data.detailId), 600);
    } catch (e) {
      this.showError(typeof e === 'string' ? e : '操作失败');
    } finally {
      this.setData({ detailSubmitting: false });
    }
  },

  onDetailProcess() { this._submitDetailHandle('processing'); },
  onDetailDone() {
    Dialog.confirm({
      title: '确认办结',
      message: this.data.detailForm.send_sms && this.data.detail && !this.data.detail.is_anonymous
        ? '办结后将向反馈人发送短信通知,确认?' : '确认完成办结?'
    }).then(() => this._submitDetailHandle('done')).catch(() => {});
  },

  onDetailReject() {
    wx.showModal({
      title: '驳回反馈', editable: true, placeholderText: '请填写驳回原因(至少2字)',
      confirmText: '确认驳回', confirmColor: '#FF4D4F',
      success: (m) => {
        if (m.confirm) {
          const reason = (m.content || '').trim();
          if (reason.length < 2) { this.showError('请填写驳回原因'); return; }
          this._doDetailReject(reason);
        }
      }
    });
  },

  async _doDetailReject(reason) {
    try {
      await feedbackPost('/feedback/admin/reject', { ticket_id: this.data.detailId, reason }, { loadingTitle: '提交中...' });
      this.showSuccess('已驳回');
      this._updateListItemStatus(this.data.detailId, 'rejected');
      this.loadStats();
      setTimeout(() => this.loadDetail(this.data.detailId), 600);
    } catch (e) { this.showError(typeof e === 'string' ? e : '操作失败'); }
  },

  onDetailDelete() {
    wx.showModal({
      title: '删除此反馈', content: '删除后将从所有列表和统计中移除,数据库保留备查。确定继续?',
      confirmText: '确认删除', confirmColor: '#FF4D4F', editable: true, placeholderText: '可填删除原因(选填)',
      success: (m) => { if (m.confirm) this._doDetailDelete((m.content || '').trim()); }
    });
  },

  async _doDetailDelete(reason) {
    try {
      await feedbackPost('/feedback/admin/delete', { ticket_id: this.data.detailId, reason }, { loadingTitle: '删除中...' });
      this.showSuccess('已删除');
      const items = this.data.items.filter(it => it.id !== this.data.detailId);
      this.setData({ items, detailShow: false });
      this.loadStats();
    } catch (e) { this.showError(typeof e === 'string' ? e : '删除失败'); }
  },

  _updateListItemStatus(id, status) {
    const items = this.data.items.map(it => it.id === id ? { ...it, status } : it);
    this.setData({ items });
  },

  // 快捷拨打反馈人电话(冒泡阻断,避免触发卡片跳转)
  onCallReporter(e) {
    const phone = e.currentTarget.dataset.phone;
    if (!phone) return;
    wx.makePhoneCall({ phoneNumber: String(phone) });
  }
});
