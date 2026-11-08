# -*- coding: utf-8 -*-
"""台股 AI 突破雷達：自選個股專屬頁面。清單存在網址參數中，不使用共用 SQLite 寫入。"""
import re
import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(page_title="自選個股｜台股 AI 突破雷達", page_icon="⭐", layout="wide")
DB = Path(__file__).resolve().parents[1] / "twstock.sqlite3"
MAX_WATCH = 50
ID_PATTERN = re.compile(r"^(上市|上櫃):([A-Za-z0-9]{4,6})$")


def parse_watch(raw):
    """限制數量、去重、驗證鍵值，避免不可信的網址參數造成過量查詢。"""
    if isinstance(raw, list):
        raw = raw[0] if raw else ""
    seen, result = set(), []
    for value in str(raw or "").split(","):
        value = value.strip()
        if ID_PATTERN.fullmatch(value) and value not in seen:
            seen.add(value)
            result.append(value)
            if len(result) >= MAX_WATCH:
                break
    return result


def save_watch(items):
    """網址可加入書籤，重新整理仍能保留個人的自選清單。"""
    value = ",".join(items)
    if value:
        st.query_params["watch"] = value
    elif "watch" in st.query_params:
        del st.query_params["watch"]


@st.cache_data(ttl=300)
def load_stocks(db_path, stamp):
    with sqlite3.connect(db_path) as conn:
        return pd.read_sql_query(
            """SELECT market, code, MAX(name) AS name
               FROM daily
               WHERE market IN ('上市','上櫃')
               GROUP BY market, code
               ORDER BY market, code""", conn
        )


@st.cache_data(ttl=300)
def load_recent(db_path, stamp, keys):
    """一次取自選股票近 260 日資料，不向官方 API 發出額外請求。"""
    if not keys:
        return pd.DataFrame()
    pairs = [key.split(":", 1) for key in keys]
    conditions = " OR ".join("(market = ? AND code = ?)" for _ in pairs)
    params = [part for pair in pairs for part in pair]
    sql = f"""
        SELECT date, market, code, name, close, volume
        FROM (
            SELECT date, market, code, name, close, volume,
                   ROW_NUMBER() OVER (PARTITION BY market, code ORDER BY date DESC) AS rn
            FROM daily WHERE {conditions}
        ) WHERE rn <= 260 ORDER BY market, code, date
    """
    with sqlite3.connect(db_path) as conn:
        return pd.read_sql_query(sql, conn, params=params)


@st.cache_data(ttl=300)
def load_inst(db_path, stamp, keys):
    if not keys:
        return pd.DataFrame()
    pairs = [key.split(":", 1) for key in keys]
    conditions = " OR ".join("(market = ? AND code = ?)" for _ in pairs)
    params = [part for pair in pairs for part in pair]
    with sqlite3.connect(db_path) as conn:
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='institutional'"
        ).fetchone()
        if not exists:
            return pd.DataFrame()
        return pd.read_sql_query(
            f"""SELECT date,market,code,foreign_net,trust_net,dealer_net
                 FROM institutional WHERE {conditions}
                 ORDER BY market,code,date DESC""",
            conn, params=params
        )


def summary_rows(history, inst, keys):
    """只列出使用者選擇的股票，缺法人紀錄顯示缺資料，不以零替代。"""
    result = []
    for key in keys:
        market, code = key.split(":", 1)
        p = history[(history["market"] == market) & (history["code"] == code)].sort_values("date")
        if p.empty:
            result.append({"市場": market, "代號": code, "名稱": "尚無行情",
                           "行情日期": "—", "收盤價": None, "漲跌幅%": None, "MA20": None,
                           "外資(張)": None, "投信(張)": None, "自營商(張)": None, "三大法人(張)": None,
                           "法人日期": "—"})
            continue
        current = p.iloc[-1]
        previous = p.iloc[-2] if len(p) > 1 else None
        close = float(current["close"])
        pct = (close / float(previous["close"]) - 1) * 100 if previous is not None and float(previous["close"]) > 0 else None
        ma20 = float(p["close"].tail(20).mean()) if len(p) >= 20 else None
        row = {"市場": market, "代號": code, "名稱": str(current["name"]),
               "行情日期": pd.Timestamp(current["date"]).strftime("%Y-%m-%d"),
               "收盤價": close, "漲跌幅%": pct, "MA20": ma20, "法人日期": "—",
               "外資(張)": None, "投信(張)": None, "自營商(張)": None, "三大法人(張)": None}
        if not inst.empty:
            d = inst[(inst["market"] == market) & (inst["code"] == code)].sort_values("date")
            if not d.empty:
                last = d.iloc[-1]
                values = pd.to_numeric(last[["foreign_net","trust_net","dealer_net"]], errors="coerce")
                if values.notna().all():
                    row["外資(張)"], row["投信(張)"], row["自營商(張)"] = (values / 1000).tolist()
                    row["三大法人(張)"] = float(values.sum() / 1000)
                    row["法人日期"] = pd.Timestamp(last["date"]).strftime("%Y-%m-%d")
        result.append(row)
    return pd.DataFrame(result)


st.title("⭐ 自選個股")
st.caption("此頁只顯示你選擇的個股，不混入全市場排行榜。數據為資料庫內最新歷史資料，非盤中即時行情。")

if not DB.exists():
    st.error("找不到 twstock.sqlite3，目前無法載入自選個股。")
    st.stop()

stamp = DB.stat().st_mtime_ns
try:
    stocks = load_stocks(str(DB), stamp)
except (sqlite3.Error, ValueError) as exc:
    st.error(f"載入股票清單失敗：{exc}")
    st.stop()
if stocks.empty:
    st.warning("資料庫尚無股票行情。")
    st.stop()
stocks["code"] = stocks["code"].astype(str).str.strip()
stocks["id"] = stocks["market"] + ":" + stocks["code"]
stocks["label"] = stocks["code"] + " " + stocks["name"].astype(str) + "（" + stocks["market"] + "）"
labels = dict(zip(stocks["id"], stocks["label"]))

selected = [key for key in parse_watch(st.query_params.get("watch", "")) if key in labels]

with st.expander("➕ 新增或移除自選個股", expanded=not bool(selected)):
    choose = st.selectbox("搜尋並選擇股票", options=stocks["id"].tolist(),
                          format_func=lambda item: labels.get(item, item),
                          index=None, placeholder="輸入股票代號或名稱搜尋", key="add_watch")
    if st.button("加入自選", type="primary", disabled=not choose or choose in selected):
        if len(selected) >= MAX_WATCH:
            st.warning(f"自選清單最多 {MAX_WATCH} 檔。")
        else:
            save_watch(selected + [choose])
            st.rerun()
    if selected:
        remove = st.selectbox("移除自選", selected, format_func=lambda item: labels.get(item, item),
                              index=None, placeholder="選擇要移除的股票", key="remove_watch")
        if st.button("移除選取股票", disabled=not remove):
            save_watch([item for item in selected if item != remove])
            st.rerun()

if not selected:
    st.info("目前還沒有自選個股。請展開上方區塊，搜尋股票代號或名稱，點選「加入自選」。")
    st.stop()

st.caption(f"目前自選 {len(selected)} 檔（最多 {MAX_WATCH} 檔）。可以把此頁網址加入書籤，以便下次開啟相同清單。")
try:
    prices = load_recent(str(DB), stamp, tuple(selected))
    inst = load_inst(str(DB), stamp, tuple(selected))
except sqlite3.Error as exc:
    st.error(f"讀取自選資料失敗：{exc}")
    st.stop()

if not prices.empty:
    prices["date"] = pd.to_datetime(prices["date"], errors="coerce")
    prices["close"] = pd.to_numeric(prices["close"], errors="coerce")
    prices["volume"] = pd.to_numeric(prices["volume"], errors="coerce")
    prices = prices.dropna(subset=["date", "close"]).drop_duplicates(["date","market","code"], keep="last")
if not inst.empty:
    inst["date"] = pd.to_datetime(inst["date"], errors="coerce")

board = summary_rows(prices, inst, selected)
if board.empty:
    st.info("自選股票目前沒有可用行情。")
    st.stop()

st.subheader("📋 自選個股專屬看板")
st.dataframe(board, use_container_width=True, hide_index=True,
             column_config={
                 "收盤價": st.column_config.NumberColumn("收盤價", format="%.2f"),
                 "漲跌幅%": st.column_config.NumberColumn("漲跌幅%", format="%+.2f"),
                 "MA20": st.column_config.NumberColumn("MA20", format="%.2f"),
                 "外資(張)": st.column_config.NumberColumn("外資(張)", format="%.2f"),
                 "投信(張)": st.column_config.NumberColumn("投信(張)", format="%.2f"),
                 "自營商(張)": st.column_config.NumberColumn("自營商(張)", format="%.2f"),
                 "三大法人(張)": st.column_config.NumberColumn("三大法人(張)", format="%.2f")
             })
st.caption("法人數據原始單位為股，除以 1,000 換算為張；沒有資料時保留空白。請留意行情日期與法人日期可能不同。")

st.subheader("📈 自選股票走勢與法人")
chosen = st.selectbox("查看自選股票", selected, format_func=lambda item: labels.get(item, item), key="watch_detail")
market, code = chosen.split(":", 1)
p = prices[(prices["market"] == market) & (prices["code"] == code)].sort_values("date").copy()
if len(p):
    p["MA5"] = p["close"].rolling(5, min_periods=5).mean()
    p["MA20"] = p["close"].rolling(20, min_periods=20).mean()
    st.line_chart(p.set_index("date")[["close", "MA5", "MA20"]], use_container_width=True)
    st.caption("收盤價與均線均為歷史值；MA20 未滿 20 個交易日不顯示。")
else:
    st.warning("這檔股票沒有歷史行情。")

if not inst.empty:
    d = inst[(inst["market"] == market) & (inst["code"] == code)].sort_values("date").tail(20).copy()
    if not d.empty:
        for col, name in [("foreign_net","外資"), ("trust_net","投信"), ("dealer_net","自營商")]:
            d[name] = pd.to_numeric(d[col], errors="coerce") / 1000
        d["三大法人合計"] = d[["外資","投信","自營商"]].sum(axis=1, min_count=3)
        st.bar_chart(d.set_index("date")[["外資","投信","自營商"]], use_container_width=True)
        st.dataframe(d[["date","外資","投信","自營商","三大法人合計"]].iloc[::-1],
                     use_container_width=True, hide_index=True)
    else:
        st.info("這檔股票沒有法人紀錄。")
else:
    st.info("資料庫目前沒有可顯示的法人紀錄。")
st.caption("自選清單僅儲存在本頁網址中；不使用共用伺服器資料庫儲存個人選股，請保留含 watch 參數的網址。")
