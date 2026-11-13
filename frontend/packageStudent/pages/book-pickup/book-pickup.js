const { createPage } = require('../../../utils/page-mixin');
const { tokenGet, tokenPost } = require('../../../utils/request');

function buildDerived(d) {
  const isSelf = d.pickup_type === 'self_pickup';
  const isMail = d.pickup_type === 'mail';
  const site = d.pickup_site || null;
  const hasAddr = !!(site && site.has_address);
  const hasContact = !!(site && (site.teacher_name || site.teacher_phone));
  const contactText = hasContact
    ? ('联系人：' + (site.teacher_name || '') + (site.teacher_phone ? (' ' + site.teacher_phone) : ''))
    : '';
  const cur = d.current || null;
  let summary = '每个学期统计一次，提交后仍可回来修改';
  if (d.filled && cur) {
    if (cur.pickup_type === 'self_pickup') {
      summary = '当前选择：到校领取';
      if (cur.pickup_date) summary += ' · ' + cur.pickup_date;
    } else if (cur.pickup_type === 'mail') {
      summary = '当前选择：邮寄 · ' + (cur.province || '') + (cur.city || '') + (cur.district || '') + (cur.detail_addr || '');
    }
    if (cur.updated_at) summary += '（更新于' + cur.updated_at + '）';
  }
  const last = d.last_mail || null;
  let lastText = '';
  if (last) {
    lastText = '第 ' + (last.pc || '') + ' 批：' + (last.province || '') + (last.city || '') + (last.district || '') + (last.detail_addr || '') + '（' + (last.receiver_name || '') + ' ' + (last.receiver_phone || '') + '）';
  }
  const hasRegion = !!(d.province && d.city && d.district);
  return {
    is_self_pickup: isSelf,
    is_mail: isMail,
    has_pc: !!d.pc,
    show_pending: !!(d.loaded && !d.filled),
    show_filled: !!(d.loaded && !!d.filled),
    status_summary: summary,
    has_site_addr: hasAddr,
    has_site_contact: hasContact,
    site_address: (site && site.address) || '',
    site_contact_text: contactText,
    show_site_contact_only: !!(isSelf && !hasAddr && hasContact),
    show_site_empty: !!(isSelf && !hasAddr && !hasContact),
    has_pickup_date: !!d.pickup_date,
    no_pickup_date: !d.pickup_date,
    has_last_mail: !!last,
    last_mail_text: lastText,
    has_region: hasRegion,
    no_region: !hasRegion,
    region_text: hasRegion ? (d.province + ' / ' + d.city + ' / ' + d.district) : '请选择省/市/区',
    submitting: !!d.submitting,
    not_submitting: !d.submitting,
    submit_btn_text: d.filled ? '保存修改' : '提交登记'
  };
}

createPage({
  data: {
    loaded: false,
    pc: null,
    filled: false,
    current: null,
    last_mail: null,
    pickup_site: null,
    // 表单（pickup_type 为英文枚举：self_pickup-到校领取 / mail-邮寄）
    pickup_type: 'self_pickup',
    pickup_date: '',
    receiver_name: '',
    receiver_phone: '',
    province: '',
    city: '',
    district: '',
    // region-picker 空值必须传 []（不传或传 ['', '', ''] 原生侧读 value[0] 会炸 null[0]）
    region: [],
    detail_addr: '',
    // 日期选择器
    showDatePicker: false,
    currentDate: new Date().getTime(),
    minDate: new Date(new Date().setHours(0, 0, 0, 0)).getTime(),
    maxDate: new Date(new Date().getFullYear() + 1, 11, 31).getTime(),
    submitting: false,
    // 模板派生字段（只绑简单变量，避免构建器兼容问题）
    has_pc: false,
    show_pending: false,
    show_filled: false,
    status_summary: '每个学期统计一次，提交后仍可回来修改',
    is_self_pickup: true,
    is_mail: false,
    has_site_addr: false,
    has_site_contact: false,
    site_address: '',
    site_contact_text: '',
    show_site_contact_only: false,
    show_site_empty: true,
    has_pickup_date: false,
    no_pickup_date: true,
    has_last_mail: false,
    last_mail_text: '',
    has_region: false,
    no_region: true,
    region_text: '请选择省/市/区',
    submit_btn_text: '提交登记',
    not_submitting: true
  },

  onLoad() {
    this.fetchStatus();
  },

  onShow() {
    this.fetchStatus();
  },

  fetchStatus() {
    const that = this;
    return tokenGet('/student_book_pickup/status', {}, { showLoading: this.data.loaded === false }).then(function (data) {
      const payload = data || {};
      const current = payload.current || null;
      const site = payload.pickup_site || null;
      const patch = {
        loaded: true,
        pc: payload.pc || null,
        filled: !!payload.filled,
        current: current,
        last_mail: payload.last_mail || null,
        pickup_site: site
      };
      if (current) {
        patch.pickup_type = current.pickup_type || 'self_pickup';
        patch.pickup_date = current.pickup_date || '';
        patch.receiver_name = current.receiver_name || '';
        patch.receiver_phone = current.receiver_phone || '';
        patch.province = current.province || '';
        patch.city = current.city || '';
        patch.district = current.district || '';
        patch.detail_addr = current.detail_addr || '';
        patch.region = current.province ? [current.province, current.city, current.district] : [];
        if (current.pickup_date) {
          const t = Date.parse(current.pickup_date);
          if (!isNaN(t)) patch.currentDate = t;
        }
      } else {
        patch.pickup_type = 'self_pickup';
      }
      const merged = Object.assign({}, that.data, patch);
      Object.assign(patch, buildDerived(merged));
      that.setData(patch);
    }).catch(function (err) {
      console.error('[book-pickup] 获取状态失败:', err);
      const merged = Object.assign({}, that.data, { loaded: true });
      const derived = buildDerived(merged);
      derived.loaded = true;
      that.setData(derived);
      wx.showToast({ title: (err && err.message) || '获取状态失败', icon: 'none', duration: 2000 });
    });
  },

  onTypeChange(e) {
    try {
      const ds = (e && e.currentTarget && e.currentTarget.dataset) || {};
      const type = ds.type;
      if (type !== 'self_pickup' && type !== 'mail') return;
      // 点已选中的不重复渲染（避免反复重建 picker / van-field 子树）
      if (type === this.data.pickup_type) return;
      const merged = Object.assign({}, this.data, { pickup_type: type });
      const derived = buildDerived(merged);
      derived.pickup_type = type;
      this.setData(derived);
    } catch (err) {
      console.error('[book-pickup] onTypeChange 失败:', err);
    }
  },

  onInputChange(e) {
    try {
      const ct = (e && e.currentTarget) || {};
      const field = (ct.dataset && ct.dataset.field) || '';
      if (!field) return;
      const detail = e.detail;
      const v = (detail && detail.value != null) ? String(detail.value) : (detail != null && typeof detail !== 'object' ? String(detail) : '');
      const update = {};
      update[field] = v;
      this.setData(update);
      const merged = Object.assign({}, this.data, update);
      this.setData(buildDerived(merged));
    } catch (err) {
      console.error('[book-pickup] onInputChange 失败:', err);
    }
  },

  onRegionChange(e) {
    try {
      const detail = (e && e.detail) || {};
      const raw = Array.isArray(detail.value) ? detail.value : [];
      const region = [raw[0] || '', raw[1] || '', raw[2] || ''];
      // region-picker 空值保持 []，3 空串是无效省市区，下次打开原生侧易炸
      const regionValue = (region[0] || region[1] || region[2]) ? region : [];
      const update = {
        region: regionValue,
        province: region[0] || '',
        city: region[1] || '',
        district: region[2] || ''
      };
      this.setData(update);
      const merged = Object.assign({}, this.data, update);
      this.setData(buildDerived(merged));
    } catch (err) {
      console.error('[book-pickup] onRegionChange 失败:', err);
    }
  },

  // 一键沿用上次邮寄地址
  onUseLastMail() {
    const last = this.data.last_mail;
    if (!last) return;
    const update = {
      pickup_type: 'mail',
      receiver_name: last.receiver_name || '',
      receiver_phone: last.receiver_phone || '',
      province: last.province || '',
      city: last.city || '',
      district: last.district || '',
      region: last.province ? [last.province, last.city, last.district] : ['', '', ''],
      detail_addr: last.detail_addr || ''
    };
    this.setData(update);
    const merged = Object.assign({}, this.data, update);
    this.setData(buildDerived(merged));
    wx.showToast({ title: '已填入上次地址', icon: 'success', duration: 1500 });
  },

  showDatePicker() {
    let currentDate = this.data.currentDate;
    if (this.data.pickup_date) {
      const t = Date.parse(this.data.pickup_date);
      if (!isNaN(t)) currentDate = t;
    }
    this.setData({ showDatePicker: true, currentDate: currentDate });
  },

  onDatePickerClose() {
    this.setData({ showDatePicker: false });
  },

  goHome() {
    wx.navigateTo({
      url: '/packageStudent/pages/my/my'
    });
  },

  onDatePickerConfirm(e) {
    const raw = (e && e.detail !== undefined) ? e.detail : undefined;
    let ts = raw;
    if (raw && typeof raw === 'object') {
      ts = raw.value !== undefined ? raw.value : raw.innerValue;
    }
    const date = new Date(ts);
    if (!ts || isNaN(date.getTime())) {
      this.setData({ showDatePicker: false });
      return;
    }
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, '0');
    const d = String(date.getDate()).padStart(2, '0');
    const update = {
      pickup_date: y + '-' + m + '-' + d,
      showDatePicker: false
    };
    this.setData(update);
    const merged = Object.assign({}, this.data, update);
    this.setData(buildDerived(merged));
  },

  _validate() {
    const t = this.data.pickup_type;
    if (t === 'self_pickup') {
      if (!this.data.pickup_date) return '请选择到校领取的大概日期';
      return '';
    }
    if (t === 'mail') {
      if (!this.data.receiver_name.trim()) return '请填写收件人姓名';
      if (!this.data.receiver_phone.trim()) return '请填写收件人电话';
      if (!/^1\d{10}$/.test(this.data.receiver_phone.trim())) return '收件人电话格式不正确（需11位手机号）';
      if (!this.data.province || !this.data.city || !this.data.district) return '请选择省/市/区';
      if (!this.data.detail_addr.trim()) return '请填写详细地址';
      return '';
    }
    return '领取方式不正确';
  },

  onSubmit() {
    if (this.data.submitting) return;
    const errMsg = this._validate();
    if (errMsg) {
      wx.showToast({ title: errMsg, icon: 'none', duration: 2000 });
      return;
    }
    const body = { pickup_type: this.data.pickup_type };
    if (this.data.pickup_type === 'self_pickup') {
      body.pickup_date = this.data.pickup_date;
    } else {
      body.receiver_name = this.data.receiver_name.trim();
      body.receiver_phone = this.data.receiver_phone.trim();
      body.province = this.data.province;
      body.city = this.data.city;
      body.district = this.data.district;
      body.detail_addr = this.data.detail_addr.trim();
    }
    const that = this;
    this.setData({ submitting: true, not_submitting: false });
    tokenPost('/student_book_pickup/submit', body, { loadingTitle: '提交中...' }).then(function () {
      wx.showToast({ title: '提交成功', icon: 'success', duration: 1500 });
      that.setData({ submitting: false, not_submitting: true });
      return that.fetchStatus();
    }).catch(function (err) {
      console.error('[book-pickup] 提交失败:', err);
      wx.showToast({ title: (err && err.message) || '提交失败', icon: 'none', duration: 2000 });
      that.setData({ submitting: false, not_submitting: true });
    });
  }
}, {
  requireAuth: true,
  userType: 'open_student'
});
