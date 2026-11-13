# 短信推送接口详细日志记录说明

## 📝 概述

改进了 `/admin/sms/push` 接口的日志记录，确保所有请求和错误信息都被详细记录，便于调试和监控。

## 🔍 日志记录内容

### 1. 请求基本信息

每个请求到达时，记录以下信息：

```
=== 收到短信推送请求 ===
请求方法: POST
请求路径: /admin/sms/push
请求头: {...}
客户端 IP: 101.37.116.233
```

### 2. 原始请求体

记录完整的原始请求体（支持两种格式）：

**JSON 格式**:
```
原始请求体: {"nCount":1,"syncType":0,"syncData":[...]}
```

**Form-data 格式**:
```
原始请求体: msg={"nCount":1,"syncType":0,"syncData":[...]}
```

### 3. 解析过程

记录数据解析的每一步：

```
❌ JSON 直接解析失败: Expecting value: line 1 column 1 (char 0)
检测到 form-data 格式，msg 参数: {"nCount":1,"syncType":0,"syncData":[...]}
✅ 使用 form-data 格式解析成功
解析后的数据: {"nCount":1,"syncType":0,"syncData":[...]}
```

### 4. 参数验证

记录参数验证的结果：

```
参数验证: nCount=1, syncType=0, syncData 数量=1
✅ 参数验证通过，开始处理推送: 类型=0, 数量=1
```

### 5. 数据处理

记录每条数据的处理过程：

```
--- 处理第 1/1 条数据 ---
项目数据: {"userID":"569","uPhone":"15286335158","rptCode":"0",...}
✅ 【状态报告】cpSubID=task_20251028145828_70af7dec, 手机=15286335158, 状态码=0, 状态=成功, 时间=2025-10-28 14:58:33:186
```

### 6. 处理完成总结

记录处理结果的总结：

```
=== 推送处理完成 ===
成功处理: 1 条
处理失败: 0 条
返回响应: code=0, msg=接收成功
```

### 7. 错误信息

所有错误都被详细记录：

```
❌ 推送参数不完整: nCount=None, syncType=0
❌ 缺少关键参数: cpSubID=None, uPhone=15286335158
❌ 处理第 1 条数据失败: KeyError: 'rptCode'
异常信息: ...
```

## 📊 日志级别

- **INFO**: 正常的请求和处理流程
- **WARNING**: 参数不完整或数据异常
- **ERROR**: 处理失败或异常情况

## 🧪 测试示例

### 测试 1: 成功的推送

```bash
curl -X POST http://localhost:8000/admin/sms/push \
  -F 'msg={"nCount":1,"syncType":0,"syncData":[{"userID":"569","uPhone":"15286335158","rptCode":"0","rptTime":"2025-10-28 14:58:33:186","spNo":"","cpSubID":"task_20251028145828_70af7dec","apiCode":"","cpSubSn":"0"}]}'
```

**日志输出**:
```
=== 收到短信推送请求 ===
请求方法: POST
请求路径: /admin/sms/push
请求头: {...}
客户端 IP: 127.0.0.1
原始请求体: msg={"nCount":1,"syncType":0,"syncData":[...]}
检测到 form-data 格式，msg 参数: {"nCount":1,"syncType":0,"syncData":[...]}
✅ 使用 form-data 格式解析成功
解析后的数据: {"nCount":1,"syncType":0,"syncData":[...]}
参数验证: nCount=1, syncType=0, syncData 数量=1
✅ 参数验证通过，开始处理推送: 类型=0, 数量=1
--- 处理第 1/1 条数据 ---
项目数据: {"userID":"569","uPhone":"15286335158",...}
✅ 【状态报告】cpSubID=task_20251028145828_70af7dec, 手机=15286335158, 状态码=0, 状态=成功, 时间=2025-10-28 14:58:33:186
=== 推送处理完成 ===
成功处理: 1 条
处理失败: 0 条
返回响应: code=0, msg=接收成功
```

### 测试 2: 缺少参数的推送

```bash
curl -X POST http://localhost:8000/admin/sms/push \
  -F 'msg={"nCount":1}'
```

**日志输出**:
```
=== 收到短信推送请求 ===
...
原始请求体: msg={"nCount":1}
✅ 使用 form-data 格式解析成功
解析后的数据: {"nCount":1}
参数验证: nCount=1, syncType=None, syncData 数量=0
❌ 推送参数不完整: nCount=1, syncType=None
返回响应: code=400, msg=缺少必要参数
```

### 测试 3: 无效的 JSON

```bash
curl -X POST http://localhost:8000/admin/sms/push \
  -F 'msg=invalid json'
```

**日志输出**:
```
=== 收到短信推送请求 ===
...
原始请求体: msg=invalid json
❌ JSON 直接解析失败: Expecting value: line 1 column 1 (char 0)
检测到 form-data 格式，msg 参数: invalid json
❌ form-data 解析失败: Expecting value: line 1 column 1 (char 0)
返回响应: code=400, msg=JSON 和 form-data 格式都解析失败
```

## 📂 日志文件位置

所有日志都被记录到以下位置：

1. **控制台输出**: 实时查看
2. **日志文件**: `logs/sms_requests.log` (JSON 格式)
3. **系统日志**: `logs/xjxt.log` (标准日志格式)

## 🔍 查看日志

### 查看所有日志
```bash
tail -f logs/xjxt.log
```

### 查看特定请求的日志
```bash
grep "task_20251028145828_70af7dec" logs/xjxt.log
```

### 查看所有错误
```bash
grep "ERROR" logs/xjxt.log
```

### 查看推送处理完成的日志
```bash
grep "推送处理完成" logs/xjxt.log
```

### 查看 JSON 格式的日志
```bash
cat logs/sms_requests.log | jq
```

## 💡 调试技巧

### 1. 追踪单个请求

使用 `cpSubID` 追踪单个请求的完整处理过程：

```bash
grep "task_20251028145828_70af7dec" logs/xjxt.log
```

### 2. 查看所有失败的请求

```bash
grep "❌" logs/xjxt.log
```

### 3. 查看处理统计

```bash
grep "推送处理完成" logs/xjxt.log
```

### 4. 实时监控

```bash
tail -f logs/xjxt.log | grep "短信推送"
```

## 📋 日志格式示例

### 完整的成功请求日志

```
2025-10-28 14:58:34,166 - controllers.admin_sms - INFO - === 收到短信推送请求 ===
2025-10-28 14:58:34,166 - controllers.admin_sms - INFO - 请求方法: POST
2025-10-28 14:58:34,166 - controllers.admin_sms - INFO - 请求路径: /admin/sms/push
2025-10-28 14:58:34,166 - controllers.admin_sms - INFO - 请求头: {...}
2025-10-28 14:58:34,166 - controllers.admin_sms - INFO - 客户端 IP: 101.37.116.233
2025-10-28 14:58:34,166 - controllers.admin_sms - INFO - 原始请求体: msg={"nCount":1,"syncType":0,"syncData":[...]}
2025-10-28 14:58:34,166 - controllers.admin_sms - INFO - 检测到 form-data 格式，msg 参数: {"nCount":1,"syncType":0,"syncData":[...]}
2025-10-28 14:58:34,166 - controllers.admin_sms - INFO - ✅ 使用 form-data 格式解析成功
2025-10-28 14:58:34,166 - controllers.admin_sms - INFO - 解析后的数据: {"nCount":1,"syncType":0,"syncData":[...]}
2025-10-28 14:58:34,166 - controllers.admin_sms - INFO - 参数验证: nCount=1, syncType=0, syncData 数量=1
2025-10-28 14:58:34,166 - controllers.admin_sms - INFO - ✅ 参数验证通过，开始处理推送: 类型=0, 数量=1
2025-10-28 14:58:34,166 - controllers.admin_sms - INFO - --- 处理第 1/1 条数据 ---
2025-10-28 14:58:34,166 - controllers.admin_sms - INFO - 项目数据: {"userID":"569","uPhone":"15286335158",...}
2025-10-28 14:58:34,166 - controllers.admin_sms - INFO - ✅ 【状态报告】cpSubID=task_20251028145828_70af7dec, 手机=15286335158, 状态码=0, 状态=成功, 时间=2025-10-28 14:58:33:186
2025-10-28 14:58:34,166 - controllers.admin_sms - INFO - === 推送处理完成 ===
2025-10-28 14:58:34,166 - controllers.admin_sms - INFO - 成功处理: 1 条
2025-10-28 14:58:34,166 - controllers.admin_sms - INFO - 处理失败: 0 条
2025-10-28 14:58:34,166 - controllers.admin_sms - INFO - 返回响应: code=0, msg=接收成功
```

## ✅ 改进总结

- ✅ 记录所有请求的基本信息
- ✅ 记录原始请求体（支持两种格式）
- ✅ 记录解析过程和结果
- ✅ 记录参数验证过程
- ✅ 记录每条数据的处理过程
- ✅ 记录处理完成的总结
- ✅ 记录所有错误和异常
- ✅ 便于调试和监控

