const { createPage } = require('../../utils/page-mixin');

createPage({
  data: {
    webviewUrl: 'https://wproxy.qdndd.com.cn/zxbm/#/home?source=12&schoolid=3184'
  },

  onLoad(options) {
    console.log('Loading enrollment webview via Nginx proxy');
  }
})
