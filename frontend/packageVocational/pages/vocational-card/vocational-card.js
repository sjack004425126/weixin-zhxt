const { createPage } = require('../../../utils/page-mixin');
const { tokenGet } = require('../../../utils/request');
const { resolveImageUrl } = require('../../../utils/image-url');

createPage({
  data: {
    loading: true,
    cardData: null,
    error: null,
    // 翻转状态：false=正面，true=背面
    isFlipped: false,
    // 动态防伪时钟（精确到秒）
    liveDate: '',
    liveTime: '',
  },

  onLoad() {
    this._tickClock();
    this._clockTimer = setInterval(() => this._tickClock(), 1000);
    this.loadCard();
  },

  onShow() {
    this._tickClock();
    this.loadCard();
  },

  onUnload() {
    if (this._clockTimer) clearInterval(this._clockTimer);
  },

  /**
   * 动态防伪时钟（精确到秒）
   * 显示格式：yyyy.mm.dd  HH:MM:SS
   */
  _tickClock() {
    const now = new Date();
    const pad = (n) => String(n).padStart(2, '0');
    const y = now.getFullYear();
    const mo = pad(now.getMonth() + 1);
    const d = pad(now.getDate());
    const h = pad(now.getHours());
    const mi = pad(now.getMinutes());
    const s = pad(now.getSeconds());
    this.setData({
      liveDate: `${y}.${mo}.${d}`,
      liveTime: `${h}:${mi}:${s}`,
    });
  },

  onPullDownRefresh() {
    this.loadCard(() => wx.stopPullDownRefresh());
  },

  async loadCard(callback) {
    this.setData({ loading: true, error: null });
    try {
      // tokenGet 已自动解 {success,msg,data} 这层
      const data = await tokenGet('/vocational_info/get_zoudou_card');
      if (!data) {
        this.setData({ cardData: null, loading: false });
        return;
      }

      if (data.valid) {
        data._photo_url = data.photo_url
          ? resolveImageUrl(data.photo_url)
          : '';
        data._semester_text = _formatSemester(data.dq_nd, data.dq_xq);
        data.sfzh_masked = _maskIdCard(data.sfzh);

        // 设计稿固定字段（若后端未提供则用默认值）
        data.school_name_cn = data.school_name_cn || '黔东南中等职业技术学校';
        data.school_name_en = data.school_name_en || 'QIANDONGNAN SECONDARY VOCATIONAL AND TECHNICAL SCHOOL';
        data.motto = data.motto || '砺志以学 · 厚德而行';
        data.pass_no = data.pass_no || `ZD-${data.dq_nd || '2025'}-${(data.xh || '').slice(-4) || '0982'}`;
        data.valid_until = data.valid_until || _endOfSemester(data.dq_nd, data.dq_xq);
        // 班主任姓名/电话由后端从班级（oa_t.bzr_id → oa_t.t_dh）取，前端不写死默认值
        // 若后端未提供，wxml 中显示「班主任信息待补充」
      }

      this.setData({ cardData: data, loading: false });
    } catch (e) {
      this.setData({ error: '加载走读证信息失败，请下拉刷新重试', loading: false });
    } finally {
      if (typeof callback === 'function') callback();
    }
  },

  /**
   * 照片加载失败 → 回退到占位符
   */
  onPhotoError() {
    const data = this.data.cardData;
    if (!data) return;
    this.setData({ cardData: { ...data, _photo_url: '' } });
  },

  /**
   * 点击照片 → 全屏预览
   */
  onPhotoTap() {
    const url = this.data.cardData && this.data.cardData._photo_url;
    if (!url) return;
    wx.previewImage({ current: url, urls: [url], showmenu: true });
  },

  /**
   * 翻转卡片（正面 ↔ 背面）
   */
  onFlipToggle() {
    this.setData({ isFlipped: !this.data.isFlipped });
  },

  /**
   * 联系班主任（空态按钮）
   */
  onContactTeacher() {
    wx.showModal({
      title: '联系班主任',
      content: '请在班级群内联系班主任，或前往学生工作处咨询。',
      confirmText: '我知道了',
      showCancel: false,
      confirmColor: '#059669',
    });
  },

  /**
   * 重新加载（错误态按钮）
   */
  onRefresh() {
    this.loadCard();
  },

  /**
   * 点击电话号码 → 调起手机拨号
   * 安全清洗：去除空格/连字符/括号等，只保留数字和 +
   */
  onCallTeacher(e) {
    const raw = (e && e.currentTarget && e.currentTarget.dataset && e.currentTarget.dataset.phone) || '';
    const phone = String(raw).replace(/[^\d+]/g, '');
    if (!phone) {
      wx.showToast({ title: '暂无可拨号码', icon: 'none' });
      return;
    }
    wx.makePhoneCall({
      phoneNumber: phone,
      fail(err) {
        // 用户取消或不支持：静默，不弹错误遮罩
        console.warn('[vocational-card] 拨号失败/取消:', err);
      }
    });
  },
}, {
  requireAuth: true,
  userType: 'vocational_student'
});

// ---- module-private helpers ----

/**
 * 学年学期展示文字 "2025-2026学年 第1学期"
 */
function _formatSemester(nd, xq) {
  if (!nd) return '';
  const year = String(nd);
  const prevYear = nd - 1;
  const text = `${prevYear}-${year}学年`;
  if (xq !== null && xq !== undefined && xq !== '') {
    return `${text} 第${xq}学期`;
  }
  return text;
}

/**
 * 身份证号脱敏：522601********0247
 */
function _maskIdCard(id) {
  if (!id) return '';
  const s = String(id).trim();
  if (s.length <= 10) return s;
  const head = s.slice(0, 6);
  const tail = s.slice(-4);
  const starCount = Math.min(s.length - 10, 8);
  return head + '*'.repeat(starCount) + tail;
}

/**
 * 默认有效截止：本学期结束
 * 第1学期 → 次年1月20日；第2学期 → 当年7月10日
 */
function _endOfSemester(nd, xq) {
  if (!nd) return '2026-01-20';
  if (xq === 2) return `${nd}-07-10`;
  return `${nd + 1}-01-20`;
}
