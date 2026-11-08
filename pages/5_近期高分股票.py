# -*- coding: utf-8 -*-
"""近期高分股票：沿用原台股雷達突破／量能／均線規則，非 AI 勝率預測。"""
import sqlite3
from pathlib import Path
import numpy as np
import pandas as pd
import streamlit as st
from top_nav import show_top_nav

st.set_page_config(page_title="近期高分股票｜台股雷達", page_icon="🏆", layout="wide", initial_sidebar_state="collapsed")
show_top_nav()
st.title("🏆 近期高分股票")
st.caption("綜合突破、量能、均線與收盤強度，依最近交易日條件評分；分數不是預測勝率。")
DB=Path(__file__).resolve().parents[1]/"twstock.sqlite3"
if not DB.exists():
    st.error("找不到行情資料庫。")
    st.stop()

@st.cache_data(ttl=300)
def read_history(path,stamp):
    with sqlite3.connect(path) as c:
        d=pd.read_sql_query("""SELECT date,market,code,name,open,high,low,close,volume
                FROM daily WHERE market IN ('上市','上櫃')
                  AND date >= (SELECT MIN(date) FROM (SELECT DISTINCT date FROM daily ORDER BY date DESC LIMIT 110))
                ORDER BY market,code,date""",c,dtype={"code":str})
    d["date"]=pd.to_datetime(d["date"],errors="coerce")
    for k in ("open","high","low","close","volume"):
        d[k]=pd.to_numeric(d[k],errors="coerce")
    return d.dropna(subset=["date","high","low","close","volume"]).drop_duplicates(["market","code","date"]).sort_values(["market","code","date"])

def score_recent(prices,asof,lookback=5,min_turnover=30000000):
    result=[]
    prices=prices.loc[prices.date<=asof]
    for (market,code),p in prices.groupby(["market","code"],sort=False):
        p=p.sort_values("date").tail(100)
        if len(p)<61: continue
        now=p.iloc[-1]; prev=p.iloc[:-1]
        # 排除過久沒有更新的股票
        if now.date < asof-pd.Timedelta(days=7):continue
        prior_close=float(prev.close.iloc[-1])
        if prior_close<=0:continue
        turnover=float(now.close*now.volume)
        if turnover<min_turnover:continue
        avgvol=float(prev.volume.tail(20).mean())
        if avgvol<=0:continue
        ratio=float(now.volume/avgvol)
        ma20=float(prev.close.tail(20).mean()); ma60=float(prev.close.tail(60).mean())
        if ma20<=0 or ma60<=0:continue
        high20=float(prev.high.tail(20).max()); high60=float(prev.high.tail(60).max())
        breakout20=bool(now.close>high20); breakout60=bool(now.close>high60)
        change=(float(now.close)/prior_close-1)*100
        strong=(float(now.close)-float(now.low))/(float(now.high)-float(now.low)) if now.high>now.low else .5
        score=30 if breakout60 else 22 if breakout20 else 0
        score+=min(25,max(0,(ratio-1)*12))
        score+=15 if now.close>ma20>ma60 else 8 if now.close>ma20 else 0
        score+=15 if strong>=.8 and change>0 else 8 if strong>=.6 and change>0 else 0
        score+=10 if change>=3 else 5 if change>0 else 0
        score+=5 if turnover>=30000000 else 0
        if not (breakout20 or ratio>=1.8):continue
        risk=[]
        if now.close/ma20>1.15:risk.append("乖離偏高")
        if change>=9:risk.append("追價風險")
        if ratio>5:risk.append("爆量風險")
        result.append({"日期":now.date.date(),"市場":market,"代號":code,"名稱":str(now["name"]),
         "收盤價":round(float(now.close),2),"漲跌幅%":round(change,2),"量比":round(ratio,2),
         "突破20日":breakout20,"突破60日":breakout60,
         "評分":round(min(100,score),1),"風險":"、".join(risk) if risk else "—"})
    board=pd.DataFrame(result)
    return board.sort_values(["評分","量比"],ascending=False) if not board.empty else board

try:
    data=read_history(str(DB),DB.stat().st_mtime_ns)
except (sqlite3.Error,ValueError) as exc:
    st.error(f"載入行情失敗：{exc}")
    st.stop()
if data.empty:
    st.warning("目前沒有歷史行情。")
    st.stop()
most_recent=data.date.max()
c1,c2,c3=st.columns(3)
with c1:
    market=st.selectbox("市場",["上市＋上櫃","上市","上櫃"])
with c2:
    latest_days=st.selectbox("近期範圍（顯示）",[1,3,5,7],format_func=lambda n:f"近 {n} 個交易日")
with c3:
    top=st.selectbox("顯示前幾名",[15,30,50],index=1)
# 根據日期切片取得最近各交易日結果，最後只保留每檔股票最近一次訊號。
calendar=sorted(data.date.dropna().unique())
recent_days=calendar[-latest_days:]
boards=[]
for d in recent_days:
    r=score_recent(data,pd.Timestamp(d))
    if not r.empty:
        boards.append(r)
if not boards:
    st.info("所選期間沒有符合突破或量能條件的股票。")
    st.stop()
board=pd.concat(boards,ignore_index=True)
board=board.sort_values(["日期","評分"],ascending=[False,False]).drop_duplicates(["市場","代號"],keep="first")
if market!="上市＋上櫃":
    board=board[board["市場"]==market]
board=board.sort_values(["評分","日期","量比"],ascending=[False,False,False])
st.caption(f"最新行情日：{most_recent.date()}｜入選 {len(board):,} 檔｜依最近 {latest_days} 個市場交易日內的最新訊號評分")
st.dataframe(board.head(top),hide_index=True,use_container_width=True)
st.download_button("下載近期高分股票 CSV",board.to_csv(index=False).encode("utf-8-sig"),
                   file_name="近期高分股票.csv",mime="text/csv")
st.caption("此分數為透明規則模型；原始價量未做除權息還原，分數需搭配風險與法人資料研判。")
