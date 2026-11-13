// vant-icon unicode 直渲映射（INCIDENTS/001：text 绕过 van-icon 组件 view+::before）
// 仅保留 top-message 实际用到的图标，避免 257 项全量映射臃肿
var ICON_CHARS = {
  'passed': '',
  'warning-o': '',
  'info-o': '',
  'close': '',
  'success': '',
  'fail': '',
  'clear': '',
  'cross': ''
};
Component({
  properties: {
    // 是否显示关闭按钮
    closable: {
      type: Boolean,
      value: false
    },
    // 提示位置 top | bottom
    position: {
      type: String,
      value: 'top'
    }
  },

  data: {
    message: '',
    type: 'error',
    visible: false,
    timer: null,
    isClicked: false,
    touchStartX: 0,
    touchStartY: 0,
    translateX: 0,
    isSwiping: false,
    isSwipingOut: false,
    iconName: 'warning-o',
    iconChar: '\ue743'
  },

  methods: {
    // 显示消息
    // message: 提示文本
    // type: success | error | warning | info
    // duration: 自动消失时长(ms)，0 表示不自动消失
    // icon: 自定义图标名称，可选
    show(message, type = 'error', duration = 3000, icon = '') {
      // 校验 type
      const safeType = this._normalizeType(type);

      // 清除之前的定时器
      if (this.data.timer) {
        clearTimeout(this.data.timer);
      }

      // 计算图标
      const iconName = icon || this._getDefaultIcon(safeType);

      // 先设置消息内容和初始位置（在屏幕右侧外）
      var iconChar = ICON_CHARS[iconName] || ICON_CHARS['warning-o'];

      this.setData({
        message: message,
        type: safeType,
        iconName: iconName,
        iconChar: iconChar,
        visible: true,
        isClicked: false,
        translateX: 500,
        isSwiping: false,
        isSwipingOut: false
      });

      // 延迟一帧后开始滑入动画
      setTimeout(() => {
        this.setData({
          translateX: 0
        });
      }, 50);

      // 设置自动隐藏（duration > 0 才自动消失）
      if (duration > 0) {
        const timer = setTimeout(() => {
          if (!this.data.isClicked) {
            this.hide();
          }
        }, duration);
        this.setData({ timer });
      }
    },

    // 主动隐藏（外部可调用）
    hide() {
      this._doHide();
    },

    // 点击关闭按钮
    onCloseTap() {
      this._doHide();
    },

    // 点击消息 - 停止自动隐藏，保持显示
    onMessageTap() {
      if (this.data.timer) {
        clearTimeout(this.data.timer);
      }
      this.setData({
        isClicked: true,
        timer: null
      });
    },

    // 点击背景 - 延迟几秒后自动消失
    onBackgroundTap() {
      if (this.data.isClicked) {
        if (this.data.timer) {
          clearTimeout(this.data.timer);
        }
        const timer = setTimeout(() => {
          this._doHide();
        }, 3000);
        this.setData({ timer });
      }
    },

    // 触摸开始
    onTouchStart(e) {
      const touches = (e && e.touches) || [];
      const first = touches[0] || {};
      this.setData({
        touchStartX: first.clientX || 0,
        touchStartY: first.clientY || 0,
        isSwiping: false
      });
    },

    // 触摸移动
    onTouchMove(e) {
      const touches = (e && e.touches) || [];
      const first = touches[0];
      if (!first) return;
      const touchEndX = first.clientX || 0;
      const touchEndY = first.clientY || 0;
      const deltaX = touchEndX - this.data.touchStartX;
      const deltaY = touchEndY - this.data.touchStartY;

      if (Math.abs(deltaX) > Math.abs(deltaY)) {
        if (deltaX < 0) {
          this.setData({
            translateX: deltaX,
            isSwiping: true
          });
        }
      }
    },

    // 触摸结束
    onTouchEnd() {
      const deltaX = this.data.translateX;

      if (deltaX < -100) {
        this.swipeOut();
      } else {
        this.setData({
          translateX: 0,
          isSwiping: false
        });
      }
    },

    // 向左滑出消失
    swipeOut() {
      this.setData({
        isSwipingOut: true,
        translateX: -500
      });

      setTimeout(() => {
        this._clear();
      }, 300);
    },

    // ---------- 内部方法 ----------

    // 校验 type
    _normalizeType(type) {
      const allowed = ['success', 'error', 'warning', 'info'];
      return allowed.includes(type) ? type : 'error';
    },

    // 根据类型返回默认图标
    _getDefaultIcon(type) {
      const iconMap = {
        success: 'passed',
        error: 'warning-o',
        warning: 'warning-o',
        info: 'info-o'
      };
      return iconMap[type] || 'warning-o';
    },

    // 隐藏动画 + 清理
    _doHide() {
      if (this.data.timer) {
        clearTimeout(this.data.timer);
      }
      this.setData({
        isSwipingOut: true,
        translateX: -500
      });
      setTimeout(() => {
        this._clear();
      }, 300);
    },

    // 完全清空状态
    _clear() {
      this.setData({
        message: '',
        visible: false,
        timer: null,
        isClicked: false,
        translateX: 0,
        isSwiping: false,
        isSwipingOut: false
      });
    }
  },

  lifetimes: {
    detached() {
      if (this.data.timer) {
        clearTimeout(this.data.timer);
      }
    }
  }
});
