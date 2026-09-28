import unittest
from unittest.mock import patch

from cheatsheet.search import Scope, lookup, parse_query


class Connection:
    def execute(self, query):
        return [("atuin", ["atuin"]), ("find", ["find"]), ("neovim", ["neovim", "nvim", "vim"])]


class ParseQueryTest(unittest.TestCase):
    def setUp(self):
        self.conn = Connection()

    def test_bare_colon_lists_popular_commands(self):
        scope = parse_query(self.conn, "atuin: ")
        self.assertEqual((scope.query, scope.sheet, scope.explicit, scope.browse), ("", "atuin", True, True))

    def test_empty_query_with_sheet_browses(self):
        scope = parse_query(self.conn, "", "atuin")
        self.assertEqual((scope.query, scope.sheet, scope.browse), ("", "atuin", True))

    def test_leading_sheet_without_colon_scopes_search(self):
        with patch("cheatsheet.search.SEARCH_COLON_FREE_PREFIXES", frozenset({"atuin"})):
            scope = parse_query(self.conn, "atuin hook")
        self.assertEqual((scope.query, scope.sheet, scope.explicit, scope.browse), ("hook", "atuin", True, False))

    def test_ambiguous_word_keeps_natural_language_query(self):
        with patch("cheatsheet.search.SEARCH_COLON_FREE_PREFIXES", frozenset()):
            scope = parse_query(self.conn, "find and replace in vim")
        self.assertEqual(scope.query, "find and replace in vim")
        self.assertIsNone(scope.sheet)
        self.assertEqual(scope.boost, ("find", "neovim"))

    def test_explicit_colon_still_scopes_ambiguous_word(self):
        scope = parse_query(self.conn, "find: files larger than 100MB")
        self.assertEqual((scope.query, scope.sheet, scope.explicit), ("files larger than 100MB", "find", True))

    def test_bare_ambiguous_sheet_still_browses(self):
        scope = parse_query(self.conn, "find")
        self.assertEqual((scope.query, scope.sheet, scope.browse), ("", "find", True))

    def test_colon_free_prefixes_can_be_configured(self):
        with patch("cheatsheet.search.SEARCH_COLON_FREE_PREFIXES", frozenset({"find"})):
            scope = parse_query(self.conn, "find files larger than 100MB")
        self.assertEqual((scope.query, scope.sheet, scope.explicit), ("files larger than 100MB", "find", True))

    def test_low_similarity_uses_popular_commands_in_scoped_sheet(self):
        scope = Scope("unrelated words", "atuin", True)
        with patch("cheatsheet.search.SEARCH_MIN_SIMILARITY", 0.4), \
             patch("cheatsheet.search.search", return_value=[{"sheet": "atuin", "similarity": 0.2}]), \
             patch("cheatsheet.search.popular_entries", return_value=[{"command": "atuin sync"}]):
            result = lookup(self.conn, scope)
        self.assertEqual((result.sheet, result.reason, result.rows[0]["command"]),
                         ("atuin", "low_similarity", "atuin sync"))

    def test_low_similarity_without_sheet_uses_top_result_sheet(self):
        scope = Scope("unrelated words", None, False)
        with patch("cheatsheet.search.SEARCH_MIN_SIMILARITY", 0.4), \
             patch("cheatsheet.search.search", return_value=[{"sheet": "neovim", "similarity": 0.2}]), \
             patch("cheatsheet.search.popular_entries", return_value=[{"command": ":w"}]) as popular:
            result = lookup(self.conn, scope)
        self.assertEqual((result.sheet, result.reason), ("neovim", "low_similarity"))
        self.assertEqual(popular.call_args.args[1].sheet, "neovim")

    def test_matching_query_keeps_search_results(self):
        scope = Scope("save file", "neovim", True)
        rows = [{"sheet": "neovim", "similarity": 0.4, "command": ":w"}]
        with patch("cheatsheet.search.SEARCH_MIN_SIMILARITY", 0.4), \
             patch("cheatsheet.search.search", return_value=rows), \
             patch("cheatsheet.search.popular_entries") as popular:
            result = lookup(self.conn, scope)
        self.assertEqual((result.rows, result.reason), (rows, None))
        popular.assert_not_called()


if __name__ == "__main__":
    unittest.main()
