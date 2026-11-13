# MAS短信平台推送接口文档

## 概述

本文档描述了系统中短信推送接口的实现，用于接收MAS短信平台的**状态报告推送**和**上行消息推送**。

这是一个**被动接收**接口，由短信平台主动推送数据到您的系统。

## 接口地址

```
POST /admin/sms/push
```

## 推送类型

| syncType | 说明 | 用途 |
|----------|------|------|
| 0 | 状态报告 | 接收短信发送结果（成功/失败） |
| 1 | 上行消息 | 接收用户回复的短信内容 |

## 请求参数

### 状态报告推送请求 (syncType=0)

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
    },
    {
      "userID": "1",
      "spNo": "10657001",
      "uPhone": "13800000002",
      "cpSubID": "14100817343197985",
      "cpSubSn": "2",
      "rptCode": "0",
      "rptTime": "2014/10/8 17:34:31"
    }
  ]
}
```

### 上行消息推送请求 (syncType=1)

```json
{
  "nCount": 2,
  "syncType": 1,
  "syncData": [
    {
      "userID": "1",
      "spNo": "10657001",
      "uPhone": "13800000001",
      "cpSubID": "14100817343197985",
      "reContent": "测试回复",
      "reTime": "2014/10/8 18:35:43"
    },
    {
      "userID": "1",
      "spNo": "10657001",
      "uPhone": "13800000002",
      "cpSubID": "14100817343197985",
      "reContent": "上行消息",
      "reTime": "2014/10/8 18:35:47"
    }
  ]
}
```

### 参数说明

| 参数名 | 类型 | 必需 | 说明 |
|--------|------|------|------|
| nCount | int | 是 | 推送总数 |
| syncType | int | 是 | 推送类型 (0=状态报告, 1=上行消息) |
| syncData | array | 是 | 推送数据数组 |
| userID | string | 否 | 用户ID |
| spNo | string | 是 | 服务号码（短信来源号码） |
| uPhone | string | 是 | 手机号码 |
| cpSubID | string | 是 | **CP任务编号（关键字段，用于关联）** |
| cpSubSn | string | 是 | 手机号码序列号 |
| rptCode | string | 是 | 状态报告码（状态报告） |
| rptTime | string | 是 | 回执时间（状态报告） |
| reContent | string | 是 | 回复内容（上行消息） |
| reTime | string | 是 | 回复时间（上行消息） |

## 状态报告码说明

| 状态码 | 说明 |
|--------|------|
| 0 | 成功 |
| MX:1315 | 号段错误 |
| MX:0003 | 单个号码当天下发条数超过上限(长短信算1条) |
| MX:0004 | 短信内容包含敏感词 |
| MX:0005 | 模板无法匹配 |
| MX:0008 | 签名无法匹配通道 |
| MX:0013 | 黑名单 |
| MX:0014 | 省份屏蔽 |
| MX:0020 | 单个号码相同内容，当天下发条数超过上限 |
| MX:0021 | 单个号码当天下发条数超过上限(同个平台) |
| MN00001 | 空号 |
| DB00107 | 业务代码错误或产品未建立 |
| DB00108 | 欠费或投诉关停 |
| DB00140 | 号码不在白名单中 |
| DB00143 | 提交超限 |

## 响应格式

### 成功响应

**必须返回以下格式，短信平台才会认为接收成功：**

```json
{
  "code": 0,
  "msg": "接收成功"
}
```

### 失败响应

```json
{
  "code": 400,
  "msg": "缺少必要参数"
}
```

或

```json
{
  "code": 500,
  "msg": "处理失败: 错误信息"
}
```

## ⚠️ 重要说明

1. **响应格式必须严格按照文档要求**，短信平台会根据 `code` 字段判断是否接收成功
2. **cpSubID 是关键字段**，用于关联您提交的短信任务
3. **推送有效期为72小时**，超过72小时的推送将被丢弃
4. **如果您的系统响应超时或返回错误**，短信平台会重试3次

## 数据库记录

回调数据会被保存到 `oa_t_sms` 表中，包含以下字段：

| 字段名 | 类型 | 说明 |
|--------|------|------|
| id | int | 主键ID |
| t_id | int | 教师ID |
| t_xm | varchar | 教师姓名 |
| fssj | datetime | 发送时间 |
| nr | text | 短信内容 |
| xs_xm | text | 学生姓名 |
| xs_dh | text | 学生电话 |
| num | int | 发送条数 |
| cpSubID | varchar | 短信平台返回的子ID |
| send_status | int | 发送状态码 |
| status_desc | text | 状态描述 |

## 使用示例

### 在MAS短信平台配置推送地址

在MAS短信平台管理后台，配置以下推送地址：

```
http://your-domain.com/admin/sms/push
```

### Python 模拟推送示例

```python
import requests
import json

# 状态报告推送
status_report = {
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
        },
        {
            "userID": "1",
            "spNo": "10657001",
            "uPhone": "13800000002",
            "cpSubID": "14100817343197985",
            "cpSubSn": "2",
            "rptCode": "MX:0013",
            "rptTime": "2014/10/8 17:34:32"
        }
    ]
}

response = requests.post(
    'http://localhost:8000/admin/sms/push',
    json=status_report
)
print(response.json())  # 应该返回 {"code": 0, "msg": "接收成功"}

# 上行消息推送
uplink_message = {
    "nCount": 1,
    "syncType": 1,
    "syncData": [
        {
            "userID": "1",
            "spNo": "10657001",
            "uPhone": "13800000001",
            "cpSubID": "14100817343197985",
            "reContent": "用户回复的内容",
            "reTime": "2014/10/8 18:35:43"
        }
    ]
}

response = requests.post(
    'http://localhost:8000/admin/sms/push',
    json=uplink_message
)
print(response.json())  # 应该返回 {"code": 0, "msg": "接收成功"}
```

### cURL 请求示例

```bash
# 状态报告推送
curl -X POST http://localhost:8000/admin/sms/push \
  -H "Content-Type: application/json" \
  -d '{
    "nCount": 1,
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
  }'

# 上行消息推送
curl -X POST http://localhost:8000/admin/sms/push \
  -H "Content-Type: application/json" \
  -d '{
    "nCount": 1,
    "syncType": 1,
    "syncData": [
      {
        "userID": "1",
        "spNo": "10657001",
        "uPhone": "13800000001",
        "cpSubID": "14100817343197985",
        "reContent": "用户回复",
        "reTime": "2014/10/8 18:35:43"
      }
    ]
  }'
```

## 配置说明

在 `backend/utils/sms_callback_config.py` 中可以配置：

1. **回调接口地址** - 需要在短信平台中配置
2. **短信平台账户信息** - 用于验证和调用
3. **签名验证** - 可选的安全验证机制
4. **参数映射** - 支持不同平台的参数名称

## 注意事项

1. **cpSubID 是关键字段** - 用于关联发送记录，必须保证唯一性
2. **状态码转换** - 系统会自动转换平台状态码为标准状态码
3. **参数灵活性** - 支持多种参数名称别名，自动识别
4. **错误处理** - 所有错误都会被记录到日志中
5. **事务管理** - 每条记录的更新都在事务中进行，确保数据一致性

## 故障排查

### 回调未被记录

1. 检查接口地址是否正确配置在短信平台
2. 查看系统日志中是否有错误信息
3. 确认 cpSubID 参数是否正确传递

### 状态码识别错误

1. 检查状态码是否在支持的列表中
2. 查看 `sms_status_codes.py` 中的映射表
3. 如需添加新的状态码，更新映射表

### 数据库记录失败

1. 检查数据库连接是否正常
2. 查看 `oa_t_sms` 表是否存在
3. 检查字段类型是否匹配

