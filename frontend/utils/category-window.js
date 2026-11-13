/**
 * 招生/调查类别时间窗口校验工具（纯函数）
 *
 * 在 home 入口（点击跳转前）调用 evaluateWindow(info)：
 *  - ok=false 时由调用方使用 this.showError(message) 提示并阻止跳转；
 *  - ok=true 时正常 navigateTo 进入采集页。
 *
 * 字段约定：后端 zs_category 提供 start_time / end_time / is_active / batch。
 */

/**
 * 解析后端返回的类别信息，判断当前是否可填写。
 * @param {object} info { is_active, start_time, end_time, batch, name, window_message }
 * @returns {{ ok: boolean, message: string, batch: number|null, phase: 'inactive'|'not_started'|'ended'|'open' }}
 */
function evaluateWindow(info) {
  if (!info) {
    return { ok: false, message: '未获取到调查信息', batch: null, phase: 'inactive' };
  }
  if (info.is_active === false) {
    return { ok: false, message: info.window_message || '该调查已停用', batch: info.batch || null, phase: 'inactive' };
  }
  const now = Date.now();
  const start = info.start_time ? new Date(info.start_time).getTime() : null;
  const end = info.end_time ? new Date(info.end_time).getTime() : null;
  if (start && now < start) {
    return {
      ok: false,
      phase: 'not_started',
      message: info.window_message || `调查未开始，开始时间：${formatTime(info.start_time)}`,
      batch: info.batch || null
    };
  }
  if (end && now > end) {
    return {
      ok: false,
      phase: 'ended',
      message: info.window_message || `调查已结束，结束时间：${formatTime(info.end_time)}`,
      batch: info.batch || null
    };
  }
  return { ok: true, message: '', batch: info.batch != null ? info.batch : null, phase: 'open' };
}

function formatTime(iso) {
  if (!iso) return '';
  try {
    const d = new Date(iso);
    const pad = (n) => (n < 10 ? '0' + n : '' + n);
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
  } catch (e) {
    return iso;
  }
}

module.exports = { evaluateWindow, formatTime };
