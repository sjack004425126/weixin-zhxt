// 临时调试：把 console.log 集中到 wx 下，方便 devtools / vConsole 抓
// 进入页面后会自动调用，把渲染用到的图片 URL 全部打印
module.exports = function logImageUrls(urls) {
  console.log('======= [enroll] 当前使用图片 URL 列表 =======');
  if (!Array.isArray(urls)) {
    console.log('(non-array)');
    return;
  }
  urls.forEach((u, i) => {
    if (!u) {
      console.log(`#${i}: (empty)`);
      return;
    }
    try {
      const parsed = new URL(u);
      console.log(`#${i}: host=${parsed.host}  path=${parsed.pathname.slice(0, 80)}…`);
    } catch (e) {
      console.log(`#${i}: ${u}`);
    }
  });
  console.log('=======  END 图片 URL 列表 =======');
};
