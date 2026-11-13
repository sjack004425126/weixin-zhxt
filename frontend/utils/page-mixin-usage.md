# 页面混入使用指南

`page-mixin` 是项目的**页面级基础设施**，统一管理消息提示、登录守卫、头部测量和通用组件挂载。所有页面都应通过 `createPage` 工厂创建，避免手动散落重复代码。

---

## 目录

1. [快速开始](#快速开始)
2. [createPage 选项](#createpage-选项)
3. [可用的混入方法](#可用的混入方法)
4. [通用组件自动注册](#通用组件自动注册)
5. [页面生命周期合并](#页面生命周期合并)
6. [迁移指南](#迁移指南)
7. [对比：不使用 page-mixin](#对比不使用-page-mixin)

---

## 快速开始

### 1. JS 文件：使用 `createPage` 工厂

```javascript
// pages/example/example.js
const { createPage } = require('../../utils/page-mixin');

createPage({
  data: {
    list: []
  },

  onLoad() {
    this.fetchList();
  },

  async fetchList() {
    try {
      const res = await wx.request({ url: '/api/list' });
      this.setData({ list: res.data });
      this.showSuccess('加载成功');
    } catch (err) {
      this.showError('加载失败');
    }
  }
});
```

### 2. WXML 文件：引入通用组件片段

```xml
<!-- pages/example/example.wxml -->
<include src="/utils/common-components.wxml" />

<view class="container">
  <!-- 你的页面内容 -->
</view>
```

### 3. JSON 文件：注册通用组件（按需）

如果通用组件已经全局注册（`app.json` 的 `usingComponents`），则页面 json 无需额外配置；否则需要注册。

**当前项目状态**：`top-message` 已在 `app.json` 全局注册，新页面**无需在 json 中声明**。

---

## createPage 选项

```typescript
createPage(pageConfig, options)
```

| 选项 | 类型 | 默认值 | 说明 |
|------|------|-------|------|
| `requireAuth` | `boolean` | `false` | 是否需要登录才能访问 |
| `userType` | `string` | - | 配合 `requireAuth` 使用，指定用户端类型 |
| `autoRegisterComponents` | `boolean` | `true` | 是否自动检测通用组件是否挂载 |

### `userType` 取值

| 取值 | 说明 |
|------|------|
| `'open_student'` | 开放教育学生 |
| `'vocational_student'` | 中职学生 |
| `'vocational_teacher'` | 中职教师 |
| `'open_teacher'` | 开放教育教师 |

### 示例：需要登录的页面

```javascript
// pages/vocational-info/vocational-info.js
const { createPage } = require('../../utils/page-mixin');

createPage({
  data: { userInfo: {} },
  onLoad() {
    this.loadUserInfo();
  },
  loadUserInfo() {
    // 这里的 onLoad 只会在登录校验通过后才执行
  }
}, {
  requireAuth: true,
  userType: 'vocational_student'
});
```

---

## 可用的混入方法

通过 `this.xxx` 直接调用，无需 import。

### 消息提示

| 方法 | 说明 | 默认 duration |
|------|------|---------------|
| `this.showSuccess(msg, duration)` | 显示成功提示 | 3000ms |
| `this.showError(msg, duration)` | 显示错误提示 | 3000ms |
| `this.showWarning(msg, duration)` | 显示警告提示 | 3000ms |
| `this.showInfo(msg, duration)` | 显示信息提示 | 3000ms |
| `this.showTopMessage(msg, type, duration, icon)` | 通用顶部消息 | 5000ms |

**自动归一化**：`message` 可以是字符串、对象（取 `.message`）、错误对象、任意对象（自动 `JSON.stringify`），永远不会出现 `[object Object]`。

**优雅降级**：如果页面没有引入 `top-message` 组件，会自动 fallback 到 `wx.showToast`。

### 登录守卫

| 方法 | 说明 |
|------|------|
| `this.checkLogin(callback)` | 检查登录态，未登录则跳转登录页 |
| `this.isLoggedIn()` | 同步返回是否登录 |
| `this.requireLogin(callback)` | 同 `checkLogin`（语义别名） |

---

## 通用组件自动注册

`createPage` 默认启用 `autoRegisterComponents: true`，会在 `onReady` 阶段自动检测当前页面 wxml 是否引入了通用组件片段。

### 引入方式

```xml
<!-- 页面 wxml 顶部 -->
<include src="/utils/common-components.wxml" />
```

### 检测机制

- `common-components.wxml` 内部包含一个不可见的 `<view id="__common-components-marker">` 标记
- `createPage` 在 `onReady` 时通过 `wx.createSelectorQuery` 查询这个标记
- **未引入**：开发环境 `console.warn` 提醒，但不阻塞页面运行（仍可通过 `wx.showToast` 降级提示）
- **已引入**：标记 `this.data._commonComponentsIncluded = true`

### 当前包含的组件

| 组件 | 状态 | 说明 |
|------|------|------|
| `top-message` | 默认引入 | 顶部消息提示，所有页面都应可用 |
| `fee-toast` | 注释状态 | 按需解开注释启用 |

新增通用组件时，请同步更新 `utils/common-components.wxml` 和本文档。

---

## 页面生命周期合并

`createPage` 会自动合并以下钩子，**混入先执行，页面后执行**：

| 钩子 | 是否合并 | 说明 |
|------|---------|------|
| `onLoad` | ✅ | 混入版本会处理头部测量和组件检测 |
| `onShow` | ✅ | 混入无实现时直接走页面 |
| `onReady` | ✅ | 混入会做头部测量 + 组件检测 |
| `onHide` | ✅ | - |
| `onUnload` | ✅ | - |
| `onPullDownRefresh` | ✅ | - |
| `onReachBottom` | ✅ | - |
| `onShareAppMessage` | ✅ | - |
| `onPageScroll` | ✅ | - |
| `onResize` | ✅ | - |

**示例**：

```javascript
// 你的 onLoad 会和混入的 onLoad 一起执行
// 混入先做头部测量和组件检测，再执行你的逻辑
createPage({
  onLoad() {
    this.fetchData();  // 这个会执行
  },
  onReady() {
    this.renderChart();  // 这个也会执行（混入的 onReady 先跑）
  }
});
```

---

## 迁移指南

### 从原生 `Page` 迁移到 `createPage`

```javascript
// 旧代码
Page({
  data: { ... },
  onLoad() { ... },
  showError() { ... }  // 自己实现的提示
});

// 新代码
const { createPage } = require('../../utils/page-mixin');

createPage({
  data: { ... },
  onLoad() { ... }
  // 不需要实现 showError，直接用混入的
});
```

### 从手写 `<top-message>` 迁移到片段

**改造前**：

```xml
<!-- pages/xxx/xxx.wxml -->
<top-message id="top-message"></top-message>
<view class="container">...</view>
```

**改造后**：

```xml
<!-- pages/xxx/xxx.wxml -->
<include src="/utils/common-components.wxml" />
<view class="container">...</view>
```

---

## 对比：不使用 page-mixin

> 假设你**不使用** `createPage` 和 `page-mixin`，自己手动实现所有功能：

### 你需要手动做的事情

| 功能 | 不使用 mixin 的代码量 | 使用 mixin 的代码量 |
|------|---------------------|---------------------|
| 创建页面 | 1 行 `Page({...})` | 1 行 `createPage({...})` |
| 头部高度测量 | 每个页面 ~10 行 | 0 行（自动） |
| 顶部消息提示 | 每个页面手动 selectComponent + 降级 | 0 行（自动） |
| 登录守卫 | 每个页面写 ~20 行 | 1 行 option |
| 通用组件引入 | 每个页面 wxml 写 `<top-message>` 等标签 | 1 行 `<include>` |

**累计**：假设项目有 70+ 页面，不使用 mixin 会产生 **数百行重复代码**，且每个页面都要记得维护同样的逻辑，**容易遗漏**（比如某天加了一个新通用组件，要改 70 个文件）。

### 实际差距举例

**场景**：一个需要登录的页面调用接口失败要提示用户。

**不使用 mixin**：

```javascript
Page({
  data: { ... },
  onLoad() {
    // 1. 手动检查登录
    if (!wx.getStorageSync('token')) {
      wx.redirectTo({ url: '/pages/login/login' });
      return;
    }

    // 2. 手动调用接口
    wx.request({
      url: '/api/data',
      success: (res) => {
        this.setData({ data: res.data });
        // 3. 手动提示成功（且要处理 message 是对象的情况）
        const msg = typeof res.message === 'string' ? res.message : '加载成功';
        this.selectComponent('#top-message').show(msg, 'success', 3000);
      },
      fail: (err) => {
        // 4. 手动提示失败
        const msg = (err && err.message) || '加载失败';
        const topMsg = this.selectComponent('#top-message');
        if (topMsg) {
          topMsg.show(msg, 'error', 3000);
        } else {
          wx.showToast({ title: msg, icon: 'none' });
        }
      }
    });
  }
});
```

```xml
<!-- 还要在 wxml 顶部手动写 -->
<top-message id="top-message"></top-message>
```

**使用 mixin**：

```javascript
const { createPage } = require('../../utils/page-mixin');

createPage({
  data: { ... },
  onLoad() {
    this.loadData();
  },
  async loadData() {
    try {
      const res = await wx.request({ url: '/api/data' });
      this.setData({ data: res.data });
      this.showSuccess('加载成功');
    } catch (err) {
      this.showError(err);
    }
  }
}, {
  requireAuth: true
});
```

```xml
<include src="/utils/common-components.wxml" />
```

**核心优势**：

1. **代码量减少 ~60%**：核心逻辑不变，样板代码被抽走
2. **统一行为**：登录跳转、消息提示的逻辑改一处，全站生效
3. **类型安全**：消息归一化防止 `[object Object]`
4. **渐进增强**：通过 `autoRegisterComponents` 选项检测挂载，开发体验更好
5. **零迁移成本**：所有 70+ 页面可以平滑切换，原有 API 完全兼容

---

## 常见问题

### Q: 我不想用 `createPage`，只想用 `showSuccess` 这些方法？

可以直接解构：

```javascript
const { showSuccess, showError, requireLogin } = require('../../utils/page-mixin');

Page({
  data: { ... },
  onLoad() {
    // 登录守卫还是需要手动调用
    requireLogin.call(this, () => {
      // 已登录逻辑
    });
    // 注意：直接解构出来的是函数，需要 call(this) 才能挂载到 this 上
  },
  someMethod() {
    showSuccess.call(this, '成功');
  }
});
```

**但是消息提示方法会找不到 `selectComponent`**，因为 `this` 上下文不对。**强烈推荐使用 `createPage`**。

### Q: 我可以覆盖混入的方法吗？

可以。`pageConfig` 中的方法会覆盖混入的同名方法：

```javascript
createPage({
  showSuccess(msg) {
    console.log('自定义提示：', msg);
    // 不会调用混入的实现
  }
});
```

如果想保留混入实现并扩展，请重写一个不同名字的方法，或者在工厂外手动调用。

### Q: 混入的 `onLoad` 和我的 `onLoad` 哪个先执行？

混入的先执行。这是为了让混入能完成准备工作（如头部测量）后，再让页面使用。

### Q: 关闭自动组件检测？

```javascript
createPage(pageConfig, {
  autoRegisterComponents: false  // 关闭检测
});
```

但你仍然需要确保 wxml 引入了通用组件片段，否则 `showSuccess` 等方法会 fallback 到 `wx.showToast`（也能用，但视觉风格不同）。
