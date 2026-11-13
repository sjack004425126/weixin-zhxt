// utils/config.js - 应用配置文件

// 扫码功能配置
export const SCAN_CONFIG = {
  // 是否强制启用调试模式
  // 开发期间设为 true，发布时设为 false
  FORCE_DEBUG_MODE: true,
  
  // 调试模式说明
  DEBUG_MODE_TIPS: {
    title: '🔧 调试模式',
    content: '扫码功能已切换为调试模式，方便测试各种场景。\n\n您可以：\n• 点击"调试选项"选择测试用例\n• 点击下方快速测试按钮\n• 使用"手动输入"功能\n• 长按扫码区域切换到真实扫码'
  },
  
  // 测试用例配置
  TEST_CASES: [
    { name: '推广链接-王小华', content: 'introducer=王小华&major=计算机应用技术' },
    { name: '推广链接-杨欢', content: 'introducer=杨欢&major=电子商务&campaign=spring2024' },
    { name: '推广链接-张龙', content: 'introducer=张龙&major=机械制造&source=teacher' },
    { name: 'Base64编码测试', content: 'uid=55-z5byA5Y2O&major=计算机应用技术' },
    { name: '推广链接-李聪聪', content: 'introducer=李聪聪&major=护理学&region=北京' },
    { name: '推广链接-潘明月', content: 'introducer=潘明月&major=会计学&campaign=autumn2024' },
    { name: '网址链接', content: 'https://www.example.com/promotion?id=12345' },
    { name: 'JSON数据', content: '{"type":"promotion","introducer":"测试老师","major":"软件工程","timestamp":"2024-01-15"}' },
    { name: '纯文本', content: '这是一个测试二维码内容，用于验证文本处理功能' },
    { name: '小程序路径', content: 'pages/vocational-zzbm/vocational-zzbm?scene=uid%3D55-z5byA5Y2O' }
  ]
};

// 应用基础配置
export const APP_CONFIG = {
  // 应用名称
  APP_NAME: '职业教育招生小程序',
  
  // 版本信息
  VERSION: '1.0.0',
  
  // 是否为开发模式
  IS_DEV: true,
  
  // API配置
  API: {
    BASE_URL: 'https://your-api-domain.com',
    TIMEOUT: 10000
  }
};

// 页面配置
export const PAGE_CONFIG = {
  // 首页配置
  HOME: {
    SHOW_DEBUG_ENTRY: true, // 是否显示调试入口
    AUTO_REFRESH: false     // 是否自动刷新
  },
  
  // 扫码页面配置
  SCAN: {
    AUTO_SAVE_HISTORY: true,    // 是否自动保存扫码历史
    MAX_HISTORY_COUNT: 50,      // 最大历史记录数量
    SHOW_INSTRUCTIONS: true     // 是否显示使用说明
  }
};

export default {
  SCAN_CONFIG,
  APP_CONFIG,
  PAGE_CONFIG
};
