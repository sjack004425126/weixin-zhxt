const { createPage } = require('../../utils/page-mixin');
const { STATIC_IMAGES } = require('../../utils/static-images');

createPage({
  data: {
    heroBg: STATIC_IMAGES.homeBg,
    content: {
      title: "黔东南开放大学简介",
      honors: [
        "五好基层党组织",
        "党建工作先进单位",
        "五四红旗团委",
        "脱贫攻坚优秀帮扶单位",
        "全省电大系统招生先进单位",
        "全省电大系统教务工作先进单位"
      ]
    },
    // 统计数字动画
    animYear: 0,
    animGraduates: 0,
    animStudents: 0,
    animTraining: 0,
    showBackTop: false
  },

  onLoad() {
    this.animateStats();
  },

  onShow() {
    wx.setNavigationBarTitle({ title: '学校简介' });
  },

  // 数字滚动动画
  animateStats() {
    if (this._animTimer) clearInterval(this._animTimer);

    this.setData({
      animYear: 0,
      animGraduates: 0,
      animStudents: 0,
      animTraining: 0
    });

    const targets = { year: 1979, graduates: 48000, students: 10000, training: 5000 };
    const duration = 1800;
    const fps = 30;
    const totalFrames = Math.ceil(duration / (1000 / fps));
    let frame = 0;

    this._animTimer = setInterval(() => {
      frame++;
      const t = frame / totalFrames;
      const ease = 1 - Math.pow(1 - t, 3);

      this.setData({
        animYear: Math.round(ease * targets.year),
        animGraduates: Math.round(ease * targets.graduates),
        animStudents: Math.round(ease * targets.students),
        animTraining: Math.round(ease * targets.training)
      });

      if (frame >= totalFrames) {
        clearInterval(this._animTimer);
        this._animTimer = null;
        this.setData({
          animYear: targets.year,
          animGraduates: targets.graduates,
          animStudents: targets.students,
          animTraining: targets.training
        });
      }
    }, 1000 / fps);
  },

  // 点击统计区域重播动画
  replayStatsAnimation() {
    this.animateStats();
    wx.vibrateShort();
  },

  // 页面滚动
  onPageScroll(e) {
    const scrollTop = e.detail.scrollTop;
    const show = scrollTop > 600;
    if (show !== this.data.showBackTop) {
      this.setData({ showBackTop: show });
    }
  },

  // 复制联系信息
  copyContact(e) {
    const text = e.currentTarget.dataset.text;
    wx.setClipboardData({
      data: text,
      success: () => {
        this.showSuccess('已复制到剪贴板');
      }
    });
  },

  // 返回顶部
  scrollToTop() {
    wx.pageScrollTo({ scrollTop: 0, duration: 400 });
    wx.vibrateShort();
  },

  onUnload() {
    if (this._animTimer) clearInterval(this._animTimer);
  },

  onShareAppMessage() {
    return {
      title: '黔东南开放大学简介',
      path: '/pages/intro/intro'
    };
  },

  onShareTimeline() {
    return {
      title: '黔东南开放大学简介'
    };
  }
});
