// static-icon-test.js
// iconfont 字体图标测试页面
// 演示 4 种使用方式：class / unicode / symbol / 动态样式

const { createPage } = require('../../../utils/page-mixin');

createPage({
  data: {
    // 5 个图标的信息（从 dist/my-iconfont.json / my-iconfont.css 提取）
    icons: [
      { id: 1, class: 'icon-1', unicode: '\\ea01', unicodeChar: '\uea01', label: '图标 1', guess: '书本' },
      { id: 2, class: 'icon-2', unicode: '\\ea02', unicodeChar: '\uea02', label: '图标 2', guess: '医疗十字' },
      { id: 3, class: 'icon-3', unicode: '\\ea03', unicodeChar: '\uea03', label: '图标 3', guess: '九宫格' },
      { id: 4, class: 'icon-4', unicode: '\\ea04', unicodeChar: '\uea04', label: '图标 4', guess: '个人' },
      { id: 5, class: 'icon-5', unicode: '\\ea05', unicodeChar: '\uea05', label: '图标 5', guess: '房子' }
    ],
    // 动态样式测试
    dynamicSize: 96,
    dynamicColor: '#1890ff',
    // 字体加载状态
    fontLoaded: true,
    loadError: ''
  },

  onLoad() {
    // 小程序中无法直接检测 @font-face 是否加载成功
    // 实际验证需要在真机/开发者工具中肉眼查看
    console.log('[静态图标测试] 页面加载，建议在真机查看效果');
  },

  onSizeChange(e) {
    this.setData({ dynamicSize: parseInt(e.detail.value, 10) || 32 });
  },

  onColorChange(e) {
    this.setData({ dynamicColor: e.currentTarget.dataset.color });
  },

  copyClass(e) {
    const cls = e.currentTarget.dataset.cls;
    wx.setClipboardData({
      data: `<text class="${cls}"></text>`,
      success: () => {
        wx.showToast({ title: `已复制 ${cls}`, icon: 'success' });
      }
    });
  },

  copyUnicode(e) {
    const code = e.currentTarget.dataset.code;
    wx.setClipboardData({
      data: code,
      success: () => {
        wx.showToast({ title: `已复制 ${code}`, icon: 'success' });
      }
    });
  }
});
