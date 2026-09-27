"""Sinh bản dịch tiếng Việt cho entry chưa có, bằng Antigravity CLI (`agy`) → data/translations.vi.json.

    uv run -m cheatsheet.translate            # chỉ dịch entry mới / đã đổi nội dung, rồi chạy lại extract
    uv run -m cheatsheet.translate --dry-run  # đếm số entry cần dịch
    uv run -m cheatsheet.translate --engine ollama  # dịch bằng model local (TRANSLATE_MODEL, mặc định gemma4)

Engine agy (mặc định) dịch tốt hơn; lượt 2 dịch lại phần agy bỏ sót bằng Ollama nếu Ollama đang chạy.

Đọc data/*.json do cheatsheet.extract sinh ra. Mỗi bản dịch khoá theo content_hash (sha256 của
embed_text tiếng Anh) nên chạy lại an toàn; entry đổi nội dung sẽ được dịch lại. File kết quả nên
được commit/soát tay như dữ liệu nguồn — sửa tay vẫn giữ nguyên ở các lần chạy sau.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

from cheatsheet.config import OLLAMA_KEEP_ALIVE, OLLAMA_URL, ROOT
from cheatsheet.extract import TRANSLATIONS, load_translations

MODEL = os.environ.get("TRANSLATE_AGY_MODEL", "gemini-3.8-flash-medium")  # dịch là việc dễ → Flash Medium là đủ
BATCH = 40
WORKERS = 4
OLLAMA_MODEL = os.environ.get("TRANSLATE_MODEL", "gemma4")
OLLAMA_BATCH = 15  # model local giữ chất lượng tốt hơn với batch nhỏ
OLLAMA_WORKERS = 4  # Ollama chỉ chạy song song tối đa 4 request

SCHEMA = {
    "type": "object",
    "properties": {"items": {"type": "array", "items": {
        "type": "object",
        "properties": {"id": {"type": "string"}, "vi": {"type": "string"},
                       "q": {"type": "array", "items": {"type": "string"}}},
        "required": ["id", "vi", "q"]}}},
    "required": ["items"],
}

PROMPT = """Bạn dịch cheatsheet kỹ thuật cho người dùng Việt Nam. Dữ liệu dùng để tìm kiếm ngữ nghĩa:
người dùng gõ câu hỏi tiếng Việt, hệ thống phải tìm ra đúng entry. Mỗi entry là một lệnh, phím tắt,
tuỳ chọn cấu hình hoặc ghi chú, kèm ngữ cảnh sheet › card › section.

Với MỖI entry trả về:
- id: giữ nguyên id đầu vào.
- vi: mô tả tiếng Việt ngắn (tối đa ~15 từ) nói entry này LÀM GÌ. Dịch theo nghĩa, không dịch sát chữ.
  Giữ nguyên thuật ngữ quen dùng (database, commit, buffer, LSP, regex...), khi có từ Việt phổ biến thì
  ghi kèm, vd "Sao lưu (backup) database ra file SQL". Nếu description trống thì suy ra từ command và
  ngữ cảnh card/section. Entry kind=note thì dịch nội dung ghi chú. Placeholder như <user>, table,
  field1 giữ nguyên.
- q: đúng 3 cụm từ tìm kiếm tiếng Việt KHÁC NHAU mà người dùng có thể gõ để tìm đúng entry này.
  Dùng từ đồng nghĩa khác nhau (xoá/gỡ bỏ, sao chép/copy, hiển thị/xem/liệt kê...) và đủ cụ thể để
  phân biệt với entry tương tự cùng card (vd `dd` xoá dòng khác `dw` xoá từ). KHÔNG mở đầu bằng từ đệm
  "cách", "làm sao", "lệnh", "câu lệnh"; KHÔNG chứa tên tool (mysql, vim, neovim, atuin).
- Không bịa tính năng không có trong entry. Không bỏ sót entry nào.

Entries (JSON):
"""


def pending_entries(translations):
    todo, seen = [], set()
    for path in sorted((ROOT / "data").glob("*.json")):
        if path == TRANSLATIONS or path.name.startswith("eval"):
            continue
        sheet = json.loads(path.read_text(encoding="utf-8"))
        for e in sheet.get("entries", []):
            h = e["content_hash"]
            if h in translations or h in seen:
                continue
            seen.add(h)
            todo.append({"hash": h, "sheet": sheet["slug"], "card": e["card"], "section": e["section"],
                         "kind": e["kind"], "command": (e["command"] or "")[:400] or None,
                         "description": e["description"], "details": (e["details"] or "")[:300] or None,
                         "example": e["example"] if e["example"] != e["command"] else None})
    return todo


def prompt_for(batch):
    payload = [{"id": str(i), **{k: v for k, v in e.items() if k != "hash" and v}} for i, e in enumerate(batch)]
    return PROMPT + json.dumps(payload, ensure_ascii=False, indent=1)


def collect(batch, items):
    result = {}
    for it in items:
        i = int(it["id"]) if it["id"].isdigit() else -1
        if 0 <= i < len(batch) and it["vi"].strip():
            result[batch[i]["hash"]] = {"src": f"{batch[i]['sheet']} · {(batch[i]['command'] or batch[i]['description'] or '')[:60]}",
                                        "vi": it["vi"].strip(),
                                        "q": [q.strip() for q in it["q"] if q.strip()][:3]}
    return result


def run_agy(batch, schema_path):
    proc = subprocess.run(
        ["agy", "-p", prompt_for(batch),
         "--model", MODEL, "--output-format", "json", "--json-schema", schema_path,
         "--disable-slash-commands", "--print-timeout", "10m"],
        capture_output=True, text=True, cwd=tempfile.gettempdir())
    if proc.returncode:
        raise RuntimeError(f"agy lỗi {proc.returncode}: {proc.stderr.strip()[-500:]}")
    out = json.loads(proc.stdout)
    if out.get("status") != "SUCCESS":
        raise RuntimeError(f"agy status {out.get('status')}: {str(out.get('response'))[:300]}")
    return collect(batch, (out.get("structured_output") or {}).get("items", []))


def run_ollama(batch, _schema_path=None):
    body = {"model": OLLAMA_MODEL, "stream": False, "format": SCHEMA, "think": False,
            "keep_alive": OLLAMA_KEEP_ALIVE, "options": {"temperature": 0.2},
            "messages": [{"role": "user", "content": prompt_for(batch)}]}
    req = urllib.request.Request(f"{OLLAMA_URL}/api/chat", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as r:
        content = json.load(r)["message"]["content"]
    return collect(batch, json.loads(content).get("items", []))


def ollama_ready():
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=5) as r:
            names = {m["name"] for m in json.load(r)["models"]}
    except OSError:
        return False
    return OLLAMA_MODEL in names or f"{OLLAMA_MODEL}:latest" in names


def save(translations):
    TRANSLATIONS.write_text(json.dumps(translations, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def main():
    translations = load_translations()
    todo = pending_entries(translations)
    print(f"{len(todo)} entry cần dịch ({len(translations)} đã có)")
    if not todo or "--dry-run" in sys.argv:
        return 0
    engine = sys.argv[sys.argv.index("--engine") + 1] if "--engine" in sys.argv else "agy"
    engines = {"agy": (run_agy, BATCH, WORKERS), "ollama": (run_ollama, OLLAMA_BATCH, OLLAMA_WORKERS)}
    if engine == "agy" and not shutil.which("agy"):
        print("⚠ không tìm thấy agy (Antigravity CLI) — chuyển sang Ollama", file=sys.stderr)
        engine = "ollama"
    passes = [engine, "ollama"] if engine == "agy" else ["ollama", "ollama"]
    if "ollama" in passes and not ollama_ready():
        if engine == "ollama":
            print(f"✗ Ollama chưa chạy hoặc chưa có model {OLLAMA_MODEL} — bỏ qua bước dịch", file=sys.stderr)
            return 1
        passes = ["agy", "agy"]

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(SCHEMA, f)
    for attempt, name in enumerate(passes, 1):  # lượt 2: dịch lại entry bị bỏ sót / batch lỗi
        run, size, workers = engines[name]
        print(f"lượt {attempt}: {name} ({len(todo)} entry)")
        batches = [todo[i:i + size] for i in range(0, len(todo), size)]
        with ThreadPoolExecutor(workers) as ex:
            futs = {ex.submit(run, b, f.name): b for b in batches}
            for fut in as_completed(futs):
                try:
                    got = fut.result()
                except Exception as e:  # noqa: BLE001 — 1 batch lỗi không làm mất batch khác
                    print(f"  ✗ batch lỗi: {e}", file=sys.stderr)
                    continue
                translations.update(got)
                save(translations)
                print(f"  +{len(got)}/{len(futs[fut])}  (tổng {len(translations)})")
        todo = [e for e in todo if e["hash"] not in translations]
        if not todo:
            break
        print(f"lượt {attempt}: còn {len(todo)} entry chưa dịch")

    from cheatsheet import extract
    extract.main()
    return 1 if todo else 0


if __name__ == "__main__":
    sys.exit(main())
