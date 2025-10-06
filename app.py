import streamlit as st
import pandas as pd
import plotly.express as px
import time
import random
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# ---------- PAGE CONFIG ----------
st.set_page_config(page_title="📈 Virtual Stock Market Demo", layout="wide")

# ---------- CUSTOM BACKGROUND ----------
st.markdown("""
    <style>
    .stApp { background-color: #f7f7f5 !important; }
    </style>
""", unsafe_allow_html=True)

# ---------- SESSION STATE ----------
for key in ["round_start", "paused", "pause_time", "demo_mode", "last_demo_trade", "stocks", "teams"]:
    if key not in st.session_state:
        if key in ["paused", "demo_mode"]:
            st.session_state[key] = False
        elif key == "last_demo_trade":
            st.session_state[key] = time.time()
        else:
            st.session_state[key] = None if key in ["round_start"] else {}

# ---------- DEMO CONFIG ----------
ROUND_DURATION = 30 * 60   # 30 minutes simulated
DEMO_SPEED = 0.2           # seconds between trades
SPEED_FACTOR = 30          # 30 min → ~5 real min demo
DEMO_TEAMS = ["Alpha","Beta","Gamma","Delta","Epsilon","Zeta","Eta","Theta","Iota","Kappa"]
NUM_STOCKS = 8

# ---------- INIT STOCKS ----------
if not st.session_state.stocks:
    st.session_state.stocks = []
    for i in range(NUM_STOCKS):
        st.session_state.stocks.append({
            "symbol": f"S{i+1}",
            "name": f"Company {chr(65+i)}",
            "price": round(random.uniform(50, 500), 2),
            "pct_change": round(random.uniform(-5, 5), 2)
        })

# ---------- INIT TEAMS ----------
if not st.session_state.teams:
    for team in DEMO_TEAMS:
        st.session_state.teams[team] = {
            "cash": 10000,
            "holdings": {}
        }

# ---------- START ROUND ----------
if st.button("▶️ Start Demo Round"):
    st.session_state.round_start = time.time()
    st.session_state.paused = False
    st.session_state.demo_mode = True

# ---------- TIMER ----------
st_autorefresh(interval=800, key="timer_refresh")
timer_placeholder = st.empty()
trading_allowed = False

if st.session_state.round_start:
    elapsed = (time.time() - st.session_state.round_start)
    elapsed /= SPEED_FACTOR  # speed up demo
    remaining = max(0, ROUND_DURATION - elapsed)
    mins, secs = divmod(int(remaining), 60)

    if remaining <= 0:
        trading_allowed = False
        timer_placeholder.markdown("<h2 style='text-align:center; color:red;'>⏹️ Trading round has ended!</h2>", unsafe_allow_html=True)
    else:
        trading_allowed = True
        color = "green" if remaining > 60 else "orange" if remaining > 10 else "red"
        timer_placeholder.markdown(f"<h1 style='text-align:center; color:{color};'>⏱️ {mins:02d}:{secs:02d}</h1>", unsafe_allow_html=True)
else:
    timer_placeholder.markdown("<h3 style='text-align:center; color:orange;'>⌛ Waiting to start demo...</h3>", unsafe_allow_html=True)

# ---------- SMART DEMO AUTO-TRADING ----------
if st.session_state.demo_mode and trading_allowed:
    if time.time() - st.session_state.last_demo_trade > DEMO_SPEED:
        st.session_state.last_demo_trade = time.time()
        team = random.choice(DEMO_TEAMS)
        stock = random.choice(st.session_state.stocks)
        qty = random.randint(1, 5)
        portfolio = st.session_state.teams[team]
        action = None
        if stock["pct_change"] >= 0:
            if portfolio["cash"] >= stock["price"] * qty:
                action = 1
            else:
                qty = max(1, int(portfolio["cash"] // stock["price"]))
                if qty > 0: action = 1
        else:
            holding_qty = portfolio["holdings"].get(stock["symbol"], 0)
            if holding_qty > 0:
                qty = min(qty, holding_qty)
                action = -1
        if action:
            if action == 1:
                portfolio["cash"] -= stock["price"] * qty
                portfolio["holdings"][stock["symbol"]] = portfolio["holdings"].get(stock["symbol"], 0) + qty
            else:
                portfolio["cash"] += stock["price"] * qty
                portfolio["holdings"][stock["symbol"]] -= qty
                if portfolio["holdings"][stock["symbol"]] == 0:
                    del portfolio["holdings"][stock["symbol"]]
        stock["price"] = round(stock["price"] * (1 + random.uniform(-0.02, 0.02)), 2)
        stock["pct_change"] = round(random.uniform(-5, 5), 2)

# ---------- STOCKS DISPLAY ----------
st.subheader("📊 Live Stock Prices")
df = pd.DataFrame(st.session_state.stocks)
df["Trend"] = df["pct_change"].apply(lambda x: "🟢" if x >= 0 else "🔴")
df_stocks = df[["symbol", "name", "price", "pct_change", "Trend"]].rename(
    columns={"symbol": "Symbol", "name": "Company", "price": "Price", "pct_change": "% Change"}
)
st.dataframe(df_stocks, use_container_width=True)

# ---------- DYNAMIC MARKET NEWS ----------
st.subheader("🗞️ Market News (Dynamic Demo)")
news_placeholder = st.empty()

def generate_stock_news():
    stock = random.choice(st.session_state.stocks)
    change = random.choice(["rises", "drops", "surges", "plummets", "edges up", "declines slightly"])
    reason = random.choice([
        "after strong earnings report",
        "due to investor optimism",
        "amid global market pressure",
        "following government policy changes",
        "as analysts upgrade outlook",
        "after product launch success",
        "amid sector volatility",
        "on reports of major acquisition",
        "after positive quarterly results",
        "as investors shift to safe assets"
    ])
    return f"{stock['name']} {change} {random.uniform(1,5):.1f}% {reason}."

# Generate 3 headlines
demo_news = [generate_stock_news() for _ in range(3)]
for i, headline in enumerate(demo_news, 1):
    st.markdown(f"**{i}. {headline}**  \n<span style='color:gray;font-size:12px;'>{datetime.now().strftime('%H:%M:%S')}</span>", unsafe_allow_html=True)

# ---------- 3D PRICE CHART ----------
df['volume'] = [i * 1000 for i in range(1, len(df) + 1)]
fig3d = px.scatter_3d(
    df, x='price', y='pct_change', z='volume', color='Trend',
    hover_name='name', size='price', size_max=18, opacity=0.8
)
fig3d.update_traces(marker=dict(line=dict(width=1, color='DarkSlateGrey')))
fig3d.update_layout(scene=dict(xaxis_title="Price", yaxis_title="% Change", zaxis_title="Volume"),
                    margin=dict(l=0, r=0, b=0, t=30))
st.plotly_chart(fig3d, use_container_width=True)

# ---------- PORTFOLIOS DISPLAY ----------
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
for team, data in st.session_state.teams.items():
    total_value = data["cash"] + sum(
        [next(s["price"] for s in st.session_state.stocks if s["symbol"] == sym) * qty for sym, qty in data["holdings"].items()]
    )
    leaderboard.append({"team": team, "value": total_value})
ldf = pd.DataFrame(leaderboard).sort_values("value", ascending=False).reset_index(drop=True)
ldf.index += 1

def highlight_top3(row):
    if row.name == 1: return ['background-color: gold; font-weight:bold'] * len(row)
    elif row.name == 2: return ['background-color: silver; font-weight:bold'] * len(row)
    elif row.name == 3: return ['background-color: #cd7f32; font-weight:bold'] * len(row)
    else: return [''] * len(row)

st.dataframe(ldf.style.apply(highlight_top3, axis=1), use_container_width=True, hide_index=False)
