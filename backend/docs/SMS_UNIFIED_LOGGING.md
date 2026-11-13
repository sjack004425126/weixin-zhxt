# 短信系统 - 统一日志实现

## 📋 概述

本文档说明如何使用统一的日志文件来记录所有短信相关的操作。

## 🎯 统一日志设计

### 日志文件位置
```
logs/sms_requests.log
```

### 日志内容
所有短信相关的操作都记录在同一个文件中：
1. **短信发送请求** - 当调用 `/admin/sms/send` 时
2. **推送状态报告** - 当 MAS 平台推送状态报告时
3. **推送上行消息** - 当用户回复短信时

## 📝 日志格式

### 短信发送请求
```json
{
  "timestamp": "2025-10-27T10:00:00.123456",
  "cpSubID": "task_20251027100000_abc12345",
  "mobile": "13800138000",
  "content": "您的验证码是123456",
  "response": "0",
  "status": "success"
}
```

**字段说明**:
- `timestamp`: 发送时间
- `cpSubID`: 任务编号（用于关联）
- `mobile`: 手机号码
- `content`: 短信内容
- `response`: API 响应（0 表示成功）
- `status`: 状态（success/failed）

### 推送状态报告
```json
{
  "timestamp": "2025-10-27T10:00:05.123456",
  "type": "status_report",
  "cpSubID": "task_20251027100000_abc12345",
  "uPhone": "13800138000",
  "spNo": "10657001",
  "rptCode": "0",
  "rptTime": "2025/10/27 10:00:00",
  "status_desc": "成功"
}
```

**字段说明**:
- `timestamp`: 接收时间
- `type`: 推送类型（status_report）
- `cpSubID`: 任务编号（与发送请求关联）
- `uPhone`: 手机号码
- `spNo`: 短信平台号
- `rptCode`: 状态码（0 表示成功）
- `rptTime`: 平台报告时间
- `status_desc`: 状态描述

### 推送上行消息
```json
{
  "timestamp": "2025-10-27T10:05:00.123456",
  "type": "uplink_message",
  "cpSubID": "task_20251027100000_abc12345",
  "uPhone": "13800138000",
  "spNo": "10657001",
  "reContent": "已收到，谢谢",
  "reTime": "2025/10/27 10:05:00"
}
```

**字段说明**:
- `timestamp`: 接收时间
- `type`: 推送类型（uplink_message）
- `cpSubID`: 任务编号（与发送请求关联）
- `uPhone`: 手机号码
- `spNo`: 短信平台号
- `reContent`: 回复内容
- `reTime`: 平台回复时间

## 🔧 实现方式

### 1. SMSTool 类中的日志方法

**文件**: `backend/utils/sms.py`

#### `log_sms_request()` 方法
```python
def log_sms_request(self, cp_sub_id, mobile, content, response_text, status="pending"):
    """记录短信请求到文本文件"""
    # 记录到 logs/sms_requests.log
```

#### `log_sms_push_callback()` 方法
```python
def log_sms_push_callback(self, log_entry: dict):
    """记录短信推送回调到文本文件"""
    # 记录到 logs/sms_requests.log
```

### 2. 推送接口中的使用

**文件**: `backend/controllers/admin_sms.py`

```python
@router.post('/sms/push')
async def sms_push(request: Request):
    # ... 处理推送数据 ...
    
    # 记录状态报告
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "type": "status_report",
        "cpSubID": cp_sub_id,
        "uPhone": u_phone,
        # ... 其他字段 ...
    }
    sms_tool = SMSTool()
    sms_tool.log_sms_push_callback(log_entry)
```

## 📊 日志查看方法

### 查看所有日志
```bash
cat logs/sms_requests.log
```

### 查看最新的日志
```bash
tail -f logs/sms_requests.log
```

### 格式化查看 JSON 日志
```bash
cat logs/sms_requests.log | jq
```

### 查看特定 cpSubID 的所有日志
```bash
grep "task_20251027100000_abc12345" logs/sms_requests.log | jq
```

### 查看特定类型的日志
```bash
# 查看所有状态报告
grep '"type": "status_report"' logs/sms_requests.log | jq

# 查看所有上行消息
grep '"type": "uplink_message"' logs/sms_requests.log | jq
```

### 查看失败的短信
```bash
grep '"status": "failed"' logs/sms_requests.log | jq
```

## 🔄 日志流程

```
1. 调用 POST /admin/sms/send
   ↓
2. SMSTool.send_sms() 生成 cpSubID
   ↓
3. SMSTool.log_sms_request() 记录发送请求
   ↓
4. 返回 cpSubID 给客户端
   ↓
5. MAS 平台处理短信
   ↓
6. MAS 推送状态报告到 POST /admin/sms/push
   ↓
7. sms_push() 调用 SMSTool.log_sms_push_callback()
   ↓
8. 记录状态报告到 logs/sms_requests.log
   ↓
9. 返回 code=0 给 MAS 平台
   ↓
10. 用户回复短信
    ↓
11. MAS 推送上行消息到 POST /admin/sms/push
    ↓
12. sms_push() 调用 SMSTool.log_sms_push_callback()
    ↓
13. 记录上行消息到 logs/sms_requests.log
    ↓
14. 返回 code=0 给 MAS 平台
```

## 💡 优势

### 1. 统一管理
- 所有日志在一个文件中
- 便于查看和分析
- 易于备份和归档

### 2. 易于追踪
- 使用 cpSubID 关联所有相关日志
- 可以追踪一条短信的完整生命周期
- 便于故障排查

### 3. 易于分析
- JSON 格式便于解析
- 可以用各种工具进行分析
- 便于生成报表

### 4. 易于集成
- 统一的日志接口
- 便于后续集成到数据库
- 便于集成到日志系统

## 🚀 后续步骤

### 1. 测试日志功能
```bash
python backend/tests/test_sms_send_and_push.py
```

### 2. 查看日志文件
```bash
cat logs/sms_requests.log | jq
```

### 3. 验证 cpSubID 关联
```bash
# 查看一条短信的完整生命周期
grep "task_20251027100000_abc12345" logs/sms_requests.log | jq
```

### 4. 迁移到数据库
当测试完成后，可以将日志数据导入数据库。

## 📚 相关文件

- 短信工具: `backend/utils/sms.py`
- 推送接口: `backend/controllers/admin_sms.py`
- 测试脚本: `backend/tests/test_sms_send_and_push.py`
- 快速开始: `backend/docs/SMS_QUICK_START.md`
- 完整指南: `backend/docs/SMS_SEND_AND_PUSH_GUIDE.md`

