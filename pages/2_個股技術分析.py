
import sqlite3
from pathlib import Path
from datetime import date
import pandas as pd
import requests
import streamlit as st
from top_nav import show_top_nav

st.set_page_config(
    page_title="個股技術分析",
    page_icon="📈",
    layout="wide"
)

show_top_nav()

DB = Path(__file__).resolve().parents[1] / "twstock.sqlite3"

st.title("📈 個股技術分析 V2.4")
st.caption("一年歷史行情｜日K線｜五條均線｜成交量")

def number(value):
    try:
        return float(str(value).replace(",", ""))
    except (ValueError, TypeError):
        return None

def roc_date(value):
    parts = str(value).split("/")
    if len(parts) != 3:
        raise ValueError("日期格式錯誤")
    return f"{int(parts[0])+1911:04d}-{int(parts[1]):02d}-{int(parts[2]):02d}"

@st.cache_data(ttl=3600)
def load_stocks():
    with sqlite3.connect(DB) as conn:
        return pd.read_sql_query(
            "SELECT DISTINCT market, code, name FROM daily",
            conn
        )

@st.cache_data(ttl=3600)
def load_local(market, code):
    with sqlite3.connect(DB) as conn:
        return pd.read_sql_query(
            """
            SELECT date, open, high, low, close, volume
            FROM daily
            WHERE market=? AND code=?
            ORDER BY date
            """,
            conn,
            params=(market, code)
        )

def fetch_twse(code, months=15):
    """上市個股：逐月取得官方歷史行情"""
    frames = []
    today = pd.Timestamp.today().normalize()

    for month in pd.period_range(
        today - pd.DateOffset(months=months),
        today,
        freq="M"
    ):
        url = "https://www.twse.com.tw/exchangeReport/STOCK_DAY"
        params = {
            "response": "json",
            "date": month.strftime("%Y%m") + "01",
            "stockNo": code
        }
        try:
            response = requests.get(
                url, params=params, timeout=25,
                headers={"User-Agent": "Mozilla/5.0"}
            )
            response.raise_for_status()
            data = response.json()
            rows = data.get("data", [])

            for r in rows:
                if len(r) < 7:
                    continue
                frames.append({
                    "date": roc_date(r[0]),
                    "open": number(r[3]),
                    "high": number(r[4]),
                    "low": number(r[5]),
                    "close": number(r[6]),
                    "volume": number(r[1])
                })
        except Exception:
            continue

    return pd.DataFrame(frames)

def fetch_tpex(code, months=15):
    """上櫃個股：櫃買中心每月歷史行情"""
    frames = []
    today = pd.Timestamp.today().normalize()

    for month in pd.period_range(
        today - pd.DateOffset(months=months),
        today,
        freq="M"
    ):
        url = (
            "https://www.tpex.org.tw/www/zh-tw/"
            "afterTrading/tradingStock"
        )
        params = {
            "code": code,
            "date": month.strftime("%Y/%m/%d"),
            "response": "json"
        }
        try:
            response = requests.get(
                url, params=params, timeout=25,
                headers={"User-Agent": "Mozilla/5.0"}
            )
            response.raise_for_status()
            data = response.json()

            tables = data.get("tables", [])
            for table in tables:
                for r in table.get("data", []):
                    if len(r) < 7:
                        continue
                    frames.append({
                        "date": roc_date(r[0]),
                        "open": number(r[3]),
                        "high": number(r[4]),
                        "low": number(r[5]),
                        "close": number(r[6]),
                        "volume": number(r[1])
                    })
        except Exception:
            continue

    return pd.DataFrame(frames)

def prepare(df):
    if df.empty:
        return df

    df = df.copy()
    df["date"] = pd.to_datetime(
        df["date"], errors="coerce"
    )
    for col in ["open", "high", "low", "close", "volume"]:
        if col not in df.columns:
            df[col] = None
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["date", "close"])
    df = df.drop_duplicates("date", keep="last")
    df = df.sort_values("date")

    for n in [5, 10, 20, 60, 240]:
        df[f"MA{n}"] = df["close"].rolling(
            n, min_periods=n
        ).mean()

    return df

if not DB.exists():
    st.error("找不到 twstock.sqlite3")
    st.stop()

stocks = load_stocks()
stocks["code"] = stocks["code"].astype(str)
stocks["label"] = (
    stocks["code"] + " " + stocks["name"] +
    "（" + stocks["market"] + "）"
)

selected_code = st.query_params.get("code", "")

matches = stocks[
    stocks["code"] == str(selected_code)
]

default_index = 0
if not matches.empty:
    default_index = stocks.index.get_loc(matches.index[0])

selected_label = st.selectbox(
    "選擇股票",
    stocks["label"].tolist(),
    index=default_index
)

selected = stocks[
    stocks["label"] == selected_label
].iloc[0]

code = selected["code"]
market = selected["market"]

st.query_params["code"] = code

if st.button("🔄 更新個股一年以上歷史行情"):
    with st.spinner("正在取得官方歷史資料..."):
        if market == "上市":
            fetched = fetch_twse(code)
        else:
            fetched = fetch_tpex(code)

        if fetched.empty:
            st.warning(
                "官方歷史行情未取得資料，將使用現有資料庫。"
            )
        else:
            st.session_state[f"history_{market}_{code}"] = fetched
            st.success(f"取得 {len(fetched)} 筆歷史行情")

local = load_local(market, code)
fetched = st.session_state.get(
    f"history_{market}_{code}",
    pd.DataFrame()
)

df = pd.concat([local, fetched], ignore_index=True)
df = prepare(df)

if df.empty:
    st.warning("這檔股票目前沒有歷史資料")
    st.stop()

latest = df.iloc[-1]
close = latest["close"]

c1, c2, c3, c4 = st.columns(4)

c1.metric("最新收盤價", f"{close:.2f}")
c2.metric(
    "20日月線",
    f"{latest['MA20']:.2f}"
    if pd.notna(latest["MA20"]) else "資料不足"
)
c3.metric(
    "60日季線",
    f"{latest['MA60']:.2f}"
    if pd.notna(latest["MA60"]) else "資料不足"
)
c4.metric(
    "240日年線",
    f"{latest['MA240']:.2f}"
    if pd.notna(latest["MA240"]) else "資料不足"
)

st.caption(
    f"最新日期：{latest['date'].date()}｜"
    f"歷史交易日：{len(df)}"
)

period = st.radio(
    "觀察期間",
    ["3個月", "6個月", "1年", "全部"],
    horizontal=True
)

days = {
    "3個月": 65,
    "6個月": 130,
    "1年": 260,
    "全部": len(df)
}

chart = df.tail(days[period]).set_index("date")

st.subheader("📊 股價與均線")
st.line_chart(
    chart[
        ["close", "MA5", "MA10", "MA20", "MA60", "MA240"]
    ],
    use_container_width=True
)

st.subheader("📉 成交量")
st.bar_chart(
    chart[["volume"]],
    use_container_width=True
)

st.subheader("🔍 技術觀察")

for n, label in [
    (5, "5日線"),
    (10, "10日線"),
    (20, "月線"),
    (60, "季線"),
    (240, "年線")
]:
    ma = latest[f"MA{n}"]
    if pd.isna(ma):
        st.write(f"{label}：資料不足")
    elif close > ma:
        st.write(f"🔴 股價站上{label}")
    elif close < ma:
        st.write(f"🟢 股價跌破{label}")
    else:
        st.write(f"⚪ 股價位於{label}")

if len(df) < 240:
    st.warning(
        f"目前只有 {len(df)} 個交易日，"
        "需要至少240個有效交易日才能計算年線。"
    )

st.subheader("📋 歷史行情明細")
st.dataframe(
    df.tail(30).iloc[::-1],
    use_container_width=True,
    hide_index=True
)

st.caption(
    "技術分析僅供研究，資料可能受除權息影響，"
    "並非投資建議。"
)
