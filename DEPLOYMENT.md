# Deployment Information

## Public URL

https://agent-production-d1e50c4d.up.railway.app

## Platform

**Railway**: project `day14-agent`, môi trường `production`, gồm 2 service:

- `agent`: agent Part 6 trong `06-lab-complete/`, build từ `06-lab-complete/Dockerfile` (multi-stage) và deploy bằng `railway up`. File cấu hình nền tảng: `06-lab-complete/railway.toml`.
- `Redis`: Redis do Railway quản lý. Agent dùng nó để lưu state của rate limit và cost guard.

## Test Commands

Không ghi API key vào file này. Trước khi chạy lệnh thứ 4, đặt key vào biến môi trường của terminal (`export AGENT_API_KEY=...` trên bash, `set AGENT_API_KEY=...` trên cmd). Mỗi lệnh chỉ in mã HTTP:

```bash
BASE=https://agent-production-d1e50c4d.up.railway.app
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/health"     # 200
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/ready"      # 200
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" -H 'Content-Type: application/json' -d '{"question":"Hello"}'   # 401
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" -H 'Content-Type: application/json' -H "X-API-Key: $AGENT_API_KEY" -d '{"question":"Hello"}'   # 200
```

Kết quả đo được ngày 2026-11-25 (ảnh: [screenshots/test.png](screenshots/test.png)):

| Lệnh | Mong đợi | Thực tế |
|---|---|---|
| `GET /health` | 200 | 200 |
| `GET /ready` | 200 | 200 |
| `POST /ask` không có key | 401 | 401 |
| `POST /ask` có key | 200 | 200 |

### Health Check

```bash
curl https://agent-production-d1e50c4d.up.railway.app/health
# {"status":"ok","environment":"production","uptime_s":807.7}

curl https://agent-production-d1e50c4d.up.railway.app/ready
# {"status":"ready","redis":"ok"}
```

### API Test (with authentication)

```bash
curl -X POST https://agent-production-d1e50c4d.up.railway.app/ask \
  -H "X-API-Key: $AGENT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"question": "Hello"}'
# {"question":"Hello","answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận.","usage":{"input_tokens":1,"output_tokens":17,"cost_usd":1.035e-05}}
# HTTP 200
```

Không có key, lệnh trên trả `401 {"detail":"Missing or invalid API key"}`.

## Environment Variables Set

Các biến đặt trong tab **Variables** của service `agent` trên Railway (Raw Editor). File này chỉ ghi tên biến, không ghi giá trị của secret.

| Biến | Cách đặt |
|---|---|
| `AGENT_API_KEY` | Secret: key ngẫu nhiên 64 ký tự hex, tạo mới riêng cho bản deploy, không dùng lại key ở local |
| `REDIS_URL` | Biến tham chiếu `${{Redis.REDIS_URL}}`, trỏ tới service Redis trong cùng project |
| `ENVIRONMENT` | `production` |
| `RATE_LIMIT_PER_MINUTE` | `10` |
| `DAILY_BUDGET_USD` | `1.0` |
| `LOG_LEVEL` | `INFO` |
| `PORT` | Railway tự cấp; `CMD` trong Dockerfile đọc `${PORT:-8000}` |

## Screenshots

- [Deployment dashboard](screenshots/dashboard.png): project `day14-agent`, service `agent` và `Redis` đều Online
- [Service running](screenshots/running.png): deployment Active, Deploy Logs có các request `/health`, `/ready`, `/ask`
- [Test results](screenshots/test.png): 4 lệnh tự kiểm trả 200 / 200 / 401 / 200
