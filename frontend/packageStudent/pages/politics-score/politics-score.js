const { createPage } = require('../../../utils/page-mixin');
const { tokenGet } = require('../../../utils/request');

createPage({
  data: {
    scoreInfo: null,
  },

  onLoad() {
    this.fetchPoliticsScores();
  },

  // 解析学期格式
  parseSemester(semester) {
    const year = semester.toString().substring(0, 2);
    const type = semester.toString().slice(-1);
    return `${year}年${type === "3" ? "春季" : "秋季"}学期`;
  },

  async fetchPoliticsScores() {
    try {
      const res = await tokenGet('/student/get_politics_scores', {}, { loadingTitle: '获取形势与政策成绩...' });

      const processedData = {
        ...res,
        scores: res.scores.map((score) => ({
          ...score,
          semesterText: this.parseSemester(score.semester),
        })),
      };

      this.setData({ scoreInfo: processedData });
    } catch (err) {
      this.showError(err.message || '获取形势与政策成绩失败');
    }
  },

  goHome() {
    wx.switchTab({ url: '/pages/home/home' });
  },

  onPullDownRefresh() {
    this.fetchPoliticsScores().then(() => wx.stopPullDownRefresh());
  },
}, {
  requireAuth: true
});
