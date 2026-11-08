# -*- coding: utf-8 -*-
"""台股法人買賣超排行：可指定結束日期與最近 1～30 個交易日。"""
import sqlite3
from pathlib import Path
import pandas as pd
import streamlit as st
from top_nav import show_top_nav

st.set_page_config(page_title="法人買賣超排行｜台股雷達", page_icon="🏦", layout="wide", initial_sidebar_state="collapsed")
show_top_nav()
st.title("🏦 法人／外資買賣超前 15 名")
st.caption("外資、投信、自營商、三大法人｜每日或累計 1～30 個交易日｜原始股數 ÷ 1,000 換算為張。非即時資料。")
DB = Path(__file__).resolve().parents[1] / "twstock.sqlite3"
if not DB.exists():
    st.error("找不到行情資料庫。")
    st.stop()

@st.cache_data(ttl=300)
def load_data(path, stamp):
    with sqlite3.connect(path) as c:
        dates = pd.read_sql_query("SELECT DISTINCT market,date FROM daily WHERE market IN ('上市','上櫃')", c)
        inst = pd.read_sql_query("""SELECT date,market,code,name,foreign_net,trust_net,dealer_net
           FROM institutional WHERE market IN ('上市','上櫃') AND date >= (SELECT MIN(date) FROM (SELECT DISTINCT date FROM daily ORDER BY date DESC LIMIT 35))""", c, dtype={"code":str})
    for d in (dates, inst):
        d["date"] = pd.to_datetime(d["date"], errors="coerce").dt.normalize()
    inst["code"] = inst["code"].astype(str).str.strip()
    for col in ("foreign_net","trust_net","dealer_net"):
        inst[col] = pd.to_numeric(inst[col], errors="coerce")
    inst = inst.dropna(subset=["date","foreign_net","trust_net","dealer_net"]).drop_duplicates(["market","code","date"],keep="last")
    return dates.dropna(subset=["date"]), inst

def rank_institutions(dates, inst, markets, end, n):
    outputs=[]
    for market in markets:
        # 僅使用截至指定日期的市場日曆，不以某檔股票的缺資料日代替交易日。
        calendar = sorted(dates.loc[(dates.market == market)&(dates.date <= end),"date"].drop_duplicates().tolist())
        selected = calendar[-n:]
        if len(selected) != n:
            continue
        rows = inst[(inst.market == market)&(inst.date.isin(selected))].copy()
        if rows.empty:
            continue
        rows["total_net"] = rows[["foreign_net","trust_net","dealer_net"]].sum(axis=1)
        sums = rows.groupby(["market","code"],as_index=False).agg(
            name=("name","last"),days=("date","nunique"),
            foreign_net=("foreign_net","sum"),trust_net=("trust_net","sum"),
            dealer_net=("dealer_net","sum"),total_net=("total_net","sum"))
        # 任一天無法人紀錄的股票均不參與排名，避免將缺漏當成 0。
        outputs.append(sums.loc[sums.days == n].copy())
    return pd.concat(outputs,ignore_index=True) if outputs else pd.DataFrame()

try:
    calendar, inst = load_data(str(DB), DB.stat().st_mtime_ns)
except (sqlite3.Error, ValueError) as exc:
    st.error(f"讀取資料失敗：{exc}")
    st.stop()
if inst.empty:
    st.warning("目前沒有完整三大法人資料。")
    st.stop()

c1,c2,c3,c4 = st.columns([1.2,1.2,1.4,1.2])
with c1:
    market_choice = st.selectbox("市場",["上市＋上櫃","上市","上櫃"])
with c2:
    who = st.selectbox("法人類別",["外資","投信","自營商","三大法人合計"])
with c3:
    period = st.selectbox("累計期間",["今日（最新資料日）","近 3 日","近 5 日","近 7 日","自行選擇 1～30 日"])
with c4:
    end_date = st.selectbox("截至資料日期",sorted(inst.date.dt.date.unique(),reverse=True))
if period.startswith("今日"):
    n=1
elif period=="近 3 日":
    n=3
elif period=="近 5 日":
    n=5
elif period=="近 7 日":
    n=7
else:
    n=st.slider("自訂累計交易日",1,30,10)

markets=["上市","上櫃"] if market_choice=="上市＋上櫃" else [market_choice]
board=rank_institutions(calendar,inst,markets,pd.Timestamp(end_date),n)
if board.empty:
    st.warning("選定日期及期間沒有足夠完整的法人資料；請改短期間或更換日期。")
    st.stop()
field={"外資":"foreign_net","投信":"trust_net","自營商":"dealer_net","三大法人合計":"total_net"}[who]
board["買賣超（張）"]=board[field]/1000
st.caption(f"截至 {end_date}｜累計 {n} 個交易日｜有效證券 {len(board):,} 檔｜資料不完整者已排除")
left,right=st.columns(2)
for panel,positive in [(left,True),(right,False)]:
    with panel:
        st.subheader(f"{who}｜{'買超' if positive else '賣超'}前 15 名")
        selected=board[board[field]>0].nlargest(15,field) if positive else board[board[field]<0].nsmallest(15,field)
        display=selected[["market","code","name","買賣超（張）"]].rename(columns={"market":"市場","code":"代號","name":"名稱"}).copy()
        st.dataframe(display,hide_index=True,use_container_width=True,
            column_config={"買賣超（張）":st.column_config.NumberColumn("買賣超（張）",format="%.0f")})
st.download_button("下載完整法人排行 CSV",board.to_csv(index=False).encode("utf-8-sig"),
                   file_name=f"法人買賣超_{end_date}_{n}日.csv",mime="text/csv")
st.caption("指定日期若遇市場缺漏日，該期間的股票將被排除；本頁不把缺少的資料視為零。一般股票每張 1,000 股，其他證券請注意交易單位差異。")
