const { createPage } = require('../../../utils/page-mixin');
const { tokenGet } = require('../../../utils/request');
const { API } = require('../../../utils/api');

/**
 * 成绩页（双入口）
 * - source=exame：中职学生 exame 系统（102:8086 代理）
 *   - 列表：GET /exame/exams/records
 *   - 详情：GET /exame/exams/records/{id}/paper（退化到 /record/{id}）
 * - 默认（无 source）：开放学生自研成绩（controllers/student_info.py /student/get_scores）
 *   - 列表：GET /student/get_scores → 直接返回 scores_list 数组
 *   - 详情：不支持单条详情，detail 模式仅 exame 用
 */
createPage({
  data: {
    mode: 'list',           // 'list' | 'detail'
    source: '',             // '' 自研 | 'exame' 中职 exame
    loading: true,
    records: [],
    detail: null,
    recordId: null,
  },

  onLoad(options) {
    const source = (options && options.source) || '';
    if (options && options.record_id) {
      this.setData({ mode: 'detail', source, recordId: Number(options.record_id) });
      this.loadDetail();
    } else {
      this.setData({ mode: 'list', source });
      this.loadList();
    }
  },

  onShow() {
    if (this.data.mode === 'list') this.loadList();
    if (this.data.mode === 'detail' && this.data.recordId) this.loadDetail();
  },

  onPullDownRefresh() {
    const task = this.data.mode === 'detail' ? this.loadDetail() : this.loadList();
    task.then(() => wx.stopPullDownRefresh());
  },

  async loadList() {
    this.setData({ loading: true });
    try {
      if (this.data.source === 'exame') {
        const resp = await tokenGet(
          API.EXAME_SCORE.LIST,
          { page: 1, page_size: 50 },
          { loadingTitle: '获取成绩列表...' }
        );
        const data = resp && resp.data ? resp.data : resp;
        this.setData({ records: (data && data.list) || [], loading: false });
      } else {
        // 自研：开放学生上学期考试成绩，直接返回数组
        const data = await tokenGet(
          API.SCORE.GET_LIST,
          {},
          { loadingTitle: '获取成绩列表...' }
        );
        const list = Array.isArray(data) ? data : (data && data.list) || [];
        // 归一化给 wxml：course_name → exam_title，total_score 保持
        const records = list.map((s, idx) => ({
          id: s.course_id || idx,
          exam_title: s.course_name || s.kcmc || '未知课程',
          score: s.total_score,
          total_score: s.total_score,
          form_score: s.form_score,
          final_score: s.final_score,
          is_passed: s.total_score != null && Number(s.total_score) >= 60,
          grading_status: 'done',
          submitted_at: '',
          _self: true,
        }));
        this.setData({ records, loading: false });
      }
    } catch (err) {
      this.setData({ loading: false });
      this.showError(err.message || err.msg || '获取成绩列表失败');
    }
  },

  async loadDetail() {
    this.setData({ loading: true });
    const fmt = (s) => {
      if (!s) return '';
      const d = new Date(s);
      if (isNaN(d.getTime())) return s;
      const p = (n) => (n < 10 ? '0' + n : '' + n);
      return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
    };
    const typeMap = { 1: '单选题', 2: '多选题', 3: '判断题', 4: '填空题', 5: '简答题' };
    const normalize = (data) => {
      if (!data) return data;
      const out = { ...data };
      if (out.submitted_at) out.submitted_at = fmt(out.submitted_at);
      if (out.started_at) out.started_at = fmt(out.started_at);
      out.questions = (out.questions || []).map((q, idx) => {
        const nq = { ...q };
        nq.typeLabel = typeMap[q.type] || q.type || '未知';
        nq.order = idx + 1;
        // 正确答案文本：客观题从 options.is_correct 提取 label
        if ((q.type === 1 || q.type === 2 || q.type === 3) && Array.isArray(q.options)) {
          const corrects = q.options.filter(o => o.is_correct).map(o => o.label || o.content);
          nq.correctText = corrects.join('、') || '-';
          // 我的答案文本：student_answer 可能是 id（数字）或 label
          const mine = q.student_answer ?? q.user_answer;
          if (mine == null || mine === '') {
            nq.mineText = '未作答';
          } else if (Array.isArray(q.options) && q.options.length) {
            const parts = String(mine).split(',').map(s => s.trim()).filter(s => s !== '');
            nq.mineText = parts.map(p0 => {
              const hit = q.options.find(o => String(o.id) === p0 || (o.label || '').toUpperCase() === p0.toUpperCase());
              return hit ? (hit.label ? `${hit.label} ${hit.content || ''}`.trim() : (hit.content || p0)) : p0;
            }).join('、');
          } else {
            nq.mineText = String(mine);
          }
        } else {
          const mine = q.student_answer ?? q.user_answer ?? '';
          nq.mineText = mine === '' || mine == null ? '未作答' : String(mine);
          nq.correctText = '';
        }
        return nq;
      });
      return out;
    };
    try {
      const resp = await tokenGet(
        API.EXAME_SCORE.PAPER(this.data.recordId),
        {},
        { loadingTitle: '获取成绩详情...' }
      );
      const data = resp && resp.data ? resp.data : resp;
      this.setData({ detail: normalize(data), loading: false });
    } catch (err) {
      try {
        const resp2 = await tokenGet(
          API.EXAME_SCORE.DETAIL(this.data.recordId),
          {},
          { loadingTitle: '获取成绩详情...' }
        );
        const data = resp2 && resp2.data ? resp2.data : resp2;
        this.setData({ detail: normalize(data), loading: false });
      } catch (err2) {
        this.setData({ loading: false });
        this.showError(err2.message || err2.msg || '获取成绩详情失败');
      }
    }
  },

  goToDetail(e) {
    // 自研成绩没有单条详情页，不跳转
    const item = (e.currentTarget.dataset || {});
    if (this.data.source !== 'exame') return;
    const recordId = e.currentTarget.dataset.record;
    wx.redirectTo({
      url: `/packageStudent/pages/score/score?source=exame&record_id=${recordId}`
    });
  },

  goToExameList() {
    if (this.data.source === 'exame') {
      wx.redirectTo({ url: '/packageStudent/pages/exame-list/exame-list' });
    } else {
      wx.redirectTo({ url: '/packageStudent/pages/my/my' });
    }
  },

  goBack() {
    this.goToExameList();
  },
}, {
  // 双端共用：中职（source=exame）+ 开放（自研），不限制 userType，只要求登录
  requireAuth: true
});
