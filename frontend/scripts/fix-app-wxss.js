// 修复 app.wxss：在全局范围内声明 .van-icon 用同样的 vant-icon 字体
// 思路：保留 custom-icon（其他代码可能用），但同时在 app.wxss 末尾追加 vant-icon 的 @font-face 和 .van-icon 通用样式
const fs = require('fs');
const path = 'E:/MyPrj/zhxt/zhpt-new/frontend/app.wxss';
let c = fs.readFileSync(path, 'utf8');

// 找到任意一个 vant-icon 的 base64 源（从 vant-icon 组件里读）
const vantIconPath = 'E:/MyPrj/zhxt/zhpt-new/frontend/components/vant-icon/index.wxss';
const vc = fs.readFileSync(vantIconPath, 'utf8');
const m = vc.match(/src:\s*url\("data:font\/woff2;charset=utf-8;base64,([A-Za-z0-9+\/=]+)"\)\s*format\("woff2"\);/);
if (!m) {
  console.error('NOT FOUND vant-icon base64');
  process.exit(1);
}
const base64 = m[1];
console.log('vant-icon base64 length:', base64.length);

// 追加到 app.wxss 末尾：vant-icon 全局 @font-face + .van-icon 基础样式
const append = `

/* ============ 全局 vant-icon 字体（让所有页面都能用 van-icon，无需每个 .wxss 都 import） ============ */
@font-face {
  font-display: auto;
  font-family: 'vant-icon';
  font-style: normal;
  font-weight: 400;
  src: url("data:font/woff2;charset=utf-8;base64,${base64}") format("woff2");
}

.van-icon {
  position: relative;
  display: inline-block;
  font: normal normal normal 14px/1 "vant-icon", sans-serif;
  font-size: inherit;
  text-rendering: auto;
  -webkit-font-smoothing: antialiased;
}

.van-icon-info {
  position: absolute;
  right: 0;
  top: 0;
  transform: translate(50%, -50%);
  transform-origin: 100%;
}
`;

fs.appendFileSync(path, append, 'utf8');
console.log('appended, new size:', fs.statSync(path).size);