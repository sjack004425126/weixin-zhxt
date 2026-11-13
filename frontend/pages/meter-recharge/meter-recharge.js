/**
 * 电表充值页面 v3（跳转模式）
 *
 * 流程：
 *  1. 用户输入电表名称
 *  2. debounce 300ms 触发后端模糊搜索
 *  3. 命中后显示电表信息卡片 + 「跳转充值」按钮
 *     → 调 wx.navigateToMiniProgram 跳转目标小程序充值页
 */
const { createPage } = require('../../utils/page-mixin');
const http = require('../../utils/request');

const SEARCH_DEBOUNCE_MS = 300;
const MIN_QUERY_LEN = 1;

// 目标小程序 appId（贵州智学堂 / 充值小程序）
const TARGET_APP_ID = 'wx5fb830b234320db1';
const TARGET_PATH_TPL = 'pages/tenant/deviceDetail/deviceDetail'; // ?sn= 在运行时拼接

createPage({
  data: {
    houseName: '',
    hasSearched: false,
    lastQuery: '',
    meter: null,        // 后端返回的电表对象
    searching: false,
    jumping: false,    // 跳转进行中
  },

  _debounceTimer: null,
  _seq: 0,

  onLoad() {},

  onShareAppMessage() {
    return {
      title: '电表充值 - 输入电表名称跳转充值',
      path: '/pages/meter-recharge/meter-recharge'
    };
  },

  // ============================================================
  // 输入区交互
  // ============================================================
  onHouseNameInput(e) {
    const raw = (e.detail.value || '').trimStart();
    const value = raw.toUpperCase();
    this.setData({ houseName: value });

    if (!value) {
      if (this._debounceTimer) clearTimeout(this._debounceTimer);
      this._seq++;
      this.setData({
        hasSearched: false,
        lastQuery: '',
        meter: null,
        searching: false,
      });
      return;
    }
    if (value.length < MIN_QUERY_LEN) return;

    if (this._debounceTimer) clearTimeout(this._debounceTimer);
    this._debounceTimer = setTimeout(() => this._doSearch(value), SEARCH_DEBOUNCE_MS);
  },

  onConfirm(e) {
    const value = (e && e.detail && e.detail.value) || this.data.houseName;
    if (this._debounceTimer) clearTimeout(this._debounceTimer);
    if (value && value.length >= MIN_QUERY_LEN) this._doSearch(value);
  },

  onClear() {
    if (this._debounceTimer) clearTimeout(this._debounceTimer);
    this._seq++;
    this.setData({
      houseName: '',
      hasSearched: false,
      lastQuery: '',
      meter: null,
      searching: false,
      jumping: false,
    });
  },

  // ============================================================
  // 搜索（带竞态保护）
  // ============================================================
  async _doSearch(query) {
    const q = (query || '').trim();
    if (!q) return;

    const mySeq = ++this._seq;
    this.setData({
      hasSearched: true,
      lastQuery: q,
      searching: true,
      meter: null,
      jumping: false,
    });

    try {
      const res = await http.get(
        '/dianbiao/by-house-name',
        { house_name: q },
        { showLoading: false, timeout: 15000 }
      );
      if (mySeq !== this._seq) return;

      // request.js 已自动解包 success→data，res 即 data（对象或 null）
      this.setData({ meter: res || null, searching: false });
    } catch (err) {
      if (mySeq !== this._seq) return;
      this.setData({ meter: null, searching: false });
    }
  },

  // ============================================================
  // 跳转充值
  // ============================================================
  onJumpToRecharge() {
    const meter = this.data.meter;
    if (!meter || !meter.sn) return;

    const sn = meter.sn;
    const finalPath = `${TARGET_PATH_TPL}?sn=${encodeURIComponent(sn)}`;
    const extraData = {
      sn,
      device_id: meter.device_id,
      id: meter.device_id,
    };

    this.setData({ jumping: true });

    if (typeof wx.navigateToMiniProgram !== 'function') {
      this.setData({ jumping: false });
      return;
    }

    wx.navigateToMiniProgram({
      appId: TARGET_APP_ID,
      path: finalPath,
      extraData,
      envVersion: 'release',
      success: () => this.setData({ jumping: false }),
      fail: () => this.setData({ jumping: false }),
      complete: () => this.setData({ jumping: false }),
    });
  },

  onUnload() {
    if (this._debounceTimer) clearTimeout(this._debounceTimer);
  },
});
