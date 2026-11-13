/**
 * 问卷填写页 - survey-fill
 * 蓝白配色版 (基于 zhpt-new/design 风格)
 *
 * URL 参数:
 *   sid      问卷ID（必填）
 *   aid      草稿ID（可选，有则续答）
 *
 * 功能:
 * - 支持所有问卷类型（SURVEY/REGISTRATION/VOTE/EXAM）
 * - 支持所有题型（SINGLE/MULTI/TEXT/TEXT_MULTI/RATE/SCORE/NPS/DATE 等）
 * - 草稿自动保存（每 30s）
 * - 防作弊：切屏次数检测 + 无操作超时
 * - 提交时记录 wx_openid（用于身份核对）
 * - 提交后按 settings.redirect 跳转
 *
 * 登录态处理:
 * - 有 token → 带上 Authorization 头（后端记录 user_id 等）
 * - 无 token → 匿名填写（后端仅记录 wx_openid）
 * - wx_openid 从 app.globalData.userInfo.openid 获取，未登录则通过 wx.login 换取
 */
const { createPage } = require('../../../utils/page-mixin');
const { get, post } = require('../../../utils/request');
const app = getApp();

createPage({
  data: {
    // ---------- 页面状态 ----------
    loading: true,
    submitting: false,
    sid: null,
    aid: null,

    // ---------- 问卷信息 ----------
    survey: null,
    questions: [],
    settings: {},
    survey_type: '',
    is_anonymous: false,
    already_submitted: false,

    // ---------- 作答数据 ----------
    answers: {},
    start_time: null,

    // ---------- 校验错误 ----------
    errors: {},

    // ---------- 字符计数 ----------
    _charCounts: {},

    // ---------- 文本输入镜像(防止 textarea value 双向绑定回退) ----------
    _textValues: {},
    _textMultiValues: {},

    // ---------- 多选计数 ----------
    _multiLengths: {},

    // ---------- 选项选中状态 ----------
    _selectedOptions: {},

    // ---------- 防作弊 ----------
    switch_count: 0,
    max_switch: 5,

    // ---------- 草稿 ----------
    draft_timer: null,

    // ---------- UI ----------
    questions_per_page: 0,
    show_confirm: false,

    // ---------- 日期选择 ----------
    datePickerInfo: null,
    showDatePicker: false,
    datePickerType: 'date',
    datePickerValue: Date.now(),
    // 日期选择器 min/max 必须为数字，避免传入 undefined
    datePickerMin: new Date(1900, 0, 1).getTime(),
    datePickerMax: new Date(2100, 11, 31).getTime(),

    // ---------- 成功弹窗 ----------
    showSuccessModal: false,
    _receiptId: '',

    // ---------- 计算属性(在 data 中维护) ----------
    _durationText: '',
    _progress: 0,
    _progressText: '0/0',
    _durationTimer: null,
    _currentNavIdx: -1,  // 侧边导航当前高亮题号
    _showAnswerCard: false,  // 答题卡弹层显示
    _showBackToTop: false,   // 返回顶部按钮显示
    _answeredCount: 0,       // 已答题数
    _totalQuestionCount: 0,  // 总题数
    _answeredMap: {},        // { [qid]: true } 已答状态映射（供 wxml 响应式读取）

    // ---------- 错误 ----------
    error_msg: '',

    // ---------- 次数限制 ----------
    submit_limit: 1,             // 周期内总上限
    submit_limit_period: 'once', // once/day/week/month/forever
    submit_used: 0,              // 本周期已提交次数
    submit_remaining: 1,         // 本周期还可提交次数
    submit_can_submit: true,     // 当前能否提交
    submit_message: '',          // 文案

    // ---------- SCALE 量表题 5 档 emoji ----------
    scaleEmojiLevels: [
      { level: 1, icon: '😡', label: '非常不满意' },
      { level: 2, icon: '😟', label: '不满意' },
      { level: 3, icon: '😐', label: '一般' },
      { level: 4, icon: '😊', label: '满意' },
      { level: 5, icon: '🤩', label: '非常满意' },
    ],
  },

  onLoad(query) {
    // 缓存视口高度，用于 onPageScroll 计算题号高亮
    wx.getWindowInfo({
      success: (res) => {
        this._winHeight = res.windowHeight;
      }
    });

    // 兼容多种进入方式:
    //   1. 小程序码(场景码)扫码: query = { scene: "TW9XC7fx" }
    //   2. 短链 / 链接:          query = { code: "TW9XC7fx" }
    //   3. 老链接 fallback:      query = { sid: 123 }
    const rawScene = query.scene || query.code || '';
    const code = decodeURIComponent(rawScene || '').trim();
    const sid = query.sid ? parseInt(query.sid) : null;

    if (!code && !sid) {
      console.error('[survey-fill] 缺少问卷参数, query=', query);
      this.showError('缺少问卷参数(code 或 sid)');
      return wx.navigateBack();
    }

    this.setData({ code, sid });

    if (query.aid) {
      this.setData({ aid: parseInt(query.aid) });
    }

    // 确保有 wx_openid(即使没登录也要通过 wx.login 获取),先拿到再加载问卷
    this._ensureWxOpenid().finally(() => {
      this._setupAntiCheat();
      if (code) {
        this._loadSurveyByCode(code);
      } else {
        this._loadSurvey(sid);
      }
    });
  },

  onUnload() {
    // 离开页面前：把暂存的输入值兜底写回 answers（用户可能没失焦就返回）
    if (this._pendingText) {
      Object.keys(this._pendingText).forEach(qid => {
        this._setAnswer(qid, this._pendingText[qid]);
      });
      this._pendingText = null;
    }
    if (this._pendingTextMulti) {
      // 按 qid 聚合
      const grouped = {};
      Object.keys(this._pendingTextMulti).forEach(key => {
        const [qid, idxStr] = key.split('_');
        const idx = parseInt(idxStr, 10);
        if (!grouped[qid]) grouped[qid] = [];
        grouped[qid][idx] = this._pendingTextMulti[key];
      });
      Object.keys(grouped).forEach(qid => {
        const current = this.data.answers[qid] || [];
        const updated = [...current];
        grouped[qid].forEach((v, i) => { if (v !== undefined) updated[i] = v; });
        this._setAnswer(qid, updated);
      });
      this._pendingTextMulti = null;
    }
    this._stopTimers();
  },

  onShow() {
    // 页面显示时重置草稿计时
    this._startDraftTimer();
  },

  // 页面滚动：自动高亮侧边导航当前可见题目 + 显示/隐藏返回顶部
  onPageScroll(e) {
    const scrollTop = e.scrollTop;
    // 返回顶部按钮：超过 500rpx 就显示
    if (scrollTop > 500 && !this.data._showBackToTop) {
      this.setData({ _showBackToTop: true });
    } else if (scrollTop <= 500 && this.data._showBackToTop) {
      this.setData({ _showBackToTop: false });
    }

    if (!this.data.questions || this.data.questions.length === 0) return;
    const query = wx.createSelectorQuery();
    query.selectAll('.question-item').boundingClientRect();
    query.exec((res) => {
      if (!res || !res[0] || res[0].length === 0) return;
      const list = res[0];
      // 触发点：视口上 1/3 区域
      const triggerLine = (this._winHeight || 667) / 3;
      let found = -1;
      for (let i = 0; i < list.length; i++) {
        const rect = list[i];
        if (rect.top <= triggerLine && rect.bottom > 0) {
          found = i;
          break;
        }
      }
      if (found === -1) return;
      if (found !== this.data._currentNavIdx) {
        this.setData({ _currentNavIdx: found });
      }
    });
  },

  onHide() {
    // 立即保存一次草稿（包含正在输入的暂存内容），避免切走页面后丢失
    this._autoSaveDraft();
  },

  // ================================================================
  // 确保有 openid（已登录从 globalData 取，未登录通过 wx.login + 后端换）
  // ================================================================
  async _ensureWxOpenid() {
    const userInfo = app.globalData?.userInfo || {};
    if (userInfo.openid || userInfo.wx_openid) return;

    try {
      const loginRes = await new Promise((resolve, reject) => {
        wx.login({ success: resolve, fail: reject });
      });
      if (!loginRes.code) return;

      const res = await post('/survey-fill/wx/code2openid', { code: loginRes.code });
      if (res.data?.openid) {
        app.globalData = app.globalData || {};
        app.globalData.userInfo = app.globalData.userInfo || {};
        app.globalData.userInfo.openid = res.data.openid;
        wx.setStorageSync('survey_openid_cache', res.data.openid);
      }
    } catch (e) {
      console.warn('_ensureWxOpenid failed', e);
      const cached = wx.getStorageSync('survey_openid_cache');
      if (cached) {
        app.globalData = app.globalData || {};
        app.globalData.userInfo = app.globalData.userInfo || {};
        app.globalData.userInfo.openid = cached;
      }
    }
  },

  _getWxOpenid() {
    const userInfo = app.globalData?.userInfo || {};
    return userInfo.openid || userInfo.wx_openid || '';
  },

  // ================================================================
  // 通过 survey_code 加载问卷（新增）
  // ================================================================
  async _loadSurveyByCode(code) {
    try {
      const deviceId = this._getDeviceId();
      const res = await get(`/survey-fill/surveys/by-code/${code}?device_id=${encodeURIComponent(deviceId)}`, {});

      const data = res;
      const limitSummary = this._buildLimitSummary(data);
      const questions = data.questions || [];

      // 初始化 answers 和辅助数据
      const answers = {};
      const errors = {};
      const charCounts = {};
      const multiLengths = {};
      const selectedOptions = {};
      const textValues = {};
      const textMultiValues = {};
      questions.forEach(q => {
        if (q.qtype === 'MULTI') {
          answers[q.qid] = [];
          multiLengths[q.qid] = 0;
          selectedOptions[q.qid] = {};
          (q.options || []).forEach(opt => {
            selectedOptions[q.qid][opt.id] = false;
          });
        } else if (q.qtype === 'TEXT_MULTI') {
          const opts = q.options || [];
          answers[q.qid] = opts.map(() => '');
        } else if (q.qtype === 'MATRIX_SINGLE') {
          answers[q.qid] = {};
        } else if (q.qtype === 'SLIDER') {
          answers[q.qid] = (q.slider_min !== undefined && q.slider_min !== null) ? q.slider_min : 0;
        } else if (q.qtype === 'SCALE') {
          answers[q.qid] = 0;
        } else if (['RATE', 'SCORE', 'NPS'].includes(q.qtype)) {
          answers[q.qid] = 0;
        } else {
          answers[q.qid] = null;
        }
        errors[q.qid] = false;
        charCounts[q.qid] = 0;
      });

      this.setData({
        sid: data.sid,
        survey: {
          sid: data.sid,
          survey_code: data.survey_code,
          title: data.title,
          subtitle: data.subtitle || '',
          description: data.description || '',
          survey_type: data.survey_type,
          is_anonymous: data.is_anonymous,
          max_answers: data.max_answers,
          start_at: data.start_at,
          end_at: data.end_at,
          estimated_minutes: data.estimated_minutes || 3,
        },
        questions,
        settings: data.settings || {},
        survey_type: data.survey_type,
        is_anonymous: data.is_anonymous,
        already_submitted: data.already_submitted,
        // ---- 次数限制字段 ----
        submit_limit: Number(data.submit_limit || 1),
        submit_limit_period: data.submit_limit_period || 'once',
        submit_used: Number(data.submit_used || 0),
        submit_remaining: Number(data.submit_remaining != null ? data.submit_remaining : (data.submit_limit || 1)),
        submit_can_submit: data.submit_can_submit !== false,
        submit_message: data.submit_message || '',
        limit_summary: limitSummary.text,
        limit_summary_tone: limitSummary.tone,  // ok/warn/block
        answers,
        errors,
        _charCounts: charCounts,
        _multiLengths: multiLengths,
        _selectedOptions: selectedOptions,
        _textValues: textValues,
        _textMultiValues: textMultiValues,
        loading: false,
        max_switch: data.settings?.anti_cheat?.max_switch_count || 5,
        questions_per_page: data.settings?.submission?.questions_per_page || 0,
      });

      this._updateProgress();
      this._updateAnswerCounts();
      this._startDraftTimer();
      this._startDurationTimer();

    } catch (err) {
      console.error('_loadSurveyByCode error', err);
      this.showError(err.message || '加载问卷失败');
      this.setData({ loading: false, error_msg: (err.message || '加载失败') });
    }
  },

  // ================================================================
  // 加载问卷（原有 by-sid）
  // ================================================================
  async _loadSurvey(sid) {
    try {
      const deviceId = this._getDeviceId();
      const res = await get(`/survey-fill/surveys/${sid}?device_id=${encodeURIComponent(deviceId)}`, {});

      const data = res;
      const limitSummary = this._buildLimitSummary(data);
      const questions = data.questions || [];

      // 初始化 answers 和辅助数据
      const answers = {};
      const errors = {};
      const charCounts = {};
      const multiLengths = {};  // 多选题选中数量
      const selectedOptions = {};  // 选项选中状态
      const textValues = {};
      const textMultiValues = {};
      questions.forEach(q => {
        if (q.qtype === 'MULTI') {
          answers[q.qid] = [];
          multiLengths[q.qid] = 0;
          selectedOptions[q.qid] = {};
          (q.options || []).forEach(opt => {
            selectedOptions[q.qid][opt.id] = false;
          });
        } else if (q.qtype === 'TEXT_MULTI') {
          const opts = q.options || [];
          answers[q.qid] = opts.map(() => '');
        } else if (q.qtype === 'MATRIX_SINGLE') {
          answers[q.qid] = {};
        } else if (q.qtype === 'SLIDER') {
          // 滑动条默认取 slider_min,避免 0 错位
          answers[q.qid] = (q.slider_min !== undefined && q.slider_min !== null) ? q.slider_min : 0;
        } else if (q.qtype === 'SCALE') {
          // 量表题默认 0(未选)
          answers[q.qid] = 0;
        } else if (['RATE', 'SCORE', 'NPS'].includes(q.qtype)) {
          // 评分/星级默认 0
          answers[q.qid] = 0;
        } else {
          answers[q.qid] = null;
        }
        errors[q.qid] = false;
        charCounts[q.qid] = 0;
      });

      // 恢复本地草稿
      const localDraft = wx.getStorageSync(`survey_draft_${data.sid}`) || null;
      const draftAnswers = localDraft?.answers;
      const savedTextValues = localDraft?.textValues || {};
      const savedTextMultiValues = localDraft?.textMultiValues || {};
      if (draftAnswers && Array.isArray(draftAnswers)) {
        draftAnswers.forEach(item => {
          if (item.qid in answers) {
            answers[item.qid] = item.value;
            if (typeof item.value === 'string') {
              charCounts[item.qid] = item.value.length;
              // 优先用 storage 镜像值（反映用户最近输入），否则用 answers 字符串
              textValues[item.qid] = savedTextValues[item.qid] !== undefined
                ? savedTextValues[item.qid]
                : item.value;
            }
            if (Array.isArray(item.value)) {
              multiLengths[item.qid] = item.value.length;
              if (selectedOptions[item.qid]) {
                Object.keys(selectedOptions[item.qid]).forEach(optId => {
                  selectedOptions[item.qid][optId] = item.value.includes(optId);
                });
              }
              // TEXT_MULTI 多项填空：恢复每项文本到镜像
              item.value.forEach((v, i) => {
                const k = `${item.qid}_${i}`;
                textMultiValues[k] = savedTextMultiValues[k] !== undefined
                  ? savedTextMultiValues[k]
                  : (v || '');
              });
            }
          }
        });
      } else if (this.data.aid) {
        try {
          const draftRes = await get(`/survey-fill/drafts/${this.data.aid}`, {});
          if (draftRes.success && draftRes.data) {
            (draftRes.data.answers || []).forEach(item => {
              if (item.qid in answers) {
                answers[item.qid] = item.value;
                if (typeof item.value === 'string') {
                  charCounts[item.qid] = item.value.length;
                  textValues[item.qid] = item.value;
                }
                if (Array.isArray(item.value)) {
                  multiLengths[item.qid] = item.value.length;
                  if (selectedOptions[item.qid]) {
                    Object.keys(selectedOptions[item.qid]).forEach(optId => {
                      selectedOptions[item.qid][optId] = item.value.includes(optId);
                    });
                  }
                  item.value.forEach((v, i) => {
                    textMultiValues[`${item.qid}_${i}`] = v || '';
                  });
                }
              }
            });
          }
        } catch (e) {
          console.warn('加载草稿失败', e);
        }
      }

      this.setData({
        survey: {
          sid: data.sid,
          survey_code: data.survey_code,
          title: data.title,
          subtitle: data.subtitle || '',
          description: data.description || '',
          survey_type: data.survey_type,
          is_anonymous: data.is_anonymous,
          max_answers: data.max_answers,
          start_at: data.start_at,
          end_at: data.end_at,
          estimated_minutes: data.estimated_minutes || data.settings?.estimated_minutes || 3,
        },
        questions,  // 原始数据保留
        settings: data.settings || {},
        survey_type: data.survey_type,
        is_anonymous: data.is_anonymous,
        already_submitted: data.already_submitted,
        // ---- 次数限制字段 ----
        submit_limit: Number(data.submit_limit || 1),
        submit_limit_period: data.submit_limit_period || 'once',
        submit_used: Number(data.submit_used || 0),
        submit_remaining: Number(data.submit_remaining != null ? data.submit_remaining : (data.submit_limit || 1)),
        submit_can_submit: data.submit_can_submit !== false,
        submit_message: data.submit_message || '',
        limit_summary: limitSummary.text,
        limit_summary_tone: limitSummary.tone,
        answers,
        errors,
        _charCounts: charCounts,
        _multiLengths: multiLengths,
        _selectedOptions: selectedOptions,
        _textValues: textValues,
        _textMultiValues: textMultiValues,
        loading: false,
        max_switch: data.settings?.anti_cheat?.max_switch_count || 5,
        questions_per_page: data.settings?.submission?.questions_per_page || 0,
      });

      this._updateProgress();
      this._updateAnswerCounts();
      this._startDraftTimer();
      this._startDurationTimer();

    } catch (err) {
      console.error('_loadSurvey error', err);
      this.showError(err.message || '加载问卷失败');
      this.setData({ loading: false, error_msg: (err.message || '加载失败') });
    }
  },

  // ================================================================
  // 作答操作
  // ================================================================

  // 单选选项点击（自定义样式）
  onOptionTap(e) {
    const { qid, optid } = e.currentTarget.dataset;
    this._setAnswer(qid, optid);
  },

  // 多选选项点击（自定义样式）
  onMultiOptionTap(e) {
    const { qid, optid } = e.currentTarget.dataset;
    const current = this.data.answers[qid] || [];
    let newValue;
    let newLength;
    let isSelected;
    if (current.includes(optid)) {
      newValue = current.filter(id => id !== optid);
      newLength = newValue.length;
      isSelected = false;
    } else {
      newValue = [...current, optid];
      newLength = newValue.length;
      isSelected = true;
    }
    this._setAnswer(qid, newValue);
    this.setData({
      [`_multiLengths.${qid}`]: newLength,
      [`_selectedOptions.${qid}.${optid}`]: isSelected
    });
  },

  // 清空多选
  onClearMulti(e) {
    const { qid } = e.currentTarget.dataset;
    const options = this.data.questions.find(q => q.qid === qid)?.options || [];
    this._setAnswer(qid, []);
    // 清除所有选项的选中状态
    const updates = { [`_multiLengths.${qid}`]: 0 };
    options.forEach(opt => {
      updates[`_selectedOptions.${qid}.${opt.id}`] = false;
    });
    this.setData(updates);
  },

  onRadioChange(e) {
    const { qid, value } = e.currentTarget.dataset;
    this._setAnswer(qid, value);
  },

  onCheckboxChange(e) {
    const { qid } = e.currentTarget.dataset;
    this._setAnswer(qid, Array.isArray(e.detail) ? e.detail : []);
  },

  // 单行/多行填空：textarea 是非受控组件，只要 bindinput 里 setData 触发 wxml 重渲染，
  // 就会导致光标跳回、组合字符丢失（用户感知：打字回退）。
  // 因此 bindinput 完全不调用 setData，只把当前值暂存在实例字段 _pendingText 中，
  // 由 bindblur 时统一提交；字符计数也只在 bindblur 时更新。
  onTextInput(e) {
    const { qid } = e.currentTarget.dataset;
    const value = typeof e.detail === 'string' ? e.detail : '';
    if (!this._pendingText) this._pendingText = {};
    this._pendingText[qid] = value;
    // 同步答题卡状态（_setAnswer 内部已包含本判断，避免重复 setData）
    this._syncAnsweredState(qid);
    // 节流：每 ~5 次按键存一次草稿，兼顾性能和"切页面不丢数据"
    this._pendingSaveCount = (this._pendingSaveCount || 0) + 1;
    if (this._pendingSaveCount % 5 === 0) {
      this._autoSaveDraft();
    }
  },

  // 失焦时再写入 answers（作为提交数据源），保证输入过程不触发 value 重渲染
  onTextBlur(e) {
    const { qid } = e.currentTarget.dataset;
    const query = wx.createSelectorQuery().in(this);
    query.select(`#txt-${qid}`).fields({ properties: ['value'] }).exec(([node]) => {
      const raw = node && node.value;
      const value = (typeof raw === 'string') ? raw.trim() : '';
      this._setAnswer(qid, value);
      this.setData({ [`_charCounts.${qid}`]: value.length || 0 });
      this.setData({ [`_textValues.${qid}`]: value });
      this._autoSaveDraft();
      if (this._pendingText) delete this._pendingText[qid];
    });
  },

  // 多项填空：同 TEXT 思路，bindinput 不写 data
  onTextMultiInput(e) {
    const { qid, index } = e.currentTarget.dataset;
    const key = `${qid}_${index}`;
    const value = typeof e.detail === 'string' ? e.detail : '';
    if (!this._pendingTextMulti) this._pendingTextMulti = {};
    this._pendingTextMulti[key] = value;
    // 同步答题卡状态
    this._syncAnsweredState(qid);
    this._pendingSaveCount = (this._pendingSaveCount || 0) + 1;
    if (this._pendingSaveCount % 5 === 0) {
      this._autoSaveDraft();
    }
  },

  onTextMultiBlur(e) {
    const { qid, index } = e.currentTarget.dataset;
    const key = `${qid}_${index}`;
    const query = wx.createSelectorQuery().in(this);
    query.select(`#txtm-${qid}-${index}`).fields({ properties: ['value'] }).exec(([node]) => {
      const raw = node && node.value;
      const value = (typeof raw === 'string') ? raw : '';
      const current = this.data.answers[qid] || [];
      const updated = [...current];
      updated[index] = value;
      this._setAnswer(qid, updated);
      this.setData({ [`_textMultiValues.${key}`]: value });
      this._autoSaveDraft();
      if (this._pendingTextMulti) delete this._pendingTextMulti[key];
    });
  },

  // NPS 选择（自定义按钮）
  onNpsSelect(e) {
    const { qid, score } = e.currentTarget.dataset;
    this._setAnswer(qid, score);
  },

  onNpsChange(e) {
    const { qid } = e.currentTarget.dataset;
    this._setAnswer(qid, e.detail);
  },

  // SCALE 量表题:点 emoji 档
  onScaleEmojiTap(e) {
    const { qid, level } = e.currentTarget.dataset;
    this._setAnswer(qid, level);
  },

  onMatrixRadioChange(e) {
    const { qid, row } = e.currentTarget.dataset;
    const matrix = { ...(this.data.answers[qid] || {}) };
    matrix[row] = e.detail;
    this._setAnswer(qid, matrix);
  },

  onDateTap(e) {
    const { qid, format } = e.currentTarget.dataset;
    this.setData({
      datePickerInfo: { qid, format },
      showDatePicker: true,
      datePickerType: (format && format.includes('HH:mm')) ? 'datetime' : 'date',
      datePickerValue: Date.now(),
    });
  },

  onDatePickerClose() {
    this.setData({ showDatePicker: false });
  },

  onDatePickerConfirm(e) {
    const date = new Date(e.detail);
    const pad = n => String(n).padStart(2, '0');
    const value = this.data.datePickerType === 'datetime'
      ? `${date.getFullYear()}-${pad(date.getMonth()+1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
      : `${date.getFullYear()}-${pad(date.getMonth()+1)}-${pad(date.getDate())}`;
    const qid = this.data.datePickerInfo?.qid;
    if (qid) this._setAnswer(qid, value);
    this.setData({ showDatePicker: false });
  },

  _setAnswer(qid, value) {
    // 首次作答时启动计时器
    if (!this.data.start_time && !this.data._durationTimer) {
      this.setData({ start_time: Date.now() });
      this._startDurationTimer();
    }

    this.setData({ [`answers.${qid}`]: value });
    // 清除该题目的错误状态
    if (this.data.errors[qid]) {
      this.setData({ [`errors.${qid}`]: false });
    }
    // 同步答题卡状态
    this._syncAnsweredState(qid);
    // 每次作答自动写入 localStorage
    this._autoSaveDraft();
    this._updateProgress();
  },

  // 同步某题的已答状态到 _answeredMap（供 wxml 响应式读取）
  _syncAnsweredState(qid) {
    const questions = this.data.questions || [];
    const item = questions.find(q => q.qid === qid);
    if (!item) return;
    const answered = this._isQuestionAnswered(item);
    const cur = this.data._answeredMap || {};
    if (Boolean(cur[qid]) === answered) return;  // 无变化，跳过
    const updated = { ...cur };
    if (answered) {
      updated[qid] = true;
    } else {
      delete updated[qid];
    }
    this.setData({ _answeredMap: updated });
    this._updateAnswerCountsFromMap();
  },

  // 基于 _answeredMap 重新统计总数（比遍历 questions 快）
  _updateAnswerCountsFromMap() {
    const total = (this.data.questions || []).length;
    const answered = Object.keys(this.data._answeredMap || {}).length;
    this.setData({
      _answeredCount: answered,
      _totalQuestionCount: total,
    });
  },

  _updateProgress() {
    const questions = this.data.questions || [];
    const answers = this.data.answers || {};
    const total = questions.length;
    const answered = Object.values(answers).filter(v =>
      v !== null && v !== undefined && v !== '' &&
      !(Array.isArray(v) && v.length === 0) &&
      !(typeof v === 'object' && Object.keys(v).length === 0)
    ).length;
    this.setData({
      _progress: total > 0 ? Math.round((answered / total) * 100) : 0,
      _progressText: `${answered}/${total}`,
    });
  },

  // ================================================================
  // 校验
  // ================================================================

  _validateAll() {
    const errors = {};
    let hasError = false;
    for (const q of this.data.questions) {
      const val = this.data.answers[q.qid];
      const isEmpty = val === null || val === undefined || val === '' ||
        (Array.isArray(val) && val.length === 0) ||
        (typeof val === 'object' && Object.keys(val).length === 0);
      if (q.required && isEmpty) {
        errors[q.qid] = true;
        hasError = true;
      }
    }
    this.setData({ errors });
    return !hasError;
  },

  // ================================================================
  // 防作弊
  // ================================================================

  _setupAntiCheat() {
    wx.onAppShow(() => {
      const newCount = this.data.switch_count + 1;
      this.setData({ switch_count: newCount });
      const maxSwitch = this.data.max_switch;
      if (maxSwitch > 0 && newCount > maxSwitch) {
        wx.showModal({
          title: '检测到频繁切屏',
          content: `您已离开页面 ${newCount} 次，超过限制(${maxSwitch}次)，即将自动提交`,
          showCancel: false,
          success: () => this.onConfirmSubmit(),
        });
      } else if (newCount > 1) {
        wx.showToast({ title: `离开 ${newCount} 次/${maxSwitch}次`, icon: 'none' });
      }
    });
  },

  // ================================================================
  // 辅助计算方法
  // ================================================================

  // 滑动条百分比
  _calcSliderPercent(item, value) {
    const min = item.slider_min !== undefined ? item.slider_min : 0;
    const max = item.slider_max !== undefined ? item.slider_max : 100;
    const v = value !== null && value !== undefined ? value : min;
    return Math.max(0, Math.min(100, ((v - min) / (max - min)) * 100));
  },

  // 判断某题是否已作答（覆盖所有题型 + 暂存的输入内容）
  _isQuestionAnswered(item) {
    if (!item) return false;
    const qid = item.qid;
    // 优先读 pending（用户正在输入但还未失焦的内容）
    if (this._pendingText && this._pendingText[qid] !== undefined && this._pendingText[qid] !== '') {
      return true;
    }
    const ans = this.data.answers && this.data.answers[qid];
    if (ans === null || ans === undefined || ans === '') return false;
    if (Array.isArray(ans)) {
      if (ans.length === 0) return false;
      return ans.some(v => v !== null && v !== undefined && v !== '');
    }
    if (typeof ans === 'object') {
      return Object.values(ans).some(v => v !== null && v !== undefined && v !== '');
    }
    if (typeof ans === 'number') return true;
    if (typeof ans === 'string') return ans.trim().length > 0;
    return Boolean(ans);
  },

  // 点击侧边导航跳转到对应题目（滚动到视野）
  _onNavItemTap(e) {
    const { idx, qid } = e.currentTarget.dataset;
    this.setData({ _currentNavIdx: idx });
    this._scrollToQuestion(idx);
    // 答题卡中点击后关闭弹层
    if (this.data._showAnswerCard) {
      this.setData({ _showAnswerCard: false });
    }
  },

  noop() {},

  // 切换答题卡弹层
  _toggleAnswerCard() {
    this.setData({ _showAnswerCard: !this.data._showAnswerCard });
  },

  // 返回顶部
  _scrollToTop() {
    wx.pageScrollTo({ scrollTop: 0, duration: 400 });
  },

  // 通用：滚动到指定题目并留出 sticky 标题高度
  _scrollToQuestion(idx) {
    const query = wx.createSelectorQuery();
    query.select(`#q-${idx}`).boundingClientRect();
    query.selectViewport().scrollOffset();
    query.exec((res) => {
      if (!res || !res[0]) return;
      const rect = res[0];
      const scrollTop = res[1] ? res[1].scrollTop : 0;
      // 目标位置 = 题目顶部相对页面的偏移 - sticky 标题高度余量（~120px ≈ 240rpx）
      const targetTop = (rect.top + scrollTop) - 120;
      wx.pageScrollTo({
        scrollTop: Math.max(0, targetTop),
        duration: 300,
      });
    });
  },

  // 跳转到第一道未答题目
  _scrollToFirstUnanswered() {
    const questions = this.data.questions || [];
    for (let i = 0; i < questions.length; i++) {
      if (!this._isQuestionAnswered(questions[i])) {
        this.setData({ _currentNavIdx: i, _showAnswerCard: false });
        this._scrollToQuestion(i);
        return;
      }
    }
    // 全部答完，弹层提示一下
    wx.showToast({ title: '已全部答完 🎉', icon: 'none', duration: 1500 });
    this.setData({ _showAnswerCard: false });
  },

  // 更新已答题数统计（用于问卷加载/草稿回填后一次性同步）
  _updateAnswerCounts() {
    const questions = this.data.questions || [];
    const total = questions.length;
    const map = {};
    for (let i = 0; i < questions.length; i++) {
      const q = questions[i];
      if (this._isQuestionAnswered(q)) {
        map[q.qid] = true;
      }
    }
    this.setData({
      _answeredMap: map,
      _answeredCount: Object.keys(map).length,
      _totalQuestionCount: total,
    });
  },

  // 滑动条预设值点击
  _onSliderPreset(e) {
    const { value, qid } = e.currentTarget.dataset;
    this._setAnswer(qid, parseInt(value));
  },

  /**
   * van-slider 实时拖动事件 - 用户拖动时持续触发
   * van-slider 的 e.detail 就是当前数值（已经是 step 对齐后的最终值）
   * 注意: van-slider 是自定义组件,e.target 是内部实际触摸的元素( slider__button-wrapper ),
   * 其上定义了 data-qid="..." 属性,所以用 e.target.dataset.qid 最可靠。
   */
  _onVanSliderChange(e) {
    const qid = e.target.dataset.qid || e.currentTarget.dataset.qid;
    const value = e.detail;
    if (qid == null || value == null) return;
    if (this.data.answers[qid] !== value) {
      this._setAnswer(qid, value);
    }
  },

  /**
   * van-slider 拖动结束事件 - 触发一次"完成"提示(可选)
   */
  _onVanSliderDragEnd(e) {
    // 拖动结束时不需额外动作,值已在 change 中写入
  },

  /**
   * 评分五角星点击
   * bindtap 直接绑在 <text> 上,e.currentTarget 就是 text 本身,dataset 一定有 data-qid / data-score
   */
  onRateTap(e) {
    const ds = e.currentTarget.dataset || {};
    const score = ds.score;
    const qid = ds.qid;
    console.log('[survey-fill] onRateTap', qid, score);
    if (score == null || qid == null) return;
    this._setAnswer(qid, +score);
  },

  // NPS 反馈文案
  _npsFeedbackText(score) {
    if (score === -1) return '不适用';
    if (score <= 6) return '批评者';
    if (score <= 8) return '被动者';
    return '推荐者';
  },

  // ================================================================
  // 自动草稿保存（每次作答触发，无 UI 反馈）
  // 关键：把 bindinput 暂存在 _pendingText 的内容也合并到草稿，
  // 避免用户还在输入（未失焦）时跳走页面导致内容丢失。
  // ================================================================

  _collectPendingTextValues() {
    // 把 _pendingText 合并进 _textValues（不修改 page.data，避免触发渲染）
    const merged = { ...(this.data._textValues || {}) };
    if (this._pendingText) {
      Object.keys(this._pendingText).forEach(qid => {
        merged[qid] = this._pendingText[qid];
      });
    }
    return merged;
  },

  _collectPendingTextMultiValues() {
    const merged = { ...(this.data._textMultiValues || {}) };
    if (this._pendingTextMulti) {
      Object.keys(this._pendingTextMulti).forEach(key => {
        merged[key] = this._pendingTextMulti[key];
      });
    }
    return merged;
  },

  _autoSaveDraft() {
    const { sid, answers } = this.data;
    if (!sid) return;
    // 把 pending 暂存同步进 answers，保证切页面后刷新也能回填
    const liveAnswers = { ...answers };
    if (this._pendingText) {
      Object.keys(this._pendingText).forEach(qid => {
        if (liveAnswers[qid] === null || liveAnswers[qid] === undefined || liveAnswers[qid] === '') {
          liveAnswers[qid] = this._pendingText[qid];
        }
      });
    }
    const answerList = Object.entries(liveAnswers).map(([qid, value]) => ({ qid, value }));
    wx.setStorageSync(`survey_draft_${sid}`, {
      answers: answerList,
      textValues: this._collectPendingTextValues(),
      textMultiValues: this._collectPendingTextMultiValues(),
      saved_at: Date.now(),
    });
  },

  _startDraftTimer() {
    // 定时器保留（页面隐藏/返回场景兜底），每次触发也是写 localStorage
    if (this.data.draft_timer) clearInterval(this.data.draft_timer);
    // 输入频繁时 3 秒一次足够，覆盖"正在打字→切走页面"的场景
    const timer = setInterval(() => this._autoSaveDraft(), 3000);
    this.setData({ draft_timer: timer });
  },

  // ================================================================
  // 提交流程
  // ================================================================

  onSubmitTap() {
    if (this.data.already_submitted) {
      wx.showModal({ title: '提示', content: '您已经提交过该问卷，不能重复提交', showCancel: false });
      return;
    }
    if (this.data.submit_can_submit === false || this.data.submit_remaining <= 0) {
      wx.showModal({
        title: '已达提交上限',
        content: this.data.submit_message || `本周期内最多提交 ${this.data.submit_limit} 次，您已用完`,
        showCancel: false,
        confirmText: '我知道了',
      });
      return;
    }
    if (!this._validateAll()) {
      const firstErrorQid = Object.keys(this.data.errors).find(qid => this.data.errors[qid]);
      if (firstErrorQid) {
        const qIndex = this.data.questions.findIndex(q => q.qid === firstErrorQid);
        if (qIndex >= 0) this._scrollToQuestion(qIndex);
      }
      wx.showToast({ title: '请完善必填信息', icon: 'none', duration: 2000 });
      return;
    }
    this.setData({ show_confirm: true });
  },

  async onConfirmSubmit() {
    this.setData({ show_confirm: false, submitting: true });

    try {
      let wx_code = '';
      for (let i = 0; i < 2 && !wx_code; i++) {
        try {
          const loginRes = await new Promise((resolve, reject) => {
            wx.login({ success: resolve, fail: reject });
          });
          wx_code = loginRes.code || '';
        } catch (e) {
          if (i === 0) await new Promise(r => setTimeout(r, 300));
        }
      }

      const { sid, aid, answers, questions } = this.data;
      const answerList = Object.entries(answers).map(([qid, value]) => {
        const q = questions.find(q => q.qid === qid);
        let value_text = '';
        if (q && q.options) {
          if (Array.isArray(value)) {
            value_text = value.map(v => {
              const opt = q.options.find(o => o.id === v || o.value === v);
              return opt ? opt.label : v;
            }).join(', ');
          } else if (value !== null && value !== undefined) {
            const opt = q.options.find(o => o.id === value || o.value === value);
            value_text = opt ? opt.label : String(value);
          }
        } else if (value !== null && value !== undefined) {
          value_text = String(value);
        }
        return { qid, value, value_text, qtype: q ? q.qtype : 'TEXT' };
      });

      const usedSec = Math.round((Date.now() - this.data.start_time) / 1000);
      const { ts: sig_ts, nonce: sig_nonce } = this._buildNonce();
      await post(`/survey-fill/surveys/${sid}/submit`, {
        aid: aid || null,
        answers: answerList,
        duration_sec: usedSec,
        device_id: this._getDeviceId(),
        wx_code,
        sig_ts,
        sig_nonce,
      });

      this._stopTimers();
      wx.removeStorageSync(`survey_draft_${sid}`);

      // 生成凭据 ID，显示成功弹窗
      const receiptId = Date.now().toString().slice(-8);
      this.setData({
        submitting: false,
        showSuccessModal: true,
        _receiptId: receiptId,
        already_submitted: true,
      });

    } catch (err) {
      console.error('submit error', err);
      if (err.data?.errors) {
        const errors = {};
        err.data.errors.forEach(e => { errors[e.qid] = true; });
        this.setData({ errors });
        const qIndex = this.data.questions.findIndex(q => q.qid === err.data.errors[0].qid);
        if (qIndex >= 0) this._scrollToQuestion(qIndex);
      }
      if (err.code === 4001 || err.data?.code === 4001) {
        this.setData({
          submit_can_submit: false,
          submit_remaining: 0,
          error_msg: err.message || '提交次数已达上限',
        });
      }
      this.showError(err.message || '提交失败');
      this.setData({ submitting: false });
    }
  },

  onCancelSubmit() {
    this.setData({ show_confirm: false });
  },

  // 成功弹窗：返回列表
  onSuccessBackToList() {
    this.setData({ showSuccessModal: false });
    wx.reLaunch({ url: '/pages/home/home' });
  },

  // 成功弹窗：重新作答
  onSuccessRetake() {
    this.setData({
      showSuccessModal: false,
      answers: {},
      errors: {},
      _charCounts: {},
      _multiLengths: {},
      _selectedOptions: {},
      start_time: Date.now(),
      _progress: 0,
      _progressText: '0/0',
    });
    this._startDurationTimer();
    this._startDraftTimer();
  },

  onBack() {
    wx.navigateBack();
  },

  // ================================================================
  // 工具
  // ================================================================

  _stopTimers() {
    if (this.data.draft_timer) { clearInterval(this.data.draft_timer); this.setData({ draft_timer: null }); }
    if (this.data._durationTimer) { clearInterval(this.data._durationTimer); this.setData({ _durationTimer: null }); }
  },

  _startDurationTimer() {
    if (this.data._durationTimer) clearInterval(this.data._durationTimer);
    const update = () => {
      const sec = Math.round((Date.now() - (this.data.start_time || Date.now())) / 1000);
      const m = Math.floor(sec / 60);
      const s = sec % 60;
      const pad = n => String(n).padStart(2, '0');
      this.setData({ _durationText: `${pad(m)}:${pad(s)}` });
    };
    update();
    const timer = setInterval(update, 1000);
    this.setData({ _durationTimer: timer });
  },

  _getDeviceId() {
    if (this._device_id) return this._device_id;
    try {
      const info = wx.getDeviceInfo();
      this._device_id = `${info.platform}_${info.brand}_${info.model}_${info.system}`.replace(/\s/g, '_').substring(0, 64);
    } catch (e) {
      this._device_id = `unknown_${Date.now()}`;
    }
    return this._device_id;
  },

  _buildNonce() {
    const ts = Math.floor(Date.now() / 1000);
    const nonce = `${ts}_${Math.random().toString(36).slice(2, 10)}${Date.now().toString(36)}`;
    return { ts, nonce };
  },

  _buildLimitSummary(data) {
    const period = data.submit_limit_period || 'once';
    const periodLabel = { once: '终身', day: '今天', week: '本周', month: '本月', forever: '今天' }[period] || '当前周期';
    const limit = Number(data.submit_limit || 0);
    const used = Number(data.submit_used || 0);
    const remaining = Number(data.submit_remaining != null ? data.submit_remaining : 0);
    const canSubmit = data.submit_can_submit !== false;
    if (limit === 0) return { text: `不限提交次数`, tone: 'ok' };
    if (!canSubmit || remaining <= 0) return { text: `本问卷${periodLabel}最多填 ${limit} 次，您已用完，无法再提交`, tone: 'block' };
    if (used === 0) return { text: `${periodLabel}可填 ${limit} 次，本次为第1次`, tone: 'ok' };
    return { text: `${periodLabel}已填 ${used}/${limit} 次，还剩 ${remaining} 次机会`, tone: 'warn' };
  },

  showError(msg) {
    wx.showToast({ title: msg, icon: 'none', duration: 2000 });
  },
}, {
  requireAuth: false,
  autoRegisterComponents: false,
});
