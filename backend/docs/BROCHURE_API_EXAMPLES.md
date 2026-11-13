# 招生简章 API 使用示例

## 文件命名规则

### ✅ 有效的文件名（纯数字）
- `1.jpg`
- `2.png`
- `3.gif`
- `10.jpeg`
- `100.jpg`

### ❌ 无效的文件名（会被过滤）
- `street1.png` - 包含字母
- `street2.png` - 包含字母
- `cover.jpg` - 包含字母
- `1a.jpg` - 包含字母
- `a1.jpg` - 包含字母
- `test.png` - 包含字母

## API 接口说明

### 1. 获取招生简章列表

**接口**: `GET /brochure/list/{school_type}`

**支持的类型**:
- `open` - 开放大学
- `vocational` - 中职教育
- `adult` - 成人高考

**示例请求**:
```bash
# 获取成人高考招生简章
curl http://localhost:3050/brochure/list/adult

# 获取开放大学招生简章
curl http://localhost:3050/brochure/list/open

# 获取中职招生简章
curl http://localhost:3050/brochure/list/vocational
```

**响应示例**:
```json
{
  "success": true,
  "msg": "获取成功",
  "data": [
    {
      "name": "1.jpg",
      "path": "brochure/adult/1.jpg",
      "url": "http://localhost:3050/brochure/image/brochure/adult/1.jpg?t=1234567890&s=abc123...",
      "sort": 1
    },
    {
      "name": "2.png",
      "path": "brochure/adult/2.png",
      "url": "http://localhost:3050/brochure/image/brochure/adult/2.png?t=1234567890&s=def456...",
      "sort": 2
    }
  ]
}
```

**注意**: 
- 只返回纯数字命名的图片文件
- 按排序号升序排列
- URL 包含签名，有效期 1 小时

### 2. 上传招生简章图片

**接口**: `POST /brochure/upload/{school_type}`

**参数**:
- `school_type` (路径参数): open/vocational/adult
- `file` (表单文件): 图片文件
- `sort` (表单字段): 排序号（正整数）

**示例请求**:
```bash
# 上传成人高考招生简章第1张图片
curl -X POST http://localhost:3050/brochure/upload/adult \
  -F "file=@/path/to/image.jpg" \
  -F "sort=1"

# 上传第2张图片
curl -X POST http://localhost:3050/brochure/upload/adult \
  -F "file=@/path/to/image.png" \
  -F "sort=2"
```

**响应示例**:
```json
{
  "success": true,
  "msg": "上传成功",
  "data": {
    "name": "1.jpg",
    "path": "brochure/adult/1.jpg",
    "url": "http://localhost:3050/brochure/image/brochure/adult/1.jpg?t=1234567890&s=abc123..."
  }
}
```

**注意**:
- 文件会被重命名为 `{sort}.{ext}`
- 如果同名文件已存在，会被覆盖
- `sort` 必须是正整数（> 0）

### 3. 删除招生简章图片

**接口**: `DELETE /brochure/delete/{school_type}/{filename}`

**示例请求**:
```bash
# 删除成人高考招生简章的第1张图片
curl -X DELETE http://localhost:3050/brochure/delete/adult/1.jpg

# 删除第2张图片
curl -X DELETE http://localhost:3050/brochure/delete/adult/2.png
```

**响应示例**:
```json
{
  "success": true,
  "msg": "删除成功",
  "data": null
}
```

### 4. 重新排序招生简章图片

**接口**: `POST /brochure/reorder/{school_type}`

**请求体**:
```json
[
  {
    "old_name": "2.jpg",
    "new_sort": 1
  },
  {
    "old_name": "1.jpg",
    "new_sort": 2
  }
]
```

**示例请求**:
```bash
curl -X POST http://localhost:3050/brochure/reorder/adult \
  -H "Content-Type: application/json" \
  -d '[
    {"old_name": "2.jpg", "new_sort": 1},
    {"old_name": "1.jpg", "new_sort": 2}
  ]'
```

**响应示例**:
```json
{
  "success": true,
  "msg": "排序成功",
  "data": null
}
```

## MinIO 直接上传

如果直接在 MinIO 中上传文件，请遵循以下规则：

### 目录结构
```
zhpt-bucket/
  └── brochure/
      ├── open/          # 开放大学
      │   ├── 1.jpg
      │   ├── 2.jpg
      │   └── 3.png
      ├── vocational/    # 中职教育
      │   ├── 1.jpg
      │   └── 2.jpg
      └── adult/         # 成人高考
          ├── 1.jpg
          ├── 2.png
          └── 3.jpg
```

### 上传步骤
1. 登录 MinIO 控制台
2. 进入 `zhpt-bucket` 存储桶
3. 导航到对应目录（如 `brochure/adult/`）
4. 上传图片文件
5. **重要**: 将文件重命名为纯数字格式（如 `1.jpg`, `2.png`）

### 验证上传
上传完成后，访问 API 接口验证：
```bash
curl http://localhost:3050/brochure/list/adult
```

应该能看到刚上传的图片列表。

## 常见问题

### Q: 为什么我的图片没有显示？
A: 检查文件名是否为纯数字格式。`street1.png` 不会显示，需要重命名为 `1.png`。

### Q: 如何修改图片顺序？
A: 使用重新排序接口，或者直接在 MinIO 中重命名文件。

### Q: 支持哪些图片格式？
A: 支持 `.jpg`, `.jpeg`, `.png`, `.gif` 格式。

### Q: 图片 URL 为什么会过期？
A: 为了安全，图片 URL 包含签名，有效期 1 小时。前端会自动处理刷新。

### Q: 可以上传视频吗？
A: 目前只支持图片格式，不支持视频。
