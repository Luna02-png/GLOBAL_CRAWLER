# Global Product Trend Intelligence (GPTI) — v0.1 MVP

Ứng dụng nghiên cứu xu hướng sản phẩm đa ngành, đa thị trường, chạy trên Windows (Python), giao diện web tại `http://127.0.0.1:8765`.
Được xây theo spec `GLOBAL_PRODUCT_TREND_INTELLIGENCE_MASTER_PROMPT.md` (V3.2). Xem trạng thái từng yêu cầu ở mục **Tình trạng triển khai** cuối file.

> **Nguyên tắc dữ liệu:** không bịa sản phẩm, link, ngày, số liệu. Tín hiệu thiếu bị loại khỏi điểm (không tính = 0) và làm giảm *Data Coverage*.
> Dữ liệu DEMO (fixture) luôn gắn cờ `is_fixture` + nhãn **DEMO** và có thể ẩn bằng nút *show DEMO data*.

---

## 1. Cài đặt trên Windows (1 lần)

1. Cài **Python 3.12+** từ python.org (tick *Add python.exe to PATH*).
2. Giải nén thư mục `gpti`, ví dụ `C:\GPTI`.
3. Chạy `scripts\install.bat` (tạo `.venv`, cài thư viện, tạo database `data\gpti.sqlite3`, copy `.env.example` → `.env`).
4. Chạy `scripts\start.bat` → trình duyệt mở `http://127.0.0.1:8765`.

Giao diện đã được build sẵn trong `backend/static` — **không cần Node.js** để dùng. Chỉ cần Node 20+ nếu muốn sửa giao diện (`cd frontend && npm install && npm run build`).

## 2. Lấy dữ liệu thật lần đầu

1. **Source Manager** → bấm **Test** ở *Google News RSS* và một vài feed (Sneaker News, The Verge…). Nguồn nào chạy được sẽ chuyển `WORKING`; nguồn bị chặn sẽ báo `BLOCKED` / `RATE_LIMITED` / `ERROR` đúng sự thật.
2. **Smart Scan Manager** → sửa / tạo preset (thị trường + ngành/danh mục + từ khóa + nguồn + P1/P2/P3) → bấm **Quick**.
3. Theo dõi tiến độ ở bảng *Scan queue & history* (task, nguồn, lỗi, thời gian).
4. Kết quả xuất hiện ở **Product Research Sheet** và 4 module còn lại.

Muốn xem thử giao diện khi chưa có mạng: `cd backend && ..\.venv\Scripts\python -m app.cli demo` (nạp dữ liệu DEMO tổng hợp, có nhãn rõ ràng).

## 3. Lịch quét (Asia/Ho_Chi_Minh)

| Ưu tiên | Mặc định | Ghi chú |
|---|---|---|
| P1 Daily | 07:00 mỗi ngày (cả cuối tuần) | sửa giờ trong preset |
| P2 Weekly | 07:00 thứ Hai | sửa thứ/giờ trong preset |
| P3 On Demand | không tự chạy | chỉ chạy khi bấm Refresh |

* Khi `start.bat` đang chạy, scheduler nội bộ kiểm tra mỗi phút. Mỗi khung giờ chỉ tạo **đúng 1 job** (khóa `dedup_key` UNIQUE trong DB) — kể cả khi chạy 2 tiến trình.
* Nếu máy tắt lúc 07:00, khi bật lại app chỉ chạy **1 lần quét bù** (catch-up), không dồn tất cả lần bị lỡ.
* **Máy tắt / ngủ thì không thể quét lúc 07:00.** Để tự động hơn: chạy `scripts\register_task.ps1` trong PowerShell — tạo task *GPTI-AutoStart* (mở server khi đăng nhập) và *GPTI-RunDue-0700* (07:00 hằng ngày chạy `run_due.bat`, có *WakeToRun* + *StartWhenAvailable*). Kiểm tra: `Get-ScheduledTask GPTI-* | Get-ScheduledTaskInfo`. Gỡ: `scripts\unregister_task.ps1`.
* Muốn chạy 24/7 thật sự: xem `docs/DEPLOY_VPS.md`.
* Quét thủ công (Quick/Full, theo preset, sản phẩm, dòng chọn, danh mục, thị trường) **không bao giờ sửa preset đã lưu**.

## 4. Copy sang Google Sheets

Trong mọi bảng: tick chọn dòng (hoặc để lọc) → **COPY TO GOOGLE SHEETS** (phạm vi: selected / filtered / all, có/không header) → Ctrl+V trong Google Sheets.
* Clipboard chứa cả TSV (đã escape tab, xuống dòng, dấu ") và bảng HTML → mỗi giá trị vào đúng 1 ô.
* URL luôn là chuỗi thuần, copy riêng được. Cột ảnh: chọn `image = raw URL` hoặc `image = =IMAGE()` (chỉ tạo công thức cho URL ảnh hợp lệ).
* Thứ tự cột = thứ tự đang hiển thị (kéo thả cột, ẩn/hiện bằng *Columns ▾*). Có **EXPORT CSV** (UTF-8 BOM) và **EXPORT XLSX**.
* **COPY SELECTED CELLS**: click 1 ô → copy ô đó; nếu đang chọn nhiều dòng → copy cột của ô đó cho các dòng đã chọn. (AG Grid bản Community không có chọn vùng ô kiểu Excel; có thể bôi đen chữ trong ô để copy.)

## 5. Product Link Finder

* Nút **Find Product Links** trên mỗi dòng / trong khung chi tiết chỉ tìm cho **đúng sản phẩm đó** (không quét lại cả danh mục).
* Ứng viên: URL bằng chứng của sản phẩm + truy vấn Google News riêng cho sản phẩm + URL bạn tự thêm. Mỗi trang được tải (tôn trọng robots.txt), so khớp SKU/tên/số model → `EXACT MATCH / HIGH CONFIDENCE / POSSIBLE MATCH / REJECTED`, chấm điểm độ đầy đủ thông tin dựa trên nội dung thực sự thấy được.
* **Best Product Information URL** có thể là bài báo/review/trang chính hãng; **Optional Purchase URL** lưu riêng, chỉ khi trang bán hàng có giá/tình trạng kho xác thực. Không có link mua **không** bị coi là thiếu link.
* Trạng thái `TITLE_MATCH` = mới khớp theo tiêu đề feed (chưa mở trang); `VERIFIED` = đã kiểm tra nội dung trang hoặc do bạn chọn.
* Bạn có thể đổi link chính bằng nút **set**; lần tìm sau không ghi đè lựa chọn của bạn.

## 5b. Thêm dữ liệu mạng xã hội & Google Trends (trang *Add Evidence & Imports*)

* **Nút “➕ Send to Global Crawler”**: kéo lên thanh bookmark Chrome. Bạn tự lướt TikTok/Instagram/X/Shopee… (khách hoặc tài khoản của bạn, tự giải CAPTCHA như bình thường) → bấm nút → form mở sẵn link, tiêu đề, mô tả, tài khoản đăng, lượt thích/xem nếu trang có hiện → kiểm tra → **Save as evidence**. App không tự đăng nhập, không tự cào các trang này, không lưu mật khẩu.
* **Bulk paste**: dán nhiều link (có thể kèm cột tiêu đề, tên sản phẩm, thị trường, views, likes, comments, account từ Google Sheets).
* **Google Trends CSV**: tải CSV “Interest over time” trên trends.google.com → kéo vào → gán từ khóa với sản phẩm + thị trường → cột *search* trong điểm số có dữ liệu thật (chỉ số tương đối 0-100).

## 6. Lệnh hữu ích (trong `backend`, đã activate `.venv`)

```
python -m app.cli serve                 # API + UI + worker + scheduler
python -m app.cli run-due               # quét các preset đến hạn rồi thoát (dùng cho Task Scheduler)
python -m app.cli scan --preset 1 --full
python -m app.cli status                # trạng thái nguồn + job gần nhất
python -m app.cli recompute             # tính lại toàn bộ điểm từ dữ liệu quan sát gốc
python -m app.cli demo                  # nạp dữ liệu DEMO
python -m pytest -q                     # chạy test backend
```

## 7. Kiến trúc

```
backend/app
  models.py        bảng canonical (products, evidence, product_links, scan_*, trends, releases, opportunities, shortlists…)
  adapters/        rss (publisher feeds), google_news (RSS theo thị trường), youtube (API chính thức), fixture (DEMO), unsupported
  pipeline/        extract (trích sản phẩm/SKU/claim/ngày), canonical (định danh), ingest, links (Link Finder)
  scoring/engine   Trend / Early Signal / Rumor confidence / Hype / Opportunity — luôn tính lại từ evidence gốc
  jobs.py          hàng đợi bền vững trong DB: dedup, ưu tiên + chống đói, checkpoint, pause/resume/cancel, phục hồi sau crash
  scheduler.py     P1/P2/P3, catch-up 1 lần, timezone Asia/Ho_Chi_Minh
  export.py        TSV/CSV/XLSX an toàn cho Google Sheets
  main.py          FastAPI + phục vụ UI
  alembic/         migration (SQLite → PostgreSQL chỉ cần đổi GPTI_DATABASE_URL)
frontend/          React + TypeScript + Vite + AG Grid Community (build ra backend/static)
e2e/               test trình duyệt (Playwright)
```

Năm module (Dashboard, Research Sheet, Upcoming, Opportunity, Early Radar) đọc **cùng một database canonical**.

## 8. Tình trạng triển khai (trung thực)

| Hạng mục | Trạng thái |
|---|---|
| 5 module + Scan Manager, Taxonomy, Sources, Link Finder, Saved Lists, Settings, What's New | ✅ có giao diện + API |
| Taxonomy Industry → Category → Subcategory, alias đa ngôn ngữ, merge/deactivate an toàn, many-to-many | ✅ |
| Thị trường/vùng/thành phố tùy chỉnh | ✅ (thành phố chỉ lưu, không quét vì chưa có nguồn địa phương đáng tin) |
| Preset do người dùng tạo, P1/P2/P3, Discovery/Tracking, Quick/Full, giới hạn tài nguyên | ✅ |
| Hàng đợi bền vững, dedup, checkpoint, pause/resume, catch-up, không "thành công giả" | ✅ có test |
| Nguồn thật: Google News RSS + 9 feed nhà xuất bản + YouTube API | ⚠️ **code xong nhưng chưa xác minh live** — môi trường build bị chặn mạng; hãy bấm *Test* trên máy bạn (xem `docs/SOURCES.md`) |
| TikTok / Instagram / X / Google Trends | ⛔ cần quyền API chính thức → hiển thị `NOT_CONFIGURED`, không scrape |
| Trend / Early / Opportunity score, coverage, small-sample safeguards | ✅ (social/search/retail sẽ trống tới khi có nguồn tương ứng) |
| Copy Google Sheets (TSV + HTML), CSV, XLSX, =IMAGE() | ✅ test backend + frontend + trình duyệt |
| Trích xuất sản phẩm | rule-based (không cần AI trả phí); độ chính xác phụ thuộc tiêu đề bài viết — sản phẩm nghi trùng được gắn `review` |
| pandas / Tailwind trong spec | không dùng (không cần cho MVP; CSS thuần) — có thể thêm sau |
