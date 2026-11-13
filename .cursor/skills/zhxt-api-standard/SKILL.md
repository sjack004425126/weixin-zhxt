---
name: zhxt-api-standard
description: Enforces the zhxt frontend-backend API contract when writing or reviewing Vue pages that call the backend. Use when adding or editing a request call (tokenGet/tokenPost/tokenPut/tokenDelete), handling a response, unwrapping the { success, msg, data } envelope, writing try/catch error handling, or debugging a page where data renders empty / undefined. Applies to frontend/src/views/** and frontend/src/api/**.
---

# zhxt 前后端接口调用标准

本项目后端所有接口统一返回信封 `{ success, msg, data }`，前端 `request.js` **不做解包**，直接透传整个信封。因此**页面层必须自行取 `.data`，并在 catch 中用 `e.msg` 提示**。

违反此约定的典型症状：接口 200 但页面空白、`data.list` 为 `undefined`、表格无数据、树形结构不渲染。

## 核心契约（三条铁律）

### 1. 取值：业务数据在 `res.data`

```js
// ❌ 错误：res 是整个信封
const res = await dormitoryApi.getTree()
treeData.value = res          // → { success, msg, data }

// ✅ 正确
const res = await dormitoryApi.getTree()
treeData.value = res?.data || []
```

对象型数据同理：

```js
const rd = (await dormitoryApi.batchCreateBeds({ ss_id, items }))?.data || {}
ElMessage.success(`添加 ${rd.added} 项，跳过 ${rd.skipped} 项`)
```

数组型数据必须给空数组兜底（避免 `v-for` / `.map` / `.length` 报错）：

```js
const list = (await dormitoryApi.getBeds(id))?.data || []
```

对象型数据必须给空对象兜底（避免 `obj.foo` 报错）：

```js
const detail = (await dormitoryStatsApi.getRoomBeds(id))?.data || {}
const cwsl = detail.cwsl || 8
```

### 2. 错误提示：catch 里用 `ElMessage.error(e.msg)`

`request.js` 保证 reject 的对象一定带 `msg` 字段（业务失败取后端 `msg`；网络/超时取本地生成的提示文案）。

```js
try {
  const res = await dormitoryApi.getTree()
  treeData.value = res?.data || []
} catch (e) {
  ElMessage.error(e.msg || '加载失败')
} finally {
  treeLoading.value = false
}
```

**禁止**在 catch 里只写 `console.error(e)` —— 用户看不到任何反馈。

### 3. 成功提示：ElMessage.success + 重新加载

写操作成功后，提示并重新拉取受影响的数据：

```js
ElMessage.success('保存成功')
await loadTree()
```

## 完整模板

```vue
<script setup>
import { ElMessage } from 'element-plus'
import { dormitoryApi } from '@/api/dormitory'

const list = ref([])
const loading = ref(false)

const loadList = async () => {
  loading.value = true
  try {
    const res = await dormitoryApi.getList()
    list.value = res?.data || []
  } catch (e) {
    ElMessage.error(e.msg || '加载失败')
  } finally {
    loading.value = false
  }
}

const save = async (payload) => {
  try {
    await dormitoryApi.create(payload)
    ElMessage.success('保存成功')
    await loadList()
  } catch (e) {
    ElMessage.error(e.msg || '保存失败')
  }
}

const remove = async (id) => {
  ElMessageBox.confirm('确定删除？', '警告', { type: 'warning' }).then(async () => {
    try {
      await dormitoryApi.delete(id)
      ElMessage.success('删除成功')
      await loadList()
    } catch (e) {
      ElMessage.error(e.msg || '删除失败')
    }
  }).catch(() => {})
}
</script>
```

## 常见错误对照表

| 错误写法 | 正确写法 |
|---|---|
| `list.value = await api.getList()` | `list.value = (await api.getList())?.data \|\| []` |
| `const d = await api.getDetail(id)` | `const d = (await api.getDetail(id))?.data \|\| {}` |
| `catch (e) { console.error(e) }` | `catch (e) { ElMessage.error(e.msg \|\| '操作失败') }` |
| `catch (e) { ElMessage.error('操作失败') }` | `catch (e) { ElMessage.error(e.msg \|\| '操作失败') }`（优先用后端具体原因） |
| `const r = await api.create(x); r.added` | `const r = (await api.create(x))?.data \|\| {}; r.added` |
| `if (res.success) { ... }` | `if (res?.success) { ... }`（信封层判断，业务数据仍是 `res.data`） |

## 后端侧约定

新增接口时用 `_ok` / `_err` 助手（`backend/app/core/response.py`）：

```python
from app.core.response import success_response, error_response

def _ok(data=None, msg: str = "操作成功"):
    return success_response(msg=msg, data=data)

def _err(msg: str):
    return error_response(msg=msg)
```

接口写法：

```python
@router.get("/xxx")
async def get_xxx(db: Session = Depends(get_db), _: dict = Depends(require_route_permission())):
    try:
        data = [...]
        return _ok(data=data)
    except Exception as e:
        logger.error(f"获取失败: {e}")
        return _err(f"获取失败: {e}")
```

要点：
- 成功必须 `return _ok(data=业务数据)`，不要裸返回 list/dict（裸返回会绕过信封，前端 `.data` 拿到 undefined）。
- 失败必须 `return _err("具体原因")`，`msg` 会原样显示给用户，写用户能看懂的文案。
- 需要登录的接口加 `_: dict = Depends(require_route_permission())`。

## api 封装层写法

`frontend/src/api/*.js` 只做**路径与参数转发**，不解包、不吞错误：

```js
import instance from '@/utils/request'

export const dormitoryApi = {
  // 后端统一返回 { success, msg, data }，由 vue 页面自行解构 res.data
  getTree: () => instance.tokenGet('/api/v1/dormitory_manage/dormitory/tree'),
  create: (data) => instance.tokenPost('/api/v1/dormitory_manage/dormitory/xxx', data),
}
```

可选的第三个参数是请求配置：

```js
getList: (params) => instance.tokenGet('/api/v1/xxx/list', params, {
  showLoading: true,
  loadingTitle: '加载中...',
})
```

## Blob / 文件下载

下载不走 `.data`（响应是二进制），用 `downloadBlob`：

```js
import { downloadBlob } from '@/utils/request'
const blob = await downloadBlob('/api/v1/xxx/export', { id }, '导出.xlsx')
```

## 自检清单

改动请求相关代码后逐条核对：

- [ ] 所有 `await` 拿到的结果都通过 `?.data` 取值
- [ ] 数组用 `|| []` 兜底，对象用 `|| {}` 兜底
- [ ] 所有 catch 块都有 `ElMessage.error(e.msg || '兜底文案')`，没有裸 `console.error(e)`
- [ ] 写操作成功后调用了 `ElMessage.success` 并重新加载数据
- [ ] 新增后端接口用 `_ok(data=...)` / `_err(msg)` 返回，没有裸返回
- [ ] api 封装层没有做解包、没有 `.catch()` 吞错误

## 参考实现

`frontend/src/views/dormitory_manage/DormitoryManage.vue` 是本标准最完整的参考实现（树形结构、批量操作、弹窗编辑、拖拽排序等场景齐全）。
