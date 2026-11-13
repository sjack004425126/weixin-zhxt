# [001] vant-icon 组件在 login 页面不显示图标

> **日期**：2026-08-08
> **严重度**：🔴 高（阻塞核心登录功能）
> **影响范围**：login 页面所有图标（10 处）
> **状态**：✅ 已解决
> **解决用时**：约 3 小时（多次错误方向）

---

## 一、现象描述

### 用户反馈
> "我测试清理了其他所有元素，还是不显示。"

### 截图
- 顶部测试块（前缀 `测试 B`）：✅ 显示图标（phone-o、chat-o）
- 顶部测试块（前缀 `测试 A`）：❌ 不显示（所有 van-icon 都不显示）
- login 主页面：❌ 所有 van-icon 都不显示（10 个图标全部空白）

### 关键矛盾
- `icon-isolate` 页面（独立测试页）：✅ 正常显示
- `login-icons-test` 页面：✅ 正常显示
- `login` 页面：❌ 全部不显示

**三个页面使用的都是同一个 `vant-icon` 组件（`/components/vant-icon/index`）。**

---

## 二、排查过程

### 步骤 1：检查组件是否正常引用
**假设**：可能是 `login.json` 没注册组件。

**验证**：
```json
// login.json
{
  "usingComponents": {
    "van-icon": "/components/vant-icon/index",
    "van-button": "@vant/weapp/button/index"
  }
}
```

**结论**：✅ 组件已注册。

---

### 步骤 2：检查全局样式冲突
**假设**：可能是 `app.wxss` 或 `home.wxss` 的全局样式影响了 vant-icon。

**验证**：把所有 `login.wxss` 内容备份清空，重新写最简单的样式。

**结论**：❌ 问题依旧。

---

### 步骤 3：检查嵌套结构
**假设**：可能是 `<view>` 嵌套结构问题。

**验证**：把所有 van-icon 移到 login 页面最顶部、最外层，**不嵌套任何东西**。

**结论**：❌ 仍然不显示。

---

### 步骤 4：检查 vant-icon 字体是否加载
**假设**：可能是字体文件 `//at.alicdn.com/...woff2` 加载失败。

**验证**：写两个测试：
- **测试 A**：`<van-icon name="phone-o" />`
- **测试 B**：`<text style="font-family:vant-icon">真实 unicode 字符（如 \ue6fc）</text>`

**结果**：
- 测试 A：❌ 不显示
- 测试 B（前两个图标）：✅ 显示了 phone 和 chat 图标

**结论**：
- ✅ vant-icon 字体**已加载**（测试 B 显示了图标）
- ❌ `<van-icon>` 组件本身**不工作**（测试 A 不显示）

---

### 步骤 5：尝试 HTML 实体
**错误尝试**：在 wxml 中使用 `&#xe6fc;` 代替 unicode 字符。

**结果**：wxml 中显示为字面字符串 `&#xe6fc;`。

**教训**：❌ **wxml 不解析 HTML 实体**，必须写入真实的 unicode 字符。

---

### 步骤 6：用 Python 脚本批量替换
**方案**：解析 `vant-icon/index.wxss` 建立图标名 → unicode 字符映射，把所有 `<van-icon name="...">` 替换为 `<text class="vi">unicode字符</text>`。

**结果**：✅ 成功修复。

---

## 三、根本原因

### 技术原理

`vant-icon` 组件用 **`view` 元素 + `::before` 伪元素** 实现字体图标：

```wxml
<!-- components/vant-icon/index.wxml -->
<view class="van-icon van-icon-phone-o">
  <van-info wx:if="..." />
</view>
```

```css
/* components/vant-icon/index.wxss */
.van-icon {
  font-family: vant-icon;
}
.van-icon:before {
  display: inline-block;
  content: "\e6fc";  /* phone-o 的 unicode 字符 */
}
```

**`view` 的 `::before` 伪元素依赖小程序 wxss 引擎正确处理"伪元素 + content"**。

### 为什么 login 页面出问题

**最可能的根本原因**（**未完全证实**）：
`login.wxss` 中的某个 wxss 规则（如 `.van-icon { transition: all !important; }` 或 `@import` 顺序问题）**破坏了 vant-icon 组件的 view + ::before 渲染**。

**次要可能性**：
- 多个 wxss 文件的 `@import` 顺序冲突
- 某个全局 `view:before` 规则被覆盖

### 三个页面对比

| 页面 | vant-icon 表现 | 推测原因 |
|------|--------------|----------|
| `icon-isolate` | ✅ 正常 | 独立页面，wxss 简单，无冲突 |
| `login-icons-test` | ✅ 正常 | 测试页，wxss 简单 |
| `login` | ❌ 不显示 | wxss 复杂，多处 import |

---

## 四、修复方案

### 核心修复：把 `<van-icon>` 替换为 `<text>`

**原理**：用 `<text>` 元素直接渲染 vant-icon 字体的 unicode 字符，**完全绕过** view + ::before 伪元素机制。

### 改动文件

#### 1. `pages/login/login.wxml`

**修改前**：
```wxml
<van-icon name="phone-o" size="40rpx" color="#E86433" class="custom-input-icon" />
<van-icon name="lock" size="48rpx" />
```

**修改后**：
```wxml
<text class="vi custom-input-icon" style="font-family:vant-icon,sans-serif;font-size:40rpx;color:#E86433;"></text>
<text class="vi" style="font-family:vant-icon,sans-serif;font-size:48rpx;"></text>
```

> 注意：`>` 后面必须是**真实 unicode 字符**（UTF-8 编码），不是 `&#xe6fc;` HTML 实体。

#### 2. `pages/login/login.wxss`

**添加 .vi 基础样式**：
```css
/* vi 类：用于直接用 text 渲染 vant-icon 字体的 unicode 字符 */
.vi {
  display: inline-block;
  vertical-align: middle;
  line-height: 1;
  font-family: vant-icon, sans-serif;
}

/* type-icon 内的图标样式（替换原 .type-icon .van-icon） */
.type-icon .vi {
  color: #999;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.type-icon.active .vi {
  color: #E86433;
  transform: scale(1.2);
}
```

### 修复脚本

见 [`fix/replace_van_icon.py`](./fix/replace_van_icon.py)（自动批量替换）。

---

## 五、经验教训

### 1. ❌ 排查误区

| 误区 | 为什么错 |
|------|---------|
| 怀疑嵌套结构问题 | 与嵌套无关，移到最外层仍不显示 |
| 怀疑全局样式冲突 | 清空 login.wxss 也不显示 |
| 怀疑组件未注册 | icon-isolate 用同一个组件能显示 |
| 怀疑字体未加载 | 实际字体可用（测试 B 证明了） |

### 2. ✅ 关键诊断方法

**最终有效的诊断是"分离测试"**：
1. 把问题拆成"组件渲染"和"字体加载"两个独立维度
2. **绕过组件**（用 text 直接渲染 unicode 字符）测试字体
3. **保留组件**（用 van-icon）测试组件渲染

这个方法快速定位到：**字体 OK，组件不工作**。

### 3. 💡 wxml 不解析 HTML 实体

**关键发现**：wxml 中写 `&#xe6fc;` 会被当作字面字符串显示。
- 必须写入**真实的 unicode 字符**（UTF-8 编码）
- 可用 Python 脚本批量生成：`chr(0xE6FC)`

### 4. 📋 修复脚本原则

修复脚本必须：
1. 解析 `vant-icon/index.wxss` 建立 name → unicode 映射
2. 用真实 unicode 字符替换（不要用 HTML 实体）
3. **验证替换后的字符编码**（确保 UTF-8 字节正确）

---

## 六、排查指南（类似问题快速定位）

### 症状
vant-icon（或类似字体图标组件）在某个特定页面不显示，但其他页面正常。

### 步骤

#### 1. 确认组件引用
```json
// <page>.json
{
  "usingComponents": {
    "van-icon": "/components/vant-icon/index"
  }
}
```

#### 2. 字体加载测试
在页面顶部写：
```wxml
<!-- 测试字体是否加载 -->
<text style="font-family:vant-icon,sans-serif;font-size:48rpx;color:red;">真实字符</text>
```

> 注意：直接用 unicode 字符（如 `chr(0xE6FC)`），不要用 `&#xe6fc;`。

#### 3. 隔离测试
- 把 `<van-icon>` 移到页面**最外层、最顶部**
- 清空该页面所有自定义 wxss
- 重启开发工具

#### 4. 决定修复方案

| 测试结果 | 原因 | 修复方案 |
|---------|------|---------|
| text 显示图标，van-icon 不显示 | 组件渲染问题 | **用 text 替换 van-icon**（本次方案） |
| text 不显示图标 | 字体未加载 | 检查 `@font-face`、网络 |
| 两个都不显示 | 字体未加载或页面被错误禁用 | 进一步排查网络 |

### 5. 批量替换 van-icon 为 text

**模板脚本**（用 Python）：

```python
import re

# 解析 vant-icon wxss 建立映射
wxss = open('vant-icon/index.wxss', 'r', encoding='utf-8').read()
pattern = re.compile(r'\.van-icon-([a-z0-9-]+):before\{content:"\\([a-f0-9]+)"\}')
name_to_unicode = {m.group(1): chr(int(m.group(2), 16)) for m in pattern.finditer(wxss)}

# 替换 wxml
wxml = open('login.wxml', 'r', encoding='utf-8').read()
def replace_icon(m):
    name = m.group(1)
    size = m.group(2) or '1em'
    color = m.group(3) or 'inherit'
    cls = m.group(4) or ''
    if name not in name_to_unicode:
        return m.group(0)
    char = name_to_unicode[name]
    extra = (' ' + cls) if cls else ''
    return f'<text class="vi{extra}" style="font-family:vant-icon,sans-serif;font-size:{size};color:{color};">{char}</text>'

icon_pattern = re.compile(
    r'<van-icon\s+name="([^"]+)"(?:\s+size="([^"]+)")?(?:\s+color="([^"]+)")?(?:\s+class="([^"]+)")?\s*/>'
)
new_wxml = icon_pattern.sub(replace_icon, wxml)

open('login.wxml', 'w', encoding='utf-8').write(new_wxml)
```

---

## 七、相关资源

- 修复脚本：[`fix/replace_van_icon.py`](./fix/replace_van_icon.py)
- 涉及文件：
  - `pages/login/login.wxml`（主要修改）
  - `pages/login/login.wxss`（添加 .vi 样式）
  - `components/vant-icon/index.wxss`（图标映射来源）
- 截图：见 [`screenshots/`](./screenshots/)

---

## 八、未解决问题

⚠️ **以下问题未完全证实**：

1. **vant-icon 组件在 login 页面失败的根本原因**未完全查明
   - 怀疑是 wxss 规则冲突，但未定位到具体哪条规则
   - 建议未来单独建一个最小复现案例来研究

2. **是否其他页面也受影响**
   - 当前只发现 login 页面有问题
   - 建议全项目扫描其他页面（如 `register`、`forgot-password`）的 vant-icon 用法

3. **vant-icon 组件本身是否有 BUG**
   - 不排除是 vant-icon 组件在特定 wxss 环境下不稳定的可能性
   - 可考虑长期方案：用 text 统一替换所有 vant-icon 用法

---

## 九、后续修复记录

### 9.1 同一问题在更多页面（2026-08-08）

**新发现**：`packageVocational` 和 `packageTeacher` 包下的 3 个登录页面也存在同样的图标不显示问题。

**新增排查点**：这 3 个页面的 wxss **完全没有 `@import` vant-icon**，意味着字体加载链路都缺失：
- `vant-icon` 组件本身依赖 view + ::before 伪元素
- 即使组件能渲染，字体 `@font-face` 也没引入
- 即便加上 `@import`，组件渲染仍然不工作（推测）

**修复**：把 3 个 wxml 中所有 `<van-icon>` 替换为 `<text class="vi">真实 unicode 字符</text>`，并在 wxss 中添加 `@import` + `.vi` 样式。

涉及文件：
- `packageVocational/pages/vocational-login/vocational-login.{wxml,wxss}`（10 个图标）
- `packageTeacher/pages/open-teacher-login/open-teacher-login.{wxml,wxss}`（3 个图标）
- `packageTeacher/pages/vocational-teacher-login/vocational-teacher-login.{wxml,wxss}`（3 个图标）

### 9.2 关键教训（补充）

**`@import vant-icon` 是必须的**：任何使用 vant-icon 字体的页面（即使是 text 方式），都必须在 wxss 顶部 `@import "../../components/vant-icon/index.wxss";`，否则 `@font-face` 不会加载，字体图标全部显示为空白或乱码。

### 9.3 subPackage 路径陷阱（2026-08-08）

**问题**：在 `packageTeacher` 和 `packageVocational` 这些 subPackage 里，`@import` 路径不能用 2 个 `../`，必须用 3 个 `../../..` 才能找到主包的 `components/`。

**错误示例**（编译报错：`path not found`）：
```css
/* 在 packageTeacher/pages/open-teacher-login/open-teacher-login.wxss 中 */
@import "../../components/vant-icon/index.wxss";  /* ❌ 找不到 */
```

**正确示例**：
```css
/* subPackage 里的页面需要 3 个 ../ */
@import "../../../components/vant-icon/index.wxss";  /* ✅ */
```

**路径规则**：

| 页面位置 | `@import` 深度 |
|---------|--------------|
| `pages/xxx/xxx.wxss`（主包） | `../../components/` |
| `packageXxx/pages/xxx/xxx.wxss`（subPackage） | `../../../components/` |

**教训**：subPackage 是个独立的根目录，路径计算时要把"包根目录"也当作一层。
