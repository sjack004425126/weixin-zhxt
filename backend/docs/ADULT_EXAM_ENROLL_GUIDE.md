# 成人高考招生简章功能说明

## 功能概述
新增"成人高考"招生简章模块，用于展示贵州开放大学黔东南分校成人高考招生简章图片。

## 前端实现

### 1. 招生简章选择页面更新
**文件**: `frontend/pages/enroll-guide/enroll-guide.wxml`
- 新增"成人高考"卡片，显示图标📖
- 卡片标题：成人高考
- 卡片副标题：Adult College Entrance Exam
- 卡片描述：贵州开放大学黔东南分校成人高考招生简章

**文件**: `frontend/pages/enroll-guide/enroll-guide.js`
- 新增 `goToAdultExam()` 方法，跳转到成人高考招生简章页面

### 2. 成人高考招生简章页面
**目录**: `frontend/pages/adult-exam-enroll/`

**文件列表**:
- `adult-exam-enroll.wxml` - 页面结构（参考 enroll 页面）
- `adult-exam-enroll.js` - 页面逻辑
- `adult-exam-enroll.wxss` - 页面样式
- `adult-exam-enroll.json` - 页面配置

**功能特性**:
- 图片轮播展示
- 左右滑动切换
- 点击图片放大预览
- 自定义指示器显示当前页码
- 快速导航按钮
- 加载状态提示
- 空状态提示

### 3. 路由注册
**文件**: `frontend/app.json`
- 在 pages 数组中添加 `pages/adult-exam-enroll/adult-exam-enroll`

## 后端实现

### API 接口
**文件**: `backend/controllers/brochure.py`

**更新内容**:
1. 在 `BROCHURE_DIRS` 字典中新增 `'adult': 'brochure/adult'`
2. 所有接口自动支持 `adult` 类型

**支持的接口**:
- `GET /brochure/list/adult` - 获取成人高考招生简章列表
- `POST /brochure/upload/adult` - 上传成人高考招生简章图片
- `DELETE /brochure/delete/adult/{filename}` - 删除指定图片
- `POST /brochure/reorder/adult` - 重新排序图片

## MinIO 存储结构

### 目录路径
```
zhpt-bucket/
  └── brochure/
      ├── open/          # 开放大学招生简章
      ├── vocational/    # 中职招生简章
      └── adult/         # 成人高考招生简章 (新增)
```

### 图片命名规则
- 文件名格式：`{纯数字}.{扩展名}`
- 示例：`1.jpg`, `2.png`, `3.jpg`
- 排序号决定显示顺序
- **重要**：只会获取纯数字命名的图片，如 `street1.png`, `cover.jpg` 等非纯数字文件名会被自动过滤

### 文件名过滤规则
系统会自动过滤以下类型的文件：
- ❌ `street1.png` - 包含字母
- ❌ `street2.png` - 包含字母
- ❌ `cover.jpg` - 包含字母
- ❌ `1a.jpg` - 包含字母
- ✅ `1.jpg` - 纯数字，会显示
- ✅ `2.png` - 纯数字，会显示
- ✅ `10.jpg` - 纯数字，会显示

## 使用说明

### 上传图片到 MinIO
1. 在 MinIO 中创建目录 `brochure/adult/`
2. 上传图片文件，命名为 `1.jpg`, `2.jpg`, `3.jpg` 等
3. 或使用后端 API 接口上传

### 测试步骤
1. 启动后端服务
2. 启动微信小程序
3. 进入"招生简章选择"页面
4. 点击"成人高考"卡片
5. 查看招生简章图片展示

## 技术栈
- 前端：微信小程序、Vant Weapp
- 后端：FastAPI、Python
- 存储：MinIO
- 样式：苹果风格设计

## 注意事项
1. 图片建议使用 JPG 或 PNG 格式
2. 图片文件名必须以数字开头（用于排序）
3. 确保 MinIO 中 `brochure/adult/` 目录存在
4. 图片访问使用签名验证，有效期 1 小时
