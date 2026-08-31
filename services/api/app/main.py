import asyncio
from contextlib import asynccontextmanager, suppress
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import get_settings
from .database import create_schema
from .errors import AppError
from .jobs import care_report_scheduler
from .routers import (
    admin,
    auth,
    care,
    consents,
    conversations,
    families,
    knowledge,
    media,
    realtime,
    reminders,
    styles,
    voice,
)
from .schemas import HealthOut

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    if not settings.is_local and settings.app_secret_key == "guiyin-local-secret-change-me":
        raise RuntimeError("Non-local deployments must configure APP_SECRET_KEY")
    create_schema()
    scheduler_task = None
    if settings.background_jobs_enabled and settings.app_env != "test":
        scheduler_task = asyncio.create_task(
            care_report_scheduler(settings.report_scheduler_interval_seconds)
        )
    yield
    if scheduler_task is not None:
        scheduler_task.cancel()
        with suppress(asyncio.CancelledError):
            await scheduler_task


app = FastAPI(
    title=settings.app_name,
    version="0.2.0",
    description="归音家庭情感协同 AI App 本地完整 MVP API",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def trace_middleware(request: Request, call_next):
    trace_id = request.headers.get("X-Trace-ID") or str(uuid4())
    request.state.trace_id = trace_id
    response = await call_next(request)
    response.headers["X-Trace-ID"] = trace_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), geolocation=()"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "trace_id": getattr(request.state, "trace_id", str(uuid4())),
                "details": exc.details,
            }
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    details = [
        {"location": list(error["loc"]), "message": error["msg"], "type": error["type"]}
        for error in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "请求参数不正确",
                "trace_id": getattr(request.state, "trace_id", str(uuid4())),
                "details": {"items": details},
            }
        },
    )


@app.get("/health", response_model=HealthOut, tags=["system"])
def health() -> HealthOut:
    provider = settings.ai_provider if settings.ai_api_key else "demo"
    return HealthOut(status="ok", environment=settings.app_env, ai_provider=provider)


API_PREFIX = "/api/v1"
app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(auth.me_router, prefix=API_PREFIX)
app.include_router(families.router, prefix=API_PREFIX)
app.include_router(consents.router, prefix=API_PREFIX)
app.include_router(conversations.router, prefix=API_PREFIX)
app.include_router(realtime.router, prefix=API_PREFIX)
app.include_router(knowledge.router, prefix=API_PREFIX)
app.include_router(media.router, prefix=API_PREFIX)
app.include_router(care.router, prefix=API_PREFIX)
app.include_router(reminders.router, prefix=API_PREFIX)
app.include_router(voice.router, prefix=API_PREFIX)
app.include_router(styles.router, prefix=API_PREFIX)
app.include_router(admin.router, prefix=API_PREFIX)
