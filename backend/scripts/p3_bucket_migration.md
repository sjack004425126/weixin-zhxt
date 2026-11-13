# P3 桶迁移操作手册（短暂停机直迁版）

> 约定：业务允许**短时停机**（预计 5-30 分钟，视对象数量）。
> 策略：停业务 → 一次性 `mc mirror` 全量 → 改 `.env` → 起业务 → 核验 → 删老桶。

---

## 0. 前置准备

```bash
# 新桶已建
mc ls zhpt/ | grep guizhou-zhpt-prod-private

# 当前老桶大小记录下来（备份后对比用）
mc du zhpt/headphoto
#   示例输出:  12 GiB  4521 objects

# 发布维护公告（建议避开业务高峰，例如深夜/早上 6 点前）
```

---

## 1. 停业务

```bash
# 停掉后端（按你实际进程管理方式）
systemctl stop zhpt-backend
# 或: pm2 stop zhpt-backend  /  kill <uvicorn_pid>

# 可选: nginx 返回维护页，避免前端报错给用户看
```

---

## 2. 全量 mirror 到新桶

```bash
# 关键：--preserve 保留元数据；--overwrite 覆盖（首次为空等价无效）
mc mirror --preserve --overwrite zhpt/headphoto zhpt/guizhou-zhpt-prod-private

# 等进度条跑完，记录最终对象数与总大小
```

## 3. 核验两桶一致

```bash
# 大小和对象数应基本一致
mc du zhpt/headphoto
mc du zhpt/guizhou-zhpt-prod-private

# 严格 diff
mc diff zhpt/headphoto zhpt/guizhou-zhpt-prod-private
#   期望: 无输出；有 < 表示新桶缺失，需要重跑 mirror
#   ">" 表示新桶多出来（首次不会有）
```

如有 `<` 缺失，再跑一次 `mc mirror` 补齐后重 diff，直到无差异。

---

## 4. 切 `.env` 到新桶 + service account

编辑 `backend/.env`：

```diff
- MINIO_ACCESS_KEY=flysky
- MINIO_SECRET_KEY=Skh@004425
+ MINIO_ACCESS_KEY=ZXU2KINV0UJ2D9CTW65H
+ MINIO_SECRET_KEY=L+ypCx0aCJXpcevt0Xqe9WhUiGijVx7a9ogaUV2b

- MINIO_BUCKET=headphoto
- MINIO_BUCKET_PRIVATE=headphoto
+ MINIO_BUCKET=guizhou-zhpt-prod-private
+ MINIO_BUCKET_PRIVATE=guizhou-zhpt-prod-private
```

`MINIO_BUCKET_PUBLIC` 保持 `guizhou-zhpt-prod-public`。

---

## 5. 起业务

```bash
systemctl start zhpt-backend
# 或你的启动方式

# 看日志确认没有 MinIO 连接错误
tail -f /path/to/backend.log
```

## 6. 业务验证清单

逐项人工验证（推荐用微信开发者工具）：

- [ ] 学生登录后能看到**自己的头像**（photo_upload → 新桶）
- [ ] 打开招生简章页，**中职 / 开大 / 成人高考**三个都能加载全部图片
- [ ] 打开就业推荐文章，**文章配图**正常显示
- [ ] 3+4 报名页、成人高考报名页，**上传一张新图**看是否存入新桶：
  ```bash
  mc ls zhpt/guizhou-zhpt-prod-private/zs/ | head
  # 应该能看到新上传的文件
  ```
- [ ] 随机抽一个学生删除头像 → 重新上传，确认流程通

全部通过后 → 恢复维护公告。

---

## 7. 回滚预案（仅 cutover 后问题时用）

如果第 5 步起业务后发现严重问题（图片大面积 404 等），立刻回滚：

```diff
- MINIO_BUCKET=guizhou-zhpt-prod-private
- MINIO_BUCKET_PRIVATE=guizhou-zhpt-prod-private
+ MINIO_BUCKET=headphoto
+ MINIO_BUCKET_PRIVATE=headphoto

- MINIO_ACCESS_KEY=ZXU2KINV0UJ2D9CTW65H
- MINIO_SECRET_KEY=L+ypCx0aCJXpcevt0Xqe9WhUiGijVx7a9ogaUV2b
+ MINIO_ACCESS_KEY=flysky
+ MINIO_SECRET_KEY=Skh@004425
```

重启后端即回到停机前的状态（老桶完全没动过，数据完整）。

如果已经有**新写入进入新桶**，这些新对象还在新桶里不会丢失，待下次重新切桶时会继续可见；但在老桶运行期间暂时看不到这几条。

---

## 8. 删老桶（稳定运行若干天后）

建议**至少稳定运行 7 天 + 做一次完整备份**再删：

```bash
# 1) 本地备份（万一要回溯）
mkdir -p /backup/minio/headphoto-$(date +%Y%m%d)
mc mirror --preserve zhpt/headphoto /backup/minio/headphoto-$(date +%Y%m%d)/

# 2) 把老桶置不可写（预防误操作）
mc anonymous set none zhpt/headphoto

# 3) 彻底删除老桶（不可恢复！）
mc rb --force zhpt/headphoto
```

---

## 总耗时估算

| 对象数 | 网络 | 预计 mirror 时间 | 总停机时间 |
|---|---|---|---|
| < 1k | 内网千兆 | < 1 分钟 | 5-8 分钟 |
| 1k-10k | 内网千兆 | 2-5 分钟 | 8-15 分钟 |
| 10k-100k | 内网千兆 | 10-30 分钟 | 20-40 分钟 |

实际耗时以 `mc mirror` 输出的进度条为准。

---

## 与 Phase A（已撤销）的区别

原 dual-read 方案代码已全部撤销，现在代码和 P2 结束时完全一致，即：
- 读写都走 `MINIO_BUCKET` 单桶
- 切桶通过改 `.env` + 重启生效
- 没有回源逻辑，cutover 完成后不再有任何 legacy 分支
