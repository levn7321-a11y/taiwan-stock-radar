import sqlite3
from pathlib import Path
import pandas as pd
import streamlit as st
import altair as alt

st.set_page_config(page_title="台股 AI 突破雷達 V2.3", page_icon="📈", layout="wide", initial_sidebar_state="collapsed")
DB = Path(__file__).resolve().parents[1] / "twstock.sqlite3"
MA = (5, 10, 20, 60, 240)

st.markdown("""
<style>
.block-container {max-width:100%;padding:1rem 1.5rem 2rem}
header[data-testid="stHeader"] {background:transparent}
h1 {font-size:1.9rem!important;letter-spacing:.02em}
div[data-testid="stMetric"] {border:1px solid #394554;border-radius:7px;padding:12px;background:#17212d}
div[data-testid="stMetric"] label {color:#a7b6c9!important}
div[data-testid="stMetricValue"] {color:#f2f6fc}
div[data-testid="stDataFrame"] {border:1px solid #354354;border-radius:6px}
.stTabs [data-baseweb="tab-list"] {gap:5px;border-bottom:1px solid #405064}
.stTabs [data-baseweb="tab"] {padding:10px 20px;border-radius:5px 5px 0 0}
.stTabs [aria-selected="true"] {background:#213448}
section[data-testid="stSidebar"] {background:#111c28}
.market-header {background:linear-gradient(90deg,#172a3e,#203a50);padding:12px 16px;border-left:4px solid #2aa6c9;border-radius:4px;margin-bottom:12px}
.market-header b {font-size:1.1rem;color:#eaf4ff}
.market-header small {color:#9eb4c9}
</style>
""", unsafe_allow_html=True)

@st.cache_data(ttl=300)
def prices_from_db(path, stamp):
    with sqlite3.connect(path) as conn:
        return pd.read_sql_query(
            "SELECT date,market,code,name,close,volume FROM daily ORDER BY market,code,date", conn
        )

@st.cache_data(ttl=300)
def institutions_from_db(path, stamp):
    with sqlite3.connect(path) as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "institutional" not in tables:
            return None
        return pd.read_sql_query("SELECT * FROM institutional", conn)

def normalize_inst(df):
    required = {"date", "market", "code", "name", "foreign_net", "trust_net"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError("缺少欄位：" + "、".join(sorted(missing)))
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["code"] = df["code"].astype(str).str.replace(r"\.0$", "", regex=True).str.strip()
    for c in ("foreign_net", "trust_net"):
        df[c] = pd.to_numeric(df[c].astype(str).str.replace(",", "", regex=False), errors="coerce")
    return df.dropna(subset=["date"])

def market_filter(df, selected):
    return df if selected == "上市＋上櫃" else df[df["market"] == selected]

def style_change(v):
    if pd.isna(v): return ""
    return "color: #e74b58; font-weight: bold" if v > 0 else ("color: #15a36c; font-weight: bold" if v < 0 else "")

st.title("📈 台股 AI 突破雷達 V2.3｜專業看盤")
st.caption("台股行情看板｜紅漲綠跌｜均線趨勢｜法人籌碼｜非即時報價・非投資建議")
tab_radar, tab_ma, tab_inst = st.tabs(["📊 行情總覽與排行榜", "📈 個股技術分析", "🏦 法人籌碼排行榜"])

prices = pd.DataFrame()
if DB.exists():
    try:
        prices = prices_from_db(str(DB), DB.stat().st_mtime_ns)
        prices["date"] = pd.to_datetime(prices["date"], errors="coerce")
        prices["code"] = prices["code"].astype(str).str.strip()
        for c in ("close", "volume"):
            prices[c] = pd.to_numeric(prices[c], errors="coerce")
        prices = (prices.dropna(subset=["date", "close"])
                  .drop_duplicates(["market", "code", "date"], keep="last")
                  .sort_values(["market", "code", "date"]))
    except Exception as e:
        st.error(f"行情資料讀取失敗：{e}")
else:
    st.warning("找不到 twstock.sqlite3，請先執行歷史資料回補。")

@st.cache_data(ttl=300)
def build_ranking(prices):
    if prices.empty:
        return pd.DataFrame()
    p = prices.copy()
    group = p.groupby(["market", "code"], sort=False)
    p["前收"] = group["close"].shift(1)
    p["漲跌幅%"] = (p["close"] / p["前收"] - 1) * 100
    for n in MA:
        p[f"MA{n}"] = group["close"].transform(lambda s: s.rolling(n, min_periods=n).mean())
    p["均量20"] = group["volume"].transform(lambda s: s.rolling(20, min_periods=20).mean())
    p["量比"] = p["volume"] / p["均量20"].replace(0, float("nan"))
    latest = p.groupby(["market", "code"], sort=False).tail(1).copy()
    latest["多頭均線數"] = sum((latest["close"] > latest[f"MA{n}"]).fillna(False).astype(int) for n in MA)
    latest["均線訊號"] = latest.apply(
        lambda r: "站上月季線" if pd.notna(r["MA60"]) and r["close"] > r["MA20"] and r["close"] > r["MA60"]
        else ("站上月線" if pd.notna(r["MA20"]) and r["close"] > r["MA20"] else "觀察"), axis=1)
    return latest

ranking = build_ranking(prices)

with tab_radar:
    st.markdown('<div class="market-header"><b>市場行情總覽</b><br><small>全市場個股行情與技術指標・依資料庫最近交易日計算</small></div>', unsafe_allow_html=True)
    if ranking.empty:
        st.info("目前沒有可用的行情資料。")
    else:
        c1, c2, c3, c4 = st.columns([1.2, 1.2, 1.2, 1.5])
        with c1: market = st.selectbox("市場", ["上市＋上櫃", "上市", "上櫃"], key="rank_market")
        with c2: sort = st.selectbox("排行榜", ["漲幅排行", "跌幅排行", "成交量排行", "量比排行", "多頭排列排行"], key="rank_sort")
        with c3: trend = st.selectbox("均線條件", ["全部", "站上月線", "站上月季線"], key="rank_trend")
        with c4: keyword = st.text_input("搜尋代號／名稱", placeholder="例如 2330 或 台積電")
        d = market_filter(ranking, market).copy()
        if trend == "站上月線":
            d = d[d["MA20"].notna() & (d["close"] > d["MA20"])]
        elif trend == "站上月季線":
            d = d[d["MA60"].notna() & (d["close"] > d["MA20"]) & (d["close"] > d["MA60"])]
        if keyword:
            d = d[d["code"].str.contains(keyword, case=False, regex=False) |
                  d["name"].astype(str).str.contains(keyword, case=False, regex=False)]
        sort_key, ascending = {
            "漲幅排行": ("漲跌幅%", False), "跌幅排行": ("漲跌幅%", True),
            "成交量排行": ("volume", False), "量比排行": ("量比", False),
            "多頭排列排行": ("多頭均線數", False)
        }[sort]
        d = d.sort_values(sort_key, ascending=ascending, na_position="last")
        latest_date = ranking["date"].max().date()
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("篩選結果", f"{len(d):,} 檔")
        m2.metric("上漲家數", f"{int((d['漲跌幅%'] > 0).sum()):,} 檔")
        m3.metric("下跌家數", f"{int((d['漲跌幅%'] < 0).sum()):,} 檔")
        m4.metric("站上月線", f"{int((d['close'] > d['MA20']).sum()):,} 檔")
        m5.metric("行情最新日期", str(latest_date))
        st.caption("每檔顯示自己的最新交易日；各市場更新時間可能不同。量比＝當日成交量／20 日平均成交量。")
        view = d.rename(columns={"date":"日期","market":"市場","code":"代號","name":"名稱",
                                 "close":"收盤價","volume":"成交量"})
        cols = ["日期","市場","代號","名稱","收盤價","漲跌幅%","成交量","量比",
                "MA5","MA10","MA20","MA60","MA240","多頭均線數","均線訊號"]
        view = view[cols]
        view["日期"] = pd.to_datetime(view["日期"]).dt.strftime("%Y-%m-%d")
        st.dataframe(view.style.map(style_change, subset=["漲跌幅%"]).format(
            {"收盤價":"{:.2f}","漲跌幅%":"{:+.2f}","成交量":"{:,.0f}","量比":"{:.2f}",
             **{f"MA{n}":"{:.2f}" for n in MA}}, na_rep="—"),
            use_container_width=True, hide_index=True, height=680)
        st.download_button("⬇️ 下載目前排行榜 CSV",
                           data=view.to_csv(index=False).encode("utf-8-sig"),
                           file_name="taiwan_stock_ma_ranking.csv", mime="text/csv")
        st.caption("行情排行為研究用途，並非原 V2.0 突破評分榜。240 日年線若資料不足將顯示空白。")

with tab_ma:
    if ranking.empty:
        st.info("目前沒有可用的行情資料。")
    else:
        c1, c2 = st.columns([1, 3])
        with c1: market = st.selectbox("市場", ["上市＋上櫃", "上市", "上櫃"], key="detail_market")
        opts = market_filter(ranking, market).sort_values(["market","code"])
        opts = opts.assign(label=opts["code"]+" "+opts["name"].astype(str)+"（"+opts["market"]+"）")
        with c2: choice = st.selectbox("股票", opts["label"].tolist())
        selected = opts[opts["label"] == choice].iloc[0]
        s = prices[(prices["market"] == selected["market"]) & (prices["code"] == selected["code"])].copy()
        s = s.sort_values("date").set_index("date")
        for n in MA: s[f"MA{n}"] = s["close"].rolling(n, min_periods=n).mean()
        st.caption(f"資料最新日期：{s.index.max().date()}｜累積 {len(s)} 個交易日")
        st.markdown('<div class="market-header"><b>個股技術走勢</b><br><small>收盤價・均線・成交量</small></div>', unsafe_allow_html=True)
        # 使用既有 close/volume 資料；資料庫未必有 OHLC，因此不虛構 K 棒。
        chart_data = s[["close"] + [f"MA{n}" for n in MA]].tail(180).reset_index()
        chart_long = chart_data.melt("date", var_name="指標", value_name="價格").dropna()
        chart = alt.Chart(chart_long).mark_line(strokeWidth=2).encode(
            x=alt.X("date:T", title="交易日期"),
            y=alt.Y("價格:Q", scale=alt.Scale(zero=False), title="價格"),
            color=alt.Color("指標:N", scale=alt.Scale(
                domain=["close", "MA5", "MA10", "MA20", "MA60", "MA240"],
                range=["#ffffff", "#f6bf54", "#58c6f5", "#d77df1", "#43c59e", "#ef6576"])),
            tooltip=[alt.Tooltip("date:T", title="日期"), "指標:N", alt.Tooltip("價格:Q", format=".2f")]
        ).properties(height=390)
        st.altair_chart(chart, use_container_width=True)
        if "volume" in s.columns:
            volume_data = s[["volume"]].tail(180).reset_index()
            bars = alt.Chart(volume_data).mark_bar(color="#4c9ec5").encode(
                x=alt.X("date:T", title="交易日期"),
                y=alt.Y("volume:Q", title="成交量"),
                tooltip=["date:T", alt.Tooltip("volume:Q", format=",")]
            ).properties(height=115)
            st.altair_chart(bars, use_container_width=True)
        st.caption("目前資料庫僅提供收盤價與成交量，故以均線走勢圖呈現；真正的日 K 線需另外取得開高低收資料。")
        st.dataframe(s[["close"] + [f"MA{n}" for n in MA]].tail(20).iloc[::-1],
                     use_container_width=True)
        if len(s) < 240: st.warning(f"僅有 {len(s)} 個交易日，240 日年線尚無法完整計算。")

with tab_inst:
    st.markdown('<div class="market-header"><b>法人籌碼排行</b><br><small>外資・投信｜每日買超與賣超前 15 名</small></div>', unsafe_allow_html=True)
    st.caption("優先讀取 institutional 資料表；沒有資料時可匯入 CSV。買賣超單位依來源，匯入前請確認一致。")
    uploaded = st.file_uploader("匯入法人 CSV（選用）", type=["csv"], key="v22_inst")
    inst = None
    try:
        if uploaded is not None:
            inst = normalize_inst(pd.read_csv(uploaded, dtype={"code":str}))
        elif DB.exists():
            raw = institutions_from_db(str(DB), DB.stat().st_mtime_ns)
            if raw is not None: inst = normalize_inst(raw)
    except Exception as e:
        st.error(f"法人資料讀取失敗：{e}")
    if inst is None or inst.empty:
        st.info("目前沒有法人資料。每日自動抓取尚未接入；請先匯入包含 date、market、code、name、foreign_net、trust_net 的 CSV。")
    else:
        a, b, c = st.columns(3)
        with a: date = st.selectbox("資料日期", sorted(inst["date"].dt.date.unique(), reverse=True))
        with b: market = st.selectbox("市場", ["上市＋上櫃", "上市", "上櫃"], key="inst_market")
        with c: who = st.selectbox("法人", ["外資", "投信"])
        d = market_filter(inst[inst["date"].dt.date == date], market).copy()
        col = "foreign_net" if who == "外資" else "trust_net"
        left, right = st.columns(2)
        for panel, title, positive in ((left, "買超前 15", True), (right, "賣超前 15", False)):
            with panel:
                st.markdown(f"#### {who}｜{title}")
                t = d[d[col] > 0].nlargest(15, col) if positive else d[d[col] < 0].nsmallest(15, col)
                t = t[["market","code","name",col]].rename(
                    columns={"market":"市場","code":"代號","name":"名稱",col:"買賣超"})
                st.dataframe(t.style.map(style_change, subset=["買賣超"]).format({"買賣超":"{:+,.0f}"}),
                             use_container_width=True, hide_index=True, height=580)
        st.download_button("⬇️ 下載當日法人資料 CSV",
                           data=d.to_csv(index=False).encode("utf-8-sig"),
                           file_name=f"institutional_{date}.csv", mime="text/csv")
