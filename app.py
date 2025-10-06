import streamlit as st
import random
import pandas as pd
import time
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# ---------- PAGE CONFIG ----------
st.set_page_config(page_title="📈 Virtual Stock Market Demo", layout="wide")

# ---------- DEMO SETTINGS ----------
ROUND_DURATION = 30 * 60  # 30 minutes simulated
SPEED_FACTOR = 30  # 1 virtual minute = 2 real seconds (round lasts ~5 minutes)
REFRESH_INTERVAL = 1000  # in ms

# ---------- AUTO REFRESH ----------
st_autorefresh(interval=REFRESH_INTERVAL, key="refresh_key")

# ---------- INITIAL DATA ----------
DEMO_TEAMS = [
    "Alpha Traders", "Bear Bulls", "Quantum Investors", "Pallotti Pioneers",
    "Money Masters", "AI Financers", "Profit Prophets", "Stock Sharks",
    "Wall Street Ninjas", "Bullionaires"
]

STOCKS = {
    "INFY": {"name": "Infosys", "price": 1500.0},
    "TCS": {"name": "TCS", "price": 3600.0},
    "HDFCBANK": {"name": "HDFC Bank", "price": 1600.0},
    "RELIANCE": {"name": "Reliance", "price": 2500.0},
    "ITC": {"name": "ITC", "price": 450.0},
}

# ---------- SESSION STATE INIT ----------
if "start_time" not in st.session_state:
    st.session_state.start_time = time.time()
if "teams" not in st.session_state:
    st.session_state.teams = {
        team: {"cash": 100000, "holdings": {}} for team in DEMO_TEAMS
    }
if "stocks" not in st.session_state:
    st.session_state.stocks = STOCKS.copy()

# ---------- SIMULATE STOCK PRICE UPDATES ----------
def update_stock_prices():
    for symbol in st.session_state.stocks:
        change_percent = random.uniform(-0.5, 0.5)
        st.session_state.stocks[symbol]["price"] *= (1 + change_percent / 100)
        st.session_state.stocks[symbol]["price"] = round(st.session_state.stocks[symbol]["price"], 2)

# ---------- SIMULATE RANDOM TRADES ----------
def simulate_trades():
    for team in DEMO_TEAMS:
        if random.random() < 0.3:  # 30% chance of trade per refresh
            stock = random.choice(list(st.session_state.stocks.keys()))
            price = st.session_state.stocks[stock]["price"]
            quantity = random.randint(1, 10)
            action = random.choice(["buy", "sell"])
            portfolio = st.session_state.teams[team]

            if action == "buy" and portfolio["cash"] >= price * quantity:
                portfolio["cash"] -= price * quantity
                portfolio["holdings"][stock] = portfolio["holdings"].get(stock, 0) + quantity

            elif action == "sell" and stock in portfolio["holdings"] and portfolio["holdings"][stock] > 0:
                sell_qty = min(quantity, portfolio["holdings"][stock])
                portfolio["cash"] += price * sell_qty
                portfolio["holdings"][stock] -= sell_qty
                if portfolio["holdings"][stock] == 0:
                    del portfolio["holdings"][stock]

# ---------- TIMER ----------
elapsed = time.time() - st.session_state.start_time
remaining = ROUND_DURATION - elapsed * SPEED_FACTOR

# ---------- DEMO MODE AUTO-UPDATES ----------
update_stock_prices()
simulate_trades()

# ---------- HEADER ----------
st.title("📊 Virtual Stock Market Demo (Offline Mode)")
st.write("Simulated 30-minute trading round (runs for ~5 minutes in real time)")

# ---------- TIMER DISPLAY ----------
minutes = max(int(remaining // 60), 0)
seconds = max(int(remaining % 60), 0)
st.markdown(f"### ⏱️ Time Remaining: {minutes:02d}:{seconds:02d}")

if remaining <= 0:
    st.success("✅ Demo Round Completed!")
    st.stop()

# ---------- STOCK MARKET DISPLAY ----------
st.subheader("📈 Live Stock Prices")
df_stocks = pd.DataFrame([
    {"Symbol": s, "Company": d["name"], "Price (₹)": round(d["price"], 2)}
    for s, d in st.session_state.stocks.items()
])
st.dataframe(df_stocks, use_container_width=True)

# ---------- PORTFOLIOS DISPLAY (ALL TEAMS) ----------
st.subheader("💼 Portfolios (All Demo Teams)")
for team in DEMO_TEAMS:
    portfolio = st.session_state.teams[team]
    st.markdown(f"**Team: {team}** | Cash: ₹{portfolio['cash']:.2f}")
    if portfolio["holdings"]:
        df_holdings = pd.DataFrame.from_dict(portfolio["holdings"], orient="index", columns=["Quantity"])
        st.dataframe(df_holdings, use_container_width=True)
    else:
        st.info(f"Team {team} has no holdings yet.")

# ---------- LEADERBOARD ----------
st.subheader("🏆 Leaderboard")
leaderboard = []
for team, portfolio in st.session_state.teams.items():
    total_value = portfolio["cash"]
    for stock, qty in portfolio["holdings"].items():
        total_value += qty * st.session_state.stocks[stock]["price"]
    leaderboard.append({"Team": team, "Total Value (₹)": round(total_value, 2)})

df_leaderboard = pd.DataFrame(leaderboard).sort_values("Total Value (₹)", ascending=False)
st.dataframe(df_leaderboard, use_container_width=True)
