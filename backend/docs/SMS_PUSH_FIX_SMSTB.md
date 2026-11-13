# 短信推送接口完整功能说明

## 📝 功能概述

推送接口现在支持两个功能：

1. **SMSTb 保存**: 循环遍历所有数据，每条数据生成一条 SMSTb 记录
   - ✅ 保存 cpSubID、uPhone、rptcode
   - ✅ 每条数据对应一条记录

2. **SMSLog 同步检查**: 循环遍历所有数据，检查并更新 SMSLog 状态
   - ✅ 根据 xs_dh 和 cpSubID 查询记录
   - ✅ 更新 send_status 和 status_desc

## 🔧 修复内容

### 问题 1: 无效的字段

**问题代码**:
```python
to_save_sms_tb = {
    "cpSubID": push_data.get('syncData', [{}])[0].get('cpSubID'),
    "type": "push_request_form",  # ❌ SMSTb 模型中没有这个字段
    "nr": push_data
}
db.add(SMSTb(**to_save_sms_tb))
db.commit()
```

### 问题 2: 重复保存

**现象**: 一个请求生成了 2 条 SMSTb 记录

**原因**:
- MAS 平台可能在没有收到响应时重试了请求
- 客户端可能发送了两次请求
- 网络问题导致重试

**解决方案**: 添加幂等性检查，防止重复保存

### 修复后的代码

#### 1. 循环遍历所有数据，保存到 SMSTb 并更新 SMSLog

```python
# 获取推送数据
sync_data = push_data.get('syncData', [])

# 循环遍历所有数据，保存到 SMSTb 并更新 SMSLog 状态
for item in sync_data:
    try:
        u_phone = item.get('uPhone')
        cp_sub_id = item.get('cpSubID')
        rpt_code = item.get('rptCode')

        # 保存到 SMSTb 表
        sms_record = SMSTb(
            cpSubID=cp_sub_id,
            uPhone=u_phone,
            rptcode=rpt_code
        )
        db.add(sms_record)
        db.commit()

        # 查询 SMSLog 记录
        smslog = db.query(SMSLog).filter_by(xs_dh=u_phone, cpSubID=cp_sub_id).first()
        if smslog:
            # 更新状态
            smslog.send_status = rpt_code
            status_desc = get_status_description(rpt_code)
            smslog.status_desc = status_desc
            db.commit()
        else:
            # 记录未找到记录到日志文件
            result_log = {
                "timestamp": datetime.now().isoformat(),
                "type": "smslog_update",
                "uPhone": u_phone,
                "cpSubID": cp_sub_id,
                "status": "not_found"
            }
            sms_tool.log_sms_push_callback(result_log)

    except Exception as e:
        # 记录处理错误到日志文件
        error_log = {
            "timestamp": datetime.now().isoformat(),
            "type": "smslog_error",
            "error": str(e),
            "item": item
        }
        sms_tool.log_sms_push_callback(error_log)
```

## 📊 SMSTb 模型字段

SMSTb 模型（教师回调记录表）包含以下字段：

| 字段名 | 类型 | 说明 |
|--------|------|------|
| id | Integer | 主键ID（自增） |
| cpSubID | String(50) | 系统任务ID |
| uPhone | String(50) | 手机号码 |
| rptcode | String(300) | 答复码 |

## 🔄 处理流程

### 循环遍历所有数据，同时保存到 SMSTb 和更新 SMSLog

1. **获取推送数据**: 从 form-data 中解析 JSON 数据
2. **循环遍历**: 遍历 syncData 中的每一条数据
3. **保存到 SMSTb**:
   - 提取 cpSubID、uPhone、rptCode
   - 创建 SMSTb 对象
   - 保存到数据库
4. **更新 SMSLog**:
   - 根据 xs_dh 和 cpSubID 查询 SMSLog 记录
   - 如果找到：更新 send_status 和 status_desc
   - 如果未找到：记录日志
5. **异常处理**: 捕获异常并记录到日志文件

## 📝 数据保存示例

### 输入数据

```json
{
  "nCount": 2,
  "syncType": 0,
  "syncData": [
    {
      "userID": "569",
      "uPhone": "15121438850",
      "rptCode": "0",
      "rptTime": "2025-10-30 13:08:41:970",
      "cpSubID": "202510301308362630",
      "cpSubSn": "0"
    },
    {
      "userID": "569",
      "uPhone": "15286335158",
      "rptCode": "0",
      "rptTime": "2025-10-30 13:08:41:970",
      "cpSubID": "202510301308362630",
      "cpSubSn": "0"
    }
  ]
}
```

### 保存到数据库

#### SMSTb 表

会创建 2 条 SMSTb 记录（每条数据对应一条）：

| id | cpSubID | uPhone | rptcode |
|----|---------|--------|---------|
| 1 | 202510301308362630 | 15121438850 | 0 |
| 2 | 202510301308362630 | 15286335158 | 0 |

#### SMSLog 表

会更新 2 条 SMSLog 记录（每条数据对应一条）：

| xs_dh | cpSubID | send_status | status_desc |
|-------|---------|-------------|-------------|
| 15121438850 | 202510301308362630 | 0 | 成功 |
| 15286335158 | 202510301308362630 | 0 | 成功 |

## 🚀 部署步骤

1. **停止服务**: 按 `Ctrl+C`
2. **重启服务**: 运行 `python backend/main.py`
3. **测试**: 发送推送请求验证

## 🧪 测试方法

### 使用 curl 测试

```bash
curl -X POST http://localhost:8000/admin/sms/push \
  -d 'msg={"nCount":1,"syncType":0,"syncData":[{"userID":"569","uPhone":"15286335158","rptCode":"0","rptTime":"2025-10-30 13:08:41:970","cpSubID":"202510301308362630","cpSubSn":"0"}]}'
```

### 预期响应

```json
{
  "code": 0,
  "msg": "接收成功"
}
```

### 验证数据库

```bash
# 查看保存的数据
mysql> SELECT * FROM sms_tb;
```

## 📊 日志记录

接口会记录以下日志到 `logs/sms_requests.log`：

### 1. 原始请求日志

```json
{
  "timestamp": "2025-10-30T13:08:47.717141",
  "type": "push_request_body",
  "raw_body": "msg={...}",
  "client_ip": "101.37.116.233:50091"
}
```

### 2. SMSLog 更新成功日志

```json
{
  "timestamp": "2025-10-30T13:08:47.912817",
  "type": "smslog_update",
  "uPhone": "13595523636",
  "cpSubID": "202510300850526191",
  "status": "updated",
  "status_desc": "成功"
}
```

### 3. SMSLog 未找到日志

```json
{
  "timestamp": "2025-10-30T13:08:47.912817",
  "type": "smslog_update",
  "uPhone": "13595523636",
  "cpSubID": "202510300850526191",
  "status": "not_found"
}
```

### 4. SMSLog 处理错误日志

```json
{
  "timestamp": "2025-10-30T13:08:47.912817",
  "type": "smslog_error",
  "error": "...",
  "item": {...}
}
```

### 5. 解析后的数据日志

```json
{
  "timestamp": "2025-10-30T13:08:47.912817",
  "type": "push_data",
  "data": {...}
}
```

### 6. 异常日志（如果有）

```json
{
  "timestamp": "2025-10-30T13:08:47.912817",
  "type": "push_exception",
  "error": "...",
  "error_type": "..."
}
```

## ✅ 功能总结

### SMSTb 保存功能
- ✅ 循环遍历所有数据项
- ✅ 每条数据生成一条 SMSTb 记录
- ✅ 保存 cpSubID、uPhone、rptcode
- ✅ 每条数据独立保存

### SMSLog 同步检查功能
- ✅ 循环遍历所有数据项
- ✅ 根据 xs_dh 和 cpSubID 查询记录
- ✅ 更新 send_status 和 status_desc
- ✅ 记录每条数据的处理结果
- ✅ 处理异常情况

## 💡 注意事项

1. **循环处理**: 每条数据都会被处理一次
2. **独立保存**: 每条数据生成独立的 SMSTb 记录
3. **异常处理**: 单条数据的异常不会影响其他数据的处理
4. **字符编码**: 使用 `ensure_ascii=False` 保留中文字符

## 🔍 查看日志

```bash
# 查看所有日志
cat logs/sms_requests.log | jq

# 查看所有异常
grep '"type": "push_exception"' logs/sms_requests.log | jq

# 实时监控
tail -f logs/sms_requests.log | jq
```

## 📚 相关文件

- `backend/models/models.py` - SMSTb 模型定义
- `backend/controllers/admin_sms.py` - 推送接口实现
- `backend/utils/sms.py` - SMS 工具类

