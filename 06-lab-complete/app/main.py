"""
Production AI Agent — Part 6 Final Project.

  • GET  /health : liveness, luôn 200 khi process còn chạy (không phụ thuộc Redis)
  • GET  /ready  : readiness, 503 khi Redis không kết nối được
  • POST /ask    : API key (401) → rate limit (429) → cost guard (402) → mock LLM
  • Log          : mỗi dòng log của app là 1 JSON object
  • Shutdown     : uvicorn xử lý SIGTERM (ngừng nhận request mới, chờ request đang chạy xong),
                   lifespan ghi log và đóng kết nối Redis trước khi thoát

Kiểm tra:  python check_production_ready.py
"""
import json
import logging
import sys
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import redis
from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.auth import verify_api_key
from app.config import settings
from app.cost_guard import check_budget, estimate_tokens, record_cost
from app.rate_limiter import check_rate_limit
from app.redis_client import r, redis_healthy
from utils.mock_llm import ask as llm_ask

# ─────────────────────────────────────────────────────────
# Structured logging (tiêu chí 10): mỗi dòng log là 1 JSON object
# ─────────────────────────────────────────────────────────
_STANDARD_ATTRS = set(vars(logging.makeLogRecord({}))) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(timespec="milliseconds"),
            "lvl": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        # Các field truyền qua logger.info(..., extra={...})
        for key, value in vars(record).items():
            if key not in _STANDARD_ATTRS and key not in payload:
                payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(JsonFormatter())
_level = logging.getLevelName(settings.log_level)
logging.basicConfig(level=_level if isinstance(_level, int) else logging.INFO,
                    handlers=[_handler], force=True)
logger = logging.getLogger("agent")

STARTED_AT = time.time()


# ─────────────────────────────────────────────────────────
# Graceful shutdown (tiêu chí 11)
# Khi nhận SIGTERM, uvicorn ngừng nhận request mới và chờ request đang chạy trả xong,
# rồi mới chạy phần sau `yield`. Không tự đăng ký signal handler để khỏi chặn handler của uvicorn.
# ─────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("startup", extra={"environment": settings.environment, "port": settings.port,
                                  "rate_limit_per_minute": settings.rate_limit_per_minute})
    if not settings.agent_api_key:
        logger.warning("agent_api_key_not_set")  # mọi request /ask sẽ bị 401
    yield
    logger.info("shutdown", extra={"uptime_s": round(time.time() - STARTED_AT, 1)})
    try:
        r.close()
    except redis.RedisError:
        pass


app = FastAPI(title="Production AI Agent", lifespan=lifespan)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        # Lỗi không lường trước: traceback chỉ nằm trong log JSON, client nhận thông báo gọn.
        logger.exception("unhandled_error", extra={"method": request.method, "path": request.url.path})
        response = JSONResponse(status_code=500, content={"detail": "Internal server error"})
    # Không log API key hay nội dung câu hỏi.
    logger.info("request", extra={
        "method": request.method,
        "path": request.url.path,
        "status": response.status_code,
        "ms": round((time.perf_counter() - start) * 1000, 1),
    })
    return response


@app.exception_handler(redis.RedisError)
async def redis_unavailable(request: Request, exc: redis.RedisError):
    logger.error("redis_unavailable", extra={"path": request.url.path, "error": type(exc).__name__})
    return JSONResponse(status_code=503,
                        content={"detail": "Service temporarily unavailable, please retry"},
                        headers={"Retry-After": "5"})


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    user_id: str | None = Field(default=None, max_length=128)


@app.get("/health")
def health():
    """Liveness: process còn chạy là 200, không kiểm tra Redis."""
    return {"status": "ok", "environment": settings.environment,
            "uptime_s": round(time.time() - STARTED_AT, 1)}


@app.get("/ready")
def ready():
    """Readiness: chỉ nhận traffic khi Redis (state của rate limit và cost guard) kết nối được."""
    if not redis_healthy():
        return JSONResponse(status_code=503, content={"status": "not ready", "redis": "unreachable"})
    return {"status": "ready", "redis": "ok"}


@app.post("/ask")
def ask(body: AskRequest, api_key: str = Depends(verify_api_key)):
    check_rate_limit(api_key)   # vượt giới hạn → 429
    check_budget()              # hết budget → 402
    answer = llm_ask(body.question)
    input_tokens = estimate_tokens(body.question)
    output_tokens = estimate_tokens(answer)
    cost = record_cost(input_tokens, output_tokens)
    return {
        "question": body.question,
        "answer": answer,
        "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens,
                  "cost_usd": round(cost, 8)},
    }
