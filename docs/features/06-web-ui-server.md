# Feature 06: Web UI & REST API Server

> **Mục đích:** Cung cấp máy chủ HTTP tối giản (xây dựng bằng thư viện chuẩn Python + `psycopg_pool`), phục vụ các REST API JSON tra cứu cheatsheet và ứng dụng Single Page Application (SPA) giao diện Google Keep style tại `web/index.html`.

---

## 📂 Các File Liên Quan

| File | Vai trò trong Feature |
|---|---|
| [`server.py`](file:///home/chuminh/cheatsheet/server.py) | Máy chủ HTTP đa luồng (`ThreadingHTTPServer`), quản lý Connection Pool, định tuyến API/Static và cơ chế auto-reload watcher. |
| [`web/index.html`](file:///home/chuminh/cheatsheet/web/index.html) | Toàn bộ giao diện người dùng SPA: HTML, CSS Variables (Dark/Light theme) và JavaScript thuần (không dùng framework ngoài). |
| [`db/schema.sql`](file:///home/chuminh/cheatsheet/db/schema.sql#L90-L130) | Cung cấp hàm SQL [`sheet_json()`](file:///home/chuminh/cheatsheet/db/schema.sql#L90) tái dựng cây dữ liệu JSON và view [`sheet_list`](file:///home/chuminh/cheatsheet/db/schema.sql#L125). |
| [`.air.toml`](file:///home/chuminh/cheatsheet/.air.toml) | Cấu hình live-reload cho công cụ `air` (nếu nhà phát triển quen dùng công cụ của Go). |
| [`cheatsheet/config.py`](file:///home/chuminh/cheatsheet/cheatsheet/config.py) | Khai báo `APP_HOST` và `APP_PORT` (đọc từ `.env`). |

---

## ⚙️ Luồng Hoạt Động & Cơ Chế Cốt Lõi

```mermaid
flowchart TD
    Client["Trình duyệt / Client"] -->|HTTP Request| Server["server.py (ThreadingHTTPServer)"]
    
    Server --> Route{"Định tuyến URL"}
    
    Route -->|GET /api/cheatsheets| ListAPI["Query: SELECT * FROM sheet_list"]
    Route -->|GET /api/cheatsheets/:slug| SheetAPI["Query: SELECT sheet_json(:slug)"]
    Route -->|GET /api/search?q=...| SearchAPI["cheatsheet.search() -> search_entries()"]
    Route -->|GET /api/* (khác)| Err404["404 Not Found"]
    Route -->|GET /:slug hoặc tĩnh| WebSPA["Trả về web/index.html (Client routing)"]
    
    ListAPI & SheetAPI & SearchAPI --> Pool[("psycopg ConnectionPool (1-4 conns)")]
```

### 1. Máy chủ tối giản không phụ thuộc framework
- Không dùng FastAPI/Django/Flask. Sử dụng trực tiếp [`http.server.BaseHTTPRequestHandler`](file:///home/chuminh/cheatsheet/server.py#L33) và [`psycopg_pool.ConnectionPool`](file:///home/chuminh/cheatsheet/server.py#L27) giúp server khởi động ngay lập tức (<10ms) và tiêu tốn cực ít bộ nhớ.

### 2. Dựng cây JSON trực tiếp trong cơ sở dữ liệu (`sheet_json`)
- Để frontend nhận được cấu trúc hoàn chỉnh `card -> section -> items` (bao gồm code block, tables, tooltips, tags) với tốc độ cao nhất, hàm SQL [`sheet_json()`](file:///home/chuminh/cheatsheet/db/schema.sql#L90) ghép nối trực tiếp dữ liệu từ bảng `sheets` và `entries` thành một chuỗi JSONB duy nhất trong 1 truy vấn.

### 3. Tự động reload khi sửa mã nguồn (`--reload`)
- Tích hợp sẵn bộ theo dõi `mtime` tập tin (watch loop kiểm tra mỗi 0.4s). Khi phát hiện thay đổi trong `cheatsheet/`, `web/`, `db/`, `server.py` hoặc `.env`, server sẽ tự khởi động lại tiến trình con mà không cần cài thêm thư viện bên ngoài.

---

## 🌐 Danh Sách REST Endpoints

| Phương thức | Đường dẫn | Tham số | Ý nghĩa |
|---|---|---|---|
| `GET` | `/api/cheatsheets` | Không | Danh sách toàn bộ cheatsheets kèm tổng số cards và entries. |
| `GET` | `/api/cheatsheets/<slug>` | `slug`: mã định danh sheet | Cấu trúc chi tiết của 1 sheet để render web (cards/sections/items). |
| `GET` | `/api/search` | `q` *(bắt buộc)*, `sheet`, `limit` (max 50) | Tìm kiếm hybrid và trả về danh sách kết quả kèm điểm số. |
| `GET` | `/<slug>` | | Trả về `web/index.html` (Frontend tự đọc path để fetch API sheet tương ứng). |

---

## 🛠️ Hướng Dẫn Vận Hành

### Chạy chế độ thông thường
```bash
uv run server.py
```

### Chạy chế độ phát triển (Auto-reload)
```bash
uv run server.py --reload
# hoặc nếu dùng công cụ air:
air
```
Truy cập giao diện Web tại: `http://127.0.0.1:8080` (hoặc cổng được chỉ định trong file `.env`).
