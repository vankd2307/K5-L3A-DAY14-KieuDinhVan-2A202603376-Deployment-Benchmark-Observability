"""
Rate limiting (tiêu chí 7).

  • Mỗi API key tối đa RATE_LIMIT_PER_MINUTE request trong 60 giây (sliding window)
  • Vượt giới hạn → HTTP 429 kèm header Retry-After
  • State lưu trong Redis (sorted set, score = thời điểm request) nên mọi worker / instance
    dùng chung và vẫn còn sau khi restart agent
"""
import hashlib
import math
import time
import uuid

from fastapi import HTTPException

from app.config import settings
from app.redis_client import r

WINDOW_SECONDS = 60


def check_rate_limit(key: str) -> None:
    now = time.time()
    # Băm API key để key thô không bao giờ nằm trong Redis.
    bucket = "ratelimit:" + hashlib.sha256(key.encode()).hexdigest()[:16]
    member = f"{now:.6f}:{uuid.uuid4().hex}"

    # pipeline() mặc định là MULTI/EXEC: 4 lệnh chạy liền một khối,
    # 2 worker gọi cùng lúc cũng không đếm sai.
    pipe = r.pipeline()
    pipe.zremrangebyscore(bucket, 0, now - WINDOW_SECONDS)  # bỏ request cũ hơn 60 giây
    pipe.zadd(bucket, {member: now})                        # ghi request hiện tại
    pipe.zcard(bucket)                                      # đếm request trong cửa sổ
    pipe.expire(bucket, WINDOW_SECONDS)                     # key tự xoá khi không còn dùng
    _, _, count, _ = pipe.execute()

    limit = settings.rate_limit_per_minute
    if count > limit:
        r.zrem(bucket, member)  # request bị từ chối không chiếm chỗ trong cửa sổ
        oldest = r.zrange(bucket, 0, 0, withscores=True)
        retry_after = math.ceil(oldest[0][1] + WINDOW_SECONDS - now) if oldest else WINDOW_SECONDS
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded: {limit} requests per minute",
            headers={"Retry-After": str(max(1, retry_after))},
        )
