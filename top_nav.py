"""共用上方浮動導覽與黑／白模式。使用 Streamlit 原生元件以保留跨頁 session_state。"""
import streamlit as st

# 六個主選單，每個都可以點擊開啟浮動式下拉選擇。
MENUS = (
    ("🏠 市場掃描", (("市場掃描首頁", "app.py"), ("行情／均線排行榜", "pages/1_均線與法人籌碼.py"))),
    ("📊 行情與均線", (("行情與均線總覽", "pages/1_均線與法人籌碼.py"), ("個股技術分析", "pages/2_個股技術分析.py"))),
    ("🏦 法人買賣超", (("法人買／賣超前 15 名", "pages/4_法人買賣超排行.py"), ("法人籌碼總覽", "pages/1_均線與法人籌碼.py"))),
    ("⭐ 自選個股", (("我的自選個股", "pages/3_自選個股.py"), ("選股排行榜", "pages/1_均線與法人籌碼.py"))),
    ("🏆 近期高分", (("近期高分股票", "pages/5_近期高分股票.py"), ("短線突破雷達", "app.py"))),
    ("📈 個股分析", (("個股技術分析", "pages/2_個股技術分析.py"), ("自選個股走勢", "pages/3_自選個股.py"))),
)


def _theme_css(light):
    bg = "#f8fafc" if light else "#0c1422"
    panel = "#ffffff" if light else "#162334"
    text = "#192638" if light else "#eff5fd"
    muted = "#5b6a80" if light else "#9fb2c9"
    border = "#dce4ed" if light else "#2c4057"
    hover = "#e8f3fe" if light else "#20384f"
    accent = "#1279c4" if light else "#5cb5fa"
    # DataGrid 由 Streamlit 自己繪製，此處以容器及字色為主；原生介面仍會受使用者瀏覽器設定影響。
    return f"""
    <style>
    :root {{
      --background-color: {bg};
      --secondary-background-color: {panel};
      --text-color: {text};
      --primary-color: {accent};
    }}
    html, body, [data-testid="stApp"], [data-testid="stAppViewContainer"],
    [data-testid="stMain"], [data-testid="stHeader"],
    [data-testid="stSidebar"] {{
      background-color: {bg} !important;
      color: {text} !important;
    }}
    [data-testid="stApp"] p, [data-testid="stApp"] h1,
    [data-testid="stApp"] h2, [data-testid="stApp"] h3,
    [data-testid="stApp"] label, [data-testid="stApp"] span,
    [data-testid="stSidebar"] p, [data-testid="stSidebar"] label {{
      color: {text} !important;
    }}
    [data-testid="stApp"] [data-testid="stMarkdownContainer"],
    [data-testid="stApp"] [data-testid="stMarkdownContainer"] li,
    [data-testid="stApp"] [data-testid="stMarkdownContainer"] strong,
    [data-testid="stApp"] [data-testid="stWidgetLabel"],
    [data-testid="stApp"] [data-testid="stPopover"] button,
    [data-testid="stApp"] [data-testid="stPageLink"] a {{
      color: {text} !important;
    }}
    [data-testid="stApp"] .block-container {{
      padding-top: 5.5rem !important;
    }}
    [data-testid="stApp"] small, [data-testid="stApp"] .stCaption {{
      color: {muted} !important;
    }}
    [data-testid="stMetric"], .market-header, .stock-table-wrap {{
      background: {panel} !important;
      border-color: {border} !important;
    }}
    .market-header b, .market-header small {{
      color: {text} !important;
    }}
    .stock-table th {{
      background: {hover} !important;
      color: {text} !important;
    }}
    .stock-table td {{
      background: {panel} !important;
      color: {text} !important;
      border-color: {border} !important;
    }}
    [data-testid="stMetric"] [data-testid="stMetricValue"],
    [data-testid="stMetric"] label {{
      color: {text} !important;
    }}
    .st-key-radar_top_nav {{
      position: sticky;
      top: 3.75rem;
      z-index: 90;
      background: {panel};
      border: 1px solid {border};
      border-radius: 12px;
      padding: 12px 14px 10px;
      min-height: 64px;
      margin-bottom: 16px;
      box-shadow: 0 8px 25px rgba(5, 15, 35, .10);
    }}
    .st-key-radar_top_nav [data-testid="stPopover"] button {{
      background: transparent !important;
      color: {text} !important;
      border: none !important;
      border-radius: 5px !important;
      font-weight: 650;
      white-space: nowrap;
    }}
    .st-key-radar_top_nav [data-testid="stPopover"] button:hover {{
      background: {hover} !important;
      color: {accent} !important;
    }}
    .st-key-radar_top_nav [data-testid="stToggle"] {{
      margin-top: 4px;
    }}
    .st-key-radar_top_nav [data-testid="stToggle"] label {{
      color: {text} !important;
      white-space: nowrap;
    }}
    [data-testid="stPopoverBody"], [data-testid="stPopoverBody"] * {{
      color: {text} !important;
    }}
    [data-testid="stPopoverBody"] {{
      border: 1px solid {border};
      background: {panel};
      box-shadow: 0 12px 28px rgba(0,0,0,.22);
    }}
    </style>
    """


def _update_theme_preference():
    """切換先寫入非 Widget 狀態，避免跨頁時 Streamlit 清理 Widget key。"""
    st.session_state["radar_theme_preference"] = bool(st.session_state["_radar_theme_toggle"])


def show_top_nav():
    """置頂浮動選單與跨頁保存的黑白色系。"""
    if "radar_theme_preference" not in st.session_state:
        st.session_state["radar_theme_preference"] = False
    # Streamlit 切換頁面時會清理前頁 Widget 的 key。非 Widget 的 preference 保持不變。
    st.session_state["_radar_theme_toggle"] = bool(st.session_state["radar_theme_preference"])
    st.markdown(_theme_css(bool(st.session_state["radar_theme_preference"])), unsafe_allow_html=True)
    with st.container(key="radar_top_nav"):
        cols = st.columns([1, 1, 1.2, 1, 1, 1, 1.15], gap="small", vertical_alignment="center")
        for col, (title, links) in zip(cols, MENUS):
            with col:
                with st.popover(title, use_container_width=True):
                    for label, path in links:
                        st.page_link(path, label=label, use_container_width=True)
        with cols[-1]:
            st.toggle("☀️ 白底模式", key="_radar_theme_toggle",
                      on_change=_update_theme_preference,
                      help="開啟為白底；關閉為黑底。")
