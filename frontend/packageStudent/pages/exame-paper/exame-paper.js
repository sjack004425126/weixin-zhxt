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
    countdownStr: '01:00:00',
    _timer: null,
    isSubmitting: false,
    loading: true,
    submitting: false,
    showCardPanel: false,
    answeredCount: 0,
    autoNext: true,
    _autoNextTimer: null,
    autoNextTip: false,
  },

  async onLoad(options) {
    const examId = Number(options.exam_id);
    if (!examId) {
      this.showError('缺少参数');
      return;
    }
    let autoNext = true;
    try {
      const v = wx.getStorageSync('exame_auto_next');
      if (v === 0 || v === false) autoNext = false;
    } catch (err) {}
    this.setData({ examId, autoNext });

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
    if (this.data._autoNextTimer) {
      clearTimeout(this.data._autoNextTimer);
      this.data._autoNextTimer = null;
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
      // 后端 start 返回结构：{ record_id, started_at, duration, exam: { id, title, duration, ..., questions: [...] } }
      const examObj = data.exam || {};
      const raw = examObj.questions || data.questions || [];
      const questions = (raw || []).map((q, idx) => this._normalizeQuestion(q, idx));
      // 按 started_at 计算剩余秒数（续考时扣掉已用时间）
      let totalSec = Number(data.duration || examObj.duration || 60) * 60;
      if (data.started_at) {
        const used = Math.floor((Date.now() - new Date(data.started_at).getTime()) / 1000);
        if (used > 0) totalSec = Math.max(totalSec - used, 60);
      }
      this.setData({
        recordId: data.record_id,
        exam: examObj.id ? examObj : { title: '考试中' },
        questions,
        countdown: totalSec,
        countdownStr: this._fmtTime(totalSec),
        showCardPanel: false,
        answeredCount: 0,
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
        this._timer = null;
        this.setData({ countdown: 0, countdownStr: '00:00:00' });
        this.showError('考试时间到，系统将自动交卷');
        setTimeout(() => this.submitPaper(true), 1000);
        return;
      }
      this.setData({
        countdown: c,
        countdownStr: this._fmtTime(c),
      });
    };
    this.setData({ countdownStr: this._fmtTime(this.data.countdown) });
    this.data._timer = setInterval(tick, 1000);
  },

  _fmtTime(totalSec) {
    const c = Math.max(Number(totalSec) || 0, 0);
    const h = Math.floor(c / 3600);
    const m = Math.floor((c % 3600) / 60);
    const s = c % 60;
    const pad = (n) => (n < 10 ? '0' + n : '' + n);
    return `${pad(h)}:${pad(m)}:${pad(s)}`;
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
    }, () => {
      this._updateAnsweredCount();
      this._scheduleAutoNext();
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
    }, () => this._updateAnsweredCount());
  },

  onTextInput(e) {
    const { qindex } = e.currentTarget.dataset;
    const val = e.detail.value;
    this.setData({
      [`questions[${qindex}].answerText`]: val,
      [`questions[${qindex}].answered`]: !!val && val.trim().length > 0,
    }, () => this._updateAnsweredCount());
  },

  _updateAnsweredCount() {
    const n = this.data.questions.filter(q => q.answered).length;
    this.setData({ answeredCount: n });
  },

  toggleAutoNext(e) {
    const checked = !!(e && e.detail !== undefined ? e.detail : !this.data.autoNext);
    this.setData({ autoNext: checked });
    try { wx.setStorageSync('exame_auto_next', checked ? 1 : 0); } catch (err) {}
    this.showSuccess(checked ? '已开启答题后自动下一题' : '已关闭自动下一题');
  },

  _scheduleAutoNext() {
    if (!this.data.autoNext) return;
    if (this.data._autoNextTimer) clearTimeout(this.data._autoNextTimer);
    // 最后一题不自动跳，提示去答题卡检查
    if (this.data.currentIndex >= this.data.questions.length - 1) return;
    this.setData({ autoNextTip: true });
    this.data._autoNextTimer = setTimeout(() => {
      this.data._autoNextTimer = null;
      this.setData({ autoNextTip: false });
      const next = Math.min(this.data.currentIndex + 1, this.data.questions.length - 1);
      this.setData({ currentIndex: next });
    }, 600);
  },

  openCard() { this.setData({ showCardPanel: true }); },
  closeCard() { this.setData({ showCardPanel: false }); },
  noop() {},

  prevQuestion() {
    if (this.data._autoNextTimer) { clearTimeout(this.data._autoNextTimer); this.data._autoNextTimer = null; }
    if (this.data.currentIndex > 0) {
      this.setData({ currentIndex: this.data.currentIndex - 1, autoNextTip: false });
    }
  },

  nextQuestion() {
    if (this.data._autoNextTimer) { clearTimeout(this.data._autoNextTimer); this.data._autoNextTimer = null; }
    if (this.data.currentIndex < this.data.questions.length - 1) {
      this.setData({ currentIndex: this.data.currentIndex + 1, autoNextTip: false });
    }
  },

  goToQuestion(e) {
    if (this.data._autoNextTimer) { clearTimeout(this.data._autoNextTimer); this.data._autoNextTimer = null; }
    const idx = Number(e.currentTarget.dataset.index);
    if (idx >= 0 && idx < this.data.questions.length) {
      this.setData({ currentIndex: idx, showCardPanel: false, autoNextTip: false });
    } else if (e.currentTarget.dataset.index === undefined) {
      // 答题卡按钮兜底（无 index 时仅关闭浮层）
      this.setData({ showCardPanel: false });
    }
  },

  async submitPaper(e) {
    // bindtap 会传入事件对象，不能当 force 用；只有显式 true 才跳过确认
    const force = (typeof e === 'boolean') ? e : false;
    if (e && e.stopPropagation) { /* tap 事件，无需处理 */ }
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
            url: `/packageStudent/pages/score/score?source=exame&record_id=${this.data.recordId}`
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
  userType: 'vocational_student'
})
