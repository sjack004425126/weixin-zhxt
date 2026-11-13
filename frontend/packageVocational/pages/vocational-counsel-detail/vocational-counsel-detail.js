const { createPage } = require('../../../utils/page-mixin');
const { tokenGet, tokenPost } = require('../../../utils/request');

// 心理咨询预约（纯预约制）
// 客户端 2 张卡：我的预约 / 预约咨询时段
// 不再有候诊排队看板、不再扫码签到、不再叫号提醒
createPage({
  data: {
    scheduleId: null,
    loading: true,
    board: null,
    mine: null,
    booking: false,
    phoneSuffix: '',
    showQuickRegister: false,
    timer: null
  },

  onLoad(options) {
    const id = options.id ? parseInt(options.id) : null;
    this.setData({ scheduleId: id });
    if (id) this.refresh();
  },
  onShow() {
    if (this.data.timer) clearInterval(this.data.timer);
    const t = setInterval(() => { if (this.data.scheduleId) this.refresh(true); }, 8000);
    this.setData({ timer: t });
  },
  onHide() { if (this.data.timer) clearInterval(this.data.timer); },
  onUnload() { if (this.data.timer) clearInterval(this.data.timer); },

  async refresh(silent) {
    if (!silent) this.setData({ loading: true });
    try {
      const [board, my] = await Promise.all([
        tokenGet('/counsel/board', { schedule_id: this.data.scheduleId }, { showLoading: false }),
        tokenGet('/counsel/my_ticket', { schedule_id: this.data.scheduleId }, { showLoading: false })
      ]);
      const b = board || {};
      // 场次已结束（老师已开新台）：自动跳到该老师最新可约场次，避免停留在老场次
      const st = String(b.status || '');
      if (st && st !== 'published' && st !== 'calling') {
        try {
          const list = await tokenGet('/counsel/open_list', {}, { showLoading: false }) || [];
          const sameDoctor = list.filter(x => String(x.doctor_name || '') === String(b.doctor_name || ''));
          const target = (sameDoctor.length ? sameDoctor : list)[0];
          if (target && target.id && target.id !== this.data.scheduleId) {
            this.setData({ scheduleId: target.id });
            this.refresh(true);
            return;
          }
        } catch (e) { /* 忽略自动跳转失败，继续展示已结束提示 */ }
      }
      b.slots = b.slots || [];
      const mine = (my && my.mine) || null;
      const hasActive = !!(my && my.has_active);
      const activeNo = (my && my.active_no) || '';

      // 号段：可约标记（仅 2 天内含当天可点，后端同样强校验）
      // 新规则：只有「未完成预约中（booked 且号段未过期）」才锁死；
      // 已咨询 attended / 已取消 cancelled / 已过期都可重新预约
      // 同段已占（mine.slot_id）单独提示“已预约”，避免重复点撞唯一索引 500
      b.slots.forEach(s => {
        const within = s.within_advance !== undefined ? !!s.within_advance : true;
        const bookable = (typeof s.bookable === 'boolean') ? s.bookable : ((s.left || 0) > 0 && s.status === 'open' && within);
        const isMySlot = !!(mine && mine.slot_id === s.id && mine.status !== 'cancelled');
        s.can_book = !!bookable && !hasActive && !isMySlot;
        s.within_advance = within;
        if (isMySlot) {
          s.limit_text = mine.status === 'attended' ? '已咨询' : '已预约';
        } else if (hasActive) {
          s.limit_text = `您已有未完成预约 ${activeNo}`;
        } else if (!within && (s.days_ahead || 0) > 2) {
          s.limit_text = '仅支持提前2天内预约';
        } else if ((s.days_ahead || 0) < 0) {
          s.limit_text = '已过期';
        } else {
          s.limit_text = '';
        }
      });

      this.setData({ board: b, mine, hasActive, activeNo, loading: false });
    } catch (e) {
      this.setData({ loading: false });
      if (!silent) this.showError((typeof e === 'string' ? e : (e && e.message)) || '加载失败');
    }
  },

  // ---------- 预约 ----------
  async bookSlot(e) {
    if (this.data.booking) return;
    const { id, tag } = e.currentTarget.dataset;
    wx.showModal({
      title: '确认预约',
      content: `确定预约 ${tag} 段吗？预约成功后您的号码牌即为该段咨询顺序。`,
      success: async (r) => {
        if (!r.confirm) return;
        this.setData({ booking: true });
        try {
          const res = await tokenPost('/counsel/book', { slot_id: id, phone_suffix: this.data.phoneSuffix }, { showLoading: false });
          this.showSuccess((res && res.msg) || '预约成功');
          this.refresh(true);
        } catch (err) { this.showError((typeof err === 'string' ? err : (err && err.message)) || '预约失败'); }
        finally { this.setData({ booking: false }); }
      }
    });
  },
  onPhoneInput(e) { this.setData({ phoneSuffix: String(e.detail.value || '').replace(/\D/g, '').slice(0, 4) }); },
  toggleQuickRegister() { this.setData({ showQuickRegister: !this.data.showQuickRegister }); },

  goBack() { wx.navigateBack(); }
}, { requireAuth: true, userType: 'vocational_student' });
