
import streamlit as st
import pandas as pd

st.set_page_config(page_title="均線與法人籌碼", layout="wide")
st.title("📈 台股 AI 突破雷達 V2.1")
st.caption("均線趨勢｜外資與投信買賣超｜上市上櫃")

tab1, tab2 = st.tabs(["📊 均線分析", "🏦 法人排行榜"])

with tab1:
    st.subheader("五條均線分析")
    uploaded = st.file_uploader(
        "匯入歷史行情 CSV",
        type=["csv"],
        key="price_csv"
    )

    if uploaded:
        df = pd.read_csv(uploaded)
        needed = {"date", "code", "close"}
        if not needed.issubset(df.columns):
            st.error("CSV 必須包含 date、code、close 欄位")
        else:
            df["date"] = pd.to_datetime(df["date"])
            df["close"] = pd.to_numeric(
                df["close"], errors="coerce"
            )
            df["code"] = df["code"].astype(str)
            df = df.dropna(subset=["date", "close"])
            df = df.sort_values(["code", "date"])

            for n in [5, 10, 20, 60, 240]:
                df[f"MA{n}"] = (
                    df.groupby("code")["close"]
                    .transform(
                        lambda s: s.rolling(
                            n, min_periods=n
                        ).mean()
                    )
                )

            codes = sorted(df["code"].unique())
            code = st.selectbox("選擇股票", codes)
            stock = df[df["code"] == code].set_index("date")

            cols = ["close", "MA5", "MA10",
                    "MA20", "MA60", "MA240"]
            st.line_chart(stock[cols].tail(120))
            st.dataframe(
                stock[cols].tail(10),
                use_container_width=True
            )
            if len(stock) < 240:
                st.warning("歷史交易日不足 240 天，年線尚無法完整計算。")

with tab2:
    st.subheader("每日法人買賣超 TOP 15")
    st.info("請匯入已整理的法人買賣超 CSV 資料。")

    uploaded_inst = st.file_uploader(
        "匯入法人 CSV",
        type=["csv"],
        key="inst_csv"
    )

    if uploaded_inst:
        df = pd.read_csv(uploaded_inst)
        needed = {
            "date", "market", "code", "name",
            "foreign_net", "trust_net"
        }

        if not needed.issubset(df.columns):
            st.error(
                "CSV 缺少必要欄位：" +
                ", ".join(sorted(needed - set(df.columns)))
            )
        else:
            df["date"] = pd.to_datetime(
                df["date"], errors="coerce"
            )
            df = df.dropna(subset=["date"])
            latest = df["date"].max()
            df = df[df["date"] == latest].copy()

            market = st.selectbox(
                "市場",
                ["上市＋上櫃", "上市", "上櫃"]
            )
            if market != "上市＋上櫃":
                df = df[df["market"] == market]

            st.caption(f"資料日期：{latest.date()}")

            for col, title in [
                ("foreign_net", "外資"),
                ("trust_net", "投信")
            ]:
                df[col] = pd.to_numeric(
                    df[col], errors="coerce"
                )
                st.markdown(f"### {title}買賣超")

                left, right = st.columns(2)
                with left:
                    st.write("買超前 15 名")
                    st.dataframe(
                        df[df[col] > 0].nlargest(15, col),
                        use_container_width=True
                    )
                with right:
                    st.write("賣超前 15 名")
                    st.dataframe(
                        df[df[col] < 0].nsmallest(15, col),
                        use_container_width=True
                    )
