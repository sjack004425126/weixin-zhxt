# MAS短信平台推送接口实现指南

## 📋 文档分析总结

根据 **MAS短信平台HTTP自有接口1.5最新.docx** 文档分析，该接口是**推送型接口**，而非回调型接口。

### 🔄 接口流程

```
您的系统                    MAS短信平台
   |                            |
   |--1. 提交短信请求---------->|
   |                            |
   |<--2. 返回提交结果----------|
   |                            |
   |                    (处理短信)
   |                            |
   |<--3. 推送状态报告---------|
   |                            |
   |--4. 返回接收确认-------->|
   |                            |
   |<--5. 推送上行消息---------|
   |                            |
   |--6. 返回接收确认-------->|
```

## 🎯 核心区别

| 特性 | 回调接口 | 推送接口 |
|------|--------|--------|
| **方向** | 您的系统 → 平台 | 平台 → 您的系统 |
| **主动方** | 您的系统 | 短信平台 |
| **触发方式** | 您主动查询 | 平台主动推送 |
| **实现方式** | 轮询 | 事件驱动 |

## 📊 推送接口详解

### 1. 状态报告推送 (syncType=0)

**用途**: 接收短信发送结果

**请求格式**:
```json
{
  "nCount": 2,
  "syncType": 0,
  "syncData": [
    {
      "userID": "1",
      "spNo": "10657001",
      "uPhone": "13800000001",
      "cpSubID": "14100817343197985",
      "cpSubSn": "1",
      "rptCode": "0",
      "rptTime": "2014/10/8 17:34:31"
    }
  ]
}
```

**关键字段**:
- `cpSubID`: 您提交短信时的任务编号（用于关联）
- `rptCode`: 状态码（0=成功，其他=失败）
- `rptTime`: 回执时间

### 2. 上行消息推送 (syncType=1)

**用途**: 接收用户回复的短信

**请求格式**:
```json
{
  "nCount": 1,
  "syncType": 1,
  "syncData": [
    {
      "userID": "1",
      "spNo": "10657001",
      "uPhone": "13800000001",
      "cpSubID": "14100817343197985",
      "reContent": "用户回复内容",
      "reTime": "2014/10/8 18:35:43"
    }
  ]
}
```

**关键字段**:
- `cpSubID`: 原始任务编号
- `reContent`: 用户回复的内容
- `reTime`: 回复时间

## ✅ 响应要求

**必须返回以下格式，短信平台才会认为接收成功：**

```json
{
  "code": 0,
  "msg": "接收成功"
}
```

### 重要说明

1. **响应格式严格**：短信平台根据 `code` 字段判断是否接收成功
2. **code=0 表示成功**：其他值表示失败，平台会重试
3. **重试机制**：如果您的系统响应超时或返回错误，平台会重试3次
4. **有效期**：推送有效期为72小时

## 🔧 实现要点

### 1. 配置推送地址

在MAS短信平台管理后台配置：
```
http://your-domain.com/admin/sms/push
```

### 2. 接收推送

您的系统需要实现一个 POST 接口来接收推送：

```python
@router.post('/admin/sms/push')
async def sms_push(request: Request, db: Session = DatabaseDep):
    # 1. 解析JSON数据
    push_data = await request.json()
    
    # 2. 提取参数
    n_count = push_data.get('nCount')
    sync_type = push_data.get('syncType')
    sync_data = push_data.get('syncData', [])
    
    # 3. 处理数据
    for item in sync_data:
        if sync_type == 0:
            # 处理状态报告
            handle_status_report(item, db)
        elif sync_type == 1:
            # 处理上行消息
            handle_uplink_message(item, db)
    
    # 4. 返回成功响应
    return {'code': 0, 'msg': '接收成功'}
```

### 3. 关键字段映射

| 文档字段 | 数据库字段 | 说明 |
|---------|----------|------|
| cpSubID | cpSubID | 任务编号（关键） |
| uPhone | xs_dh | 手机号码 |
| spNo | spNo | 服务号码 |
| rptCode | send_status | 状态码 |
| rptTime | fssj | 时间 |
| reContent | nr | 回复内容 |

## 📝 状态码列表

| 状态码 | 说明 |
|--------|------|
| 0 | 成功 |
| MX:1315 | 号段错误 |
| MX:0003 | 单个号码当天下发条数超过上限 |
| MX:0004 | 短信内容包含敏感词 |
| MX:0005 | 模板无法匹配 |
| MX:0008 | 签名无法匹配通道 |
| MX:0013 | 黑名单 |
| MX:0014 | 省份屏蔽 |
| MX:0020 | 单个号码相同内容超过上限 |
| MX:0021 | 单个号码当天下发条数超过上限(同个平台) |
| MN00001 | 空号 |
| DB00107 | 业务代码错误或产品未建立 |
| DB00108 | 欠费或投诉关停 |
| DB00140 | 号码不在白名单中 |
| DB00143 | 提交超限 |

## 🧪 测试

运行测试脚本：
```bash
python backend/tests/test_sms_callback.py
```

## 📚 相关文件

- 接口实现: `backend/controllers/admin_sms.py`
- API文档: `backend/docs/SMS_CALLBACK_API.md`
- 测试脚本: `backend/tests/test_sms_callback.py`
- 状态码: `backend/utils/sms_status_codes.py`
- 配置文件: `backend/utils/sms_callback_config.py`

## 🚀 部署步骤

1. **确保数据库表存在**
   ```sql
   ALTER TABLE oa_t_sms ADD COLUMN send_status INT;
   ALTER TABLE oa_t_sms ADD COLUMN status_desc TEXT;
   ```

2. **启动后端服务**
   ```bash
   python backend/main.py
   ```

3. **在MAS平台配置推送地址**
   - 登录MAS短信平台管理后台
   - 配置推送地址: `http://your-domain.com/admin/sms/push`

4. **测试推送**
   ```bash
   python backend/tests/test_sms_callback.py
   ```

## ⚠️ 常见问题

### Q: 为什么推送没有被接收？
A: 检查以下几点：
1. 推送地址是否正确配置
2. 您的系统是否可以从外网访问
3. 防火墙是否允许来自短信平台的请求
4. 查看系统日志中是否有错误信息

### Q: 如何确认推送已被接收？
A: 查询数据库中的 `oa_t_sms` 表，检查是否有新的记录。

### Q: 推送失败会怎样？
A: 短信平台会重试3次，如果仍然失败，推送将被丢弃。

### Q: 如何处理重复推送？
A: 使用 `cpSubID` 和 `uPhone` 作为唯一键，避免重复处理。

