/**
 * 小程序考试 API 配置（独立模块）
 *
 * 前缀：/mini-api/* （避开 /api/ 前缀，避免与现有 zhpt-new 系统的 nginx location 冲突）
 *
 * 所有端点对应 exam 后端的 /mini-api/*（独立实现，不复用 /api/v1/student/*）
 *
 * nginx 配置示例：
 *   location /mini-api/ {
 *       proxy_pass http://127.0.0.1:8086/mini-api/;
 *       ...
 *   }
 *
 * 流程：
 *   1. mini-login 调用 LOGIN 拿 token
 *   2. token 存到 wx.storage（mini_exam_token）
 *   3. 其他端点都用 tokenPost/get（自动带 Authorization）
 */

const API_EXAME = {
  // ========== 认证 ==========
  LOGIN: '/mini-api/auth/login',                     // POST 学号+密码登录
  ME:    '/mini-api/auth/me',                        // GET 拿当前用户信息

  // ========== 考试 ==========
  LIST:  '/mini-api/exams',                          // GET 考试列表
  START: '/mini-api/exams/start',                    // POST 开始考试
  SUBMIT: '/mini-api/exams/submit',                  // POST 提交试卷
  RECORDS: '/mini-api/exams/records',                // GET 成绩列表
  RECORD_DETAIL: (id) => `/mini-api/exams/record/${id}`, // GET 成绩详情
};

// 独立存储 key（避免污染现有 vocational_student_userInfo）
const TOKEN_KEY = 'mini_exam_token';
const USER_KEY = 'mini_exam_user';
const REMEMBER_KEY = 'mini_exam_remember';

module.exports = {
  API_EXAME,
  TOKEN_KEY,
  USER_KEY,
  REMEMBER_KEY,
};