/**
 * 全屏水印绘制工具
 * 使用 <canvas type="2d"> 元素，把水印（身份证后 6 位 + 姓名 + 时间戳）
 * 斜铺成图片，再以 image 标签覆盖页面，让学生截图后无法简单 PS。
 */

/**
 * 构造水印文本
 */
function buildWatermarkText(info) {
  if (!info) return '';
  const { idNumber = '', name = '', timestamp } = info;
  const tail = idNumber ? idNumber.slice(-6) : '';
  const d = timestamp ? new Date(timestamp) : new Date();
  const pad = (n) => String(n).padStart(2, '0');
  const timeStr = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
  const parts = [];
  if (name) parts.push(name);
  if (tail) parts.push(`****${tail}`);
  parts.push(timeStr);
  return parts.join(' · ');
}

/**
 * 离屏绘制水印图片。
 * @param {Object} opts
 * @param {string} opts.selector canvas 选择器，如 "#watermark-canvas"
 * @param {string} opts.text 水印文本
 * @param {number} opts.width 画布宽(px)
 * @param {number} opts.height 画布高(px)
 * @param {string} [opts.color='#000000']
 * @param {number} [opts.opacity=0.08]
 * @param {number} [opts.fontSize=22]
 * @param {number} [opts.rotate=-22] 旋转角度（度）
 * @param {number} [opts.density=4] 横向密度
 * @param {Object} opts.component 页面实例
 * @returns {Promise<string>}
 */
function drawWatermarkImage(opts) {
  const {
    selector,
    text,
    width,
    height,
    color = '#000000',
    opacity = 0.08,
    fontSize = 22,
    rotate = -22,
    density = 4,
    component,
  } = opts;

  return new Promise((resolve, reject) => {
    if (!selector || !text) return reject('selector and text are required');
    if (!component) return reject('component is required');
    if (!width || !height) return reject('width and height are required');

    const sys = wx.getSystemInfoSync();
    const dpr = sys.pixelRatio || 2;

    const query = wx.createSelectorQuery().in(component);
    query
      .select(selector)
      .fields({ node: true, size: true })
      .exec((res) => {
        if (!res || !res[0] || !res[0].node) {
          return reject(new Error('watermark canvas not found'));
        }
        const canvas = res[0].node;
        const ctx = canvas.getContext('2d');
        canvas.width = width * dpr;
        canvas.height = height * dpr;
        ctx.scale(dpr, dpr);

        ctx.clearRect(0, 0, width, height);
        // 不再绘制白底，保证生成图透明背景，便于叠加到卡片上

        ctx.globalAlpha = opacity;
        ctx.fillStyle = color;
        ctx.font = `${fontSize}px "PingFang SC","Helvetica Neue",sans-serif`;
        ctx.textBaseline = 'middle';

        const lineHeight = fontSize * 4;
        const colWidth = width / Math.max(1, density);

        for (let y = -lineHeight; y < height + lineHeight; y += lineHeight) {
          for (let x = 0; x < width + colWidth; x += colWidth) {
            const offset = (Math.floor(y / lineHeight) % 2) * (colWidth / 2);
            ctx.save();
            ctx.translate(x + offset, y);
            ctx.rotate((rotate * Math.PI) / 180);
            ctx.fillText(text, 0, 0);
            ctx.restore();
          }
        }

        ctx.globalAlpha = 1;

        wx.canvasToTempFilePath(
          {
            canvas,
            fileType: 'png',
            quality: 1,
            success: (r) => resolve(r.tempFilePath),
            fail: (e) => reject(e),
          },
          component
        );
      });
  });
}

module.exports = {
  drawWatermarkImage,
  buildWatermarkText,
};