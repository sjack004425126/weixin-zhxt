const { createPage } = require('../../../utils/page-mixin');
const { tokenGet, tokenPost } = require('../../../utils/request');
const { API } = require('../../../utils/api');

/**
 * 自测答题页（开放学生自研）
 * 流程：
 *  1. onLoad 拿 kc_id/sj_id/jl_id，调 GET /student_exam/get_exame_paper 取题
 *  2. 作答保存在本地 answers[{tm_id, tm_dt}]
 *  3. 交卷 POST /student_exam/submit_exam {sj_id,kc_id,jl_id,answers}
 * 答案格式：后端要 [{tm_id, tm_dt}]，tm_dt 为作答文本（选择题存选项字母/内容）
 */
createPage({
  data: {
    kcId: null,
    sjId: null,
    jlId: null,
    kcName: '',
    questions: [],
    currentIndex: 0,
    loading: true,
    submitting: false,
  },

  async onLoad(options) {
    const kcId = Number(options.kc_id);
    const sjId = Number(options.sj_id);
    const jlId = options.jl_id;
    if (!kcId || !sjId || !jlId) {
      this.showError('缺少答题参数');
      return;
    }
    this.setData({ kcId, sjId, jlId });
    await this.loadPaper();
  },

  async loadPaper() {
    this.setData({ loading: true });
    try {
      const data = await tokenGet(
        API.EXAME_PAPER.GET_EXAM_PAPER,
        { kc_id: this.data.kcId, sj_id: this.data.sjId, jl_id: this.data.jlId },
        { loadingTitle: '获取试卷...' }
      );
      const list = (data && data.sj_tm_list) || [];
      const questions = list.map((q, idx) => this._normalize(q, idx));
      this.setData({
        questions,
        kcName: (data && data.kc_name) || '',
        loading: false,
      });
    } catch (err) {
      this.setData({ loading: false });
      this.showError(err.message || err.msg || '获取试卷失败');
    }
  },

  _normalize(q, idx) {
    const tx = q.tx || '';
    const options = [];
    if (q.xxA != null) options.push({ label: 'A', content: q.xxA, selected: false });
    if (q.xxB != null) options.push({ label: 'B', content: q.xxB, selected: false });
    if (q.xxC != null) options.push({ label: 'C', content: q.xxC, selected: false });
    if (q.xxD != null) options.push({ label: 'D', content: q.xxD, selected: false });
    return {
      tm_id: q.tm_id,
      tx,
      tg: q.tg || '',
      options,
      answerText: '',
      order: idx + 1,
      answered: false,
    };
  },

  isChoice(q) {
    return q.tx === '单选题' || q.tx === '判断题';
  },

  selectOption(e) {
    const { qindex, oindex } = e.currentTarget.dataset;
    const qi = Number(qindex), oi = Number(oindex);
    const key = `questions[${qi}].options`;
    const options = this.data.questions[qi].options.map((o, i) => ({
      ...o, selected: i === oi,
    }));
    this.setData({
      [key]: options,
      [`questions[${qi}].answered`]: true,
    });
  },

  toggleMultiOption(e) {
    const { qindex, oindex } = e.currentTarget.dataset;
    const qi = Number(qindex), oi = Number(oindex);
    const options = this.data.questions[qi].options.map((o, i) =>
      i === oi ? { ...o, selected: !o.selected } : o
    );
    const anySelected = options.some((o) => o.selected);
    this.setData({
      [`questions[${qi}].options`]: options,
      [`questions[${qi}].answered`]: anySelected,
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
    if (this.data.currentIndex > 0) this.setData({ currentIndex: this.data.currentIndex - 1 });
  },

  nextQuestion() {
    if (this.data.currentIndex < this.data.questions.length - 1) {
      this.setData({ currentIndex: this.data.currentIndex + 1 });
    }
  },

  _buildAnswers() {
    return this.data.questions.map((q) => {
      let tmDt = '';
      if (q.tx === '单选题' || q.tx === '判断题') {
        const sel = q.options.find((o) => o.selected);
        tmDt = sel ? sel.label : '';
      } else if (q.tx === '多选题') {
        tmDt = q.options.filter((o) => o.selected).map((o) => o.label).join(',');
      } else {
        tmDt = q.answerText || '';
      }
      return { tm_id: q.tm_id, tm_dt: tmDt };
    });
  },

  async saveProgress(silent) {
    try {
      await tokenPost(
        API.SELF_EXAM.SAVE_ANSWERS,
        { sj_id: this.data.sjId, kc_id: this.data.kcId, jl_id: String(this.data.jlId), answers: this._buildAnswers() },
        silent ? { showLoading: false } : { loadingTitle: '保存中...' }
      );
      if (!silent) this.showSuccess('已保存');
    } catch (err) {
      if (!silent) this.showError(err.message || err.msg || '保存失败');
    }
  },

  async submitPaper() {
    if (this.data.submitting) return;
    const list = this.data.questions;
    const answered = list.filter((q) => q.answered).length;
    if (answered < list.length) {
      const confirmed = await new Promise((res) => {
        wx.showModal({
          title: '还有未做的题目',
          content: `已答 ${answered}/${list.length}，确认交卷？`,
          success: (r) => res(r.confirm),
          fail: () => res(false),
        });
      });
      if (!confirmed) return;
    }
    this.setData({ submitting: true });
    try {
      const data = await tokenPost(
        API.EXAME_PAPER.SUBMIT_EXAM,
        { sj_id: this.data.sjId, kc_id: this.data.kcId, jl_id: String(this.data.jlId), answers: this._buildAnswers() },
        { loadingTitle: '交卷中...' }
      );
      this.setData({ submitting: false });
      const r = (data && data.submit_result) || {};
      wx.showModal({
        title: '交卷成功',
        content: `客观题得分：${r.objective_score != null ? r.objective_score : '-'}分\n正确率：${r.accuracy_rate != null ? r.accuracy_rate + '%' : '-'}`,
        showCancel: false,
        success: () => {
          wx.redirectTo({ url: '/packageStudent/pages/self-exam-papers/self-exam-papers?kc_id=' + this.data.kcId });
        },
      });
    } catch (err) {
      this.setData({ submitting: false });
      this.showError(err.message || err.msg || '交卷失败');
    }
  },

  exitExam() {
    wx.showModal({
      title: '退出答题',
      content: '退出前可先保存作答，确定退出？',
      success: (r) => {
        if (r.confirm) wx.navigateBack();
      },
    });
  },
}, {
  requireAuth: true,
  userType: 'open_student'
});
