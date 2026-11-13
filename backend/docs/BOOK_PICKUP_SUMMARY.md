# 新书领取功能总结（供 Web 管理后端参考）

> 适用范围：开放教育学生新书领取登记 + 班主任自取地点设置
> 小程序已上线实现，Web 管理端可按此文档重建后端管理功能。

---

## 1. 业务概述

开放教育每学期统计一次新生教材领取方式，学生二选一：

| 枚举值 `pickup_type` | 中文含义 | 附加信息 |
|---|---|---|
| `self_pickup` | 到校领取 | 大概到校日期 `pickup_date` + 班主任设置的自取地点 |
| `mail` | 邮寄 | 收件人 / 电话 / 省市区 / 详细地址 |

核心规则：

1. **按批次 `pc` 统计**，`pc` 取自 `lw_sys.sys_pc`，后端每次实时查，不信任前端 / token。
2. **同一 `(学号 xs_xh, 批次 pc)` 只留一条**，重复提交 = `UPDATE`，学生可随时回来修改。
3. **自取地点不存快照**。班主任改地址后，学生端实时看到新地址。
4. 每个老师带多个班**共用同一个地址**。

涉及三端：

| 端 | 页面 | 文件 |
|---|---|---|
| 学生 | 我的 → 新书领取登记 | `packageStudent/pages/my/my` → `packageStudent/pages/book-pickup/book-pickup` |
| 班主任（开放教师） | 教师中心 → 新书自取地点 | `packageTeacher/pages/open-teacher-my/open-teacher-my` → `packageTeacher/pages/open-teacher-book-site/open-teacher-book-site` |
| 后端 | FastAPI | `backend/controllers/student_book_pickup.py`、`backend/controllers/open_teacher.py` |

---

## 2. 数据库模型

### 2.1 主表 `oa_xs_book_pickup`

SQLAlchemy：`backend/models/models.py` → `OaXsBookPickup`，表名 `oa_xs_book_pickup`。

模型定义原文：

```python
class OaXsBookPickup(Base):
    """开放教育学生新书领取登记表

    每个学期统计一次，批次(pc)取自 lw_sys.sys_pc，后端实时查询不信任 token。
    同一 (xs_xh, pc) 只保留一条记录，重复提交为 UPDATE，支持随时修改。

    领取方式 pickup_type 为英文语义字符串枚举：
    - self_pickup: 到校领取(需填写 pickup_date，格式 YYYY-MM-DD)
    - mail: 邮寄(需填写收件人 receiver_name / 电话 receiver_phone /
      省市区 province/city/district / 详细地址 detail_addr)
    """
    __tablename__ = 'oa_xs_book_pickup'
    __table_args__ = (
        UniqueConstraint('xs_xh', 'pc', name='uq_book_pickup_xh_pc'),
        Index('ix_book_pickup_xh_pc', 'xs_xh', 'pc'),
        {'implicit_returning': False},
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
    xs_xh = Column(String( snippets20), nullable=False, comment='学号')
    xs_xm = Column(String(20), comment='姓名(冗余)')
    xs_bj_id = Column(Integer, comment='班级ID(冗余，方便按班统计)')
    pc = Column(Integer, nullable=False, comment='批次，取自 lw_sys.sys_pc')
    pickup_type = Column(String(16), nullable=False, comment='领取方式: self_pickup-到校领取 / mail-邮寄')
    pickup_date = Column(String(20), comment='到校领取日期 YYYY-MM-DD (self_pickup时必填)')
    receiver_name = Column(String(20), comment='收件人姓名 (mail时必填)')
    receiver_phone = Column(String(15), comment='收件人电话 (mail时必填)')
    province = Column(String(50), comment='省 (mail时必填)')
    city = Column(String(50), comment='市 (mail时必填)')
    district = Column(String(50), comment='区/县 (mail时必填)')
    detail_addr = Column(String(200), comment='详细地址 (mail时必填)')
    addtime = Column(DateTime, default=datetime.now, comment='创建时间')
    updatetime = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='最后修改时间')
```

字段说明：

| 字段 | 类型（MSSQL 建议） | 必填 | 说明 |
|---|---|---|---|
| `id` | `INT IDENTITY(1,1) PK` | 是 | 主键 |
| `xs_xh` | `NVARCHAR(20) NOT NULL` | 是 | 学号，关联 `oa_xs.xs_xh` |
| `xs_xm` | `NVARCHAR(20) NULL` | 否 | 姓名冗余，提交时顺手更新 |
| `xs_bj_id` | `INT NULL` | 否 | 班级 ID 冗余，方便按班统计，关联 `oa_bj.bj_id` |
| `pc` | `INT NOT NULL` | 是 | 批次，=`lw_sys.sys_pc` |
| `pickup_type` | `NVARCHAR(16) NOT NULL` | 是 | `self_pickup` / `mail` |
| `pickup_date` | `NVARCHAR(20) NULL` | 条件 | 到校日期 `YYYY-MM-DD`，`self_pickup` 时必填 |
| `receiver_name` | `NVARCHAR(20) NULL` | 条件 | `mail` 必填 |
| `receiver_phone` | `NVARCHAR(15) NULL` | 条件 | `mail` 必填，11 位手机号 `^1\d{10}$` |
| `province` / `city` / `district` | `NVARCHAR(50) NULL` | 条件 | `mail` 必填，省 / 市 / 区 |
| `detail_addr` | `NVARCHAR(200) NULL` | 条件 | `mail` 必填 |
| `addtime` | `DATETIME` | 是 | 创建时间 |
| `updatetime` | `DATETIME` | 是 | 最后修改时间 |

约束 / 索引（MSSQL 建表示例）：

```sql
CREATE TABLE oa_xs_book_pickup (
  id INT IDENTITY(1,1) PRIMARY KEY,
  xs_xh NVARCHAR(20) NOT NULL,
  xs_xm NVARCHAR(20) NULL,
  xs_bj_id INT NULL,
  pc INT NOT NULL,
  pickup_type NVARCHAR(16) NOT NULL, -- self_pickup / mail
  pickup_date NVARCHAR(20) NULL,
  receiver_name NVARCHAR(20) NULL,
  receiver_phone NVARCHAR(15) NULL,
  province NVARCHAR(50) NULL,
  city NVARCHAR(50) NULL,
  district NVARCHAR(50) NULL,
  detail_addr NVARCHAR(200) NULL,
  addtime DATETIME DEFAULT GETDATE(),
  updatetime DATETIME DEFAULT GETDATE(),
  CONSTRAINT uq_book_pickup_xh_pc UNIQUE (xs_xh, pc)
);

CREATE INDEX ix_book_pickup_xh_pc ON oa_xs_book_pickup (xs_xh, pc);
CREATE INDEX ix_book_pickup_pc_bj ON oa_xs_book_pickup (pc, xs_bj_id);
```

### 2.2 班主任地址字段 `oa_t.t_book_pickup_addr`

`Teacher` 模型表 `oa_t` 新增字段：

```python
t_book_pickup_addr = Column(String(200), comment='班主任设置的新书自取地点；学生选到校领取时实时展示')
```

```sql
ALTER TABLE oa_t ADD t_book_pickup_addr NVARCHAR(200) NULL;
```

语义：班主任设置的自取地点，空（`NULL` / 空串）表示未设置，学生端显示“联系班主任”。一个老师多班共用。

### 2.3 关联表

```text
oa_xs_book_pickup.xs_xh   → oa_xs.xs_xh（学生）
oa_xs_book_pickup.xs_bj_id → oa_bj.bj_id（班级，冗余统计用）
oa_xs.xs_bj_id → oa_bj.bj_id → oa_bj.bj_bzr_id → oa_t.t_id（班主任）
oa_t.t_book_pickup_addr（自取地点，实时读）
lw_sys.sys_pc（当前批次，单行表取第一条）
```

> 注意自取地点查找链：`student.xs_bj_id → Class.bj_bzr_id → Teacher.t_book_pickup_addr`，
> 见 `student_book_pickup.py:_get_pickup_site()`。学生没分班 / 班级没班主任时返回 `null`。

---

## 3. 后端接口（小程序现行）

基址前缀 + Token 鉴权（`verify_token_and_get_payload`，`payload` 里有 `xs_id` / `xs_xh` 或 `t_id`）。

### 3.1 `GET /student_book_pickup/status`

学生打开登记页时调（`onLoad` / `onShow` 都调一次）。

返回 `data`：

```json
{
  "pc": 12,
  "filled": true,
  "current": {
    "pickup_type": "mail",
    "pickup_type_text": "邮寄",
    "pickup_date": "",
    "receiver_name": "张三",
    "receiver_phone": "13800000000",
    "province": "贵州省",
    "city": "黔东南州",
    "district": "凯里市",
    "detail_addr": "xx路1号",
    "updated_at": "2026-08-10 12:00:00"
  },
  "last_mail": {
    "pc": 11,
    "receiver_name": "...",
    "receiver_phone": "...",
    "province": "...",
    "city": "...",
    "district": "...",
    "detail_addr": "..."
  },
  "pickup_type_labels": { "self_pickup": "到校领取", "mail": "邮寄" },
  "pickup_site": {
    "address": "校本部一楼教材室（找张老师）",
    "has_address": true,
    "teacher_name": "李老师",
    "teacher_phone": "13900000000"
  }
}
```

- `current = null` 表示本批次未登记。
- `last_mail`：该生 `pc < 当前 pc` 的最新一条且 `pickup_type = mail` 的记录，用于“一键沿用上次地址”。非 `mail` 则为 `null`。
- `pickup_site = null` 表示查不到班主任；`has_address = false` 表示班主任还没设地址。

### 3.2 `POST /student_book_pickup/submit`

Upsert 本批次。请求体：

```json
// 到校领取
{ "pickup_type": "self_pickup", "pickup_date": "2026-09-01" }

// 邮寄
{
  "pickup_type": "mail",
  "receiver_name": "张三",
  "receiver_phone": "13800000000",
  "province": "贵州省",
  "city": "黔东南州",
  "district": "凯里市",
  "detail_addr": "xx路1号"
}
```

服务端校验（`student_book_pickup.py:submit_pickup`）：

- `self_pickup`：`pickup_date` 必填，`YYYY-MM-DD` 合法；同时**清空所有邮寄字段**防脏数据。
- `mail`：姓名 / 电话 / 省市区 / 详细地址必填，电话 `^1\d{10}$`；同时 `pickup_date = ""`。
- 查不到 `sys_pc` 报 500“系统批次未配置”。

写入：按 `(xs_xh, pc)` 查，无则 `INSERT`，有则 `UPDATE` + 刷新 `xs_xm` / `xs_bj_id` / `updatetime`。

成功返回：

```json
{
  "success": true,
  "msg": "提交成功",
  "data": {
    "pc": 12,
    "submitted_at": "2026-08-10 12:00:00",
    "current": { "...同 status.current..." }
  }
}
```

### 3.3 班主任 `GET /open_teacher/book_pickup_site` / `POST /open_teacher/book_pickup_site`

- `GET` 返回 `{ "address": "..." }`。
- `POST { "address": "..." }`，`trim` 后最长 200 字，空串表示清空（存 `NULL`），见 `open_teacher.py:save_book_pickup_site`。

---

## 4. 小程序功能流程

### 4.1 学生端 `book-pickup`

入口：`packageStudent/pages/my/my` → “新书领取登记” → `packageStudent/pages/book-pickup/book-pickup`。

流程：

1. 进页 `fetchStatus()` → 渲染三块：状态提示条（未填 / 已填 `status_summary`）、领取方式二选一、自取 / 邮寄表单（`hidden` 切换，不用 `wx:if` 反复重建，避免基础库 `null[0]` 报错）。
2. `self_pickup`：展示 `pickup_site`：
   - 有地址 → 显示地址 + 联系人；
   - 无地址但有联系人 → “自取地点请联系班主任”；
   - 都没有 → “暂未设置领取地点”。
3. `mail`：
   - 若有 `last_mail` 显示“上次地址 + 一键沿用”；
   - 省市区用原生 `picker mode=region`（空值必须 `[]`），收件人 / 电话 / 详细地址用 `van-field`。
4. 校验通过 → `POST submit` → Toast 成功 → 重新 `fetchStatus()`，按钮文案 `提交登记` / `保存修改` 切换。

前端文件：`book-pickup.{wxml,wxss,js,json}`。

### 4.2 班主任端 `open-teacher-book-site`

入口：`packageTeacher/pages/open-teacher-my/open-teacher-my` → “新书自取地点”。

流程：`fetchSite()` 回显 → `textarea` 编辑（200 字计数）→ `onSave()`。留空保存 = 清空。

前端文件：`open-teacher-book-site.{wxml,wxss,js,json}`。

---

## 5. 给 Web 管理后端的功能建议

新项目只需围绕上面两张表做管理端，推荐接口：

1. **登记明细查询**：按 `pc` / 班级 / `pickup_type` / 关键字（学号姓名）/ 有无填写筛选分页，关联 `oa_xs` 补全班级名。
2. **统计看板**：按 `pc` 统计 `已登记 / 未登记`；已登记中 `self_pickup` / `mail` 占比；按 `xs_bj_id` 分班统计未登记名单（催报用）。
3. **导出**：按批次导出 Excel：`mail` 导出完整收件地址（省市区 + 详细 + 电话），`self_pickup` 导出 `pickup_date` + 当时班主任地址（注意现行是实时地址，导出如需留痕建议 Web 端导出时连查 `oa_t` 快照，或新增快照字段）。
4. **批次管理**：读写 `lw_sys.sys_pc`，切换批次即开启新一轮统计，历史批次只读。
5. **代设自取地点**：按教师 / 班级批量查看 `t_book_pickup_addr` 是否为空，支持管理员代填。
6. **字典**：`pickup_type` 前端显示用 `{ "self_pickup": "到校领取", "mail": "邮寄" }`。

判空注意：历史脏数据可能两种分支字段混填，统计时以 `pickup_type` 为准，另一分支字段忽略。

---

## 6. 相关代码索引

| 内容 | 路径 |
|---|---|
| 学生接口 | `backend/controllers/student_book_pickup.py` |
| 班主任接口 | `backend/controllers/open_teacher.py`（`book_pickup_site`） |
| 数据模型 | `backend/models/models.py`（`OaXsBookPickup`、`Teacher.t_book_pickup_addr`） |
| 路由注册 | `backend/main.py`（`student_book_pickup_router`） |
| 学生前端 | `frontend/packageStudent/pages/book-pickup/` |
| 教师前端 | `frontend/packageTeacher/pages/open-teacher-book-site/` |
| 入口菜单 | `frontend/packageStudent/pages/my/my.wxml`、`frontend/packageTeacher/pages/open-teacher-my/open-teacher-my.wxml` |
