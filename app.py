import streamlit as st
import requests
import os
import pandas as pd
import plotly.express as px
from datetime import datetime
import time

# ---------- PAGE CONFIG ----------
st.set_page_config(page_title="📈 Virtual Stock Market", layout="wide")

# ---------- BACKEND URL ----------
BACKEND = os.environ.get("BACKEND", "https://game-of-trades-vblh.onrender.com")

# ---------- SESSION STATE ----------
for key in ["team", "round_start", "paused", "pause_time", "buy_click", "sell_click"]:
    if key not in st.session_state:
        st.session_state[key] = False if key in ["paused", "buy_click", "sell_click"] else None

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
    except:
        return None
    return None

def trade(team, symbol, qty):
    try:
        r = requests.post(f"{BACKEND}/trade", json={"team": team, "symbol": symbol, "qty": qty})
        if r.status_code == 200: return r.json()
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
                st.experimental_rerun()
            else:
                port = fetch_portfolio(team_input)
                if port:
                    st.session_state.team = team_input
                    st.info(f"Team '{team_input}' logged in successfully.")
                    st.experimental_rerun()
                else:
                    st.error("Error occurred. Try another team name.")
    st.stop()

team_name = st.session_state.team

# ---------- ORGANIZER CONTROLS ----------
st.sidebar.subheader("🔐 Organizer Access")
password = st.sidebar.text_input("Enter Organizer Password", type="password")
is_admin = password == "admin123"

if is_admin:
    with st.expander("⚙️ Organizer Controls"):
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("▶️ Start Round"):
                st.session_state.round_start = time.time()
                st.session_state.paused = False
        with col2:
            if st.button("⏸ Pause Round") and st.session_state.round_start and not st.session_state.paused:
                st.session_state.paused = True
                st.session_state.pause_time = time.time()
        with col3:
            if st.button("🔄 Resume Round") and st.session_state.paused:
                paused_duration = time.time() - st.session_state.pause_time
                st.session_state.round_start += paused_duration
                st.session_state.paused = False
        if st.button("♻️ Reset Round"):
            st.session_state.round_start = None
            st.session_state.paused = False
            st.session_state.pause_time = 0

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

# ---------- PLACEHOLDERS ----------
portfolio_placeholder = st.empty()
stocks_placeholder = st.empty()
leaderboard_placeholder = st.empty()
news_placeholder = st.empty()

# ---------- FUNCTION TO UPDATE ALL DATA ----------
def update_data():
    stocks = fetch_stocks() or []
    leaderboard = fetch_leaderboard() or []
    news = fetch_news() or {}
    portfolio = fetch_portfolio(team_name) or {}

    # PORTFOLIO
    with portfolio_placeholder:
        st.subheader("💼 Portfolio")
        if portfolio:
            st.metric("Available Cash", f"₹{portfolio['cash']:.2f}")
            if portfolio.get("holdings"):
                holdings_df = pd.DataFrame.from_dict(portfolio["holdings"], orient="index")
                st.dataframe(holdings_df, use_container_width=True)
            else:
                st.info("No holdings yet. Buy some stocks!")

    # STOCKS
    with stocks_placeholder:
        st.subheader("📊 Live Stock Prices")
        if stocks:
            df = pd.DataFrame(stocks)
            df["Trend"] = df["pct_change"].apply(lambda x: "🟢" if x >= 0 else "🔴")
            st.dataframe(df[["symbol","name","price","pct_change","Trend"]]
                         .rename(columns={"symbol":"Symbol","name":"Company","price":"Price","pct_change":"% Change"}), use_container_width=True)
            # 3D chart
            df['volume'] = [i*1000 for i in range(1,len(df)+1)]
            fig3d = px.scatter_3d(df, x='price', y='pct_change', z='volume', color='Trend',
                                  hover_name='name', size='price', size_max=18, opacity=0.8)
            fig3d.update_traces(marker=dict(line=dict(width=1,color='DarkSlateGrey')))
            fig3d.update_layout(scene=dict(xaxis_title="Price", yaxis_title="% Change", zaxis_title="Volume"), margin=dict(l=0,r=0,b=0,t=30))
            st.plotly_chart(fig3d, use_container_width=True)

    # LEADERBOARD
    with leaderboard_placeholder:
        st.subheader("🏆 Live Leaderboard")
        if leaderboard:
            ldf = pd.DataFrame(leaderboard).sort_values("value", ascending=False).reset_index(drop=True)
            ldf.index += 1
            def highlight_top3(row):
                if row.name==1: return ['background-color: gold; font-weight:bold']*len(row)
                elif row.name==2: return ['background-color: silver; font-weight:bold']*len(row)
                elif row.name==3: return ['background-color: #cd7f32; font-weight:bold']*len(row)
                else: return ['']*len(row)
            st.dataframe(ldf.style.apply(highlight_top3, axis=1), use_container_width=True, hide_index=False)
        else:
            st.info("No teams yet.")

    # NEWS
    with news_placeholder:
        st.subheader("📰 Market News")
        if news.get("articles"):
            for article in news["articles"]:
                st.markdown(f"""
                <div style='background-color:#fdfdfd;padding:10px;margin-bottom:8px;border-radius:8px;
                box-shadow:0 2px 6px rgba(0,0,0,0.1)'>
                    <b><a href="{article['url']}" target="_blank">{article['title']}</a></b><br>
                    <span style="color:gray;font-size:12px;">{datetime.now().strftime('%H:%M:%S')}</span>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("No news available right now.")

    return stocks

# ---------- TRADE SECTION ----------
st.subheader("💸 Place Trade")
trade_col1, trade_col2, trade_col3, trade_col4 = st.columns([2,2,1,1])
with trade_col1:
    selected_stock = st.selectbox("Select Stock", [])
with trade_col2:
    qty = st.number_input("Quantity", min_value=1, step=1, value=1)
with trade_col3:
    if st.button("Buy") and trading_allowed:
        res = trade(team_name, selected_stock, int(qty))
        if res: st.success(f"✅ Bought {qty} of {selected_stock}")
        else: st.error("Failed to buy. Check cash balance.")
with trade_col4:
    if st.button("Sell") and trading_allowed:
        res = trade(team_name, selected_stock, -int(qty))
        if res: st.success(f"✅ Sold {qty} of {selected_stock}")
        else: st.error("Failed to sell. Check holdings.")

# ---------- INITIAL DATA LOAD ----------
stocks_data = update_data()

# ---------- LIGHTWEIGHT REFRESH ----------
# Only update every 5 seconds without rerunning everything
st_autorefresh(interval=5000, key="data_refresh")
