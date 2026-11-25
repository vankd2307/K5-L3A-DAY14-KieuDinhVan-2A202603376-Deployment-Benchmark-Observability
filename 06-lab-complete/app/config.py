"""
Config — 12-Factor: mọi cấu hình đọc từ biến môi trường (tiêu chí 9).

  • Mỗi giá trị đọc từ env lúc khởi tạo Settings, có mặc định hợp lý khi chạy local.
  • Không hard-code secret: AGENT_API_KEY mặc định là chuỗi rỗng → mọi request /ask bị 401
    cho tới khi đặt key thật bằng biến môi trường (fail closed).
  • Danh sách biến đầy đủ nằm trong .env.example.
"""
import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    port: int = field(default_factory=lambda: int(os.getenv("PORT", "8000")))
    environment: str = field(default_factory=lambda: os.getenv("ENVIRONMENT", "development"))
    agent_api_key: str = field(default_factory=lambda: os.getenv("AGENT_API_KEY", ""))
    redis_url: str = field(default_factory=lambda: os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    rate_limit_per_minute: int = field(
        default_factory=lambda: int(os.getenv("RATE_LIMIT_PER_MINUTE", "10")))
    daily_budget_usd: float = field(
        default_factory=lambda: float(os.getenv("DAILY_BUDGET_USD", "1.0")))
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO").upper())


settings = Settings()
