// 修改 vant-icon/index.wxss 的 @font-face src，改为 my-iconfont 的格式
const fs = require('fs');
const path = 'E:/MyPrj/zhxt/zhpt-new/frontend/components/vant-icon/index.wxss';
let c = fs.readFileSync(path, 'utf8');

// 替换 MIME 类型 + 添加 format
const old = 'src: url("data:application/font-woff2;base64,';
const idx = c.indexOf(old);
if (idx === -1) {
  console.error('NOT FOUND old src: application MIME');
  process.exit(1);
}

const newSrc = `src: url("data:font/woff2;charset=utf-8;base64,`;
c = c.replace(old, newSrc);

// 在 base64 字符串的结束引号前加 format('woff2')
// 原结束: ");  改为: ") format("woff2");
const oldEnd = '");';
// 只替换第一个出现的位置（即 font-face 的 src 结束引号）
const endIdx = c.indexOf(oldEnd, idx + newSrc.length);
if (endIdx === -1) {
  console.error('NOT FOUND ); end');
  process.exit(1);
}
const newEnd = `") format("woff2");`;
c = c.substring(0, endIdx) + newEnd + c.substring(endIdx + oldEnd.length);

fs.writeFileSync(path, c, 'utf8');
console.log('OK, new length:', c.length);

// 验证
const newC = fs.readFileSync(path, 'utf8');
const fontFaceMatch = newC.match(/@font-face\s*\{[\s\S]*?\}/);
if (fontFaceMatch) console.log('--- @font-face block:');
else console.log('NO @font-face found!');
console.log(fontFaceMatch ? fontFaceMatch[0].substring(0, 500) : '');
