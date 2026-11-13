// 统一的页面混入系统 - 集成所有功能
const { checkAuth, isUserLoggedIn, requireLogin } = require('./auth-guard');
const http = require('./request');

// ============================================================================
// 通用组件：所有 createPage 创建的页面，默认期望 wxml 顶部通过
// <include src="/utils/common-components.wxml" /> 引入这些组件。
// 路径常量集中在这里，便于统一修改。
// ============================================================================
const COMMON_COMPONENTS_WXML_PATH = '/utils/common-components.wxml';

// ============================================================================
// 内部工具：通用生命周期合并器
// 把混入钩子和页面钩子合并成"先混入、后页面"的复合函数。
// ============================================================================
function composeLifecycle(mixinFn, pageFn) {
  if (!mixinFn) return pageFn;
  if (!pageFn) return mixinFn;
  return function (...args) {
    mixinFn.apply(this, args);
    pageFn.apply(this, args);
  };
}

// 需要合并生命周期的小程序钩子
const LIFECYCLE_HOOKS = ['onLoad', 'onShow', 'onReady', 'onHide', 'onUnload', 'onPullDownRefresh', 'onReachBottom', 'onShareAppMessage', 'onPageScroll', 'onResize'];

// ============================================================================
// pageMixin：所有页面通用的数据、生命周期、方法
// ============================================================================
const pageMixin = {
  data: {
    // 通用页面数据
    _headerHeight: 0,
    // 内部标记：当前页面是否通过 <include> 引入了通用组件片段
    _commonComponentsIncluded: false
  },

  /**
   * 默认的 top-message 实例 id 列表。
   * 页面可在自己的 data/onLoad 中覆盖：this._topMessageIds = ['#top-message-bottom']
   * showTopMessage 会按顺序查找可用实例。
   */
  _topMessageIds: ['#top-message'],

  onLoad() {
    // 页面加载时的通用逻辑（占位，方便未来扩展）
  },

  onReady() {
    // 自动测量固定头部高度，设置占位
    this._measureHeaderHeight();
    // 检测通用组件是否已挂载（开发体验增强）
    this._checkCommonComponentsMounted();
  },

  // ---------- 私有：工具方法 ----------

  _measureHeaderHeight() {
    const query = wx.createSelectorQuery();
    query.select('.page-header').boundingClientRect(rect => {
      if (rect && rect.height > 0) {
        this.setData({ _headerHeight: rect.height });
      }
    }).exec();
  },

  /**
   * 检查 wxml 顶部是否引入了通用组件片段（top-message）。
   * 支持两种方式（任一即可）：
   *   ① <include src="/utils/common-components.wxml" />
   *   ② 手动写 <top-message id="top-message"></top-message>
   *
   * 仅在 autoRegisterComponents === true 时调用，且只在开发环境报警告。
   */
  _checkCommonComponentsMounted() {
    if (!this.data.__autoRegisterComponents) return;
    // 跳过开发环境判断（__DEV__ 在小程序原生环境不存在）
    // 让 onReady 后端完成首次布局再检测
    setTimeout(() => {
      const query = wx.createSelectorQuery();
      // 优先检测 include 标记；缺失再检测组件实例本身
      query.select('#__common-components-marker').boundingClientRect();
      query.select('#top-message').boundingClientRect();
      query.exec(res => {
        const list = res || [];
        const includeMark = list[0];
        const topMsg = list[1];
        const hasInclude = !!(includeMark && includeMark.height >= 0);
        const hasTopMessage = !!(topMsg && topMsg.height >= 0);

        this.setData({
          _commonComponentsIncluded: hasInclude || hasTopMessage
        });

        if (!hasInclude && !hasTopMessage) {
          console.warn(
            `[page-mixin] 页面 [${this.route || 'unknown'}] 未挂载 top-message 组件。\n` +
            `请在 wxml 顶部二选一添加：\n` +
            `  ① <include src="${COMMON_COMPONENTS_WXML_PATH}" />\n` +
            `  ② <top-message id="top-message"></top-message>\n` +
            `相关方法（showSuccess/showError 等）仍会通过 wx.showToast 降级生效。`
          );
        }
      });
    }, 0);
  },

  // ---------- 公开：顶部消息提示 ----------

  /**
   * 在页面的 _topMessageIds 列表中按顺序查找第一个可用实例。
   * 找不到任何可用实例时返回 null（调用方负责降级）。
   *
   * 页面可通过覆盖 _topMessageIds 来使用自定义 id 的实例：
   *   data: { _topMessageIds: ['#top-message-bottom'] }
   * 或在 onLoad 中动态指定：
   *   this._topMessageIds = ['#top-message-top', '#top-message-bottom']
   *
   * @returns {object|null}
   */
  _findTopMessageInstance() {
    const ids = Array.isArray(this._topMessageIds) && this._topMessageIds.length
      ? this._topMessageIds
      : ['#top-message'];

    for (const id of ids) {
      if (!id) continue;
      const inst = this.selectComponent(id);
      if (inst && typeof inst.show === 'function') {
        return inst;
      }
    }
    return null;
  },

  /**
   * 通用顶部消息提示
   * @param {string|object} message 提示内容（支持字符串、对象、错误对象）
   * @param {string} type success | error | warning | info
   * @param {number} duration 自动消失时长（ms）；0 表示不自动消失
   * @param {string} [icon] 自定义图标，可选
   */
  showTopMessage(message, type = 'error', duration = 5000, icon = '') {
    const safeMessage = this._normalizeMessage(message);

    const topMessage = this._findTopMessageInstance();

    if (topMessage) {
      topMessage.show(safeMessage, type, duration, icon);
    } else {
      // 降级：使用原生 wx.showToast
      wx.showToast({
        title: safeMessage,
        icon: type === 'success' ? 'success' : 'none',
        duration,
        mask: false
      });
    }
  },

  showSuccess(message, duration = 3000) {
    this.showTopMessage(message, 'success', duration);
  },

  showError(message, duration = 3000) {
    this.showTopMessage(message, 'error', duration);
  },

  showWarning(message, duration = 3000) {
    this.showTopMessage(message, 'warning', duration);
  },

  showInfo(message, duration = 3000) {
    this.showTopMessage(message, 'info', duration);
  },

  // ---------- 公开：登录守卫（透传 auth-guard） ----------

  checkLogin(callback) {
    return checkAuth(callback);
  },

  isLoggedIn() {
    return isUserLoggedIn();
  },

  requireLogin(callback) {
    return this.checkLogin(callback);
  },

  // ---------- 公开：HTTP 客户端（不必再 import request） ----------

  /**
   * 页面级 HTTP 客户端（下划线开头避免微信把它当 data 序列化）
   * - 用法：this._http.get('/api/x') / this._http.tokenPost('/api/x', data)
   * - 失败统一 reject 带 message/code/data/response 的 Error
   * - 自动 401 refresh + 请求去重 + loading 计数
   *
   * 历史原因：旧版本用 this.http.*，微信会把 http 当 data 报 'Free data with key "http"'，
   *          故改名 _http。page-mixin 仍暴露同名 http getter 以保持兼容。
   */
  // 注：微信 Page(config) 会把 config 里除保留名之外的所有字段当 data 序列化。
  // 这里用一个 getter 代理，避免把整个 http(request) 模块作为 data key 传给微信
  // （否则会触发 'Free data with key "http" seems not a simple value'）。
  get http() { return require('./request'); },

  // ---------- 内部：消息归一化 ----------

  _normalizeMessage(message) {
    if (typeof message === 'string') return message;
    if (message && typeof message === 'object') {
      if (message.message) return String(message.message);
      try {
        return JSON.stringify(message);
      } catch (e) {
        return '未知错误';
      }
    }
    return String(message || '未知错误');
  }
};

// ============================================================================
// createPage：统一的页面工厂
// @param {Object} pageConfig 页面配置（与原生 Page 参数一致）
// @param {Object} [options]
// @param {boolean} [options.requireAuth=false] 是否需要登录才能进入
// @param {string} [options.userType] 当 requireAuth=true 时指定端类型
// @param {boolean} [options.autoRegisterComponents=true] 是否启用通用组件自动注册检测
// ============================================================================
function createPage(pageConfig = {}, options = {}) {
  const finalOptions = {
    requireAuth: false,
    autoRegisterComponents: true,
    ...options
  };

  // 1. 如果需要登录守卫，先用 requireLogin 装饰 pageConfig
  if (finalOptions.requireAuth === true) {
    if (finalOptions.userType) {
      pageConfig.userType = finalOptions.userType;
    }
    pageConfig = requireLogin(pageConfig);
  }

  // 2. 标记是否启用自动组件检测（供运行时探针使用）
  pageConfig.data = pageConfig.data || {};
  pageConfig.data.__autoRegisterComponents = finalOptions.autoRegisterComponents;

  // 3. 合并 data（页面 data 优先）
  const mergedData = {
    ...pageMixin.data,
    ...pageConfig.data
  };

  // 4. 合并生命周期钩子（混入先执行，页面后执行）
  for (const hook of LIFECYCLE_HOOKS) {
    const mixinFn = pageMixin[hook];
    const pageFn = pageConfig[hook];
    if (mixinFn || pageFn) {
      pageConfig[hook] = composeLifecycle(mixinFn, pageFn);
    }
  }

  // 5. 浅合并方法（页面定义的方法会覆盖 mixin 同名方法）
  const finalConfig = {
    ...pageMixin,
    ...pageConfig,
    data: mergedData
  };

  // 6. 修复微信 Page() 把 'http' 当 data 序列化的告警
  //    小程序 Page(config) 会枚举 config 的可枚举属性当 data。
  //    pageMixin 上的 http（request 模块）会被深度克隆，产生：
  //      "Free data with key \"http\" of page ... seems not a simple value."
  //    解决方案：先 delete 掉避免被枚举；再通过 defineProperty 加不可枚举的
  //    getter 暴露 this.http，保持现有 this.http.get(...) 写法不变。
  if (finalConfig.http && typeof finalConfig.http === 'object') {
    const httpRef = finalConfig.http;
    delete finalConfig.http;
    Object.defineProperty(finalConfig, 'http', {
      configurable: true,
      enumerable: false,
      get() { return httpRef; }
    });
  }

  return Page(finalConfig);
}

// ============================================================================
// 导出
// ============================================================================
module.exports = {
  // 混入的所有方法（可以直接使用）
  ...pageMixin,

  // 统一的页面创建函数
  createPage,

  // 通用组件片段的 wxml 路径，方便页面 wxml 顶部引用
  COMMON_COMPONENTS_WXML_PATH,

  // 登录相关方法（auth-guard 透传）
  checkAuth,
  isUserLoggedIn,
  requireLogin
};
