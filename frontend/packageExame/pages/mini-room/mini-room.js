/**
 * 小程序 - 答题页（重构版 v3）
 *
 * 数据模型（参照 exame-paper）：
 *   questions[i] = {
 *     id, type:1|2|3|4|5, score, content,
 *     options: [{ id, label:"A", content, selected:false }],   // type=1,2
 *     selectedJudge: 'A'|'B'                                 // type=3
 *     answerText: string,                                    // type=4,5
 *     answered: boolean,  marked: boolean
 *   }
 *
 * 后端约定：
 *   - /exams/start 返回 { record_id, questions, remaining_seconds, saved_answers? }
 *   - questions[i].options[i].id 是数据库选项 id（提交答案用 id 也好、用 label 也可）
 *   - 提交时 answers = [{ question_id, answer }, ...]，answer 字段：
 *       单选/判断 → option.id 或 label 字符串
 *       多选      → option.id 数组  或  "A,B,C"
 *       填空/简答 → 文本
 */
const { createPage } = require('../../../utils/page-mixin');
const { tokenPost } = require('../../../utils/request');
const { API_EXAME, TOKEN_KEY } = require('../../../utils/api-exame');

// 题型常量（后端定义）
const TYPE_SINGLE = 1;
const TYPE_MULTI  = 2;
const TYPE_JUDGE  = 3;
const TYPE_BLANK  = 4;
const TYPE_ESSAY  = 5;

// 题型显示顺序（按用户要求：单选 → 多选 → 判断 → 填空 → 主观题）
const TYPE_ORDER = [TYPE_SINGLE, TYPE_MULTI, TYPE_JUDGE, TYPE_BLANK, TYPE_ESSAY];

// 题型中文标签 + 图标（避免在 wxml 表达式中调用方法失效问题）
const TYPE_LABEL = {
  [TYPE_SINGLE]: '单选题',
  [TYPE_MULTI]:  '多选题',
  [TYPE_JUDGE]:  '判断题',
  [TYPE_BLANK]:  '填空题',
  [TYPE_ESSAY]:  '简答题',
};

const TYPE_ICON = {
  [TYPE_SINGLE]: '◉',
  [TYPE_MULTI]:  '☑',
  [TYPE_JUDGE]:  '✓✕',
  [TYPE_BLANK]:  '▭',
  [TYPE_ESSAY]:  '✎',
};

createPage({
  data: {
    examId: 0,
    examTitle: '',
    recordId: 0,
    questions: [],
    currentIndex: 0,
    remainingSeconds: 60 * 60,  // 默认 60 分钟兜底（后端 start 返回后会覆盖）
    remainingText: '60:00',     // 预格式化的字符串，wxml 直接显示
    showCardPanel: false,
    showSubmitModal: false,
    cheatModalVisible: false,
    cheatCount: 0,
    submitting: false,
    autoNextEnabled: true,
    autoNextCountdown: null,
    loadError: '',
    progressPercent: 0,
    answeredCount: 0,
    markedCount: 0,
    unansweredCount: 0,
    unansweredListText: '',
    textAnswerLength: 0,
    cardByType: [],          // 答题卡按题型分组：[{type, typeLabel, total, answered, items: [...] }]
  },

  timer: null,
  _autoNextTimer: null,

  onLoad(query) {
    const token = wx.getStorageSync(TOKEN_KEY);
    if (!token) {
      wx.reLaunch({ url: '/packageExame/pages/mini-login/mini-login' });
      return;
    }

    this.setData({
      examId: Number(query.exam_id) || 0,
      examTitle: decodeURIComponent(query.exam_title || '考试'),
    });

    // ⭐ 同步导航栏标题（用户反馈顶部标题没替换成功）
    if (this.data.examTitle) {
      wx.setNavigationBarTitle({ title: this.data.examTitle });
    }

    this.startExam();
  },

  onShow() {
    // 回到前台：如果计时器已存在则说明考试进行中，不重置
    // 避免在 onShow 重复调 startExam 覆盖 remainingSeconds 导致数字归零
  },

  onUnload() {
    if (this.timer) clearInterval(this.timer);
    if (this._autoNextTimer) clearTimeout(this._autoNextTimer);
    // 最后再存一次（兜底，防止 setData 节流未触发）
    this._saveProgress(true);
  },

  // 防作弊：监听切到后台
  onHide() {
    if (this.data.recordId && this.timer) {
      this.data.cheatCount++;
      this.setData({ cheatCount: this.data.cheatCount, cheatModalVisible: true });
    }
    // 切后台时立即同步落盘（小程序进程可能被回收，内存数据丢失）
    this._saveProgress(true);
  },

  // ============ 本地进度缓存（防止退出/被杀进程后答题记录丢失） ============
  // 缓存 key：每个 recordId 独立一份
  _progressKey() {
    return `mini_exam_progress_${this.data.recordId || 'unknown'}`;
  },

  _saveProgress(force = false) {
    // 只在已有 recordId 且有题目时存
    if (!this.data.recordId || !this.data.questions || this.data.questions.length === 0) return;
    if (!force && this._saveTimer) return;  // 节流：300ms 内多次调用只执行一次
    const payload = {
      recordId: this.data.recordId,
      examId: this.data.examId,
      examTitle: this.data.examTitle,
      questions: this.data.questions,  // 包含 selected / selectedJudge / answerText / marked
      currentIndex: this.data.currentIndex,
      cheatCount: this.data.cheatCount || 0,
      savedAt: Date.now(),
    };
    try {
      wx.setStorageSync(this._progressKey(), payload);
    } catch (e) {
      console.warn('[mini-room] save progress failed:', e);
    }
    if (!force) {
      this._saveTimer = setTimeout(() => { this._saveTimer = null; }, 300);
    }
  },

  _clearProgress() {
    if (!this.data.recordId) return;
    try {
      wx.removeStorageSync(this._progressKey());
    } catch (e) { /* ignore */ }
  },

  _loadProgress(recordId, examId) {
    try {
      const cache = wx.getStorageSync(`mini_exam_progress_${recordId}`);
      if (!cache || cache.recordId !== recordId) return null;
      // 校验：examId 必须一致 + 保存时间距今 < 30 分钟（防止脏缓存）
      if (cache.examId !== examId) return null;
      if (Date.now() - (cache.savedAt || 0) > 30 * 60 * 1000) return null;
      return cache;
    } catch (e) {
      return null;
    }
  },

  hideCheatModal() {
    this.setData({ cheatModalVisible: false });
  },

  simulateCheat() {
    this.data.cheatCount++;
    this.setData({ cheatCount: this.data.cheatCount, cheatModalVisible: true });
  },

  // ============ 加载试卷（核心：归一化 + 按题型分组排序） ============
  async startExam(options = {}) {
    const silent = !!options.silent;
    if (!silent) this.setData({ loadError: '' });
    try {
      const resp = await tokenPost(
        API_EXAME.START,
        { exam_id: this.data.examId },
        { loadingTitle: silent ? '' : '加载试卷...', timeout: 30000 }
      );
      // 兼容后端多种返回结构
      // 实际：{ record_id, paper:[...], saved_answers, title, remaining_seconds, ... }
      // 兼容：{ record_id, questions:[...], ... } 或包一层 data
      let data = (resp && (resp.paper || resp.questions)) ? resp
               : (resp && resp.data && (resp.data.paper || resp.data.questions)) ? resp.data
               : (resp && resp.record_id) ? resp
               : {};

      if (data && data.paper && !data.questions) {
        data.questions = data.paper;  // 统一内部用 questions
      }

      const rawQuestions = data.questions || [];
      const savedAnswers = data.saved_answers || {};   // 续答：{question_id: answer}

      // ⭐ 归一化 + 按题型排序
      const questions = rawQuestions
        .map((q, idx) => this._normalizeQuestion(q, idx, savedAnswers))
        .sort((a, b) => {
          const oa = TYPE_ORDER.indexOf(a.type);
          const ob = TYPE_ORDER.indexOf(b.type);
          if (oa !== ob) return oa - ob;
          // 同题型保持原序（sort 字段）
          return a._sort - b._sort;
        });

      // ⭐ 用后端返回的标题（最权威）+ 同步到导航栏
      const title = data.title || this.data.examTitle || '考试';

      // ⭐ 倒计时兜底：如果后端没返回，优先用 duration*60；都没有则按 60 分钟兜底
      let remaining = Number(data.remaining_seconds) || 0;
      if (remaining <= 0) {
        const durMin = Number(data.duration) || 60;
        remaining = durMin * 60;
        console.warn('[mini-room] 后端未返回 remaining_seconds，按 duration 兜底:', remaining);
      }

      this.setData({
        examTitle: title,
        recordId: data.record_id,
        questions,
        currentIndex: 0,
        // ⭐ remainingSeconds 始终以服务端为准（基于后端的 started_at）
        remainingSeconds: remaining,
        remainingText: this.formatTime(remaining),  // 预格式化，避免 wxml 函数调用问题
        loadError: '',
        cheatCount: 0,
      }, () => {
        this._recomputeStats();
        this.startCountdown();
        // 同步更新导航栏标题
        wx.setNavigationBarTitle({ title });
      });

      // 首次开始（非续答）轻提示一下
      if (!silent && data.resumed) {
        wx.showToast({ title: '继续上次答题', icon: 'none' });
      }

      // ⭐ 本地进度恢复：服务端 saved_answers 只反映"已交卷/重提交"场景
      // 用户"退出考试界面"再回来时，服务端没有存档 → 优先用本地缓存恢复选项
      this._restoreFromLocalCache(rawQuestions);
    } catch (err) {
      if (!silent) {
        this.setData({ loadError: err.message || '开始考试失败，请检查网络后重试' });
      }
    }
  },

  // 从本地缓存恢复用户的答题选择（仅在服务端没有 saved_answers 时使用）
  _restoreFromLocalCache(rawQuestions) {
    const cache = this._loadProgress(this.data.recordId, this.data.examId);
    if (!cache || !cache.questions || !Array.isArray(cache.questions)) return;
    // 把缓存里的 options.selected / selectedJudge / answerText / marked 合并到内存 questions
    const cacheById = {};
    cache.questions.forEach(q => { cacheById[q.id] = q; });
    const merged = this.data.questions.map(q => {
      const c = cacheById[q.id];
      if (!c) return q;
      return {
        ...q,
        // 恢复选项 selected
        options: (q.options || []).map(o => ({
          ...o,
          selected: (c.options || []).find(co => co.id === o.id)?.selected || false,
        })),
        selectedJudge: c.selectedJudge || '',
        answerText: c.answerText || '',
        marked: !!c.marked,
      };
    });
    let restoredAny = false;
    merged.forEach(q => {
      const hasSelected = (q.options || []).some(o => o.selected);
      const hasOther = q.selectedJudge || q.answerText;
      if (hasSelected || hasOther) restoredAny = true;
    });
    this.setData({
      questions: merged,
      currentIndex: Math.min(Math.max(cache.currentIndex || 0, 0), Math.max(merged.length - 1, 0)),
      cheatCount: cache.cheatCount || 0,
    }, () => {
      this._recomputeStats();
      if (restoredAny) {
        wx.showToast({ title: '已恢复上次答题进度', icon: 'none', duration: 1500 });
      }
    });
  },

  // 把后端单题归一化为前端结构
  _normalizeQuestion(q, idx, savedAnswers) {
    const type = Number(q.type);
    const saved = savedAnswers[String(q.id)] ?? savedAnswers[q.id];
    const options = (q.options || []).map(o => ({
      id: o.id,
      label: o.label || '',
      content: o.content || '',
      selected: false,
    }));

    let selectedJudge = '';
    let answerText = '';
    if (saved !== undefined && saved !== null && saved !== '') {
      if (type === TYPE_SINGLE) {
        // saved = "A" 或 option.id
        if (typeof saved === 'string' && /^[A-Z]$/.test(saved)) {
          const opt = options.find(o => o.label === saved);
          if (opt) opt.selected = true;
        } else {
          const opt = options.find(o => String(o.id) === String(saved));
          if (opt) opt.selected = true;
        }
      } else if (type === TYPE_MULTI) {
        // saved 可能是 ['A','C'] / ['1','3'] / "A,ABC"
        const letters = [];
        if (Array.isArray(saved)) {
          letters.push(...saved);
        } else if (typeof saved === 'string') {
          letters.push(...saved.split(',').map(s => s.trim()).filter(Boolean));
        }
        // 把 letters 转成 label（如果存的是 id，也兼容）
        letters.forEach(letterOrId => {
          if (/^[A-Z]$/.test(letterOrId)) {
            const opt = options.find(o => o.label === letterOrId);
            if (opt) opt.selected = true;
          } else {
            const opt = options.find(o => String(o.id) === String(letterOrId));
            if (opt) opt.selected = true;
          }
        });
      } else if (type === TYPE_JUDGE) {
        // saved = "A" 表示正确 "B" 表示错误
        if (saved === 'A' || saved === '正确' || saved === 'true' || saved === 'T') selectedJudge = 'A';
        else if (saved === 'B' || saved === '错误' || saved === 'false' || saved === 'F') selectedJudge = 'B';
      } else {
        // 填空 / 简答
        answerText = Array.isArray(saved) ? saved.join(';') : String(saved);
      }
    }

    return {
      id: q.id,
      type,
      content: q.content || '',
      score: Number(q.score || 0),
      options,
      selectedJudge,
      answerText,
      answered: false,
      marked: false,
      _sort: q._sort || q.sort || idx,  // 用于同题型内的顺序
    };
  },

  // ============ 倒计时 ============
  startCountdown() {
    if (this.timer) clearInterval(this.timer);
    this.timer = setInterval(() => {
      let r = this.data.remainingSeconds - 1;
      if (r <= 0) {
        clearInterval(this.timer);
        this.timer = null;
        this.setData({ remainingSeconds: 0, remainingText: '00:00' });
        wx.showToast({ title: '时间到，自动交卷', icon: 'none' });
        this.showSubmitConfirm(true);
        return;
      }
      this.setData({
        remainingSeconds: r,
        remainingText: this.formatTime(r),
      });
    }, 1000);
  },

  // ============ 选项选择 ============
  selectOption(e) {
    const { qindex, oindex } = e.currentTarget.dataset;
    const q = this.data.questions[qindex];
    if (!q) return;
    const key = `questions[${qindex}].options`;
    const options = q.options.map((o, i) => ({ ...o, selected: i === Number(oindex) }));
    this.setData({ [key]: options }, () => this._recomputeStats());
    this._saveProgress();

    // 自动下一题（仅单选）
    if (this.data.autoNextEnabled && q.type === TYPE_SINGLE) {
      this._scheduleAutoNext();
    }
  },

  toggleMultiOption(e) {
    const { qindex, oindex } = e.currentTarget.dataset;
    const q = this.data.questions[qindex];
    if (!q) return;
    const key = `questions[${qindex}].options`;
    const options = q.options.map((o, i) => i === Number(oindex) ? { ...o, selected: !o.selected } : { ...o });
    this.setData({ [key]: options }, () => this._recomputeStats());
    this._saveProgress();
  },

  selectJudge(e) {
    const { qindex, judge } = e.currentTarget.dataset;
    const q2 = this.data.questions[qindex];
    if (!q2) return;
    const newJudge = q2.selectedJudge === judge ? '' : judge;
    this.setData({ [`questions[${qindex}].selectedJudge`]: newJudge }, () => this._recomputeStats());
    this._saveProgress();

    // 自动下一题（仅判断）
    if (this.data.autoNextEnabled && newJudge) {
      this._scheduleAutoNext();
    }
  },

  _scheduleAutoNext() {
    if (this.data.currentIndex >= this.data.questions.length - 1) {
      this.showSuccess('已是最后一题，可打开答题卡检查或交卷');
      return;
    }
    if (this._autoNextTimer) clearTimeout(this._autoNextTimer);
    this.setData({ autoNextCountdown: 1 });
    this._autoNextTimer = setTimeout(() => {
      this.setData({ autoNextCountdown: null });
      const next = Math.min(this.data.currentIndex + 1, this.data.questions.length - 1);
      this.setData({ currentIndex: next }, () => this._recomputeStats());
    }, 450);
  },

  // ============ 文本输入 ============
  onTextInput(e) {
    const { qindex } = e.currentTarget.dataset;
    const val = e.detail.value || '';
    this.setData({
      [`questions[${qindex}].answerText`]: val,
    }, () => {
      this._recomputeStats();
      // 简答题字数实时
      const q = this.data.questions[qindex];
      if (q && q.type === TYPE_ESSAY && qindex === this.data.currentIndex) {
        this.setData({ textAnswerLength: val.length });
      }
      this._saveProgress();
    });
  },

  // ============ 自动下一题 ============
  toggleAutoNext() {
    const next = !this.data.autoNextEnabled;
    this.setData({ autoNextEnabled: next });
    this.showSuccess(next ? '已开启答题后自动下一题' : '已关闭自动下一题');
  },

  // ============ 标记 ============
  toggleMark() {
    const idx = this.data.currentIndex;
    const cur = this.data.questions[idx] && this.data.questions[idx].marked;
    this.setData({ [`questions[${idx}].marked`]: !cur }, () => this._recomputeStats());
    this._saveProgress();
    this.showSuccess(!cur ? `已标记第 ${idx + 1} 题待复查` : `已取消第 ${idx + 1} 题标记`);
  },

  // ============ 导航 ============
  onPrev() {
    if (this.data.currentIndex > 0) {
      this.setData({ currentIndex: this.data.currentIndex - 1 }, () => this._recomputeStats());
    }
  },

  onNext() {
    if (this.data.currentIndex < this.data.questions.length - 1) {
      this.setData({ currentIndex: this.data.currentIndex + 1 }, () => this._recomputeStats());
    } else {
      // 最后一题点击"下一题"：提示去答题卡交卷
      wx.showToast({
        title: '已是最后一题，请点 📋 答题卡交卷',
        icon: 'none',
        duration: 2200,
      });
    }
  },

  // ============ 答题卡 ============
  showCard() { this.setData({ showCardPanel: true }); },
  hideCard() { this.setData({ showCardPanel: false }); },
  noop() {},

  jumpToQuestion(e) {
    const idx = e.currentTarget.dataset.idx;
    this.setData({ currentIndex: idx, showCardPanel: false }, () => this._recomputeStats());
  },

  // ============ 提交确认 ============
  showSubmitConfirm(force) {
    if (force) {
      this._doSubmit();
      return;
    }
    const list = this.data.questions;
    const unansweredIdx = [];
    list.forEach((q, idx) => {
      if (!q.answered) unansweredIdx.push(idx);
    });

    let unansweredListText = '';
    if (unansweredIdx.length > 0) {
      const shown = unansweredIdx.slice(0, 6).map(i => `${i + 1}`).join('、');
      unansweredListText = `${shown}${unansweredIdx.length > 6 ? ' 等题' : ' 题'}`;
    }

    this.setData({
      showSubmitModal: true,
      unansweredCount: unansweredIdx.length,
      unansweredListText,
    });
  },

  hideSubmitConfirm() {
    this.setData({ showSubmitModal: false });
  },

  onSubmit() {
    if (this.data.submitting) return;
    this._doSubmit();
  },

  _doSubmit() {
    this.setData({ submitting: true, showSubmitModal: false });
    if (this.timer) { clearInterval(this.timer); this.timer = null; }

    const answers = this.data.questions.map(q => {
      let answer;
      if (q.type === TYPE_SINGLE) {
        const sel = q.options.find(o => o.selected);
        answer = sel ? (sel.label || sel.id) : null;
      } else if (q.type === TYPE_MULTI) {
        const selected = q.options.filter(o => o.selected);
        // 后端判分依赖 set(ua.split(",")) == set(ca.split(","))，
        // 用逗号连接选项 label/id，存成字符串避免 Pydantic 422
        answer = selected.length > 0
          ? selected.map(o => o.label || o.id).join(',')
          : null;
      } else if (q.type === TYPE_JUDGE) {
        answer = q.selectedJudge || null;
      } else {
        answer = q.answerText || '';
      }
      return { question_id: q.id, answer };
    });

    tokenPost(
      API_EXAME.SUBMIT,
      { record_id: this.data.recordId, answers },
      { loadingTitle: '交卷中...', timeout: 30000 }
    ).then(resp => {
      const data = (resp && resp.score !== undefined) ? resp
                   : (resp && resp.data) ? resp.data
                   : resp;
      this.setData({ submitting: false });
      // 交卷成功，清掉本地答题进度缓存
      this._clearProgress();
      wx.redirectTo({
        url: `/packageExame/pages/mini-scores/mini-scores?record_id=${this.data.recordId}&score=${data.score || 0}&is_passed=${data.is_passed ? 1 : 0}`,
      });
    }).catch(err => {
      console.error('[mini-room] submit err:', err, JSON.stringify(err));
      this.setData({ submitting: false });
      wx.showModal({
        title: '交卷失败',
        content: (err && err.message) || '网络异常，是否重试？',
        confirmText: '重试',
        cancelText: '取消',
        success: (res) => { if (res.confirm) this._doSubmit(); },
      });
    });
  },

  // ============ 工具 ============
  formatTime(seconds) {
    // 严格容错：任何 falsy/NaN 都按 0 处理
    let s = Number(seconds);
    if (!Number.isFinite(s) || s < 0) s = 0;
    s = Math.floor(s);
    const m = Math.floor(s / 60);
    const sec = s % 60;
    return `${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
  },

  getTypeLabel(type) {
    return ({
      1: '单选题', 2: '多选题', 3: '判断题', 4: '填空题', 5: '简答题'
    })[type] || '题目';
  },

  // 重新计算：每题 answered + 已答总数 + 已标记总数 + 进度 + 简答字数
  _recomputeStats() {
    const list = this.data.questions;
    if (!list || list.length === 0) return;

    let answered = 0;
    let markedCount = 0;
    let textLen = 0;
    const curQ = list[this.data.currentIndex];

    const updated = list.map((q, idx) => {
      let isAnswered = false;
      if (q.type === TYPE_SINGLE) {
        isAnswered = q.options.some(o => o.selected);
      } else if (q.type === TYPE_MULTI) {
        isAnswered = q.options.some(o => o.selected);
      } else if (q.type === TYPE_JUDGE) {
        isAnswered = !!q.selectedJudge;
      } else {
        isAnswered = !!(q.answerText && q.answerText.trim().length > 0);
      }
      if (isAnswered) answered++;
      if (q.marked) markedCount++;

      if (idx === this.data.currentIndex && q.type === TYPE_ESSAY) {
        textLen = (q.answerText || '').length;
      }

      // 仅在变化时返回新对象（性能）
      return q.answered === isAnswered ? q : { ...q, answered: isAnswered };
    });

    const progress = Math.round(((this.data.currentIndex + 1) / list.length) * 100);

    // ⭐ 答题卡按题型分组（用于美化后的答题卡）
    const typeMap = new Map();
    updated.forEach((q, idx) => {
      const t = q.type;
      if (!typeMap.has(t)) {
        typeMap.set(t, {
          type: t,
          typeLabel: TYPE_LABEL[t] || '题目',
          total: 0,
          answered: 0,
          items: [],
        });
      }
      const bucket = typeMap.get(t);
      bucket.total++;
      if (q.answered) bucket.answered++;
      bucket.items.push({
        idx,
        answered: !!q.answered,
        marked: !!q.marked,
        current: idx === this.data.currentIndex,
      });
    });
    // 按题型固定顺序：单选 → 多选 → 判断 → 填空 → 简答
    const order = [TYPE_SINGLE, TYPE_MULTI, TYPE_JUDGE, 4, 5];
    const cardByType = order
      .map(t => typeMap.get(t))
      .filter(Boolean);

    this.setData({
      questions: updated,
      answeredCount: answered,
      markedCount,
      progressPercent: progress,
      textAnswerLength: textLen,
      cardByType,
    });
  },

  showSuccess(msg) {
    if (this._showSuccess) return this._showSuccess(msg);
    wx.showToast({ title: msg, icon: 'success' });
  },
});