# 短信发送接口修复说明

## 🐛 问题描述

当通过外网访问 `/admin/sms/send` 接口时，出现以下错误：

```
TypeError: Object of type bytes is not JSON serializable
RequestValidationError: Input should be a valid dictionary or object to extract fields from
```

### 错误原因

1. **Pydantic 模型验证问题**: FastAPI 的 Pydantic 模型在解析请求体时，对 UTF-8 编码的中文内容处理不当
2. **异常处理器问题**: 异常处理器尝试序列化包含 `bytes` 对象的错误信息，导致 JSON 序列化失败

## ✅ 修复方案

### 1. 修改 `/admin/sms/send` 接口

**文件**: `backend/controllers/admin_sms.py`

**改动**:
- 将接口从使用 Pydantic 模型改为直接处理 `Request` 对象
- 手动解析 JSON 请求体
- 手动验证必要参数

**优势**:
- ✅ 避免 Pydantic 模型验证问题
- ✅ 更好地处理 UTF-8 编码
- ✅ 更灵活的参数验证

### 2. 修改异常处理器

**文件**: `backend/main.py`

**改动**:
- 在 `validation_exception_handler` 中处理 `bytes` 对象
- 将 `bytes` 转换为字符串，确保可以被 JSON 序列化

**优势**:
- ✅ 避免 JSON 序列化失败
- ✅ 提供更清晰的错误信息

## 🧪 测试方法

### 方法 1: 使用 curl 测试

```bash
# 测试中文内容
curl -X POST http://localhost:8000/admin/sms/send \
  -H "Content-Type: application/json; charset=utf-8" \
  -d '{"mobile":"15286335158","content":"测试短信-小石1"}'

# 预期响应
{
  "success": true,
  "message": "短信已提交，等待平台回调",
  "data": {
    "cpSubID": "task_20251028144300_abc12345",
    "response": "0"
  }
}
```

### 方法 2: 使用测试脚本

```bash
python backend/tests/test_sms_send_fix.py
```

**测试内容**:
1. ✅ 发送包含中文的短信
2. ✅ 发送英文短信
3. ✅ 缺少参数的错误处理
4. ✅ 推送回调测试

## 📝 修改详情

### `/admin/sms/send` 接口修改

**之前**:
```python
@router.post('/sms/send')
async def send_sms(request_data: SendSmsRequest):
    # 使用 Pydantic 模型
    sms_tool = SMSTool()
    result = sms_tool.send_sms(request_data.mobile, request_data.content)
    ...
```

**之后**:
```python
@router.post('/sms/send')
async def send_sms(request: Request):
    # 直接处理 Request 对象
    body = await request.body()
    request_data = json.loads(body) if isinstance(body, bytes) else body
    
    # 手动验证参数
    mobile = request_data.get('mobile')
    content = request_data.get('content')
    
    if not mobile or not content:
        return {"success": False, "message": "缺少必要参数", "data": None}
    
    # 发送短信
    sms_tool = SMSTool()
    result = sms_tool.send_sms(mobile, content)
    ...
```

### 异常处理器修改

**之前**:
```python
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "msg": "请求参数验证失败",
            "data": {"errors": exc.errors()}  # 可能包含 bytes 对象
        }
    )
```

**之后**:
```python
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    # 处理错误信息，确保可以被 JSON 序列化
    errors = []
    for error in exc.errors():
        error_dict = dict(error)
        # 将 input 字段转换为字符串
        if 'input' in error_dict and isinstance(error_dict['input'], bytes):
            try:
                error_dict['input'] = error_dict['input'].decode('utf-8')
            except:
                error_dict['input'] = str(error_dict['input'])
        errors.append(error_dict)
    
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "msg": "请求参数验证失败",
            "data": {"errors": errors}
        }
    )
```

## 🚀 部署步骤

1. **停止服务**: 按 `Ctrl+C` 停止运行中的服务
2. **重启服务**: 运行 `python backend/main.py`
3. **测试接口**: 使用上面的测试方法验证修复

## 📊 测试结果

### 测试 1: 中文短信
```bash
curl -X POST http://localhost:8000/admin/sms/send \
  -H "Content-Type: application/json; charset=utf-8" \
  -d '{"mobile":"15286335158","content":"测试短信-小石1"}'
```

**预期结果**: ✅ 成功

### 测试 2: 英文短信
```bash
curl -X POST http://localhost:8000/admin/sms/send \
  -H "Content-Type: application/json; charset=utf-8" \
  -d '{"mobile":"15286335158","content":"Test SMS"}'
```

**预期结果**: ✅ 成功

### 测试 3: 缺少参数
```bash
curl -X POST http://localhost:8000/admin/sms/send \
  -H "Content-Type: application/json; charset=utf-8" \
  -d '{"mobile":"15286335158"}'
```

**预期结果**: ❌ 返回错误信息

## 💡 关键改进

### 1. 更好的编码处理
- 直接处理 `Request` 对象，避免 Pydantic 的编码问题
- 支持 UTF-8 编码的中文内容

### 2. 更灵活的参数验证
- 手动验证参数，可以提供更清晰的错误信息
- 支持可选参数的灵活处理

### 3. 更健壮的异常处理
- 处理 `bytes` 对象，避免 JSON 序列化失败
- 提供更详细的错误信息

## 📚 相关文件

- 短信发送接口: `backend/controllers/admin_sms.py`
- 异常处理: `backend/main.py`
- 测试脚本: `backend/tests/test_sms_send_fix.py`
- 日志文件: `logs/sms_requests.log`

## 🔍 故障排查

### 问题: 仍然收到 422 错误

**解决方案**:
1. 确保已重启服务
2. 检查请求头是否包含 `Content-Type: application/json`
3. 检查请求体是否是有效的 JSON 格式

### 问题: 看不到日志

**解决方案**:
1. 检查 `logs/` 目录是否存在
2. 检查后端服务是否正常运行
3. 查看后端控制台是否有错误信息

### 问题: 短信没有发送

**解决方案**:
1. 检查手机号码是否正确
2. 检查短信内容是否为空
3. 查看日志文件中的错误信息

## 📞 支持

如有问题，请查看日志文件：
```bash
cat logs/sms_requests.log | jq
```

或查看后端控制台输出。

