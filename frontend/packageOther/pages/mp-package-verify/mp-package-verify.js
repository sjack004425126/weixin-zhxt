// mp-package-verify.js
// svg 项目 dist/mp/ 验证页
const { createPage } = require('../../../utils/page-mixin');

createPage({
  data: {
    codes: [
      { cls: 'grid',   code: String.fromCharCode(0xe001) },
      { cls: 'home',   code: String.fromCharCode(0xe002) },
      { cls: 'plus',   code: String.fromCharCode(0xe003) },
      { cls: 'upload', code: String.fromCharCode(0xe004) },
      { cls: 'user',   code: String.fromCharCode(0xe005) },
    ],
  },
  onLoad() {
    console.log('[mp 包验证] 已加载，依赖 app.wxss 全局 @import 的 my-iconfont.wxss');
    console.log('[unicode 测试]', this.data.codes.map(c => c.cls + '=' + c.code.charCodeAt(0).toString(16)).join(', '));
  }
});