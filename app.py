import streamlit as st
import requests
import json
import os
import pandas as pd
import plotly.express as px
import time

# ---------- PAGE CONFIG ----------
st.set_page_config(page_title="📈 Virtual Stock Market", layout="wide")

# ---------- BACKEND URL ----------
BACKEND = os.environ.get("BACKEND", "https://game-of-trades-vblh.onrender.com")

# ---------- ROUND DURATION ----------
ROUND_DURATION = 30 * 60  # 30 minutes

# ---------- SESSION STATE ----------
if "team" not in st.session_state:
    st.session_state.team = None
if "round_start" not in st.session_state:
    st.session_state.round_start = time.time()

# ---------- UTILITY FUNCTIONS ----------
def fetch_stocks():
    r = requests.get(f"{BACKEND}/stocks", timeout=6)
    return r.json() if r.status_code == 200 else []

def fetch_leaderboard():
    r = requests.get(f"{BACKEND}/leaderboard", timeout=6)
    return r.json() if r.status_code == 200 else []

def fetch_news():
    r = requests.get(f"{BACKEND}/news", timeout=6)
    return r.json() if r.status_code == 200 else {}

def fetch_portfolio(team):
    r = requests.get(f"{BACKEND}/portfolio/{team}", timeout=6)
    return r.json() if r.status_code == 200 else None

def init_team(team):
    r = requests.post(f"{BACKEND}/init_team", json={"team": team})
    return r.json() if r.status_code == 200 else None

def trade(team, symbol, qty):
    r = requests.post(f"{BACKEND}/trade", json={"team": team, "symbol": symbol, "qty": qty})
    return r.json() if r.status_code == 200 else None

# ---------- TIMER FUNCTION ----------
def get_remaining_time():
    elapsed = time.time() - st.session_state.round_start
    remaining = max(0, ROUND_DURATION - elapsed)
    mins, secs = divmod(int(remaining), 60)
    return mins, secs, remaining

# ---------- TEAM LOGIN / REGISTRATION ----------
if st.session_state.team is None:
    st.title("👥 Register or Login Your Team")
    team_name_input = st.text_input("Enter Team Name")

    if st.button("Continue"):
        if team_name_input.strip() == "":
            st.warning("Please enter a valid team name.")
        else:
            res = init_team(team_name_input)
            if res:
                st.success(f"✅ Team '{team_name_input}' created with ₹{res['cash']:.2f}")
                st.session_state.team = team_name_input
                st.session_state.round_start = time.time()
            else:
                port = fetch_portfolio(team_name_input)
                if port:
                    st.info(f"✅ Team '{team_name_input}' logged in successfully.")
                    st.session_state.team = team_name_input
                    st.session_state.round_start = time.time()
                else:
                    st.error("❌ Error occurred. Try another team name.")
    st.stop()

# ---------- DASHBOARD ----------
team_name = st.session_state.team

# ---- TIMER ----
mins, secs, remaining = get_remaining_time()
placeholder_timer = st.empty()

if remaining > 0:
    with placeholder_timer.container():
        st.info(f"⏱️ **Time Remaining: {mins:02d}:{secs:02d}**")
else:
    st.warning("⏹️ Trading round has ended!")

# ---- AUTO REFRESH EVERY 5 SECONDS (for live updates) ----
st_autorefresh = st.experimental_data_editor  # dummy for no import errors
st.experimental_rerun = None  # disabled flicker-prone rerun
st_autorefresh = st.empty()
time.sleep(1)
st.session_state.refresh_trigger = time.time()

# ---- FETCH DATA ----
try:
    stocks = fetch_stocks()
    leaderboard = fetch_leaderboard()
    news = fetch_news()
except requests.exceptions.RequestException:
    st.error("❌ Could not connect to backend. Check BACKEND URL.")
    st.stop()

# ---------- PORTFOLIO ----------
portfolio = fetch_portfolio(team_name)
if portfolio:
    st.subheader(f"📊 Portfolio — {team_name}")
    st.metric("Total Portfolio Value", f"₹{portfolio['portfolio_value']:.2f}")
    st.write(f"💵 **Cash:** ₹{portfolio['cash']:.2f}")

    if portfolio["holdings"]:
        holdings_df = pd.DataFrame.from_dict(portfolio["holdings"], orient="index")
        holdings_df.index.name = "Stock"
        st.dataframe(holdings_df, use_container_width=True)
    else:
        st.info("No holdings yet. Buy some stocks!")

    # ---- TRADE SECTION ----
    st.subheader("💸 Trade Stocks")
    col1, col2, col3, col4 = st.columns([2,2,1,1])
    with col1:
        selected_stock = st.selectbox("Select Stock", [s["symbol"] for s in stocks])
    with col2:
        qty = st.number_input("Quantity", min_value=1, step=1, value=1)
    with col3:
        if st.button("Buy"):
            if remaining > 0:
                res = trade(team_name, selected_stock, int(qty))
                if res and res.get("success"):
                    st.success(f"✅ Bought {qty} of {selected_stock}")
                else:
                    st.error("Failed to buy — check your cash balance.")
            else:
                st.warning("⏹️ Trading round has ended!")
    with col4:
        if st.button("Sell"):
            if remaining > 0:
                res = trade(team_name, selected_stock, -int(qty))
                if res and res.get("success"):
                    st.success(f"✅ Sold {qty} of {selected_stock}")
                else:
                    st.error("Failed to sell — check your holdings.")
            else:
                st.warning("⏹️ Trading round has ended!")
else:
    st.warning("Portfolio not found. Try creating a new team.")

# ---------- STOCKS ----------
st.subheader("💹 Live Stock Prices")
if stocks:
    df = pd.DataFrame(stocks)
    df["Trend"] = df["pct_change"].apply(lambda x: "🟢" if x >= 0 else "🔴")
    st.dataframe(df[["symbol", "name", "price", "pct_change", "Trend"]].rename(columns={
        "symbol": "Symbol",
        "name": "Company",
        "price": "Price",
        "pct_change": "% Change"
    }), use_container_width=True)

    # ---- 3D Scatter ----
    st.subheader("📊 Stock Performance (3D View)")
    df['volume'] = [i * 1000 for i in range(1, len(df)+1)]
    fig3d = px.scatter_3d(
        df,
        x='price', y='pct_change', z='volume',
        color='Trend',
        hover_name='name',
        size='price',
        size_max=20,
        title='Stock Price vs % Change vs Volume'
    )
    st.plotly_chart(fig3d, use_container_width=True)
else:
    st.warning("No stock data available.")

# ---------- LEADERBOARD ----------
st.subheader("🏆 Leaderboard")
if leaderboard:
    ldf = pd.DataFrame(leaderboard)
    st.dataframe(ldf, use_container_width=True)
else:
    st.info("No teams yet.")

# ---------- NEWS ----------
st.subheader("📰 Market News")
if news.get("articles"):
    for article in news["articles"]:
        st.markdown(f"🔗 [{article['title']}]({article['url']})")
else:
    st.info("No news available right now.")

