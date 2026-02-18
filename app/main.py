import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse

from app.core.config import get_settings
from app.core.database import init_db
from app.core.scheduler import start_scheduler, stop_scheduler
from app.api import share as share_router
from app.api import webpage as webpage_router
from app.api import challenge as challenge_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"ScamVax Backend 启动 (env={settings.app_env})")
    await init_db()
    start_scheduler()
    yield
    stop_scheduler()
    logger.info("ScamVax Backend 已关闭")


app = FastAPI(
    title="ScamVax API",
    description="家庭防骗演习平台后端",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.app_env == "development" else None,
    redoc_url=None,
)

# ─── CORS ─────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.app_env == "development" else [settings.base_url],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# ─── Routers ──────────────────────────────────────────────────────────────────
app.include_router(challenge_router.router)   # POST /create_challenge, GET /c/{id}
app.include_router(share_router.router)       # POST /api/share/create (旧接口保留)
app.include_router(webpage_router.router)     # GET /s/{id} (旧接口保留)


# ─── Health check ─────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    """Render 健康检查 — 返回纯文本 OK"""
    return PlainTextResponse("OK")


# ─── 全局错误处理 ─────────────────────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error(f"未处理异常: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error_code": "INTERNAL_ERROR", "message": "服务器内部错误"},
    )
