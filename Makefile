# Nạp dữ liệu cheatsheet vào Postgres (pgvector) — xem `make help`.
# schema.sql tạo lại sheets/entries, db/seed/<slug>.sql INSERT từng sheet; bảng embeddings giữ nguyên,
# nên nạp lại bao nhiêu lần cũng chỉ embed phần văn bản mới/đổi.

SHELL  := bash
ENGINE ?= agy   # engine dịch: agy | ollama

PSQL = docker compose exec -T db sh -c 'psql -v ON_ERROR_STOP=1 -q -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"'

.DEFAULT_GOAL := help
.PHONY: help setup up down extract translate seed load reload embed status psql serve eval

help:  ## Liệt kê lệnh
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

setup:  ## Cài đặt lần đầu (.env, container, Ollama, nạp + embed)
	./scripts/setup.sh

up:  ## Bật Postgres, chờ healthy
	docker compose up -d --wait

down:  ## Tắt Postgres (giữ volume)
	docker compose down

extract:  ## sheets/*.json + *.html → data/*.json, db/seed/<slug>.sql
	uv run -q -m cheatsheet.extract

translate:  ## Dịch entry mới sang tiếng Việt (ENGINE=agy|ollama); tự extract lại
	uv run -q -m cheatsheet.translate --engine $(strip $(ENGINE)) \
	  || echo "⚠ còn entry chưa có bản dịch tiếng Việt (search vẫn chạy, kém chính xác hơn)" >&2

seed: up  ## Nạp db/schema.sql + db/seed/*.sql (bảng embeddings giữ nguyên)
	cat db/schema.sql db/seed/*.sql | $(PSQL)

embed: up  ## Embed văn bản mới/đổi + dọn vector mồ côi
	uv run -q -m cheatsheet.embed --prune

load: seed embed status  ## Nạp db/seed/*.sql đang có vào DB rồi embed (không extract/dịch)

reload: extract translate load  ## Sinh lại seed từ sheets/ + dịch rồi nạp vào DB

status: up  ## Số entry mỗi sheet, số vector
	@docker compose exec -T db sh -c 'psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB" -c "TABLE sheet_list" \
	  -c "SELECT model, count(*) AS vectors FROM embeddings GROUP BY model"'

psql: up  ## Mở psql trong container
	docker compose exec -it db sh -c 'psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"'

serve:  ## Chạy web server
	uv run server.py

eval:  ## Đo hit@1 / hit@5 / MRR
	uv run -m cheatsheet.evaluate
