const { createPage } = require('../../../utils/page-mixin');

createPage({
  data: {},

  onLoad() {
    this._hasDraw = false;
    this._isDrawing = false;
    this._ctx = null;
    this._canvas = null;
    this._width = 0;
    this._height = 0;
  },

  onReady() {
    this.initCanvas();
  },

  initCanvas() {
    const query = wx.createSelectorQuery();
    query.select('#sigCanvas')
      .fields({ node: true, size: true })
      .exec((res) => {
        if (!res[0] || !res[0].node) {
          setTimeout(() => this.initCanvas(), 200);
          return;
        }
        const canvas = res[0].node;
        const ctx = canvas.getContext('2d');
        const dpr = wx.getWindowInfo().pixelRatio;
        const w = res[0].width;
        const h = res[0].height;

        canvas.width = w * dpr;
        canvas.height = h * dpr;
        ctx.scale(dpr, dpr);

        this._ctx = ctx;
        this._canvas = canvas;
        this._width = w;
        this._height = h;

        this.drawBackground();
      });
  },

  // 画田字格 + placeholder 文字
  drawBackground() {
    const ctx = this._ctx;
    const w = this._width;
    const h = this._height;
    if (!ctx) return;

    // 白色背景
    ctx.fillStyle = '#fff';
    ctx.fillRect(0, 0, w, h);

    // 田字格：虚线
    ctx.strokeStyle = '#e0e0e0';
    ctx.lineWidth = 1;
    ctx.setLineDash([8, 6]);

    // 横中线
    ctx.beginPath();
    ctx.moveTo(0, h / 2);
    ctx.lineTo(w, h / 2);
    ctx.stroke();

    // 竖中线
    ctx.beginPath();
    ctx.moveTo(w / 2, 0);
    ctx.lineTo(w / 2, h);
    ctx.stroke();

    // 对角线（田字格风格）
    ctx.strokeStyle = '#f0f0f0';
    ctx.beginPath();
    ctx.moveTo(0, 0);
    ctx.lineTo(w, h);
    ctx.stroke();

    ctx.beginPath();
    ctx.moveTo(w, 0);
    ctx.lineTo(0, h);
    ctx.stroke();

    ctx.setLineDash([]);

    // placeholder 文字
    if (!this._hasDraw) {
      ctx.fillStyle = '#d9d9d9';
      ctx.font = '18px sans-serif';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText('请在此处签名', w / 2, h / 2);
    }

    // 恢复画笔设置
    this.resetPen();
  },

  resetPen() {
    const ctx = this._ctx;
    ctx.strokeStyle = '#000000';
    ctx.lineWidth = 3;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.setLineDash([]);
  },

  onTouchStart(e) {
    if (!this._ctx) return;

    // 第一笔时清掉 placeholder 文字，重绘背景
    if (!this._hasDraw) {
      this._hasDraw = true;
      this.redrawGrid();
    }

    const touches = (e && e.touches) || [];
    const touch = touches[0];
    if (!touch) return;
    this._lastX = touch.x;
    this._lastY = touch.y;
    this._isDrawing = true;
  },

  onTouchMove(e) {
    if (!this._isDrawing || !this._ctx) return;
    const touches = (e && e.touches) || [];
    const touch = touches[0];
    if (!touch) return;
    const x = touch.x;
    const y = touch.y;

    this._ctx.beginPath();
    this._ctx.moveTo(this._lastX, this._lastY);
    this._ctx.lineTo(x, y);
    this._ctx.stroke();

    this._lastX = x;
    this._lastY = y;
  },

  onTouchEnd() {
    this._isDrawing = false;
  },

  // 只重绘田字格（不含 placeholder）
  redrawGrid() {
    const ctx = this._ctx;
    const w = this._width;
    const h = this._height;

    ctx.fillStyle = '#fff';
    ctx.fillRect(0, 0, w, h);

    ctx.strokeStyle = '#e0e0e0';
    ctx.lineWidth = 1;
    ctx.setLineDash([8, 6]);

    ctx.beginPath();
    ctx.moveTo(0, h / 2);
    ctx.lineTo(w, h / 2);
    ctx.stroke();

    ctx.beginPath();
    ctx.moveTo(w / 2, 0);
    ctx.lineTo(w / 2, h);
    ctx.stroke();

    ctx.strokeStyle = '#f0f0f0';
    ctx.beginPath();
    ctx.moveTo(0, 0);
    ctx.lineTo(w, h);
    ctx.stroke();

    ctx.beginPath();
    ctx.moveTo(w, 0);
    ctx.lineTo(0, h);
    ctx.stroke();

    ctx.setLineDash([]);
    this.resetPen();
  },

  onClear() {
    this._hasDraw = false;
    this.drawBackground();
  },

  onCancel() {
    wx.navigateBack();
  },

  onConfirm() {
    if (!this._hasDraw) {
      wx.showToast({ title: '请先完成签名', icon: 'none' });
      return;
    }
    if (!this._canvas) return;

    const base64 = this._canvas.toDataURL('image/png');
    const eventChannel = this.getOpenerEventChannel();
    eventChannel.emit('signatureDone', { base64 });
    wx.navigateBack();
  }
});
