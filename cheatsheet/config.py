"""Cấu hình chung, đọc từ .env ở thư mục gốc (biến môi trường có sẵn được ưu tiên)."""

import math
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_env(path=ROOT / ".env"):
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        m = re.match(r"^\s*([A-Z_][A-Z0-9_]*)\s*=\s*(.*?)\s*$", line)
        if m and not line.lstrip().startswith("#"):
            os.environ.setdefault(m[1], m[2].strip("'\""))


_load_env()

DATABASE_URL = os.environ.get("DATABASE_URL", "")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")  # Ollama native (systemd)
OLLAMA_KEEP_ALIVE = os.environ.get("OLLAMA_KEEP_ALIVE", "1h")        # giữ model trong RAM giữa các lần gọi
EMBED_MODEL = os.environ.get("EMBED_MODEL", "bge-m3")
EMBED_DIM = int(os.environ.get("EMBED_DIM", "1024"))
APP_HOST = os.environ.get("APP_HOST", "127.0.0.1")
APP_PORT = int(os.environ.get("APP_PORT", "8080"))
SEARCH_COLON_FREE_PREFIXES = frozenset(
    prefix.strip().lower()
    for prefix in os.environ.get(
        "SEARCH_COLON_FREE_PREFIXES",
        "atuin,awk,gawk,bash,curl,egrep,grep,jq,jqlang,mongo,mongodb,mongosh,mysql,"
        "neovim,nvim,vim,pg,postgres,postgresql,psql,sed,gunzip,gzip,tar,unzip,zip,xargs",
    ).split(",")
    if prefix.strip()
)
if any(not re.fullmatch(r"[a-z0-9][\w.+-]*", prefix, re.ASCII) for prefix in SEARCH_COLON_FREE_PREFIXES):
    raise ValueError("SEARCH_COLON_FREE_PREFIXES chỉ nhận alias ASCII, cách nhau bằng dấu phẩy")
SEARCH_MIN_SIMILARITY = float(os.environ.get("SEARCH_MIN_SIMILARITY", "0.40"))
SEARCH_MAX_AVERAGE_MS = float(os.environ.get("SEARCH_MAX_AVERAGE_MS", "200"))
if not 0 <= SEARCH_MIN_SIMILARITY <= 1:
    raise ValueError("SEARCH_MIN_SIMILARITY phải từ 0 đến 1")
if not math.isfinite(SEARCH_MAX_AVERAGE_MS) or SEARCH_MAX_AVERAGE_MS <= 0:
    raise ValueError("SEARCH_MAX_AVERAGE_MS phải lớn hơn 0")
