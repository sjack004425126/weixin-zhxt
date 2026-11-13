const { createPage } = require('../../../utils/page-mixin');
const { tokenGet, tokenPost } = require('../../../utils/request');
const { API } = require('../../../utils/api');

/**
 * 考试答题页（exame 考试系统）
 *
 * 流程：
 *  1. onLoad：判断是否带 record_id（继续答题），否则调 start 创建/复用 record
 *  2. start 返回题目列表（含 record_id）
 *  3. 用户作答 → 本地 state 保存
 *  4. submit：调 /exame/exams/submit 提交
 */
createPage({
  data: {
    examId: null,
    recordId: null,
    exam: null,
    questions: [],
    currentIndex: 0,
    countdown: 60 * 60,
    countdownStr: '',
    _timer: null,
    isSubmitting: false,
    loading: true,
    submitting: false,
  },

  async onLoad(options) {
    const examId = Number(options.exam_id);
    if (!examId) {
      this.showError('缺少参数');
      return;
    }
    this.setData({ examId });

    if (options.record_id) {
      // 继续答题：根据 record_id 拉题目
      this.setData({ recordId: Number(options.record_id) });
      await this.loadPaperByRecord();
    } else {
      // 新开：调 start 创建/复用
      await this.startExam();
    }
  },

  onUnload() {
    if (this.data._timer) {
      clearInterval(this.data._timer);
    }
  },

  async startExam() {
    try {
      const resp = await tokenPost(
        API.EXAME_PAPER.START_EXAME,
        { exam_id: this.data.examId },
        { loadingTitle: '准备试卷...' }
      );
      const data = resp && resp.data ? resp.data : resp;
      if (!data || !data.record_id) {
        this.showError('开始考试失败');
        return;
      }
      const questions = (data.questions || []).map((q, idx) => this._normalizeQuestion(q, idx));
      this.setData({
        recordId: data.record_id,
        exam: data.exam || null,
        questions,
        countdown: (data.duration || 60) * 60,
        loading: false,
      }, () => this._startTimer());
    } catch (err) {
      this.setData({ loading: false });
      this.showError(err.message || '开始考试失败');
    }
  },

  async loadPaperByRecord() {
    // exame 没有"按 record 拉题目"的接口，所以仍走 start；后端会复用进行中记录
    return this.startExam();
  },

  _normalizeQuestion(q, idx) {
    // 题型归一化为前端易用结构
    // type: 1=单选 2=多选 3=判断 4=填空 5=简答
    const typeMap = { 1: '单选题', 2: '多选题', 3: '判断题', 4: '填空题', 5: '简答题' };
    const options = (q.options || []).map(o => ({
      id: o.id,
      label: o.label,
      content: o.content,
      selected: false,
    }));
    return {
      id: q.id,
      type: typeMap[q.type] || '未知',
      content: q.content || '',
      options,
      answerText: '',
      score: q.score || 0,
      order: idx + 1,
      answered: false,
    };
  },

  _startTimer() {
    if (this.data._timer) clearInterval(this.data._timer);
    const tick = () => {
      let c = this.data.countdown - 1;
      if (c <= 0) {
        clearInterval(this.data._timer);
        this.showError('考试时间到，系统将自动交卷');
        setTimeout(() => this.submitPaper(true), 1000);
        return;
      }
      const h = Math.floor(c / 3600);
      const m = Math.floor((c % 3600) / 60);
      const s = c % 60;
      const pad = (n) => (n < 10 ? '0' + n : '' + n);
      this.setData({
        countdown: c,
        countdownStr: `${pad(h)}:${pad(m)}:${pad(s)}`,
      });
    };
    tick();
    this.data._timer = setInterval(tick, 1000);
  },

  // 单选/判断：选中
  selectOption(e) {
    const { qindex, oindex } = e.currentTarget.dataset;
    const key = `questions[${qindex}].options`;
    const options = this.data.questions[qindex].options.map((o, i) => ({
      ...o,
      selected: i === Number(oindex),
    }));
    this.setData({
      [key]: options,
      [`questions[${qindex}].answered`]: true,
    });
  },

  // 多选：toggle
  toggleMultiOption(e) {
    const { qindex, oindex } = e.currentTarget.dataset;
    const options = this.data.questions[qindex].options.map((o, i) =>
      i === Number(oindex) ? { ...o, selected: !o.selected } : o
    );
    const anySelected = options.some(o => o.selected);
    this.setData({
      [`questions[${qindex}].options`]: options,
      [`questions[${qindex}].answered`]: anySelected,
    });
  },

  onTextInput(e) {
    const { qindex } = e.currentTarget.dataset;
    const val = e.detail.value;
    this.setData({
      [`questions[${qindex}].answerText`]: val,
      [`questions[${qindex}].answered`]: !!val && val.trim().length > 0,
    });
  },

  prevQuestion() {
    if (this.data.currentIndex > 0) {
      this.setData({ currentIndex: this.data.currentIndex - 1 });
    }
  },

  nextQuestion() {
    if (this.data.currentIndex < this.data.questions.length - 1) {
      this.setData({ currentIndex: this.data.currentIndex + 1 });
    }
  },

  goToQuestion(e) {
    const idx = Number(e.currentTarget.dataset.index);
    if (idx >= 0 && idx < this.data.questions.length) {
      this.setData({ currentIndex: idx });
    }
  },

  async submitPaper(force) {
    if (this.data.submitting) return;
    const list = this.data.questions;
    const answered = list.filter(q => q.answered).length;

    if (!force && answered < list.length) {
      const confirmed = await new Promise(res => {
        wx.showModal({
          title: '还有未做的题目',
          content: `已答 ${answered}/${list.length}，确认交卷？`,
          success: r => res(r.confirm),
          fail: () => res(false),
        });
      });
      if (!confirmed) return;
    }

    // 组装答案
    const answers = list.map(q => {
      let answer;
      if (q.type === '单选题' || q.type === '判断题') {
        const sel = q.options.find(o => o.selected);
        answer = sel ? sel.id : null;
      } else if (q.type === '多选题') {
        answer = q.options.filter(o => o.selected).map(o => o.id);
      } else {
        // 填空/简答
        answer = q.answerText || '';
      }
      return { question_id: q.id, answer };
    });

    this.setData({ submitting: true });
    try {
      const resp = await tokenPost(
        API.EXAME_PAPER.SUBMIT_EXAME,
        { record_id: this.data.recordId, answers },
        { loadingTitle: '交卷中...' }
      );
      const data = resp && resp.data ? resp.data : resp;
      this.setData({ submitting: false });
      wx.showModal({
        title: '交卷成功',
        content: `得分：${data && data.score != null ? data.score : 0} / ${data && data.total_score != null ? data.total_score : '-'}${data && data.is_passed ? '\n恭喜通过！' : '\n未通过，加油！'}`,
        showCancel: false,
        success: () => {
          wx.redirectTo({
            url: `/packageStudent/pages/score/score?record_id=${this.data.recordId}`
          });
        },
      });
    } catch (err) {
      this.setData({ submitting: false });
      this.showError(err.message || '交卷失败');
    }
  },

  exitExam() {
    wx.showModal({
      title: '退出考试',
      content: '退出后当前作答将保留，下次进入可继续，确定退出？',
      success: r => {
        if (r.confirm) {
          wx.redirectTo({ url: '/packageStudent/pages/exame-list/exame-list' });
        }
      },
    });
  },
}, {
  requireAuth: true,
  userType: 'open_student'
})
