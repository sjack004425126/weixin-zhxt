// 公共静态图集中表
//
// 所有图实际存放位置：MinIO 桶 guizhou-zhpt-prod-public，对象前缀 static/images/
// 访问路径：BASE_URL + /static/images/<filename>
//   - 开发: http://172.16.14.216:3050/static/images/...
//   - 测试: http://172.16.100.102:3050/static/images/...
//   - 生产: https://m.qdndd.com.cn/static/images/...
// 由各环境的 nginx /static/ location 反代到 MinIO 公共桶完成。
//
// 维护规范：
//   1. 任何新增的"和后端业务数据无关、UI 用的静态图"先上传到 MinIO 公共桶
//      guizhou-zhpt-prod-public/static/images/ 下，然后在此表新增一行。
//   2. WXML/JS 不允许再硬编码图片绝对 URL，统一从此处 require。
const { BASE_URL } = require('./request');

const STATIC_BASE = BASE_URL + '/static/images';

const STATIC_IMAGES = {
  // ===== 首页 / 介绍页 =====
  homeBg: STATIC_BASE + '/home_bg.jpg',
  logo: STATIC_BASE + '/logo.png',
  videoCover: STATIC_BASE + '/video-cover.jpg',
  gkbm001: STATIC_BASE + '/gkbm001.png',
  // 首页四个功能入口图标
  zbm: STATIC_BASE + '/zbm.png',
  zsf: STATIC_BASE + '/zsf.png',
  kbm: STATIC_BASE + '/kbm.png',
  ksf: STATIC_BASE + '/ksf.png',

  // ===== 通用 =====
  // 默认头像用生产 HTTPS 直链：本地开发 BASE_URL 是 http，<image> 会报“不再支持 HTTP”告警；
  // 默认头像是公开静态图，dev 下也直接走生产 https，避免告警。私有头像仍走当前 BASE_URL，
  // 生产 BASE_URL 本就是 https，发布后告警自动消失。
  defaultAvatar: 'https://m.qdndd.com.cn/static/zhxt/images/default-avatar.png',

  // ===== 答题页底部图标 =====
  examPre: STATIC_BASE + '/pre.png',
  examNext: STATIC_BASE + '/next.png',
  examDatika: STATIC_BASE + '/datika.png',
  examJiaojuan: STATIC_BASE + '/jiaojuan.png',
  examSet: STATIC_BASE + '/set.png',
  examExit: STATIC_BASE + '/exit.png',
};

module.exports = { STATIC_BASE, STATIC_IMAGES };
