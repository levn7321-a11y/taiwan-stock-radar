"""V2.7.3 light default, watchlist editing, and anonymous stock popularity tests."""
import ast
import pathlib
import tempfile
import unittest
from unittest.mock import patch

import search_popularity as pop

ROOT = pathlib.Path(__file__).resolve().parents[1]


class DashboardTests(unittest.TestCase):
    def test_theme_defaults_to_light_and_persists_on_links(self):
        nav = (ROOT / "top_nav.py").read_text(encoding="utf-8")
        dashboard = (ROOT / "pages/1_均線與法人籌碼.py").read_text(encoding="utf-8")
        self.assertIn('st.query_params.get("theme", "light")', nav)
        self.assertIn('st.query_params["theme"]', nav)
        self.assertIn("stButtonGroup", nav)
        self.assertIn('"theme": "light" if st.session_state.get("radar_light_theme", True) else "dark"', dashboard)

    def test_stock_table_has_watch_checkbox_without_date_market(self):
        src = (ROOT / "pages/1_均線與法人籌碼.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "render_ranking_table")
        segment = ast.get_source_segment(src, fn)
        self.assertIn('st.data_editor(', segment)
        self.assertIn('"加入自選"', segment)
        self.assertIn('"code", "name"', segment)
        self.assertIn('st.query_params["market"]', segment)
        self.assertNotIn('"date", "market", "code"', segment)

    def test_real_search_ranking_no_fabricated_values(self):
        with tempfile.TemporaryDirectory() as path:
            db = pathlib.Path(path) / "searches.sqlite3"
            valid = {"上市:2330": "2330 台積電", "上市:2317": "2317 鴻海"}
            with patch.object(pop, "DB", db):
                self.assertEqual(pop.top_stock_searches(valid), [])
                self.assertFalse(pop.record_stock_search("上市", "9999", valid))
                for _ in range(3):
                    self.assertTrue(pop.record_stock_search("上市", "2330", valid))
                self.assertTrue(pop.record_stock_search("上市", "2317", valid))
                results = pop.top_stock_searches(valid)
            self.assertEqual(results[0], ("上市", "2330", "2330 台積電", 3))
            self.assertEqual(results[1][-1], 1)

    def test_scripts_compile(self):
        for path in [ROOT/"top_nav.py", ROOT/"pages/1_均線與法人籌碼.py",
                     ROOT/"search_popularity.py"]:
            ast.parse(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
