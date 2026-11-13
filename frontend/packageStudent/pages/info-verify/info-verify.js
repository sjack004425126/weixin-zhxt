const { createPage } = require('../../../utils/page-mixin');
const { tokenGet, tokenPost } = require('../../../utils/request');
const { isValidIdCard } = require('../../../utils/util');

// ============================================================
// 字段配置
// ============================================================

// 兜底选项（后端没返回时使用）
const FALLBACK_GENDERS = [
  { text: '男', value: '1' },
  { text: '女', value: '0' }
];

const FALLBACK_NATIONS = ['汉族', '蒙古族', '回族', '藏族', '维吾尔族', '苗族', '彝族', '壮族', '布依族', '朝鲜族',
  '满族', '侗族', '瑶族', '白族', '土家族', '哈尼族', '哈萨克族', '傣族', '黎族', '傈僳族',
  '佤族', '畲族', '高山族', '拉祜族', '水族', '东乡族', '纳西族', '景颇族', '科尔克孜族', '土族',
  '达斡尔族', '仫佬族', '羌族', '布朗族', '撒拉族', '毛南族', '仡佬族', '锡伯族', '阿昌族', '普米族',
  '塔吉克族', '怒族', '乌孜别克族', '俄罗斯族', '鄂温克族', '德昂族', '保安族', '裕固族', '京族', '塔塔尔族',
  '独龙族', '鄂伦春族', '赫哲族', '门巴族', '珞巴族', '基诺族', '其他'
].map(n => ({ text: n, value: n }));

// 字段 -> 选项来源
function normalizeOptions(field, raw) {
  if (field === 'xs_xb') {
    const list = Array.isArray(raw) && raw.length ? raw : FALLBACK_GENDERS;
    return list.map(o => {
      if (typeof o === 'string') return { text: o, value: o };
      const t = o.text != null ? o.text : o.name;
      const v = o.value != null ? o.value : t;
      return { text: String(t), value: String(v) };
    });
  }
  if (field === 'xs_mz') {
    const list = Array.isArray(raw) && raw.length ? raw : FALLBACK_NATIONS;
    return list.map(o => {
      if (typeof o === 'string') return { text: o, value: o };
      const t = o.text != null ? o.text : o.name;
      const v = o.value != null ? o.value : t;
      return { text: String(t), value: String(v) };
    });
  }
  return [];
}

function buildPickerColumns(options) {
  return options.map(o => o.text);
}

function resolveDisplayText(options, rawValue) {
  if (rawValue === undefined || rawValue === null) return '';
  const strVal = String(rawValue);
  const hit = options.find(o => o.value === strVal || o.text === strVal);
  return hit ? hit.text : strVal;
}

function resolvePickerIndex(options, rawValue) {
  if (rawValue === undefined || rawValue === null) return 0;
  const strVal = String(rawValue);
  const idx = options.findIndex(o => o.value === strVal || o.text === strVal);
  return idx >= 0 ? idx : 0;
}

// 核对状态：no-未核对 / ok-已核对 / md-已修改待确认 / err-数据异常
const STATE_TEXT = {
  no: '未核对',
  ok: '已核对',
  md: '已修改',
  err: '数据异常'
};

// 筛选签
const FILTERS = [
  { key: 'all', label: '全部' },
  { key: 'no', label: '未核对' },
  { key: 'ok', label: '已核对' },
  { key: 'md', label: '已修改' },
  { key: 'err', label: '数据异常' }
];

// ============================================================
// 字段格式校验
// ============================================================
// key -> { validate(value): boolean, message: string }
// 非空校验由 required 统一处理，这里只做格式校验。
const FIELD_VALIDATORS = {
  // 身份证号：15 位或 18 位，含出生日期与校验码验证
  xs_sfzh: {
    validate: (v) => isValidIdCard(v),
    message: '身份证号格式不正确，请核对后重新输入'
  }
};

/**
 * 校验某个字段的值，返回错误信息（空字符串表示通过）
 * @param {string} key 字段 key
 * @param {string} value 字段值
 * @param {boolean} required 是否必填
 * @returns {string} 错误信息
 */
function validateFieldValue(key, value, required) {
  const v = String(value == null ? '' : value).trim();

  if (!v) {
    return required ? '该项内容为空，请补充' : '';
  }

  const rule = FIELD_VALIDATORS[key];
  if (rule && !rule.validate(v)) {
    return rule.message;
  }

  return '';
}

createPage({
  data: {
    loading: false,
    status: 'pending',        // pending / verified
    statusText: '待核对',
    statusClass: 'status-banner-pending',
    submittedAt: '',
    // 分组数据：[{key, name, rows: [...]}]（完整数据源）
    groups: [],
    // 按筛选过滤后的视图数据
    viewGroups: [],
    // 筛选
    filter: 'all',
    filters: FILTERS,
    counts: { all: 0, no: 0, ok: 0, md: 0, err: 0 },
    // 内部统计（用于提交门槛，不在界面展示）
    confirmedCount: 0,
    totalCount: 0,
    // 全局唯一 picker
    pickerKey: '',
    pickerFieldLabel: '',
    pickerColumns: [],
    pickerIndex: 0,
    changedCount: 0,
    // 是否存在任何操作痕迹（已确认/已修改），决定「全部取消」是否可用
    hasAction: false,
    // 学习承诺书弹窗
    showCommitment: false,
    commitmentChecked: false,
    commitmentLevel: '',
    commitmentMajor: ''
  },

  onLoad() {
    this.fetchInfo();
  },

  onShow() {
    this.fetchInfo();
  },

  async fetchInfo() {
    try {
      const res = await tokenGet('/student_info_verify/info');
      // request.js 已解包：res 即后端 data
      const payload = res || {};
      console.log('[info-verify] 接口返回:', JSON.stringify(payload));

      const status = payload.status || 'pending';
      this._drafts = {};

      const statusMap = {
        pending: { text: '待核对', cls: 'status-banner-pending' },
        verified: { text: '已核对完成', cls: 'status-banner-verified' }
      };
      const meta = statusMap[status] || statusMap.pending;

      // 字段选项
      const optionsMap = {
        xs_xb: normalizeOptions('xs_xb', payload.gender_options),
        xs_mz: normalizeOptions('xs_mz', payload.nation_options)
      };

      // 构建分组行
      const rawGroups = Array.isArray(payload.groups) && payload.groups.length
        ? payload.groups
        : this._fallbackGroups(payload);

      const groups = rawGroups.map(g => ({
        key: g.key,
        name: g.name,
        rows: (g.rows || []).map(r => {
          const opts = optionsMap[r.key] || [];
          const value = r.value != null ? String(r.value) : '';
          const displayText = opts.length ? resolveDisplayText(opts, value) : value;
          const originalText = opts.length
            ? resolveDisplayText(opts, r.original)
            : (r.original != null ? String(r.original) : '');
          // 只读字段不参与核对
          const readonly = !!r.readonly || !r.editable;
          const modified = !!r.modified && !readonly;
          // 数据异常：必填项为空
          const isError = !readonly && !!r.required && !value.trim();
          let state = 'no';
          if (isError) state = 'err';
          else if (status === 'verified') state = 'ok';
          else if (modified) state = 'md';
          return {
            key: r.key,
            label: r.label,
            value: value,
            displayText: displayText,
            originalText: originalText,
            editing: false,
            draft: '',
            inputError: '',
            modified: modified,
            justActed: false,
            required: !!r.required,
            readonly: readonly,
            hasOptions: opts.length > 0,
            options: opts,
            state: state,
            stateText: STATE_TEXT[state],
            errorMsg: isError ? '该项内容为空，请补充' : ''
          };
        })
      }));

      this.setData({
        groups,
        status,
        statusText: meta.text,
        statusClass: meta.cls,
        submittedAt: payload.submitted_at || '',
        pickerKey: '',
        pickerColumns: [],
        pickerFieldLabel: '',
        pickerIndex: 0,
        commitmentLevel: payload.commitment_info?.level || '',
        commitmentMajor: payload.commitment_info?.major || ''
      }, () => this._refreshStats());
    } catch (err) {
      console.error('[info-verify] 获取信息失败:', err);
      wx.showToast({
        title: (err && err.message) || '获取信息失败',
        icon: 'none',
        duration: 2000
      });
    }
  },

  // 后端无 groups 时的兜底
  _fallbackGroups(payload) {
    const original = payload.original || {};
    const labels = payload.field_labels || {};
    const pick = (k) => {
      const orig = original[k] != null ? String(original[k]) : '';
      return {
        key: k,
        label: labels[k] || k,
        value: orig,
        original: orig,
        editable: true,
        required: true,
        readonly: false,
        modified: false
      };
    };
    return [
      {
        key: 'basic', name: '基本信息',
        rows: [
          pick('xs_xm'), pick('xs_xb'),
          pick('xs_sfzh'), pick('xs_mz')
        ]
      }
    ];
  },

  /**
   * 切换筛选签
   *
   * 切换时清掉 justActed 标记，让筛选严格按状态过滤；
   * justActed 只是为了「用户刚操作完的那一项」不因状态变化而从列表消失。
   */
  onFilterChange(e) {
    const { filter } = e.currentTarget.dataset || {};
    if (!filter) return;
    const groups = (this.data.groups || []).map(g => ({
      key: g.key,
      name: g.name,
      rows: g.rows.map(r => (r.justActed ? Object.assign({}, r, { justActed: false }) : r))
    }));
    this.setData({ filter, groups }, () => this._refreshStats());
  },

  /**
   * 确认某项无误
   */
  onConfirmField(e) {
    const { key } = e.currentTarget.dataset || {};
    if (!key) return;
    if (this.data.status !== 'pending') return;

    // 若有未保存的草稿，确认即视为接受当前草稿
    const draft = (this._drafts && this._drafts[key] != null) ? this._drafts[key] : null;

    this._updateRow(key, (row) => {
      if (row.readonly) return row;
      const v = draft != null ? String(draft).trim() : String(row.value || '').trim();
      const modified = v !== String(row.originalText || '');
      const isError = row.required && !v;
      return Object.assign({}, row, {
        value: v,
        displayText: v,
        editing: false,
        draft: '',
        inputError: '',
        modified: modified && !isError,
        justActed: true,
        state: isError ? 'err' : 'ok',
        stateText: STATE_TEXT[isError ? 'err' : 'ok'],
        errorMsg: isError ? '该项内容为空，请补充' : ''
      });
    }, () => {
      if (this._drafts) delete this._drafts[key];
    });
  },

  /**
   * 打开就地编辑
   */
  onEditField(e) {
    const { key } = e.currentTarget.dataset || {};
    if (!key) return;
    if (this.data.status !== 'pending') return;

    this._updateRow(key, (row) => {
      if (row.readonly) return row;
      return Object.assign({}, row, {
        editing: true,
        draft: row.value
      });
    });
  },

  /**
   * 取消编辑（不保存）
   */
  onCancelEdit(e) {
    const { key } = e.currentTarget.dataset || {};
    if (!key) return;

    if (this._drafts) delete this._drafts[key];

    this._updateRow(key, (row) => {
      if (row.readonly) return row;
      const isError = row.required && !String(row.value || '').trim();
      const state = isError ? 'err' : (row.modified ? 'md' : 'no');
      return Object.assign({}, row, {
        editing: false,
        draft: '',
        inputError: '',
        justActed: false,
        state: state,
        stateText: STATE_TEXT[state],
        errorMsg: isError ? '该项内容为空，请补充' : ''
      });
    });
  },

  /**
   * 保存修改 -> 状态回到「已修改待确认」
   *
   * 保存前做格式校验（如身份证号）。校验不通过时：
   * - 不退出编辑态，保持编辑框，让用户直接改正
   * - 错误信息显示在行内（红色）
   */
  onSaveField(e) {
    const { key } = e.currentTarget.dataset || {};
    if (!key) return;

    const draft = (this._drafts && this._drafts[key] != null) ? this._drafts[key] : null;

    // 先取当前值做格式校验
    const row = this._findRow(key);
    if (!row || row.readonly) return;
    const raw = String(draft != null ? draft : (row.draft != null ? row.draft : row.value)).trim();

    const errMsg = validateFieldValue(key, raw, row.required);
    if (errMsg) {
      // 校验失败：保持编辑态 + 行内错误提示
      this._updateRow(key, (r) => Object.assign({}, r, {
        editing: true,
        draft: raw,
        inputError: errMsg
      }));
      wx.showToast({ title: errMsg, icon: 'none', duration: 2000 });
      return;
    }

    this._updateRow(key, (row2) => {
      if (row2.readonly) return row2;
      const v = String(draft != null ? draft : (row2.draft != null ? row2.draft : row2.value)).trim();
      const modified = v !== String(row2.originalText || '');
      const isError = row2.required && !v;
      // 有改动 -> 已修改待确认；无改动 -> 保持未核对（仍可点确认）
      const state = isError ? 'err' : (modified ? 'md' : 'no');
      return Object.assign({}, row2, {
        value: v,
        displayText: v,
        editing: false,
        draft: '',
        inputError: '',
        modified: modified && !isError,
        justActed: true,
        state: state,
        stateText: STATE_TEXT[state],
        errorMsg: isError ? '该项内容为空，请补充' : ''
      });
    }, () => {
      if (this._drafts) delete this._drafts[key];
      wx.showToast({ title: '已保存，请确认', icon: 'none', duration: 1200 });
    });
  },

  /**
   * 通用：更新某行（key 为字段 key）
   */
  _updateRow(key, fn, cb) {
    const groups = this.data.groups.map(g => ({
      key: g.key,
      name: g.name,
      rows: g.rows.map(r => (r.key === key ? fn(r) : r))
    }));
    this.setData({ groups }, () => {
      this._refreshStats();
      if (cb) cb();
    });
  },

  /**
   * 刷新筛选结果 + 计数 + 进度
   */
  _refreshStats() {
    const groups = this.data.groups || [];
    const filter = this.data.filter;

    // 统计（只统计可编辑字段）
    const allRows = [];
    groups.forEach(g => g.rows.forEach(r => { if (!r.readonly) allRows.push(r); }));

    const counts = {
      all: allRows.length,
      no: 0, ok: 0, md: 0, err: 0
    };
    allRows.forEach(r => { counts[r.state] = (counts[r.state] || 0) + 1; });

    // 按筛选过滤（保留分组结构，空组移除）
    const filteredGroups = groups.map(g => ({
      key: g.key,
      name: g.name,
      rows: g.rows.filter(r => {
        if (r.readonly) {
          // 只读字段在「全部」时展示，其他筛选下隐藏
          return filter === 'all';
        }
        // 正在编辑的行始终保持可见
        if (r.editing) return true;
        if (filter === 'all') return true;
        // 用户本次操作过的行（刚保存/刚确认）始终保持可见，
        // 否则状态一变（如 no -> md）行会从当前筛选里消失，
        // 导致「确认 / 编辑」按钮看起来凭空消失。
        if (r.justActed) return true;
        return r.state === filter;
      })
    })).filter(g => g.rows.length > 0);

    const totalCount = allRows.length;
    const confirmedCount = allRows.filter(r => r.state === 'ok' || r.state === 'md').length;

    const changedCount = allRows.filter(r => r.modified).length;
    // 有任何操作痕迹（已确认 或 已修改）时，「全部取消」可用
    const hasAction = allRows.some(r => r.state === 'ok' || r.state === 'md' || r.modified);

    this.setData({
      viewGroups: filteredGroups,
      counts: counts,
      confirmedCount: confirmedCount,
      totalCount: totalCount,
      changedCount: changedCount,
      hasAction: hasAction
    });
  },

  /**
   * 打开 picker
   */
  onOpenPicker(e) {
    const { key } = e.currentTarget.dataset || {};
    if (!key) return;
    if (this.data.status !== 'pending') return;

    const row = this._findRow(key);
    if (!row || !row.hasOptions) return;

    this.setData({
      pickerKey: key,
      pickerFieldLabel: row.label,
      pickerColumns: buildPickerColumns(row.options),
      pickerIndex: resolvePickerIndex(row.options, row.value)
    });
  },

  _findRow(key) {
    const groups = this.data.groups || [];
    for (let i = 0; i < groups.length; i++) {
      const hit = groups[i].rows.find(r => r.key === key);
      if (hit) return hit;
    }
    return null;
  },

  /**
   * 手动输入变更
   *
   * 注意 1：原生 input 的 bindinput 事件 e.detail 是 { value, cursor } 对象，
   *         不是字符串，必须取 e.detail.value，否则会显示成 [object Object]。
   * 注意 2：直接改写 this.data 而不调用 setData，避免受控回写导致光标跳到末尾；
   *         同时把草稿同步进 row.draft，这样其它地方触发 setData 重渲染时不会丢输入。
   */
  onFieldChange(e) {
    const { key } = e.currentTarget.dataset || {};
    if (!key) return;

    const detail = (e && e.detail) || {};
    let value = '';
    if (typeof detail === 'string') {
      value = detail;
    } else if (detail && detail.value != null) {
      value = String(detail.value);
    }

    if (!this._drafts) this._drafts = {};
    this._drafts[key] = value;

    // 静默更新草稿（不走 setData，防止光标跳到末尾）
    const groups = this.data.groups || [];
    for (let i = 0; i < groups.length; i++) {
      const rows = groups[i].rows;
      for (let j = 0; j < rows.length; j++) {
        if (rows[j].key === key) {
          rows[j].draft = value;
          // 用户已重新输入 -> 清除上一次的格式错误提示。
          // 用精确路径 setData，不动 input 的 value 绑定，避免光标跳到末尾。
          // （只清 inputError；errorMsg 是后端数据异常态提示，保留）
          if (rows[j].inputError) {
            rows[j].inputError = '';
            this.setData({ [`groups[${i}].rows[${j}].inputError`]: '' });
          }
          return;
        }
      }
    }
  },

  /**
   * 全部取消
   *
   * 同时处理两种情况：
   * 1. 已修改的项 -> 恢复原始值，状态回到「未核对」
   * 2. 已确认（无误）的项 -> 状态也回到「未核对」，允许用户重新核对
   */
  onCancelAll() {
    if (this.data.status !== 'pending') return;
    if (!this.data.hasAction) return;

    const changedCount = this.data.changedCount;
    const confirmedCount = this.data.confirmedCount;
    let tip = '';
    if (changedCount > 0 && confirmedCount > 0) {
      tip = `您已修改 ${changedCount} 项、确认 ${confirmedCount} 项，全部取消后所有改动将恢复到原始值，且已确认项将重新变为待核对，确定吗？`;
    } else if (changedCount > 0) {
      tip = `您已修改 ${changedCount} 项，全部取消后所有改动将恢复到原始值，确定吗？`;
    } else {
      tip = `您已确认 ${confirmedCount} 项，全部取消后这些项将重新变为待核对，确定吗？`;
    }

    wx.showModal({
      title: '全部取消',
      content: tip,
      confirmText: '确定恢复',
      cancelText: '再想想',
      success: (r) => {
        if (!r.confirm) return;
        this._drafts = {};
        const groups = this.data.groups.map(g => ({
          key: g.key,
          name: g.name,
          rows: g.rows.map(row => {
            if (row.readonly) return row;
            const isError = row.required && !String(row.originalText || '').trim();
            const state = isError ? 'err' : 'no';
            return Object.assign({}, row, {
              value: row.originalText,
              displayText: row.originalText,
              draft: '',
              inputError: '',
              editing: false,
              modified: false,
              justActed: false,
              state: state,
              stateText: STATE_TEXT[state],
              errorMsg: isError ? '该项内容为空，请补充' : ''
            });
          })
        }));
        this.setData({
          groups,
          pickerKey: '',
          pickerColumns: [],
          pickerFieldLabel: '',
          pickerIndex: 0
        }, () => this._refreshStats());
        wx.showToast({ title: '已全部取消', icon: 'success', duration: 1500 });
      }
    });
  },

  onPickerClose() {
    this.setData({
      pickerKey: '',
      pickerColumns: [],
      pickerFieldLabel: '',
      pickerIndex: 0
    });
  },

  onPickerChange(e) {
    const detail = (e && e.detail) || {};
    const idx = typeof detail.index === 'number'
      ? detail.index
      : (typeof detail.value === 'number' ? detail.value : this.data.pickerIndex);
    this.setData({ pickerIndex: idx });
  },

  onPickerConfirm(e) {
    const detail = (e && e.detail) || {};
    const key = this.data.pickerKey;
    if (!key) return;

    const row = this._findRow(key);
    if (!row || !row.options || !row.options.length) {
      this.onPickerClose();
      return;
    }

    let idx = this.data.pickerIndex;
    if (typeof detail.index === 'number') {
      idx = detail.index;
    } else if (typeof detail.value === 'number') {
      const i = row.options.findIndex(o => o.text === detail.value);
      if (i >= 0) idx = i;
    }

    const picked = row.options[idx] || row.options[0];
    const newValue = picked.value;
    const newText = picked.text;

    this.setData({
      pickerKey: '',
      pickerColumns: [],
      pickerFieldLabel: '',
      pickerIndex: 0
    });

    // 记录草稿 + 实时预览，点「保存」后才真正生效
    if (!this._drafts) this._drafts = {};
    this._drafts[key] = newText;

    this._updateRow(key, (r) => {
      if (r.readonly) return r;
      return Object.assign({}, r, {
        draft: newText,
        displayText: newText
      });
    });
  },

  onSubmit() {
    if (this.data.status !== 'pending') {
      wx.showToast({ title: '已提交，无需重复操作', icon: 'none', duration: 1800 });
      return;
    }

    // 完成门槛：必须全部项目已核对
    if (this.data.confirmedCount < this.data.totalCount) {
      const remain = this.data.totalCount - this.data.confirmedCount;
      wx.showToast({ title: `还有 ${remain} 项未核对`, icon: 'none', duration: 2000 });
      this.setData({ filter: 'no' }, () => this._refreshStats());
      return;
    }

    // 关闭所有编辑器
    const hasEditing = (this.data.groups || []).some(g => g.rows.some(r => r.editing));
    if (hasEditing) {
      const groups = this.data.groups.map(g => ({
        key: g.key,
        name: g.name,
        rows: g.rows.map(r => (r.editing ? Object.assign({}, r, { editing: false }) : r))
      }));
      this.setData({ groups });
    }

    // 必须先阅读并勾选同意承诺书
    if (!this.data.commitmentChecked) {
      wx.showToast({ title: '请先阅读并勾选同意学习承诺书', icon: 'none', duration: 2000 });
      this.setData({ showCommitment: true });
      return;
    }

    this._doConfirmAndSubmit();
  },

  // 打开承诺书弹窗（只读查看）
  onOpenCommitment() {
    this.setData({ showCommitment: true });
  },

  // 勾选 / 取消勾选同意
  onCommitmentToggle() {
    this.setData({ commitmentChecked: !this.data.commitmentChecked });
  },

  onCommitmentClose() {
    this.setData({ showCommitment: false });
  },

  _doConfirmAndSubmit() {
    const changedCount = this.data.changedCount;
    const title = changedCount > 0 ? '提交修改' : '确认无误';
    const content = changedCount > 0
      ? `本次共修改 ${changedCount} 项，提交后将写入档案，继续？`
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
    // 收集所有修改项
    const changes = [];
    (this.data.groups || []).forEach(g => {
      g.rows.forEach(r => {
        if (r.readonly) return;
        const orig = String(r.originalText || '');
        const cur = String(r.value || '');
        if (orig !== cur) {
          changes.push({ field: r.key, value: cur });
        }
      });
    });

    this.setData({ loading: true });
    try {
      await tokenPost('/student_info_verify/submit', {
        changes,
        commitment_agreed: !!this.data.commitmentChecked
      }, { loadingTitle: '提交中...' });
      wx.showToast({
        title: changes.length > 0 ? '已保存修改' : '提交成功',
        icon: 'success',
        duration: 1500
      });
      await this.fetchInfo();
    } catch (err) {
      console.error('[info-verify] 提交失败:', err);
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
  userType: 'open_student'
});
