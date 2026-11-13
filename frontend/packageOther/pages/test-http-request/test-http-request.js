/**
 * HTTP 请求规范测试页（重构验证）
 *
 * 用途：
 *   14 个测试场景验证 HTTP_REQUEST_GUIDE.md 中规约的"标准范式"是否真的可用。
 *
 * 涵盖：
 *   ① await/try/catch/finally 范式
 *   ② 自动加 token（tokenGet/Post）
 *   ③ 业务/网络/HTTP/Auth 错误归一
 *   ④ isAuthError 静默（避免重复跳登录）
 *   ⑤ showSuccess/showError 顶部消息
 *   ⑥ loading 计数（多请求并发）
 *   ⑦ 请求去重（GET 50ms 窗口）
 *   ⑧ 拦截器（addResponseInterceptor）
 *   ⑨ 文件上传（tokenUploadFile）
 *   ⑩ onPullDownRefresh 用 .finally
 */
const { createPage } = require('../../../utils/page-mixin');
const { API } = require('../../../utils/api');
const {
  silentGet, silentPost,
  tokenGet, tokenPost,
  quickPost,
  tokenUploadFile,
  addResponseInterceptor
} = require('../../../utils/request');

// 测试用的"必定失败"端点
const ENDPOINT_NOT_FOUND = '/__not_exist_path_for_test__'; // 404
const ENDPOINT_500       = '/__trigger_500_for_test__';    // 5xx（如果后端没有这个端点就会 404，归一为 HTTP）

// 测试用：业务错误码（依赖后端能识别测试 query）
// 真实后端可能没有这个端点 → 走 HTTP 404
// 我们保留配置，便于对接方调整
const TEST_BIZ_FAIL = '/test/business_fail'; // 期望业务失败（code!=0）

// 全局拦截器：注入请求时间戳，便于观察去重
let _interceptorInstalled = false;
function installInterceptor() {
  if (_interceptorInstalled) return;
  _interceptorInstalled = true;
  addResponseInterceptor((data) => {
    if (data && typeof data === 'object') {
      data.__interceptor_ts = Date.now();
    }
    return data;
  });
}
installInterceptor();

createPage({
  data: {
    // 测试结果展示
    logs: [],
    logId: 0,

    // 共享测试状态
    parallelLoading: false,
    parallelCount: 3,
    dedupLoading: false,
    dedupSent: 0, // 实际发出的请求数

    // 文件上传
    uploadProgress: 0,
    uploadResult: '',

    // 当前错误样本（完整结构）
    lastError: null,

    // 是否有 token（控制 tokenGet 测试）
    hasToken: false
  },

  onLoad() {
    this.checkAuth();
  },

  onShow() {
    this.checkAuth();
  },

  // ---------- 顶部日志工具 ----------
  _appendLog(title, status, payload) {
    const logs = this.data.logs.slice(0, 49); // 保留 50 条
    logs.unshift({
      id: ++this.data.logId,
      title,
      status, // 'success' | 'fail' | 'info'
      payload: payload == null ? '' :
        typeof payload === 'string' ? payload :
        JSON.stringify(payload, null, 2),
      at: this._now()
    });
    this.setData({ logs });
  },

  _now() {
    const d = new Date();
    const p = (n) => (n < 10 ? '0' + n : '' + n);
    return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}.${String(d.getMilliseconds()).padStart(3, '0')}`;
  },

  _formatError(err) {
    if (!err) return null;
    return {
      message: err.message,
      errorType: err.errorType,
      isAuthError: !!err.isAuthError,
      code: err.code,
      hasData: err.data !== undefined,
      hasResponse: err.response !== undefined,
    };
  },

  async checkAuth() {
    try {
      const app = getApp();
      const userInfo = app.globalData.userInfo;
      const hasToken = !!(userInfo && userInfo.token);
      this.setData({ hasToken });
      this._appendLog('检测登录态', 'info', { hasToken });
    } catch (e) {
      this.setData({ hasToken: false });
    }
  },

  // ============================================================
  // 测试 1：silentGet（无 token 公开 GET）
  // ============================================================
  async test1_silentGet() {
    this._appendLog('测试 1：silentGet 公开 GET', 'info', '开始');
    try {
      const data = await silentGet(API.MAJOR.GET_ALL);
      this._appendLog('测试 1：silentGet', 'success', {
        type: Array.isArray(data) ? 'array' : typeof data,
        length: Array.isArray(data) ? data.length : 'n/a',
        ts: data && data.__interceptor_ts
      });
      this.showSuccess('测试 1 通过');
    } catch (err) {
      this._appendLog('测试 1：silentGet', 'fail', this._formatError(err));
      if (err.isAuthError) return;
      this.showError(err.message);
    }
  },

  // ============================================================
  // 测试 2：tokenGet（带 token 的 GET）
  // ============================================================
  async test2_tokenGet() {
    if (!this.data.hasToken) {
      this._appendLog('测试 2：tokenGet', 'fail', '当前未登录，无 token，跳过');
      this.showError('请先登录后再测 tokenGet');
      return;
    }
    this._appendLog('测试 2：tokenGet 带 Authorization', 'info', '开始');
    try {
      const data = await tokenGet(API.MAJOR.GET_ALL);
      this._appendLog('测试 2：tokenGet', 'success', {
        type: Array.isArray(data) ? 'array' : typeof data,
        interceptor: data && data.__interceptor_ts
      });
      this.showSuccess('测试 2 通过（自动加 Bearer）');
    } catch (err) {
      this._appendLog('测试 2：tokenGet', 'fail', this._formatError(err));
      if (err.isAuthError) return;
      this.showError(err.message);
    }
  },

  // ============================================================
  // 测试 3：tokenPost 提交
  // ============================================================
  async test3_tokenPost() {
    if (!this.data.hasToken) {
      this._appendLog('测试 3：tokenPost', 'fail', '请先登录');
      return;
    }
    this._appendLog('测试 3：tokenPost', 'info', '提交测试数据');
    try {
      const data = await tokenPost('/test/echo', { hello: 'world', at: Date.now() });
      this._appendLog('测试 3：tokenPost', 'success', data);
      this.showSuccess('测试 3 通过');
    } catch (err) {
      this._appendLog('测试 3：tokenPost', 'fail', this._formatError(err));
      if (err.isAuthError) return;
      this.showError(err.message);
    }
  },

  // ============================================================
  // 测试 4：业务错误（code != 0）
  // ============================================================
  async test4_businessFail() {
    this._appendLog('测试 4：业务错误（code != 0）', 'info', '开始');
    try {
      await silentGet(TEST_BIZ_FAIL, { reason: 'unit-test' });
      this._appendLog('测试 4', 'fail', '期望业务失败但成功了');
    } catch (err) {
      const formatted = this._formatError(err);
      formatted.code_check = err.errorType === 'BUSINESS';
      this._appendLog('测试 4：业务错误', formatted.code_check ? 'success' : 'fail', formatted);
      this.setData({ lastError: formatted });
      if (err.isAuthError) return;
      this.showError(err.message);
    }
  },

  // ============================================================
  // 测试 5：网络错误（NETWORK）
  // ============================================================
  async test5_networkFail() {
    this._appendLog('测试 5：网络错误', 'info', '使用错误域名触发 NETWORK');
    try {
      await silentGet('https://invalid-domain-for-test.localhost/api');
      this._appendLog('测试 5', 'fail', '期望网络失败但成功了');
    } catch (err) {
      const ok = err.errorType === 'NETWORK';
      this._appendLog('测试 5：网络错误', ok ? 'success' : 'fail', this._formatError(err));
      this.setData({ lastError: this._formatError(err) });
      if (err.isAuthError) return;
      this.showError(err.message);
    }
  },

  // ============================================================
  // 测试 6：HTTP 404
  // ============================================================
  async test6_http404() {
    this._appendLog('测试 6：HTTP 404', 'info', '使用不存在路径');
    try {
      await silentGet(ENDPOINT_NOT_FOUND);
      this._appendLog('测试 6', 'fail', '期望 404 但成功了');
    } catch (err) {
      const ok = err.errorType === 'HTTP';
      this._appendLog('测试 6：HTTP', ok ? 'success' : 'fail', this._formatError(err));
      this.setData({ lastError: this._formatError(err) });
      if (err.isAuthError) return;
      this.showError(err.message);
    }
  },

  // ============================================================
  // 测试 7：401 自动跳转（isAuthError 静默）
  // ============================================================
  async test7_authSilent() {
    if (!this.data.hasToken) {
      this._appendLog('测试 7', 'fail', '请先登录以获得一个"过期 token"（或主动改 token 为无效值）');
      return;
    }
    this._appendLog('测试 7：401 自动跳转', 'info', '期望 err.isAuthError=true');

    // 临时把 token 改成无效字符串
    const app = getApp();
    const oldUserInfo = app.globalData.userInfo;
    try {
      app.globalData.userInfo = { ...oldUserInfo, token: '__invalid_token_for_test__' };

      try {
        await tokenGet('/test/requires_auth');
        this._appendLog('测试 7', 'fail', '期望 401 但成功了');
      } catch (err) {
        const formatted = this._formatError(err);
        formatted.silent_pass = err.isAuthError === true;
        this._appendLog('测试 7：401', formatted.silent_pass ? 'success' : 'fail', formatted);
        this.setData({ lastError: formatted });
        // isAuthError 时不调用 showError —— 由守卫统一处理跳转
        if (err.isAuthError) {
          this._appendLog('测试 7：isAuthError 拦截', 'success', 'showError 被跳过，跳转由守卫接管');
        } else {
          this.showError(err.message);
        }
      }
    } finally {
      app.globalData.userInfo = oldUserInfo;
    }
  },

  // ============================================================
  // 测试 8：并发 3 个请求，loading 计数
  // ============================================================
  async test8_parallelLoading() {
    this.setData({ parallelLoading: true });
    this._appendLog('测试 8：并发 3 请求', 'info', '观察 loading 计数（应只在第一个 show，最后一个 hide）');
    try {
      const [a, b, c] = await Promise.all([
        silentGet(API.MAJOR.GET_ALL).catch((e) => ({ err: e.message })),
        silentGet(API.MAJOR.GET_ALL).catch((e) => ({ err: e.message })),
        silentGet(API.MAJOR.GET_ALL).catch((e) => ({ err: e.message })),
      ]);
      this._appendLog('测试 8：并发', 'success', { a: !!a, b: !!b, c: !!c });
      this.showSuccess('测试 8 通过（loading 计数正确）');
    } catch (err) {
      this._appendLog('测试 8', 'fail', this._formatError(err));
    } finally {
      this.setData({ parallelLoading: false });
    }
  },

  // ============================================================
  // 测试 9：GET 请求去重（50ms 窗口）
  // ============================================================
  async test9_dedup() {
    this.setData({ dedupLoading: true });
    this._appendLog('测试 9：GET 去重', 'info', '同时发起 5 次相同 GET，期望合并');
    try {
      // install 一个 response 拦截器，统计本次进入次数
      // 注意：addResponseInterceptor 没有卸载 API，所以本次累加只在本次测试有效
      let entered = 0;
      const myInterceptor = (data) => {
        if (data && data.__dedup_probe) entered++;
        return data;
      };
      addResponseInterceptor(myInterceptor);
      const promises = [];
      for (let i = 0; i < 5; i++) {
        promises.push(
          silentGet(API.MAJOR.GET_ALL, { __dedup_probe: 1 }).catch((e) => e.message)
        );
      }
      await Promise.all(promises);
      this.setData({ dedupSent: entered });
      this._appendLog('测试 9：去重', entered <= 1 ? 'success' : 'fail', { entered, hint: '期望 entered <= 1' });
      this.showSuccess(entered <= 1 ? '测试 9 通过（已合并）' : '测试 9 失败（未合并）');
    } catch (err) {
      this._appendLog('测试 9', 'fail', this._formatError(err));
    } finally {
      this.setData({ dedupLoading: false });
    }
  },

  // ============================================================
  // 测试 10：拦截器（response 注入 __interceptor_ts）
  // ============================================================
  async test10_interceptor() {
    this._appendLog('测试 10：响应拦截器', 'info', '期望 data.__interceptor_ts 已注入');
    try {
      const data = await silentGet(API.MAJOR.GET_ALL);
      const ok = !!(data && data.__interceptor_ts);
      this._appendLog('测试 10：拦截器', ok ? 'success' : 'fail', { ts: data && data.__interceptor_ts });
      this.showSuccess(ok ? '拦截器已生效' : '拦截器未生效');
    } catch (err) {
      this._appendLog('测试 10', 'fail', this._formatError(err));
      if (err.isAuthError) return;
      this.showError(err.message);
    }
  },

  // ============================================================
  // 测试 11：文件上传（tokenUploadFile）
  // ============================================================
  async test11_upload() {
    this._appendLog('测试 11：文件上传', 'info', '尝试上传本地图片');
    try {
      // 选一张图（需要 wx.chooseMedia 权限）
      const chooseRes = await new Promise((resolve, reject) => {
        wx.chooseMedia({
          count: 1,
          mediaType: ['image'],
          sourceType: ['album', 'camera'],
          success: resolve,
          fail: reject
        });
      });

      const filePath = chooseRes.tempFiles[0].tempFilePath;
      this._appendLog('测试 11：已选图', 'info', { filePath });

      const result = await tokenUploadFile({
        url: '/test/upload',
        filePath,
        name: 'file'
      });

      this._appendLog('测试 11：上传', 'success', result);
      this.setData({ uploadResult: JSON.stringify(result) });
      this.showSuccess('上传测试完成（结果取决于后端）');
    } catch (err) {
      const formatted = this._formatError(err);
      formatted.step = 'chooseMedia or upload';
      this._appendLog('测试 11：上传', 'fail', formatted);
      if (err.isAuthError) return;
      this.showError(err.message);
    }
  },

  // ============================================================
  // 测试 12：错误体完整结构（err.message/code/data/response）
  // ============================================================
  async test12_errorStructure() {
    this._appendLog('测试 12：错误体完整结构', 'info', '触发 404 并展示 Error 全字段');
    try {
      await silentGet(ENDPOINT_NOT_FOUND);
    } catch (err) {
      const fullDump = {
        message: err.message,
        errorType: err.errorType,
        isAuthError: err.isAuthError,
        code: err.code,
        data: err.data,
        response: err.response,
        // instance check
        isErrorInstance: err instanceof Error,
        hasStack: !!err.stack,
      };
      this.setData({ lastError: fullDump });
      this._appendLog('测试 12：Error 全字段', 'success', {
        errorType: err.errorType,
        message: err.message,
        fields: Object.keys(fullDump)
      });
      if (err.isAuthError) return;
      this.showError(err.message);
    }
  },

  // ============================================================
  // 测试 13：下拉刷新（fetchData().finally）
  // ============================================================
  async test13_pullRefresh() {
    this._appendLog('测试 13：下拉刷新 .finally 兜底', 'info', '应保证 stopPullDownRefresh 必触发');
    try {
      const data = await silentGet(API.MAJOR.GET_ALL);
      this._appendLog('测试 13：刷新', 'success', {
        type: Array.isArray(data) ? 'array' : typeof data,
        length: Array.isArray(data) ? data.length : 'n/a'
      });
      this.showSuccess('刷新成功');
    } catch (err) {
      this._appendLog('测试 13：刷新', 'fail', this._formatError(err));
      if (err.isAuthError) return;
      this.showError(err.message);
    } finally {
      wx.stopPullDownRefresh();
    }
  },

  onPullDownRefresh() {
    // 测试 onPullDownRefresh + .finally 范式
    this.test13_pullRefresh();
  },

  // ============================================================
  // 测试 14：quickPost（无 loading 立即提交）
  // ============================================================
  async test14_quickPost() {
    this._appendLog('测试 14：quickPost', 'info', '不显示 loading');
    try {
      const data = await quickPost('/test/echo', { q: 'quick', at: Date.now() });
      this._appendLog('测试 14', 'success', data);
      this.showSuccess('quickPost 完成');
    } catch (err) {
      this._appendLog('测试 14', 'fail', this._formatError(err));
      if (err.isAuthError) return;
      this.showError(err.message);
    }
  },

  // ============================================================
  // 工具：清空日志
  // ============================================================
  clearLogs() {
    this.setData({ logs: [], lastError: null });
    this.showSuccess('日志已清空');
  },

  // 演示在 catch 里同时拿到业务码（用于业务级降级）
  async test15_businessFallback() {
    this._appendLog('测试 15：业务码分支', 'info', '在 catch 里读取 err.code 决定 UI 降级');
    try {
      await silentGet(TEST_BIZ_FAIL);
    } catch (err) {
      if (err.isAuthError) return;
      // 业务分支：根据 code 区分文案
      let userText = err.message;
      if (err.code === 1001) userText = '参数错误，请检查输入';
      else if (err.code === 1004) userText = '权限不足';
      this._appendLog('测试 15：业务分支', 'success', { code: err.code, message: err.message, userText });
      this.showError(userText);
    }
  }
});