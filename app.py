import streamlit as st
import requests
import os
import pandas as pd
import plotly.express as px
import time
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# ---------- PAGE CONFIG ----------
st.set_page_config(page_title="📈 Virtual Stock Market", layout="wide")

# ---------- TECH DARK THEME BACKGROUND ----------
st.markdown("""
    <style>
    .stApp {
        background-image: url("https://images.unsplash.com/photo-1507525428034-b723cf961d3e");
        background-size: cover;
        background-attachment: fixed;
        color: #e0e0e0 !important;
    }
    h1, h2, h3, h4 { color: #00ffff !important; text-shadow: 1px 1px 3px #000; }
    div.stButton > button:first-child {
        background-color: #121212 !important;
        color: #00ffff !important;
        border-radius: 12px;
        border: 2px solid #00ffff !important;
        font-weight: 600;
        transition: all 0.3s ease-in-out;
    }
    div.stButton > button:first-child:hover {
        background-color: #00ffff !important;
        color: #121212 !important;
        border: 2px solid #00ffff !important;
        transform: scale(1.05);
    }
    .stDataFrame { background-color: rgba(18, 18, 18, 0.85) !important; color: #e0e0e0 !important; border-radius: 10px; }
    .stMetric { background-color: rgba(18, 18, 18, 0.6) !important; padding: 12px; border-radius: 10px; color: #00ffff !important; }
    .streamlit-expanderHeader { background-color: #121212 !important; color: #00ffff !important; font-weight: 600; }
    a { color: #00ffff !important; text-decoration: none !important; }
    a:hover { text-decoration: underline !important; }
    ::-webkit-scrollbar { width: 8px; }
    ::-webkit-scrollbar-thumb { background: #00ffff; border-radius: 4px; }
    ::-webkit-scrollbar-track { background: rgba(18,18,18,0.5); }
    </style>
""", unsafe_allow_html=True)

# ---------- BACKEND URL ----------
BACKEND = os.environ.get("BACKEND", "https://game-of-trades-vblh.onrender.com")

# ---------- SESSION STATE ----------
for key in ["team", "round_start", "paused", "pause_time", "buy_clicked", "sell_clicked"]:
    if key not in st.session_state:
        if key in ["buy_clicked", "sell_clicked", "paused"]:
            st.session_state[key] = False
        else:
            st.session_state[key] = None if key in ["team", "round_start"] else 0

ROUND_DURATION = 30 * 60  # 30 minutes

# ---------- UTILITY FUNCTIONS ----------
def safe_get(url, timeout=5):
    try:
        r = requests.get(url, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except:
        return None

def fetch_stocks(): return safe_get(f"{BACKEND}/stocks")
def fetch_leaderboard(): return safe_get(f"{BACKEND}/leaderboard")
def fetch_news(): return safe_get(f"{BACKEND}/news")
def fetch_portfolio(team): return safe_get(f"{BACKEND}/portfolio/{team}")

def init_team(team):
    try:
        r = requests.post(f"{BACKEND}/init_team", json={"team": team})
        if r.status_code == 200: return r.json()
    except: return None
    return None

def trade(team, symbol, qty):
    try:
        r = requests.post(f"{BACKEND}/trade", json={"team": team, "symbol": symbol, "qty": qty})
        if r.status_code == 200: return r.json()
    except: return None
    return None

# ---------- TEAM REGISTRATION ----------
if st.session_state.team is None:
    st.title("👥 Register or Login Your Team")
    team_input = st.text_input("Enter Team Name")
    if st.button("Continue"):
        if team_input.strip():
            res = init_team(team_input)
            if res:
                st.session_state.team = team_input
                st.success(f"Team '{team_input}' created with ₹{res['cash']:.2f}")
                st.stop()
            else:
                port = fetch_portfolio(team_input)
                if port:
                    st.session_state.team = team_input
                    st.info(f"Team '{team_input}' logged in successfully.")
                    st.stop()
                else:
                    st.error("Error occurred. Try another team name.")
    st.stop()

team_name = st.session_state.team

# ---------- ORGANIZER PASSWORD ----------
st.sidebar.subheader("🔐 Organizer Access")
password = st.sidebar.text_input("Enter Organizer Password", type="password")
is_admin = password == "admin123"

# ---------- ORGANIZER CONTROLS ----------
if is_admin:
    with st.expander("⚙️ Organizer Controls (Admin Only)"):
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("▶️ Start Round"):
                st.session_state.round_start = time.time()
                st.session_state.paused = False
                st.success("✅ Round started.")
        with col2:
            if st.button("⏸ Pause Round"):
                if st.session_state.round_start and not st.session_state.paused:
                    st.session_state.paused = True
                    st.session_state.pause_time = time.time()
                    st.info("⏸ Round paused.")
        with col3:
            if st.button("🔄 Resume Round"):
                if st.session_state.paused:
                    st.session_state.round_start += time.time() - st.session_state.pause_time
                    st.session_state.paused = False
                    st.success("▶️ Round resumed.")
        if st.button("♻️ Reset Round"):
            st.session_state.round_start = None
            st.session_state.paused = False
            st.session_state.pause_time = 0
            st.warning("Round reset.")

# ---------- AUTO-REFRESH TIMER ----------
st_autorefresh(interval=1000, key="timer_refresh")  # refresh every 1 second

# ---------- TIMER ----------
timer_placeholder = st.empty()
if st.session_state.round_start:
    elapsed = (st.session_state.pause_time - st.session_state.round_start) if st.session_state.paused else (time.time() - st.session_state.round_start)
    remaining = max(0, ROUND_DURATION - elapsed)
    mins, secs = divmod(int(remaining), 60)
    color = "red" if remaining <= 10 else "orange" if remaining <= 60 else "green"

    if remaining <= 0:
        trading_allowed = False
        timer_placeholder.markdown("<h2 style='text-align:center; color:red;'>⏹️ Trading round has ended!</h2>", unsafe_allow_html=True)
    else:
        trading_allowed = True
        timer_placeholder.markdown(f"<h1 style='text-align:center; color:{color};'>⏱️ {mins:02d}:{secs:02d}</h1>", unsafe_allow_html=True)
else:
    trading_allowed = False
    timer_placeholder.markdown("<h3 style='text-align:center; color:orange;'>⌛ Waiting for round...</h3>", unsafe_allow_html=True)

# ---------- FETCH DATA ----------
stocks = fetch_stocks()
leaderboard = fetch_leaderboard()
news = fetch_news()
portfolio = fetch_portfolio(team_name)

# ---------- PORTFOLIO & TRADE ----------
if portfolio:
    st.subheader("💼 Portfolio")
    st.metric("Available Cash", f"₹{portfolio['cash']:.2f}")
    if portfolio["holdings"]:
        st.dataframe(pd.DataFrame.from_dict(portfolio["holdings"], orient="index"), use_container_width=True)
    else:
        st.info("No holdings yet!")

st.subheader("💸 Place Trade")
if stocks:
    col1, col2, col3, col4 = st.columns([2,2,1,1])
    with col1: selected_stock = st.selectbox("Select Stock", [s["symbol"] for s in stocks])
    with col2: qty = st.number_input("Quantity", min_value=1, step=1, value=1)
    with col3:
        if st.button("Buy"):
            if trading_allowed:
                res = trade(team_name, selected_stock, int(qty))
                st.success(f"✅ Bought {qty} of {selected_stock}" if res else "Failed to buy.")
            else: st.warning("Round ended!")
    with col4:
        if st.button("Sell"):
            if trading_allowed:
                res = trade(team_name, selected_stock, -int(qty))
                st.success(f"✅ Sold {qty} of {selected_stock}" if res else "Failed to sell.")
            else: st.warning("Round ended!")

# ---------- STOCKS DISPLAY ----------
if stocks:
    st.subheader("📊 Live Stock Prices")
    df = pd.DataFrame(stocks)
    df["Trend"] = df["pct_change"].apply(lambda x: "🟢" if x>=0 else "🔴")
    st.dataframe(df[["symbol","name","price","pct_change","Trend"]].rename(columns={"symbol":"Symbol","name":"Company","price":"Price","pct_change":"% Change"}), use_container_width=True)
    df['volume'] = [i*1000 for i in range(1,len(df)+1)]
    fig3d = px.scatter_3d(df, x='price', y='pct_change', z='volume', color='Trend', hover_name='name', size='price', size_max=18, opacity=0.8)
    fig3d.update_traces(marker=dict(line=dict(width=1,color='DarkSlateGrey')))
    fig3d.update_layout(scene=dict(xaxis_title="Price", yaxis_title="% Change", zaxis_title="Volume"), margin=dict(l=0,r=0,b=0,t=30))
    st.plotly_chart(fig3d, use_container_width=True)
else: st.warning("No stock data available.")

# ---------- LEADERBOARD ----------
st.subheader("🏆 Live Leaderboard")
if leaderboard:
    ldf = pd.DataFrame(leaderboard).sort_values("value",ascending=False).reset_index(drop=True)
    ldf.index += 1
    def highlight_top3(row):
        return ['background-color: gold; font-weight:bold']*len(row) if row.name==1 else \
               ['
