const { createPage } = require('../../../utils/page-mixin');
const { tokenGet, tokenPost } = require('../../../utils/request');
const { resolveImageUrl } = require('../../../utils/image-url');

// 教师端预约管理台（纯预约制 - 按天卡片式排号优化版）
// 2 视图：预约名单 / 号段排班
// - 预约名单：按天卡片展示排号与预约人员，一眼看出哪天几个号，点击卡片查看学生全部档案
// - 号段排班：新增号段（可单独指定日期与咨询地点）、删除号段、结束号段
createPage({
  data: {
    scheduleId: null,
    loading: true,
    pageMode: 'list',           // list | slots
    detail: null,
    dayGroups: [],              // 按天统计排号：包含 total_quota、total_booked、weekday 等
    activeDayDate: '',          // 当前高亮选中的日期
    remark: '',
    // 学生档案卡片
    showProfile: false,
    profileLoading: false,
    profileBooking: null,
    profileSlot: null,
    profile: null,
    // 新增号段表单
    newSlotDate: '',
    newSlotStart: '',
    newSlotEnd: '',
    newSlotQuota: 2,
    newSlotCategory: '',        // 咨询项目类别：由教师自行填写
    newSlotLocation: ''         // 咨询地点：号段级自定义
  },

  onLoad(options) {
    const id = options.id ? parseInt(options.id) : null;
    this.setData({ scheduleId: id });
    this.ensureDesk();
  },
  onShow() {
    if (this.data.timer) clearInterval(this.data.timer);
    const t = setInterval(() => { if (this.data.scheduleId) this.loadDetail(true); }, 8000);
    this.setData({ timer: t });
    // 直进无 id 时补拉一次
    if (!this.data.scheduleId) this.ensureDesk();
  },
  onHide() { if (this.data.timer) clearInterval(this.data.timer); },
  onUnload() { if (this.data.timer) clearInterval(this.data.timer); },

  async ensureDesk() {
    // 直进模式：无 id 时自动获取当前台（tokenGet 直接返回 data）
    if (this.data.scheduleId) { this.loadDetail(); return; }
    this.setData({ loading: true });
    try {
      const res = await tokenGet('/counsel/teacher/desk', {}, { showLoading: false });
      const sid = res && res.schedule_id;
      if (sid) {
        this.setData({ scheduleId: sid });
        this.loadDetail();
      } else {
        this.setData({ loading: false });
        this.showError('获取管理台失败');
      }
    } catch (e) {
      this.setData({ loading: false });
      this.showError((typeof e === 'string' ? e : (e && e.message)) || '获取管理台失败');
    }
  },

  // 计算星期几
  calcWeekday(dateStr) {
    if (!dateStr) return '';
    try {
      const parts = dateStr.split('-');
      if (parts.length === 3) {
        const d = new Date(parseInt(parts[0], 10), parseInt(parts[1], 10) - 1, parseInt(parts[2], 10));
        const days = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];
        return days[d.getDay()] || '';
      }
    } catch (err) {
      // ignore
    }
    return '';
  },

  // 格式化月-日
  calcShortDate(dateStr) {
    if (!dateStr) return '';
    const parts = dateStr.split('-');
    if (parts.length === 3) {
      return `${parseInt(parts[1], 10)}月${parseInt(parts[2], 10)}日`;
    }
    return dateStr;
  },

  async loadDetail(silent) {
    if (!silent) this.setData({ loading: true });
    try {
      const res = await tokenGet('/counsel/teacher/schedule/detail', { schedule_id: this.data.scheduleId }, { showLoading: false });
      const d = res || {};
      d.slots = d.slots || [];

      // 预计算展示字段，避免 WXML 三元/&& 触发渲染层崩溃
      d.slots.forEach(sl => {
        sl.tickets = sl.tickets || [];
        sl.status_text = sl.status === 'open' ? '可预约' : (sl.status === 'full' ? '已约满' : '已结束');
        sl.tickets.forEach(t => {
          t.status_text = t.status === 'booked' ? '待咨询' : (t.status === 'attended' ? '已咨询' : '已取消');
        });
      });

      // 按天分组：卡片式排号聚合，一眼看出哪天几个号
      const groups = [];
      const gmap = {};
      d.slots.forEach(sl => {
        const k = sl.counsel_date || '未定日期';
        if (!gmap[k]) {
          gmap[k] = {
            date: k,
            weekday: this.calcWeekday(k),
            shortDate: this.calcShortDate(k),
            slots: [],
            total_quota: 0,
            total_booked: 0,
            total_tickets: 0
          };
          groups.push(gmap[k]);
        }
        gmap[k].slots.push(sl);
        gmap[k].total_quota += (Number(sl.quota) || 0);
        gmap[k].total_booked += (Number(sl.booked) || 0);
        gmap[k].total_tickets += (sl.tickets ? sl.tickets.length : 0);
      });
      groups.sort((a, b) => String(a.date).localeCompare(String(b.date)));

      const patch = {
        detail: d,
        dayGroups: groups,
        loading: false,
        activeDayDate: this.data.activeDayDate || (groups[0] ? groups[0].date : '')
      };
      if (!this.data.newSlotDate) {
        const now = new Date();
        const pad = (n) => String(n).padStart(2, '0');
        patch.newSlotDate = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
      }

      this.setData(patch);
    } catch (e) {
      this.setData({ loading: false });
      if (!silent) this.showError((typeof e === 'string' ? e : (e && e.message)) || '加载失败');
    }
  },

  // 快捷定位到指定日期的排号卡片
  scrollToDay(e) {
    const { date } = e.currentTarget.dataset;
    this.setData({ activeDayDate: date });
    wx.pageScrollTo({
      selector: `#day-${date}`,
      offsetTop: -70,
      duration: 300
    });
  },

  // ---------- 视图切换 ----------
  setPageMode(e) {
    this.setData({ pageMode: e.currentTarget.dataset.mode });
  },

  // ---------- 预约人员卡片 ----------
  noop() {},
  async openProfile(e) {
    const { id } = e.currentTarget.dataset;
    this.setData({ showProfile: true, profileLoading: true, profileBooking: null, profileSlot: null, profile: null });
    try {
      const res = await tokenGet('/counsel/teacher/booking/profile', { booking_id: id }, { showLoading: false });
      const r = res || {};
      const stu = r.student || {};
      if (stu.photo_url) stu.photo_url_full = resolveImageUrl(stu.photo_url);
      this.setData({
        profileLoading: false,
        profileBooking: r.booking || null,
        profileSlot: r.slot || null,
        profile: stu,
      });
    } catch (err) {
      this.setData({ profileLoading: false });
      this.showError((typeof err === 'string' ? err : (err && err.message)) || '加载档案失败');
    }
  },
  closeProfile() { this.setData({ showProfile: false }); },
  previewProfilePhoto() {
    const url = this.data.profile && this.data.profile.photo_url_full;
    if (url) wx.previewImage({ urls: [url] });
  },
  callProfilePhone(e) {
    const { phone } = e.currentTarget.dataset;
    if (!phone) { this.showWarning('暂无联系电话'); return; }
    wx.makePhoneCall({ phoneNumber: phone });
  },
  async cancelBookingFromProfile() {
    const b = this.data.profileBooking;
    if (!b) return;
    const code = b.display_no || '';
    wx.showModal({
      title: '取消预约', content: `确定取消 ${code} 的预约吗？取消后号源自动释放。`,
      success: async (r) => {
        if (!r.confirm) return;
        try {
          await tokenPost('/counsel/teacher/booking/mark', { booking_id: b.id || b.booking_id, status: 'cancelled' }, { showLoading: false });
          this.showSuccess('已取消该预约');
          this.setData({ showProfile: false });
          this.loadDetail(true);
        } catch (err) { this.showError((typeof err === 'string' ? err : (err && err.message)) || '取消失败'); }
      }
    });
  },

  // ---------- 预约名单操作 ----------
  async markAttended(e) {
    const { id } = e.currentTarget.dataset;
    try {
      await tokenPost('/counsel/teacher/booking/mark', { booking_id: id, status: 'attended' }, { showLoading: false });
      this.showSuccess('已标记为已咨询');
      this.loadDetail(true);
    } catch (err) { this.showError((typeof err === 'string' ? err : (err && err.message)) || '操作失败'); }
  },
  async markMissed(e) {
    const { id, code } = e.currentTarget.dataset;
    wx.showModal({
      title: '标记未赴约', content: `确定将 ${code} 标记为未赴约（作废）吗？`,
      success: async (r) => {
        if (!r.confirm) return;
        try {
          await tokenPost('/counsel/teacher/booking/mark', { booking_id: id, status: 'cancelled' }, { showLoading: false });
          this.showSuccess('已标记为未赴约');
          this.loadDetail(true);
        } catch (err) { this.showError((typeof err === 'string' ? err : (err && err.message)) || '操作失败'); }
      }
    });
  },
  onRemarkInput(e) {
    const { id } = e.currentTarget.dataset;
    const v = typeof e.detail === 'string' ? e.detail : e.detail.value;
    const detail = this.data.detail;
    (detail.slots || []).forEach(sl => {
      (sl.tickets || []).forEach(t => {
        if (String(t.id) === String(id)) t.remark = v;
      });
    });
    this.setData({ detail });
  },
  async saveRemark(e) {
    const { id } = e.currentTarget.dataset;
    const detail = this.data.detail;
    let remark = '';
    (detail.slots || []).forEach(sl => {
      (sl.tickets || []).forEach(t => { if (String(t.id) === String(id)) remark = t.remark || ''; });
    });
    try {
      await tokenPost('/counsel/teacher/remark', { booking_id: id, remark: remark }, { showLoading: false });
      this.showSuccess('备注已保存（学生不可见）');
      this.loadDetail(true);
    } catch (err) { this.showError((typeof err === 'string' ? err : (err && err.message)) || '保存失败'); }
  },

  // ---------- 号段排班 ----------
  onNewSlotInput(e) {
    const { field } = e.currentTarget.dataset;
    const v = typeof e.detail === 'string' ? e.detail : e.detail.value;
    this.setData({ [field]: field === 'newSlotQuota' ? (parseInt(v, 10) || 0) : v });
  },
  onNewSlotDateChange(e) { this.setData({ newSlotDate: e.detail.value }); },
  async submitNewSlot() {
    const { newSlotDate, newSlotStart, newSlotEnd, newSlotQuota, newSlotCategory, newSlotLocation } = this.data;
    if (!newSlotDate) { this.showWarning('请选择咨询日期'); return; }
    if (!newSlotStart || !newSlotEnd) { this.showWarning('请填写号段起止时间'); return; }
    if (!newSlotQuota) { this.showWarning('请填写放号数量'); return; }
    const category = String(newSlotCategory || '').trim();
    if (!category) { this.showWarning('请填写咨询项目类别'); return; }
    try {
      await tokenPost('/counsel/teacher/slot/add', {
        schedule_id: this.data.scheduleId,
        counsel_date: newSlotDate,
        start_time: newSlotStart,
        end_time: newSlotEnd,
        quota: newSlotQuota,
        category,
        location: String(newSlotLocation || '').trim()
      }, { showLoading: false });
      this.showSuccess('号段已发布');
      this.setData({
        newSlotStart: '', newSlotEnd: '', newSlotQuota: 2,
        newSlotCategory: '', newSlotLocation: ''
      });
      this.loadDetail(true);
    } catch (e) { this.showError((typeof e === 'string' ? e : (e && e.message)) || '发布失败'); }
  },
  async deleteSlot(e) {
    const { id, tag, date } = e.currentTarget.dataset;
    wx.showModal({
      title: '删除空号段', content: `确定删除 ${date || ''} ${tag} 段吗？仅无预约可删，有预约请用「结束此号段」。`,
      success: async (r) => {
        if (!r.confirm) return;
        try {
          await tokenPost('/counsel/teacher/slot/delete', { schedule_id: this.data.scheduleId, slot_id: id }, { showLoading: false });
          this.showSuccess('号段已删除');
          this.loadDetail(true);
        } catch (e) { this.showError((typeof e === 'string' ? e : (e && e.message)) || '删除失败'); }
      }
    });
  },
  async settleSlot(e) {
    const { id, tag, date } = e.currentTarget.dataset;
    wx.showModal({
      title: '结束此号段', content: `结束 ${date || ''} ${tag} 段？该段未赴约的预约将自动作废（可重约），已咨询不受影响。`,
      success: async (r) => {
        if (!r.confirm) return;
        try {
          const res = await tokenPost('/counsel/teacher/slot/settle', { schedule_id: this.data.scheduleId, slot_id: id }, { showLoading: false });
          this.showSuccess((res && res.msg) || '已结束');
          this.loadDetail(true);
        } catch (e) { this.showError((typeof e === 'string' ? e : (e && e.message)) || '操作失败'); }
      }
    });
  },

  goBack() { wx.navigateBack(); }
}, { requireAuth: true, userType: 'vocational_teacher' });
