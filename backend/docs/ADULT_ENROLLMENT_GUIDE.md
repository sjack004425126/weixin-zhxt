# 成人高等教育报名系统使用指南

## 功能概述

成人高等教育2025年预报名系统，支持用户在线填写报名信息，包括：
1. 姓名
2. 手机号
3. 意向专业及费用明细
4. 学习中心选择

## 页面流程

### 1. 进入页面
- 自动弹出招生简章弹窗
- 用户必须滑动到底部阅读完整内容
- 点击"我已阅读"按钮关闭弹窗

### 2. 填写表单
- 输入姓名（必填）
- 输入手机号（必填，11位数字）
- 选择意向专业（必选，显示学费信息）
- 选择学习中心（必选）

### 3. 提交报名
- 所有必填项填写完成后，提交按钮激活
- 点击提交，数据保存到 `zs_adult_enrollment` 表
- 提交成功后显示提示信息

## 技术实现

### 前端页面
- **路径**: `frontend/pages/adult-exam-enroll/`
- **文件**:
  - `adult-exam-enroll.wxml` - 页面结构
  - `adult-exam-enroll.js` - 页面逻辑
  - `adult-exam-enroll.wxss` - 页面样式
  - `adult-exam-enroll.json` - 页面配置

### 后端接口
- **文件**: `backend/controllers/adult_enrollment.py`
- **接口列表**:

#### 1. 获取招生简章
```
GET /enrollment/prospectus?code=adult_exam
```
返回招生类别的招生简章（富文本HTML）

#### 2. 获取字典列表
```
GET /enrollment/dict_list?category_code=adult_exam&type=zyyx
GET /enrollment/dict_list?category_code=adult_exam&type=xxzx
```
返回专业列表（zyyx）或学习中心列表（xxzx）

#### 3. 提交报名
```
POST /enrollment/adult_submit
```
请求体：
```json
{
  "name": "张三",
  "phone": "13800138000",
  "major_code": "computer_science",
  "learning_center_code": "center_beijing",
  "wx_openid": "xxx",
  "wx_nickname": "微信昵称",
  "wx_headimgurl": "头像URL"
}
```

#### 4. 检查是否已报名
```
GET /enrollment/adult_check?phone=13800138000
```
检查手机号是否已经报名

### 数据库表

#### zs_category - 招生类别表
存储招生简章（prospectus字段）

#### zs_dict - 通用字典表
存储专业、学习中心等字典数据

#### zs_adult_enrollment - 成人教育报名表
存储报名信息

## 富文本图片处理

参考 `photo-upload` 页面的实现方式：

1. **图片自适应**
   ```javascript
   html.replace(
     /<img([^>]*)>/gi,
     '<img$1 style="max-width:100%;height:auto;display:block;margin:20rpx 0;">'
   );
   ```

2. **相对路径处理**
   ```javascript
   processed.replace(
     /src="(?!http|https|data:)([^"]*)"/gi,
     (match, p1) => {
       const baseUrl = getApp().globalData.baseUrl || '';
       return `src="${baseUrl}${p1}"`;
     }
   );
   ```

3. **rich-text组件渲染**
   ```xml
   <rich-text nodes="{{processedProspectus}}" />
   ```

## 样式特点

1. **渐变色主题**: 使用紫色渐变 (#667eea → #764ba2)
2. **卡片式设计**: 圆角、阴影效果
3. **响应式交互**: 按钮点击动画、表单聚焦效果
4. **滚动提示**: 招生简章未读完时显示滚动提示动画

## 注意事项

1. **防重复提交**: 同一手机号只能报名一次
2. **表单验证**: 
   - 姓名不能为空
   - 手机号必须是11位数字
   - 专业和学习中心必须选择
3. **招生简章**: 必须滑动到底部才能关闭弹窗
4. **图片处理**: 富文本中的图片自动适配屏幕宽度

## 页面配置

在 `app.json` 中添加页面路径：
```json
{
  "pages": [
    "pages/adult-exam-enroll/adult-exam-enroll"
  ]
}
```

## 测试步骤

1. 确保数据库表已创建
2. 在 `zs_category` 表中添加招生类别数据
3. 在 `zs_dict` 表中添加专业和学习中心数据
4. 访问页面测试完整流程
5. 检查 `zs_adult_enrollment` 表中的数据

## 数据初始化

参考 `backend/docs/ZS_DATABASE_SCHEMA_MSSQL.sql` 文件中的初始化数据部分。
