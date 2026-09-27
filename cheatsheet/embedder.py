"""Client tối giản cho Ollama /api/embed (stdlib, không thêm dependency).

Ollama chạy native trên máy (systemd service `ollama`), không chạy trong Docker.
"""

import json
import urllib.error
import urllib.request

from cheatsheet.config import EMBED_DIM, EMBED_MODEL, OLLAMA_KEEP_ALIVE, OLLAMA_URL


class EmbedError(RuntimeError):
    pass


def embed(texts, model=EMBED_MODEL, timeout=300):
    """list[str] → list[list[float]] (đã chuẩn hoá L2 bởi Ollama)."""
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/embed",
        data=json.dumps({"model": model, "input": texts, "keep_alive": OLLAMA_KEEP_ALIVE}).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            vecs = json.load(r)["embeddings"]
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace").strip()
        if e.code == 404:
            raise EmbedError(f"Ollama chưa có model {model} — chạy: ollama pull {model}") from e
        raise EmbedError(f"Ollama lỗi {e.code}: {detail}") from e
    except urllib.error.URLError as e:
        raise EmbedError(f"Không kết nối được Ollama ở {OLLAMA_URL} ({e.reason}) — "
                         "chạy: sudo systemctl start ollama") from e
    if vecs and len(vecs[0]) != EMBED_DIM:
        raise EmbedError(f"{model} trả về {len(vecs[0])} chiều, schema đang là vector({EMBED_DIM})")
    return vecs


def model_digest(model=EMBED_MODEL, timeout=5):
    """Digest của model trong Ollama (đổi khi `ollama pull` ra bản mới); None nếu không xác định được."""
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=timeout) as r:
            models = json.load(r)["models"]
    except (urllib.error.URLError, KeyError, ValueError):
        return None
    names = {model, model if ":" in model else f"{model}:latest"}
    return next((m["digest"] for m in models if m.get("name") in names), None)


def to_pgvector(vec):
    """list[float] → literal '[...]' để cast ::vector trong SQL."""
    return "[" + ",".join(f"{x:.7g}" for x in vec) + "]"
