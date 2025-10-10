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

# ---------- TECH DARK THEME ----------
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
</style>
""", unsafe_allow_html=True)

# ---------- BACKEND ----------
BACKEND = os.environ.get("BACKEND", "https://game-of-trades-vblh.onrender.com")

# ---------- SESSION STATE ----------
for key in ["team", "round_start", "paused", "pause_time"]:
    if key not in st.session_state:
        st.session_state[key] = None if key != "paused" else False

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
        if r.status_code == 200:
            return r.json()
    except:
        return None
    return None

def trade(team, symbol, qty):
    try:
        r = requests.post(f"{BACKEND}/trade", json={"team": team, "symbol": symbol, "qty": qty})
        if r.status_code == 200:
            return r.json()
    except:
        return None
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

# ---------- ORGANIZER ----------
st.sidebar.subheader("🔐 Organizer Access")
password = st.sidebar.text_input("Enter Organizer Password", type="password")
is_admin = password == "admin123"

if is_admin:
    with st.expander("⚙️ Organizer Controls (Admin Only)"):
        col1, col2, col3, col4 = st.columns(4)
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
        with col4:
            if st.button("♻️ Reset Round"):
                st.session_state.round_start = None
                st.session_state.paused = False
                st.session_state.pause_time = 0
                st.warning("Round reset.")

# ---------- AUTO REFRESH ----------
refresh = st.sidebar.checkbox("🔄 Auto-refresh data every 5s", value=True)
if refresh:
    st_autorefresh(interval=5000, key="data_refresh")

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

# ---------- FETCH LIVE DATA ----------
stocks = fetch_stocks()
leaderboard = fetch_leaderboard()
news = fetch_news()
portfolio = fetch_portfolio(team_name)

# ---------- PORTFOLIO ----------
if portfolio:
    st.subheader("💼 Portfolio")
    st.metric("Available Cash", f"₹{portfolio['cash']:.2f}")
    if portfolio.get("holdings"):
        st.dataframe(pd.DataFrame.from_dict(portfolio["holdings"], orient="index"), use_container_width=True)
    else:
        st.info("No holdings yet!")

# ---------- TRADE SECTION ----------
if stocks and trading_allowed:
    st.subheader("💸 Execute Trades")

    with st.form("trade_form", clear_on_submit=False):
        col1, col2, col3 = st.columns([2, 2, 1])
        with col1:
            selected_stock = st.selectbox("Select Stock", [s["symbol"] for s in stocks])
        with col2:
            qty = st.number_input("Quantity", min_value=1, step=1, value=1)
        with col3:
            action = st.radio("Action", ["Buy", "Sell"], horizontal=True)

        submitted = st.form_submit_button("Confirm Trade")

        if submitted:
            if action == "Buy":
                res = trade(team_name, selected_stock, int(qty))
                if res:
                    st.success(f"✅ Bought {qty} of {selected_stock}")
                else:
                    st.error("Failed to buy. Check cash balance.")
            else:
                res = trade(team_name, selected_stock, -int(qty))
                if res:
                    st.success(f"✅ Sold {qty} of {selected_stock}")
                else:
                    st.error("Failed to sell. Check holdings.")
            portfolio = fetch_portfolio(team_name)
            # Quick toast so participants see immediate feedback
            try:
                st.toast("Trade executed successfully!", icon="💹")
            except Exception:
                pass

# ---------- LIVE STOCKS + 3D CHART ----------
st.subheader("📊 Live Stock Prices")

# Auto-refresh block (runs every 5 seconds)
stocks = fetch_stocks()  # Fetch fresh stock data

if stocks:
    df = pd.DataFrame(stocks)

    # Calculate trend dynamically
    df["Trend"] = df["pct_change"].apply(lambda x: "🟢" if x >= 0 else "🔴")

    # Add a small 'volume' for 3D chart visualization (dummy for demo purposes)
    df['volume'] = [i*1000 for i in range(1, len(df)+1)]

    # Display updated dataframe with styling
    def style_trend(row):
        return ['color: green;' if row['Trend']=='🟢' else 'color: red;']*len(row)
    st.dataframe(
        df[["symbol","name","price","pct_change","Trend"]].rename(
            columns={"symbol":"Symbol","name":"Company","price":"Price","pct_change":"% Change"}
        ).style.apply(style_trend, axis=1),
        use_container_width=True
    )

    # Create 3D scatter plot
    fig3d = px.scatter_3d(
        df,
        x='price',
        y='pct_change',
        z='volume',
        color='Trend',
        color_discrete_map={'🟢':'#00ffcc','🔴':'#ff4d4d'},
        hover_name='name',
        size='price',
        size_max=20,
        opacity=0.8
    )

    # Dark theme for 3D plot
    fig3d.update_layout(
        scene=dict(
            xaxis_title="Price",
            yaxis_title="% Change",
            zaxis_title="Volume",
            xaxis=dict(backgroundcolor="rgb(18,18,18)", gridcolor="gray", showbackground=True),
            yaxis=dict(backgroundcolor="rgb(18,18,18)", gridcolor="gray", showbackground=True),
            zaxis=dict(backgroundcolor="rgb(18,18,18)", gridcolor="gray", showbackground=True),
        ),
        margin=dict(l=0,r=0,b=0,t=30),
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="white")
    )

    # Add subtle marker outlines
    fig3d.update_traces(marker=dict(line=dict(width=1,color='DarkSlateGrey')))

    # Render 3D plot
    st.plotly_chart(fig3d, use_container_width=True)
else:
    st.info("No stock data available at the moment.")

# ---------- LEADERBOARD ----------
st.subheader("🏆 Live Leaderboard")
if leaderboard:
    ldf = pd.DataFrame(leaderboard).sort_values("value", ascending=False).reset_index(drop=True)
    ldf.index += 1
    def highlight_top3(row):
        if row.name == 1: return ['background-color: gold; font-weight:bold'] * len(row)
        elif row.name == 2: return ['background-color: silver; font-weight:bold'] * len(row)
        elif row.name == 3: return ['background-color: #cd7f32; font-weight:bold'] * len(row)
        else: return [''] * len(row)
    st.dataframe(ldf.style.apply(highlight_top3, axis=1), use_container_width=True, hide_index=False)
else:
    st.info("No teams yet. Waiting for participants to trade...")

# ---------- MARKET NEWS ----------
st.subheader("📰 Market News")
if news and "articles" in news and news["articles"]:
    for article in news["articles"]:
        st.markdown(f"""
        <div style='background-color:rgba(18,18,18,0.8); padding:10px; margin-bottom:8px; border-radius:8px; color:#e0e0e0;'>
            <b><a href="{article['url']}" target="_blank">{article['title']}</a></b><br>
            <span style="color:gray; font-size:12px;">{datetime.now().strftime('%H:%M:%S')}</span>
        </div>
        """, unsafe_allow_html=True)
else:
    st.info("No news available right now.")

