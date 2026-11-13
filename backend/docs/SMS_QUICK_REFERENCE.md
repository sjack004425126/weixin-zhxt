# MAS短信平台推送接口 - 快速参考

## 🎯 一句话总结

**MAS短信平台会主动推送短信发送结果和用户回复到您的系统**

## 📍 接口地址

```
POST /admin/sms/push
```

## 📤 推送类型

### 状态报告 (syncType=0)
短信平台推送短信发送结果

### 上行消息 (syncType=1)
短信平台推送用户回复的短信

## 📥 请求示例

### 状态报告
```json
{
  "nCount": 1,
  "syncType": 0,
  "syncData": [{
    "cpSubID": "task_001",
    "uPhone": "13800000001",
    "rptCode": "0",
    "rptTime": "2025/10/27 10:00:00"
  }]
}
```

### 上行消息
```json
{
  "nCount": 1,
  "syncType": 1,
  "syncData": [{
    "cpSubID": "task_001",
    "uPhone": "13800000001",
    "reContent": "用户回复",
    "reTime": "2025/10/27 10:05:00"
  }]
}
```

## 📤 响应示例

**必须返回**:
```json
{
  "code": 0,
  "msg": "接收成功"
}
```

## 🔑 关键字段

| 字段 | 说明 | 必需 |
|------|------|------|
| nCount | 推送数量 | 是 |
| syncType | 推送类型 (0/1) | 是 |
| cpSubID | 任务编号 | 是 |
| uPhone | 手机号码 | 是 |
| rptCode | 状态码 | 是 |
| reContent | 回复内容 | 是 |

## ✅ 状态码

| 码 | 说明 |
|----|------|
| 0 | 成功 |
| MX:0013 | 黑名单 |
| MX:0004 | 敏感词 |
| MN00001 | 空号 |
| DB00108 | 欠费 |

## 🚀 配置步骤

1. 在MAS平台配置推送地址
2. 启动您的系统
3. 测试推送

## 🧪 测试命令

```bash
curl -X POST http://localhost:8000/admin/sms/push \
  -H "Content-Type: application/json" \
  -d '{
    "nCount": 1,
    "syncType": 0,
    "syncData": [{
      "cpSubID": "test_001",
      "uPhone": "13800000001",
      "rptCode": "0",
      "rptTime": "2025/10/27 10:00:00"
    }]
  }'
```

## 📊 数据库表

表名: `oa_t_sms`

关键字段:
- `cpSubID`: 任务编号
- `xs_dh`: 手机号码
- `send_status`: 状态码
- `status_desc`: 状态描述
- `nr`: 短信内容/回复内容
- `fssj`: 时间

## ⚠️ 重要提示

1. **响应必须是 code=0**，否则平台会重试
2. **cpSubID 用于关联**，必须与提交时一致
3. **有效期 72 小时**，超期推送会被丢弃
4. **重试 3 次**，失败后放弃

## 📞 常见错误

| 错误 | 原因 | 解决 |
|------|------|------|
| 推送未收到 | 地址配置错误 | 检查MAS平台配置 |
| 平台重试 | 响应格式错误 | 返回 `{"code": 0}` |
| 数据丢失 | 数据库错误 | 检查表结构 |

## 📚 详细文档

- 完整指南: `SMS_PUSH_INTERFACE_GUIDE.md`
- API文档: `SMS_CALLBACK_API.md`
- 测试脚本: `backend/tests/test_sms_callback.py`

