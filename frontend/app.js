// app.js - 应用入口
// 登录/会话相关逻辑已统一迁移到 utils/auth-guard.js
// 这里只保留 App 生命周期钩子和与登录无关的全局状态

const authGuard = require('./utils/auth-guard');
const { TOKEN_KEY: MINI_TOKEN_KEY, USER_KEY: MINI_USER_KEY } = require('./utils/api-exame');

App({
  onLaunch() {
    // 1. 尝试从任一有效端的 storage 恢复会话
    //    解决"冷启动用户被强制重登"问题
    authGuard.initAppSession();

    // 1.5 mini_exam 端恢复（独立存储，独立端，不归 auth-guard 管）
    try {
      const miniToken = wx.getStorageSync(MINI_TOKEN_KEY);
      const miniUser = wx.getStorageSync(MINI_USER_KEY);
      if (miniToken && miniUser) {
        this.globalData.userInfo = { ...miniUser, token: miniToken };
      }
    } catch (e) {
      console.warn('[app.onLaunch] restore mini_exam session failed', e);
    }

    // 2. 解决微信开发者工具 1.06+ 在分包预下载后偶发的 navigateTo:fail timeout
    if (wx.onLazyLoadError) {
      wx.onLazyLoadError((res) => {
        console.warn('[App.onLazyLoadError]', res);
      }, 30000);
    }

    // 3. 检查小程序更新
    if (wx.canIUse && wx.canIUse('getUpdateManager')) {
      const updateManager = wx.getUpdateManager();
      updateManager.onCheckForUpdate(() => { /* hasUpdate 提示埋点位置 */ });
      updateManager.onUpdateReady(() => {
        wx.showModal({
          title: '更新提示',
          content: '新版本已经准备好，是否重启应用？',
          showCancel: false,
          success: (res) => { if (res.confirm) updateManager.applyUpdate(); }
        });
      });
      updateManager.onUpdateFailed(() => {
        wx.showModal({
          title: '更新失败',
          content: '新版本下载失败，请检查网络设置',
          showCancel: false
        });
      });
    }
  },

  globalData: {
    version: '3.9.43',
    userInfo: null,
    selectedBkCourses: []
  },

  // ============ 登录相关方法（透传到 auth-guard） ============
  // 业务代码可继续通过 app.xxx 调用，行为与 authGuard.xxx 完全一致

  /** 检查登录态（同步返回 bool）。已废弃业务里误用的"懒初始化"逻辑。 */
  checkLogin() {
    return authGuard.isUserLoggedIn();
  },

  /** 获取当前用户信息（自动从 globalData 或 storage 恢复） */
  getUserInfo() {
    return authGuard.getUserInfo();
  },

  /** wx.login code 的 Promise 封装 */
  getOpenid_code() {
    return authGuard.getOpenidCode();
  },

  /**
   * 退出登录。
   * 不传 userType：清空所有端的会话（兼容旧 app.logout 行为）
   * 传 userType：只清指定端
   */
  logout(userType) {
    return authGuard.logoutByType(userType);
  },

  // 4 个端专属 logout（保留旧 API，内部委托给 auth-guard）
  logoutOpenStudent() { return authGuard.logoutByType('open_student'); },
  logoutVocationalStudent() { return authGuard.logoutByType('vocational_student'); },
  logoutVocationalTeacher() { return authGuard.logoutByType('vocational_teacher'); },
  logoutOpenTeacher() { return authGuard.logoutByType('open_teacher'); }
});