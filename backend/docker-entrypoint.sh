#!/bin/sh
# ============================================================
# zhpt-backend 容器入口脚本
#
# 存在的唯一理由：解决 bind mount 的**属主 uid 不匹配**导致的启动失败。
#
# 现象（容器反复重启，日志只有一行）：
#     PermissionError: [Errno 13] Permission denied: '/app/logs/xjxt.log'
#
# 根因：
#     /app/logs、/app/uploads、/app/data 是宿主机目录 bind mount 进来的。
#     宿主机上这些目录的属主 uid（宝塔站点用户通常是 1001），
#     必须与容器内 app 用户的 uid 一致，否则非 root 的 app 用户写不进去。
#     镜像里的 `chown` 只对镜像层内的目录有效，
#     **对 bind mount 进来的目录无效**（bind mount 会覆盖镜像层）。
#
# 本脚本的做法：
#     1. 以 root 进入容器（USER root）
#     2. 把挂载目录的属主修正成 APP_UID:APP_GID
#     3. 再降权回 app 用户执行真正的启动命令
#
# ⚠️ 宿主机目录属主如果本来就不是 root，改属主会影响宿主机上的文件属主。
#    对 logs/ uploads/ data/ 这类应用专用目录来说这是期望行为。
#    如果宿主机目录必须保持原属主，把环境变量 FIX_MOUNT_OWNER 设为 0 即可跳过修正。
# ============================================================

set -e

# ⚠️ 降权目标 uid **必须**与要 chown 的目标 uid 一致，否则改完属主照样写不了。
#    这里不信任环境变量的默认值，直接从容器内的 app 用户取实际 uid/gid ——
#    这是唯一能保证「chown 的属主 == 运行进程的 uid」的来源。
#
#    历史事故（2026-11-03 headphoto）：
#      Dockerfile 用 `useradd -r` → app 的 uid 动态分配成 999
#      而 APP_UID 环境变量写的是 1001
#      结果：chown 把目录改成 1001，进程却跑在 999 → 依然无写权限
#            sqlite3.OperationalError: attempt to write a readonly database
if id app >/dev/null 2>&1; then
    DEFAULT_APP_UID="$(id -u app)"
    DEFAULT_APP_GID="$(id -g app)"
else
    DEFAULT_APP_UID="1001"
    DEFAULT_APP_GID="1001"
fi

# 允许环境变量覆盖（一般不需要；改了必须与镜像内 app 的 uid 一致）
APP_UID="${APP_UID:-$DEFAULT_APP_UID}"
APP_GID="${APP_GID:-$DEFAULT_APP_GID}"
FIX_MOUNT_OWNER="${FIX_MOUNT_OWNER:-1}"

# 需要修正属主的运行期目录
RUNTIME_DIRS="/app/logs /app/uploads /app/data"

if [ "$(id -u)" = "0" ] && [ "$FIX_MOUNT_OWNER" = "1" ]; then
    echo ">>> [entrypoint] 以 root 进入，修正挂载目录属主为 ${APP_UID}:${APP_GID}"

    for d in $RUNTIME_DIRS; do
        if [ -d "$d" ]; then
            # 目录不存在时创建，并设为 0775（属主可写、同组可读）
            mkdir -p "$d"
            current_owner="$(stat -c '%u:%g' "$d" 2>/dev/null || echo 'unknown')"
            if [ "$current_owner" != "${APP_UID}:${APP_GID}" ]; then
                chown -R "${APP_UID}:${APP_GID}" "$d" 2>/dev/null || \
                    echo ">>> [entrypoint] ⚠️ chown $d 失败（权限不足），继续尝试启动"
                # 属主改不了时至少保证目录本身可进入
                chmod 0775 "$d" 2>/dev/null || true
                echo ">>> [entrypoint]    $d: $current_owner -> ${APP_UID}:${APP_GID}"
            else
                echo ">>> [entrypoint]    $d: 属主已正确 ($current_owner)"
            fi
        else
            echo ">>> [entrypoint] ⚠️ $d 不存在，跳过"
        fi
    done

    # 降权回 app 用户
    if id app >/dev/null 2>&1; then
        echo ">>> [entrypoint] 降权为 app 用户 (uid=$(id -u app))"
        # setpriv 来自 util-linux（debian slim 已内置）；
        # 万一不可用则回退到 su，仍可正常运行（只是降权方式不同）。
        if command -v setpriv >/dev/null 2>&1; then
            exec setpriv --reuid=app --regid=app --init-groups "$@"
        elif command -v su >/dev/null 2>&1; then
            exec su -s /bin/sh -c 'exec "$@"' -- app "$@"
        else
            echo ">>> [entrypoint] ⚠️ 没有 setpriv/su，以 root 继续执行"
        fi
    else
        echo ">>> [entrypoint] ⚠️ 容器内没有 app 用户，以 root 继续执行"
    fi
fi

exec "$@"
