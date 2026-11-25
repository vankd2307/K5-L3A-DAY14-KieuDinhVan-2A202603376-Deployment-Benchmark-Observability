"""
Cost guard (tiêu chí 8).

  • Cộng dồn chi phí LLM (tính theo token) vào Redis, theo từng ngày (UTC)
  • Tổng chi phí trong ngày đạt DAILY_BUDGET_USD → HTTP 402
"""
from datetime import datetime, timezone

from fastapi import HTTPException

from app.config import settings
from app.redis_client import r

# Giá USD / 1K tokens (tham khảo gpt-4o-mini)
PRICE_INPUT_PER_1K = 0.00015
PRICE_OUTPUT_PER_1K = 0.0006

BUDGET_KEY_TTL_SECONDS = 2 * 24 * 3600  # giữ key thêm 1 ngày rồi Redis tự xoá


def _budget_key() -> str:
    return f"cost:daily:{datetime.now(timezone.utc):%Y-%m-%d}"


def estimate_tokens(text: str) -> int:
    """Mock LLM không trả usage → ước lượng ~4 ký tự / token."""
    return max(1, len(text) // 4)


def check_budget() -> None:
    """Gọi TRƯỚC khi gọi LLM. Hết budget → raise HTTPException(status_code=402)."""
    spent = float(r.get(_budget_key()) or 0.0)
    if spent >= settings.daily_budget_usd:
        raise HTTPException(
            status_code=402,
            detail=f"Daily budget of {settings.daily_budget_usd} USD exceeded",
        )


def record_cost(input_tokens: int, output_tokens: int) -> float:
    """Gọi SAU khi gọi LLM. Cộng chi phí của request vào tổng, trả về chi phí request."""
    cost = (input_tokens / 1000) * PRICE_INPUT_PER_1K + (output_tokens / 1000) * PRICE_OUTPUT_PER_1K
    key = _budget_key()
    pipe = r.pipeline()
    pipe.incrbyfloat(key, cost)
    pipe.expire(key, BUDGET_KEY_TTL_SECONDS)
    pipe.execute()
    return cost
