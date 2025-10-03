import streamlit as st
import requests
import os
import pandas as pd
import plotly.express as px
import time
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="📈 Virtual Stock Market", layout="wide")

# ---- Backend URL ----
BACKEND = os.environ.get("BACKEND", "https://virtual-stock-market-7mxp.onrender.com")

# ---- Session State ----
if "team" not in st.session_state:
    st.session_state.team = None
if "round_start" not in st.session_state:
    st.session_state.round_start = None
if "buy_clicked" not in st.session_state:
    st.session_state.buy_clicked = False
if "sell_clicked" not in st.session_state:
    st.session_state.sell_clicked = False

ROUND_DURATION = 15 * 60  # 15 minutes

# ---- Utility Functions ----
def fetch_stocks():
    return requests.get(f"{BACKEND}/stocks", timeout=6).json()

def fetch_leaderboard():
    return requests.get(f"{BACKEND}/leaderboard", timeout=6).json()

def fetch_news():
    return requests.get(f"{BACKEND}/news", timeout=6).json()

def fetch_portfolio(team):
    r = requests.get(f"{BACKEND}/portfolio/{team}", timeout=6)
    return r.json() if r.status_code == 200 else None

def init_team(team):
    r = requests.post(f"{BACKEND}/init_team", json={"team": team})
    return r.json() if r.status_code == 200 else None

def trade(team, symbol, qty):
    r = requests.post(f"{BACKEND}/trade", json={"team": team, "symbol": symbol, "qty": qty})
    return r.json() if r.status_code == 200 else None

# ---- Auto-refresh timer ----
st_autorefresh(interval=1000, key="timer_refresh")

# ---- Team Registration ----
if st.session_state.team is None:
    st.title("👥 Register or Login Your Team")
    team_name_input = st.text_input("Enter Team Name")
    if st.button("Continue"):
        if team_name_input.strip() == "":
            st.warning("Please enter a valid team name.")
        else:
            res = init_team(team_name_input)
            if res:
                st.success(f"Team '{team_name_input}' created with ₹{res['cash']:.2f}")
                st.session_state.team = team_name_input
                st.session_state.round_start = time.time()
            else:
                port = fetch_portfolio(team_name_input)
                if port:
                    st.info(f"Team '{team_name_input}' already exists. Logged in successfully.")
                    st.session_state.team = team_name_input
                    st.session_state.round_start = time.time()
                else:
                    st.error("Error occurred. Try another team name.")
    st.stop()  # Wait until team is registered

team_name = st.session_state.team

# ---- Countdown Timer ----
if st.session_state.round_start is None:
    st.session_state.round_start = time.time()

elapsed = time.time() - st.session_state.round_start
remaining = ROUND_DURATION - elapsed

if remaining <= 0:
    st.warning("⏹️ Trading round has ended!")
    trading_allowed = False
else:
    mins, secs = divmod(int(remaining), 60)
    st.info(f"⏱️ Time Remaining: {mins:02d}:{secs:02d}")
    trading_allowed = True

# ---- Fetch Data ----
try:
    stocks = fetch_stocks()
    leaderboard = fetch_leaderboard()
    news = fetch_news()
except requests.exceptions.RequestException as e:
    st.error(f"❌ Could not connect to backend. Check BACKEND URL. Error: {e}")
    st.stop()

# ---- Portfolio Section ----
portfolio = fetch_portfolio(team_name)
if portfolio:
    st.subheader(f"📊 Portfolio for {team_name}")
    st.metric("Total Portfolio Value", f"₹{portfolio['portfolio_value']:.2f}")
    st.write(f"💵 **Cash:** ₹{portfolio['cash']:.2f}")

    if portfolio["holdings"]:
        holdings_df = pd.DataFrame.from_dict(portfolio["holdings"], orient="index")
        st.dataframe(holdings_df, use_container_width=True)
    else:
        st.info("No holdings yet. Buy some stocks!")

    # ---- Buy/Sell Form ----
    st.subheader("💸 Place Trade")
    col1, col2, col3, col4 = st.columns([2,2,1,1])
    with col1:
        selected_stock = st.selectbox("Select Stock", [s["symbol"] for s in stocks])
    with col2:
        qty = st.number_input("Quantity", min_value=1, step=1, value=1)

    with col3:
        if st.button("Buy"):
            st.session_state.buy_clicked = True
    with col4:
        if st.button("Sell"):
            st.session_state.sell_clicked = True

    # Process Buy
    if st.session_state.buy_clicked:
        if trading_allowed:
            res = trade(team_name, selected_stock, int(qty))
            if res:
                st.success(f"✅ Bought {qty} of {selected_stock}")
            else:
                st.error("Failed to buy. Check cash balance.")
        else:
            st.warning("Trading round has ended!")
        st.session_state.buy_clicked = False

    # Process Sell
    if st.session_state.sell_clicked:
        if trading_allowed:
            res = trade(team_name, selected_stock, -int(qty))
            if res:
                st.success(f"✅ Sold {qty} of {selected_stock}")
            else:
                st.error("Failed to sell. Check holdings.")
        else:
            st.warning("Trading round has ended!")
        st.session_state.sell_clicked = False
else:
    st.warning("Portfolio not found. Try creating a new team.")

# ---- Stocks Section ----
st.subheader("💹 Live Stock Prices")
df = pd.DataFrame(stocks)
if not df.empty:
    df["Trend"] = df["pct_change"].apply(lambda x: "🟢" if x >=0 else "🔴")
    st.dataframe(df[["symbol","name","price","pct_change","Trend"]].rename(columns={
        "symbol":"Symbol","name":"Company","price":"Price","pct_change":"% Change"
    }), use_container_width=True)

    # ---- 3D Scatter Chart ----
    st.subheader("📊 Stocks 3D Scatter Chart")
    df['volume'] = [i*1000 for i in range(1, len(df)+1)]
    fig3d = px.scatter_3d(
        df, x='price', y='pct_change', z='volume',
        color='Trend', hover_name='name', size='price', size_max=20,
        title='Stock Price vs % Change vs Volume'
    )
    st.plotly_chart(fig3d, use_container_width=True)
else:
    st.warning("No stock data available.")

# ---- Leaderboard ----
st.subheader("🏆 Leaderboard")
if leaderboard:
    ldf = pd.DataFrame(leaderboard)
    st.dataframe(ldf, use_container_width=True)

    # ---- Portfolio Surface Chart ----
    st.subheader("📈 Portfolio Value Surface Chart")
    teams = [t['team'] for t in leaderboard]
    stock_symbols = [s['symbol'] for s in stocks]
    z_matrix = []
    for t in teams:
        port = fetch_portfolio(t)
        row = []
        for s in stock_symbols:
            qty = port['holdings'].get(s, {}).get('qty',0)
            price = port['holdings'].get(s, {}).get('price',0)
            row.append(qty*price)
        z_matrix.append(row)
    fig_surface = px.imshow(
        z_matrix,
        labels=dict(x="Stocks", y="Teams", color="Value"),
        x=stock_symbols,
        y=teams,
        color_continuous_scale='Viridis',
        text_auto=True
    )
    st.plotly_chart(fig_surface, use_container_width=True)
else:
    st.info("No teams yet.")

# ---- News ----
st.subheader("📰 Market News")
if news.get("articles"):
    for article in news["articles"]:
        st.markdown(f"🔗 [{article['title']}]({article['url']})")
else:
    st.info("No news available right now.")
