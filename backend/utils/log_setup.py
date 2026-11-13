"""
日志目录与文件处理器的**容错**封装。

背景
----
容器里应用以非 root 用户（app，uid 1001）运行，``/app/logs`` 通常是宿主机
bind mount 进来的目录。宿主机属主 uid 与容器内 uid 不一致时::

    PermissionError: [Errno 13] Permission denied: '/app/logs/xjxt.log'

这个异常如果发生在 ``main.py`` 的 ``create_app()`` 里，就会让 **gunicorn
worker 启动即崩**，容器陷入「启动 → 崩 → 重启」循环，而日志里只有一行
PermissionError，极难联想到是 uid 不匹配。

所以本模块提供两件东西：

1. :func:`safe_file_handler` —— 创建文件处理器，失败返回 ``None``，
   **绝不**因为写不了日志文件而让业务代码崩溃（退化成只输出到 stdout）。
2. :func:`ensure_log_dir` —— 日志目录创建/可写性检查，同样容错。

配合 ``docker-entrypoint.sh``（以 root 修正挂载目录属主后再降权），
部署端 uid 不匹配的问题也能被自动修掉。
"""

import os
import logging
from logging.handlers import RotatingFileHandler

# 允许用环境变量覆盖日志根目录（挂载点不同时用得上）
LOG_DIR_ENV = 'LOG_DIR'
DEFAULT_LOG_DIR = 'logs'

# 探测结果缓存，避免每次建 handler 都重复做 stat/写测试
_log_dir_cache = None


def get_log_dir() -> str:
    """返回日志根目录（环境变量 LOG_DIR，默认相对当前工作目录的 logs/）。"""
    return os.environ.get(LOG_DIR_ENV) or DEFAULT_LOG_DIR


def ensure_log_dir(log_dir=None) -> str:
    """
    确保日志目录存在且**当前进程可写**。

    返回值
    ------
    str | None
        可写时返回目录路径；不可写时返回 ``None``（调用方应退化为只打 stdout）。
    """
    global _log_dir_cache

    log_dir = log_dir or get_log_dir()

    # 同一进程内目录状态一般不变，缓存探测结果，避免重复 IO
    if _log_dir_cache == log_dir:
        return log_dir

    try:
        os.makedirs(log_dir, exist_ok=True)
    except OSError as e:
        logging.getLogger(__name__).warning(
            '日志目录 %s 创建失败: %s（将只输出到 stdout）', log_dir, e
        )
        return None

    # 目录在、但没有写权限（属主 uid 不匹配 / 只读挂载）→ 提前发现。
    # 用「真实写入一个探针文件」而不是 os.access：
    #   - os.access 用的是**真实 uid** 判断，在某些挂载/ACL 场景会误报；
    #   - 而 write 权限才是我们真正需要的。
    probe = os.path.join(log_dir, '.write_probe')
    try:
        with open(probe, 'w', encoding='utf-8') as f:
            f.write('')
        os.remove(probe)
    except OSError as e:
        logging.getLogger(__name__).warning(
            '日志目录 %s 不可写（属主 uid 与容器用户不匹配？）: %s，将只输出到 stdout',
            log_dir, e,
        )
        return None

    _log_dir_cache = log_dir
    return log_dir


def safe_file_handler(filename, max_bytes=10 * 1024 * 1024, backup_count=5,
                      encoding='utf-8', **kwargs):
    """
    安全地创建 :class:`RotatingFileHandler`。

    - 目录不存在 → 自动创建
    - 目录/文件不可写 → 返回 ``None``，**不抛异常**

    实现要点
    --------
    1. 先用 ``os.open(..., O_APPEND)`` **实际探一次**可写性。
       这一步不能省：``RotatingFileHandler`` 默认在构造时就 open 文件，
       不可写时直接抛 ``PermissionError``（就是原来崩溃的那个点）；
       而 ``delay=True`` 虽然把 open 推迟到首次写入，但那样 handler
       会被成功创建、之后每次写日志都刷一段 "--- Logging error ---"
       堆栈，既吵又没意义。这里用「主动探测 + delay=True」两头兼顾：
       探测失败 → 返回 None，整个 handler 干脆不挂上。

    2. ``delay=True``：真正的 open 推迟到第一次写日志时。即便那之后
       文件句柄出问题，logging 内部只会往 stderr 打印告警，
       不会把业务流程带崩。

    返回值
    ------
    RotatingFileHandler | None
    """
    parent = os.path.dirname(os.path.abspath(filename))
    try:
        if parent:
            os.makedirs(parent, exist_ok=True)

        # ---- 主动探测可写性（这是避免崩溃的关键）----
        probe_fd = os.open(filename, os.O_APPEND | os.O_CREAT, 0o644)
        os.close(probe_fd)

        return RotatingFileHandler(
            filename,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding=encoding,
            delay=True,
            **kwargs,
        )
    except OSError as e:
        logging.getLogger(__name__).warning(
            '日志文件 %s 无法创建（%s），将只输出到 stdout', filename, e
        )
        return None


def safe_append_line(path: str, line: str, encoding: str = 'utf-8') -> bool:
    """
    追加一行文本到文件，失败时静默返回 ``False``（不抛异常）。

    用于短信请求记录、调试日志这类「尽力而为」的旁路日志 ——
    它们不应该影响主流程。
    """
    try:
        parent = os.path.dirname(os.path.abspath(path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, 'a', encoding=encoding) as f:
            f.write(line)
        return True
    except OSError as e:
        logging.getLogger(__name__).warning('写入 %s 失败: %s', path, e)
        return False
