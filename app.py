# app.py - Streamlit Virtual Stock Market with Offline Safe Mode (Option B)
import streamlit as st
import requests
import os
import pandas as pd
import plotly.express as px
import time
import random
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# ---------- PAGE CONFIG ----------
st.set_page_config(page_title="📈 Virtual Stock Market (Safe Mode)", layout="wide")

# ---------- THEME (kept minimal for clarity) ----------
st.markdown("""
<style>
.stApp { background-color: #0b0f14; color: #e0e0e0; }
h1, h2, h3, h4 { color: #00ffff; text-shadow: 1px 1px 3px #000; }
div.stButton > button:first-child { background-color:#121212; color:#00ffff; border-radius:8px; border:1px solid #00ffff; }
</style>
""", unsafe_allow_html=True)

# ---------- BACKEND ----------
BACKEND = os.environ.get("BACKEND", "https://game-of-trades-vblh.onrender.com")

# ---------- CONSTANTS ----------
ROUND_DURATION = 30 * 60  # 30 minutes
OFFLINE_SEED_STOCKS = [
    {"symbol":"AAPL","name":"Apple Inc.","price":175.00},
    {"symbol":"GOOGL","name":"Alphabet","price":135.00},
    {"symbol":"MSFT","name":"Microsoft","price":310.00},
    {"symbol":"TSLA","name":"Tesla","price":210.00},
    {"symbol":"INFY","name":"Infosys","price":18.50},
]

# ---------- SESSION STATE INIT ----------
if "team" not in st.session_state: st.session_state.team = None
for key in ["round_start","paused","pause_time","buy_click","sell_click","backend_online","sim_stocks","local_portfolios","trade_queue"]:
    if key not in st.session_state:
        # sensible defaults
        if key == "paused": st.session_state[key] = False
        elif key == "backend_online": st.session_state[key] = True
        elif key == "sim_stocks":
            # seed simulated stocks
            sim = []
            for s in OFFLINE_SEED_STOCKS:
                sim.append({
                    "symbol": s["symbol"],
                    "name": s["name"],
                    "price": s["price"],
                    "pct_change": 0.0,
                    "last_update": time.time()
                })
            st.session_state.sim_stocks = sim
        elif key == "local_portfolios": st.session_state.local_portfolios = {}
        elif key == "trade_queue": st.session_state.trade_queue = []
        else:
            st.session_state[key] = None

# ---------- UTILITY ----------
def safe_get(url, timeout=4):
    try:
        r = requests.get(url, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None

def post_json(url, json_data, timeout=6):
    try:
        r = requests.post(url, json=json_data, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None

def check_backend():
    """Quick check if backend stocks endpoint responds."""
    res = safe_get(f"{BACKEND}/stocks")
    st.session_state.backend_online = bool(res)
    return res

def fetch_stocks_online():
    return safe_get(f"{BACKEND}/stocks")

def fetch_leaderboard_online():
    return safe_get(f"{BACKEND}/leaderboard")

def fetch_news_online():
    return safe_get(f"{BACKEND}/news")

def fetch_portfolio_online(team):
    return safe_get(f"{BACKEND}/portfolio/{team}")

def init_team_online(team):
    return post_json(f"{BACKEND}/init_team", {"team": team})

def trade_online(team, symbol, qty):
    return post_json(f"{BACKEND}/trade", {"team": team, "symbol": symbol, "qty": qty})

# ---------- SIMULATION HELPERS ----------
def sim_step_update():
    """Update simulated stock prices via small random walk."""
    for s in st.session_state.sim_stocks:
        # small percent move
        pct = random.uniform(-0.8, 0.8)
        old = s["price"]
        new = max(0.01, round(old * (1 + pct/100.0), 2))
        s["pct_change"] = round(((new - old) / old) * 100, 2)
        s["price"] = new
        s["last_update"] = time.time()

def get_sim_stocks():
    # perform update then return snapshot list
    sim_step_update()
    # ensure a consistent structure like backend
    return [{"symbol": s["symbol"], "name": s["name"], "price": s["price"], "pct_change": s["pct_change"]} for s in st.session_state.sim_stocks]

# ---------- FLUSH QUEUE ----------
def flush_trade_queue():
    """Try to replay queued trades to backend. Remove successfully applied ones."""
    if not st.session_state.backend_online:
        return
    new_queue = []
    for item in st.session_state.trade_queue:
        res = trade_online(item["team"], item["symbol"], item["qty"])
        if res:
            # optionally could verify res content; report to admin via st.info after flush
            st.success(f"Synced queued trade: {item['team']} {item['symbol']} {item['qty']}")
        else:
            new_queue.append(item)
    st.session_state.trade_queue = new_queue

# ---------- TEAM REGISTRATION ----------
if st.session_state.team is None:
    st.title("👥 Register or Login Your Team")
    team_input = st.text_input("Enter Team Name")
    if st.button("Continue"):
        # check backend
        online = check_backend()
        if online:
            # try init on backend
            res = init_team_online(team_input)
            if res:
                st.session_state.team = team_input
                st.success(f"Team '{team_input}' created with ₹{res.get('cash', 0):.2f}")
                st.stop()
            else:
                # maybe team exists: try fetching portfolio
                port = fetch_portfolio_online(team_input)
                if port:
                    st.session_state.team = team_input
                    st.info(f"Team '{team_input}' logged in (online).")
                    st.stop()
                else:
                    st.error("Backend init failed. Try again or continue in Offline Mode.")
        else:
            # Offline: create local portfolio
            if team_input.strip():
                st.session_state.team = team_input
                # seed local portfolio if not present
                if team_input not in st.session_state.local_portfolios:
                    st.session_state.local_portfolios[team_input] = {"cash": 100000.0, "holdings": {}}
                st.success(f"Offline: Team '{team_input}' created locally with ₹100000.00")
                st.stop()
    st.stop()

team_name = st.session_state.team

# ---------- ORGANIZER ----------
st.sidebar.subheader("🔐 Organizer Access")
password = st.sidebar.text_input("Enter Organizer Password", type="password")
is_admin = password == "admin123"

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

# ---------- AUTO-REFRESH (every 4 sec) ----------
st_autorefresh(interval=4000, key="full_refresh")

# ---------- CHECK BACKEND & FETCH DATA ----------
online_stocks = check_backend()
if st.session_state.backend_online:
    # backend online
    stocks = fetch_stocks_online() or []       # if any failure, default empty list
    leaderboard = fetch_leaderboard_online() or []
    news = fetch_news_online() or {}
    portfolio = fetch_portfolio_online(team_name) or None
    # attempt flush of queued trades
    if st.session_state.trade_queue:
        flush_trade_queue()
else:
    # offline -> use simulated stocks, local leaderboard/news
    stocks = get_sim_stocks()
    leaderboard = []  # could be built from local_portfolios if desired
    news = {"articles": []}
    # portfolio from local store
    portfolio = st.session_state.local_portfolios.get(team_name, {"cash":100000.0, "holdings":{}})

# ---------- OFFLINE BANNER (Option B) ----------
if not st.session_state.backend_online:
    st.markdown("""
    <div style='background-color: #1b1f23; border-left: 6px solid #ffb86b; padding:12px; border-radius:6px;'>
    <b>🔄 Live backend temporarily unavailable.</b><br>
    ✅ Don’t worry — trading continues in Safe Mode (simulated prices). Your trades are queued and will be synced automatically when the backend returns.
    </div>
    """, unsafe_allow_html=True)

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

# ---------- PORTFOLIO DISPLAY ----------
st.subheader("💼 Portfolio")
if portfolio:
    # portfolio can be backend dict or local dict; handle both
    if isinstance(portfolio, dict):
        cash = portfolio.get("cash", 0.0)
        holdings = portfolio.get("holdings", {})
    else:
        # backend might return other structure; fallback
        cash = 0.0
        holdings = {}
    st.metric("Available Cash", f"₹{cash:.2f}")
    if holdings:
        st.dataframe(pd.DataFrame.from_dict(holdings, orient="index"), use_container_width=True)
    else:
        st.info("No holdings yet!")

# ---------- TRADE UI ----------
if stocks:
    col1, col2, col3, col4 = st.columns([2,2,1,1])
    with col1:
        selected_stock = st.selectbox("Select Stock", [s["symbol"] for s in stocks])
    with col2:
        qty = st.number_input("Quantity", min_value=1, step=1, value=1)
    with col3:
        buy = st.button("Buy", key="buy_btn")
    with col4:
        sell = st.button("Sell", key="sell_btn")

    # Process buy/sell immediately (online or offline)
    def apply_local_trade(team, symbol, qty):
        # qty positive -> buy, negative -> sell
        port = st.session_state.local_portfolios.setdefault(team, {"cash":100000.0, "holdings":{}})
        # find current price from stocks list
        price = next((s["price"] for s in stocks if s["symbol"] == symbol), None)
        if price is None:
            return False, "Price not found"
        total = price * abs(qty)
        if qty > 0:
            # buy: check cash
            if port["cash"] < total:
                return False, "Insufficient cash (offline)"
            port["cash"] -= total
            port["holdings"][symbol] = port["holdings"].get(symbol, 0) + qty
            return True, "Bought offline"
        else:
            # sell
            current_qty = port["holdings"].get(symbol, 0)
            if current_qty < abs(qty):
                return False, "Insufficient holdings (offline)"
            port["holdings"][symbol] = current_qty - abs(qty)
            if port["holdings"][symbol] == 0:
                del port["holdings"][symbol]
            port["cash"] += total
            return True, "Sold offline"

    if buy and trading_allowed:
        if st.session_state.backend_online:
            res = trade_online(team_name, selected_stock, int(qty))
            if res:
                st.success(f"✅ Bought {qty} of {selected_stock} (online)")
            else:
                # fallback: convert to offline queued trade and apply locally
                ok, msg = apply_local_trade(team_name, selected_stock, int(qty))
                if ok:
                    st.session_state.trade_queue.append({"team":team_name,"symbol":selected_stock,"qty":int(qty)})
                    st.warning("Backend trade failed — applied locally and queued for sync.")
                else:
                    st.error(f"Failed to buy: {msg}")
        else:
            ok, msg = apply_local_trade(team_name, selected_stock, int(qty))
            if ok:
                st.session_state.trade_queue.append({"team":team_name,"symbol":selected_stock,"qty":int(qty)})
                st.success(f"✅ Bought {qty} of {selected_stock} (offline, queued).")
            else:
                st.error(f"Failed to buy (offline): {msg}")

    if sell and trading_allowed:
        if st.session_state.backend_online:
            res = trade_online(team_name, selected_stock, -int(qty))
            if res:
                st.success(f"✅ Sold {qty} of {selected_stock} (online)")
            else:
                ok, msg = apply_local_trade(team_name, selected_stock, -int(qty))
                if ok:
                    st.session_state.trade_queue.append({"team":team_name,"symbol":selected_stock,"qty":-int(qty)})
                    st.warning("Backend sell failed — applied locally and queued for sync.")
                else:
                    st.error(f"Failed to sell: {msg}")
        else:
            ok, msg = apply_local_trade(team_name, selected_stock, -int(qty))
            if ok:
                st.session_state.trade_queue.append({"team":team_name,"symbol":selected_stock,"qty":-int(qty)})
                st.success(f"✅ Sold {qty} of {selected_stock} (offline, queued).")
            else:
                st.error(f"Failed to sell (offline): {msg}")

# ---------- STOCKS DISPLAY + 3D CHART ----------
if stocks:
    st.subheader("📊 Live Stock Prices")
    df = pd.DataFrame(stocks)
    # ensure numeric types
    df["pct_change"] = pd.to_numeric(df["pct_change"], errors="coerce").fillna(0.0)
    df["Trend"] = df["pct_change"].apply(lambda x: "🟢" if x>=0 else "🔴")
    st.dataframe(df[["symbol","name","price","pct_change","Trend"]].rename(
        columns={"symbol":"Symbol","name":"Company","price":"Price","pct_change":"% Change"}), use_container_width=True)

    # 3D chart
    df['volume'] = [i*1000 for i in range(1,len(df)+1)]
    fig3d = px.scatter_3d(df, x='price', y='pct_change', z='volume', color='Trend',
                          hover_name='name', size='price', size_max=18, opacity=0.8)
    fig3d.update_traces(marker=dict(line=dict(width=1,color='DarkSlateGrey')))
    fig3d.update_layout(scene=dict(xaxis_title="Price", yaxis_title="% Change", zaxis_title="Volume"), margin=dict(l=0,r=0,b=0,t=30))
    st.plotly_chart(fig3d, use_container_width=True)

# ---------- LEADERBOARD ----------
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
    st.info("No teams yet. Waiting for participants to trade... (Leaderboard empty)")

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

# ---------- DEBUG (Hidden for production, can be toggled) ----------
if st.sidebar.checkbox("Show debug info", False):
    st.sidebar.write("Backend online:", st.session_state.backend_online)
    st.sidebar.write("Queued trades:", st.session_state.trade_queue)
    st.sidebar.write("Local portfolios:", st.session_state.local_portfolios)
    st.sidebar.write("Team:", team_name)
