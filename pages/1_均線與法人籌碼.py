
import sqlite3
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="台股 AI 突破雷達 V2.4",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

DB = Path(__file__).resolve().parents[1] / "twstock.sqlite3"
MA = (5, 10, 20, 60, 240)

st.markdown("""
<style>
.block-container {
    max-width: 100%;
    padding: 1rem 1.4rem 2rem;
}
h1 {font-size: 1.9rem !important}
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
    padding: 12px 16px;
    border-left: 4px solid #2aa6c9;
    border-radius: 4px;
    margin: 12px 0;
}
.market-header b {
    color: #eaf4ff;
    font-size: 1.1rem;
}
.market-header small {color: #9eb4c9}
.stTabs [data-baseweb="tab-list"] {gap: 5px}
.stTabs [data-baseweb="tab"] {
    padding: 10px 18px;
}
.stTabs [aria-selected="true"] {
    background: #213448;
}
</style>
""", unsafe_allow_html=True)


@st.cache_data(ttl=300)
def prices_from_db(path, stamp):
    with sqlite3.connect(path) as conn:
        return pd.read_sql_query(
            """
            SELECT date, market, code, name, close, volume
            FROM daily
            ORDER BY market, code, date
            """,
            conn,
        )


@st.cache_data(ttl=300)
def institutions_from_db(path, stamp):
    with sqlite3.connect(path) as conn:
        tables = {
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if "institutional" not in tables:
            return None
        return pd.read_sql_query(
            "SELECT * FROM institutional", conn
        )


def normalize_inst(df):
    required = {
        "date", "market", "code", "name",
        "foreign_net", "trust_net"
    }
    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            "缺少欄位：" + "、".join(sorted(missing))
        )

    df = df.copy()
    df["date"] = pd.to_datetime(
        df["date"], errors="coerce"
    )
    df["code"] = (
        df["code"].astype(str)
        .str.replace(r"\.0$", "", regex=True)
        .str.strip()
    )
    for c in ("foreign_net", "trust_net"):
        df[c] = pd.to_numeric(
            df[c].astype(str).str.replace(
                ",", "", regex=False
            ),
            errors="coerce",
        )
    return df.dropna(subset=["date"])


def market_filter(df, selected):
    if selected == "上市＋上櫃":
        return df
    return df[df["market"] == selected]


def style_change(v):
    if pd.isna(v):
        return ""
    if v > 0:
        return "color:#e74b58;font-weight:bold"
    if v < 0:
        return "color:#15a36c;font-weight:bold"
    return ""


def header(title, subtitle):
    st.markdown(
        f"""
        <div class="market-header">
            <b>{title}</b>
            <br>
            <small>{subtitle}</small>
        </div>
        """,
        unsafe_allow_html=True,
    )


@st.cache_data(ttl=300)
def build_ranking(prices):
    if prices.empty:
        return pd.DataFrame()

    p = prices.copy()
    group = p.groupby(
        ["market", "code"], sort=False
    )

    p["前收"] = group["close"].shift(1)
    p["漲跌幅%"] = (
        p["close"] / p["前收"] - 1
    ) * 100

    for n in MA:
        p[f"MA{n}"] = group["close"].transform(
            lambda s: s.rolling(
                n, min_periods=n
            ).mean()
        )

    p["均量20"] = group["volume"].transform(
        lambda s: s.rolling(
            20, min_periods=20
        ).mean()
    )
    p["量比"] = (
        p["volume"] /
        p["均量20"].replace(0, float("nan"))
    )

    latest = p.groupby(
        ["market", "code"], sort=False
    ).tail(1).copy()

    latest["多頭均線數"] = sum(
        (
            latest["close"] > latest[f"MA{n}"]
        ).fillna(False).astype(int)
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
            if (
                pd.notna(r["MA20"])
                and r["close"] > r["MA20"]
            )
            else "觀察"
        ),
        axis=1,
    )
    return latest


def get_stock_history(market, code):
    s = prices[
        (prices["market"] == market)
        & (prices["code"] == code)
    ].copy()

    s = s.sort_values("date")
    s = s.set_index("date")

    for n in MA:
        s[f"MA{n}"] = s["close"].rolling(
            n, min_periods=n
        ).mean()

    return s


def render_stock_analysis(market, code, name):
    s = get_stock_history(market, code)

    if s.empty:
        st.warning("目前沒有這檔股票的歷史資料")
        return

    header(
        f"📈 {code} {name}｜個股技術分析",
        "股價趨勢・月線・季線・年線・成交量",
    )

    latest = s.iloc[-1]
    close = latest["close"]

    c1, c2, c3, c4 = st.columns(4)

    c1.metric("最新收盤價", f"{close:.2f}")

    for col, n, title in (
        (c2, 20, "MA20 月線"),
        (c3, 60, "MA60 季線"),
        (c4, 240, "MA240 年線"),
    ):
        value = latest[f"MA{n}"]
        col.metric(
            title,
            f"{value:.2f}"
            if pd.notna(value)
            else "資料不足",
        )

    st.caption(
        f"最新交易日：{s.index.max().date()}"
        f"｜歷史資料：{len(s)} 個交易日"
    )

    period = st.radio(
        "觀察期間",
        ["3個月", "6個月", "1年", "全部"],
        index=2,
        horizontal=True,
        key=f"period_{market}_{code}",
    )

    period_days = {
        "3個月": 65,
        "6個月": 130,
        "1年": 260,
        "全部": len(s),
    }

    show = s.tail(period_days[period])

    line_cols = [
        "close", "MA5", "MA10",
        "MA20", "MA60", "MA240"
    ]

    chart_data = (
        show[line_cols]
        .reset_index()
        .melt(
            "date",
            var_name="指標",
            value_name="價格",
        )
        .dropna(subset=["價格"])
    )

    chart = (
        alt.Chart(chart_data)
        .mark_line(strokeWidth=2)
        .encode(
            x=alt.X(
                "date:T",
                title="交易日期",
            ),
            y=alt.Y(
                "價格:Q",
                scale=alt.Scale(zero=False),
                title="股價",
            ),
            color=alt.Color(
                "指標:N",
                scale=alt.Scale(
                    domain=line_cols,
                    range=[
                        "#ffffff",
                        "#f6bf54",
                        "#58c6f5",
                        "#d77df1",
                        "#43c59e",
                        "#ef6576",
                    ],
                ),
            ),
            tooltip=[
                alt.Tooltip(
                    "date:T", title="日期"
                ),
                "指標:N",
                alt.Tooltip(
                    "價格:Q", format=".2f"
                ),
            ],
        )
        .properties(height=380)
    )

    st.altair_chart(
        chart, use_container_width=True
    )

    st.subheader("📊 每日成交量")

    volume_data = (
        show[["volume"]]
        .reset_index()
    )

    volume_chart = (
        alt.Chart(volume_data)
        .mark_bar(color="#4c9ec5")
        .encode(
            x=alt.X(
                "date:T", title="交易日期"
            ),
            y=alt.Y(
                "volume:Q", title="成交量"
            ),
            tooltip=[
                alt.Tooltip(
                    "date:T", title="日期"
                ),
                alt.Tooltip(
                    "volume:Q",
                    title="成交量",
                    format=",",
                ),
            ],
        )
        .properties(height=150)
    )

    st.altair_chart(
        volume_chart, use_container_width=True
    )

    st.subheader("🔍 均線觀察")

    cols = st.columns(5)

    for col, n in zip(cols, MA):
        value = latest[f"MA{n}"]

        if pd.isna(value):
            status = "資料不足"
        elif close > value:
            status = "🔴 站上均線"
        elif close < value:
            status = "🟢 跌破均線"
        else:
            status = "⚪ 貼近均線"

        with col:
            st.write(f"**MA{n}**")
            st.write(status)

    if len(s) < 240:
        st.warning(
            f"目前只有 {len(s)} 個交易日。"
            "需至少 240 個有效交易日，"
            "才能完整計算年線。"
        )

    with st.expander("📋 查看歷史行情明細"):
        st.dataframe(
            s[
                ["close", "volume"] +
                [f"MA{n}" for n in MA]
            ].tail(50).iloc[::-1],
            use_container_width=True,
        )

    st.caption(
        "目前為收盤價均線走勢圖，"
        "並非開高低收日K棒。"
        "技術分析僅供研究，不構成投資建議。"
    )


def selectable_table(df, key, count=20):
    if df.empty:
        st.info("沒有符合條件的股票")
        return None

    shown = df.head(count).reset_index(
        drop=True
    )

    event = st.dataframe(
        shown,
        use_container_width=True,
        hide_index=True,
        height=min(
            900,
            42 + len(shown) * 36,
        ),
        on_select="rerun",
        selection_mode="single-row",
        key=key,
    )

    rows = event.selection.rows

    if rows:
        return int(rows[0])

    return None


st.title("📈 台股 AI 突破雷達 V2.4｜專業看盤")
st.caption(
    "台股行情｜紅漲綠跌｜均線分析｜"
    "法人籌碼｜非即時報價"
)

tab_radar, tab_ma, tab_inst = st.tabs([
    "📊 行情總覽與排行榜",
    "📈 個股技術分析",
    "🏦 法人籌碼排行榜",
])

prices = pd.DataFrame()

if DB.exists():
    try:
        prices = prices_from_db(
            str(DB),
            DB.stat().st_mtime_ns,
        )

        prices["date"] = pd.to_datetime(
            prices["date"], errors="coerce"
        )

        prices["code"] = (
            prices["code"].astype(str).str.strip()
        )

        for c in ("close", "volume"):
            prices[c] = pd.to_numeric(
                prices[c], errors="coerce"
            )

        prices = (
            prices.dropna(
                subset=["date", "close"]
            )
            .drop_duplicates(
                ["market", "code", "date"],
                keep="last",
            )
            .sort_values(
                ["market", "code", "date"]
            )
        )

    except Exception as e:
        st.error(f"行情讀取失敗：{e}")

else:
    st.warning(
        "找不到 twstock.sqlite3，"
        "請先執行歷史資料回補。"
    )

ranking = build_ranking(prices)


# ====================================
# 第一頁：行情排行榜
# ====================================

with tab_radar:
    header(
        "市場行情總覽",
        "點選股票，即可展開技術分析與成交量",
    )

    if ranking.empty:
        st.info("目前沒有可用的行情資料")

    else:
        c1, c2, c3, c4 = st.columns(
            [1.2, 1.2, 1.2, 1.5]
        )

        with c1:
            market = st.selectbox(
                "市場",
                ["上市＋上櫃", "上市", "上櫃"],
                key="rank_market",
            )

        with c2:
            sort = st.selectbox(
                "排行榜",
                [
                    "漲幅排行",
                    "跌幅排行",
                    "成交量排行",
                    "量比排行",
                    "多頭排列排行",
                ],
                key="rank_sort",
            )

        with c3:
            trend = st.selectbox(
                "均線條件",
                [
                    "全部",
                    "站上月線",
                    "站上月季線",
                ],
                key="rank_trend",
            )

        with c4:
            keyword = st.text_input(
                "搜尋代號／名稱",
                placeholder="例如 2330 或 台積電",
            )

        d = market_filter(
            ranking, market
        ).copy()

        if trend == "站上月線":
            d = d[
                d["MA20"].notna()
                & (d["close"] > d["MA20"])
            ]

        elif trend == "站上月季線":
            d = d[
                d["MA60"].notna()
                & (d["close"] > d["MA20"])
                & (d["close"] > d["MA60"])
            ]

        if keyword:
            d = d[
                d["code"].str.contains(
                    keyword,
                    case=False,
                    regex=False,
                )
                | d["name"].astype(str).str.contains(
                    keyword,
                    case=False,
                    regex=False,
                )
            ]

        sort_key, ascending = {
            "漲幅排行": ("漲跌幅%", False),
            "跌幅排行": ("漲跌幅%", True),
            "成交量排行": ("volume", False),
            "量比排行": ("量比", False),
            "多頭排列排行": (
                "多頭均線數", False
            ),
        }[sort]

        d = d.sort_values(
            sort_key,
            ascending=ascending,
            na_position="last",
        )

        latest_date = ranking[
            "date"
        ].max().date()

        m1, m2, m3, m4, m5 = st.columns(5)

        m1.metric(
            "篩選結果",
            f"{len(d):,} 檔",
        )
        m2.metric(
            "上漲家數",
            f"{int((d['漲跌幅%'] > 0).sum()):,} 檔",
        )
        m3.metric(
            "下跌家數",
            f"{int((d['漲跌幅%'] < 0).sum()):,} 檔",
        )
        m4.metric(
            "站上月線",
            f"{int((d['close'] > d['MA20']).sum()):,} 檔",
        )
        m5.metric(
            "行情最新日期",
            str(latest_date),
        )

        title_col, count_col = st.columns(
            [5, 1]
        )

        with title_col:
            st.subheader("🏆 全市場股票排行榜")

        with count_col:
            display_count = st.selectbox(
                "每頁顯示",
                [10, 20, 50],
                index=1,
                key="display_count",
            )

        st.caption(
            "點選表格中的股票列，"
            "下方會立即顯示該股技術走勢與成交量。"
        )

        view = d.rename(
            columns={
                "date": "日期",
                "market": "市場",
                "code": "代號",
                "name": "名稱",
                "close": "收盤價",
                "volume": "成交量",
            }
        )

        cols = [
            "日期", "市場", "代號", "名稱",
            "收盤價", "漲跌幅%", "成交量",
            "量比", "MA5", "MA10",
            "MA20", "MA60", "MA240",
            "多頭均線數", "均線訊號",
        ]

        view = view[cols].copy()

        view["日期"] = pd.to_datetime(
            view["日期"]
        ).dt.strftime("%Y-%m-%d")

        for col in [
            "收盤價", "漲跌幅%", "量比",
            "MA5", "MA10", "MA20",
            "MA60", "MA240",
        ]:
            view[col] = pd.to_numeric(
                view[col], errors="coerce"
            ).round(2)

        view["MA240"] = view[
            "MA240"
        ].astype(object).where(
            view["MA240"].notna(),
            "資料不足",
        )

        shown = view.head(
            display_count
        ).reset_index(drop=True)

        selected_row = selectable_table(
            shown,
            key="ranking_selection",
            count=display_count,
        )

        if selected_row is not None:
            picked = shown.iloc[selected_row]

            st.success(
                f"已選擇：{picked['代號']} "
                f"{picked['名稱']}"
            )

            render_stock_analysis(
                picked["市場"],
                str(picked["代號"]),
                picked["名稱"],
            )

        st.download_button(
            "⬇️ 下載目前排行榜 CSV",
            data=view.to_csv(
                index=False
            ).encode("utf-8-sig"),
            file_name="taiwan_stock_ma_ranking.csv",
            mime="text/csv",
        )


# ====================================
# 第二頁：個股技術分析
# ====================================

with tab_ma:
    if ranking.empty:
        st.info("目前沒有行情資料")

    else:
        c1, c2 = st.columns([1, 3])

        with c1:
            detail_market = st.selectbox(
                "市場",
                ["上市＋上櫃", "上市", "上櫃"],
                key="detail_market",
            )

        opts = market_filter(
            ranking, detail_market
        ).sort_values(
            ["market", "code"]
        ).copy()

        opts["label"] = (
            opts["code"]
            + " "
            + opts["name"].astype(str)
            + "（"
            + opts["market"]
            + "）"
        )

        with c2:
            choice = st.selectbox(
                "選擇股票",
                opts["label"].tolist(),
                key="detail_choice",
            )

        selected = opts[
            opts["label"] == choice
        ].iloc[0]

        render_stock_analysis(
            selected["market"],
            selected["code"],
            selected["name"],
        )


# ====================================
# 第三頁：法人籌碼排行榜
# ====================================

with tab_inst:
    header(
        "法人籌碼排行",
        "外資・投信｜買超與賣超排行",
    )

    st.caption(
        "優先讀取 institutional 資料表；"
        "若尚未建立資料，可手動匯入 CSV。"
    )

    uploaded = st.file_uploader(
        "匯入法人 CSV（選用）",
        type=["csv"],
        key="v24_inst",
    )

    inst = None

    try:
        if uploaded is not None:
            inst = normalize_inst(
                pd.read_csv(
                    uploaded,
                    dtype={"code": str},
                )
            )

        elif DB.exists():
            raw = institutions_from_db(
                str(DB),
                DB.stat().st_mtime_ns,
            )

            if raw is not None:
                inst = normalize_inst(raw)

    except Exception as e:
        st.error(f"法人資料讀取失敗：{e}")

    if inst is None or inst.empty:
        st.info(
            "目前沒有法人資料。"
            "每日自動抓取尚未接入，"
            "請先匯入法人 CSV。"
        )

    else:
        a, b, c, e = st.columns(
            [1.5, 1.2, 1.2, 1]
        )

        with a:
            inst_date = st.selectbox(
                "資料日期",
                sorted(
                    inst["date"].dt.date.unique(),
                    reverse=True,
                ),
            )

        with b:
            inst_market = st.selectbox(
                "市場",
                ["上市＋上櫃", "上市", "上櫃"],
                key="inst_market",
            )

        with c:
            who = st.selectbox(
                "法人",
                ["外資", "投信"],
            )

        with e:
            inst_count = st.selectbox(
                "顯示檔數",
                [10, 15, 20, 50],
                index=1,
                key="inst_count",
            )

        d = market_filter(
            inst[
                inst["date"].dt.date == inst_date
            ],
            inst_market,
        ).copy()

        col = (
            "foreign_net"
            if who == "外資"
            else "trust_net"
        )

        left, right = st.columns(2)

        for panel, title, positive, panel_key in (
            (left, "買超排行", True, "buy"),
            (right, "賣超排行", False, "sell"),
        ):
            with panel:
                st.subheader(f"{who}｜{title}")

                if positive:
                    t = d[
                        d[col] > 0
                    ].nlargest(inst_count, col)
                else:
                    t = d[
                        d[col] < 0
                    ].nsmallest(inst_count, col)

                t = t[
                    ["market", "code", "name", col]
                ].rename(
                    columns={
                        "market": "市場",
                        "code": "代號",
                        "name": "名稱",
                        col: "買賣超",
                    }
                ).reset_index(drop=True)

                picked_index = selectable_table(
                    t,
                    key=f"inst_{panel_key}",
                    count=inst_count,
                )

                if picked_index is not None:
                    picked = t.iloc[picked_index]

                    st.session_state[
                        "inst_selected_stock"
                    ] = (
                        picked["市場"],
                        str(picked["代號"]),
                        picked["名稱"],
                    )

        if "inst_selected_stock" in st.session_state:
            m, code, name = st.session_state[
                "inst_selected_stock"
            ]

            st.divider()

            if not ranking[
                (ranking["market"] == m)
                & (ranking["code"] == code)
            ].empty:
                render_stock_analysis(
                    m, code, name
                )
            else:
                st.warning(
                    f"{code} {name} "
                    "目前沒有可用的技術分析資料。"
                )

        st.download_button(
            "⬇️ 下載當日法人資料 CSV",
            data=d.to_csv(
                index=False
            ).encode("utf-8-sig"),
            file_name=f"institutional_{inst_date}.csv",
            mime="text/csv",
        )
