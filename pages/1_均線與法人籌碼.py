
import sqlite3
from pathlib import Path
from html import escape
from urllib.parse import urlencode

import pandas as pd
import altair as alt
import streamlit as st

st.set_page_config(
    page_title="台股 AI 突破雷達 V2.5",
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
            SELECT date,market,code,name,close,volume
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
    required = {
        "date", "market", "code", "name",
        "foreign_net", "trust_net"
    }
    if not required.issubset(df.columns):
        return pd.DataFrame()

    df = df.copy()
    df["date"] = pd.to_datetime(
        df["date"], errors="coerce"
    )
    df["code"] = (
        df["code"].astype(str)
        .str.replace(r"\.0$", "", regex=True)
        .str.strip()
    )
    df["market"] = df["market"].astype(str).str.strip()

    for c in ["foreign_net", "trust_net"]:
        df[c] = pd.to_numeric(
            df[c].astype(str).str.replace(
                ",", "", regex=False
            ),
            errors="coerce"
        )

    return df.dropna(subset=["date"])


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
    return "?" + urlencode({
        "stock": str(code),
        "market": str(market)
    })


def render_ranking_table(df, count):
    size = {10: 16, 20: 14, 50: 13}[count]

    columns = [
        ("date", "日期"),
        ("market", "市場"),
        ("code", "代號"),
        ("name", "名稱"),
        ("close", "收盤價"),
        ("漲跌幅%", "漲跌幅%"),
        ("volume", "成交量"),
        ("量比", "量比"),
        ("MA5", "MA5"),
        ("MA10", "MA10"),
        ("MA20", "MA20"),
        ("MA60", "MA60"),
        ("MA240", "MA240"),
        ("多頭均線數", "多頭均線數"),
        ("均線訊號", "均線訊號")
    ]

    parts = [
        f'<div class="stock-table-wrap" '
        f'style="--stock-font:{size}px">',
        '<table class="stock-table"><thead><tr>'
    ]

    for _, title in columns:
        parts.append(f"<th>{escape(title)}</th>")

    parts.append("</tr></thead><tbody>")

    for _, row in df.head(count).iterrows():
        parts.append("<tr>")

        for key, _ in columns:
            value = row[key]

            if key == "name":
                url = escape(
                    stock_url(row["market"], row["code"]),
                    quote=True
                )
                cell = (
                    f'<a class="stock-link" href="{url}" '
                    f'target="_self">'
                    f'{escape(str(value))}</a>'
                )

            elif key == "date":
                cell = escape(
                    pd.Timestamp(value).strftime("%Y-%m-%d")
                )

            elif key == "漲跌幅%":
                color = (
                    "stock-up" if value > 0
                    else "stock-down" if value < 0
                    else ""
                ) if pd.notna(value) else ""
                label = (
                    f"{value:+.2f}"
                    if pd.notna(value) else "—"
                )
                cell = (
                    f'<span class="{color}">{label}</span>'
                )

            elif key == "volume":
                cell = fmt(value, 0)

            elif key in [
                "close", "量比",
                "MA5", "MA10", "MA20",
                "MA60", "MA240"
            ]:
                cell = fmt(value)

            else:
                cell = escape(str(value))

            parts.append(f"<td>{cell}</td>")

        parts.append("</tr>")

    parts.append("</tbody></table></div>")
    st.markdown(
        "".join(parts), unsafe_allow_html=True
    )


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
        "技術均線｜成交量｜外資投信｜主力籌碼"
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

    period = st.radio(
        "觀察期間",
        ["3個月", "6個月", "1年", "全部"],
        index=2,
        horizontal=True,
        key=f"period_{market}_{code}"
    )

    days = {
        "3個月": 65,
        "6個月": 130,
        "1年": 260,
        "全部": len(s)
    }

    show = s.tail(days[period])

    st.subheader("📉 股價與技術均線")

    lines = [
        "close", "MA5", "MA10",
        "MA20", "MA60", "MA240"
    ]

    chart_data = (
        show[lines]
        .reset_index()
        .melt(
            "date",
            var_name="指標",
            value_name="價格"
        )
        .dropna(subset=["價格"])
    )

    chart = (
        alt.Chart(chart_data)
        .mark_line(strokeWidth=2)
        .encode(
            x=alt.X("date:T", title="交易日期"),
            y=alt.Y(
                "價格:Q",
                scale=alt.Scale(zero=False),
                title="股價"
            ),
            color=alt.Color(
                "指標:N",
                scale=alt.Scale(
                    domain=lines,
                    range=[
                        "#ffffff", "#f6bf54",
                        "#58c6f5", "#d77df1",
                        "#43c59e", "#ef6576"
                    ]
                )
            ),
            tooltip=[
                alt.Tooltip("date:T", title="日期"),
                "指標:N",
                alt.Tooltip("價格:Q", format=".2f")
            ]
        )
        .properties(height=380)
    )

    st.altair_chart(
        chart, use_container_width=True
    )

    st.subheader("📊 成交量與20日均量")

    volume_long = (
        show[["volume", "均量20"]]
        .reset_index()
        .melt(
            "date",
            var_name="指標",
            value_name="成交量"
        )
        .dropna(subset=["成交量"])
    )

    volume_chart = (
        alt.Chart(volume_long)
        .mark_line(strokeWidth=2)
        .encode(
            x=alt.X("date:T", title="交易日期"),
            y=alt.Y("成交量:Q", title="成交量"),
            color=alt.Color(
                "指標:N",
                scale=alt.Scale(
                    domain=["volume", "均量20"],
                    range=["#4c9ec5", "#f6bf54"]
                )
            ),
            tooltip=[
                "date:T", "指標:N",
                alt.Tooltip("成交量:Q", format=",.0f")
            ]
        )
        .properties(height=170)
    )

    st.altair_chart(
        volume_chart, use_container_width=True
    )

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
    st.subheader("🏦 最近法人籌碼")

    if inst.empty:
        st.info(
            "目前尚未取得外資、投信歷史資料。"
            "需先接入法人每日資料更新。"
        )
    else:
        d = inst[
            (inst["market"] == market)
            & (inst["code"] == code)
        ].copy()

        d = (
            d.sort_values("date")
            .drop_duplicates("date", keep="last")
        )

        if d.empty:
            st.info("這檔股票目前沒有法人資料")
        else:
            latest_inst = d.iloc[-1]

            st.caption(
                "法人最新日期："
                f"{latest_inst['date'].date()}"
                "｜單位依資料來源"
            )

            c1, c2, c3 = st.columns(3)

            for col, n in zip(
                [c1, c2, c3], [5, 10, 20]
            ):
                recent = d.tail(n)

                if len(recent) < n:
                    col.metric(
                        f"最近{n}日外資",
                        "資料不足"
                    )
                else:
                    col.metric(
                        f"最近{n}日外資",
                        fmt(recent["foreign_net"].sum(), 0)
                    )

            c1, c2, c3 = st.columns(3)

            for col, n in zip(
                [c1, c2, c3], [5, 10, 20]
            ):
                recent = d.tail(n)

                if len(recent) < n:
                    col.metric(
                        f"最近{n}日投信",
                        "資料不足"
                    )
                else:
                    col.metric(
                        f"最近{n}日投信",
                        fmt(recent["trust_net"].sum(), 0)
                    )

            chart_inst = (
                d.tail(30)[
                    ["date", "foreign_net", "trust_net"]
                ]
                .melt(
                    "date",
                    var_name="法人",
                    value_name="買賣超"
                )
            )

            inst_chart = (
                alt.Chart(chart_inst)
                .mark_bar()
                .encode(
                    x=alt.X("date:T", title="日期"),
                    y=alt.Y("買賣超:Q"),
                    color="法人:N",
                    xOffset="法人:N",
                    tooltip=[
                        "date:T", "法人:N",
                        alt.Tooltip("買賣超:Q", format=",.0f")
                    ]
                )
                .properties(height=220)
            )

            st.altair_chart(
                inst_chart, use_container_width=True
            )

            st.dataframe(
                d.tail(20).iloc[::-1][
                    ["date", "foreign_net", "trust_net"]
                ],
                use_container_width=True,
                hide_index=True
            )

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

    st.caption(
        "目前顯示收盤價均線走勢，"
        "尚非開高低收日K棒；"
        "資料僅供研究，非投資建議。"
    )


st.title("📈 台股 AI 突破雷達 V2.5｜專業看盤")
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

        for c in ["close", "volume"]:
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
            st.query_params.clear()
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
        a, b, c, d = st.columns(
            [1.2, 1.2, 1.2, 1.5]
        )

        with a:
            market = st.selectbox(
                "市場",
                ["上市＋上櫃", "上市", "上櫃"]
            )

        with b:
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

        with c:
            trend = st.selectbox(
                "均線條件",
                [
                    "全部",
                    "站上月線",
                    "站上月季線"
                ]
            )

        with d:
            keyword = st.text_input(
                "搜尋代號／名稱",
                placeholder="例如2330或台積電"
            )

        data = market_filter(
            ranking, market
        ).copy()

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

        st.caption(
            "藍色股票名稱可直接點擊。"
            "依顯示檔數自動調整表格字體。"
        )

        render_ranking_table(data, count)

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
    header(
        "法人籌碼排行榜",
        "外資、投信買賣超"
    )

    uploaded = st.file_uploader(
        "匯入法人 CSV（選用）",
        type=["csv"]
    )

    if uploaded is not None:
        try:
            inst = normalize_institutions(
                pd.read_csv(
                    uploaded, dtype={"code": str}
                )
            )
        except Exception as e:
            st.error(f"CSV讀取失敗：{e}")

    if inst.empty:
        st.info(
            "目前沒有法人資料。"
            "請先接入每日法人資料或匯入CSV。"
        )
    else:
        a, b, c = st.columns(3)

        with a:
            day = st.selectbox(
                "資料日期",
                sorted(
                    inst["date"].dt.date.unique(),
                    reverse=True
                )
            )

        with b:
            market = st.selectbox(
                "市場",
                ["上市＋上櫃", "上市", "上櫃"]
            )

        with c:
            who = st.selectbox(
                "法人",
                ["外資", "投信"]
            )

        d = market_filter(
            inst[inst["date"].dt.date == day],
            market
        )

        col = (
            "foreign_net"
            if who == "外資"
            else "trust_net"
        )

        left, right = st.columns(2)

        for panel, title, positive in [
            (left, "買超前15", True),
            (right, "賣超前15", False)
        ]:
            with panel:
                st.subheader(f"{who}｜{title}")

                if positive:
                    t = d[d[col] > 0].nlargest(15, col)
                else:
                    t = d[d[col] < 0].nsmallest(15, col)

                t = t[
                    ["market", "code", "name", col]
                ].rename(
                    columns={
                        "market": "市場",
                        "code": "代號",
                        "name": "名稱",
                        col: "買賣超"
                    }
                ).copy()

                t["查看分析"] = t.apply(
                    lambda r: stock_url(
                        r["市場"], r["代號"]
                    ),
                    axis=1
                )

                st.dataframe(
                    t,
                    column_config={
                        "查看分析":
                        st.column_config.LinkColumn(
                            "個股分析",
                            display_text="點擊查看"
                        )
                    },
                    hide_index=True,
                    use_container_width=True
                )

        st.download_button(
            "⬇️ 下載法人資料 CSV",
            data=d.to_csv(
                index=False
            ).encode("utf-8-sig"),
            file_name=f"institutional_{day}.csv",
            mime="text/csv"
        )

st.caption(
    "非即時行情｜歷史資料不足時均線不顯示"
    "｜非投資建議"
)

