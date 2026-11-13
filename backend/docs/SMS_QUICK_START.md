# 短信发送和推送 - 快速开始

## 🚀 5分钟快速开始

### 1️⃣ 启动服务
```bash
python backend/main.py
```

### 2️⃣ 发送短信
```bash
curl -X POST http://localhost:8000/admin/sms/send \
  -H "Content-Type: application/json" \
  -d '{
    "mobile": "13800138000",
    "content": "您的验证码是123456"
  }'
```

**响应**:
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

**保存 cpSubID**: `task_20251027100000_abc12345`

### 3️⃣ 模拟推送状态报告
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

**响应**:
```json
{
  "code": 0,
  "msg": "接收成功"
}
```

### 4️⃣ 查看日志
```bash
# 查看统一日志文件（包含所有短信相关的日志）
cat logs/sms_requests.log

# 或者用 tail 查看最新的日志
tail -f logs/sms_requests.log

# 用 jq 格式化查看 JSON 日志
cat logs/sms_requests.log | jq
```

## 📝 日志格式

### sms_requests.log（统一日志文件）

**短信发送请求**:
```json
{"timestamp": "2025-10-27T10:00:00.123456", "cpSubID": "task_20251027100000_abc12345", "mobile": "13800138000", "content": "您的验证码是123456", "response": "0", "status": "success"}
```

**推送状态报告**:
```json
{"timestamp": "2025-10-27T10:00:05.123456", "type": "status_report", "cpSubID": "task_20251027100000_abc12345", "uPhone": "13800138000", "rptCode": "0", "status_desc": "成功"}
```

**推送上行消息**:
```json
{"timestamp": "2025-10-27T10:00:10.123456", "type": "uplink_message", "cpSubID": "task_20251027100000_abc12345", "uPhone": "13800138000", "reContent": "已收到"}
```

## 🧪 运行完整测试
```bash
python backend/tests/test_sms_send_and_push.py
```

## 📊 关键概念

| 概念 | 说明 |
|------|------|
| **cpSubID** | 任务编号，用于关联发送和回调 |
| **syncType=0** | 状态报告（短信发送结果） |
| **syncType=1** | 上行消息（用户回复） |
| **rptCode** | 状态码（0=成功，其他=失败） |

## 🔗 API 端点

| 方法 | 端点 | 说明 |
|------|------|------|
| POST | `/admin/sms/send` | 发送短信 |
| POST | `/admin/sms/push` | 接收推送回调 |

## 📂 文件位置

| 文件 | 位置 |
|------|------|
| 短信工具 | `backend/utils/sms.py` |
| 推送接口 | `backend/controllers/admin_sms.py` |
| 测试脚本 | `backend/tests/test_sms_send_and_push.py` |
| 统一日志文件 | `logs/sms_requests.log` |

## ✅ 测试清单

- [ ] 启动服务
- [ ] 发送短信（获取 cpSubID）
- [ ] 推送状态报告（成功）
- [ ] 推送状态报告（失败 - 黑名单）
- [ ] 推送上行消息
- [ ] 查看日志文件
- [ ] 运行完整测试脚本

## 🎯 下一步

1. **验证日志**: 检查 `logs/` 目录中的日志文件
2. **测试不同场景**: 修改 rptCode 测试不同的状态码
3. **集成到业务**: 在您的业务代码中调用 `/admin/sms/send`
4. **迁移到数据库**: 测试完成后恢复数据库模式

## 📞 常见错误

| 错误 | 原因 | 解决 |
|------|------|------|
| 手机号无效 | 格式不对 | 使用 13-19 开头的11位号码 |
| cpSubID 不匹配 | 推送时用错了ID | 确保使用发送时返回的ID |
| 推送失败 | 参数不完整 | 检查 nCount, syncType, syncData |

## 💡 提示

- 每次发送都会生成新的 cpSubID
- 推送时必须使用对应的 cpSubID
- 日志文件是纯文本，每行一条JSON记录
- 可以用 `jq` 工具格式化查看日志：`cat logs/sms_requests.log | jq`

## 📚 详细文档

- 完整指南: `backend/docs/SMS_SEND_AND_PUSH_GUIDE.md`
- 推送接口: `backend/docs/SMS_PUSH_INTERFACE_GUIDE.md`
- 状态码: `backend/utils/sms_status_codes.py`

