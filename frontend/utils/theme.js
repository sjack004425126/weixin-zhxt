/**
 * 全局主题配置
 * 统一管理整个应用的主题色彩和样式配置
 */

// 主题色彩配置
const THEME_COLORS = {
  // 主色调 - 蓝色系
  primary: '#1890FF',
  primaryLight: '#E6F7FF',
  primaryDark: '#0050B3',
  
  // 辅助色彩
  success: '#52C41A',
  warning: '#FAAD14',
  error: '#FF4D4F',
  info: '#1890FF',
  
  // 文字颜色
  textMain: '#333333',
  textSecondary: '#666666',
  textLight: '#999999',
  textDisabled: '#BFBFBF',
  
  // 背景颜色
  bgWhite: '#FFFFFF',
  bgGray: '#F7F8FA',
  bgLight: '#FAFBFC',
  
  // 边框颜色
  borderColor: '#EEEEEE',
  borderLight: '#F0F0F0'
};

// 渐变配置
const THEME_GRADIENTS = {
  primary: 'linear-gradient(135deg, #1890FF 0%, #40A9FF 100%)',
  background: 'linear-gradient(180deg, #E6F7FF 0%, #F7F8FA 100%)'
};

// 阴影配置
const THEME_SHADOWS = {
  card: '0 4rpx 16rpx rgba(24, 144, 255, 0.08)',
  cardHover: '0 8rpx 24rpx rgba(24, 144, 255, 0.12)',
  cardActive: '0 2rpx 8rpx rgba(24, 144, 255, 0.15)'
};

// 圆角配置
const THEME_RADIUS = {
  sm: '8rpx',
  md: '12rpx',
  lg: '16rpx',
  xl: '20rpx'
};

// 间距配置
const THEME_SPACING = {
  xs: 8,
  sm: 16,
  md: 24,
  lg: 32,
  xl: 48
};

// 字体大小配置
const THEME_FONT_SIZE = {
  xs: 20,
  sm: 24,
  md: 28,
  lg: 32,
  xl: 36,
  xxl: 40
};

// 动画时长配置
const THEME_ANIMATION = {
  fast: 200,
  base: 300,
  slow: 500
};

// 层级配置
const THEME_Z_INDEX = {
  base: 1,
  popup: 100,
  modal: 1000,
  toast: 2000
};

// 导出主题配置对象
const THEME = {
  colors: THEME_COLORS,
  gradients: THEME_GRADIENTS,
  shadows: THEME_SHADOWS,
  radius: THEME_RADIUS,
  spacing: THEME_SPACING,
  fontSize: THEME_FONT_SIZE,
  animation: THEME_ANIMATION,
  zIndex: THEME_Z_INDEX
};

// 工具函数：获取主题色
const getThemeColor = (colorName) => {
  return THEME_COLORS[colorName] || THEME_COLORS.primary;
};

// 工具函数：获取带透明度的颜色
const getThemeColorWithOpacity = (colorName, opacity = 0.1) => {
  const color = getThemeColor(colorName);
  // 将十六进制颜色转换为 rgba
  const r = parseInt(color.slice(1, 3), 16);
  const g = parseInt(color.slice(3, 5), 16);
  const b = parseInt(color.slice(5, 7), 16);
  return `rgba(${r}, ${g}, ${b}, ${opacity})`;
};

// 工具函数：生成状态标签样式
const getStatusTagStyle = (type = 'primary') => {
  const colorMap = {
    primary: THEME_COLORS.primary,
    success: THEME_COLORS.success,
    warning: THEME_COLORS.warning,
    error: THEME_COLORS.error
  };
  
  const color = colorMap[type] || colorMap.primary;
  const r = parseInt(color.slice(1, 3), 16);
  const g = parseInt(color.slice(3, 5), 16);
  const b = parseInt(color.slice(5, 7), 16);
  
  return {
    backgroundColor: `rgba(${r}, ${g}, ${b}, 0.1)`,
    color: color,
    border: `1rpx solid rgba(${r}, ${g}, ${b}, 0.2)`
  };
};

// 工具函数：生成卡片样式
const getCardStyle = (hover = false) => {
  return {
    backgroundColor: THEME_COLORS.bgWhite,
    borderRadius: THEME_RADIUS.lg,
    boxShadow: hover ? THEME_SHADOWS.cardHover : THEME_SHADOWS.card,
    border: `1rpx solid ${THEME_COLORS.borderColor}`,
    transition: `all ${THEME_ANIMATION.base}ms ease`
  };
};

// 工具函数：生成按钮样式
const getButtonStyle = (type = 'primary') => {
  if (type === 'primary') {
    return {
      background: THEME_GRADIENTS.primary,
      borderColor: THEME_COLORS.primary,
      color: '#ffffff',
      boxShadow: THEME_SHADOWS.card
    };
  }
  
  return {
    backgroundColor: THEME_COLORS.bgWhite,
    borderColor: THEME_COLORS.borderColor,
    color: THEME_COLORS.textSecondary
  };
};

// 导出配置和工具函数
module.exports = {
  THEME,
  getThemeColor,
  getThemeColorWithOpacity,
  getStatusTagStyle,
  getCardStyle,
  getButtonStyle
};
