import streamlit as st
import requests
import os
import pandas as pd
import plotly.express as px
import time
from datetime import datetime

# ---------- PAGE CONFIG ----------
st.set_page_config(page_title="📈 Virtual Stock Market", layout="wide")

# ---------- CUSTOM BACKGROUND ----------
st.markdown("""
    <style>
    .stApp {
        background-color: #f7f7f5 !important;
    }
    </style>
""", unsafe_allow_html=True)

# ---------- BACKEND URL ----------
BACKEND = os.environ.get("BACKEND", "https://game-of-trades-vblh.onrender.com")

# ---------- SESSION STATE ----------
for key in ["team", "round_start", "paused", "pause_time", "last_refresh"]:
    if key not in st.session_state:
        st.session_state[key] = None if key == "team" else 0

ROUND_DURATION = 30 * 60  # 30 minutes

# ---------- UTILITY FUNCTIONS ----------
def safe_get(url, timeout=5):
    try:
        r = requests.get(url, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"⚠️ GET error from {url}: {e}")
        return None

def safe_post(url, data, timeout=5):
    try:
        r = requests.post(url, json=data, timeout=timeout)
        if r.status_code != 200:
            st.error(f"🚫 POST failed: {r.status_code} — {r.text}")
            return None
        return r.json()
    except Exception as e:
        st.error(f"⚠️ POST error: {e}")
        return None

def fetch_stocks():
    return safe_get(f"{BACKEND}/stocks")

def fetch_leaderboard():
    return safe_get(f"{BACKEND}/leaderboard")

def fetch_news():
    return safe_get(f"{BACKEND}/news")

def fetch_portfolio(team):
    return safe_get(f"{BACKEND}/portfolio/{team}")

def init_team(team):
    res = safe_post(f"{BACKEND}/init_team", {"team": team})
    if not res:
        port = fetch_portfolio(team)
        if port:
            return port
    return res

def trade(team, symbol, qty):
    return safe_post(f"{BACKEND}/trade", {"team": team, "symbol": symbol, "qty": qty})

# ---------- TEAM REGISTRATION ----------
if not st.session_state.team:
    st.title("👥 Register or Login Your Team")
    team_name_input = st.text_input("Enter Team Name")

    if st.button("Continue"):
        if team_name_input.strip():
            res = init_team(team_name_input)
            if res:
                st.success(f"Welcome, {team_name_input}! Portfolio loaded.")
                st.session_state.team = team_name_input
                st.session_state.last_refresh = time.time()
                st.rerun()
            else:
                st.error("❌ Could not register or load team. Try again.")
    st.stop()

team_name = st.session_state.team

# ---------- ORGANIZER CONTROLS ----------
with st.expander("⚙️ Organizer Controls"):
    st.write("Control the round timer here.")
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        if st.button("▶️ Start Round"):
            st.session_state.round_start = time.time()
            st.session_state.paused = False
            st.success("✅ Round started.")
            st.rerun()

    with col2:
        if st.button("⏸ Pause Round"):
            if st.session_state.round_start and not st.session_state.paused:
                st.session_state.paused = True
                st.session_state.pause_time = time.time()
                st.info("⏸ Round paused.")
                st.rerun()

    with col3:
        if st.button("🔄 Resume Round"):
            if st.session_state.paused:
                paused_duration = time.time() - st.session_state.pause_time
                st.session_state.round_start += paused_duration
                st.session_state.paused = False
                st.success("▶️ Round resumed.")
                st.rerun()

    with col4:
        if st.button("♻️ Reset Round"):
            st.session_state.round_start = None
            st.session_state.paused = False
            st.session_state.pause_time = 0
            st.warning("Round reset. You must start again.")
            st.rerun()

# ---------- TIMER ----------
timer_placeholder = st.empty()
if st.session_state.round_start:
    if st.session_state.paused:
        elapsed = st.session_state.pause_time - st.session_state.round_start
    else:
        elapsed = time.time() - st.session_state.round_start

    remaining = max(0, ROUND_DURATION - elapsed)
    mins, secs = divmod(int(remaining), 60)
    color = "green" if remaining > 60 else ("orange" if remaining > 10 else "red")

    if remaining <= 0:
        trading_allowed = False
        timer_placeholder.markdown(
            "<h2 style='text-align:center; color:red;'>⏹️ Trading round has ended!</h2>",
            unsafe_allow_html=True
        )
    else:
        trading_allowed = True
        timer_placeholder.markdown(
            f"<h1 style='text-align:center; color:{color};'>⏱️ {mins:02d}:{secs:02d}</h1>",
            unsafe_allow_html=True
        )
else:
    trading_allowed = False
    timer_placeholder.markdown(
        "<h3 style='text-align:center; color:orange;'>⌛ Waiting for round to start...</h3>",
        unsafe_allow_html=True
    )

# ---------- FETCH DATA ----------
# Refresh every 10 seconds instead of blinking every second
if time.time() - st.session_state.last_refresh > 10:
    stocks = fetch_stocks()
    leaderboard = fetch_leaderboard()
    news = fetch_news()
    portfolio = fetch_portfolio(team_name)
    st.session_state.last_refresh = time.time()
else:
    stocks = fetch_stocks()
    leaderboard = fetch_leaderboard()
    portfolio = fetch_portfolio(team_name)
    news = fetch_news()

# ---------- PORTFOLIO ----------
if portfolio:
    st.subheader("💼 Portfolio")
    st.metric("Available Cash", f"₹{portfolio['cash']:.2f}")

    if portfolio["holdings"]:
        holdings_df = pd.DataFrame.from_dict(portfolio["holdings"], orient="index")
        st.dataframe(holdings_df, use_container_width=True)
    else:
        st.info("No holdings yet. Buy some stocks!")

    # ---------- TRADE ----------
    st.subheader("💸 Place Trade")
    if stocks:
        col1, col2, col3, col4 = st.columns([2, 2, 1, 1])
        with col1:
            selected_stock = st.selectbox("Select Stock", [s["symbol"] for s in stocks])
        with col2:
            qty = st.number_input("Quantity", min_value=1, step=1, value=1)

        with col3:
            if st.button("💰 Buy", key="buy_button"):
                if trading_allowed:
                    res = trade(team_name, selected_stock, int(qty))
                    if res and "cash" in res:
                        st.success(f"✅ Bought {qty} of {selected_stock}")
                        st.session_state.last_refresh = 0
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("❌ Buy failed. Check backend message above.")
                else:
                    st.warning("Trading round has ended!")

        with col4:
            if st.button("📉 Sell", key="sell_button"):
                if trading_allowed:
                    res = trade(team_name, selected_stock, -int(qty))
                    if res and "cash" in res:
                        st.success(f"✅ Sold {qty} of {selected_stock}")
                        st.session_state.last_refresh = 0
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("❌ Sell failed. Check backend message above.")
                else:
                    st.warning("Trading round has ended!")

# ---------- STOCKS ----------
if stocks:
    st.subheader("📊 Live Stock Prices")
    df = pd.DataFrame(stocks)
    df["Trend"] = df["pct_change"].apply(lambda x: "🟢" if x >= 0 else "🔴")
    st.dataframe(df[["symbol", "name", "price", "pct_change", "Trend"]]
                 .rename(columns={"symbol": "Symbol", "name": "Company", "price": "Price", "pct_change": "% Change"}),
                 use_container_width=True)

    df['volume'] = [i * 1000 for i in range(1, len(df) + 1)]
    fig3d = px.scatter_3d(df, x='price', y='pct_change', z='volume', color='Trend',
                          hover_name='name', size='price', size_max=18, opacity=0.8)
    fig3d.update_traces(marker=dict(line=dict(width=1, color='DarkSlateGrey')))
    fig3d.update_layout(scene=dict(xaxis_title="Price", yaxis_title="% Change", zaxis_title="Volume"),
                        margin=dict(l=0, r=0, b=0, t=30))
    st.plotly_chart(fig3d, use_container_width=True)
else:
    st.warning("No stock data available right now.")

# ---------- LEADERBOARD ----------
st.subheader("🏆 Live Leaderboard")
if leaderboard:
    ldf = pd.DataFrame(leaderboard).sort_values("value", ascending=False).reset_index(drop=True)
    ldf.index += 1

    def highlight_top3(row):
        if row.name == 1:
            return ['background-color: gold; font-weight:bold'] * len(row)
        elif row.name == 2:
            return ['background-color: silver; font-weight:bold'] * len(row)
        elif row.name == 3:
            return ['background-color: #cd7f32; font-weight:bold'] * len(row)
        else:
            return [''] * len(row)

    st.dataframe(ldf.style.apply(highlight_top3, axis=1), use_container_width=True, hide_index=False)
else:
    st.info("No teams yet. Waiting for participants to trade...")

# ---------- NEWS ----------
st.subheader("📰 Market News")
if news and "articles" in news and news["articles"]:
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
