# 全局主题配置使用指南

## 概述

我们已经建立了一套完整的全局主题配置系统，用于统一管理整个应用的颜色、样式和设计规范。

## 文件结构

```
frontend/
├── styles/
│   └── theme.wxss          # 全局主题样式文件
├── utils/
│   └── theme.js            # 主题配置 JavaScript 文件
├── app.wxss                # 全局样式文件（引入主题）
└── app.json                # 全局配置（导航栏颜色等）
```

## 主题配置

### 1. 颜色系统

#### 主色调
- `--primary-color: #1890FF` - 主色（蓝色）
- `--primary-light: #E6F7FF` - 浅色背景
- `--primary-dark: #0050B3` - 深色主色
- `--primary-gradient` - 主色渐变

#### 辅助色彩
- `--success-color: #52C41A` - 成功色（绿色）
- `--warning-color: #FAAD14` - 警告色（黄色）
- `--error-color: #FF4D4F` - 错误色（红色）

#### 文字颜色
- `--text-main: #333333` - 主要文字
- `--text-secondary: #666666` - 次要文字
- `--text-light: #999999` - 浅色文字
- `--text-disabled: #BFBFBF` - 禁用文字

### 2. 背景颜色
- `--bg-white: #FFFFFF` - 白色背景
- `--bg-gray: #F7F8FA` - 灰色背景
- `--bg-light: #FAFBFC` - 浅色背景

### 3. 边框和阴影
- `--border-color: #EEEEEE` - 边框颜色
- `--card-shadow` - 卡片阴影
- `--card-shadow-hover` - 悬停阴影

### 4. 圆角大小
- `--border-radius-sm: 8rpx` - 小圆角
- `--border-radius-md: 12rpx` - 中等圆角
- `--border-radius-lg: 16rpx` - 大圆角
- `--border-radius-xl: 20rpx` - 超大圆角

## 使用方法

### 1. 在 WXSS 中使用

```css
/* 使用主题颜色 */
.my-button {
  background: var(--primary-color);
  color: var(--bg-white);
  border-radius: var(--border-radius-md);
  box-shadow: var(--card-shadow);
}

/* 使用主题渐变 */
.gradient-bg {
  background: var(--primary-gradient);
}

/* 使用预定义的通用样式类 */
.my-card {
  @extend .theme-card;
}

.my-title {
  @extend .theme-title;
}
```

### 2. 在 JavaScript 中使用

```javascript
// 引入主题配置
const { THEME, getThemeColor, getStatusTagStyle } = require('../../utils/theme');

Page({
  data: {
    primaryColor: getThemeColor('primary'),
    buttonStyle: getButtonStyle('primary')
  },
  
  onLoad() {
    // 动态设置样式
    const tagStyle = getStatusTagStyle('success');
    console.log('成功标签样式:', tagStyle);
  }
});
```

### 3. 通用样式类

我们提供了一些预定义的通用样式类：

```css
/* 颜色类 */
.theme-primary { color: var(--primary-color); }
.theme-primary-bg { background-color: var(--primary-color); }
.theme-gradient-bg { background: var(--primary-gradient); }

/* 卡片类 */
.theme-card { /* 标准卡片样式 */ }
.theme-card-header { /* 带装饰线的卡片头部 */ }

/* 标题类 */
.theme-title { /* 带装饰条的标题 */ }

/* 状态标签类 */
.status-tag.primary { /* 主色标签 */ }
.status-tag.success { /* 成功标签 */ }
.status-tag.warning { /* 警告标签 */ }
.status-tag.error { /* 错误标签 */ }
```

## 全局配置

### 1. 导航栏配置（app.json）

```json
{
  "window": {
    "navigationBarBackgroundColor": "#1890FF",
    "navigationBarTextStyle": "white"
  },
  "tabBar": {
    "selectedColor": "#1890FF"
  }
}
```

### 2. 页面级配置

如果某个页面需要特殊的导航栏颜色，可以在页面的 JSON 文件中配置：

```json
{
  "navigationBarTitleText": "特殊页面",
  "navigationBarBackgroundColor": "#52C41A",
  "navigationBarTextStyle": "white"
}
```

## 主题切换

如果将来需要支持主题切换（如深色模式），可以通过以下方式：

### 1. 定义多套主题

```css
/* 浅色主题 */
page[data-theme="light"] {
  --primary-color: #1890FF;
  --bg-color: #FFFFFF;
}

/* 深色主题 */
page[data-theme="dark"] {
  --primary-color: #40A9FF;
  --bg-color: #1F1F1F;
}
```

### 2. JavaScript 切换

```javascript
// 切换主题
function switchTheme(theme) {
  const pages = getCurrentPages();
  const currentPage = pages[pages.length - 1];
  currentPage.setData({
    theme: theme
  });
}
```

## 最佳实践

1. **统一使用 CSS 变量**：避免硬编码颜色值
2. **使用预定义样式类**：提高代码复用性
3. **保持一致性**：所有页面使用相同的主题配置
4. **易于维护**：颜色修改只需要在主题文件中进行
5. **响应式设计**：使用主题中定义的间距和字体大小

## 示例页面

参考 `pages/vocational-my/vocational-my.wxss` 查看完整的主题使用示例。

这套主题配置系统确保了整个应用的视觉一致性，同时便于维护和扩展。
