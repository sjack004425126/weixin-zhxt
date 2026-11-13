# 短信推送接口修复说明

## 🐛 问题描述

MAS 平台推送数据时，接口无法正确解析请求数据。

### 错误原因

MAS 平台使用 **form-data** 格式发送数据，而不是标准的 JSON 格式。数据被放在 `msg` 参数中：

```
msg={"nCount":1,"syncType":0,"syncData":[...]}
```

而不是直接的 JSON 请求体。

## ✅ 修复方案

### 1. 支持两种请求格式

**文件**: `backend/controllers/admin_sms.py`

**改动**:
- 支持标准 JSON 格式
- 支持 form-data 格式（MAS 平台实际使用）
- 自动检测并解析两种格式

**优势**:
- ✅ 兼容 MAS 平台的 form-data 格式
- ✅ 向后兼容 JSON 格式
- ✅ 自动格式检测
- ✅ 更详细的日志记录

### 2. 改进异常处理器

**文件**: `backend/main.py`

**改动**:
- 添加 `PlainTextResponse` 导入
- 改进通用异常处理器
- 添加备用响应机制

**优势**:
- ✅ 避免 JSON 序列化失败
- ✅ 即使 JSON 响应失败也能返回响应
- ✅ 更详细的错误日志

## 🧪 测试方法

### 方法 1: 使用 curl 测试 form-data 格式（MAS 平台实际格式）

#### 测试推送成功的状态报告
```bash
curl -X POST http://localhost:8000/admin/sms/push \
  -F 'msg={"nCount":1,"syncType":0,"syncData":[{"userID":"569","uPhone":"15286335158","rptCode":"0","rptTime":"2025-10-28 14:58:33:186","spNo":"","cpSubID":"task_20251028145828_70af7dec","apiCode":"","cpSubSn":"0"}]}'
```

#### 测试推送上行消息
```bash
curl -X POST http://localhost:8000/admin/sms/push \
  -F 'msg={"nCount":1,"syncType":1,"syncData":[{"userID":"569","uPhone":"15286335158","reContent":"已收到，谢谢","reTime":"2025-10-28 15:00:00:000","spNo":"","cpSubID":"task_20251028145828_70af7dec","apiCode":"","cpSubSn":"0"}]}'
```

### 方法 2: 使用 curl 测试 JSON 格式（向后兼容）

#### 测试推送成功的状态报告
```bash
curl -X POST http://localhost:8000/admin/sms/push \
  -H "Content-Type: application/json; charset=utf-8" \
  -d '{
    "nCount": 1,
    "syncType": 0,
    "syncData": [
      {
        "userID": "569",
        "uPhone": "15286335158",
        "rptCode": "0",
        "rptTime": "2025-10-28 14:58:33:186",
        "spNo": "",
        "cpSubID": "task_20251028145828_70af7dec",
        "apiCode": "",
        "cpSubSn": "0"
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

### 方法 3: 使用测试脚本

```bash
python backend/tests/test_sms_push_formdata.py
```

**测试内容**:
1. ✅ form-data 格式的状态报告
2. ✅ JSON 格式的状态报告
3. ✅ form-data 格式的上行消息
4. ✅ form-data 格式的批量消息

## 📝 修改详情

### `/admin/sms/push` 接口改进

**改动**:
```python
# 获取请求体
body = await request.body()

# 记录原始请求体（用于调试）
try:
    body_str = body.decode('utf-8') if isinstance(body, bytes) else str(body)
    logger.info(f"收到短信推送请求: {body_str}")
except Exception as e:
    logger.info(f"收到短信推送请求 (无法解码): {str(e)}")

# 尝试解析 JSON 数据
push_data = None

# 方法 1: 尝试直接解析为 JSON
try:
    push_data = json.loads(body) if isinstance(body, bytes) else body
    logger.info("使用 JSON 格式解析成功")
except Exception as e:
    logger.debug(f"JSON 直接解析失败: {str(e)}")

    # 方法 2: 尝试解析为 form-data 格式
    try:
        form_data = await request.form()
        msg_param = form_data.get('msg')

        if msg_param:
            logger.info(f"检测到 form-data 格式，msg 参数: {msg_param}")
            push_data = json.loads(msg_param)
            logger.info("使用 form-data 格式解析成功")
        else:
            logger.error("form-data 中没有 msg 参数")
            return {'code': 400, 'msg': 'form-data 中缺少 msg 参数'}
    except Exception as form_error:
        logger.error(f"form-data 解析失败: {str(form_error)}")
        return {'code': 400, 'msg': 'JSON 和 form-data 格式都解析失败'}

if not push_data:
    logger.error("无法解析推送数据")
    return {'code': 400, 'msg': '无法解析推送数据'}
```

**关键改进**:
- ✅ 支持 JSON 格式（直接请求体）
- ✅ 支持 form-data 格式（msg 参数）
- ✅ 自动检测并选择合适的解析方法
- ✅ 详细的日志记录便于调试

### 异常处理器改进

**改动**:
```python
@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """处理其他未捕获的异常"""
    try:
        logging.error(f"未处理的异常: {str(exc)}", exc_info=True)
    except Exception as log_exc:
        logging.error(f"记录异常时出错: {str(log_exc)}")
    
    try:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "msg": "服务器内部错误",
                "data": None
            }
        )
    except Exception as response_exc:
        # 如果 JSONResponse 也失败了，返回纯文本响应
        logging.error(f"创建 JSON 响应时出错: {str(response_exc)}")
        return PlainTextResponse(
            "Internal Server Error",
            status_code=500
        )
```

## 🚀 部署步骤

1. **停止服务**: 按 `Ctrl+C` 停止运行中的服务
2. **重启服务**: 运行 `python backend/main.py`
3. **测试接口**: 使用上面的测试方法验证修复

## 📊 测试结果

### 测试 1: form-data 格式的状态报告（MAS 平台实际格式）
```bash
curl -X POST http://localhost:8000/admin/sms/push \
  -F 'msg={"nCount":1,"syncType":0,"syncData":[{"userID":"569","uPhone":"15286335158","rptCode":"0","rptTime":"2025-10-28 14:58:33:186","spNo":"","cpSubID":"task_20251028145828_70af7dec","apiCode":"","cpSubSn":"0"}]}'
```

**预期结果**: ✅ 成功，返回 `{"code": 0, "msg": "接收成功"}`

### 测试 2: JSON 格式的状态报告（向后兼容）
```bash
curl -X POST http://localhost:8000/admin/sms/push \
  -H "Content-Type: application/json; charset=utf-8" \
  -d '{"nCount":1,"syncType":0,"syncData":[{"userID":"569","uPhone":"15286335158","rptCode":"0","rptTime":"2025-10-28 14:58:33:186","spNo":"","cpSubID":"task_20251028145828_70af7dec","apiCode":"","cpSubSn":"0"}]}'
```

**预期结果**: ✅ 成功，返回 `{"code": 0, "msg": "接收成功"}`

### 测试 3: form-data 格式的上行消息
```bash
curl -X POST http://localhost:8000/admin/sms/push \
  -F 'msg={"nCount":1,"syncType":1,"syncData":[{"userID":"569","uPhone":"15286335158","reContent":"已收到，谢谢","reTime":"2025-10-28 15:00:00:000","spNo":"","cpSubID":"task_20251028145828_70af7dec","apiCode":"","cpSubSn":"0"}]}'
```

**预期结果**: ✅ 成功，返回 `{"code": 0, "msg": "接收成功"}`

## 💡 关键改进

### 1. 支持多种请求格式
- ✅ 支持标准 JSON 格式（直接请求体）
- ✅ 支持 form-data 格式（MAS 平台实际使用）
- ✅ 自动检测并选择合适的解析方法

### 2. 更好的编码处理
- 改进请求体的解码处理
- 支持 UTF-8 编码的中文内容
- 处理 `bytes` 对象

### 3. 更健壮的异常处理
- 处理 `bytes` 对象，避免 JSON 序列化失败
- 添加备用响应机制
- 提供更详细的错误日志

### 4. 更清晰的日志记录
- 记录原始请求体
- 记录解析方法（JSON 或 form-data）
- 记录解码错误
- 便于调试

## 📚 相关文件

- 短信推送接口: `backend/controllers/admin_sms.py`
- 异常处理: `backend/main.py`
- 测试脚本: `backend/tests/test_sms_push_fix.py`
- 日志文件: `logs/sms_requests.log`

## 🔍 故障排查

### 问题: 仍然收到 500 错误

**解决方案**:
1. 确保已重启服务
2. 检查请求头是否包含 `Content-Type: application/json`
3. 检查请求体是否是有效的 JSON 格式
4. 查看后端控制台是否有错误信息

### 问题: 看不到日志

**解决方案**:
1. 检查 `logs/` 目录是否存在
2. 检查后端服务是否正常运行
3. 查看后端控制台是否有错误信息

### 问题: 推送没有被记录

**解决方案**:
1. 检查推送请求的 JSON 格式是否正确
2. 检查 `nCount` 和 `syncType` 是否正确
3. 查看日志文件中的错误信息

## 📞 支持

如有问题，请查看日志文件：
```bash
cat logs/sms_requests.log | jq
```

或查看后端控制台输出。

