import ast
from pathlib import Path
import unittest

import pandas as pd

PAGE = Path(__file__).resolve().parents[1] / "pages" / "1_均線與法人籌碼.py"


def load_logic():
    tree = ast.parse(PAGE.read_text(encoding="utf-8"))
    names = {"filter_security_type", "signed_lots", "trading_dates_by_market", "build_inst_ranking"}
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    namespace = {
        "pd": pd,
        "SECURITY_TYPES": ["一般股票（代碼初篩）", "ETF／其他證券（代碼初篩）", "全部商品"],
        "LOT_COLUMNS": {"外資": "foreign_net_lots", "投信": "trust_net_lots", "自營商": "dealer_net_lots", "三大法人合計": "total_net_lots"},
    }
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(PAGE), "exec"), namespace)
    return namespace


class RadarV268Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.logic = load_logic()

    def test_stock_code_filter(self):
        df = pd.DataFrame({"code": ["2330", "0050", "00937B", "3481", "00712"]})
        result = self.logic["filter_security_type"](df, "一般股票（代碼初篩）")
        self.assertEqual(result.code.tolist(), ["2330", "3481"])

    def test_other_security_filter(self):
        df = pd.DataFrame({"code": ["2330", "0050", "00937B", "3481", "00712"]})
        result = self.logic["filter_security_type"](df, "ETF／其他證券（代碼初篩）")
        self.assertEqual(result.code.tolist(), ["0050", "00937B", "00712"])

    def test_signed_lots(self):
        f = self.logic["signed_lots"]
        self.assertEqual(f(1200), "+1,200")
        self.assertEqual(f(-300), "-300")
        self.assertEqual(f(0.2), "+0.200")
        self.assertEqual(f(-0.2), "-0.200")

    def test_five_day_completeness(self):
        dates = pd.date_range("2026-10-01", periods=5)
        prices = pd.DataFrame({"date": dates, "market": ["上市"] * 5})
        rows = []
        for code, n in [("2330", 5), ("2317", 4)]:
            for day in dates[:n]:
                rows.append({"date": day, "market": "上市", "code": code, "name": code,
                             "foreign_net_lots": 10, "trust_net_lots": 0,
                             "dealer_net_lots": 0, "total_net_lots": 10})
        inst = pd.DataFrame(rows)
        build = self.logic["build_inst_ranking"]
        board = build(inst, prices, "上市", 5)
        self.assertEqual(board.code.tolist(), ["2330"])
        self.assertEqual(board.foreign_net_lots.iloc[0], 50)
        self.assertTrue(build(inst, prices, "上市", 10).empty)


if __name__ == "__main__":
    unittest.main()
