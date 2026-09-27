"""Hybrid search (vector + keyword). Dùng chung cho server.py và công cụ debug bên dưới.

    uv run -m cheatsheet.search "câu lệnh tạo bảng trong mysql là gì?"
    uv run -m cheatsheet.search -s neovim -n 5 "xoá một dòng"

Phần __main__ chỉ để soát chất lượng truy vấn (in rank vector/keyword),
không phải CLI `chs` chính thức.
"""

import argparse
import time

from psycopg.rows import dict_row

from cheatsheet.config import EMBED_MODEL
from cheatsheet.embedder import embed, to_pgvector


def search(conn, query, sheet=None, limit=10, kw_weight=0.15):
    vec = to_pgvector(embed([query])[0])
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute("SELECT * FROM search_entries(%s, %s::vector, %s, %s, %s, %s)",
                           (query, vec, EMBED_MODEL, sheet, limit, kw_weight)).fetchall()


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
        rows = search(conn, args.query, args.sheet, args.limit)
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
