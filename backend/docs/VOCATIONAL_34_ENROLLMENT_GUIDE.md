# 3+4中本贯通报名系统使用指南

## 功能概述

本系统用于"3+4"中本贯通培养舞蹈表演专业面试考生报名登记。

## 数据库表

### zs_vocational34_enrollment

存储3+4报名信息的主表，包含以下字段：

#### 基本信息
- `id`: 主键ID
- `serial_number`: 序号（自动生成，格式：V34000001）
- `name`: 学生姓名（必填）
- `admission_ticket_no`: 准考证号
- `gender`: 性别（male/female，必填）
- `nation`: 民族代码
- `id_card`: 身份证号码（必填）
- `junior_school_name`: 原初中毕业学校全称
- `junior_school_county`: 原初中毕业学校所在县份
- `is_qdn_graduate`: 是否黔东南州的2025年应届初中毕业生（1-是，0-否）

#### 籍贯信息
- `household_type`: 户口性质（agricultural/non_agricultural）
- `household_province`: 户籍省份
- `household_city`: 户籍城市
- `household_district`: 户籍区县
- `household_address`: 户籍详细地址
- `residence_province`: 实际居住省份
- `residence_city`: 实际居住城市
- `residence_district`: 实际居住区县
- `residence_address`: 实际居住详细地址

#### 联系方式
- `phone`: 手机号（必填）

#### 监护人信息
- `guardian_name`: 监护人姓名
- `guardian_phone`: 监护人联系方式
- `guardian_relation`: 监护人身份（father/mother/other）

#### 证件照片（存储URL路径）
- `id_card_front_url`: 身份证正面照片URL
- `id_card_back_url`: 身份证反面照片URL
- `photo_url`: 标准证件照URL
- `consent_letter_url`: 知情同意书照片URL

#### 确认信息
- `is_confirmed`: 知情确认（1-已确认，0-未确认）
- `signature_base64`: 考生签名（base64编码，必填）

#### 状态信息
- `status`: 状态（0-待审核，1-审核通过，2-审核不通过，3-已录取）
- `batch`: 批次
- `submit_time`: 提交时间
- `audit_time`: 审核时间
- `auditor_id`: 审核人ID
- `audit_remark`: 审核备注

#### 微信信息
- `wx_openid`: 微信openid
- `wx_nickname`: 微信昵称
- `wx_headimgurl`: 微信头像

## API 接口

### 1. 获取招生简章

```
GET /vocational34/prospectus
```

返回：
```json
{
  "code": "vocational_34",
  "name": "3+4中本贯通",
  "description": "描述",
  "prospectus": "招生简章HTML内容",
  "start_time": "2025-01-01T00:00:00",
  "end_time": "2025-12-31T23:59:59",
  "batch": 1
}
```

### 2. 获取字典列表

```
GET /vocational34/dict_list?type=nation
```

参数：
- `type`: 字典类型（nation-民族）
- `parent_code`: 父级编码（可选）

返回：
```json
[
  {
    "id": 1,
    "code": "han",
    "label": "汉族",
    "parent_code": null,
    "sort_order": 0,
    "remark": "",
    "extra_data": ""
  }
]
```

### 3. 提交报名信息

```
POST /vocational34/submit
```

请求体：
```json
{
  "name": "张三",
  "admission_ticket_no": "202501001",
  "gender": "male",
  "nation": "han",
  "id_card": "520000199001011234",
  "junior_school_name": "某某中学",
  "junior_school_county": "某某县",
  "is_qdn_graduate": 1,
  "household_type": "agricultural",
  "household_province": "贵州省",
  "household_city": "黔东南苗族侗族自治州",
  "household_district": "凯里市",
  "household_address": "某某街道某某号",
  "residence_province": "贵州省",
  "residence_city": "黔东南苗族侗族自治州",
  "residence_district": "凯里市",
  "residence_address": "某某街道某某号",
  "phone": "13800138000",
  "guardian_name": "李四",
  "guardian_phone": "13900139000",
  "guardian_relation": "father",
  "id_card_front_url": "/uploads/id_card_front.jpg",
  "id_card_back_url": "/uploads/id_card_back.jpg",
  "photo_url": "/uploads/photo.jpg",
  "consent_letter_url": "/uploads/consent.jpg",
  "is_confirmed": 1,
  "signature_base64": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA...",
  "wx_openid": "oxxxxxxxxxxxxxx",
  "wx_nickname": "微信昵称",
  "wx_headimgurl": "https://..."
}
```

返回：
```json
{
  "success": true,
  "message": "报名成功",
  "id": 1,
  "serial_number": "V34000001"
}
```

### 4. 检查报名状态

```
GET /vocational34/check?id_card=520000199001011234
```

参数：
- `id_card`: 身份证号

返回：
```json
{
  "has_enrolled": true,
  "enrollment": {
    "id": 1,
    "serial_number": "V34000001",
    "name": "张三",
    "id_card": "520000199001011234",
    "status": 0,
    "submit_time": "2025-01-01T10:00:00"
  }
}
```

## 前端页面

### 页面路径
```
frontend/pages/three-plus-four-register/
```

### 页面功能

1. **招生简章展示**
   - 弹窗形式展示
   - 必须滚动到底部才能关闭
   - 支持富文本内容

2. **表单填写**
   - 考生基本信息
   - 籍贯信息（使用微信原生地区选择器）
   - 联系方式
   - 监护人信息
   - 证件照片上传（4张）
   - 知情确认
   - 手写签名

3. **表单验证**
   - 必填项验证
   - 手机号格式验证
   - 身份证号格式验证
   - 重复报名检查

4. **数据提交**
   - 图片上传到服务器，存储URL
   - 签名使用base64编码直接存储
   - 自动获取微信用户信息

## 测试步骤

### 1. 准备测试数据

在 `zs_category` 表中插入测试数据：

```sql
INSERT INTO zs_category (code, name, description, prospectus, is_active, start_time, end_time, batch)
VALUES (
  'vocational_34',
  '3+4中本贯通',
  '3+4中本贯通培养舞蹈表演专业面试考生报名',
  '<h1>招生简章</h1><p>这是招生简章内容...</p>',
  1,
  '2025-01-01 00:00:00',
  '2025-12-31 23:59:59',
  1
);
```

在 `zs_dict` 表中插入民族字典数据：

```sql
-- 获取 category_id
SELECT id FROM zs_category WHERE code = 'vocational_34';

-- 插入民族数据（假设 category_id = 2）
INSERT INTO zs_dict (category_id, type, code, label, sort_order, is_active)
VALUES 
  (2, 'nation', 'han', '汉族', 1, 1),
  (2, 'nation', 'miao', '苗族', 2, 1),
  (2, 'nation', 'dong', '侗族', 3, 1),
  (2, 'nation', 'buyi', '布依族', 4, 1);
```

### 2. 启动后端服务

```bash
cd backend
python main.py
```

### 3. 测试前端页面

1. 在微信开发者工具中打开小程序
2. 导航到 3+4 报名页面
3. 阅读招生简章
4. 填写表单信息
5. 上传证件照片
6. 完成手写签名
7. 提交报名

### 4. 验证数据

查询数据库确认数据已正确保存：

```sql
SELECT * FROM zs_vocational34_enrollment ORDER BY id DESC LIMIT 1;
```

## 注意事项

1. **图片上传**
   - 需要实现 `/api/upload/image` 接口
   - 返回格式：`{"url": "/uploads/xxx.jpg"}`
   - 图片大小限制：10MB

2. **签名处理**
   - 签名使用 base64 编码
   - 格式：`data:image/png;base64,iVBORw0KGgo...`
   - 直接存储到数据库，不需要上传

3. **地区选择**
   - 使用微信原生 `<picker mode="region">`
   - 自动返回省/市/区数组
   - 分别存储到对应字段

4. **表单验证**
   - 必填项：姓名、性别、身份证号、手机号、知情确认、签名
   - 身份证号：18位
   - 手机号：11位，1开头

5. **重复报名检查**
   - 根据身份证号判断
   - 提交前检查是否已报名

## 常见问题

### Q1: 图片上传失败
A: 检查上传接口是否正常，确认文件大小是否超限

### Q2: 签名无法保存
A: 检查签名组件是否正确触发 submit 事件

### Q3: 地区选择器不显示
A: 确认使用的是 `<picker mode="region">`

### Q4: 提交时提示"该身份证号已经报名"
A: 检查数据库中是否已存在相同身份证号的记录

## 后续优化建议

1. 添加图片压缩功能
2. 添加身份证OCR识别
3. 添加报名进度查询
4. 添加报名信息修改功能
5. 添加管理后台审核功能
