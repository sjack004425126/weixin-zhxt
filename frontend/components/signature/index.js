Component({
  data: {
    ctx: null,
    canvas: null,
    isDrawing: false,
    lastX: 0,
    lastY: 0,
    hasDraw: false,
    canvasRect: null
  },

  properties: {},

  lifetimes: {
    attached() {
      // 延迟初始化，等 popup 动画完成后 canvas 才有正确尺寸
      setTimeout(() => {
        this.initCanvas();
      }, 300);
    }
  },

  methods: {
    initCanvas() {
      const query = this.createSelectorQuery();
      query.select('#signatureCanvas')
        .fields({ node: true, size: true, rect: true })
        .exec((res) => {
          if (!res[0] || !res[0].node) {
            // 如果还没准备好，再等一下
            setTimeout(() => this.initCanvas(), 200);
            return;
          }

          const canvas = res[0].node;
          const ctx = canvas.getContext('2d');

          const dpr = wx.getWindowInfo().pixelRatio;
          canvas.width = res[0].width * dpr;
          canvas.height = res[0].height * dpr;
          ctx.scale(dpr, dpr);

          ctx.strokeStyle = '#000000';
          ctx.lineWidth = 3;
          ctx.lineCap = 'round';
          ctx.lineJoin = 'round';

          this.setData({ ctx, canvas });
          this.updateCanvasRect();
        });
    },

    updateCanvasRect() {
      this.createSelectorQuery()
        .select('#signatureCanvas')
        .boundingClientRect((rect) => {
          if (rect) {
            this.setData({ canvasRect: rect });
          }
        })
        .exec();
    },

    // 将页面坐标转换为 canvas 内部坐标
    getCanvasPoint(touch) {
      const rect = this.data.canvasRect;
      if (rect) {
        return {
          x: touch.clientX - rect.left,
          y: touch.clientY - rect.top
        };
      }
      // fallback
      return { x: touch.x, y: touch.y };
    },

    onTouchStart(e) {
      if (!this.data.ctx) return;
      // 每次开始触摸时更新一下 rect，防止滚动等导致偏移
      this.updateCanvasRect();
      const touches = (e && e.touches) || [];
      const t = touches[0];
      if (!t) return;
      const point = this.getCanvasPoint(t);
      this.setData({
        isDrawing: true,
        lastX: point.x,
        lastY: point.y
      });
    },

    onTouchMove(e) {
      if (!this.data.isDrawing || !this.data.ctx) return;

      const touches = (e && e.touches) || [];
      const t = touches[0];
      if (!t) return;
      const point = this.getCanvasPoint(t);
      const { ctx, lastX, lastY } = this.data;

      ctx.beginPath();
      ctx.moveTo(lastX, lastY);
      ctx.lineTo(point.x, point.y);
      ctx.stroke();

      this.setData({
        lastX: point.x,
        lastY: point.y,
        hasDraw: true
      });
    },

    onTouchEnd() {
      this.setData({ isDrawing: false });
    },

    cancel() {
      this.triggerEvent('cancel');
    },

    clear() {
      const { ctx, canvas } = this.data;
      if (ctx && canvas) {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        this.setData({ hasDraw: false });
      }
    },

    submit() {
      if (!this.data.hasDraw) {
        wx.showToast({ title: '请先完成签名', icon: 'none' });
        return;
      }
      const { canvas } = this.data;
      if (!canvas) return;

      const base64 = canvas.toDataURL('image/png');
      this.triggerEvent('submit', { base64 });
    }
  },

  options: {
    styleIsolation: 'isolated',
    pureDataPattern: /^_/
  }
});
