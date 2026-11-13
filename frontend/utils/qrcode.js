// 简化版二维码生成工具
// 实际项目中建议使用完整的二维码库如 qrcode.js

const QRCode = {
  // 生成二维码数据
  generate: function(text, options = {}) {
    const size = options.size || 200;
    const margin = options.margin || 20;
    
    // 这里返回一个模拟的二维码数据结构
    // 实际应用中需要使用真正的二维码算法
    return {
      size: size,
      margin: margin,
      data: this.createQRMatrix(text, size),
      text: text
    };
  },

  // 创建二维码矩阵（简化版）
  createQRMatrix: function(text, size) {
    const matrixSize = 25; // 简化的矩阵大小
    const matrix = [];
    
    // 初始化矩阵
    for (let i = 0; i < matrixSize; i++) {
      matrix[i] = [];
      for (let j = 0; j < matrixSize; j++) {
        matrix[i][j] = false;
      }
    }
    
    // 简化的二维码图案生成
    // 实际应用中需要使用标准的二维码生成算法
    this.addFinderPatterns(matrix, matrixSize);
    this.addDataPattern(matrix, matrixSize, text);
    
    return matrix;
  },

  // 添加定位图案
  addFinderPatterns: function(matrix, size) {
    const positions = [
      [0, 0], // 左上
      [0, size - 7], // 右上
      [size - 7, 0] // 左下
    ];
    
    positions.forEach(([row, col]) => {
      // 7x7 定位图案
      for (let i = 0; i < 7; i++) {
        for (let j = 0; j < 7; j++) {
          if (row + i < size && col + j < size) {
            const isEdge = i === 0 || i === 6 || j === 0 || j === 6;
            const isCenter = i >= 2 && i <= 4 && j >= 2 && j <= 4;
            matrix[row + i][col + j] = isEdge || isCenter;
          }
        }
      }
    });
  },

  // 添加数据图案（简化版）
  addDataPattern: function(matrix, size, text) {
    // 简化的数据编码，基于文本内容生成图案
    const hash = this.simpleHash(text);
    
    for (let i = 8; i < size - 8; i++) {
      for (let j = 8; j < size - 8; j++) {
        // 避开定位图案区域
        if (this.isInFinderPattern(i, j, size)) continue;
        
        // 基于哈希值生成图案
        const index = (i * size + j) % hash.length;
        matrix[i][j] = hash.charCodeAt(index) % 2 === 0;
      }
    }
  },

  // 检查是否在定位图案区域
  isInFinderPattern: function(row, col, size) {
    const patterns = [
      [0, 0, 8, 8], // 左上
      [0, size - 8, 8, 8], // 右上
      [size - 8, 0, 8, 8] // 左下
    ];
    
    return patterns.some(([r, c, w, h]) => {
      return row >= r && row < r + h && col >= c && col < c + w;
    });
  },

  // 简单哈希函数
  simpleHash: function(str) {
    let hash = '';
    for (let i = 0; i < str.length; i++) {
      const char = str.charCodeAt(i);
      hash += char.toString(16);
    }
    return hash;
  },

  // 在Canvas上绘制二维码
  drawOnCanvas: function(ctx, qrData, x = 0, y = 0) {
    const { data, size, margin } = qrData;
    const matrixSize = data.length;
    const cellSize = (size - margin * 2) / matrixSize;
    
    // 清空画布
    ctx.clearRect(x, y, size, size);
    
    // 绘制白色背景
    ctx.setFillStyle('#FFFFFF');
    ctx.fillRect(x, y, size, size);
    
    // 绘制二维码
    ctx.setFillStyle('#000000');
    for (let i = 0; i < matrixSize; i++) {
      for (let j = 0; j < matrixSize; j++) {
        if (data[i][j]) {
          const cellX = x + margin + j * cellSize;
          const cellY = y + margin + i * cellSize;
          ctx.fillRect(cellX, cellY, cellSize, cellSize);
        }
      }
    }
  }
};

// 导出模块
module.exports = {
  qrcode: function(errorCorrectionLevel, mode) {
    return {
      addData: function(data) {
        this.data = data;
      },
      make: function() {
        this.modules = QRCode.createQRMatrix(this.data, 25);
      },
      getModuleCount: function() {
        return this.modules ? this.modules.length : 0;
      },
      modules: null,
      data: null
    };
  },
  QRCode: QRCode
};
