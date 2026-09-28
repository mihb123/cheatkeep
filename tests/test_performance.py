import json
import statistics
import time
import unittest

import psycopg

from cheatsheet.config import DATABASE_URL, EMBED_MODEL, ROOT, SEARCH_COLON_FREE_PREFIXES, SEARCH_MAX_AVERAGE_MS
from cheatsheet.search import lookup, parse_query


CASES = (
    "atuin: ",
    "mysql: tạo bảng",
    "mysql: purple elephant dancing",
    "grep: hiển thị số dòng khớp",
    "atuin hook",
    "xoá dòng trong vim",
    "xem danh sách các bảng",
    "curl download file",
    "find and replace in vim",
)
REPETITIONS = 5
def run_query(conn, query):
    return lookup(conn, parse_query(conn, query), 5).rows


class SearchPerformanceTest(unittest.TestCase):
    def test_search_average_under_configured_limit_for_each_case(self):
        self.assertGreaterEqual(len(CASES), 5)
        self.assertTrue(DATABASE_URL, "Thiếu DATABASE_URL; cấu hình .env trước khi chạy make test")
        failures = []
        all_samples = []
        results = []

        with psycopg.connect(DATABASE_URL, connect_timeout=5) as conn:
            entries = conn.execute("SELECT count(*) FROM entries").fetchone()[0]
            indexed = conn.execute(
                "SELECT count(*) FROM entries e WHERE EXISTS "
                "(SELECT 1 FROM embeddings v WHERE v.content_hash = e.content_hash AND v.model = %s)",
                (EMBED_MODEL,),
            ).fetchone()[0]
            self.assertGreater(entries, 0, "DB chưa có entries; chạy make load")
            self.assertEqual(indexed, entries, f"Thiếu vector {EMBED_MODEL} cho entries; chạy make embed")

            for query in CASES:
                run_query(conn, query)
                samples = []
                for _ in range(REPETITIONS):
                    started = time.perf_counter_ns()
                    rows = run_query(conn, query)
                    samples.append((time.perf_counter_ns() - started) / 1_000_000)
                    self.assertTrue(rows, f"Search không trả kết quả: {query}")
                if query == "atuin: ":
                    expected = json.loads((ROOT / "sheets" / "atuin.json").read_text(encoding="utf-8"))["popular_commands"]
                    self.assertEqual([row["command"] for row in rows], expected)
                if query == "atuin hook" and "atuin" in SEARCH_COLON_FREE_PREFIXES:
                    self.assertTrue(all(row["sheet"] == "atuin" for row in rows))
                if query == "find and replace in vim" and "find" not in SEARCH_COLON_FREE_PREFIXES:
                    self.assertEqual(rows[0]["sheet"], "neovim")

                average = statistics.mean(samples)
                all_samples.extend(samples)
                results.append((query, average))
                if average >= SEARCH_MAX_AVERAGE_MS:
                    failures.append(f"{query}: {average:.1f} ms")

        overall_average = statistics.mean(all_samples)
        print(f"\nHIỆU NĂNG SEARCH · {len(CASES)} case × {REPETITIONS} lần · ngưỡng <{SEARCH_MAX_AVERAGE_MS:g} ms/case")
        print(f"  {'#':>2}  {'TRUY VẤN':<36}  {'TB (ms)':>8}  KẾT QUẢ")
        for index, (query, average) in enumerate(results, 1):
            print(f"  {index:>2}  {query.strip():<36}  {average:>8.1f}  {'ĐẠT' if average < SEARCH_MAX_AVERAGE_MS else 'TRƯỢT'}")
        print(f"  Trung bình chung: {overall_average:.1f} ms\n", flush=True)
        self.assertLess(overall_average, SEARCH_MAX_AVERAGE_MS,
                        f"Trung bình tổng vượt {SEARCH_MAX_AVERAGE_MS:g} ms")
        self.assertFalse(failures, f"Trung bình từng case phải dưới {SEARCH_MAX_AVERAGE_MS:g} ms: {', '.join(failures)}")
