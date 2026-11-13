Component({
  data: {
    ctx: null,
    canvas: null,
    isDrawing: false,
    lastX: 0,
    lastY: 0
  },

  lifetimes: {
    attached() {
      this.initCanvas();
    }
  },

  methods: {
    async initCanvas() {
      const query = this.createSelectorQuery();
      query.select('#signatureCanvas')
        .fields({ node: true, size: true })
        .exec((res) => {
          const canvas = res[0].node;
          const ctx = canvas.getContext('2d');
          
          // 设置画布大小
          const dpr = wx.getDeviceInfo().pixelRatio;
          canvas.width = res[0].width * dpr;
          canvas.height = res[0].height * dpr;
          ctx.scale(dpr, dpr);
          
          // 设置画笔样式
          ctx.strokeStyle = '#000000';
          ctx.lineWidth = 2;
          ctx.lineCap = 'round';
          ctx.lineJoin = 'round';
          
          this.setData({ ctx, canvas });
        });
    },

    onTouchStart(e) {
      const t = (e && e.touches && e.touches[0]) || {};
      const { x, y } = t;
      this.setData({
        isDrawing: true,
        lastX: x || 0,
        lastY: y || 0
      });
    },

    onTouchMove(e) {
      if (!this.data.isDrawing) return;

      const t = (e && e.touches && e.touches[0]) || null;
      if (!t) return;
      const { x, y } = t;
      const { ctx, lastX, lastY } = this.data;
      
      ctx.beginPath();
      ctx.moveTo(lastX, lastY);
      ctx.lineTo(x, y);
      ctx.stroke();
      
      this.setData({
        lastX: x,
        lastY: y
      });
    },

    onTouchEnd() {
      this.setData({ isDrawing: false });
    },

    clear() {
      const { ctx, canvas } = this.data;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
    },

    submit() {
      const { canvas } = this.data;
      const base64 = canvas.toDataURL('image/png');
      this.triggerEvent('submit', { base64 });
    }
  }
}); 