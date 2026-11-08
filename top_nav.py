"""共用上方導覽：將主要功能從左側移至網站內容最上方。"""
import streamlit as st

PAGES = [
    ("app.py", "🏠 市場掃描"),
    ("pages/1_均線與法人籌碼.py", "📊 行情與均線"),
    ("pages/4_法人買賣超排行.py", "🏦 法人買賣超"),
    ("pages/3_自選個股.py", "⭐ 自選個股"),
    ("pages/5_近期高分股票.py", "🏆 近期高分"),
    ("pages/2_個股技術分析.py", "📈 個股分析"),
]

def show_top_nav():
    """所有頁面統一使用同一列選單。"""
    cols = st.columns(len(PAGES), gap="small")
    for col, (path, label) in zip(cols, PAGES):
        with col:
            st.page_link(path, label=label, use_container_width=True)
    st.divider()
