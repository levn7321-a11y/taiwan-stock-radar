
import sqlite3
from pathlib import Path
from html import escape
from urllib.parse import urlencode

import pandas as pd
import altair as alt
import streamlit as st
from top_nav import show_top_nav
from price_periods import convert_price_period, chart_tail_count
from technical_charts import chart_view, PANEL_OPTIONS, calculate_kd
from search_popularity import record_stock_search, top_stock_searches

st.set_page_config(
    page_title="台股 AI 突破雷達 V2.6.8",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

DB = Path(__file__).resolve().parents[1] / "twstock.sqlite3"
MA = (5, 10, 20, 60, 240)

show_top_nav()

st.markdown("""
<style>
.block-container {
    max-width: 100%;
    padding: 1rem 1.3rem 2rem;
}
h1 {font-size: 1.85rem !important}
div[data-testid="stMetric"] {
    background: #17212d;
    border: 1px solid #394554;
    border-radius: 7px;
    padding: 12px;
}
div[data-testid="stMetric"] label {
    color: #a7b6c9 !important;
}
div[data-testid="stMetricValue"] {
    color: #f2f6fc;
}
.market-header {
    background: linear-gradient(90deg,#172a3e,#203a50);
    padding: 13px 16px;
    border-left: 4px solid #2aa6c9;
    border-radius: 5px;
    margin: 12px 0;
}
.market-header b {
    color: #eaf4ff;
    font-size: 1.1rem;
}
.market-header small {color: #9eb4c9}
.stock-table-wrap {
    width: 100%;
    overflow-x: auto;
    border: 1px solid #394554;
    border-radius: 7px;
}
.stock-table {
    width: 100%;
    border-collapse: collapse;
    white-space: nowrap;
    font-size: var(--stock-font,14px);
}
.stock-table th {
    background: #203247;
    color: #e9f3ff;
    text-align: right;
    padding: 11px 9px;
    position: sticky;
    top: 0;
}
.stock-table td {
    padding: 10px 9px;
    text-align: right;
    border-bottom: 1px solid #354354;
}
.stock-table th:nth-child(-n+4),
.stock-table td:nth-child(-n+4) {
    text-align: left;
}
.stock-table tr:hover td {
    background: rgba(70,145,200,.13);
}
.stock-link {
    color: #259de0 !important;
    font-weight: 700;
    text-decoration: underline;
    cursor: pointer;
}
.stock-up {color:#e74b58;font-weight:700}
.stock-down {color:#15a36c;font-weight:700}
.stock-muted {color:#8995a6}
</style>
""", unsafe_allow_html=True)


@st.cache_data(ttl=300)
def load_prices(path, stamp):
    with sqlite3.connect(path) as conn:
        return pd.read_sql_query(
            """
            SELECT date,market,code,name,open,high,low,close,volume
            FROM daily
            ORDER BY market,code,date
            """, conn
        )


@st.cache_data(ttl=300)
def load_institutions(path, stamp):
    with sqlite3.connect(path) as conn:
        tables = {
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if "institutional" not in tables:
            return pd.DataFrame()
        return pd.read_sql_query(
            "SELECT * FROM institutional", conn
        )


def normalize_institutions(df):
    required = {"date", "market", "code", "name", "foreign_net", "trust_net", "dealer_net"}
    if not required.issubset(df.columns):
        return pd.DataFrame()
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.normalize()
    df["code"] = df["code"].astype(str).str.replace(r"\.0$", "", regex=True).str.strip()
    df["market"] = df["market"].astype(str).str.strip()
    for c in ["foreign_net", "trust_net", "dealer_net"]:
        df[c] = pd.to_numeric(df[c].astype(str).str.replace(",", "", regex=False), errors="coerce")
    df = df.dropna(subset=["date", "foreign_net", "trust_net", "dealer_net"])
    df = df.drop_duplicates(["date", "market", "code"], keep="last")
    # 資料庫保存原始股數；畫面統一轉換為張（一般股票 1 張 = 1000 股）。
    for c in ["foreign_net", "trust_net", "dealer_net"]:
        df[c + "_lots"] = df[c] / 1000.0
    df["total_net_lots"] = (df["foreign_net"] + df["trust_net"] + df["dealer_net"]) / 1000.0
    return df.sort_values(["market", "code", "date"])


LOT_COLUMNS = {
    "外資": "foreign_net_lots", "投信": "trust_net_lots",
    "自營商": "dealer_net_lots", "三大法人合計": "total_net_lots",
}


SECURITY_TYPES = ["一般股票（代碼初篩）", "ETF／其他證券（代碼初篩）", "全部商品"]

def filter_security_type(df, choice):
    """代碼初篩，非交易所官方商品分類；不可視為精確股票清單。"""
    if df.empty or choice == "全部商品":
        return df
    stock_like = df["code"].astype(str).str.fullmatch(r"[1-9][0-9]{3}", na=False)
    return df[stock_like] if choice == SECURITY_TYPES[0] else df[~stock_like]

def signed_lots(value, decimals=0):
    if pd.isna(value):
        return "—"
    value = float(value)
    if decimals == 0 and value != 0 and abs(value) < 0.5:
        decimals = 3
    return f"{value:+,.{decimals}f}"


def trading_dates_by_market(price_df, market, n):
    return sorted(price_df.loc[price_df["market"] == market, "date"].dropna().unique())[-n:]


def build_inst_ranking(inst_df, price_df, market_choice, n):
    if inst_df.empty or price_df.empty:
        return pd.DataFrame()
    markets = ["上市", "上櫃"] if market_choice == "上市＋上櫃" else [market_choice]
    result = []
    for m in markets:
        dates = trading_dates_by_market(price_df, m, n)
        if len(dates) < n:
            continue
        part = inst_df[(inst_df["market"] == m) & (inst_df["date"].isin(dates))].copy()
        if part.empty:
            continue
        sums = part.groupby(["market", "code"], as_index=False).agg(
            name=("name", "last"), days=("date", "nunique"),
            **{key: (key, "sum") for key in LOT_COLUMNS.values()}
        )
        # 只納入最近 N 個市場交易日都有法人紀錄的股票。
        sums = sums[sums["days"] == n].copy()
        if not sums.empty:
            result.append(sums)
    return pd.concat(result, ignore_index=True) if result else pd.DataFrame()


def market_filter(df, selected):
    if selected == "上市＋上櫃":
        return df
    return df[df["market"] == selected]


def header(title, subtitle):
    st.markdown(
        '<div class="market-header">'
        f'<b>{escape(title)}</b><br>'
        f'<small>{escape(subtitle)}</small>'
        '</div>',
        unsafe_allow_html=True
    )


@st.cache_data(ttl=300)
def build_ranking(prices):
    if prices.empty:
        return pd.DataFrame()

    p = prices.copy()
    g = p.groupby(["market", "code"], sort=False)

    p["前收"] = g["close"].shift(1)
    p["漲跌幅%"] = (
        p["close"] / p["前收"] - 1
    ) * 100

    for n in MA:
        p[f"MA{n}"] = g["close"].transform(
            lambda s: s.rolling(
                n, min_periods=n
            ).mean()
        )

    p["均量20"] = g["volume"].transform(
        lambda s: s.rolling(
            20, min_periods=20
        ).mean()
    )
    p["量比"] = (
        p["volume"] /
        p["均量20"].replace(0, float("nan"))
    )

    latest = g.tail(1).copy()

    latest["多頭均線數"] = sum(
        (latest["close"] > latest[f"MA{n}"])
        .fillna(False).astype(int)
        for n in MA
    )

    latest["均線訊號"] = latest.apply(
        lambda r:
        "站上月季線"
        if (
            pd.notna(r["MA60"])
            and r["close"] > r["MA20"]
            and r["close"] > r["MA60"]
        )
        else (
            "站上月線"
            if pd.notna(r["MA20"])
            and r["close"] > r["MA20"]
            else "觀察"
        ),
        axis=1
    )
    return latest


def fmt(value, decimals=2):
    if pd.isna(value):
        return "—"
    return f"{float(value):,.{decimals}f}"


def stock_url(market, code):
    params = {"stock": str(code), "market": str(market),
              "theme": "light" if st.session_state.get("radar_light_theme", True) else "dark"}
    keys = st.session_state.get("radar_watch_keys", [])
    if keys:
        params["watch"] = ",".join(keys)
    return "?" + urlencode(params)


def render_ranking_table(df, count):
    """可勾選加入自選的排行榜，日期與市場預設不顯示。"""
    shown = df.head(count).copy()
    if shown.empty:
        st.info("目前沒有符合條件的股票。")
        return
    selected_keys = set(st.session_state.get("radar_watch_keys", []))
    shown["加入自選"] = [
        f"{m}:{code}" in selected_keys
        for m, code in zip(shown["market"], shown["code"])
    ]
    shown["查看分析"] = [
        stock_url(m, code) for m, code in zip(shown["market"], shown["code"])
    ]
    names = {
        "code": "股票代號", "name": "股票名稱", "close": "收盤價",
        "volume": "成交量"
    }
    visible_columns = [
        "加入自選", "code", "name", "close", "漲跌幅%", "volume", "量比",
        "MA5", "MA10", "MA20", "MA60", "MA240", "多頭均線數",
        "均線訊號", "查看分析"
    ]
    editor = shown[visible_columns].rename(columns=names).copy()
    editor_key = "watch_editor_only" if st.session_state.get("watch_only", False) else "watch_editor_ranking"
    edited = st.data_editor(
        editor, hide_index=True, use_container_width=True,
        num_rows="fixed", key=editor_key,
        disabled=[c for c in editor.columns if c != "加入自選"],
        column_config={
            "加入自選": st.column_config.CheckboxColumn("加入自選", help="勾選後按下方加入按鈕"),
            "查看分析": st.column_config.LinkColumn("個股分析", display_text="查看圖表"),
            "收盤價": st.column_config.NumberColumn("收盤價", format="%.2f"),
            "漲跌幅%": st.column_config.NumberColumn("漲跌幅%", format="%+.2f")
        }
    )
    if st.button("⭐ 加入勾選股票", key=f"add_checked_{editor_key}"):
        additions = [
            f"{m}:{code}" for m, code, checked in zip(
                shown["market"], shown["code"], edited["加入自選"]
            ) if checked
        ]
        old = list(st.session_state.get("radar_watch_keys", []))
        updated = list(dict.fromkeys(old + additions))[:50]
        if len(updated) == len(old):
            st.info("未勾選新的股票，或已經加入自選。")
        else:
            save_watchlist(updated)
            st.rerun()


def get_history(market, code):
    s = prices[
        (prices["market"] == market)
        & (prices["code"] == code)
    ].copy()

    if s.empty:
        return s

    s = s.sort_values("date").set_index("date")

    for n in MA:
        s[f"MA{n}"] = s["close"].rolling(
            n, min_periods=n
        ).mean()

    s["均量20"] = s["volume"].rolling(
        20, min_periods=20
    ).mean()

    return s


def render_stock_analysis(market, code, name, inst):
    s = get_history(market, code)

    if s.empty:
        st.warning("找不到這檔股票的歷史行情")
        return

    header(
        f"📈 {code} {name}｜個股完整分析",
        "技術均線｜成交量｜三大法人買賣超（張）｜主力籌碼"
    )

    latest = s.iloc[-1]
    close = latest["close"]

    a, b, c, d = st.columns(4)

    a.metric("最新收盤價", fmt(close))
    b.metric("MA20 月線", fmt(latest["MA20"]))
    c.metric("MA60 季線", fmt(latest["MA60"]))
    d.metric(
        "MA240 年線",
        fmt(latest["MA240"])
        if pd.notna(latest["MA240"])
        else "資料不足"
    )

    st.caption(
        f"行情日期：{s.index.max().date()}"
        f"｜有效交易日：{len(s)}"
    )

    timeframe = st.segmented_control(
        "K 線週期", ["日線", "週線", "月線"],
        default="日線", key=f"timeframe_{market}_{code}"
    )
    period = st.radio(
        "觀察期間",
        ["3個月", "6個月", "1年", "全部"],
        index=2,
        horizontal=True,
        key=f"period_{market}_{code}"
    )
    chart_source = convert_price_period(s, timeframe or "日線")
    show = chart_source.tail(chart_tail_count(timeframe or "日線", period, len(chart_source)))
    st.caption(f"目前顯示：{timeframe or '日線'}｜週／月線為收盤價聚合後重新計算的各期均線，非日線均線。")

    st.subheader("📈 K 線與技術指標")
    indicator = st.segmented_control(
        "下方指標切換", PANEL_OPTIONS,
        default="成交量", key=f"indicator_{market}_{code}"
    )
    # 使用該市場完整交易日曆檢查法人資料是否漏日。
    calendar = prices.loc[
        (prices["market"] == market) &
        (prices["date"] <= s.index.max()), "date"
    ].dropna().drop_duplicates().sort_values()
    own_inst = inst.loc[
        (inst["market"] == market) & (inst["code"] == code),
        ["date", "foreign_net", "trust_net", "dealer_net"]
    ].copy() if not inst.empty else pd.DataFrame()
    kchart, missing = chart_view(
        show, indicator or "成交量", frequency=timeframe or "日線",
        inst=own_inst, calendar=calendar
    )
    if kchart is not None:
        st.altair_chart(kchart, use_container_width=True)
        detail = calculate_kd(show)
        end_bar = detail.iloc[-1]
        change = float(end_bar["close"] - end_bar["open"])
        color = "🔴" if change > 0 else "🟢" if change < 0 else "⚪"
        st.caption(
            f"{color} 最新 {timeframe or '日線'}："
            f"開 {end_bar['open']:,.2f}｜高 {end_bar['high']:,.2f}｜"
            f"低 {end_bar['low']:,.2f}｜收 {end_bar['close']:,.2f}｜"
            f"開收漲跌 {change:+,.2f}"
        )
        if (indicator or "成交量") == "KD線" and pd.notna(end_bar["K"]):
            st.caption(f"KD（9,3,3）：K {end_bar['K']:.1f}｜D {end_bar['D']:.1f}")
    if missing:
        st.warning(missing)
    st.caption("台股慣例：紅 K 為收漲、綠 K 為收跌。法人買賣超以張表示，紅色買超、綠色賣超；滑鼠移入圖表可查看數值。")

    if pd.notna(latest["均量20"]) and latest["均量20"] > 0:
        ratio = latest["volume"] / latest["均量20"]
        st.metric("最新量比（對20日均量）", f"{ratio:.2f}")

    st.subheader("🔍 均線觀察")

    cols = st.columns(5)

    for col, n in zip(cols, MA):
        ma = latest[f"MA{n}"]

        if pd.isna(ma):
            status = "資料不足"
        elif close > ma:
            status = "🔴 站上"
        elif close < ma:
            status = "🟢 跌破"
        else:
            status = "⚪ 持平"

        col.metric(f"MA{n}", status)

    if len(s) < 240:
        st.warning(
            f"目前只有 {len(s)} 個交易日，"
            "尚未具備完整240日年線。"
        )

    st.divider()
    st.subheader("🏦 法人買賣超分析（單位：張）")
    if inst.empty:
        st.info("目前沒有可用的三大法人資料。")
    else:
        d = inst[(inst["market"] == market) & (inst["code"] == code)].copy()
        d = d.sort_values("date").drop_duplicates("date", keep="last")
        if d.empty:
            st.info("這檔股票目前沒有法人資料。")
        else:
            last_date = d["date"].max()
            st.caption(f"最新法人日期：{last_date.date()}｜買超為正、賣超為負｜一般股票 1 張 = 1,000 股")
            latest_inst = d.iloc[-1]
            cols = st.columns(4)
            for col, (label, key) in zip(cols, LOT_COLUMNS.items()):
                col.metric(f"{label}（當日）", signed_lots(latest_inst[key]) + " 張")

            st.markdown("**法人累計買賣超**")
            rows = []
            for n in [1, 5, 10, 20]:
                dates = trading_dates_by_market(prices, market, n)
                recent = d[d["date"].isin(dates)]
                row = {"期間": f"近 {n} 日"}
                complete = len(dates) == n and recent["date"].nunique() == n
                for label, key in LOT_COLUMNS.items():
                    row[label + "（張）"] = signed_lots(recent[key].sum()) if complete else "資料不足"
                rows.append(row)
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
            st.caption("累計以市場最近 N 個行情交易日計算；缺少任一天法人資料時顯示資料不足，不以零代替。")

            chart_source = d.tail(20).copy()
            chart_long = chart_source[["date"] + list(LOT_COLUMNS.values())].melt(
                "date", var_name="key", value_name="買賣超張數"
            )
            labels = {v: k for k, v in LOT_COLUMNS.items()}
            chart_long["法人"] = chart_long["key"].map(labels)
            chart_long["方向"] = chart_long["買賣超張數"].apply(lambda v: "買超" if v > 0 else "賣超" if v < 0 else "持平")
            chosen = st.selectbox("柱狀圖顯示", list(LOT_COLUMNS), key=f"inst_chart_{market}_{code}")
            chart_long = chart_long[chart_long["法人"] == chosen]
            bars = alt.Chart(chart_long).mark_bar().encode(
                x=alt.X("date:T", title="交易日期"),
                y=alt.Y("買賣超張數:Q", title="買賣超（張）"),
                color=alt.Color("方向:N", scale=alt.Scale(
                    domain=["買超", "賣超", "持平"], range=["#e74b58", "#15a36c", "#8995a6"]
                )),
                tooltip=[alt.Tooltip("date:T", title="日期"), "法人:N", alt.Tooltip("買賣超張數:Q", format="+,.3f")]
            ).properties(height=240)
            st.altair_chart(bars, use_container_width=True)
            details = d.tail(20).iloc[::-1][["date"] + list(LOT_COLUMNS.values())].copy()
            details = details.rename(columns={"date": "日期", **{v: k + "（張）" for k, v in LOT_COLUMNS.items()}})
            st.dataframe(details, hide_index=True, use_container_width=True)

    st.subheader("🏢 主力籌碼")
    st.info(
        "主力買賣超與券商分點資料尚未接入。"
        "外資、投信資料不能直接視為主力買賣超。"
    )

    with st.expander("📋 最近50日行情與均線"):
        st.dataframe(
            s.tail(50).iloc[::-1][
                ["close", "volume"] +
                [f"MA{n}" for n in MA]
            ],
            use_container_width=True
        )

    st.caption("技術訊號僅供研究，未還原除權息，非投資建議。")


st.title("📈 台股 AI 突破雷達 V2.6.8｜專業看盤")
st.caption(
    "點擊股票名稱查看技術分析、成交量與法人籌碼"
)

prices = pd.DataFrame()
inst = pd.DataFrame()

if DB.exists():
    try:
        prices = load_prices(
            str(DB), DB.stat().st_mtime_ns
        )
        prices["date"] = pd.to_datetime(
            prices["date"], errors="coerce"
        )
        prices["code"] = prices["code"].astype(str).str.strip()

        for c in ["open", "high", "low", "close", "volume"]:
            prices[c] = pd.to_numeric(
                prices[c], errors="coerce"
            )

        prices = (
            prices.dropna(subset=["date", "close"])
            .drop_duplicates(
                ["market", "code", "date"],
                keep="last"
            )
            .sort_values(["market", "code", "date"])
        )

        inst = normalize_institutions(
            load_institutions(
                str(DB), DB.stat().st_mtime_ns
            )
        )

    except Exception as e:
        st.error(f"資料讀取失敗：{e}")
else:
    st.error("找不到 twstock.sqlite3")

ranking = build_ranking(prices)

# 自選清單保存在網址參數，不寫入共用資料庫；收藏網址即可下次繼續使用。
def read_watchlist(raw, valid_keys):
    selected = []
    for item in str(raw or "").split(","):
        item = item.strip()
        if item in valid_keys and item not in selected:
            selected.append(item)
    return selected[:50]


def save_watchlist(items):
    items = list(dict.fromkeys(items))[:50]
    st.session_state["radar_watch_keys"] = items
    if items:
        st.query_params["watch"] = ",".join(items[:100])
    elif "watch" in st.query_params:
        del st.query_params["watch"]


stock_options = {}
if not ranking.empty:
    for row in ranking[["market", "code", "name"]].itertuples(index=False):
        key = f"{row.market}:{row.code}"
        stock_options[key] = f"{row.code} {row.name}（{row.market}）"

watchlist = read_watchlist(st.query_params.get("watch", "") or ",".join(st.session_state.get("radar_watch_keys", [])), stock_options)
st.session_state["radar_watch_keys"] = watchlist
with st.sidebar:
    st.header("⭐ 自選個股")
    watch_only = st.toggle("只顯示自選個股畫面", value=st.query_params.get("view") == "watch", key="watch_only")
    if watch_only:
        st.query_params["view"] = "watch"
    elif st.query_params.get("view") == "watch":
        del st.query_params["view"]
    chosen = st.selectbox(
        "新增自選個股",
        options=[""] + list(stock_options),
        format_func=lambda key: "搜尋股票並加入" if not key else stock_options[key],
        key="watch_add",
    )
    if st.button("＋ 加入自選", use_container_width=True, disabled=not chosen or chosen in watchlist or len(watchlist) >= 50):
        watchlist.append(chosen)
        save_watchlist(watchlist)
        st.rerun()
    st.caption(f"已收藏 {len(watchlist)} 檔（最多 50 檔）")
    for key in watchlist:
        left, right = st.columns([5, 1])
        left.markdown(f"[{stock_options[key]}]({stock_url(*key.split(':', 1))}&watch={','.join(watchlist)}&view=watch)")
        if right.button("✕", key=f"watch_remove_{key}", help="移除自選"):
            watchlist.remove(key)
            save_watchlist(watchlist)
            st.rerun()
    st.caption("自選清單保存在目前網址，請將網址加入書籤；換裝置或清除網址參數不會自動同步。")

selected_code = st.query_params.get("stock", "")
selected_market = st.query_params.get("market", "")

# 有指定股票時，先顯示分析，避免還要往下找
if selected_code and selected_market:
    matched = ranking[
        (ranking["code"] == selected_code)
        & (ranking["market"] == selected_market)
    ]

    if not matched.empty:
        picked = matched.iloc[0]

        if st.button("← 返回股票排行榜"):
            remaining = {k: st.query_params[k] for k in ("theme", "watch") if k in st.query_params}
            st.query_params.clear()
            st.query_params.update(remaining)
            st.rerun()

        render_stock_analysis(
            picked["market"],
            picked["code"],
            picked["name"],
            inst
        )
    else:
        st.warning("找不到指定的股票")

    st.stop()


if watch_only:
    header("⭐ 我的自選個股", "只顯示收藏的股票｜點擊股票名稱查看完整技術分析與法人籌碼")
    if not watchlist:
        st.info("目前沒有自選個股，請使用左側「新增自選個股」加入。")
    else:
        keys = set(watchlist)
        watch_data = ranking[
            ranking.apply(lambda r: f"{r['market']}:{r['code']}" in keys, axis=1)
        ].copy()
        if watch_data.empty:
            st.warning("自選清單中的股票目前沒有行情資料。")
        else:
            watch_data["自選順序"] = watch_data.apply(
                lambda r: watchlist.index(f"{r['market']}:{r['code']}"), axis=1
            )
            watch_data = watch_data.sort_values("自選順序")
            st.metric("自選個股", f"{len(watch_data)} 檔")
            render_ranking_table(watch_data, 50 if len(watch_data) > 20 else 20)
            st.caption("自選股使用現有日收盤行情，並非即時報價。")
    st.stop()


tab_radar, tab_ma, tab_inst = st.tabs([
    "📊 行情總覽與排行榜",
    "📈 個股技術分析",
    "🏦 法人籌碼排行榜"
])


with tab_radar:
    header(
        "市場行情總覽",
        "點擊股票名稱，即可查看個股完整分析"
    )

    if ranking.empty:
        st.info("目前沒有行情資料")
    else:
        a, b, c, d, e = st.columns([1.15, 1.45, 1.2, 1.2, 1.5])

        with a:
            market = st.selectbox(
                "市場",
                ["上市＋上櫃", "上市", "上櫃"]
            )

        with b:
            security_type = st.selectbox("商品類型", SECURITY_TYPES, key="radar_security_type")

        with c:
            sort = st.selectbox(
                "排行榜",
                [
                    "漲幅排行",
                    "跌幅排行",
                    "成交量排行",
                    "量比排行",
                    "多頭排列排行"
                ]
            )

        with d:
            trend = st.selectbox(
                "均線條件",
                [
                    "全部",
                    "站上月線",
                    "站上月季線"
                ]
            )

        with e:
            keyword = st.text_input(
                "搜尋代號／名稱",
                placeholder="例如 2330 或台積電"
            )
            if st.button("🔎 搜尋個股", key="submit_stock_search", use_container_width=True):
                term = keyword.strip().casefold()
                exact = ranking.loc[
                    (ranking["code"].astype(str).str.casefold() == term) |
                    (ranking["name"].astype(str).str.casefold() == term)
                ] if term else pd.DataFrame()
                if len(exact) == 1:
                    match = exact.iloc[0]
                    record_stock_search(match["market"], match["code"], stock_options)
                    st.success(f"已搜尋：{match['code']} {match['name']}")
                elif term:
                    st.info("輸入可唯一辨識的股票代號或名稱，才計入站內熱門搜尋。")

        data = filter_security_type(
            market_filter(ranking, market), security_type
        ).copy()
        st.caption("商品分類為代碼初步篩選，並非證交所／櫃買中心的正式證券分類。")

        if trend == "站上月線":
            data = data[
                data["MA20"].notna()
                & (data["close"] > data["MA20"])
            ]

        elif trend == "站上月季線":
            data = data[
                data["MA60"].notna()
                & (data["close"] > data["MA20"])
                & (data["close"] > data["MA60"])
            ]

        if keyword:
            data = data[
                data["code"].str.contains(
                    keyword, case=False, regex=False
                )
                | data["name"].astype(str).str.contains(
                    keyword, case=False, regex=False
                )
            ]

        sort_key, ascending = {
            "漲幅排行": ("漲跌幅%", False),
            "跌幅排行": ("漲跌幅%", True),
            "成交量排行": ("volume", False),
            "量比排行": ("量比", False),
            "多頭排列排行": ("多頭均線數", False)
        }[sort]

        data = data.sort_values(
            sort_key,
            ascending=ascending,
            na_position="last"
        )

        m1, m2, m3, m4, m5 = st.columns(5)

        m1.metric("篩選結果", f"{len(data):,} 檔")
        m2.metric(
            "上漲家數",
            f"{int((data['漲跌幅%'] > 0).sum()):,} 檔"
        )
        m3.metric(
            "下跌家數",
            f"{int((data['漲跌幅%'] < 0).sum()):,} 檔"
        )
        m4.metric(
            "站上月線",
            f"{int((data['close'] > data['MA20']).sum()):,} 檔"
        )
        m5.metric(
            "行情最新日期",
            str(ranking["date"].max().date())
        )

        left, right = st.columns([5, 1])

        with left:
            st.subheader("🏆 全市場股票排行榜")

        with right:
            count = st.selectbox(
                "每頁顯示",
                [10, 20, 50],
                index=1
            )

        st.caption("勾選左欄後按「加入勾選股票」；點選右側「查看圖表」開啟個股分析。")

        render_ranking_table(data, count)

        st.subheader("🔎 站內熱門搜尋 TOP 10")
        popular = top_stock_searches(stock_options)
        if popular:
            hot = pd.DataFrame(popular, columns=["市場", "代號", "股票", "搜尋次數"])
            hot.insert(0, "名次", range(1, len(hot) + 1))
            hot["查看圖表"] = [
                stock_url(m, code) for m, code in zip(hot["市場"], hot["代號"])
            ]
            st.dataframe(hot.drop(columns=["市場"]), hide_index=True, use_container_width=True,
                         column_config={"查看圖表": st.column_config.LinkColumn("個股分析", display_text="查看圖表")})
        else:
            st.info("目前尚無有效股票代號搜尋紀錄。")
        st.caption("僅統計本站使用者主動提交的有效個股搜尋，非全台市場熱度；部署重啟後可能歸零。")

        st.download_button(
            "⬇️ 下載排行榜 CSV",
            data=data.to_csv(
                index=False
            ).encode("utf-8-sig"),
            file_name="taiwan_stock_ranking.csv",
            mime="text/csv"
        )


with tab_ma:
    if ranking.empty:
        st.info("沒有行情資料")
    else:
        opts = ranking.sort_values(
            ["market", "code"]
        ).copy()

        opts["label"] = (
            opts["code"] + " "
            + opts["name"].astype(str)
            + "（" + opts["market"] + "）"
        )

        choice = st.selectbox(
            "選擇股票",
            opts["label"].tolist()
        )

        picked = opts[
            opts["label"] == choice
        ].iloc[0]

        render_stock_analysis(
            picked["market"],
            picked["code"],
            picked["name"],
            inst
        )


with tab_inst:
    header("法人籌碼排行榜 V2.6.8", "外資｜投信｜自營商｜三大法人合計｜單位：張")
    st.caption("排行榜以資料庫法人股數換算為張；僅列入選定期間每個交易日都有法人紀錄的股票。")
    if inst.empty:
        st.info("資料庫尚無完整三大法人資料，請先確認每日資料更新。")
    else:
        c1, c2, c3, c4, c5 = st.columns(5)
        with c1:
            inst_market = st.selectbox("市場", ["上市＋上櫃", "上市", "上櫃"], key="inst_market")
        with c2:
            inst_type = st.selectbox("商品類型", SECURITY_TYPES, key="inst_security_type")
        with c3:
            inst_period = st.selectbox("累計期間", [1, 5, 10, 20], key="inst_period", format_func=lambda n: f"近 {n} 個交易日")
        with c4:
            inst_who = st.selectbox("法人類別", list(LOT_COLUMNS), key="inst_who")
        with c5:
            inst_count = st.selectbox("排行筆數", [15, 30, 50], key="inst_count")

        board = filter_security_type(
            build_inst_ranking(inst, prices, inst_market, inst_period), inst_type
        )
        st.caption("一般股票以四位數且首碼 1～9 初步辨識；ETF／其他證券分類僅供篩選參考，不代表官方證券分類。")
        if board.empty:
            st.warning("所選期間沒有符合完整資料條件的股票。可先改選近 1 日或 5 日，等待歷史缺口補齊。")
        else:
            col = LOT_COLUMNS[inst_who]
            latest_date = inst["date"].max().date()
            st.caption(f"法人資料最新日期：{latest_date}｜有效股票 {len(board):,} 檔｜買超紅色、賣超綠色")
            left, right = st.columns(2)
            for panel, title, positive in [(left, "買超排行榜", True), (right, "賣超排行榜", False)]:
                with panel:
                    st.subheader(f"{inst_who}｜{title}")
                    selected = board[board[col] > 0].nlargest(inst_count, col) if positive else board[board[col] < 0].nsmallest(inst_count, col)
                    selected = selected[["market", "code", "name", col]].rename(columns={
                        "market": "市場", "code": "代號", "name": "名稱", col: "買賣超（張）"
                    }).copy()
                    # 計算保留原始精度，畫面預設顯示整數張。
                    selected["買賣超（張）"] = selected["買賣超（張）"].map(signed_lots)
                    selected["個股分析"] = selected.apply(lambda r: stock_url(r["市場"], r["代號"]), axis=1)
                    st.dataframe(selected, hide_index=True, use_container_width=True,
                        column_config={"個股分析": st.column_config.LinkColumn("個股分析", display_text="點擊查看")})
            export = board.rename(columns={"market": "市場", "code": "代號", "name": "名稱", **{v: k + "（張）" for k, v in LOT_COLUMNS.items()}})
            st.download_button("⬇️ 下載法人累計排行榜 CSV", data=export.to_csv(index=False).encode("utf-8-sig"),
                file_name=f"institutional_ranking_{inst_period}d.csv", mime="text/csv")


st.caption(
    "非即時行情｜歷史資料不足時均線不顯示"
    "｜非投資建議"
)
