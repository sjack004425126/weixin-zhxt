Component({
  properties: {
    show: {
      type: Boolean,
      value: false
    },
    majorName: {
      type: String,
      value: ''
    },
    tuition: {
      type: Number,
      value: 0
    },
    books: {
      type: Number,
      value: 0
    },
    total: {
      type: Number,
      value: 0
    }
  },

  data: {
    timer: null
  },

  observers: {
    'show': function(show) {
      if (show) {
        // 清除之前的定时器
        if (this.data.timer) {
          clearTimeout(this.data.timer);
        }
        // 设置新的定时器
        const timer = setTimeout(() => {
          this.setData({ show: false });
        }, 3000);
        this.setData({ timer });
      }
    }
  }
}); 