// top-message 组件测试页面
// 覆盖：4 种类型 / 自定义图标 / 4 种位置 / 多种 duration / 交互 / 边界

// 顶部消息提示组件实例 id 列表（按优先级查找）
// 本页面在 wxml 中定义了 3 个 top-message 实例：
//   - #top-message-top       顶部实例（默认）
//   - #top-message-bottom    底部实例
//   - #top-message-closable  可关闭实例（closable 模式）
// 把它们全部注册到 page-mixin 的查找列表里，showTopMessage 会按顺序找到第一个可用实例
const topMessageIds = ['#top-message-top', '#top-message-bottom', '#top-message-closable'];

const { createPage } = require('../../../utils/page-mixin');

createPage({
  data: {
    // 计数器，用于 burst/random 场景
    counter: 0,
    // 把 top-message 实例 id 列表注册到 data（createPage 模式下更直观）
    _topMessageIds: topMessageIds
  },

  onLoad() {
    // 兜底：也写到 this._topMessageIds，便于外部直接调用
    this._topMessageIds = topMessageIds;
  },

  // ============================================================
  // 1. 基础类型
  // ============================================================
  showSuccess() {
    this.showTopMessage('操作成功！', 'success', 3000);
  },

  showError() {
    this.showTopMessage('操作失败，请重试', 'error', 3000);
  },

  showWarning() {
    this.showTopMessage('请注意：当前操作不可撤销', 'warning', 3000);
  },

  showInfo() {
    this.showTopMessage('温馨提示：系统将于 23:00 升级', 'info', 3000);
  },

  // ============================================================
  // 2. showTopMessage 通用 API
  // ============================================================
  callShowTopMessage() {
    this.showTopMessage('通用 API 调用', 'info', 3000);
  },

  callShowTopMessageLong() {
    this.showTopMessage(
      '这是一段非常长的提示文案，用于测试多行换行、行高、文本溢出处理是否正常。文字应该自动换行而不撑破卡片。',
      'warning', 5000
    );
  },

  callShowTopMessageCustomIcon() {
    // 传 vant icon 名称：star-o / gift / fire-o / like-o / gold-coin-o 等
    this.showTopMessage('自定义图标：star-o', 'success', 3000, 'star-o');
  },

  callShowTopMessageInBottom() {
    const bottomMsg = this.selectComponent('#top-message-bottom');
    bottomMsg && bottomMsg.show('底部位置的消息提示', 'info', 3000);
  },

  // ============================================================
  // 3. duration 控制
  // ============================================================
  showDuration1s() {
    this.showTopMessage('1 秒后消失', 'success', 1000);
  },

  showDuration5s() {
    this.showTopMessage('5 秒后消失', 'info', 5000);
  },

  showDuration10s() {
    this.showTopMessage('10 秒后消失', 'warning', 10000);
  },

  showDurationForever() {
    this.showTopMessage('duration=0，永不自动消失（需手动关闭）', 'error', 0);
  },

  // ============================================================
  // 4. 交互测试
  // ============================================================
  showThenHide5s() {
    this.showTopMessage('5 秒后我会主动 hide()', 'info', 30000);
    setTimeout(() => {
      this.selectComponent('#top-message-top').hide();
    }, 5000);
  },

  showThenHideNow() {
    this.showTopMessage('这条几乎看不到，因为我立即 hide() 了', 'warning', 30000);
    setTimeout(() => {
      this.selectComponent('#top-message-top').hide();
    }, 100);
  },

  // ============================================================
  // 5. closable 关闭按钮
  // ============================================================
  showClosableSuccess() {
    this._showClosable('可关闭：操作成功', 'success');
  },

  showClosableError() {
    this._showClosable('可关闭：操作失败', 'error');
  },

  showClosableWarning() {
    this._showClosable('可关闭：警告信息', 'warning');
  },

  showClosableInfo() {
    this._showClosable('可关闭：普通信息', 'info');
  },

  _showClosable(msg, type) {
    const closable = this.selectComponent('#top-message-closable');
    closable && closable.show(msg, type, 0); // duration=0 不自动消失
  },

  // ============================================================
  // 6. 连续调用 / 覆盖
  // ============================================================
  showBurst() {
    const types = ['success', 'error', 'warning', 'info', 'success'];
    const msgs = ['第一条', '第二条', '第三条', '第四条', '第五条（最终显示）'];
    types.forEach((t, i) => {
      setTimeout(() => {
        this.showTopMessage(msgs[i], t, 10000);
      }, i * 100);
    });
  },

  showRapid() {
    // 同一个组件实例，连续切换 type
    const seq = [
      ['success', 'OK'],
      ['error', 'NO'],
      ['warning', 'WAIT'],
      ['info', 'INFO']
    ];
    seq.forEach(([t, m], i) => {
      setTimeout(() => {
        this.showTopMessage(m, t, 5000);
      }, i * 300);
    });
  },

  // ============================================================
  // 7. 边界场景
  // ============================================================
  showEmptyString() {
    // 边界：空字符串
    this.showTopMessage('', 'info', 3000);
  },

  showUndefined() {
    // 边界：undefined (page-mixin 会归一化为 '未知错误')
    this.showTopMessage(undefined, 'error', 3000);
  },

  showNull() {
    // 边界：null
    this.showTopMessage(null, 'error', 3000);
  },

  showNumber() {
    // 边界：纯数字
    this.showTopMessage(404, 'error', 3000);
  },

  showEmoji() {
    this.showTopMessage('🎉 恭喜发财 🚀 🚀 🚀', 'success', 3000);
  },

  showVeryLong() {
    const longText = '超长文本测试：' +
      '在微信公众号 H5 项目中，错误提示常常伴随着完整堆栈。' +
      '本组件必须能够优雅处理 500+ 字符的输入而不撑爆屏幕、不出现滚动条遮挡。' +
      '建议做法：限制最大行数 + 滚动查看 + 点击展开完整内容。';
    this.showTopMessage(longText, 'warning', 10000);
  },

  showErrorObject() {
    // 边界：error 对象
    const err = new Error('网络连接超时，请检查防火墙设置');
    this.showTopMessage(err, 'error', 5000);
  },

  showInvalidType() {
    // 边界：非法 type（应回退为 error）
    this.showTopMessage('非法 type 测试', 'unknown-type', 3000);
  },

  // ============================================================
  // 8. 模拟业务场景
  // ============================================================
  simulateSaveSuccess() {
    this.showTopMessage('保存成功', 'success', 3000);
    setTimeout(() => {
      this.showTopMessage('正在同步到云端...', 'info', 2000);
    }, 1500);
    setTimeout(() => {
      this.showTopMessage('同步完成', 'success', 2000);
    }, 4500);
  },

  simulateNetworkError() {
    this.showTopMessage('网络连接失败，正在重试...', 'error', 2000);
    setTimeout(() => {
      this.showTopMessage('重试失败', 'error', 2000);
    }, 2500);
    setTimeout(() => {
      this.showTopMessage('已切换到离线模式', 'warning', 3000);
    }, 5000);
  },

  simulateFormValidation() {
    const errors = [
      '姓名不能为空',
      '手机号格式不正确',
      '身份证号不合法'
    ];
    errors.forEach((msg, i) => {
      setTimeout(() => {
        this.showTopMessage(msg, 'error', 2000);
      }, i * 800);
    });
  },

  simulateConfirmAction() {
    this.showTopMessage('正在提交订单...', 'info', 2000);
    setTimeout(() => {
      this.showTopMessage('支付成功', 'success', 3000);
    }, 2500);
  },

  // ============================================================
  // 工具
  // ============================================================
  hideAll() {
    ['#top-message-top', '#top-message-bottom', '#top-message-closable'].forEach(sel => {
      const c = this.selectComponent(sel);
      c && c.hide();
    });
  },

  // ============================================================
  // 工具：把 page-mixin 的 showTopMessage 接到 this 上
  // ============================================================
  // 注意：page-mixin.js 已通过 createPage 自动注入 showTopMessage。
  // 这里保留一个同名方法用于演示「自定义 id 路由」的场景——直接调用指定实例
  showTopMessageOn(instanceId, message, type, duration, icon) {
    const cmp = this.selectComponent(instanceId);
    if (cmp && typeof cmp.show === 'function') {
      cmp.show(this._normalizeMessage(message), type, duration, icon);
    }
  },

  _normalize(msg) {
    // 兼容旧用法：委托给 page-mixin 的统一实现
    return this._normalizeMessage(msg);
  }
});
