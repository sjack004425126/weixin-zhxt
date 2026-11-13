/**
 * 金额防伪绘制工具
 * 把金额渲染到 type=2d 的 canvas 并导出临时图片路径，
 * 配合噪点/防伪细线/中文大写让 PS 修改难度大幅上升。
 */

/**
 * 把数字金额（最多两位小数）转换为中文大写。
 * 支持 0.00 ~ 999999999999.99；超出返回空字符串，由调用方兜底。
 */
function numberToChineseCurrency(num) {
  if (typeof num !== 'number' || !isFinite(num) || num < 0) return '';
  if (num === 0) return '零元整';

  const digits = ['零', '壹', '贰', '叁', '肆', '伍', '陆', '柒', '捌', '玖'];
  const intUnits = ['', '拾', '佰', '仟'];
  const bigUnits = ['', '万', '亿', '万亿'];
  const decUnits = ['角', '分'];

  const fixed = num.toFixed(2);
  const dotIdx = fixed.indexOf('.');
  const intPartStr = dotIdx >= 0 ? fixed.slice(0, dotIdx) : fixed;
  const decPartStr = dotIdx >= 0 ? fixed.slice(dotIdx + 1) : '00';

  let intResult = '';
  const intDigits = intPartStr.split('').map(Number);
  let zeroFlag = false;

  const groups = [];
  for (let i = intDigits.length; i > 0; i -= 4) {
    groups.unshift(intDigits.slice(Math.max(0, i - 4), i));
  }

  groups.forEach((group, gi) => {
    const bigUnit = bigUnits[groups.length - 1 - gi] || '';
    let groupStr = '';
    for (let i = 0; i < group.length; i++) {
      const d = group[i];
      const pos = group.length - 1 - i;
      if (d === 0) {
        zeroFlag = true;
      } else {
        if (zeroFlag) {
          groupStr += '零';
          zeroFlag = false;
        }
        groupStr += digits[d] + intUnits[pos];
      }
    }
    if (groupStr) {
      intResult += groupStr + bigUnit;
      zeroFlag = false;
    } else if (intResult && !intResult.endsWith('零')) {
      intResult += '零';
    }
  });
  intResult = intResult.replace(/零+$/, '');
  if (!intResult) intResult = '零';

  let decResult = '';
  const jiao = Number(decPartStr[0]);
  const fen = Number(decPartStr[1]);
  if (jiao > 0) decResult += digits[jiao] + '角';
  else if (intResult && !intResult.endsWith('零')) decResult += '零';
  if (fen > 0) decResult += digits[fen] + '分';

  return intResult + '元' + (decResult || '整');
}

/**
 * 使用 <canvas type="2d"> 元素离屏绘制金额并导出图片。
 * canvas 必须存在于 DOM（可隐藏），并且传入 selector。
 *
 * @param {Object} opts
 * @param {string} opts.selector 必填，如 "#amount-canvas-xf"
 * @param {string} opts.amount 形如 "5000.00"
 * @param {string} [opts.color='#1890FF']
 * @param {number} [opts.fontSize=36] 主金额字号(px)
 * @param {number} [opts.width] 画布宽(px)，默认根据字体大小估算
 * @param {number} [opts.height] 画布高(px)，默认 fontSize*2.2
 * @param {boolean} [opts.showChinese=true] 是否同时绘制中文大写
 * @param {boolean} [opts.noise=true] 是否绘制防伪细线+噪点
 * @param {string} [opts.bg='#FFFFFF']
 * @param {Object} [opts.component] 页面实例（必填，canvasToTempFilePath 第二参）
 * @returns {Promise<string>} 临时图片路径
 */
function drawAmountToImage(opts) {
  const {
    selector,
    amount,
    color = '#1890FF',
    fontSize = 36,
    width,
    height,
    showChinese = true,
    noise = true,
    bg = '#FFFFFF',
    component,
  } = opts;

  return new Promise((resolve, reject) => {
    if (!selector) return reject('selector is required');
    if (!component) return reject('component (this) is required');
    const text = '¥' + (amount || '0.00');
    const sys = wx.getSystemInfoSync();
    const dpr = sys.pixelRatio || 2;

    const charW = fontSize * 0.62;
    const padding = fontSize * 0.6;
    const w = width || Math.ceil((text.length + (showChinese ? 6 : 0)) * charW + padding * 2);
    const h = height || Math.ceil((showChinese ? 2 : 1) * fontSize * 1.6 + padding);

    const query = wx.createSelectorQuery().in(component);
    query
      .select(selector)
      .fields({ node: true, size: true })
      .exec((res) => {
        if (!res || !res[0] || !res[0].node) {
          // 兼容旧 canvas：直接拒绝，由调用方降级
          return reject(new Error('canvas node not found for ' + selector));
        }
        const canvas = res[0].node;
        const ctx = canvas.getContext('2d');
        const dpr2 = sys.pixelRatio || 2;
        canvas.width = w * dpr2;
        canvas.height = h * dpr2;
        ctx.scale(dpr2, dpr2);

        // 背景
        ctx.fillStyle = bg;
        ctx.fillRect(0, 0, w, h);

        // 防伪细线
        if (noise) {
          ctx.strokeStyle = 'rgba(0,0,0,0.05)';
          ctx.lineWidth = 1;
          for (let i = 0; i < 6; i++) {
            const y = (h / 6) * i + 6;
            ctx.beginPath();
            ctx.moveTo(8, y);
            ctx.lineTo(w - 8, y);
            ctx.stroke();
          }
          // 噪点
          ctx.fillStyle = 'rgba(0,0,0,0.07)';
          for (let i = 0; i < 80; i++) {
            const x = Math.random() * w;
            const y = Math.random() * h;
            ctx.fillRect(x, y, 1, 1);
          }
        }

        // 主金额
        ctx.fillStyle = color;
        ctx.font = `bold ${fontSize}px "PingFang SC","Helvetica Neue",sans-serif`;
        ctx.textBaseline = 'middle';
        ctx.fillText(text, padding, h / (showChinese ? 2.8 : 2));

        // 中文大写
        if (showChinese) {
          const chinese = numberToChineseCurrency(Number(amount));
          if (chinese) {
            ctx.fillStyle = '#475569';
            ctx.font = `${Math.floor(fontSize * 0.46)}px "PingFang SC","Helvetica Neue",sans-serif`;
            ctx.fillText(`（${chinese}）`, padding, h * 0.78);
          }
        }

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
  numberToChineseCurrency,
  drawAmountToImage,
};