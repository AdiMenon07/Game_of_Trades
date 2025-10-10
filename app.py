import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import time
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# ---------- CONFIG ----------
st.set_page_config(page_title="📈 Game of Trades", layout="wide")

# ---------- CUSTOM THEME ----------
st.markdown("""
<style>
.stApp {
    background-color: #0b0f19;
    color: #e0e0e0;
}
h1, h2, h3, h4 {
    color: #00e0ff;
}
.stButton>button {
    border-radius: 12px;
    font-weight: bold;
    background: linear-gradient(90deg, #005bea, #00c6fb);
    color: white;
    border: none;
}
.stButton>button:hover {
    background: linear-gradient(90deg, #00c6fb, #005bea);
}
.dataframe tbody tr th {
    color: #00e0ff !important;
}
</style>
""", unsafe_allow_html=True)

# ---------- APP CONSTANTS ----------
API_URL = "https://game-of-trades-vblh.onrender.com"  # Replace with your deployed backend API
ROUND_DURATION = 300  # seconds (5 minutes)

# ---------- SESSION STATE ----------
if "team_name" not in st.session_state:
    st.session_state.team_name = ""
if "round_start" not in st.session_state:
    st.session_state.round_start = None
if "paused" not in st.session_state:
    st.session_state.paused = False
if "pause_time" not in st.session_state:
    st.session_state.pause_time = 0

# ---------- HEADER ----------
st.title("⚡ Game of Trades - Virtual Stock Market")

# ---------- LOGIN ----------
team_name = st.text_input("Enter your Team Name:", st.session_state.team_name)
if team_name:
    st.session_state.team_name = team_name
else:
    st.stop()

# ---------- TIMER ----------
colT1, colT2 = st.columns([3, 1])
with colT2:
    if st.button("▶️ Start Round", use_container_width=True):
        st.session_state.round_start = time.time()
        st.session_state.paused = False
    if st.button("⏸️ Pause", use_container_width=True):
        if not st.session_state.paused and st.session_state.round_start:
            st.session_state.pause_time = time.time()
            st.session_state.paused = True
    if st.button("⏹️ Stop", use_container_width=True):
        st.session_state.round_start = None
        st.session_state.paused = False

# ---------- AUTO REFRESH ----------
st_autorefresh(interval=5000, key="autorefresh")

# ---------- TIMER DISPLAY ----------
timer_placeholder = st.empty()
if st.session_state.round_start:
    elapsed = (st.session_state.pause_time - st.session_state.round_start) if st.session_state.paused else (time.time() - st.session_state.round_start)
    remaining = max(0, ROUND_DURATION - elapsed)
    mins, secs = divmod(int(remaining), 60)
    color = "red" if remaining <= 10 else "orange" if remaining <= 60 else "#00e0ff"

    if remaining <= 0:
        trading_allowed = False
        timer_placeholder.markdown("<h2 style='text-align:center; color:red;'>⏹️ Trading round has ended!</h2>", unsafe_allow_html=True)
    else:
        trading_allowed = True
        timer_placeholder.markdown(f"<h1 style='text-align:center; color:{color};'>⏱️ {mins:02d}:{secs:02d}</h1>", unsafe_allow_html=True)
else:
    trading_allowed = False
    timer_placeholder.markdown("<h3 style='text-align:center; color:orange;'>⌛ Waiting for round...</h3>", unsafe_allow_html=True)

# ---------- DATA FETCH HELPERS ----------
@st.cache_data(ttl=5)
def fetch_stocks():
    try:
        res = requests.get(f"{API_URL}/stocks")
        return pd.DataFrame(res.json())
    except:
        return pd.DataFrame()

@st.cache_data(ttl=5)
def fetch_leaderboard():
    try:
        res = requests.get(f"{API_URL}/leaderboard")
        return res.json()
    except:
        return []

@st.cache_data(ttl=10)
def fetch_news():
    try:
        res = requests.get(f"{API_URL}/news")
        return res.json()
    except:
        return {}

@st.cache_data(ttl=5)
def fetch_portfolio(team):
    try:
        res = requests.get(f"{API_URL}/portfolio?team={team}")
        return res.json()
    except:
        return {}

# ---------- FETCH DATA ----------
stocks = fetch_stocks()
leaderboard = fetch_leaderboard()
news = fetch_news()
portfolio = fetch_portfolio(team_name)

# ---------- PORTFOLIO ----------
st.subheader("💼 Your Portfolio")
if portfolio:
    df_port = pd.DataFrame(portfolio)
    st.dataframe(df_port, use_container_width=True)
else:
    st.info("You don’t have any stocks yet.")

# ---------- STOCK MARKET ----------
st.subheader("📈 Live Market")

if stocks is not None and not stocks.empty:
    for i, row in stocks.iterrows():
        with st.container():
            col1, col2, col3, col4, col5 = st.columns([2,1,1,1,2])
            col1.markdown(f"**{row['name']}** ({row['symbol']})")
            col2.write(f"₹{row['price']:.2f}")
            col3.write(f"{row['change']}%")
            col4.write(f"Vol: {row['volume']}")

            buy_key = f"buy_{row['symbol']}"
            sell_key = f"sell_{row['symbol']}"
            if buy_key not in st.session_state: st.session_state[buy_key] = False
            if sell_key not in st.session_state: st.session_state[sell_key] = False

            buy_clicked = col5.button("🟢 Buy", key=f"btn_buy_{row['symbol']}")
            sell_clicked = col5.button("🔴 Sell", key=f"btn_sell_{row['symbol']}")

            if buy_clicked:
                st.session_state[buy_key] = True
            if sell_clicked:
                st.session_state[sell_key] = True

            if st.session_state[buy_key]:
                resp = requests.post(f"{API_URL}/buy", json={
                    "team": team_name,
                    "symbol": row['symbol'],
                    "price": row['price']
                })
                if resp.status_code == 200:
                    st.success(f"✅ Bought {row['symbol']} successfully!")
                else:
                    st.error(f"❌ Failed to buy {row['symbol']}.")
                st.session_state[buy_key] = False

            if st.session_state[sell_key]:
                resp = requests.post(f"{API_URL}/sell", json={
                    "team": team_name,
                    "symbol": row['symbol'],
                    "price": row['price']
                })
                if resp.status_code == 200:
                    st.success(f"✅ Sold {row['symbol']} successfully!")
                else:
                    st.error(f"❌ Failed to sell {row['symbol']}.")
                st.session_state[sell_key] = False
else:
    st.warning("No live stock data available.")

# ---------- 3D PRICE MOVEMENT ----------
if stocks is not None and not stocks.empty:
    fig = px.scatter_3d(stocks, x="price", y="change", z="volume",
                        color="name", size="price", size_max=15,
                        title="Market Activity", opacity=0.8)
    st.plotly_chart(fig, use_container_width=True)

# ---------- LEADERBOARD ----------
st.subheader("🏆 Live Leaderboard")
if leaderboard:
    ldf = pd.DataFrame(leaderboard).sort_values("value", ascending=False).reset_index(drop=True)
    ldf.index += 1
    st.dataframe(ldf, use_container_width=True)
else:
    st.info("No teams yet. Waiting for participants to trade...")

# ---------- MARKET NEWS ----------
st.subheader("📰 Market News")
if news and "articles" in news and news["articles"]:
    for article in news["articles"]:
        st.markdown(f"""
        <div style='background-color:#121826; padding:10px; margin-bottom:8px; border-radius:8px; color:#e0e0e0;'>
            <b><a href="{article['url']}" target="_blank">{article['title']}</a></b><br>
            <span style="color:gray; font-size:12px;">{datetime.now().strftime('%H:%M:%S')}</span>
        </div>
        """, unsafe_allow_html=True)
else:
    st.info("No news available right now.")
