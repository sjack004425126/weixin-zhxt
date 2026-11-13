const { createPage } = require('../../../utils/page-mixin');
const { tokenGet, tokenPost } = require('../../../utils/request');

createPage({
  data: {
    kc_id: '',
    kcmc: '',
    questionList: [],
    currentQIndex: 0,       // 当前题目索引
    currentQuestion: null,

    answerList: [],         // 当前题目所有答案
    currentAIndex: 0,       // 当前学生索引
    currentAnswer: null,    // 当前展示的学生答案

    loadingAnswers: false,
    onlyPending: false,
    reviewedCount: 0,
    pendingCount: 0,

    inputScore: '',         // 自定义分数输入
    inputFocus: false,
    submitting: false,
    showAnswerCard: false,
    showQuestionPopup: false,
    questionDetail: null,
  },

  onLoad(options) {
    const app = getApp();
    const startIndex = parseInt(options.start_index || '0');
    const kc_id = options.kc_id || '';
    // 优先从 globalData 缓存读取题目列表，避免 URL 参数过长被截断
    const cached = (app.globalData._reviewGradeCache && app.globalData._reviewGradeCache[kc_id]) || [];
    const questionList = cached.length > 0 ? cached : [];
    this.setData({
      kc_id,
      kcmc: decodeURIComponent(options.kcmc || ''),
      questionList,
      currentQIndex: startIndex,
      currentQuestion: questionList[startIndex] || null,
    });
    this.loadAnswers();
  },

  async loadAnswers() {
    const { kc_id, currentQuestion, onlyPending } = this.data;
    if (!currentQuestion) return;
    this.setData({ loadingAnswers: true, answerList: [], currentAIndex: 0, currentAnswer: null, inputScore: '' });
    try {
      const data = await tokenGet('/open_teacher/review/answers', {
        kc_id,
        tm_id: currentQuestion.tm_id,
        tm_index: currentQuestion.tm_index,
        only_pending: onlyPending ? 1 : 0,
        page: 1,
        page_size: 500,
      }, { showLoading: false });

      const list = (data.answers || []).map(a => ({
        ...a,
        inputScore: a.current_score !== null && a.current_score !== undefined
          ? String(parseInt(a.current_score)) : '',
      }));

      const reviewed = list.filter(a => a.this_scored).length;
      const pending = list.filter(a => !a.this_scored).length;

      this.setData({
        answerList: list,
        currentAIndex: 0,
        currentAnswer: list[0] || null,
        reviewedCount: reviewed,
        pendingCount: pending,
        loadingAnswers: false,
        inputScore: list[0] ? (list[0].inputScore || '') : '',
      });
    } catch (e) {
      this.setData({ loadingAnswers: false });
      this.showError('获取答案失败');
    }
  },

  _goToAnswer(idx) {
    const list = this.data.answerList;
    if (idx < 0 || idx >= list.length) return;
    const item = list[idx];
    this.setData({
      currentAIndex: idx,
      currentAnswer: item,
      inputScore: item.inputScore || '',
      inputFocus: false,
    });
  },

  prevAnswer() { this._goToAnswer(this.data.currentAIndex - 1); },
  nextAnswer() { this._goToAnswer(this.data.currentAIndex + 1); },

  // 跳到下一个未评阅的学生
  nextUnscoredAnswer() {
    const list = this.data.answerList;
    const start = this.data.currentAIndex + 1;
    for (let i = start; i < list.length; i++) {
      if (!list[i].this_scored) { this._goToAnswer(i); return; }
    }
    // 从头找
    for (let i = 0; i < start; i++) {
      if (!list[i].this_scored) { this._goToAnswer(i); return; }
    }
    this.showSuccess('所有答案已评阅完成');
  },

  goToAnswer(e) {
    this._goToAnswer(e.currentTarget.dataset.idx);
    this.setData({ showAnswerCard: false });
  },

  toggleAnswerCard() {
    this.setData({ showAnswerCard: !this.data.showAnswerCard });
  },

  toggleQuestionPopup() {
    const willShow = !this.data.showQuestionPopup;
    this.setData({ showQuestionPopup: willShow });
    // 打开时才加载，且没有缓存时才请求
    if (willShow && !this.data.questionDetail) {
      this.loadQuestionDetail();
    }
  },

  async loadQuestionDetail() {
    const { currentQuestion } = this.data;
    if (!currentQuestion) return;
    try {
      const res = await tokenGet('/open_teacher/review/question_detail', {
        tm_id: currentQuestion.tm_id,
      }, { showLoading: false });
      this.setData({ questionDetail: res || null });
    } catch (e) {
      this.setData({ questionDetail: null });
    }
  },

  stopProp() {},

  toggleOnlyPending() {
    this.setData({ onlyPending: !this.data.onlyPending });
    this.loadAnswers();
  },

  // 题目切换
  prevQuestion() {
    if (this.data.currentQIndex <= 0) return;
    const idx = this.data.currentQIndex - 1;
    this.setData({ currentQIndex: idx, currentQuestion: this.data.questionList[idx], showAnswerCard: false, questionDetail: null });
    this.loadAnswers();
  },

  nextQuestion() {
    if (this.data.currentQIndex >= this.data.questionList.length - 1) return;
    const idx = this.data.currentQIndex + 1;
    this.setData({ currentQIndex: idx, currentQuestion: this.data.questionList[idx], showAnswerCard: false, questionDetail: null });
    this.loadAnswers();
  },

  // 快捷评分
  async onQuickScore(e) {
    const score = e.currentTarget.dataset.score;
    this.setData({ inputScore: String(score) });
    await this._doScore(score);
  },

  onScoreInput(e) {
    this.setData({ inputScore: e.detail.value });
  },

  async onConfirmScore() {
    const score = parseFloat(this.data.inputScore);
    if (isNaN(score) || score < 0) { this.showError('请输入有效分数'); return; }
    await this._doScore(score);
  },

  async _doScore(score) {
    if (this.data.submitting) return;
    const item = this.data.currentAnswer;
    if (!item) return;
    if (item.is_locked) { this.showError('该答卷已锁定，不可修改'); return; }
    if (score > item.fz) { this.showError(`不能超过满分 ${item.fz} 分`); return; }

    this.setData({ submitting: true });
    try {
      const res = await tokenPost('/open_teacher/review/score', {
        record_id: item.record_id,
        tm_index: item.tm_index,
        score,
      });
      this.showSuccess("本题赋分完成。")
      const idx = this.data.currentAIndex;
      const allScored = res.data && res.data.all_scored;
      const updatedItem = {
        ...item,
        current_score: score,
        this_scored: true,
        inputScore: String(parseInt(score)),
        is_locked: allScored,
      };

      const list = [...this.data.answerList];
      list[idx] = updatedItem;
      const reviewed = list.filter(a => a.this_scored).length;
      const pending = list.filter(a => !a.this_scored).length;

      this.setData({
        answerList: list,
        currentAnswer: updatedItem,
        reviewedCount: reviewed,
        pendingCount: pending,
        submitting: false,
      });

      // 自动跳到下一个未评阅
      const nextIdx = list.findIndex((a, i) => i > idx && !a.this_scored);
      if (nextIdx >= 0) {
        setTimeout(() => this._goToAnswer(nextIdx), 300);
      }
    } catch (e) {
      this.setData({ submitting: false });
      this.showError(e.message || '评分失败');
    }
  },

  goBack() { wx.navigateBack(); }
}, {
  requireAuth: true,
  userType: 'open_teacher'
});
