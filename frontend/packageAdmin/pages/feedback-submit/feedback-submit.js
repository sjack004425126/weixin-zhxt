const { createPage } = require('../../../utils/page-mixin');
const { BASE_URL } = require('../../../utils/request');
const { feedbackGet, feedbackPost, feedbackUploadFile } = require('../../../utils/feedback-request');
const { checkFeatureSwitch } = require('../../../utils/feature-switch');

// =====================================================================
// MinIO 反馈附件存储约定（与后端 services/minio_service.py 对齐）
// ---------------------------------------------------------------------
// 桶：zhxt（统一桶；原公有对象已按私有处理，经后端代理/SigV4 访问）
// 路径前缀：hq/feedback/<uuid>.<ext>
// 上传入口：FastAPI POST /feedback/upload（由 nginx 80 → 3050 反代）
// 访问 URL：后端 SigV4 预签名 /object/zhxt/hq/feedback/<uuid>.<ext>?X-Amz-...
// =====================================================================
const FEEDBACK_AUTH_CACHE_KEY = 'feedback_auth_cache';

// 字典缓存：场景/物品 + 维修类型 + 地点树
const DICT_CACHE_KEY = 'feedback_dict_cache_v2';
const DICT_CACHE_TTL = 24 * 60 * 60 * 1000; // 24 小时

createPage({
  data: {
    baseUrl: BASE_URL,
    // 维修类型列表
    repairTypeOptions: [],
    // 地点字典（2026-09-27 重构：扁平 + 任意 type_code）
    locationTypes: [],
    locationValuesByType: {},
    // 2026-09-28：按显示顺序排好的 type_code 列表（先楼栋→楼层→房间号…）
    orderedLocationTypes: [],

    dictLoading: true,

    userInfo: { name: '', user_type: '' },
    userTypeLabel: '',
    userTypeIcon: 'user-o',
    isAdmin: false,
    adminRoleLabel: '',

    submitting: false,
    // 2026-09-28：派生值，用于控制"地点备注"卡片是否显示
    hasLocationCustom: false,
    showLocRemark: false,
    // 2026-09-28：textarea 字数统计（避免 WXML 用 (form.x || '').length 这种不支持的表达式）
    locationTextLen: 0,
    locationDictTextLen: 0,
    contentLen: 0,
    form: {
      category: 'repair',
      // 维修类型（维修类优先使用）
      // 仅保留 repair_type_code（前端用来查字典 label 展示）和
      // repair_type_text（真正提交到后端的字段）。repair_type_label 不再使用。
      repair_type_code: '',
      // 2026-09-28：维修类型用户手动输入（避开字典不全）
      repair_type_text_custom: '',
      // 维修地点
      // 2026-09-28 方案 C：双列独立。
      //   - location_dict_text：列表段（仅 chip 拼接，'|' 分隔）。例：'10楼|宿舍楼A|102教室讲台'
      //   - location_user_text：备注段（仅用户手写，自由文本）
      //   - location_text    ：WXML 里只用它做展示（后端生成的合并展示串），不需要前端写。
      location_text: '',
      location_dict_text: '',
      location_user_text: '',
      // 2026-09-28 修复：独立存 selectedByType（不再依赖 location_dict_text 反推——避免 type_code 丢失）
      // 结构：{ '楼栋': '宿舍楼A', '楼层': '3楼' }
      location_dict_selected: {},
      // 2026-09-28：用于 WXML 高亮查找的扁平 map（key = `${type_code}-${name}`，value = true）
      // 之所以单独存，是因为 WXML 不支持函数调用表达式（如 isLocSelected(type, name)），
      // 必须用纯属性查找 + 字符串拼接才能命中 chip-active。
      location_chip_selected: {},
      // 2026-09-28：用户手动输入过的 type_code 集合。这些 type_code 不允许 chips 覆盖（保留用户的选择）
      location_manual_types: [],
      // 2026-09-28：每个 type_code 的手动输入值（如 '楼层' 输入 '三层半'）
      location_custom: {},
      // 公共字段
      content: '',
      images: [],
      urgency: 'normal',
      is_anonymous: false
    },
  },

  onLoad() {
    if (!this._ensureLoggedIn()) return;
    checkFeatureSwitch('feedback', this);
    this._applyIdentity();
    this._loadDict();
  },

  onShow() {
    if (this.data.userInfo && this.data.userInfo.name) {
      this._refreshAdminStatus();
    }
  },

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

  _redirectToLogin() {
    const redirect = encodeURIComponent('/packageAdmin/pages/feedback-submit/feedback-submit');
    wx.redirectTo({ url: `/packageAdmin/pages/feedback-login/feedback-login?redirect=${redirect}` });
  },

  _applyIdentity() {
    const cached = wx.getStorageSync(FEEDBACK_AUTH_CACHE_KEY) || {};
    const identity = cached.identity || {};
    const LABEL_MAP = {
      staff: { label: '工作人员', icon: 'manager-o' },
      open_teacher: { label: '开放教师', icon: 'manager-o' },
      vocational_teacher: { label: '中职教师', icon: 'manager-o' },
      open_student: { label: '开放学生', icon: 'friends-o' },
      vocational_student: { label: '中职学生', icon: 'friends-o' }
    };
    const meta = LABEL_MAP[identity.user_type] || { label: '用户', icon: 'user-o' };
    this.setData({
      userInfo: {
        name: identity.name || '',
        user_type: identity.user_type || '',
        phone: identity.phone || ''
      },
      userTypeLabel: meta.label,
      userTypeIcon: meta.icon,
      isAdmin: !!cached.is_admin,
      adminRoleLabel: cached.admin_role_label || ''
    });
  },

  _refreshAdminStatus() {
    feedbackGet('/feedback/auth/me', {}, { showLoading: false, showError: false })
      .then(res => {
        if (!res) return;
        const cached = wx.getStorageSync(FEEDBACK_AUTH_CACHE_KEY) || {};
        cached.is_admin = !!res.is_admin;
        cached.admin_role = res.admin_role || '';
        cached.admin_role_label = res.admin_role_label || '';
        wx.setStorageSync(FEEDBACK_AUTH_CACHE_KEY, cached);
        this.setData({
          isAdmin: !!res.is_admin,
          adminRoleLabel: res.admin_role_label || ''
        });
      })
      .catch((err) => {
        if (typeof err === 'string' && err.includes('过期')) {
          wx.removeStorageSync(FEEDBACK_AUTH_CACHE_KEY);
          this._redirectToLogin();
        }
      });
  },

  // ===== 字典加载（维修类型 + 地点字典） =====
  _loadDict() {
    const cached = wx.getStorageSync(DICT_CACHE_KEY);
    if (cached && cached.expireTime > Date.now() && cached.locationTypes) {
      this._applyDict(cached.repairTypes || [], cached.locationTypes || [], cached.locationValuesByType || {});
      this._fetchDict(true);  // 后台静默刷新
      return;
    }
    this._fetchDict(false);
  },

  async _fetchDict(silent) {
    const showLoading = !silent;
    try {
      // 一次性拉 字典 + 地点（按 type_code 分组）（并行）
      const [bundle, locBundle, treeRes] = await Promise.all([
        feedbackGet('/feedback/dict/bundle', {}, {
          showLoading,
          showError: !silent,
          loadingTitle: '加载中...'
        }),
        feedbackGet('/feedback/location/bundle', {}, {
          showLoading: false,
          showError: false
        }),
        feedbackGet('/feedback/location/tree', {}, {
          showLoading: false,
          showError: false
        })
      ]);
      const repairTypes = (bundle && bundle.repair_types) || [];
      // 2026-09-27：bundle 优先；缺失则回退 tree
      let locationTypes = (locBundle && locBundle.types) || [];
      let locationValuesByType = (locBundle && locBundle.values) || {};
      if (!locationTypes.length && treeRes && treeRes.list) {
        // 从扁平列表聚合
        const tcSet = {};
        treeRes.list.forEach(n => {
          const tc = n.type_code || '未分类';
          if (!tcSet[tc]) tcSet[tc] = { type_code: tc, count: 0, sort_order: n.sort_order || 0 };
          tcSet[tc].count += 1;
          locationValuesByType[tc] = locationValuesByType[tc] || [];
          locationValuesByType[tc].push(n);
        });
        locationTypes = Object.values(tcSet).sort((a, b) => a.sort_order - b.sort_order);
      }
      wx.setStorageSync(DICT_CACHE_KEY, {
        repairTypes, locationTypes, locationValuesByType,
        expireTime: Date.now() + DICT_CACHE_TTL
      });
      this._applyDict(repairTypes, locationTypes, locationValuesByType);
    } catch (e) {
      // 失败兜底
      if (!this.data.repairTypeOptions.length) {
        this._applyDict([], [], {});
      }
      this.setData({ dictLoading: false });
    }
  },

  _applyDict(repairTypes, locationTypes, locationValuesByType) {
    const repairTypeOptions = (repairTypes || [])
      .slice()
      .sort((a, b) => (a.sort_order || 0) - (b.sort_order || 0))
      .map(it => ({ code: it.code, label: it.label, group: (it.extra_data && it.extra_data.group) || '' }));

    // 2026-09-28 重构：去掉写死的 TYPE_RANK 兜底，直接按后端返回的 sort_order 全局排序。
    // 后端 /feedback/location/bundle 已经按 (sort_order, type_code) 排序传过来，
    // 前端就尊重这个顺序——sort_order 数字小的 type 排前面。
    const orderedLocationTypes = (locationTypes || [])
      .slice()
      .sort((a, b) => {
        const sa = (a.sort_order || 0);
        const sb = (b.sort_order || 0);
        if (sa !== sb) return sa - sb;
        return (a.type_code || '').localeCompare(b.type_code || '');
      })
      .map(t => ({
        ...t,
        // 2026-09-28：wx:if 不支持 (a || b).length 这种 JS 表达式，
        // 在这里把"这个 type_code 下是否有 chip"算成字段，模板里直接用 loc.hasChips
        hasChips: Array.isArray(locationValuesByType[t.type_code]) && locationValuesByType[t.type_code].length > 0
      }));
    const hasLocationDict = !!(locationTypes && locationTypes.length);

    this.setData({
      dictLoading: false,
      repairTypeOptions,
      locationTypes: locationTypes || [],
      locationValuesByType: locationValuesByType || {},
      orderedLocationTypes,
      hasLocationDict
    });
  },

  // ===== 分类切换 =====
  onCategoryTap(e) {
    const cat = e.currentTarget.dataset.cat;
    this.setData({
      'form.category': cat,
      // 清空跨类的字段
      'form.repair_type_code': '',
      'form.repair_type_text': '',
      'form.repair_type_text_custom': '',
      'form.location_text_fuzzy': '',
      'form.location_parts': [],
      'form.location_custom': {},
      // 2026-09-28 方案 C：地点三字段都重置
      'form.location_text': '',
      'form.location_dict_text': '',
      'form.location_user_text': '',
      'form.location_dict_selected': {},
      'form.location_chip_selected': {},
      'form.location_manual_types': [],
      // 2026-09-28：WXML 不支持 (xxx || '').length，把字符串长度算成 data 字段
      locationTextLen: 0,
      locationDictTextLen: 0
    });
    if (cat === 'repair') {
      this.setData({ 'form.is_anonymous': false });
    } else {
      this.setData({ 'form.urgency': 'normal' });
    }
    // 重新计算 hasLocationCustom（用于显示"地点备注"卡片）
    // 显式传 category：setData 是异步的，直接读 this.data.form.category 可能是旧值
    this._recomputeLocationDerived(cat);
  },

  // 2026-09-28：textarea 字数统计。
  // WXML 不支持 (form.x || '').length 这种表达式，必须在 JS 里算成 data 字段
  _updateLocationLengths() {
    const f = this.data.form || {};
    const tl = (f.location_text || '').length;
    const dl = (f.location_dict_text || '').length;
    if (this.data.locationTextLen !== tl || this.data.locationDictTextLen !== dl) {
      this.setData({ locationTextLen: tl, locationDictTextLen: dl });
    }
  },

  _recomputeLocationDerived(categoryOverride) {
    const f = this.data.form;
    const category = categoryOverride || f.category;
    const dictText = (f.location_dict_text || '').trim();
    const userText = (f.location_text || '').trim();
    const hasText = !!(dictText || userText);
    // 2026-09-28：维修类下"地点备注"框常驻，用户随时可编辑（chips 只是辅助拼接）
    const showLocRemark = category === 'repair';
    const hasLocationCustom = hasText;
    const changed = this.data.hasLocationCustom !== hasLocationCustom
      || this.data.showLocRemark !== showLocRemark
      || this.data.locationTextLen !== (f.location_text || '').length
      || this.data.locationDictTextLen !== (f.location_dict_text || '').length;
    if (changed) {
      this.setData({
        hasLocationCustom,
        showLocRemark,
        locationTextLen: (f.location_text || '').length,
        locationDictTextLen: (f.location_dict_text || '').length
      });
    }
  },

  // ===== 维修类型 =====
  onRepairTypeTap(e) {
    const code = e.currentTarget.dataset.code;
    const label = e.currentTarget.dataset.label;
    // 用户从 chips 选了 → 覆盖 manual 输入
    this.setData({
      'form.repair_type_code': code,
      'form.repair_type_text': label,
      'form.repair_type_text_custom': ''
    });
  },

  // ===== 维修地点 chips（2026-09-28 重构）：
  // - chips 直接显示名字（不带 "类型-" 前缀）
  // - 拼接顺序固定：按 orderedLocationTypes 顺序（楼栋→楼层→房间号…），与点击顺序无关
  // - 拼接段不可编辑，单独存在 form.location_dict_text（只读展示）
  // - 用户可在 textarea (form.location_text) 自由追加内容
  // =====

  // 2026-09-28 方案 C：列表段用 '|' 分隔（便于后端切分 + 精确 token 筛选）
  // 拼接顺序固定：按 orderedLocationTypes 顺序（楼栋→楼层→房间号…），与点击顺序无关
  // 示例：'10楼|宿舍楼A|102教室讲台'
  _composeDictText(selectedByType) {
    const ordered = this.data.orderedLocationTypes || [];
    const segs = [];
    ordered.forEach(t => {
      const v = selectedByType[t.type_code];
      if (v) segs.push(v);
    });
    Object.keys(selectedByType).forEach(tc => {
      if (!ordered.find(t => t.type_code === tc)) segs.push(selectedByType[tc]);
    });
    return segs.join('|');
  },

  // 点击 chip：写入 location_dict_selected + location_dict_text + location_chip_selected（用于 WXML 高亮）
  // - 同 type 重复点不同 value → 替换
  // - 同 type 同 value → 取消
  // - 如果该 type_code 是用户手动输入过的（location_manual_types 含此 type）→ 不允许 chips 覆盖
  onLocationChipTap(e) {
    const type_code = e.currentTarget.dataset.type;
    const name = e.currentTarget.dataset.name;
    if (!type_code || !name) return;

    // 2026-09-28 修复：从独立 dict 读取，不再用 _parseDictText 反推
    const sel = Object.assign({}, (this.data.form.location_dict_selected || {}));
    const chipSel = Object.assign({}, (this.data.form.location_chip_selected || {}));
    const manualTypes = (this.data.form.location_manual_types || []).slice();

    // 手动输入优先：chips 不能改
    if (manualTypes.indexOf(type_code) >= 0) {
      this.showWarning(`"${type_code}" 已使用手动输入，chips 暂不能修改`);
      return;
    }

    const key = `${type_code}-${name}`;
    if (sel[type_code] === name) {
      delete sel[type_code];
      delete chipSel[key];
    } else {
      // 同一个 type_code 之前选过别的 chip → 清掉那个 chip 的高亮
      if (sel[type_code]) {
        delete chipSel[`${type_code}-${sel[type_code]}`];
      }
      sel[type_code] = name;
      chipSel[key] = true;
    }

    this.setData({
      'form.location_dict_selected': sel,
      'form.location_chip_selected': chipSel,
      'form.location_dict_text': this._composeDictText(sel)
    });
    this._recomputeLocationDerived();
  },

  // 每个 type_code 下方的手动输入框：写入 location_dict_selected + location_dict_text + chip 高亮清理
  onLocationCustomInput(e) {
    const type_code = e.currentTarget.dataset.type;
    const value = (e.detail.value || '').trim();

    const sel = Object.assign({}, (this.data.form.location_dict_selected || {}));
    const chipSel = Object.assign({}, (this.data.form.location_chip_selected || {}));
    const previousChipName = sel[type_code];
    if (value) sel[type_code] = value;
    else delete sel[type_code];

    const custom = { ...((this.data.form && this.data.form.location_custom) || {}) };
    if (value) custom[type_code] = value;
    else delete custom[type_code];

    // 标记 type_code 为手动输入
    let manualTypes = (this.data.form.location_manual_types || []).slice();
    if (value) {
      if (manualTypes.indexOf(type_code) < 0) manualTypes.push(type_code);
    } else {
      manualTypes = manualTypes.filter(t => t !== type_code);
    }

    // 手动输入时清掉之前 chip 的高亮（如果之前选过 chip）
    if (previousChipName && previousChipName !== value) {
      delete chipSel[`${type_code}-${previousChipName}`];
    }

    this.setData({
      'form.location_dict_selected': sel,
      'form.location_chip_selected': chipSel,
      'form.location_dict_text': this._composeDictText(sel),
      'form.location_custom': custom,
      'form.location_manual_types': manualTypes
    });
    this._recomputeLocationDerived();
  },

  _setFormLocationParts(arr) {
    // 兼容旧调用：按 orderedLocationTypes 顺序拼接纯名字段（无分隔符）
    const selectedByType = {};
    arr.forEach(p => { if (p && p.type && p.value) selectedByType[p.type] = p.value; });
    const ordered = this.data.orderedLocationTypes || [];
    const segs = [];
    ordered.forEach(t => {
      const v = selectedByType[t.type_code];
      if (v) segs.push(v);
    });
    Object.keys(selectedByType).forEach(tc => {
      if (!ordered.find(t => t.type_code === tc)) segs.push(selectedByType[tc]);
    });
    const text = segs.join('');
    // 2026-09-28：根据 selectedByType 同步生成 chip_selected 查找表
    // 因为 WXML 不支持函数调用，只能用扁平 map + 属性查找做高亮。
    const chipSel = {};
    Object.keys(selectedByType).forEach(tc => {
      const v = selectedByType[tc];
      if (v) chipSel[`${tc}-${v}`] = true;
    });
    this.setData({
      'form.location_parts': arr,
      'form.location_text_fuzzy': text,
      'form.location_dict_text': text,
      'form.location_dict_selected': selectedByType,
      'form.location_chip_selected': chipSel
      // 不动 form.location_text（用户备注保留）
    });
  },

  onInput(e) {
    const key = e.currentTarget.dataset.key;
    this.setData({ [`form.${key}`]: e.detail.value });
    // 2026-09-28：textarea 字数实时统计
    if (key === 'location_text' || key === 'content') {
      const v = e.detail.value || '';
      if (key === 'location_text') {
        if (this.data.locationTextLen !== v.length) this.setData({ locationTextLen: v.length });
      } else {
        if (this.data.contentLen !== v.length) this.setData({ contentLen: v.length });
      }
    }
  },
  onUrgencyChange(e) {
    this.setData({ 'form.urgency': e.detail ? 'urgent' : 'normal' });
  },
  onAnonChange(e) {
    this.setData({ 'form.is_anonymous': e.detail });
  },

  goAdmin() {
    if (!this.data.isAdmin) {
      this.showError('您不是管理员');
      return;
    }
    wx.navigateTo({ url: '/packageAdmin/pages/feedback-admin/feedback-admin' });
  },

  onLogout() {
    wx.showModal({
      title: '退出登录',
      content: '退出后需要重新授权手机号才能继续使用校园反馈功能',
      confirmText: '退出',
      confirmColor: '#FF4D4F',
      success: (r) => {
        if (!r.confirm) return;
        try {
          wx.removeStorageSync(FEEDBACK_AUTH_CACHE_KEY);
          const app = getApp();
          if (app && app.globalData) app.globalData.token = '';
        } catch (e) {}
        wx.reLaunch({ url: '/packageAdmin/pages/feedback-login/feedback-login' });
      }
    });
  },

  async onChooseImage() {
    const remain = 6 - this.data.form.images.length;
    if (remain <= 0) return;
    try {
      const res = await wx.chooseMedia({
        count: remain,
        mediaType: ['image', 'video'],
        sizeType: ['compressed'],
        sourceType: ['album', 'camera'],
        maxDuration: 60,
        camera: 'back'
      });
      const images = [...this.data.form.images];
      for (const f of res.tempFiles) {
        const isVideo = f.fileType === 'video';
        if (isVideo) {
          if (f.size && f.size > 30 * 1024 * 1024) {
            this.showError('视频不能超过30MB');
            continue;
          }
          if (f.duration && f.duration > 60) {
            this.showError('视频时长不能超过60秒');
            continue;
          }
        }
        images.push({
          localPath: f.tempFilePath,
          localPoster: isVideo ? (f.thumbTempFilePath || '') : '',
          key: '', url: '', poster: '',
          type: isVideo ? 'video' : 'image',
          size: f.size || 0,
          duration: f.duration || 0
        });
      }
      this.setData({ 'form.images': images });
    } catch (e) { /* 用户取消 */ }
  },

  onPreviewImage(e) {
    const i = e.currentTarget.dataset.index;
    const sources = this.data.form.images.map(it => {
      const url = it.url ? this.data.baseUrl + it.url : it.localPath;
      return { url, type: it.type === 'video' ? 'video' : 'image' };
    });
    wx.previewMedia({ sources, current: i });
  },

  async onRemoveImage(e) {
    const i = e.currentTarget.dataset.index;
    const item = this.data.form.images[i];
    if (!item) return;
    if (item.key) {
      try {
        await feedbackPost('/feedback/delete_image', { key: item.key }, { showLoading: false });
      } catch (err) { /* 删除失败不阻塞 */ }
    }
    const arr = [...this.data.form.images];
    arr.splice(i, 1);
    this.setData({ 'form.images': arr });
  },

  _validate() {
    const f = this.data.form;
    if (f.category === 'repair') {
      // 维修类型：chips 选中 或 用户手动输入 至少有一项
      const typeCustom = (f.repair_type_text_custom || '').trim();
      if (!f.repair_type_text && !typeCustom) return '请选择维修类型';
      // 维修地点：列表段（chip 拼接）或 备注段（用户手写）至少有一项
      // 2026-09-28 方案 C：双列校验。
      // - 表单里 location_text 这个字段名用于 WXML "只读预览"，现在改名为只读展示用的容器
      // - 真正校验来源：f.location_dict_text 与 f.location_user_text
      const dictText = (f.location_dict_text || '').trim();
      const userText = (f.location_text || '').trim(); // 注意：用户手写仍存在这里
      if (!dictText && !userText) return '请选择维修地点';
    }
    if (f.content.trim().length < 2) return '请填写至少2字的描述';
    return '';
  },

  _uploadPendingMedia(items) {
    const pending = items.filter(it => !it.key);
    if (!pending.length) return Promise.resolve();

    const uploads = pending.map((it, seq) => {
      const show = seq === 0;
      return feedbackUploadFile({
        url: '/feedback/upload',
        filePath: it.localPath,
        name: 'file',
        loadingTitle: it.type === 'video' ? '视频上传中...' : '上传中...',
        showLoading: show
      }).then(data => {
        if (!data || !data.key) throw new Error('上传响应异常');
        it.key = data.key;
        it.url = data.url || '';
        it.type = data.type || it.type;
        return data;
      });
    });

    return Promise.all(uploads).catch(err => {
      const rolled = items.filter(it => it.key).map(it =>
        feedbackPost('/feedback/delete_image', { key: it.key }, { showLoading: false }).catch(() => {})
      );
      Promise.all(rolled).catch(() => {});
      throw err;
    });
  },

  async onSubmit() {
    const err = this._validate();
    if (err) { this.showError(err); return; }

    const items = this.data.form.images;

    if (items.length > 0) {
      this.setData({ submitting: true });
      try {
        await this._uploadPendingMedia(items);
        this.setData({ 'form.images': items });
      } catch (e) {
        this.setData({ submitting: false });
        this.showError(typeof e === 'string' ? e : (e && e.message) || '媒体上传失败');
        return;
      }
      this.setData({ submitting: false });
    }

    this.setData({ submitting: true });
    try {
      const f = this.data.form;
      const payload = {
        category: f.category,
        content: f.content,
        urgency: f.urgency,
        is_anonymous: f.is_anonymous,
        images: items.map(it => it.key).filter(Boolean),
      };
      // 维修类优先使用新字段
      if (f.category === 'repair') {
        // 2026-09-28：用户手动输入的维修类型覆盖字典 chip
        const typeCustom = (f.repair_type_text_custom || '').trim();
        payload.repair_type_code = typeCustom ? '' : f.repair_type_code;
        payload.repair_type_text = typeCustom || f.repair_type_text || '';
        // 2026-09-28 方案 C：双列独立提交。
        //   - location_dict_text：列表段（保留 | 分隔，便于后端切分 + 精确筛选）
        //   - location_user_text：备注段（自由文本）
        //   - location_text     ：仅展示，前端拼一个 '<dict> · <note>' 给详情页回显即可。
        // 备注：location_text 是 WXML "只读预览"框的反向赋值（来自 location_dict_text/_composeDictText），
        // 这里不再使用，避免和后端生成规则重复。前端合并展示串只用于前端展示，不发后端以免冲突。
        const dictText = (f.location_dict_text || '').trim();
        const userText = (f.location_text || '').trim();
        payload.location_dict_text = dictText;
        payload.location_user_text = userText;
        // 不再发 payload.location_text，后端按规则自动拼展示串
      }
      // 2026-09-28：调试模式打印 payload，便于确认 location_* 是否带上了
      console.log('[feedback-submit] payload=', payload);
      // 意见建议类（2026-09-27）：scene/scene_custom/item_type/item_custom 已废弃，content 已包含场景描述
      await feedbackPost('/feedback/submit', payload, { loadingTitle: '提交中...' });
      this.showSuccess('提交成功');
      setTimeout(() => {
        // 2026-09-29：改用 navigateTo，submit 保留在栈底，方便用户在"我的反馈"页用顶部返回按钮回退
        wx.navigateTo({ url: '/packageAdmin/pages/feedback-my/feedback-my' });
      }, 800);
    } catch (e) {
      this.showError(typeof e === 'string' ? e : '提交失败');
    } finally {
      this.setData({ submitting: false });
    }
  },

  goMyFeedback() {
    wx.navigateTo({ url: '/packageAdmin/pages/feedback-my/feedback-my' });
  }
});
