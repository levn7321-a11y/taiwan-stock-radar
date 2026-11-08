# -*- coding: utf-8 -*-
"""無需啟動 Streamlit UI 的核心計算測試。"""
import ast
import unittest
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]

def isolated(path, names):
    root=ast.parse((ROOT/path).read_text(encoding="utf-8"))
    nodes=[n for n in root.body if isinstance(n,ast.FunctionDef) and n.name in names]
    funcs={n.name for n in nodes}
    assert names <= funcs, f"找不到函數：{names-funcs}"
    scope={"pd":pd}
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(ROOT/path),"exec"),scope)
    return scope

class RankingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.func=staticmethod(isolated("pages/4_法人買賣超排行.py",{"rank_institutions"})["rank_institutions"])
    def test_five_days_and_missing_data(self):
        dates=pd.date_range("2026-11-02",periods=5,freq="D")
        calendar=pd.DataFrame({"date":dates,"market":["上市"]*5})
        records=[]
        for code,n in [("2330",5),("2317",4)]:
            for d in dates[:n]:
                records.append({"date":d,"market":"上市","code":code,"name":code,
                                "foreign_net":1000000,"trust_net":100000,"dealer_net":-50000})
        board=self.func(calendar,pd.DataFrame(records),["上市"],dates[-1],5)
        self.assertEqual(board.code.tolist(),["2330"])
        self.assertEqual(board.foreign_net.iloc[0],5000000)
        self.assertEqual(board.total_net.iloc[0],5250000)
    def test_selected_date_excludes_future(self):
        dates=pd.date_range("2026-11-02",periods=5)
        calendar=pd.DataFrame({"date":dates,"market":["上櫃"]*5})
        records=[{"date":d,"market":"上櫃","code":"5483","name":"測試",
                  "foreign_net":1000,"trust_net":0,"dealer_net":0} for d in dates]
        board=self.func(calendar,pd.DataFrame(records),["上櫃"],dates[2],3)
        self.assertEqual(board.foreign_net.iloc[0],3000)
        self.assertTrue(self.func(calendar,pd.DataFrame(records),["上櫃"],dates[2],5).empty)

class ScoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.func=staticmethod(isolated("pages/5_近期高分股票.py",{"score_recent"})["score_recent"])
    def test_score_breakout(self):
        dates=pd.date_range("2026-07-01",periods=62,freq="B")
        rows=[]
        for i,d in enumerate(dates):
            c=100+i*.15
            if i==61: c=125
            rows.append({"date":d,"market":"上市","code":"2330","name":"測試",
                         "high":c+1,"low":c-1,"close":c,"volume":1000000 if i<61 else 3000000})
        result=self.func(pd.DataFrame(rows),dates[-1])
        self.assertFalse(result.empty)
        self.assertTrue(result.iloc[0]["突破20日"])
        self.assertGreater(result.iloc[0]["評分"],50)
    def test_insufficient_history(self):
        dates=pd.date_range("2026-10-01",periods=20,freq="B")
        df=pd.DataFrame({"date":dates,"market":"上市","code":"2330","name":"測試",
                         "close":100.,"high":101.,"low":99.,"volume":1000000})
        self.assertTrue(self.func(df,dates[-1]).empty)

if __name__=="__main__":
    unittest.main()
