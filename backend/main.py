from fastapi import FastAPI, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import os
import logging
import sys
from contextlib import asynccontextmanager

# ⚠️ Windows 控制台默认 GBK 代码页，无法表示 ⚠️ ✅ 等字符。
#    打印中文日志时直接抛 UnicodeEncodeError，服务在绑定端口前就死了。
#    强制 stdout/stderr 转 UTF-8，并放宽到 errors="replace"（遇到无法表示的
#    字符用 ? 代替，而不是让整个进程崩溃）。
#    容器里是 Linux + UTF-8 locale，reconfigure 同样无害。
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError, ValueError):
    # Python < 3.7 没有 reconfigure；或 stdout 已被替换成非 TextIOWrapper
    pass

# 日志容错封装：日志目录/文件不可写时不让整个应用启动失败
from utils.log_setup import ensure_log_dir, safe_file_handler

# 导入配置和管理器
from init.config import get_config
from init.app_manager import app_manager
from init.database_optimized import db_manager
from init.redis_manager import redis_manager

# 导入依赖
from init.dependencies import get_admin_user

# 2、注册路由器
from controllers.login import router as login_router
from controllers.CourseManagement import router as course_management_router
from controllers.degree_english import router as degree_router
from controllers.freshman_tuition import router as freshman_tuition_router
from controllers.student_exam import router as student_exam
from controllers.student_zzbm import router as student_zzbm
from controllers.vocational_info import router as vocational_info
from controllers.vocational_tuition import router as vocational_tuition
from controllers.student_info import router as student_info
from controllers.student_info_verify import router as student_info_verify_router
from controllers.student_book_pickup import router as student_book_pickup_router
from controllers.vocational_info_verify import router as vocational_info_verify_router
from controllers.vocational_login import router as vocational_login
from controllers.admin_sms import router as admin_sms
# 腾讯云短信回调（回调地址: POST /sms/callback）
from controllers.sms_callback import router as sms_callback_router
from controllers.photo_upload import router as photo_upload
from controllers.user_avatar import router as user_avatar_router
from controllers.stats import router as stats_router
from controllers.student_leave import router as student_leave_router
from controllers.counsel import router as counsel_router
from controllers.vocational_teacher import router as vocational_teacher_router
from controllers.dormitory import router as dormitory_router
from controllers.student_stay import router as student_stay_router
from controllers.enrollment_webview import router as enrollment_webview_router
from controllers.enrollment_proxy import router as enrollment_proxy_router
from controllers.verification import router as verification_router
from controllers.wx_pay_callback import router as wx_pay_callback_router
from controllers.adult_enrollment import router as adult_enrollment_router
from controllers.graduate_employment_survey import router as graduate_employment_survey_router
from controllers.vocational_34_enrollment import router as vocational_34_enrollment_router
from controllers.job_recommend import router as job_recommend_router
from controllers.bkbk import router as bkbk_router
from controllers.open_teacher import router as open_teacher_router
from controllers.open_teacher_student import router as open_teacher_student_router
from controllers.open_teacher_review import router as open_teacher_review_router
from controllers.open_teacher_info_verify import router as open_teacher_info_verify_router
from controllers.feedback import router as feedback_router
from controllers.survey_fill_controller import router as survey_fill_router
from controllers.enrollment_query import router as enrollment_query_router
from controllers.agent_proxy import router as agent_proxy_router
from controllers.feature_switch import router as feature_switch_router
from controllers.config import router as config_router
from controllers.exame_proxy import router as exame_proxy_router
# 通用手机号快捷认证入口（zhpt-new 内全子系统共享）
from controllers.auth import router as auth_router
# 电表充值（前端按 house_name 完全匹配获取电表信息 + MinIO 预签名二维码）
from controllers.dianbiao import router as dianbiao_router
# MinIO 私有桶 / 公开桶 代理（统一入口，挂根路径，不带 /api/v1 前缀）
from controllers.photo_proxy import router as photo_proxy_router
from controllers.student_bind_openid import router as bind_openid_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 获取配置环境
    config_name = os.getenv('FASTAPI_ENV', 'development')
    config = get_config(config_name)

    # 初始化数据库连接
    try:
        db_manager.init_db(config_name)
        logging.info("✅ Database initialized successfully")

        # 可选：创建数据库表（开发环境）
        if config.app.DEBUG:
            try:
                from init.database_optimized import Base
                # 旧调用名兼容；db_manager 实际暴露的是 create_all()
                if hasattr(db_manager, 'create_tables'):
                    db_manager.create_tables(Base)
                else:
                    db_manager.create_all()
                logging.info("✅ Database tables created/updated (development mode)")
            except Exception as e:
                logging.warning(f"⚠️ Table creation skipped: {e}")

        # 反馈模块种子（字典 + 管理员保底）—— 幂等，失败不阻塞启动
        try:
            from services.feedback_init import run_all_seeds
            from init.database_optimized import db_manager as _dbm
            with _dbm.get_db_session() as _db:
                run_all_seeds(_db)
        except Exception as e:
            logging.warning(f"⚠️ Feedback seeds skipped: {e}")

    except Exception as e:
        logging.error(f"❌ Database initialization failed: {e}")
        raise

    # 初始化其他服务（Redis等）
    await app_manager.initialize(config_name)

    # 将管理器添加到应用状态
    app.state.app_manager = app_manager
    app.state.db_manager = db_manager
    app.state.redis_manager = redis_manager

    yield

    # 关闭时清理资源
    await app_manager.shutdown()
    # DatabaseManager 实际暴露的是 close_all_sessions()/dispose_engine()，
    # 历史遗留的 close_db() 不存在，兼容调用避免退出时 AttributeError。
    try:
        if hasattr(db_manager, 'close_db'):
            db_manager.close_db()
        else:
            db_manager.close_all_sessions()
            db_manager.dispose_engine()
    except Exception as e:
        logging.warning(f"⚠️ DB shutdown skipped: {e}")


def create_app(config_name: str = 'development') -> FastAPI:
    """创建FastAPI应用"""

    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
        ]
    )

    # 获取配置
    config = get_config(config_name)

    # 创建FastAPI应用
    app = FastAPI(
        title="学生综合管理平台",
        description="基于FastAPI和SQLAlchemy的学生综合管理平台",
        version="2.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan
    )

    # 设置默认响应编码为UTF-8
    import json
    from fastapi.encoders import jsonable_encoder

    class UTF8JSONResponse(JSONResponse):
        def render(self, content) -> bytes:
            return json.dumps(
                jsonable_encoder(content),
                ensure_ascii=False,
                allow_nan=False,
                indent=None,
                separators=(",", ":"),
            ).encode("utf-8")

    app.default_response_class = UTF8JSONResponse

    # 全局异常处理
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request, exc):
        """处理HTTP异常"""
        if isinstance(exc.detail, dict) and 'success' in exc.detail:
            return JSONResponse(
                status_code=exc.status_code,
                content=exc.detail
            )

        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "msg": str(exc.detail),
                "data": None
            }
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request, exc):
        """处理请求验证错误"""
        # 处理错误信息，确保可以被 JSON 序列化
        errors = []
        for error in exc.errors():
            error_dict = dict(error)
            # 将 input 字段转换为字符串，避免 bytes 无法序列化
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

    # CORS配置
    if config.app.DEBUG:
        # 开发环境：允许所有来源
        origins = ["*"]
        logging.info("🔓 开发环境：允许所有来源访问")
    else:
        # 生产环境：根据需要配置
        origins = ["*"]
        logging.info(f"🔒 生产环境：限制域名访问 - {len(origins)} 个允许的源")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
        allow_headers=["*"],
        expose_headers=["*"],
        max_age=3600,
    )

    # 注册路由
    app.include_router(login_router)
    app.include_router(course_management_router)
    app.include_router(degree_router)
    app.include_router(freshman_tuition_router)
    app.include_router(student_exam)
    app.include_router(student_zzbm)
    app.include_router(vocational_info)
    
    app.include_router(student_info)
    app.include_router(student_info_verify_router)
    app.include_router(student_book_pickup_router)
    app.include_router(vocational_info_verify_router)
    app.include_router(vocational_login)
    app.include_router(admin_sms)
    app.include_router(sms_callback_router)
    app.include_router(photo_upload)
    app.include_router(user_avatar_router)
    app.include_router(stats_router)
    app.include_router(student_leave_router)
    app.include_router(counsel_router)
    app.include_router(vocational_teacher_router)
    app.include_router(dormitory_router)
    app.include_router(student_stay_router)
    app.include_router(enrollment_proxy_router)
    app.include_router(enrollment_webview_router)
    app.include_router(verification_router)
    app.include_router(vocational_tuition)
    app.include_router(wx_pay_callback_router)
    app.include_router(adult_enrollment_router)
    app.include_router(graduate_employment_survey_router)
    app.include_router(vocational_34_enrollment_router)
    app.include_router(job_recommend_router)
    # 补考费缴纳控制器
    app.include_router(bkbk_router)
    # 开放教育教师控制器
    app.include_router(open_teacher_router)
    app.include_router(open_teacher_student_router)
    app.include_router(open_teacher_review_router)
    app.include_router(open_teacher_info_verify_router)
    # 校园反馈
    app.include_router(feedback_router)
    # 问卷填写端
    app.include_router(survey_fill_router)
    # 报名查询码
    app.include_router(enrollment_query_router)
    # Agent Token代理
    app.include_router(agent_proxy_router)
    # 功能开关
    app.include_router(feature_switch_router)
    # 系统配置
    app.include_router(config_router)
    # exame 考试系统桥接（小程序中职学生调用）
    app.include_router(exame_proxy_router)
    # 通用手机号快捷认证入口（zhpt-new 内全子系统共享）
    app.include_router(auth_router)

    # 电表充值（学生端不需要登录，按 house_name 完全匹配 + MinIO 二维码预签名）
    app.include_router(dianbiao_router)

    
    from controllers.brochure import router as brochure_router
    app.include_router(brochure_router)

    # 背景音乐签名 URL 接口（小程序 InnerAudioContext 直接拉取）
    from controllers.audio import router as audio_router
    app.include_router(audio_router)

    # MinIO 私有桶 / 公开桶 统一代理（挂根路径）
    # 含 /photo/get_headphoto/、/object/、/feedback/、/brochure/image/、/job/image/、
    #    /photo/zs_image/、/static/、/public/
    app.include_router(photo_proxy_router)

    # 学生 openid 补采
    app.include_router(bind_openid_router)

    # 添加访问统计中间件
    from middleware.stats_middleware import StatsMiddleware
    app.add_middleware(StatsMiddleware)

    # 优化的静态文件服务
    uploads_dir = "uploads"
    if not os.path.exists(uploads_dir):
        os.makedirs(uploads_dir)

    # 配置静态文件服务，添加缓存头
    class OptimizedStaticFiles(StaticFiles):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)

        def file_response(self, *args, **kwargs):
            response = super().file_response(*args, **kwargs)
            # 添加缓存头（1小时）
            response.headers["Cache-Control"] = "public, max-age=3600"
            response.headers["X-Content-Type-Options"] = "nosniff"
            return response

    app.mount("/static", OptimizedStaticFiles(directory=uploads_dir), name="static")

    # 健康检查端点（安全版本）
    @app.get("/health")
    async def health_check():
        """健康检查 - 仅返回基本状态"""
        try:
            status = await app_manager.get_health_status()
            return {
                "status": status.get("status", "unknown"),
                "timestamp": status.get("timestamp")
            }
        except Exception as e:
            return {
                "status": "error",
                "timestamp": None
            }



    @app.get("/health/detailed")
    async def detailed_health_check(current_user: dict = Depends(get_admin_user)):
        """详细健康检查 - 需要管理员权限"""
        try:
            return await app_manager.get_detailed_status()
        except Exception as e:
            return {
                "status": "error",
                "error": str(e)
            }



    # 配置生产环境日志
    if not config.app.DEBUG:
        # ⚠️ 容器里日志目录是宿主机 bind mount 进来的，属主 uid 与容器用户
        #    不一致时写不进去。这里用容错封装：拿不到目录就退化成只打 stdout，
        #    **绝不能**因为写不了日志文件让整个 worker 启动失败。
        #    详见 utils/log_setup.py 的说明。
        log_dir = ensure_log_dir()
        logger = logging.getLogger("xjxt")
        logger.setLevel(logging.INFO)

        if log_dir:
            file_handler = safe_file_handler(
                os.path.join(log_dir, 'xjxt.log'),
                max_bytes=10240000,
                backup_count=10,
            )
            if file_handler:
                file_handler.setFormatter(logging.Formatter(
                    '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
                ))
                file_handler.setLevel(logging.INFO)
                logger.addHandler(file_handler)

        logger.info('学籍管理系统启动')

    return app


def main():
    """主函数"""
    # 获取配置环境
    config_name = os.environ.get('FASTAPI_ENV', 'development')

    # 使用全局应用实例
    app = get_app()

    # 获取配置
    config = get_config(config_name)


    if config.app.DEBUG:
        uvicorn.run(
            "main:create_app",
            factory=True,
            host=config.app.HOST,
            port=config.app.PORT,
            reload=False,
            log_level="info"
        )
    else:
        # 生产模式
        if os.environ.get('HTTP_PLATFORM_PORT'):
            # IIS环境
            print("🌐 Running under IIS with uvicorn...")
            print(f"IIS Port: {os.environ.get('HTTP_PLATFORM_PORT')}")
            return app
        else:
            # 其他生产环境
            print("🏭 Starting in production mode with uvicorn...")
            uvicorn.run(
                app,
                host=config.app.HOST,
                port=config.app.PORT,
                log_level="info"
            )


# 全局应用实例
app = None

def get_app():
    """获取应用实例，确保只创建一次"""
    global app
    if app is None:
        config_name = os.environ.get('FASTAPI_ENV', 'development')
        app = create_app(config_name)
    return app

# 创建默认应用实例供uvicorn使用
app = get_app()

if __name__ == "__main__":
    main()
