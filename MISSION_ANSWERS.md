# Day 14 Lab — Mission Answers

---

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns trong `01-localhost-vs-production/develop/app.py`

| # | Anti-pattern | Dòng code | Vì sao nguy hiểm |
|---|---|---|---|
| 1 | Hardcode secret | `OPENAI_API_KEY = "sk-hardcoded-fake-key-never-do-this"` (dòng 17), `DATABASE_URL = "postgresql://admin:password123@..."` (dòng 18) | Push lên GitHub là lộ key và mật khẩu DB; muốn đổi key phải sửa code và deploy lại |
| 2 | Log ra secret | `print(f"[DEBUG] Using key: {OPENAI_API_KEY}")` (dòng 34) | Key nằm trong log, ai đọc được log (hoặc hệ thống gom log) đều thấy key |
| 3 | Dùng `print()` thay cho logging | dòng 33, 34, 38 | Không có level, không có cấu trúc JSON nên không lọc, tìm kiếm, cảnh báo được; log cả nội dung câu hỏi của người dùng |
| 4 | Không có config management | `DEBUG = True`, `MAX_TOKENS = 500` (dòng 21–22) | Cùng một code không chạy được ở dev và production với cấu hình khác nhau; DEBUG bật cả trên production |
| 5 | Không có health check | không có `/health` (gọi thử trả 404) | Platform không biết agent còn sống hay đã treo để restart |
| 6 | Bind `localhost` và port cứng | `host="localhost"`, `port=8000` (dòng 51–52) | Trong container, `localhost` không nhận kết nối từ ngoài; Railway/Render cấp port qua biến `PORT` nên app không nhận được traffic |
| 7 | `reload=True` | dòng 53 | Chế độ dev: tốn tài nguyên theo dõi file, không dành cho production |
| 8 | Không xử lý shutdown | không có lifespan hay xử lý SIGTERM | Khi platform tắt container, request đang chạy có thể bị cắt ngang |

### Exercise 1.2: Chạy bản develop

```text
$ curl -X POST "http://localhost:8000/ask?question=Hello"
{"answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic."}

$ curl http://localhost:8000/health
{"detail":"Not Found"}  [HTTP 404]

--- log của server (print ra cả secret) ---
[DEBUG] Got question: Hello
[DEBUG] Using key: sk-hardcoded-fake-key-never-do-this
[DEBUG] Response: Đây là câu trả lời từ AI agent (mock). ...
```

App chạy được, nhưng chưa sẵn sàng cho production: không có health check và log lộ cả API key.

Bản production chạy cùng câu hỏi:

```text
$ curl -X POST http://localhost:8000/ask -H "Content-Type: application/json" -d '{"question":"Hello"}'
{"question":"Hello","answer":"Đây là câu trả lời từ AI agent (mock). ...","model":"gpt-4o-mini"}
$ curl http://localhost:8000/health
{"status":"ok","uptime_seconds":3.9,"version":"1.0.0","environment":"development","timestamp":"2026-11-25T10:01:50.716602+00:00"}
$ curl http://localhost:8000/ready
{"ready":true}
```

### Exercise 1.3: So sánh develop và production

| Feature | Develop | Production | Vì sao quan trọng? |
|---|---|---|---|
| Config | Hardcode trong code (`DEBUG`, key, DB URL) | Đọc từ biến môi trường qua `config.py` (`settings`) | Một image chạy được ở mọi môi trường; secret không nằm trong code và git |
| Secret | Ghi thẳng và còn in ra log | Lấy từ env, không log secret (chỉ log độ dài câu hỏi) | Lộ key = mất tiền và mất dữ liệu; log thường được nhiều người và hệ thống đọc |
| Health check | Không có (404) | `/health` (liveness) và `/ready` (readiness) | Platform biết khi nào restart container, load balancer biết khi nào ngừng gửi traffic |
| Logging | `print()` | Log JSON có cấu trúc | Dễ parse, lọc, tìm kiếm và cảnh báo trong hệ thống gom log |
| Host / port | `localhost:8000` cứng | `0.0.0.0` và `PORT` từ env | Chạy được trong container và trên cloud, nơi platform cấp port |
| Shutdown | Đột ngột | Graceful: lifespan + xử lý SIGTERM | Không cắt ngang request đang chạy khi deploy bản mới hoặc scale xuống |

---

## Part 2: Docker

### Exercise 2.1: Câu hỏi về `02-docker/develop/Dockerfile`

1. **Base image:** `python:3.11`, bản Python đầy đủ (gồm cả compiler và nhiều thư viện hệ thống), nên image rất nặng.
2. **Working directory:** `/app`. Các lệnh `COPY`, `RUN`, `CMD` sau đó đều chạy trong thư mục này.
3. **Vì sao `COPY requirements.txt` trước:** để tận dụng layer cache. Layer `pip install` chỉ build lại khi `requirements.txt` đổi; sửa code (`app.py`) thì Docker dùng lại layer đã cài package, build nhanh hơn nhiều.
4. **CMD khác ENTRYPOINT:** `CMD` là lệnh mặc định, bị thay thế khi truyền lệnh khác lúc `docker run <image> <lệnh>`. `ENTRYPOINT` là lệnh cố định của container; tham số truyền vào `docker run` được nối thêm vào sau nó. Thường dùng `ENTRYPOINT` cho chương trình chính và `CMD` cho tham số mặc định.

### Exercise 2.2: Build và chạy bản develop

```text
$ docker build -f 02-docker/develop/Dockerfile -t my-agent:develop .
$ docker run -p 8000:8000 my-agent:develop
$ curl -X POST "http://localhost:8000/ask?question=What is Docker?"
{"answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!"}
$ curl http://localhost:8000/health
{"status":"ok","uptime_seconds":3.9,"container":true}
```

### Exercise 2.3: Multi-stage build

- **Stage 1 (builder):** dùng `python:3.11-slim`, cài thêm `gcc`, `libpq-dev` để build package, rồi `pip install --user` vào `/root/.local`. Stage này không được dùng để deploy.
- **Stage 2 (runtime):** lại bắt đầu từ `python:3.11-slim` sạch, chỉ copy thư mục package đã cài từ builder và code; tạo user `appuser` không phải root, có `HEALTHCHECK`.
- **Vì sao image nhỏ hơn:** image cuối không chứa compiler, header, cache apt/pip của bước build; base là bản `slim` thay vì bản đầy đủ.

Đo bằng `docker images` trên máy (Docker Desktop 28.0.4):

| Image | Size |
|---|---|
| `my-agent:develop` | 1.67 GB |
| `my-agent:advanced` | 240 MB |
| Chênh lệch | nhỏ hơn ~85.6% (1670 MB → 240 MB) |

### Exercise 2.4: Docker Compose stack

```text
Client ──HTTP :80──▶ Nginx (reverse proxy / load balancer)
                       │  proxy_pass http://agent_backend (agent:8000)
                       ▼
                    Agent (FastAPI, uvicorn 2 workers)
                     │                      │
          redis://redis:6379/0     http://qdrant:6333
                     ▼                      ▼
               Redis (cache/session)   Qdrant (vector DB)
          ── tất cả nằm trong network bridge "internal" ──
```

- **Những service được start:** `agent`, `redis`, `qdrant`, `nginx`. Chỉ Nginx mở port ra ngoài (80, 443); agent, Redis, Qdrant chỉ nằm trong network nội bộ.
- **Cách các service giao tiếp:** gọi nhau bằng tên service qua DNS của Docker (`agent:8000`, `redis:6379`, `qdrant:6333`). Agent chỉ start sau khi Redis và Qdrant healthy (`depends_on: condition: service_healthy`).

```text
$ docker compose -p k5-day14-docker ps
SERVICE   STATUS                    PORTS
agent     Up 8 seconds (healthy)    8000/tcp
nginx     Up 8 seconds              0.0.0.0:80->80/tcp, 0.0.0.0:443->443/tcp
qdrant    Up 19 seconds (healthy)   6333-6334/tcp
redis     Up 19 seconds (healthy)   6379/tcp

$ curl -i http://localhost/health
HTTP/1.1 200 OK
{"status":"ok","uptime_seconds":7.2,"version":"2.0.0","timestamp":"2026-11-25T10:04:27.009442"}

$ curl -X POST http://localhost/ask -H "Content-Type: application/json" -d '{"question":"Explain microservices"}'
{"answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}
```

---

## Part 3: Cloud Deployment

### Exercise 3.1 / 3.2: Deploy agent Part 6

Mình deploy chính agent Part 6 (`06-lab-complete/`), không deploy app mẫu. Chi tiết ghi trong `DEPLOYMENT.md`.

- **Nền tảng:** Railway. Project `day14-agent` có 2 service: `agent` (build từ `06-lab-complete/Dockerfile`, deploy bằng `railway up`) và `Redis` (Redis của Railway, nối qua biến `REDIS_URL=${{Redis.REDIS_URL}}`). `AGENT_API_KEY` và các biến khác đặt trong tab Variables, không ghi trong code.
- **URL public:** https://agent-production-d1e50c4d.up.railway.app
- **Mã HTTP của 4 lệnh tự kiểm ở CP6:** `/health` **200**, `/ready` **200** (`{"status":"ready","redis":"ok"}`), `/ask` không key **401**, `/ask` có key **200**
- **Ảnh:** [dashboard](screenshots/dashboard.png) · [running](screenshots/running.png) · [test](screenshots/test.png)

### Nền tảng còn lại: so sánh `railway.toml` và `render.yaml`

Hai file nằm trong `06-lab-complete/`. Mình chọn cách so sánh thay cho deploy thêm lên nền tảng thứ hai.

| Điểm so sánh | `railway.toml` | `render.yaml` |
|---|---|---|
| Định dạng, phạm vi | TOML, cấu hình **một service** (service đang deploy) | YAML Blueprint, mô tả **cả hạ tầng**: web service + Redis (Key Value) trong một file |
| Cách build | `[build] builder = "DOCKERFILE"`, `dockerfilePath` | `runtime: docker`, `rootDir: 06-lab-complete`, `dockerfilePath`, `dockerContext` (vì file nằm trong thư mục con của repo) |
| Cách deploy | `railway up` từ CLI, upload thư mục hiện tại | Render kéo code từ GitHub (New → Blueprint), tự deploy lại khi push |
| Health check | `healthcheckPath = "/health"`, `healthcheckTimeout = 100` | `healthCheckPath: /health` |
| Restart | `restartPolicyType = "ON_FAILURE"`, tối đa 3 lần | Render tự quản lý, không cấu hình trong file |
| Biến môi trường / secret | **Không** khai báo trong file; đặt trên dashboard hoặc `railway variables` | Khai báo trong `envVars`; secret `AGENT_API_KEY` dùng `sync: false` để Render hỏi giá trị lúc tạo, không ghi thẳng vào file |
| Redis | Tạo riêng trên dashboard, nối bằng biến tham chiếu `${{Redis.REDIS_URL}}` | Khai báo service `type: keyvalue` ngay trong file, `REDIS_URL` lấy qua `fromService ... property: connectionString` |
| Port | Railway cấp `PORT`, Dockerfile đọc `${PORT:-8000}` | Render cũng cấp `PORT`, dùng chung Dockerfile |
| Gói | Trial/credit | `plan: free` khai báo trong file |

Vì sao khác nhau: Railway theo hướng "deploy nhanh từ CLI", file config chỉ chứa cách build và chạy một service, còn biến và database cấu hình trên dashboard. Render theo hướng **infrastructure as code**: Blueprint mô tả đủ mọi service và cách chúng nối với nhau, nên tạo lại toàn bộ hệ thống từ repo được; vì file nằm trong git nên secret phải đánh dấu `sync: false` (hoặc `generateValue`) thay vì ghi giá trị. Cả hai đều dùng chung một Dockerfile và đọc `PORT` từ môi trường, nên cùng một image chạy được trên cả hai nền tảng.

### Exercise 3.3: Pipeline CI/CD của Cloud Run

Đọc `03-cloud-deployment/production-cloud-run/cloudbuild.yaml` và `service.yaml` (không deploy):

1. **Test:** Cloud Build chạy trong container `python:3.11-slim`, cài `requirements.txt` + `pytest` và chạy `pytest tests/`; test fail thì pipeline dừng, không build.
2. **Build:** `docker build` với 2 tag `ai-agent:$COMMIT_SHA` và `:latest`, dùng `--cache-from` image `latest` để tận dụng layer cache.
3. **Push:** đẩy cả 2 tag lên Container Registry `gcr.io/$PROJECT_ID/ai-agent`.
4. **Deploy:** `gcloud run deploy` image theo đúng `$COMMIT_SHA` (dễ rollback về commit cũ) lên region `asia-southeast1`, 1–10 instance (`min-instances=1` tránh cold start), 512Mi RAM, 1 CPU, timeout 60s; `ENVIRONMENT=production` đặt bằng env, `OPENAI_API_KEY` lấy từ **Secret Manager** chứ không ghi trong file.
5. **`service.yaml`** mô tả cùng service dạng Knative: autoscale theo concurrency (80 request/instance), `livenessProbe` gọi `/health` mỗi 30s, `startupProbe` gọi `/ready` trước khi nhận traffic, `AGENT_API_KEY` và `OPENAI_API_KEY` lấy từ secret.

---

## Part 4: API Security

### Exercise 4.1: API key (`04-api-gateway/develop`)

- **API key được kiểm ở đâu:** hàm `verify_api_key()` dùng `APIKeyHeader(name="X-API-Key")`, gắn vào `/ask` qua `Depends(verify_api_key)`. Key đúng lấy từ biến môi trường `AGENT_API_KEY`.
- **Sai key thì sao:** thiếu header → **401** "Missing API key"; có header nhưng sai key → **403** "Invalid API key". Request bị chặn trước khi gọi LLM.
- **Rotate key thế nào:** đổi giá trị `AGENT_API_KEY` trên platform rồi restart/redeploy, không cần sửa code. Để không gián đoạn, có thể tạm chấp nhận cả key cũ và key mới trong một khoảng thời gian, báo client đổi key, rồi bỏ key cũ.

```text
$ curl -i -X POST http://localhost:8000/ask -H "Content-Type: application/json" -d '{"question":"Hello"}'
HTTP/1.1 401 Unauthorized
{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}

$ curl -i -X POST http://localhost:8000/ask -H "X-API-Key: wrong-key" -H "Content-Type: application/json" -d '{"question":"Hello"}'
HTTP/1.1 403 Forbidden
{"detail":"Invalid API key."}

$ curl -i -X POST http://localhost:8000/ask -H "X-API-Key: secret-key-123" -H "Content-Type: application/json" -d '{"question":"Hello"}'
HTTP/1.1 200 OK
{"question":"Hello","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}
```

### Exercise 4.2: JWT (`04-api-gateway/production`)

JWT flow: client gửi username/password tới `POST /auth/token` → server kiểm tra rồi ký token (chứa username, role, thời điểm hết hạn 60 phút) → client gửi `Authorization: Bearer <token>` ở mỗi request → server chỉ cần xác minh chữ ký và hạn, không phải tra database.

```text
$ curl -i -X POST http://localhost:8000/auth/token -H "Content-Type: application/json" -d '{"username":"student","password":"demo123"}'
HTTP/1.1 200 OK
{"access_token": "eyJhbGciOiJI...<đã che>", "token_type": "bearer", "expires_in_minutes": 60, "hint": "<đã che>"}

$ curl -i -X POST http://localhost:8000/ask -H "Content-Type: application/json" -d '{"question":"Explain JWT"}'
HTTP/1.1 401 Unauthorized
{"detail":"Authentication required. Include: Authorization: Bearer <token>"}

$ curl -i -X POST http://localhost:8000/ask -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"question":"Explain JWT"}'
HTTP/1.1 200 OK
{"question":"Explain JWT","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé.","usage":{"requests_remaining":9,"budget_remaining_usd":1.6e-05}}
```

### Exercise 4.3: Rate limiting

- **Algorithm:** sliding window. Mỗi user có một `deque` lưu thời điểm các request; mỗi lần gọi bỏ những request cũ hơn 60 giây rồi đếm phần còn lại.
- **Limit:** user thường 10 request/60 giây (`rate_limiter_user`); admin 100 request/60 giây (`rate_limiter_admin`).
- **Bypass cho admin:** endpoint chọn limiter theo role trong JWT (`rate_limiter_admin if role == "admin"`), nên tài khoản admin (`teacher`) được giới hạn cao hơn. Lưu ý: limiter này lưu trong RAM, chạy nhiều instance thì mỗi instance đếm riêng; production cần lưu trong Redis.

```text
Vòng lặp 20 request liên tiếp với cùng token (request đầu tiên đã dùng ở 4.2):
req  1..9  -> 200
req 10..20 -> 429

$ curl -i ... (khi bị chặn)
HTTP/1.1 429 Too Many Requests
x-ratelimit-limit: 10
x-ratelimit-remaining: 0
retry-after: 59
{"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":59}}
```

### Exercise 4.4: Cost guard

- **Cách tính:** sau mỗi lần gọi LLM, ghi số token input/output; chi phí = token/1000 × giá (gpt-4o-mini: 0.00015 USD/1K input, 0.0006 USD/1K output).
- **Kiểm tra trước khi gọi LLM:** nếu chi phí trong ngày của user ≥ budget (1 USD/ngày) → **402 Payment Required**; nếu tổng chi phí toàn hệ thống ≥ 10 USD/ngày → 503; dùng tới 80% budget thì ghi log cảnh báo.
- **Reset:** record gắn với ngày (`day`), sang ngày mới thì tạo record mới.
- **Trong agent Part 6 của mình:** lưu tổng chi phí trong **Redis** bằng key theo ngày `cost:daily:<YYYY-MM-DD>`, cộng bằng `INCRBYFLOAT` và tự hết hạn sau 2 ngày, để mọi worker/instance dùng chung và không mất khi restart (bản trong `04-api-gateway` lưu trong RAM).
- **Vì sao cần cả rate limit và cost guard:** rate limit bảo vệ **tốc độ** (chống spam, quá tải trong ngắn hạn); cost guard bảo vệ **tiền** (một user gọi chậm nhưng đều, hoặc câu hỏi dài tốn nhiều token, vẫn có thể đốt hết budget mà không chạm rate limit).

---

## Part 5: Scaling & Reliability

### Exercise 5.1: Health check và readiness

- `/health` (**liveness**): process còn sống không. Fail thì platform **restart** container. Không nên phụ thuộc dịch vụ ngoài, nếu không Redis chết sẽ khiến mọi instance bị restart liên tục.
- `/ready` (**readiness**): instance có sẵn sàng nhận traffic không (đã khởi động xong, kết nối được Redis/DB, không đang tắt). Fail thì load balancer **ngừng gửi traffic** tới instance đó nhưng không restart.

```text
$ curl http://localhost:8000/health
{"status":"ok","uptime_seconds":3.7,"version":"1.0.0","environment":"development",...,"checks":{"memory":{"status":"ok","used_percent":14.0}}}
$ curl http://localhost:8000/ready
{"ready":true,"in_flight_requests":1}
```

### Exercise 5.2: Graceful shutdown

Gửi một request `POST /ask` rồi `kill -TERM <pid>` ngay sau đó 0.05 giây:

```text
Kết quả request đang chạy:
{"answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}  [HTTP 200]
process đã thoát

--- log ---
INFO:     Shutting down
INFO:     127.0.0.1:50238 - "POST /ask?question=Long%20task HTTP/1.1" 200 OK
INFO:     Waiting for application shutdown.
... INFO 🔄 Graceful shutdown initiated...
... INFO ✅ Shutdown complete
INFO:     Finished server process [355]
```

Request đang chạy vẫn hoàn thành (200) dù SIGTERM tới giữa chừng: uvicorn ngừng nhận kết nối mới, chờ request đang chạy xong, chạy phần shutdown của lifespan rồi mới thoát.

### Exercise 5.3: Stateless design

Nếu lưu state (session, history) trong RAM, mỗi instance có bộ nhớ riêng: request sau của cùng một user có thể tới instance khác và không thấy history, và restart/scale xuống là mất dữ liệu. Bản production lưu session trong Redis (`session:<id>`, có TTL), nên instance nào cũng đọc được cùng dữ liệu và có thể thêm/bớt instance tự do.

### Exercise 5.4: Load balancing

`docker compose -p k5-day14-scaling up -d --build --scale agent=3` → 3 agent + Nginx + Redis đều healthy. 10 request `POST http://localhost:8080/chat` qua Nginx được chia round-robin:

```text
req 1 -> served_by instance-7618ab
req 2 -> served_by instance-894c5f
req 3 -> served_by instance-b55e47
req 4 -> served_by instance-7618ab
...
req 10 -> served_by instance-7618ab
```

Tắt hẳn một instance (`docker stop k5-day14-scaling-agent-2`) rồi gửi tiếp 4 request cùng session: cả 4 đều được 2 instance còn lại phục vụ, history vẫn đủ 10 message.

### Exercise 5.5: Test stateless

```text
$ python test_stateless.py
Session ID: e1b7f636-5214-4e09-af97-ab009f4630ad
Request 1: [instance-894c5f]  Q: What is Docker?
Request 2: [instance-b55e47]  Q: Why do we need containers?
Request 3: [instance-7618ab]  Q: What is Kubernetes?
Request 4: [instance-894c5f]  Q: How does load balancing work?
Request 5: [instance-b55e47]  Q: What is Redis used for?
------------------------------------------------------------
Total requests: 5
Instances used: {'instance-7618ab', 'instance-b55e47', 'instance-894c5f'}
✅ All requests served despite different instances!

--- Conversation History ---
Total messages: 10
✅ Session history preserved across all instances via Redis!
```

Giải thích: 5 câu hỏi của cùng một session đi qua cả 3 instance khác nhau, nhưng history vẫn đủ 10 message (5 câu hỏi + 5 trả lời) vì state nằm trong Redis chứ không trong RAM của instance nào.

---

## Part 6: Final Project — output `check_production_ready.py`

Chạy bản đầy đủ trong WSL2 (Ubuntu, Python 3.11, Docker 28.0.4), trong `06-lab-complete/`: `python check_production_ready.py`

```text
================================================================
  📋 Checklist Deliverable
     ✅ Dockerfile (multi-stage, < 500 MB)
     ✅ docker-compose.yml (agent + redis)
     ✅ .dockerignore
     ✅ Health check endpoint (GET /health)
     ✅ Readiness endpoint (GET /ready)
     ✅ API Key authentication
     ✅ Rate limiting
     ✅ Cost guard
     ✅ Config từ environment variables
     ✅ Structured logging
     ✅ Graceful shutdown
     ✅ Public URL ready (Railway / Render config)
----------------------------------------------------------------
  Result: 12/12 tiêu chí đạt · 43/43 checks passed
  🎉 PASS 12/12 — PRODUCTION READY! Deploy nào!
================================================================
```

Một số chi tiết trong output: image 63 MB; rate limit trả 429 sau 5 request (RATE_LIMIT_PER_MINUTE=5) và vẫn 429 sau khi restart agent; SIGTERM lúc đang có request thì request vẫn trả 200, process thoát với exit code 0; `docker stop` xong trong 0.8 giây, exit code 0.

---

## AI log

> Ghi nhận việc dùng AI khi hoàn thiện Part 6 và chuẩn bị tài liệu nộp. Nội dung dưới đây mô tả phần AI hỗ trợ; kết quả chạy và kiểm chứng chỉ ghi khi có output thực tế.

| # | Phần | AI đã hỗ trợ | Kết quả nhận được | Việc cần tự rà soát / xác nhận |
|---|---|---|---|---|
| 1 | Part 6 — Final Project | Đọc yêu cầu lab, tổng hợp checklist và hỗ trợ hoàn thiện các thành phần production agent trong `06-lab-complete/`. | Bản cập nhật cho cấu hình môi trường, xác thực API key, rate limit và cost guard dùng Redis, health/readiness, JSON logging, Docker/Compose và cấu hình Railway/Render. | Đọc lại mã nguồn và cấu hình; chạy `python check_production_ready.py` trong WSL2 với Docker; chỉ ghi kết quả PASS/FAIL theo output thực tế. |
| 2 | Tài liệu nộp | Hỗ trợ tạo cấu trúc ban đầu cho `MISSION_ANSWERS.md`, `DEPLOYMENT.md` và `BENCHMARK_REPORT.md` theo hướng dẫn lab. | Có khung để điền câu trả lời, thông tin triển khai và số liệu benchmark. | Tự điền câu trả lời và số liệu từ kết quả đã chạy; kiểm tra URL, file report, CSV và ảnh trước khi nộp. |

