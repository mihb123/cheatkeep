import json
import unittest

import psycopg

from cheatsheet.config import DATABASE_URL, ROOT
from cheatsheet.search import parse_query, popular_entries


class PopularCommandsTest(unittest.TestCase):
    def test_every_sheet_has_five_curated_commands_in_seed(self):
        with psycopg.connect(DATABASE_URL, connect_timeout=5) as conn:
            sheets = conn.execute("SELECT slug, meta->'popular_commands' FROM sheets ORDER BY slug").fetchall()
            self.assertTrue(sheets, "DB chưa có sheets; chạy make load")
            for slug, commands in sheets:
                with self.subTest(sheet=slug):
                    source = json.loads((ROOT / "sheets" / f"{slug}.json").read_text(encoding="utf-8"))
                    self.assertEqual(len(source["popular_commands"]), 5)
                    self.assertEqual(commands, source["popular_commands"], f"Seed {slug} cũ; chạy make extract && make load")
                    rows = popular_entries(conn, parse_query(conn, slug))
                    self.assertEqual([row["command"] for row in rows], commands)
