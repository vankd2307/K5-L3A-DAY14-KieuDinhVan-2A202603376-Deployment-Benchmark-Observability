# ============================================================
# Production Dockerfile — multi-stage (tiêu chí 1)
#   Stage 1 (builder): cài dependencies vào virtualenv /opt/venv
#   Stage 2 (runtime): chỉ copy venv + code, chạy bằng user non-root
# Build:  docker build -t day14-agent .
# ============================================================

# ── Stage 1: builder ─────────────────────────────────────────
FROM python:3.11-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build
# Copy requirements trước để layer cài package được cache khi chỉ sửa code
COPY requirements.txt .
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install -r requirements.txt

# ── Stage 2: runtime ─────────────────────────────────────────
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    PORT=8000

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin appuser

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY app/ ./app/
COPY utils/ ./utils/

USER appuser

EXPOSE 8000

# Image slim không có curl → kiểm tra /health bằng Python
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT', '8000') + '/health', timeout=3)" || exit 1

# `exec` thay sh bằng uvicorn → uvicorn là PID 1, nhận SIGTERM khi `docker stop`.
# PORT do platform cấp (Railway/Render), mặc định 8000.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 2"]
