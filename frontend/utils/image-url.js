// 图片 URL 工具：把后端返回的相对路径拼成带 BASE_URL 的完整 URL，
// 以便在小程序 <image src> / wx.previewImage 里使用。
//
// 设计要点：
//   - 兼容已是完整 URL 的输入（http/https/data/wxfile/cloud 协议）直接返回
//   - 兼容历史遗留的 https://m.qdndd.com.cn/... 硬编码：把域名替换为当前 BASE_URL，
//     这样内网环境也能命中内网入口，不会跨网反代
//   - 支持数组 / 富文本字符串批量替换
const { BASE_URL } = require('./request');

const ABSOLUTE_RE = /^(https?:|data:|wxfile:|cloud:|blob:)/i;

// 历史硬编码的公网域名列表；加到这里即可一并收敛
const LEGACY_DOMAINS = [
  'https://m.qdndd.com.cn',
  'http://m.qdndd.com.cn',
  'http://localhost:3050',
  'http://127.0.0.1:3050',
  'http://172.16.100.102:9000',
  'http://172.16.14.216:9000',
];

function stripLegacyDomain(url) {
  if (!url) return url;
  for (const d of LEGACY_DOMAINS) {
    if (url.startsWith(d)) return url.slice(d.length) || '/';
  }
  return url;
}

/** 把单个 URL 解析为带 BASE_URL 的完整 URL。 */
function resolveImageUrl(url) {
  if (!url) return '';
  // 先把历史硬编码域名剥掉，转回相对路径再重新拼 BASE_URL
  const stripped = stripLegacyDomain(url);
  if (stripped !== url) {
    return BASE_URL + (stripped.startsWith('/') ? stripped : '/' + stripped);
  }
  if (ABSOLUTE_RE.test(url)) {
    // 公网 http 升级 https；本地开发网段（localhost/127/10/172.16/192.168）保持 http，
    // 否则拼成 https://127.0.0.1 本地根本没有证书，反而加载失败
    if (/^http:\/\//i.test(url) && !/^(localhost|127\.|10\.|172\.(1[6-9]|2\d|3[01])\.|192\.168\.)/i.test(url.slice(7))) {
      return 'https://' + url.slice(7);
    }
    return url;
  }
  return BASE_URL + (url.startsWith('/') ? url : '/' + url);
}

/** 批量解析数组。 */
function resolveImageUrls(list) {
  if (!Array.isArray(list)) return list;
  return list.map(resolveImageUrl);
}

/** 处理富文本 HTML 里的 <img src="...">，把相对路径/遗留域名转成完整 URL。 */
function resolveImageUrlsInHtml(html) {
  if (!html) return '';
  return html.replace(/src=(["'])([^"']+)\1/gi, (_, q, src) => {
    return 'src=' + q + resolveImageUrl(src) + q;
  });
}

module.exports = {
  resolveImageUrl,
  resolveImageUrls,
  resolveImageUrlsInHtml,
};
