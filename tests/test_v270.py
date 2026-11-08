"""V2.7.0 上方浮動選單與黑白主題靜態測試。"""
import ast
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
NAV = ROOT / "top_nav.py"


class NavigationThemeTests(unittest.TestCase):
    def setUp(self):
        self.tree = ast.parse(NAV.read_text(encoding="utf-8"))

    def test_six_menus_have_valid_internal_pages(self):
        assignment = next(
            node for node in self.tree.body
            if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "MENUS" for t in node.targets
            )
        )
        menus = ast.literal_eval(assignment.value)
        self.assertEqual(len(menus), 6)
        for title, links in menus:
            self.assertTrue(title)
            self.assertGreaterEqual(len(links), 2)
            for _, path in links:
                self.assertTrue((ROOT / path).is_file(), path)

    def test_toggle_and_popovers_are_present(self):
        text = NAV.read_text(encoding="utf-8")
        self.assertIn("st.popover(", text)
        self.assertIn('st.toggle("☀️ 白底模式"', text)
        self.assertIn("position: sticky", text)
        self.assertIn("radar_light_theme", text)
        self.assertIn("show_top_nav", text)

    def test_builtin_sidebar_navigation_is_hidden(self):
        config = (ROOT / ".streamlit/config.toml").read_text(encoding="utf-8")
        self.assertIn("showSidebarNavigation = false", config)

    def test_every_main_page_uses_shared_nav(self):
        for path in ["app.py", "pages/1_均線與法人籌碼.py",
                     "pages/2_個股技術分析.py", "pages/3_自選個股.py",
                     "pages/4_法人買賣超排行.py", "pages/5_近期高分股票.py"]:
            text = (ROOT / path).read_text(encoding="utf-8")
            self.assertIn("show_top_nav()", text, path)


if __name__ == "__main__":
    unittest.main()
