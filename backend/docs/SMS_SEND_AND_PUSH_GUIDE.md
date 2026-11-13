# 短信发送和推送接口使用指南

## 📋 概述

本指南介绍如何使用新的短信发送接口和推送回调接口。系统采用**测试模式**，所有数据都记录到文本文件中，便于调试和验证。

## 🎯 工作流程

```
1. 调用发送接口 → 获取 cpSubID
   POST /admin/sms/send
   
2. 短信平台处理短信
   
3. 短信平台推送状态报告 → 记录到日志文件
   POST /admin/sms/push (syncType=0)
   
4. 用户回复短信
   
5. 短信平台推送上行消息 → 记录到日志文件
   POST /admin/sms/push (syncType=1)
```

## 📤 发送短信接口

### 接口地址
```
POST /admin/sms/send
```

### 请求参数

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| mobile | string | 是 | 手机号码（单个或逗号分隔多个） |
| content | string | 是 | 短信内容 |

### 请求示例

```bash
curl -X POST http://localhost:8000/admin/sms/send \
  -H "Content-Type: application/json" \
  -d '{
    "mobile": "13800138000",
    "content": "您的验证码是123456，请勿泄露"
  }'
```

### 响应示例

**成功响应**:
```json
{
  "success": true,
  "message": "短信已提交，等待平台回调",
  "data": {
    "cpSubID": "task_20251027100000_abc12345",
    "response": "0"
  }
}
```

**失败响应**:
```json
{
  "success": false,
  "message": "无效的手机号码格式: 12345",
  "data": null
}
```

### 关键字段说明

- **cpSubID**: 任务编号，用于关联短信发送和回调
  - 格式: `task_YYYYMMDDHHmmss_xxxxxxxx`
  - 示例: `task_20251027100000_abc12345`
  - **重要**: 保存此ID，用于后续的推送回调匹配

## 📥 推送回调接口

### 接口地址
```
POST /admin/sms/push
```

### 推送类型

#### 1. 状态报告 (syncType=0)

**用途**: 接收短信发送结果

**请求示例**:
```json
{
  "nCount": 1,
  "syncType": 0,
  "syncData": [{
    "userID": "1",
    "spNo": "10657001",
    "uPhone": "13800138000",
    "cpSubID": "task_20251027100000_abc12345",
    "cpSubSn": "1",
    "rptCode": "0",
    "rptTime": "2025/10/27 10:00:00"
  }]
}
```

**状态码说明**:
- `0`: 成功
- `MX:0013`: 黑名单
- `MX:0004`: 敏感词
- `MN00001`: 空号
- `DB00108`: 欠费
- 其他: 见 `backend/utils/sms_status_codes.py`

#### 2. 上行消息 (syncType=1)

**用途**: 接收用户回复的短信

**请求示例**:
```json
{
  "nCount": 1,
  "syncType": 1,
  "syncData": [{
    "userID": "1",
    "spNo": "10657001",
    "uPhone": "13800138000",
    "cpSubID": "task_20251027100000_abc12345",
    "reContent": "已收到，谢谢",
    "reTime": "2025/10/27 10:05:00"
  }]
}
```

### 响应格式

**必须返回**:
```json
{
  "code": 0,
  "msg": "接收成功"
}
```

## 📝 日志文件

### 统一日志文件
**文件**: `logs/sms_requests.log`

**说明**: 所有短信相关的日志都记录在同一个文件中，包括：
- 短信发送请求
- 推送状态报告
- 推送上行消息

**格式**: 每行一条JSON记录

### 日志示例

#### 短信发送请求
```json
{"timestamp": "2025-10-27T10:00:00.123456", "cpSubID": "task_20251027100000_abc12345", "mobile": "13800138000", "content": "您的验证码是123456", "response": "0", "status": "success"}
```

#### 推送状态报告
```json
{"timestamp": "2025-10-27T10:00:05.123456", "type": "status_report", "cpSubID": "task_20251027100000_abc12345", "uPhone": "13800138000", "spNo": "10657001", "rptCode": "0", "rptTime": "2025/10/27 10:00:00", "status_desc": "成功"}
```

#### 推送上行消息
```json
{"timestamp": "2025-10-27T10:05:00.123456", "type": "uplink_message", "cpSubID": "task_20251027100000_abc12345", "uPhone": "13800138000", "spNo": "10657001", "reContent": "已收到，谢谢", "reTime": "2025/10/27 10:05:00"}
```

## 🧪 测试

### 运行完整测试

```bash
python backend/tests/test_sms_send_and_push.py
```

### 手动测试

#### 1. 发送短信
```bash
curl -X POST http://localhost:8000/admin/sms/send \
  -H "Content-Type: application/json" \
  -d '{
    "mobile": "13800138000",
    "content": "测试短信"
  }'
```

#### 2. 模拟推送状态报告
```bash
curl -X POST http://localhost:8000/admin/sms/push \
  -H "Content-Type: application/json" \
  -d '{
    "nCount": 1,
    "syncType": 0,
    "syncData": [{
      "userID": "1",
      "spNo": "10657001",
      "uPhone": "13800138000",
      "cpSubID": "task_20251027100000_abc12345",
      "cpSubSn": "1",
      "rptCode": "0",
      "rptTime": "2025/10/27 10:00:00"
    }]
  }'
```

#### 3. 模拟推送上行消息
```bash
curl -X POST http://localhost:8000/admin/sms/push \
  -H "Content-Type: application/json" \
  -d '{
    "nCount": 1,
    "syncType": 1,
    "syncData": [{
      "userID": "1",
      "spNo": "10657001",
      "uPhone": "13800138000",
      "cpSubID": "task_20251027100000_abc12345",
      "reContent": "已收到",
      "reTime": "2025/10/27 10:05:00"
    }]
  }'
```

## 🔄 从测试模式迁移到数据库模式

当测试完成后，按以下步骤迁移到数据库模式：

### 1. 恢复备份的推送接口
```bash
# 恢复之前备份的 admin_sms.py
git checkout backend/controllers/admin_sms.py
```

### 2. 确保数据库表存在
```sql
ALTER TABLE oa_t_sms ADD COLUMN send_status INT;
ALTER TABLE oa_t_sms ADD COLUMN status_desc TEXT;
```

### 3. 重启服务
```bash
python backend/main.py
```

## 📊 数据流图

```
┌─────────────────┐
│  您的系统       │
└────────┬────────┘
         │
         │ 1. POST /admin/sms/send
         │    (mobile, content)
         ▼
┌─────────────────────────────────┐
│  SMSTool.send_sms()             │
│  - 生成 cpSubID                 │
│  - 调用 MAS API                 │
│  - 记录到 sms_requests.log      │
└────────┬────────────────────────┘
         │
         │ 返回 cpSubID
         │
         ▼
┌─────────────────┐
│  MAS短信平台    │
│  - 处理短信     │
│  - 发送短信     │
└────────┬────────┘
         │
         │ 2. POST /admin/sms/push
         │    (syncType=0, 状态报告)
         ▼
┌──────────────────────────────────┐
│  sms_push() 推送接口             │
│  - 验证参数                      │
│  - 记录到 sms_push_callbacks.log │
│  - 返回 code=0                   │
└──────────────────────────────────┘
         │
         │ 用户回复短信
         │
         ▼
┌─────────────────┐
│  MAS短信平台    │
└────────┬────────┘
         │
         │ 3. POST /admin/sms/push
         │    (syncType=1, 上行消息)
         ▼
┌──────────────────────────────────┐
│  sms_push() 推送接口             │
│  - 验证参数                      │
│  - 记录到 sms_push_callbacks.log │
│  - 返回 code=0                   │
└──────────────────────────────────┘
```

## ⚠️ 常见问题

### Q: 如何查看发送的短信？
A: 查看 `logs/sms_requests.log` 文件，每行是一条JSON记录。

### Q: 如何查看推送回调？
A: 查看 `logs/sms_push_callbacks.log` 文件，每行是一条JSON记录。

### Q: cpSubID 的作用是什么？
A: 用于关联发送请求和推送回调。发送时生成，推送时返回，用于匹配。

### Q: 如何测试不同的状态码？
A: 在推送接口中修改 `rptCode` 字段，例如：
- `"rptCode": "0"` - 成功
- `"rptCode": "MX:0013"` - 黑名单
- `"rptCode": "MN00001"` - 空号

### Q: 日志文件在哪里？
A: 在项目根目录的 `logs/` 文件夹中。

## 📚 相关文件

- 短信工具类: `backend/utils/sms.py`
- 推送接口: `backend/controllers/admin_sms.py`
- 测试脚本: `backend/tests/test_sms_send_and_push.py`
- 状态码: `backend/utils/sms_status_codes.py`

