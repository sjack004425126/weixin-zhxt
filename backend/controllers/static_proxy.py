"""
公共静态资源兜底代理（开发/测试环境用）

历史实现：本文件单独定义路由。
重构后：所有桶代理统一在 controllers/photo_proxy.py 维护（公开桶 / 私有桶 都在一处）。

main.py 不再 include_router 这个 stub；`/static/*` 和 `/public/*` 路由由
controllers/photo_proxy.py 注册。

本文件保留为空模块以避免破坏外部 `from controllers.static_proxy import ...` 之类的旧引用。
"""
# 此 router 仅为占位，不应在 main.py 中再 include_router（避免与 photo_proxy 重复注册）
router = None

__all__ = []