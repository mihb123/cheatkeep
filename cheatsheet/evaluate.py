"""Đo chất lượng search trên bộ câu hỏi mẫu eval/queries.json.

    uv run -m cheatsheet.evaluate           # hit@1, hit@5, MRR@10 + các câu trượt
    uv run -m cheatsheet.evaluate -v        # in cả hạng của từng câu

Mỗi câu có `expect` là danh sách tiền tố lệnh; kết quả đúng khi `command` bắt đầu bằng
một trong các tiền tố (và thuộc `sheet` nếu có ghi). Câu không nêu tool chấp nhận đáp án đúng ở
mọi sheet; phần tử dạng {"sheet": "grep", "cmd": "-n"} chỉ đúng khi nằm ở sheet đó (tránh `-n`
của sed có nghĩa khác).
"""

import argparse
import json
import time

import psycopg

from cheatsheet.config import DATABASE_URL, ROOT
from cheatsheet.search import parse_query, search

K = 10


def matches(row, expect, sheet):
    if isinstance(expect, dict):
        sheet, expect = expect["sheet"], expect["cmd"]
    return (row["command"] or "").startswith(expect) and (sheet is None or row["sheet"] == sheet)


def rank_of(rows, case):
    for i, r in enumerate(rows, 1):
        if any(matches(r, e, case.get("sheet")) for e in case["expect"]):
            return i
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("-w", "--kw-weight", type=float, default=0.15)
    ap.add_argument("--file", default=str(ROOT / "eval" / "queries.json"))
    args = ap.parse_args()
    cases = json.loads(open(args.file, encoding="utf-8").read())
    ranks, t0 = [], time.perf_counter()
    with psycopg.connect(DATABASE_URL) as conn:
        for c in cases:
            rows = search(conn, parse_query(conn, c["q"]), K, args.kw_weight)
            rk = rank_of(rows, c)
            ranks.append(rk)
            if args.verbose or not rk or rk > 1:
                top = (rows[0]["command"] or rows[0]["description"] or "").splitlines()[0][:50] if rows else "-"
                print(f"{('#' + str(rk)) if rk else 'miss':>5}  {c['q']:<50}  top1: {top}")
    n = len(cases)
    hit1 = sum(1 for r in ranks if r == 1) / n
    hit5 = sum(1 for r in ranks if r and r <= 5) / n
    mrr = sum(1 / r for r in ranks if r) / n
    ms = (time.perf_counter() - t0) * 1000 / n
    print(f"\n{n} câu · hit@1 {hit1:.1%} · hit@5 {hit5:.1%} · MRR@{K} {mrr:.3f} · {ms:.0f} ms/câu")


if __name__ == "__main__":
    main()
