# 腾讯云短信发送与回调对接说明

> 适用项目：zhpt-new（职教平台）
> 生效日期：2026-11-01
> 旧方案：MAS 平台 `http://101.37.116.233:8063/subSmsApi.aspx`（已下线）

---

## 1. 架构变化

```
                    ┌─────────────────────────────┐
   zhpt-new         │  短信网关 (内网)             │
   (本项目)  ──────>│  172.16.100.103:3088         │
        │           │  /api/v1/sms_manage/        │
        │           │      sms_interface/send      │
        │           └──────────────┬──────────────┘
        │                          │ 腾讯云 SendSms
        │                          v
        │                    ┌──────────┐
        │                    │  腾讯云   │
        │                    └────┬─────┘
        │                         │ 状态回调（下发状态通知）
        │                         v
        └────── POST /sms/callback <── 公网 nginx ──> 本项目回调地址
```

**要点**
- 发送不再直连腾讯云，全部走管理员封装的网关
- 回调由腾讯云直接 POST 到本项目，需在腾讯云控制台配置回调 URL
- 网关会把发送结果写入 `sms_log` 表（`lx=7`），`cpSubID` 存的是腾讯云 `SerialNo`

---

## 2. 发送侧

### 2.1 网关接口

```
POST http://172.16.100.103:3088/api/v1/sms_manage/sms_interface/send
Content-Type: application/json
```

请求体：

| 字段 | 类型 | 说明 |
|---|---|---|
| `phone_number_set` | string[] | 手机号列表，单次最多 200 个 |
| `template_id` | string | 腾讯云模板 ID（不传则取网关后台默认） |
| `sign_name` | string | 短信签名，默认「黔东南开放大学」 |
| `template_param_set` | string[] | 模板变量，**个数必须与模板变量个数一致** |
| `session_context` | string | 调用方上下文，原样回传，便于对账 |
| `source` | string | 调用方标识，本项目固定传「小程序」 |
| `userid` | string | 接收方 ID：学生=学号，教师=用户名 |
| `username` | string | 接收方姓名 |

响应：

```json
{ "success": true, "msg": "发送成功", "data": { "code": "Ok", "msg": "send success" } }
```

### 2.2 `template_param_set` 规则

| 模板类型 | 参数个数 | 说明 |
|---|---|---|
| 验证码模板 | 2 | `[验证码, 有效分钟数]` |
| 通知类模板（无变量） | 0 | 传空数组 `[]` |
| 自定义内容模板 | 1 | `[短信正文]` |

> ⚠️ 若模板无变量却传了参数、或有变量却没传，腾讯云会返回
> `FailedOperation.TemplateParamSetNotMatchApprovedTemplate`。

### 2.3 `userid` 填写规则

| 接收方 | userid | username |
|---|---|---|
| 学生 | 学号（`xs_id`） | 学生姓名（`xs_xm`） |
| 教师 | 教师用户名（`t_yhm`） | 教师姓名（`t_xm`） |

---

## 3. 回调侧

### 3.1 接口

```
POST /sms/callback
```

腾讯云推送的是 **JSON 数组**：

```json
[
  {
    "user_receive_time": "2026-11-01 10:50:00",
    "nationcode": "86",
    "mobile": "18230736350",
    "report_status": "SUCCESS",
    "errmsg": "DELIVRD",
    "description": "用户短信送达成功",
    "sid": "99:110196198117935011214653635"
  }
]
```

| 字段 | 说明 |
|---|---|
| `sid` | **本次发送标识 ID**，与发送接口返回的 `SerialNo` 对应 → 用于查 `sms_log.cpSubID` |
| `report_status` | `SUCCESS` / `FAIL` |
| `errmsg` | 回执状态码，见 [错误码文档](https://cloud.tencent.com/document/api/382/59177) |
| `description` | 状态描述 |
| `mobile` | 手机号（可能带 `+86`） |
| `ext` | 对应发送时的 `SessionContext` |

响应（腾讯云要求）：

```json
{ "result": 0, "errmsg": "OK" }
```

### 3.2 处理逻辑

1. 校验来源 IP 是否在腾讯云回调网段内（`utils/tencent_sms_ip.py`，602 条 CIDR）
   - 非腾讯云来源直接忽略，但仍返回 `result=0`（避免腾讯重试）
   - 经 nginx 反代时，从 `X-Forwarded-For` / `X-Real-IP` 取真实公网 IP
2. 解析 JSON 数组，原始报文留档到 `logs/sms_requests.log`
3. 用 `sid` 查 `sms_log.cpSubID`：
   - 命中 → 更新 `callback_status`（**腾讯云回调原始 JSON 报文**）与 `callback_desc`（解析后的可读描述）
   - 未命中 → 用手机号兜底匹配最近一条未回调的记录
4. 回调记录写入 `sms_tb` 表留档

### 3.3 数据库字段

`sms_log` 表的两个回调字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `callback_status` | nvarchar(1000) | **腾讯云回调的原始 JSON 报文**（不解析、不改写，原样落库） |
| `callback_desc` | text | 解析后的可读描述：状态 + 错误码释义 + 接收时间 + ext |

> `callback_status` 由原先的 `SUCCESS`/`FAIL` 改为存原始报文，便于后续按需解析任意字段，
> 不必担心解析逻辑变更导致历史数据无法回溯。
> 典型报文长度约 210~240 字符，列宽由 `varchar(100)` 扩为 `nvarchar(1000)`。
> 迁移脚本：`sql/migrate_sms_log_callback_status_raw.sql`
>
> 注意：`callback_status IS NULL` 仍被用作「该记录尚未收到回调」的判断依据
> （`utils/sms.py` 复用网关记录、`utils/sms_callback_tencent.py` 兜底匹配），
> 改成原始报文不影响该语义。

---

## 4. 模板配置

模板 ID 通过环境变量配置，未配置的场景**会直接发送失败并给出明确提示**（避免把错误内容发给用户）：

| 场景 | 环境变量 | 当前默认 | 模板变量 |
|---|---|---|---|
| 验证码 | `SMS_TPL_VERIFY` | `2726397` | 验证码, 有效分钟 |
| 查询码通知 | `SMS_TPL_QUERY_CODE` | *（待管理员提供）* | 查询码 |
| 反馈办结 | `SMS_TPL_FEEDBACK_DONE` | *（待管理员提供）* | 无 |
| 请假通知（学生） | `SMS_TPL_STUDENT_LEAVE` | `2757281` | 无 |
| 请假通知（教师） | `SMS_TPL_STUDENT_LEAVE_TEACHER` | `2757283` | 无 |
| 留宿通知 | `SMS_TPL_STUDENT_STAY` | *（待管理员提供）* | 无 |
| 教师通知 | `SMS_TPL_TEACHER_NOTIFY` | *（待管理员提供）* | 无 |
| 自定义内容 | `SMS_TPL_CUSTOM` | *（待管理员提供）* | 短信正文 |

其它可配置项：

| 环境变量 | 默认 | 说明 |
|---|---|---|
| `SMS_GATEWAY_URL` | `http://172.16.100.103:3088/api/v1/sms_manage/sms_interface/send` | 网关地址 |
| `SMS_DEFAULT_SIGN_NAME` | `黔东南开放大学` | 短信签名 |
| `SMS_SOURCE` | `小程序` | 调用方标识 |
| `SMS_CALLBACK_IP_CHECK_ENABLED` | 开发环境 `false`，生产环境 `true` | 是否启用回调 IP 校验 |
| `SMS_TRUSTED_PROXY_IPS` | `172.16.100.102` | 受信代理 IP 列表（逗号分隔）。只有直连来源命中此列表时才采信 `X-Forwarded-For`，否则忽略所有代理头，防止外部伪造 |
| `FASTAPI_ENV` | `development` | 决定 IP 校验默认开关 |

---

## 5. 需要管理员配合的事项

1. **创建缺失的腾讯云模板**，把模板 ID 填入上表对应的环境变量
2. **在腾讯云控制台配置回调 URL**（指向公网 nginx，再转发到本项目 `/sms/callback`）
3. 确认 `SMS_CALLBACK_IP_CHECK_ENABLED` 在生产环境为 `true`
4. 确认 `FASTAPI_ENV=production`
5. 确认后端环境变量 `SMS_TRUSTED_PROXY_IPS` 包含 nginx 的 IP（默认 `172.16.100.102`）

---

## 5.1 Nginx 侧要求（`/usr/local/openresty/nginx/conf`）

### 站点配置 `sites/m.qdndd.com.cn.conf`

`/sms/callback` 必须使用**独立 location**，原因有二：

1. **绝不能进 `proxy_cache`** —— 回调是写操作，一旦被缓存，腾讯云拿到的是缓存响应，
   短信状态就永远回写不到 `sms_log`。
2. **独立限流 zone** —— 腾讯云回调可能短时间并发多条，沿用主站 `global_req`
   有触发 429 的风险；429 会让腾讯云持续重试。回调使用 `sms_callback` zone
   （100r/s，burst 500）。

参考配置：

```nginx
location = /sms/callback {
    client_max_body_size 1m;
    proxy_cache off;
    limit_req zone=sms_callback burst=500 nodelay;

    # X-Real-IP / X-Forwarded-For 必须透传
    include snippets/proxy_headers.conf;
    include snippets/proxy_custom.conf;

    # 不带 URI 后缀 → 原样透传 /sms/callback 路径
    proxy_pass http://m_qdndd_backend;
}
```

### `snippets/limits.conf`

需新增回调专用限流 zone：

```nginx
limit_req_zone $binary_remote_addr zone=sms_callback:10m rate=100r/s;
```

### `snippets/real_ip.conf`（重要）

`set_real_ip_from` 决定了哪些来源可以**用 `X-Forwarded-For` 覆盖 `$remote_addr`**。
一旦把整个内网段（如 `172.16.0.0/12`）列入其中，**该网段内任何客户端都能任意伪造
`X-Forwarded-For`**，而 nginx 会把伪造值当作真实 IP —— 这会同时影响：

- `access_log` 里的来源 IP
- `limit_req` 的限流键
- WAF 的 CC 防护
- **后端的腾讯云回调 IP 白名单校验**（可被绕过，伪造一个腾讯云网段 IP 即可）

因此只信任**明确的上游代理节点**，不要信任整个内网段：

```nginx
set_real_ip_from 172.16.110.1;   # 出口路由器 / 前置网关
set_real_ip_from 127.0.0.1;       # 本机回环
```

### 拓扑与验证

当前部署：

```
公网客户端 ---> 出口路由器/NAT (172.16.110.1) ---> OpenResty (172.16.100.102) ---> 后端 (172.16.14.215:3050)
```

验证方法（在服务器上执行）：

```bash
openresty -t                 # 语法检查
openresty -s reload          # 重载
tail -f /usr/local/openresty/nginx/logs/m.qdndd.com.cn.access.log | grep sms/callback
```

看到腾讯云回调的 `remote_addr` 是**公网 IP**（而非 `172.16.x.x`）即说明真实 IP 透传正常。

> 注意：若出口路由器做了 SNAT（表现为 `$remote_addr` 恒为路由器内网 IP），
> 需在路由器侧开启 XFF 透传，再把该路由器 IP 加入 `set_real_ip_from`。

---

## 6. 相关文件

| 文件 | 作用 |
|---|---|
| `utils/sms.py` | 发送入口 `SMSTool`（`send_sms` / `send_verify_sms` / `send_login_sms`） |
| `utils/sms_templates.py` | 场景 → 模板 ID 映射、模板变量构造 |
| `utils/sms_callback_tencent.py` | 回调处理、IP 白名单校验、状态码描述 |
| `utils/tencent_sms_ip.py` | 腾讯云回调 IP 网段白名单（自动生成） |
| `controllers/sms_callback.py` | 回调路由 `POST /sms/callback` |
| `models/models.py` | `SMSLog`（含 `callback_status` / `callback_desc`）、`SMSTb` |

---

## 7. 已废弃

| 文件 | 说明 |
|---|---|
| `controllers/admin_sms.py` 的 `/admin/sms/push` | 旧 MAS 平台回调（form-data + `msg` 字段），已不再被腾讯云调用 |
| `utils/sms_callback_config.py` | 旧 MAS 回调参数映射与签名校验，未被引用 |
| `utils/sms_status_codes.py` | 旧 MAS 状态码表，新流程不再使用 |
