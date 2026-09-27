"""Hybrid search (vector + keyword). Dùng chung cho server.py và công cụ debug bên dưới.

    uv run -m cheatsheet.search "câu lệnh tạo bảng trong mysql là gì?"
    uv run -m cheatsheet.search -s neovim -n 5 "xoá một dòng"
    uv run -m cheatsheet.search "mysql: tạo bảng"     # tiền tố "tool:" = chỉ tìm trong sheet đó

Phần __main__ chỉ để soát chất lượng truy vấn (in rank vector/keyword),
không phải CLI `chs` chính thức.
"""

import argparse
import re
import time
from typing import NamedTuple

from psycopg.rows import dict_row

from cheatsheet.config import EMBED_MODEL
from cheatsheet.embedder import embed, to_pgvector


# "mysql: tạo bảng" → tool "mysql" + câu hỏi "tạo bảng". Chỉ nhận tên tool ASCII để câu tiếng Việt
# có dấu hai chấm ("lỗi: ...") không bị hiểu nhầm là tiền tố.
PREFIX_RE = re.compile(r"\s*([a-z0-9][\w.+-]*)\s*:\s*(\S.*)", re.ASCII | re.IGNORECASE | re.DOTALL)


class Scope(NamedTuple):
    query: str                # câu hỏi đem đi tìm (đã bỏ tiền tố "tool:")
    sheet: str | None         # slug sheet cần lọc cứng; None → tìm mọi sheet
    explicit: bool            # người dùng đã chỉ rõ sheet (-s hoặc tiền tố)
    unknown: str | None = None  # tiền tố trông như tên tool nhưng không khớp sheet nào
    boost: tuple = ()         # sheet có tên trong câu hỏi → chỉ được cộng điểm, không lọc


def sheet_aliases(conn):
    """{alias/slug viết thường: slug}"""
    return {a.lower(): slug for slug, aliases in conn.execute("SELECT slug, slug || aliases FROM sheets")
            for a in aliases}


def parse_query(conn, query, sheet=None):
    """Tách phạm vi tìm kiếm khỏi câu hỏi: `sheet` (slug hoặc alias) hoặc tiền tố "tool:" trong query.

    Tiền tố phải bị bỏ khỏi văn bản embed — giữ "mysql:" trong vector làm hit@1 bộ eval giảm ~5 điểm.
    """
    aliases = sheet_aliases(conn)
    m = PREFIX_RE.fullmatch(query)
    prefix = m and aliases.get(m[1].lower())
    if prefix:
        query = m[2].strip()
    if sheet:
        slug = aliases.get(sheet.lower())
        if not slug:
            raise ValueError(f"không có sheet '{sheet}' (có: {', '.join(sorted(set(aliases.values())))};"
                             " viết tắt: chs --list)")
        return Scope(query, slug, True)
    if prefix:
        return Scope(query, prefix, True)
    named = {slug for a, slug in aliases.items() if re.search(rf"(?<!\w){re.escape(a)}(?!\w)", query, re.I)}
    # tiền tố lạ (vd "git:" khi chưa có sheet git, hay "error: ...") → giữ nguyên câu hỏi, tìm như thường
    return Scope(query, None, False, m[1] if m else None, tuple(sorted(named)))


def search(conn, scope, limit=10, kw_weight=0.15):
    vec = to_pgvector(embed([scope.query])[0])
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute("SELECT * FROM search_entries(%s, %s::vector, %s, %s, %s, %s, %s)",
                           (scope.query, vec, EMBED_MODEL, scope.sheet, limit, kw_weight,
                            list(scope.boost))).fetchall()


def main():
    import psycopg

    from cheatsheet.config import DATABASE_URL

    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("-s", "--sheet")
    ap.add_argument("-n", "--limit", type=int, default=8)
    args = ap.parse_args()
    t0 = time.perf_counter()
    with psycopg.connect(DATABASE_URL) as conn:
        rows = search(conn, parse_query(conn, args.query, args.sheet), args.limit)
    print(f"({(time.perf_counter() - t0) * 1000:.0f} ms)")
    for r in rows:
        ctx = " › ".join(x for x in (r["sheet"], r["card"], r["section"]) if x)
        sim = f"{r['similarity']:.3f}" if r["similarity"] is not None else "  -  "
        print(f"{r['score']:.3f}  sim={sim} kw={r['kw_ratio'] or 0:.2f}  [{ctx}]")
        print(f"    {r['command'] or ''}" + (f"   # {r['description']}" if r["description"] else ""))
        if r["description_vi"]:
            print(f"    ↳ {r['description_vi']}")


if __name__ == "__main__":
    main()
