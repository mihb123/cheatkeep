# CheatKeep (`chs`)

> **Tra cứu cheatsheet kỹ thuật bằng ngôn ngữ tự nhiên — Song ngữ Anh – Việt.**  
> Kết hợp **Hybrid Search** (Semantic Vector Search qua `pgvector` + `bge-m3` và Keyword Full-Text Search), hỗ trợ cả công cụ dòng lệnh **Terminal CLI (`chs`)** lẫn giao diện **Web UI**.

---

## 🌟 Tính năng nổi bật

- 🧠 **Tìm kiếm ngữ nghĩa song ngữ (Anh – Việt)**:
  - Hỏi bằng tiếng Việt tự nhiên (ví dụ: *"chia đôi màn hình dọc"*, *"tạo bảng trong mysql"*, *"tìm lệnh lỗi"*).
  - Tự động đối sánh qua hai tầng vector (ngữ cảnh tiếng Anh gốc và mô tả/cụm từ tiếng Việt) với mô hình `bge-m3`.
- ⚡ **Hybrid Search (Vector + Full-Text Search)**:
  - Tận dụng `pgvector` (chỉ mục HNSW cosine) kết hợp `tsvector` PostgreSQL có xử lý bỏ dấu tiếng Việt (`unaccent`).
  - Tên tool ở đầu câu có `:` sẽ chỉ tìm trong 1 sheet. Cú pháp không dấu `:` (`chs "nvim xoá dòng"`) được bật bằng `SEARCH_COLON_FREE_PREFIXES` trong `.env`, tránh hiểu nhầm câu tự nhiên như `find and replace in vim`. Tên tool ở vị trí khác vẫn được ưu tiên.
  - Chỉ nhập tên sheet hoặc hỏi câu có độ tương đồng thấp sẽ nhận 5 lệnh thường dùng của sheet; ngưỡng do `SEARCH_MIN_SIMILARITY` quyết định.
- 💻 **Terminal CLI tiện lợi (`chs`)**:
  - Tự động nạp cấu hình và chạy nhanh qua `uv run --script`.
  - Hỗ trợ copy thẳng lệnh tìm được vào clipboard (`-c`).
  - Hỗ trợ in lệnh để đưa vào shell expansion (`chs -p` dùng với `eval` hoặc keybinding).
  - Tùy chọn lọc theo cheatsheet (`-s`), xuất JSON (`--json`), hiển thị chi tiết điểm số (`-v`).
- 🌐 **Giao diện Web trực quan**:
  - Giao diện tra cứu sạch sẽ, phân chia theo thẻ (cards) và danh mục (sections).
  - Tìm kiếm tức thì, một chạm copy lệnh, responsive cho mọi kích thước màn hình.
- 🔄 **Pipeline dữ liệu tự động**:
  - Parser trích xuất nội dung từ các file HTML cheatsheet.
  - Tự động sinh bản dịch và mở rộng từ khóa tìm kiếm tiếng Việt (`data/translations.vi.json`).
  - Đánh vector embedding gia tăng (incremental, kiểm tra model digest để tự làm mới khi model cập nhật).

> 📖 **Xem tài liệu kiến trúc & tính năng chi tiết theo feature tại:** [docs/README.md](file:///home/chuminh/cheatsheet/docs/README.md)

---

## 🏗️ Kiến trúc & Công nghệ

- **Ngôn ngữ**: Python 3.11+
- **Quản lý gói & thực thi**: [uv](https://docs.astral.sh/uv/) (Astral)
- **Cơ sở dữ liệu**: PostgreSQL 18 + tiện ích mở rộng [pgvector](https://github.com/pgvector/pgvector) (chạy qua Docker Compose)
- **Mô hình Embedding**: `bge-m3` (1024 dimensions) chạy trực tiếp trên máy qua [Ollama](https://ollama.com/) (native systemd)
- **Web Server**: `server.py` tối giản bằng thư viện chuẩn Python + `psycopg 3` connection pool

---

## 🚀 Cài đặt & Bắt đầu nhanh

### 1. Yêu cầu môi trường

- Linux / macOS
- **Docker** & **Docker Compose**
- **Ollama** (chạy native trên máy)
- **uv**: `curl -LsSf https://astral.sh/uv/install.sh | sh`
- *(Tùy chọn cho CLI copy)*: `wl-copy` (Wayland), `xclip` / `xsel` (X11) hoặc `pbcopy` (macOS).

### 2. Chuẩn bị Ollama & Model

Khởi động Ollama service và tải mô hình embedding:

```bash
# Cài đặt Ollama (nếu chưa có)
curl -fsSL https://ollama.com/install.sh | sh

# Bật service Ollama
sudo systemctl enable --now ollama

# Tải model bge-m3
ollama pull bge-m3
```

### 3. Thiết lập hệ thống bằng 1 lệnh

Chạy kịch bản tự động hóa [scripts/setup.sh](file:///home/mihb/Work/cheatsheet/scripts/setup.sh):

```bash
chmod +x scripts/setup.sh
./scripts/setup.sh
```

Kịch bản sẽ tự động:
1. Tạo file cấu hình `.env` với cổng trống và mật khẩu an toàn (nếu chưa có).
2. Khởi chạy PostgreSQL container với pgvector.
3. Kiểm tra kết nối Ollama và model `bge-m3`.
4. Trích xuất dữ liệu từ các file HTML cheatsheet sang dữ liệu cấu trúc.
5. Nạp `db/schema.sql` và `db/seed/*.sql`.
6. Tính toán embeddings lưu vào pgvector (`bge-m3`).

---

## 📖 Hướng dẫn sử dụng

### 1. Terminal CLI (`chs`)

Để có thể gọi lệnh `chs` từ bất cứ thư mục nào:

```bash
ln -sf "$(pwd)/chs" ~/.local/bin/chs
```

*(Đảm bảo `~/.local/bin` đã có trong biến môi trường `$PATH`)*

#### Các ví dụ sử dụng:

```bash
# Ghi rõ tool ở đầu câu "tool: câu hỏi" → chỉ tìm trong sheet đó, chính xác nhất (khuyên dùng)
chs "mysql: tạo bảng"

# Các prefix trong .env được bỏ dấu :; chỉ ghi tên tool thì hiện 5 lệnh thường dùng
chs "atuin"
chs "atuin hook"
chs -s mysql

# Tra cứu tự nhiên trên mọi sheet (tên tool trong câu được ưu tiên, không lọc cứng)
chs "câu lệnh tạo bảng trong mysql là gì?"

# Chỉ định tìm trong 1 sheet cụ thể (-s hoặc --sheet)
chs -s neovim "chia đôi màn hình theo chiều dọc"

# Tự động copy lệnh tốt nhất vào clipboard (-c)
chs -c "backup database mysql"

# Chỉ in câu lệnh kết quả để pipe hoặc eval (-p)
eval "$(chs -p 'tìm lệnh lỗi trong thư mục hiện tại')"

# Hiển thị thông tin chi tiết: ví dụ, giải thích, điểm tương đồng (-v)
chs -v "regex tìm kiếm số điện thoại"

# Liệt kê các cheatsheet kèm mọi tiền tố/viết tắt dùng được (vd nvim:, vim:, pg:, postgres:)
chs --list

# Xuất kết quả dưới định dạng JSON
chs --json "xóa file git"
```

Các thiết lập search nằm trong `.env` (giá trị mẫu ở [`.env.example`](.env.example)):

```dotenv
SEARCH_COLON_FREE_PREFIXES=atuin,awk,bash,curl,grep,mysql,neovim,nvim,vim,psql
SEARCH_MIN_SIMILARITY=0.40
SEARCH_MAX_AVERAGE_MS=200
```

`SEARCH_COLON_FREE_PREFIXES` là danh sách alias cách nhau bằng dấu phẩy; ví dụ trên chỉ minh họa, `.env.example` chứa danh sách mặc định đầy đủ. `find` không có trong danh sách mặc định để `find and replace in vim` được tìm trên mọi sheet; `find:` vẫn lọc vào Find và `find` đứng một mình vẫn hiện 5 lệnh. Alias mới cần khai báo trong `sheets/<slug>.json` và chạy `make reload`. `SEARCH_MIN_SIMILARITY` là ngưỡng cosine, không phải phần trăm xác suất đúng: nếu mọi kết quả dưới ngưỡng, hệ thống gợi ý 5 lệnh của sheet được chỉ rõ, hoặc sheet của kết quả đứng đầu khi chưa chỉ rõ sheet. CLI đọc lại `.env` ở lần chạy sau; web server cần khởi động lại.

Nếu không khai báo các biến trên trong `.env`, ứng dụng dùng danh sách prefix đầy đủ trong `.env.example`, ngưỡng tương đồng `0.40` và ngưỡng test `200` ms.

---

### 2. Giao diện Web & REST API

Khởi động server cục bộ:

```bash
uv run server.py
```

Truy cập trên trình duyệt tại: `http://127.0.0.1:8080` (hoặc cổng được cấu hình trong file `.env`).

#### Các API Endpoint:

- `GET /api/cheatsheets`: Danh sách cheatsheet và số lượng entries/cards.
- `GET /api/cheatsheets/<slug>`: Nội dung chi tiết của sheet dạng cấu trúc cards/sections.
- `GET /api/search?q=<query>&sheet=<slug>&limit=<n>`: API tìm kiếm hybrid trả JSON; có thể bỏ `q` nếu truyền `sheet` để xem lệnh thường dùng. `suggestion` là `browse` hoặc `low_similarity` khi trả danh sách gợi ý.

---

### 3. Đánh giá chất lượng tìm kiếm (Evaluation)

Hệ thống đi kèm bộ câu hỏi chuẩn đánh giá độ chính xác tại [eval/queries.json](file:///home/mihb/Work/cheatsheet/eval/queries.json):

```bash
uv run -m cheatsheet.evaluate
```

Lệnh sẽ tính toán các chỉ số:
- **hit@1**: Tỷ lệ câu hỏi có kết quả chính xác ngay ở vị trí đầu tiên.
- **hit@5**: Tỷ lệ câu lệnh mong muốn nằm trong top 5 kết quả.
- **MRR@10**: Mean Reciprocal Rank top 10.
- Thời gian phản hồi trung bình (ms/câu).

---

## 📁 Cấu trúc thư mục

```text
.
├── cheatsheet/              # Mã nguồn chính
│   ├── cli.py               # Triển khai CLI `chs`
│   ├── config.py            # Nạp cấu hình từ .env
│   ├── embed.py             # Script đánh embedding hàng loạt
│   ├── embedder.py          # Client gọi Ollama native /api/embed
│   ├── evaluate.py          # Script đo đạc chất lượng tìm kiếm
│   ├── extract.py           # Parser HTML trích xuất cards/entries
│   ├── search.py            # Hàm gọi hybrid search trong PostgreSQL
│   └── translate.py         # Module sinh bản dịch & query tiếng Việt
├── chs                      # Symlink trỏ tới cheatsheet/cli.py
├── data/                    # Dữ liệu JSON trung gian & bản dịch tiếng Việt
│   └── translations.vi.json # Bộ từ điển dịch & 3 cụm từ tìm kiếm tương ứng
├── db/
│   ├── schema.sql           # Cấu trúc bảng, index HNSW, tsvector, store procedures
│   └── seed/<slug>.sql      # Dữ liệu seed trích xuất, 1 file / sheet (sinh bởi extract)
├── docs/                    # Tài liệu kiến trúc phân chia theo Feature
│   ├── README.md            # File Index điều hướng tài liệu
│   └── features/            # Tài liệu chi tiết cho 8 module tính năng
├── eval/
│   └── queries.json         # Tập mẫu câu hỏi và kết quả kỳ vọng để benchmark
├── sheets/                  # Nguồn cheatsheet viết tay (JSON) + README định dạng
├── scripts/
│   └── setup.sh             # Script cài đặt và triển khai toàn bộ chỉ với 1 bước
├── web/
│   └── index.html           # Single Page Application giao diện Web tra cứu
├── docker-compose.yml       # Docker Compose chạy PostgreSQL pgvector
├── pyproject.toml           # Khai báo cấu hình dự án Python
├── uv.lock                  # Lockfile phiên bản thư viện
└── server.py                # Web server HTTP tĩnh & JSON API
```

---

## 🔧 Thêm Cheatsheet mới

1. Viết nguồn JSON `sheets/<slug>.json` theo định dạng ở [sheets/README.md](sheets/README.md) (card → section → item, mỗi item có `description` + `example` ngắn).
   Cách cũ vẫn chạy: đặt file HTML vào thư mục gốc (ví dụ: `docker.html`); trang có cấu trúc mới thì bổ sung parser trong [cheatsheet/extract.py](file:///home/mihb/Work/cheatsheet/cheatsheet/extract.py).
2. Chạy trích xuất:
   ```bash
   uv run -m cheatsheet.extract
   ```
3. Dịch và bổ sung từ khóa tìm kiếm tiếng Việt (mặc định agy; `--engine ollama` dùng model local `TRANSLATE_MODEL`, mặc định gemma4):
   ```bash
   uv run -m cheatsheet.translate
   ```
4. Cập nhật cơ sở dữ liệu và đánh vector mới:
   ```bash
   make load     # nạp db/schema.sql + db/seed/*.sql rồi embed phần mới (--prune)
   ```
   Hoặc gộp bước 2–4: `make reload` (`ENGINE=ollama make reload` để dịch bằng model local). Xem mọi lệnh: `make help`.

## 🧪 Kiểm thử

Sau khi đã nạp dữ liệu bằng `make load` và bật Ollama với model embedding đã cấu hình, chạy `make test`. Lệnh này khởi động PostgreSQL nếu cần, kiểm tra đủ 5 lệnh gợi ý của mọi sheet, chạy unit test và đo hiệu năng search trên ít nhất 5 tình huống thực tế. Trung bình từng tình huống và toàn bộ phải dưới `SEARCH_MAX_AVERAGE_MS` (mặc định 200 ms); thiếu dữ liệu hoặc dịch vụ sẽ làm test thất bại.

Quy định đo và cách bổ sung case khi mở rộng tính năng: [docs/performance-testing.md](docs/performance-testing.md).

---

## 📄 License

Mã nguồn được phát triển phục vụ mục đích học tập và tra cứu công việc cá nhân.
