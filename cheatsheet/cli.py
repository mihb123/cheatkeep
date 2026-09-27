#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["psycopg[binary]>=3.2"]
# ///
"""chs — hỏi cheatsheet bằng ngôn ngữ tự nhiên ngay trên terminal.

    chs "câu lệnh tạo bảng trong mysql là gì?"
    chs -s neovim "chia đôi màn hình theo chiều dọc"
    chs -c "backup database mysql"        # copy lệnh tốt nhất vào clipboard
    eval "$(chs -p 'tìm lệnh lỗi trong thư mục hiện tại')"
    chs --list

Chạy độc lập qua shebang `uv run --script` (tự cài psycopg vào cache của uv), đọc cấu hình
từ .env ở thư mục gốc project — kể cả khi được gọi qua symlink ở nơi khác.
Cần: Postgres (docker compose up -d) và Ollama native (systemctl start ollama).
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # resolve() đi qua symlink → thư mục project
sys.path.insert(0, str(ROOT))

import psycopg  # noqa: E402

from cheatsheet.config import DATABASE_URL  # noqa: E402
from cheatsheet.embedder import EmbedError  # noqa: E402
from cheatsheet.search import search  # noqa: E402


# ------------------------------------------------------------------ output

class Style:
    def __init__(self, enabled):
        codes = {"bold": "1", "dim": "2", "red": "31", "green": "32", "yellow": "33", "cyan": "36"}
        for name, code in codes.items():
            setattr(self, name, (lambda s, c=code: f"\033[{c}m{s}\033[0m") if enabled else (lambda s: s))


def use_color(stream):
    return stream.isatty() and "NO_COLOR" not in os.environ and os.environ.get("TERM") != "dumb"


def print_results(rows, st, verbose):
    width = len(str(len(rows)))
    pad = " " * (width + 3)
    for i, r in enumerate(rows, 1):
        cmd = r["command"] or r["description"] or ""
        lines = cmd.splitlines() or [""]
        print(f"{st.dim(f'{i:>{width}}.')}  {st.bold(st.cyan(lines[0]))}")
        for extra in lines[1:]:
            print(pad + st.cyan(extra))
        if r["command"] and r["description"]:
            print(pad + r["description"])
        if r["description_vi"] and r["description_vi"] != r["description"]:
            print(pad + st.dim(r["description_vi"]))
        if r["danger"]:
            print(pad + st.red(f"⚠ {r['danger']}"))
        if verbose and r["details"]:
            print(pad + st.dim(r["details"]))
        if verbose and r["example"] and r["example"] != r["command"]:
            print(pad + st.dim("vd: ") + r["example"])
        ctx = " › ".join(x for x in (r["sheet"], r["card"], r["section"]) if x)
        score = f"  {r['score']:.3f}" if verbose else ""
        print(pad + st.dim(ctx + score))
        if i < len(rows):
            print()


def copy_to_clipboard(text):
    for cmd in (["wl-copy"], ["xclip", "-selection", "clipboard"], ["xsel", "-ib"], ["pbcopy"]):
        if shutil.which(cmd[0]):
            subprocess.run(cmd, input=text.encode(), check=True)
            return cmd[0]
    return None


# ------------------------------------------------------------------ main

def list_sheets(conn, st):
    rows = conn.execute("SELECT slug, title, entries FROM sheet_list").fetchall()
    aliases = dict(conn.execute("SELECT slug, array_to_string(aliases, ', ') FROM sheets").fetchall())
    for slug, title, n in rows:
        print(f"{st.bold(slug):<20} {title}  {st.dim(f'({n} entries · alias: {aliases.get(slug, "")})')}")


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="chs", description="Tìm lệnh trong cheatsheet bằng câu hỏi tự nhiên (vector + keyword).")
    ap.add_argument("query", nargs="*", help="câu hỏi; bỏ trống thì đọc từ stdin")
    ap.add_argument("-s", "--sheet", help="chỉ tìm trong 1 sheet (slug, vd mysql)")
    ap.add_argument("-n", "--limit", type=int, default=5, help="số kết quả (mặc định 5)")
    ap.add_argument("-c", "--copy", action="store_true", help="copy lệnh tốt nhất vào clipboard")
    ap.add_argument("-p", "--print", dest="print_only", action="store_true",
                    help="chỉ in lệnh tốt nhất (dùng với $(...) hoặc widget shell)")
    ap.add_argument("-v", "--verbose", action="store_true", help="hiện giải thích, ví dụ, điểm")
    ap.add_argument("--json", action="store_true", help="xuất JSON")
    ap.add_argument("--list", action="store_true", help="liệt kê các sheet")
    args = ap.parse_args(argv)

    st = Style(use_color(sys.stdout))
    err = Style(use_color(sys.stderr))
    query = " ".join(args.query).strip()
    if not query and not args.list and not sys.stdin.isatty():
        query = sys.stdin.read().strip()
    if not query and not args.list:
        ap.print_usage(sys.stderr)
        return 2

    try:
        with psycopg.connect(DATABASE_URL, connect_timeout=3) as conn:
            if args.list:
                list_sheets(conn, st)
                return 0
            rows = search(conn, query, args.sheet, 1 if args.print_only else max(1, args.limit))
    except EmbedError as e:
        print(err.red(f"chs: {e}"), file=sys.stderr)
        return 3
    except psycopg.OperationalError as e:
        print(err.red(f"chs: không kết nối được Postgres ({str(e).strip().splitlines()[0]})\n"
                      f"     chạy: cd {ROOT} && docker compose up -d"), file=sys.stderr)
        return 3

    if not rows:
        print(err.yellow("chs: không tìm thấy kết quả"), file=sys.stderr)
        return 1

    best = next((r["command"] for r in rows if r["command"]), None)
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2, default=float))
    elif args.print_only:
        print(best or rows[0]["description"])
    else:
        print_results(rows, st, args.verbose)

    if args.copy and best:
        tool = copy_to_clipboard(best)
        msg = f"✓ đã copy: {best}" if tool else "✗ không tìm thấy wl-copy/xclip/xsel/pbcopy"
        print(err.green(msg) if tool else err.red(msg), file=sys.stderr)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
