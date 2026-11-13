const { createPage } = require('../../../utils/page-mixin');
const { tokenGet, tokenPost } = require('../../../utils/request');

// ============================================================
// 字段配置
// ============================================================

// 基本信息字段配置
const BASIC_FIELDS = ['xm', 'xb', 'sfzh', 'mz', 'xsdh', 'zzmm'];

// 家庭联系信息字段配置（全部字段都可核对）
const FAMILY_FIELDS = ['jtxxdz', 'hkxz', 'jzdlx', 'jzxm', 'jzgx', 'jzdh'];

// 基本信息字段中文标签
const BASIC_FIELD_LABELS = {
  xm: '姓名',
  xb: '性别',
  sfzh: '身份证号',
  mz: '民族',
  xsdh: '联系电话',
  zzmm: '政治面貌'
};

// 家庭信息字段中文标签
const FAMILY_FIELD_LABELS = {
  jtxxdz: '家庭地址',
  hkxz: '户口性质',
  jzdlx: '居住地类型',
  jzxm: '监护人姓名',
  jzgx: '监护人关系',
  jzdh: '监护人电话'
};

// ============================================================
// 字典（前端硬编码）
// value 是后端存储的数字字符串，text 是显示的中文
// columnsPicker 是 van-picker 直接消费的字符串数组
// ============================================================

// 居住地类型 jzdlx
const JZDLX_OPTIONS = [
  { value: '1', text: '农村' },
  { value: '2', text: '县城' },
  { value: '3', text: '乡镇非农' },
  { value: '4', text: '城市' }
];

// 监护人关系 jzgx
const JZGX_OPTIONS = [
  { value: '1',  text: '父亲' },
  { value: '2',  text: '母亲' },
  { value: '3',  text: '继父或养父' },
  { value: '4',  text: '继母或养母' },
  { value: '5',  text: '祖父' },
  { value: '6',  text: '祖母' },
  { value: '7',  text: '外祖父' },
  { value: '8',  text: '外祖母' },
  { value: '9',  text: '兄' },
  { value: '10', text: '姐姐' },
  { value: '11', text: '其他亲属' },
  { value: '12', text: '非亲属' }
];

// 政治面貌 zzmm
const ZZMM_OPTIONS = [
  { value: '1', text: '中国共产主义青年团团员' },
  { value: '2', text: '群众' },
  { value: '3', text: '中国共产党党员' },
  { value: '4', text: '中国共产党预备党员' }
];

// 字段 -> 选项
const FIELD_OPTIONS = {
  jzdlx: JZDLX_OPTIONS,
  jzgx: JZGX_OPTIONS,
  zzmm: ZZMM_OPTIONS
};

// 生成 van-picker 直接消费的字符串数组（vant 默认行为）
function buildPickerColumns(options) {
  return options.map(o => o.text);
}

// 把任意值（数字字符串或文本）翻译成展示用的中文
function resolveDisplayText(field, rawValue) {
  if (rawValue === undefined || rawValue === null) return '';
  const strVal = String(rawValue);
  const opts = FIELD_OPTIONS[field];
  if (opts && opts.length) {
    const hit = opts.find(o => o.value === strVal);
    if (hit) return hit.text;
  }
  return strVal;
}

// 把任意值翻译成 picker columns 的 index
function resolvePickerIndex(field, rawValue) {
  if (rawValue === undefined || rawValue === null) return 0;
  const strVal = String(rawValue);
  const opts = FIELD_OPTIONS[field];
  if (!opts) return 0;
  const idx = opts.findIndex(o => o.value === strVal);
  return idx >= 0 ? idx : 0;
}

// ============================================================

createPage({
  data: {
    loading: false,
    status: 'pending',
    statusText: '待核对',
    statusClass: 'status-banner-pending',
    submittedAt: '',
    birthDate: '',
    // 当前打开 picker 的字段 key（全局只有 1 个 picker）
    pickerKey: '',
    pickerFieldLabel: '',
    pickerColumns: [],
    pickerIndex: 0,
    basicFields: BASIC_FIELDS.map(key => ({
      key,
      label: BASIC_FIELD_LABELS[key] || key,
      original: '',
      originalText: '',
      value: '',
      displayText: '',
      editing: false,
      modified: false,
      hasOptions: !!FIELD_OPTIONS[key]
    })),
    familyFields: FAMILY_FIELDS.map(key => ({
      key,
      label: FAMILY_FIELD_LABELS[key] || key,
      original: '',
      originalText: '',
      value: '',
      displayText: '',
      editing: false,
      modified: false,
      hasOptions: !!FIELD_OPTIONS[key]
    })),
    changedCount: 0
  },

  onLoad() {
    this.fetchInfo();
  },

  onShow() {
    this.fetchInfo();
  },

  async fetchInfo() {
    try {
      const res = await tokenGet('/vocational_info_verify/info');
      const payload = res || {};
      const original = payload.original || {};
      const latestModified = payload.latest_modified || {};

      const status = payload.status || 'pending';
      const statusMap = {
        pending: { text: '待核对', cls: 'status-banner-pending' },
        verified: { text: '已确认无误', cls: 'status-banner-verified' },
        modified: { text: '已核对（信息有修改）', cls: 'status-banner-modified' }
      };
      const meta = statusMap[status] || statusMap.pending;

      // 处理基本信息字段
      const basicFields = this.data.basicFields.map(f => {
        const orig = (original[f.key] != null ? original[f.key] : '').toString();
        const origText = resolveDisplayText(f.key, orig);
        const modVal = latestModified[f.key];
        const cur = (modVal !== undefined && modVal !== null) ? String(modVal) : orig;
        const curText = resolveDisplayText(f.key, cur);
        const isMod = status !== 'pending' && (cur !== orig);
        return Object.assign({}, f, {
          original: orig,
          originalText: origText,
          trueOriginal: orig,
          value: cur,
          displayText: curText,
          editing: false,
          modified: isMod
        });
      });

      // 处理家庭信息字段
      const familyFields = this.data.familyFields.map(f => {
        const orig = (original[f.key] != null ? original[f.key] : '').toString();
        const origText = resolveDisplayText(f.key, orig);
        const modVal = latestModified[f.key];
        const cur = (modVal !== undefined && modVal !== null) ? String(modVal) : orig;
        const curText = resolveDisplayText(f.key, cur);
        const isMod = status !== 'pending' && (cur !== orig);
        return Object.assign({}, f, {
          original: orig,
          originalText: origText,
          trueOriginal: orig,
          value: cur,
          displayText: curText,
          editing: false,
          modified: isMod
        });
      });

      const modifiedKeys = Object.keys(latestModified);

      this.setData({
        basicFields,
        familyFields,
        birthDate: payload.birth_date || '',
        status,
        statusText: meta.text,
        statusClass: meta.cls,
        submittedAt: payload.submitted_at || '',
        changedCount: modifiedKeys.length,
        // 重置 picker 状态
        pickerKey: '',
        pickerFieldLabel: '',
        pickerColumns: [],
        pickerIndex: 0
      });
    } catch (err) {
      this.showError((err && err.message) || '获取信息失败');
    }
  },

  /**
   * 点击右侧操作按钮：toggle 编辑模式
   */
  onActionTap(e) {
    const { key, action } = e.currentTarget.dataset || {};
    if (action !== 'toggle' || !key) return;

    let fieldsKey = 'basicFields';
    if (FAMILY_FIELDS.includes(key)) {
      fieldsKey = 'familyFields';
    }

    const fields = this.data[fieldsKey].map(f => {
      if (f.key !== key) return f;
      if (f.editing) {
        // 取消编辑：恢复原值，退出编辑态
        return Object.assign({}, f, {
          value: f.original,
          displayText: f.originalText,
          editing: false,
          modified: false
        });
      }
      // 进入编辑
      return Object.assign({}, f, { editing: true });
    });
    this.setData({ [fieldsKey]: fields }, () => this._refreshChangedCount());
  },

  /**
   * 普通输入框变更（无字典的字段）
   */
  onFieldChange(e) {
    const { key } = e.currentTarget.dataset || {};
    if (!key) return;

    let fieldsKey = 'basicFields';
    if (FAMILY_FIELDS.includes(key)) {
      fieldsKey = 'familyFields';
    }

    const value = (e.detail != null) ? String(e.detail) : '';
    const fields = this.data[fieldsKey].map(f => {
      if (f.key !== key) return f;
      const modified = (value || '') !== (f.trueOriginal || '');
      const displayText = resolveDisplayText(f.key, value);
      return Object.assign({}, f, { value, displayText, modified });
    });
    this.setData({ [fieldsKey]: fields }, () => this._refreshChangedCount());
  },

  /**
   * 打开 picker：支持两种入口
   * - 直接点"当前值"行（picker-row，pending 状态可用）
   * - 编辑模式下点 van-field
   */
  onOpenPicker(e) {
    const { key } = e.currentTarget.dataset || {};
    if (!key) return;

    const opts = FIELD_OPTIONS[key];
    if (!opts || !opts.length) return;

    // 找当前字段最新 value
    let fieldsKey = 'basicFields';
    if (FAMILY_FIELDS.includes(key)) {
      fieldsKey = 'familyFields';
    }
    const f = (this.data[fieldsKey] || []).find(x => x.key === key);
    if (!f) return;

    const labelMap = Object.assign({}, BASIC_FIELD_LABELS, FAMILY_FIELD_LABELS);

    this.setData({
      pickerKey: key,
      pickerFieldLabel: labelMap[key] || key,
      pickerColumns: buildPickerColumns(opts),
      pickerIndex: resolvePickerIndex(key, f.value)
    });
  },

  _noop() {},

  /**
   * 全部取消：把所有字段恢复为原始值（未提交前误改可一键还原）
   */
  onCancelAll() {
    if (this.data.status !== 'pending') return;
    if (this.data.changedCount === 0) return;

    wx.showModal({
      title: '全部取消',
      content: `您已修改 ${this.data.changedCount} 项，全部取消后所有改动将恢复到原始值，确定吗？`,
      confirmText: '确定恢复',
      cancelText: '再想想',
      success: (r) => {
        if (!r.confirm) return;

        const basicFields = this.data.basicFields.map(f => Object.assign({}, f, {
          value: f.original,
          displayText: f.originalText,
          editing: false,
          modified: false
        }));
        const familyFields = this.data.familyFields.map(f => Object.assign({}, f, {
          value: f.original,
          displayText: f.originalText,
          editing: false,
          modified: false
        }));

        this.setData({
          basicFields,
          familyFields,
          pickerKey: '',
          pickerColumns: [],
          pickerFieldLabel: '',
          pickerIndex: 0
        }, () => this._refreshChangedCount());

        wx.showToast({ title: '已恢复原始值', icon: 'success', duration: 1500 });
      }
    });
  },

  /**
   * picker 关闭（取消）
   */
  onPickerClose() {
    this.setData({
      pickerKey: '',
      pickerColumns: [],
      pickerFieldLabel: '',
      pickerIndex: 0
    });
  },

  /**
   * picker change 事件：实时更新选中 index
   */
  onPickerChange(e) {
    const detail = (e && e.detail) || {};
    const idx = typeof detail.index === 'number'
      ? detail.index
      : (typeof detail.value === 'number' ? detail.value : this.data.pickerIndex);
    this.setData({ pickerIndex: idx });
  },

  /**
   * picker 确认
   */
  onPickerConfirm(e) {
    const detail = (e && e.detail) || {};
    const key = this.data.pickerKey;
    if (!key) return;

    const opts = FIELD_OPTIONS[key];
    if (!opts || !opts.length) {
      this.onPickerClose();
      return;
    }

    // 兼容多种事件格式
    let idx = this.data.pickerIndex;
    if (typeof detail.index === 'number') {
      idx = detail.index;
    } else if (typeof detail.value === 'number') {
      // 字符串数组模式下，detail.value 是当前选中的文本，反查 idx
      const i = opts.findIndex(o => o.text === detail.value);
      if (i >= 0) idx = i;
    }

    const picked = opts[idx] || opts[0];
    const newValue = picked.value;
    const newDisplayText = picked.text;

    let fieldsKey = 'basicFields';
    if (FAMILY_FIELDS.includes(key)) {
      fieldsKey = 'familyFields';
    }

    const fields = this.data[fieldsKey].map(f => {
      if (f.key !== key) return f;
      const modified = (newValue || '') !== (f.trueOriginal || '');
      return Object.assign({}, f, {
        value: newValue,
        displayText: newDisplayText,
        modified
      });
    });

    this.setData({
      [fieldsKey]: fields,
      pickerKey: '',
      pickerColumns: [],
      pickerFieldLabel: '',
      pickerIndex: 0
    }, () => this._refreshChangedCount());
  },

  _refreshChangedCount() {
    const basicModified = this.data.basicFields.filter(f => f.modified).length;
    const familyModified = this.data.familyFields.filter(f => f.modified).length;
    const n = basicModified + familyModified;
    if (n !== this.data.changedCount) {
      this.setData({ changedCount: n });
    }
  },

  /**
   * 已核对状态（verified / modified）不允许再次提交
   */
  onSubmit() {
    const status = this.data.status;
    if (status !== 'pending') {
      wx.showToast({ title: '已提交，无需重复操作', icon: 'none', duration: 1800 });
      return;
    }

    const changedCount = this.data.changedCount;

    let basicFields = this.data.basicFields;
    let familyFields = this.data.familyFields;
    if (basicFields.some(f => f.editing) || familyFields.some(f => f.editing)) {
      basicFields = basicFields.map(f => ({ ...f, editing: false }));
      familyFields = familyFields.map(f => ({ ...f, editing: false }));
      this.setData({ basicFields, familyFields });
    }

    const title = changedCount > 0 ? '提交修改' : '确认无误';
    const content = changedCount > 0
      ? `本次共修改 ${changedCount} 项，提交后将写入档案并保存修改记录，继续？`
      : '请确认您已仔细核对全部信息，确认后不能再修改。';

    wx.showModal({
      title,
      content,
      confirmText: '确认提交',
      success: async (r) => {
        if (!r.confirm) return;
        await this.doSubmit();
      }
    });
  },

  async doSubmit() {
    const original = {};
    const form = {};

    [...this.data.basicFields, ...this.data.familyFields].forEach(f => {
      original[f.key] = f.original;
      form[f.key] = f.value;
    });

    const changes = [];
    [...BASIC_FIELDS, ...FAMILY_FIELDS].forEach(k => {
      const oldV = (original[k] != null ? original[k] : '').toString();
      const newV = (form[k] != null ? form[k] : '').toString();
      if (oldV !== newV) {
        changes.push({ field: k, value: newV });
      }
    });

    this.setData({ loading: true });
    try {
      const res = await tokenPost('/vocational_info_verify/submit', { changes }, { loadingTitle: '提交中...' });
      const data = res?.data || {};
      wx.showToast({
        title: data.status === 'modified' ? '已保存修改' : '提交成功',
        icon: 'success',
        duration: 1500
      });
      await this.fetchInfo();
    } catch (err) {
      wx.showToast({
        title: (err && err.message) || '提交失败',
        icon: 'none',
        duration: 1800
      });
    } finally {
      this.setData({ loading: false });
    }
  }
}, {
  requireAuth: true,
  userType: 'vocational_student'
});
