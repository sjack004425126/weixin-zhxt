# 短信日志查看指南

## 📝 日志文件位置

所有短信相关的日志都记录在：
```
logs/sms_requests.log
```

## 📊 日志类型

### 1. 短信发送请求
```json
{
  "timestamp": "2025-10-27T21:01:18.036639",
  "cpSubID": "task_20251027210117_b5e04cc1",
  "mobile": "15286335158",
  "content": "测试短信-小石",
  "response": "0",
  "status": "success"
}
```

### 2. 原始推送请求 ⭐ 新增
```json
{
  "timestamp": "2025-10-27T21:01:25.123456",
  "type": "raw_push_request",
  "raw_data": {
    "nCount": 1,
    "syncType": 0,
    "syncData": [
      {
        "userID": "1",
        "spNo": "10657001",
        "uPhone": "15286335158",
        "cpSubID": "task_20251027210117_b5e04cc1",
        "cpSubSn": "1",
        "rptCode": "0",
        "rptTime": "2025/10/27 21:01:25"
      }
    ]
  }
}
```

### 3. 推送状态报告
```json
{
  "timestamp": "2025-10-27T21:01:25.123456",
  "type": "status_report",
  "cpSubID": "task_20251027210117_b5e04cc1",
  "uPhone": "15286335158",
  "spNo": "10657001",
  "rptCode": "0",
  "rptTime": "2025/10/27 21:01:25",
  "status_desc": "成功"
}
```

### 4. 推送上行消息
```json
{
  "timestamp": "2025-10-27T21:05:00.123456",
  "type": "uplink_message",
  "cpSubID": "task_20251027210117_b5e04cc1",
  "uPhone": "15286335158",
  "spNo": "10657001",
  "reContent": "已收到，谢谢",
  "reTime": "2025/10/27 21:05:00"
}
```

## 🔍 查看日志的方法

### 1. 查看所有日志
```bash
cat logs/sms_requests.log
```

### 2. 查看最新的日志（实时跟踪）
```bash
tail -f logs/sms_requests.log
```

### 3. 格式化查看 JSON 日志
```bash
cat logs/sms_requests.log | jq
```

### 4. 查看特定 cpSubID 的所有日志
```bash
grep "task_20251027210117_b5e04cc1" logs/sms_requests.log | jq
```

### 5. 查看特定类型的日志

#### 查看所有原始推送请求
```bash
grep '"type": "raw_push_request"' logs/sms_requests.log | jq
```

#### 查看所有状态报告
```bash
grep '"type": "status_report"' logs/sms_requests.log | jq
```

#### 查看所有上行消息
```bash
grep '"type": "uplink_message"' logs/sms_requests.log | jq
```

### 6. 查看失败的短信
```bash
grep '"status": "failed"' logs/sms_requests.log | jq
```

### 7. 查看最后 N 行日志
```bash
tail -n 10 logs/sms_requests.log | jq
```

### 8. 统计日志数量
```bash
wc -l logs/sms_requests.log
```

## 🧪 完整测试流程

### 步骤 1: 发送短信
```bash
curl -X POST http://localhost:8000/admin/sms/send \
  -H "Content-Type: application/json" \
  -d '{
    "mobile": "15286335158",
    "content": "测试短信-小石"
  }'
```

**预期响应**:
```json
{
  "success": true,
  "message": "短信已提交，等待平台回调",
  "data": {
    "cpSubID": "task_20251027210117_b5e04cc1",
    "response": "0"
  }
}
```

**日志记录**:
```json
{
  "timestamp": "2025-10-27T21:01:18.036639",
  "cpSubID": "task_20251027210117_b5e04cc1",
  "mobile": "15286335158",
  "content": "测试短信-小石",
  "response": "0",
  "status": "success"
}
```

### 步骤 2: 查看发送日志
```bash
tail -f logs/sms_requests.log
```

### 步骤 3: 模拟推送状态报告
```bash
curl -X POST http://localhost:8000/admin/sms/push \
  -H "Content-Type: application/json" \
  -d '{
    "nCount": 1,
    "syncType": 0,
    "syncData": [
      {
        "userID": "1",
        "spNo": "10657001",
        "uPhone": "15286335158",
        "cpSubID": "task_20251027210117_b5e04cc1",
        "cpSubSn": "1",
        "rptCode": "0",
        "rptTime": "2025/10/27 21:01:25"
      }
    ]
  }'
```

**预期响应**:
```json
{
  "code": 0,
  "msg": "接收成功"
}
```

**日志记录** - 会记录两条日志：

1. 原始推送请求：
```json
{
  "timestamp": "2025-10-27T21:01:25.123456",
  "type": "raw_push_request",
  "raw_data": { ... }
}
```

2. 解析后的状态报告：
```json
{
  "timestamp": "2025-10-27T21:01:25.123456",
  "type": "status_report",
  "cpSubID": "task_20251027210117_b5e04cc1",
  ...
}
```

### 步骤 4: 查看完整的推送日志
```bash
grep "task_20251027210117_b5e04cc1" logs/sms_requests.log | jq
```

**预期输出** - 会看到 3 条日志：
1. 发送请求
2. 原始推送请求
3. 解析后的状态报告

## 💡 日志分析技巧

### 查看一条短信的完整生命周期
```bash
# 替换 cpSubID 为实际的值
CPSUBID="task_20251027210117_b5e04cc1"
grep "$CPSUBID" logs/sms_requests.log | jq
```

### 统计不同类型的日志
```bash
echo "=== 日志统计 ==="
echo "总日志数: $(wc -l < logs/sms_requests.log)"
echo "发送请求: $(grep -c '"status"' logs/sms_requests.log)"
echo "原始推送: $(grep -c '"type": "raw_push_request"' logs/sms_requests.log)"
echo "状态报告: $(grep -c '"type": "status_report"' logs/sms_requests.log)"
echo "上行消息: $(grep -c '"type": "uplink_message"' logs/sms_requests.log)"
```

### 查看最近 1 小时的日志
```bash
# 需要安装 jq
cat logs/sms_requests.log | jq 'select(.timestamp > "'$(date -d '1 hour ago' -Iseconds)'")'
```

## 🐛 故障排查

### 问题 1: 看不到日志文件
**解决方案**:
```bash
# 检查日志目录是否存在
ls -la logs/

# 如果不存在，创建目录
mkdir -p logs
```

### 问题 2: 日志文件为空
**解决方案**:
- 确保已经调用了 `/admin/sms/send` 接口
- 检查后端服务是否正常运行
- 查看后端控制台是否有错误信息

### 问题 3: 看不到推送日志
**解决方案**:
- 确保已经调用了 `/admin/sms/push` 接口
- 检查推送请求的 JSON 格式是否正确
- 查看后端控制台是否有错误信息

### 问题 4: cpSubID 不匹配
**解决方案**:
- 确保推送请求中的 cpSubID 与发送请求返回的 cpSubID 一致
- 检查是否有拼写错误

## 📚 相关文件

- 短信工具: `backend/utils/sms.py`
- 推送接口: `backend/controllers/admin_sms.py`
- 快速开始: `backend/docs/SMS_QUICK_START.md`
- 完整指南: `backend/docs/SMS_SEND_AND_PUSH_GUIDE.md`
- 统一日志: `backend/docs/SMS_UNIFIED_LOGGING.md`

