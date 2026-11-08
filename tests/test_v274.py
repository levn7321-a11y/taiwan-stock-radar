"""Regression checks for visible high/low labels, clickable stock names and MA240 backfill."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class V274Tests(unittest.TestCase):
    def test_source_compiles(self):
        for filename in ("app.py", "pages/1_均線與法人籌碼.py",
                         "technical_charts.py", "backfill_v26.py"):
            ast.parse((ROOT / filename).read_text(encoding="utf-8"))

    def test_footer_removed(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertNotIn("評分是透明規則模型", source)

    def test_stock_name_is_link(self):
        source = (ROOT / "pages/1_均線與法人籌碼.py").read_text(encoding="utf-8")
        self.assertIn('"股票名稱": st.column_config.LinkColumn(', source)
        self.assertIn('stock_url(m, code) + "&股票=" + str(name)', source)

    def test_chart_annotates_real_high_low(self):
        source = (ROOT / "technical_charts.py").read_text(encoding="utf-8")
        self.assertIn('df["high"].idxmax()', source)
        self.assertIn('df["low"].idxmin()', source)
        self.assertIn('f"最高 {v:,.2f}"', source)
        self.assertIn('f"最低 {v:,.2f}"', source)

    def test_backfill_uses_actual_data(self):
        source = (ROOT / "backfill_v26.py").read_text(encoding="utf-8")
        workflow = (ROOT / ".github/workflows/backfill_v26.yml").read_text(encoding="utf-8")
        self.assertIn("timedelta(days=450)", source)
        self.assertIn("default: \"90\"", workflow)
        self.assertIn("github.event.inputs.days || '90'", workflow)


if __name__ == "__main__":
    unittest.main()
