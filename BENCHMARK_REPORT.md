# Benchmark & Observability Report — Day 14

> Mọi con số phải lấy từ report JSON / CSV / screenshot thật, không ước lượng.

**Họ tên:** Kieu Dinh Van (2A202603376)
**Ngày chạy:** 2026-11-25 (Part 7 Bước 1 và Bước 2)
**Môi trường:** Windows 11, Docker Desktop 28.0.4; agent và công cụ đo chạy trong container `python:3.11-slim`

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | < 500 ms | Ngưỡng mặc định của `load_test.py`; p95 bình thường ~220 ms nên còn dư địa, nhưng bắt được khi >5% request chậm (~1.7 s) |
| Error rate `/ask` | < 2 % | Mock LLM có ~1% lỗi upstream; 2% cho phép biến động mà vẫn báo khi lỗi tăng gấp đôi |
| Accuracy trên golden dataset | ≥ 80 % | Ngưỡng quality gate mặc định của `run_eval.py`; v2 đạt 91.3% trước khi sửa, 100% sau khi sửa |

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

### 2.1 Concurrency vs latency (agent v2)

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---|---|---|---|---|---|
| 1 | 4.17 | 192.7 | 220.5 | 1690.8 | 0.33% | ✅ PASS |
| 10 | 34.7 | 192.0 | 224.8 | 1706.3 | 0.67% | ✅ PASS |
| 50 | 106.24 | 203.4 | 280.9 | 1698.7 | 1.67% | ✅ PASS |
| 100 | 135.94 | 204.5 | 342.0 | 1782.1 | 0.67% | ✅ PASS |

**Nhận xét:** RPS có tăng tuyến tính theo concurrency không? Vì sao?

Không. Concurrency tăng 100 lần (1 → 100) nhưng RPS chỉ tăng khoảng 33 lần (4.17 → 135.94). Từ 50 lên 100 user, RPS chỉ tăng thêm khoảng 28% (106.24 → 135.94).

Thời gian xử lý mỗi request ở p50 khoảng 0.2 s. Vì vậy, nếu tăng tuyến tính thì 100 user phải đạt khoảng 500 RPS. Thực tế không đạt vì agent develop chỉ chạy **1 process uvicorn**: mọi request dùng chung một event loop và một CPU. Khi nhiều request cùng chờ thì chúng phải xếp hàng. Dấu hiệu rõ nhất là p95 tăng dần (220.5 → 224.8 → 280.9 → 342.0 ms) dù p50 gần như không đổi. Ngoài ra, mỗi mức chỉ có 300 request, nên ở concurrency 100 bài test chỉ kéo dài 2.21 s, và vài request chậm khoảng 1.7 s chiếm một phần lớn tổng thời gian, kéo RPS xuống.

Cả 4 mức vẫn đạt SLO (p95 < 500 ms, error < 2%). Tuy vậy, ở 100 user p95 đã dùng khoảng 70% ngân sách latency, nên muốn tăng tải tiếp thì phải scale ngang (thêm worker hoặc instance).

### 2.2 Tail latency

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|
| 0 | 189.3 | 217.5 | 229.9 |
| 0.03 (mặc định) | 219.8 | 216.7 | 1707.6 |
| 0.1 | 351.6 | 1689.4 | 1712.2 |

**Nhận xét:** Chỉ số nào nhạy nhất với request chậm? Vì sao SLO không nên đặt theo average?

**p99 nhạy nhất.** Mock LLM cho khoảng 3% request chậm (~1.7 s). Khi `MOCK_SLOW_RATE` đổi từ 0 lên 0.03, p99 nhảy từ 229.9 ms lên 1707.6 ms (gấp ~7 lần). Trong khi đó avg chỉ tăng khoảng 30 ms (189.3 → 219.8), còn p95 gần như không đổi, vì 3% request chậm vẫn nằm ngoài 5% chậm nhất mà p95 bỏ qua. Khi tỉ lệ chậm lên 0.1 (vượt 5%), p95 cũng nhảy lên 1689.4 ms, còn avg mới là 351.6 ms.

**Không đặt SLO theo average** vì average che mất nhóm người dùng bị chậm. Ví dụ ở mức 0.1: avg 351.6 ms trông vẫn "ổn", nhưng thật ra cứ 10 người thì 1 người phải chờ gần 1.7 s. SLO theo p95/p99 đo đúng trải nghiệm của nhóm tệ nhất, và báo động ngay khi phần "đuôi" xấu đi.

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---|---|---|
| Accuracy | 4.3% (1/23) | 91.3% (21/23) | 100.0% (23/23) |
| Avg tokens / câu | 57.4 | 109.0 | 113.7 |
| Tổng cost (USD) | 0.000408 | 0.00076 | 0.00079 |
| Cost / câu đúng (USD) | 0.00040815 | 0.00003619 | 0.00003436 |
| Quality gate | ❌ FAIL | ✅ PASS | ✅ PASS (`--min-accuracy 1.0`, 0 regression) |

**Những câu v2 trả lời sai ban đầu và cách bạn sửa:**

| ID | Keyword bị thiếu | Bạn đã sửa gì |
|---|---|---|
| `scaling-03` | cpu, memory, custom metrics | Thêm tài liệu về Kubernetes HPA (từ khoá `hpa`, `kubernetes`, `autoscal`) vào `KNOWLEDGE_BASE` |
| `security-02` | token, hết hạn, chữ ký | Thêm tài liệu so sánh JWT và API key (từ khoá `jwt`) vào `KNOWLEDGE_BASE` |

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2:**

- **Chất lượng:** v2 có retrieval nên trả lời đúng 21/23 câu, sau khi sửa KB là 23/23. v1 chỉ đúng 1/23, vì không có context nên câu trả lời chung chung, thiếu keyword.
- **Chi phí:** v2 tốn gần **2 lần token mỗi câu** (109.0 so với 57.4), vì prompt chứa thêm đoạn tài liệu lấy từ knowledge base, nên tổng cost cũng gần gấp đôi (0.00076 so với 0.000408 USD). Nhưng tính trên **mỗi câu trả lời đúng** thì v2 rẻ hơn khoảng **11 lần** (0.0000362 so với 0.000408 USD). Lý do là v1 tốn tiền mà hầu như không ra câu đúng nào.
- **Latency:** v2 thêm một bước `agent.retrieve_context` (~17–24 ms trong trace) và prompt dài hơn, nên chậm hơn một chút. Nhưng phần lớn thời gian vẫn nằm ở lần gọi LLM (trace mục 4.3: span LLM chiếm 98.5%).
- **Kết luận:** chọn v2. Cái giá phải trả là thêm token và thêm vài chục ms, đổi lại chất lượng tăng từ 4% lên 100%. Thước đo đúng để so sánh là **cost trên mỗi câu đúng**, không phải cost trên mỗi request.

**Quality gate trong CI:** `run_eval.py` trả **exit code 1** khi accuracy < `--min-accuracy` hoặc khi có câu từng đúng ở baseline nay sai (regression). Job `.github/workflows/eval.yml` chạy trên mọi pull request: bật agent v2, chạy `python eval/run_eval.py --min-accuracy 0.85 --baseline reports/eval_v2.json`. Exit code 1 làm job fail. Khi bật branch protection "Require status checks to pass", PR làm giảm chất lượng sẽ **không merge được**.

---

## 4. Observability stack (production)

### 4.1 Screenshot

- [x] Dashboard Grafana khi đang có tải (thấy rõ Golden Signals) → [`screenshots/grafana-dashboard.png`](screenshots/grafana-dashboard.png)
- [x] Một trace chậm trong Jaeger (thấy span nào chiếm thời gian) → [`screenshots/jaeger-slow-trace.png`](screenshots/jaeger-slow-trace.png)
- [x] Một trace lỗi trong Jaeger (có event `exception`) → [`screenshots/jaeger-error-trace.png`](screenshots/jaeger-error-trace.png)
- [x] Trang Alerts của Prometheus với ít nhất 2 alert đang **firing** (RUBRIC) → [`screenshots/prometheus-alert-firing.png`](screenshots/prometheus-alert-firing.png)

**Số đo đúng lúc chụp `grafana-dashboard.png`** (21:47 GMT+7, Locust 30 users, 2 instance, cấu hình mặc định `MOCK_SLOW_RATE=0.03`, `MOCK_ERROR_RATE=0.01`; query Prometheus cùng biểu thức với panel, `rate[1m]` tại 14:47:00 UTC): traffic **18.98 req/s**, error rate **0.86%** (panel hiện 0.77% vì lấy giá trị vài giây trước đó), p50 176.5 ms, **p95 292.8 ms**, avg 226.7 ms, p99 1799 ms; req/s theo instance **9.42 và 9.56**; input **1455 token/s**, output **759 token/s**; in-flight 4–5.

Lần chạy trước đó (cùng cấu hình) ra số tương tự: p95 295.7 ms, avg 242.8 ms, error 0.62%. `curl http://localhost:8080/metrics` → HTTP 404. Alert rules: `promtool test rules` → SUCCESS.

**Trả lời Exercise 7.4:**

1. **p95 ≈ 293 ms, avg ≈ 227 ms.** Khoảng cách giữa hai số không lớn, còn p99 thì lên tới ~1.8 s. Nghĩa là phần lớn request nhanh và đều (~180–290 ms), nhưng có một "đuôi" nhỏ, khoảng 3% request rất chậm (~1.7 s), do mock LLM thỉnh thoảng chậm. Average không cho thấy cái đuôi đó. Phải nhìn p95/p99 mới thấy có nhóm user bị chậm.
2. **Có, Nginx chia gần đều.** Panel "Requests/s theo instance" cho 9.42 và 9.56 req/s. Lệch khoảng 1.5% vì Nginx dùng round-robin, mỗi request đi lần lượt vào từng instance.
3. **Input token/s lớn hơn output** (1455 so với 759, gần gấp đôi) vì agent v2 nhét **context lấy từ knowledge base** vào prompt cùng system prompt và câu hỏi. Prompt gửi đi vì vậy dài hơn nhiều so với câu trả lời ngắn của model. Đây cũng là lý do v2 tốn token hơn v1 ở mục 3.
4. **`curl http://localhost:8080/metrics` trả 404**, vì `nginx.conf` chặn đường dẫn `/metrics` ở cổng public. Metrics lộ thông tin nội bộ (số request, lỗi, chi phí, tên instance) và không cần cho người dùng. Prometheus vẫn scrape được vì nó gọi thẳng `agent:8000/metrics` trong mạng Docker nội bộ, không đi qua Nginx.

### 4.2 Thí nghiệm "phá hệ thống"

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` (đổi cùng lúc với B, 10:34:08 UTC) | `AgentHighErrorRate` | 91 s (pending sau 31 s, `for: 1m`) | Error rate (~20.4%) |
| B | `MOCK_SLOW_RATE=0.3` (đổi cùng lúc với A) | `AgentHighLatencyP95` | 151 s (`for: 2m`) | p95 latency (1895 ms; avg chỉ 574 ms) |
| C | `LLM_MODEL=mock-llm-large` (10:29:20 UTC) | `LLMCostBurnRateHigh` — **đã firing từ trước** (10:23:37 UTC) ở cấu hình mặc định, nên không đo được thời gian | Cost USD/giờ: cửa sổ 1m từ ~1.75 lên ~35 (~20 lần), cửa sổ 5m từ 4.1 lên 20.3 sau 3 phút; p95 từ ~293 lên 664 ms |
| D | `docker pause` 1 instance (10:28:23 UTC) | `AgentInstanceDown` | 45 s (pending sau 15 s, `for: 30s`) | Instances up (2 → 1); Nginx trả 28 lỗi 504 trong lúc pause nhưng panel Error rate của agent vẫn xanh |
| E | `AGENT_VERSION=v1` (10:32:29 UTC) | Không có alert mới | — | Retrieval hit ratio về 0, input token/s giảm ~1090 → ~660, bảng version đổi sang v1 |

Ảnh `prometheus-alert-firing.png` được chụp ở lần chạy lại thí nghiệm A + B (`MOCK_ERROR_RATE=0.2`, `MOCK_SLOW_RATE=0.3`, Locust 30 users bật lúc 21:14:20 GMT+7). Trong ảnh, nhóm `agent-slo` có **FIRING (2)** là `AgentHighErrorRate` và `AgentHighLatencyP95`. Thời gian từ lúc đổi cấu hình tới lúc firing lấy theo lần đo đầu tiên ở bảng trên (91 s và 151 s). Ở lần chạy lại, cấu hình lỗi đã được đặt sẵn từ trước, nên không dùng để đo thời gian.

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?**

Đổi sang v1 làm **chất lượng câu trả lời** sụt mạnh (accuracy 100% → 4%), nhưng agent vẫn trả 200, vẫn nhanh và thậm chí còn rẻ hơn. Mọi alert hiện tại chỉ đo **sức khoẻ kỹ thuật** (lỗi, latency, instance, chi phí), nên không có alert nào bắt được. Cách phát hiện:

1. **Quality gate trước khi deploy:** chạy `run_eval.py` trên golden dataset trong CI (mục 3). v1 chỉ đạt 4.3% nên bị chặn, không lên được production.
2. **Alert theo metric chất lượng:** panel "Retrieval hit ratio" tụt về 0 khi đổi sang v1. Nên thêm alert, ví dụ hit ratio < 50% trong 5 phút. Có thể thêm alert khi input token/s giảm đột ngột (~1090 → ~660), vì đó là dấu hiệu prompt không còn context.
3. **Online eval / giám sát định kỳ:** chạy một tập câu hỏi mẫu (synthetic probe) vào production mỗi vài phút, chấm keyword hoặc dùng LLM-as-judge, rồi alert khi điểm giảm. Có thể kết hợp với feedback của người dùng (👍/👎).
4. **Theo dõi version:** alert khi `agent_version` đang chạy khác version đã được duyệt, và deploy kiểu canary để so sánh chất lượng 2 version trước khi chuyển toàn bộ traffic.

**Vì sao lỗi 504 ở Nginx (thí nghiệm D) không hiện trên metric của agent:** instance bị `docker pause` không xử lý request nào. Nginx chờ hết timeout rồi tự trả 504 cho client. Request đó không bao giờ tới được code của agent, nên không được đếm vào `http_requests_total` của agent, và panel Error rate vẫn xanh. Muốn thấy lỗi này phải đo ở tầng phía trước: metric/log của Nginx (hoặc load balancer), blackbox probe gọi từ bên ngoài, hoặc alert `AgentInstanceDown` (đã firing sau 45 s).

### 4.3 Debug bằng trace

Chọn 1 trace chậm nhất bạn tìm được:

- `trace_id`: `c603eebc027ceaf65949d54f2e1647a4`
- Tổng thời gian: 1721.7 ms
- Span chiếm nhiều thời gian nhất: `chat mock-llm-small` (1695.0 ms, 98.5%); `agent.retrieve_context` chỉ 23.6 ms (1.4%). Input 83 token, output 44 token
- Dòng log tương ứng (grep theo `trace_id`):

```json
{"ts": "2026-11-25T10:27:05.859416+00:00", "level": "INFO", "service": "observable-agent", "instance": "c09ab712a27e", "event": "llm_call", "trace_id": "c603eebc027ceaf65949d54f2e1647a4", "span_id": "d5da98b5863a314a", "request_id": "11af56a219f4", "model": "mock-llm-small", "agent_version": "v2", "input_tokens": 83, "output_tokens": 44, "cost_usd": 3.9e-05, "llm_ms": 1695.6}
{"ts": "2026-11-25T10:27:05.859809+00:00", "level": "INFO", "service": "observable-agent", "instance": "c09ab712a27e", "event": "http_request", "trace_id": "c603eebc027ceaf65949d54f2e1647a4", "span_id": "d5da98b5863a314a", "request_id": "11af56a219f4", "method": "POST", "route": "/ask", "status": 200, "ms": 1722.3}
```

Trace lỗi: `trace_id` `4f159cb3111a01741c845c48425f287f` (104.8 ms), span `chat mock-llm-small` có `error.type=upstream_unavailable` và event `exception`; log tương ứng:

```json
{"ts": "2026-11-25T10:27:50.206675+00:00", "level": "INFO", "service": "observable-agent", "instance": "c09ab712a27e", "event": "llm_error", "trace_id": "4f159cb3111a01741c845c48425f287f", "span_id": "674afc456dc250ce", "request_id": "9f33c373ed58", "error": "Upstream LLM error: 503 Service Unavailable (mock)"}
```

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | 59.88 | 190 | 240 | 1700 | 67 / 7154 (0.94%) |
| 3 | 59.61 | 190 | 230 | 1700 | 59 / 7119 (0.83%) |

> Số của dòng `POST /ask` trong `benchmark-results/scale_1_stats.csv` và `scale_3_stats.csv`.

**Giải thích kết quả:** Scale có cải thiện p95 không? Nút thắt nằm ở đâu?

**Gần như không cải thiện.** RPS giữ nguyên (59.88 so với 59.61), p95 chỉ giảm 10 ms (240 → 230), p50 và p99 không đổi (190 và 1700 ms), tỉ lệ lỗi tương đương (0.94% và 0.83%, đúng mức `MOCK_ERROR_RATE=0.01`).

**Nút thắt không nằm ở agent mà ở chính bài test và ở LLM:**

1. **Locust là vòng kín (closed loop):** mỗi user gửi request, chờ trả lời, nghỉ `wait_time = between(0.5, 2)` (trung bình 1.25 s), rồi mới gửi tiếp. Với 100 user, mỗi vòng mất khoảng 1.25 + 0.24 ≈ 1.5 s, nên tổng tải tối đa khoảng 100 / 1.5 ≈ 67 req/s. Thực đo `/ask` 59.88 + `/health` 6.23 = **66.1 req/s**, khớp. Tức là 1 instance đã xử lý hết lượng tải Locust tạo ra. Thêm instance thì không có thêm request nào để xử lý, nên RPS không tăng.
2. **Latency do mock LLM quyết định:** mỗi request tốn ~120–190 ms chờ LLM, và ~3% request chậm ~1.7 s. Thời gian này không giảm khi thêm instance, nên p50 và p99 giữ nguyên. Với 1 instance, CPU cũng chưa bão hoà, nên chỉ có p95 nhích nhẹ do bớt xếp hàng.

Muốn thấy lợi ích của scale ngang thì phải tăng tải tới mức 1 instance bị quá tải: tăng số user, giảm `wait_time`, hoặc giới hạn CPU thấp hơn. Lúc đó p95 của 1 instance sẽ tăng vọt, còn 3 instance vẫn giữ được SLO. Khi LLM thật là nút thắt, việc cần làm là cache, streaming, hoặc chọn model nhanh hơn, chứ thêm instance agent không giúp được.

---

## 6. Kết luận

- 3 điều bạn học được về benchmark & observability:
  1. **Đo theo percentile, không theo average.** Chỉ 3% request chậm đã đẩy p99 lên 1.7 s trong khi avg gần như không đổi. SLO phải đặt theo p95/p99 thì mới bảo vệ được nhóm người dùng bị chậm.
  2. **Hệ thống "khoẻ" chưa chắc đã "đúng".** Đổi sang v1 không làm alert nào kêu, nhưng accuracy tụt từ 100% xuống 4%. Với AI agent, phải có cả eval chất lượng (quality gate trong CI, golden dataset) bên cạnh metric kỹ thuật. Cost cũng phải tính trên mỗi câu đúng, không phải mỗi request.
  3. **Metrics, traces và logs bổ sung cho nhau.** Dashboard cho biết *có* vấn đề (p95 tăng), trace chỉ ra *chỗ nào* chậm (span LLM chiếm 98.5%), log JSON có cùng `trace_id` cho biết *chi tiết* (model, token, lỗi). Muốn đọc kết quả benchmark đúng còn phải hiểu cách tạo tải: Locust vòng kín giới hạn RPS, nên scale 1 → 3 instance nhìn như "không có tác dụng".
- Nếu đưa agent này lên production thật, bạn sẽ thêm metric / alert nào nữa?

  - **Chất lượng:** alert khi retrieval hit ratio thấp, chạy synthetic probe / online eval định kỳ với alert khi điểm giảm, đếm tỉ lệ 👎 từ người dùng.
  - **Tầng biên:** metric 5xx/504 và latency tại Nginx/load balancer, cộng một blackbox probe gọi URL public (bắt được lỗi không tới được agent như thí nghiệm D).
  - **Chi phí:** cost theo từng user/API key, và alert khi một user đốt quá X% budget ngày. Thêm alert theo budget tháng, không chỉ burn rate.
  - **SLO burn rate nhiều cửa sổ** (ví dụ 5m + 1h) cho error budget, thay cho ngưỡng cố định, để vừa bắt nhanh vừa ít báo nhầm.
  - **Saturation và phụ thuộc:** in-flight gần giới hạn, CPU/memory container, Redis down / latency Redis, số lần chạm rate limit (429) và cost guard (402).
