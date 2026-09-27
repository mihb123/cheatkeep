"""Server tối giản: phục vụ web/index.html + JSON API đọc từ Postgres.

    air                         # tự reload khi đổi code (dùng air như Golang)
    uv run server.py --reload   # tự reload tích hợp sẵn không cần công cụ ngoài
    uv run server.py            # chạy thông thường (http://127.0.0.1:$APP_PORT)

GET /api/cheatsheets              → danh sách sheet
GET /api/cheatsheets/<slug>       → toàn bộ 1 sheet dạng card/section/item (sheet_json)
GET /api/search?q=..&sheet=..&limit=..
                                  → hybrid search (vector + keyword) — API cho CLI `chs`
GET /<slug>                       → web/index.html (frontend tự fetch API theo path)
"""

import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import psycopg
from psycopg_pool import ConnectionPool

from cheatsheet.config import APP_HOST, APP_PORT, DATABASE_URL, ROOT
from cheatsheet.embedder import EmbedError
from cheatsheet.search import search

WEB = ROOT / "web"
pool = ConnectionPool(DATABASE_URL, min_size=1, max_size=4, open=True, check=ConnectionPool.check_connection)

STATIC_TYPES = {".html": "text/html; charset=utf-8", ".css": "text/css", ".js": "text/javascript",
                ".png": "image/png", ".svg": "image/svg+xml", ".ico": "image/x-icon"}


class Handler(BaseHTTPRequestHandler):
    def send(self, status, body, ctype="application/json; charset=utf-8"):
        if not isinstance(body, (bytes, str)):
            body = json.dumps(body, ensure_ascii=False)
        data = body if isinstance(body, bytes) else body.encode()
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        url = urlsplit(self.path)
        path, qs = url.path, {k: v[0] for k, v in parse_qs(url.query).items()}
        try:
            if path == "/api/cheatsheets":
                with pool.connection() as conn:
                    rows = conn.execute("SELECT slug, title, subtitle, cards, entries FROM sheet_list").fetchall()
                keys = ("slug", "title", "subtitle", "cards", "entries")
                return self.send(200, [dict(zip(keys, r)) for r in rows])

            m = re.fullmatch(r"/api/cheatsheets/([\w-]+)", path)
            if m:
                with pool.connection() as conn:
                    row = conn.execute("SELECT sheet_json(%s)", (m[1],)).fetchone()[0]
                return self.send(404, {"error": "not found"}) if row is None else self.send(200, row)

            if path == "/api/search":
                q = qs.get("q", "").strip()
                if not q:
                    return self.send(400, {"error": "missing q"})
                limit = max(1, min(int(qs.get("limit", 10)), 50))
                with pool.connection() as conn:
                    rows = search(conn, q, qs.get("sheet") or None, limit)
                return self.send(200, {"query": q, "results": rows})

            if path.startswith("/api/"):
                return self.send(404, {"error": "not found"})

            # file tĩnh trong web/, còn lại trả index.html (routing phía client)
            f = (WEB / path.lstrip("/")).resolve()
            if f.is_file() and f.is_relative_to(WEB):
                return self.send(200, f.read_bytes(), STATIC_TYPES.get(f.suffix, "application/octet-stream"))
            return self.send(200, (WEB / "index.html").read_bytes(), STATIC_TYPES[".html"])
        except ValueError as e:
            return self.send(400, {"error": str(e)})
        except EmbedError as e:
            return self.send(503, {"error": str(e)})
        except psycopg.Error as e:
            return self.send(500, {"error": str(e).strip()})


class ReusableServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def serve():
    srv = ReusableServer((APP_HOST, APP_PORT), Handler)
    print(f"→ http://{APP_HOST}:{APP_PORT}")
    try:
        srv.serve_forever()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        try:
            srv.server_close()
        except Exception:
            pass
        try:
            pool.close()
        except Exception:
            pass


def watch_and_serve():
    """Tự động reload khi code thay đổi (cơ chế watch tương tự air)."""
    import subprocess
    import sys
    import time
    from pathlib import Path

    watch_dirs = [ROOT / "cheatsheet", ROOT / "web", ROOT / "db"]
    watch_files = [ROOT / "server.py", ROOT / ".env", ROOT / "pyproject.toml"]
    watch_exts = {".py", ".html", ".env", ".toml", ".sql", ".json"}

    def get_mtimes():
        mtimes = {}
        for f in watch_files:
            if f.exists():
                try:
                    mtimes[str(f)] = f.stat().st_mtime
                except OSError:
                    pass
        for d in watch_dirs:
            if d.exists():
                for p in d.rglob("*"):
                    if p.is_file() and p.suffix in watch_exts and "__pycache__" not in p.parts:
                        try:
                            mtimes[str(p)] = p.stat().st_mtime
                        except OSError:
                            pass
        return mtimes

    last_mtimes = get_mtimes()
    cmd = [sys.executable, str(ROOT / "server.py"), "--no-reload"]
    proc = subprocess.Popen(cmd)
    print(f"⚡ [auto-reload] Đang theo dõi thay đổi code tại {ROOT}")

    try:
        while True:
            time.sleep(0.4)
            current_mtimes = get_mtimes()
            changed = [Path(p).name for p, m in current_mtimes.items() if p not in last_mtimes or m > last_mtimes[p]]
            changed += [Path(p).name for p in last_mtimes if p not in current_mtimes]

            if changed:
                last_mtimes = current_mtimes
                info = ", ".join(changed[:3]) + ("..." if len(changed) > 3 else "")
                print(f"🔄 [auto-reload] Phát hiện thay đổi ({info}) → Đang reload server...")
                if proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                proc = subprocess.Popen(cmd)
    except KeyboardInterrupt:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
        print("\n👋 Server stopped.")


if __name__ == "__main__":
    import sys
    if "--reload" in sys.argv or "-r" in sys.argv:
        watch_and_serve()
    else:
        serve()
