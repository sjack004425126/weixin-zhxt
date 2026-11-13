/**
 * 本人头像上传工具（4 个个人中心页面共用）
 *
 * 后端流程与已下线的 packageStudent/pages/photo-upload 保持一致：
 *   选图 → POST /photo/upload_my_avatar（AI 抠图 + 美颜 + 上传 MinIO + 同步海康）
 *        → 轮询 GET /photo/task_status/{task_id}
 *
 * 与旧页面的关键差异：
 *   - 不再需要"手机号二次验证"（登录后 token 已带身份）
 *   - 不再需要前端传身份证号（后端从 JWT 推导身份，杜绝越权）
 *   - 允许覆盖更新（不再有"已上传过不能重复上传"的限制）
 */
const { BASE_URL } = require('./request');
const { resolveImageUrl } = require('./image-url');

const app = getApp();

// 轮询配置
const POLL_MAX_RETRIES = 60;   // 最多轮询次数(60 * 2s = 120s)
const POLL_INTERVAL_MS = 2000; // 每次间隔 2 秒

// 默认美颜参数（与后端 DEFAULT_AVATAR_BEAUTY 保持一致）
const DEFAULT_BEAUTY = {
  whitening_strength: 8,
  brightness_strength: 5,
  contrast_strength: 5,
  sharpen_strength: 2,
  saturation_strength: 5,
};

/**
 * 读取当前登录用户的 token。
 * 依次尝试：globalData → 各角色 storage（教师为嵌套结构）。
 */
function readToken() {
  try {
    const ui = app.globalData && app.globalData.userInfo;
    if (ui && ui.token) return ui.token;
  } catch (e) {}

  const keys = [
    'open_student_userInfo',
    'vocational_student_userInfo',
    'open_teacher_auth_cache',
    'vocational_teacher_auth_cache',
  ];
  for (let i = 0; i < keys.length; i++) {
    try {
      const cached = wx.getStorageSync(keys[i]);
      if (!cached) continue;
      // 教师端：嵌套结构 { userInfo: { token } }
      if (cached.userInfo && cached.userInfo.token) return cached.userInfo.token;
      // 学生端：扁平结构 { token }
      if (cached.token) return cached.token;
    } catch (e) {}
  }
  return '';
}

/**
 * 原生 wx.uploadFile（自动注入 token）。
 * 用原生 API 而非 request.js，是为了避免大文件走 JSON 序列化。
 */
function rawUpload({ url, filePath, name = 'photo', formData = {} }) {
  return new Promise((resolve, reject) => {
    const token = readToken();
    if (!token) {
      return reject({ msg: '未登录或登录已过期,请重新登录后再上传', noToken: true });
    }
    const fullUrl = url.startsWith('http') ? url : BASE_URL + url;
    wx.uploadFile({
      url: fullUrl,
      filePath,
      name,
      formData,
      header: { Authorization: 'Bearer ' + token },
      success: (res) => {
        let body;
        try {
          body = typeof res.data === 'string' ? JSON.parse(res.data) : res.data;
        } catch (e) {
          return reject({ msg: '返回数据解析失败: ' + res.data });
        }
        if (res.statusCode === 401) {
          return reject({ msg: '登录已过期,请重新登录', unauthorized: true });
        }
        if (res.statusCode < 200 || res.statusCode >= 300) {
          return reject({ msg: (body && body.msg) || ('HTTP ' + res.statusCode) });
        }
        if (body && body.success === false) {
          return reject({ msg: body.msg || '上传失败' });
        }
        resolve(body && body.data ? body.data : body);
      },
      fail: (err) => reject({ msg: (err && (err.errMsg || err.message)) || '网络异常,上传失败' })
    });
  });
}

/**
 * 原生 wx.request GET（自动注入 token）。
 */
function rawGet(path) {
  return new Promise((resolve, reject) => {
    const token = readToken();
    if (!token) {
      return reject({ msg: '未登录或登录已过期', noToken: true });
    }
    const fullUrl = path.startsWith('http') ? path : BASE_URL + path;
    wx.request({
      url: fullUrl,
      method: 'GET',
      header: { Authorization: 'Bearer ' + token },
      success: (res) => {
        if (res.statusCode === 401) {
          return reject({ msg: '登录已过期,请重新登录', unauthorized: true });
        }
        const body = res.data || {};
        if (body.success === false) {
          return reject({ msg: body.msg || '查询失败' });
        }
        resolve(body.data !== undefined ? body.data : body);
      },
      fail: (err) => reject({ msg: (err && (err.errMsg || err.message)) || '网络异常,查询失败' })
    });
  });
}

/**
 * 轮询任务状态，返回完成后的 result。
 */
async function pollTask(taskId, onProgress) {
  for (let i = 0; i < POLL_MAX_RETRIES; i++) {
    try {
      const res = await rawGet(`/photo/task_status/${taskId}`);

      if (res && typeof res.progress === 'number' && onProgress) {
        onProgress(res);
      }

      if (res.status === 'completed') {
        return res.result || {};
      }
      if (res.status === 'failed') {
        throw new Error(res.error || '处理失败');
      }

      await new Promise(r => setTimeout(r, POLL_INTERVAL_MS));
    } catch (err) {
      // 401 立即退出
      if (err && (err.unauthorized || err.noToken)) throw err;
      // 网络抖动继续重试；最后一次失败才抛
      if (i >= POLL_MAX_RETRIES - 1) throw err;
      await new Promise(r => setTimeout(r, POLL_INTERVAL_MS));
    }
  }
  throw new Error('处理超时，请重试');
}

/**
 * 选图并提交头像上传任务。
 *
 * @param {Object}   options
 * @param {string[]} options.sourceType  ['camera'] / ['album'] / ['camera','album']
 * @param {Function} options.onProgress  进度回调 (progressInfo) => void
 * @returns {Promise<{photo_url: string}>} 成功返回含 photo_url 的结果
 */
async function chooseAndUploadAvatar({ sourceType = ['camera', 'album'], onProgress } = {}) {
  const filePath = await new Promise((resolve, reject) => {
    wx.chooseMedia({
      count: 1,
      mediaType: ['image'],
      sourceType,
      camera: 'front',
      sizeType: ['compressed'],
      success: (res) => {
        const file = res.tempFiles && res.tempFiles[0];
        if (!file || !file.tempFilePath) {
          return reject({ msg: '选择照片失败，请重试' });
        }
        if (file.size && file.size > 5 * 1024 * 1024) {
          return reject({ msg: '图片大小不能超过 5MB' });
        }
        resolve(file.tempFilePath);
      },
      fail: (err) => {
        if (err && err.errMsg && err.errMsg.indexOf('cancel') >= 0) {
          return reject({ msg: '', cancelled: true });
        }
        reject({ msg: '选择照片失败，请重试' });
      }
    });
  });

  const formData = Object.assign(
    {
      size_name: 'two_inch',
      bg_color_name: 'blue',
    },
    DEFAULT_BEAUTY
  );

  const submitRes = await rawUpload({
    url: '/photo/upload_my_avatar',
    filePath,
    name: 'photo',
    formData,
  });

  const taskId = submitRes && submitRes.task_id;
  if (!taskId) {
    throw new Error('创建任务失败');
  }

  const result = await pollTask(taskId, onProgress);
  return result;
}

module.exports = {
  readToken,
  rawUpload,
  rawGet,
  pollTask,
  chooseAndUploadAvatar,
  resolveImageUrl,
};
