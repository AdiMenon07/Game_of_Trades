import streamlit as st
import streamlit.components.v1 as components
import requests
import os
import pandas as pd
import plotly.express as px
import time
from datetime import datetime

st.set_page_config(page_title="📈 Virtual Stock Market", layout="wide")

# ---------- CONFIG ----------
BACKEND = os.environ.get("BACKEND", "https://game-of-trades-vblh.onrender.com")
ROUND_DURATION = 30 * 60  # 30 minutes

# ---------- SESSION STATE KEYS ----------
if "team" not in st.session_state:
    st.session_state.team = None

# Use round_end (timestamp in seconds) as canonical single-value timer
# If round_end is None => no round started
# If paused => round_end is None and paused_remaining holds seconds remaining
for k, default in {
    "round_end": None,
    "paused": False,
    "paused_remaining": None,
    "buy_clicked": False,
    "sell_clicked": False,
}.items():
    if k not in st.session_state:
        st.session_state[k] = default

# ---------- UTILITIES ----------
def safe_get(url, timeout=4):
    try:
        r = requests.get(url, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None

def safe_post(url, payload, timeout=4):
    try:
        r = requests.post(url, json=payload, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None

def fetch_stocks():
    return safe_get(f"{BACKEND}/stocks") or []

def fetch_leaderboard():
    return safe_get(f"{BACKEND}/leaderboard") or []

def fetch_news():
    return safe_get(f"{BACKEND}/news") or {"articles": []}

def fetch_portfolio(team):
    if not team:
        return None
    return safe_get(f"{BACKEND}/portfolio/{team}")

def init_team(team):
    if not team:
        return None
    return safe_post(f"{BACKEND}/init_team", {"team": team})

def trade(team, symbol, qty):
    if not team:
        return None
    return safe_post(f"{BACKEND}/trade", {"team": team, "symbol": symbol, "qty": qty})

def is_trading_allowed_server_side():
    """
    Server-side check used when processing a Buy/Sell click.
    Ensures real enforcement regardless of client display.
    """
    # If a round_end exists and not paused => compare to current time
    if st.session_state.round_end is not None and not st.session_state.paused:
        return time.time() < st.session_state.round_end
    # If paused => trading not allowed
    return False

def format_mmss(seconds):
    seconds = max(0, int(seconds))
    m, s = divmod(seconds, 60)
    return f"{m:02d}:{s:02d}"

# ---------- TEAM LOGIN / REG ----------
if st.session_state.team is None:
    st.title("👥 Register or Login Your Team")
    team_name_input = st.text_input("Enter Team Name")
    if st.button("Continue"):
        if not team_name_input.strip():
            st.warning("Please enter a valid team name.")
        else:
            res = init_team(team_name_input.strip())
            if res:
                st.success(f"✅ Team '{team_name_input.strip()}' created with ₹{res.get('cash',0):.2f}")
                st.session_state.team = team_name_input.strip()
            else:
                # try login
                port = fetch_portfolio(team_name_input.strip())
                if port:
                    st.info(f"✅ Team '{team_name_input.strip()}' logged in successfully.")
                    st.session_state.team = team_name_input.strip()
                else:
                    st.error("❌ Could not create or find that team. Check backend or try another name.")
    st.stop()

team_name = st.session_state.team

# ---------- ORGANIZER CONTROLS ----------
with st.expander("⚙️ Organizer Controls (Start / Pause / Resume / Reset)"):
    st.write("These controls modify `round_end` stored in this app's session state.")
    # NOTE: session_state is per-user. If you want a single global timer across all participants,
    # store round_end centrally in your backend (e.g., POST/GET to /round) and use that value here.
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        if st.button("▶️ Start Round (30m)"):
            st.session_state.round_end = time.time() + ROUND_DURATION
            st.session_state.paused = False
            st.session_state.paused_remaining = None
            st.success("Round started.")
    with col2:
        if st.button("⏸ Pause Round"):
            if st.session_state.round_end and not st.session_state.paused:
                st.session_state.paused_remaining = max(0, st.session_state.round_end - time.time())
                st.session_state.round_end = None
                st.session_state.paused = True
                st.info("Round paused.")
            else:
                st.warning("No running round to pause.")
    with col3:
        if st.button("▶️ Resume Round"):
            if st.session_state.paused and st.session_state.paused_remaining is not None:
                st.session_state.round_end = time.time() + max(0, st.session_state.paused_remaining)
                st.session_state.paused_remaining = None
                st.session_state.paused = False
                st.success("Round resumed.")
            else:
                st.warning("Round not paused.")
    with col4:
        if st.button("♻️ Reset Round"):
            st.session_state.round_end = None
            st.session_state.paused = False
            st.session_state.paused_remaining = None
            st.info("Round reset (no active round).")

# ---------- TIMER DISPLAY (client-side smooth, non-blinking) ----------
# Determine what to pass to JS:
if st.session_state.round_end is not None and not st.session_state.paused:
    # pass end timestamp in milliseconds for client JS
    end_ts_ms = int(st.session_state.round_end * 1000)
    paused_flag = False
    paused_remaining = None
elif st.session_state.paused and st.session_state.paused_remaining is not None:
    end_ts_ms = None
    paused_flag = True
    paused_remaining = int(st.session_state.paused_remaining)
else:
    end_ts_ms = None
    paused_flag = False
    paused_remaining = None

# HTML/JS widget (updates locally every second)
timer_html = f"""
<div id="timer-container" style="text-align:center; font-family:Inter, sans-serif;">
  <div id="timer-label" style="font-size:14px; color:#666;">Round Timer</div>
  <div id="timer-value" style="font-size:44px; font-weight:700; margin-top:6px; color:#2b9348;">--:--</div>
  <div id="timer-sub" style="font-size:13px; color:#999; margin-top:4px;"></div>
</div>

<script>
(function() {{
  const endTs = {end_ts_ms if end_ts_ms is not None else 'null'};
  const paused = { 'true' if paused_flag else 'false' };
  const pausedRem = {paused_remaining if paused_remaining is not None else 'null'};

  const val = document.getElementById('timer-value');
  const sub = document.getElementById('timer-sub');

  function formatMMSS(totalSec) {{
    totalSec = Math.max(0, Math.floor(totalSec));
    const m = Math.floor(totalSec / 60);
    const s = totalSec % 60;
    return String(m).padStart(2,'0') + ':' + String(s).padStart(2,'0');
  }}

  function setColorByRemaining(sec) {{
    if (sec <= 10) {{
      val.style.color = '#ff0033';
      val.style.animation = 'blinker 1s linear infinite';
    }} else if (sec <= 60) {{
      val.style.color = '#ff8c00';
      val.style.animation = '';
    }} else {{
      val.style.color = '#2b9348';
      val.style.animation = '';
    }}
  }}

  if (paused === true || paused === 'true') {{
    val.textContent = formatMMSS(pausedRem || 0);
    sub.textContent = '⏸️ Paused';
    setColorByRemaining(pausedRem || 0);
  }} else if (!endTs) {{
    val.textContent = '--:--';
    sub.textContent = '⌛ Waiting to start...';
    val.style.color = '#666';
  }} else {{
    function tick() {{
      const remMs = endTs - Date.now();
      const remSec = Math.ceil(remMs / 1000);
      if (remMs <= 0) {{
        val.textContent = '00:00';
        sub.textContent = '⏹️ Round ended';
        setColorByRemaining(0);
        clearInterval(intervalId);
        return;
      }}
      val.textContent = formatMMSS(remSec);
      sub.textContent = 'Ends ' + new Date(endTs).toLocaleTimeString();
      setColorByRemaining(remSec);
    }}
    tick();
    const intervalId = setInterval(tick, 1000);
  }}

  // blinker animation
  const style = document.createElement('style');
  style.innerHTML = '@keyframes blinker {{ 50% {{ opacity: 0; }} }}';
  document.head.appendChild(style);
}})();
</script>
"""

components.html(timer_html, height=120)

# ---------- FETCH DATA ----------
stocks = fetch_stocks()
leaderboard = fetch_leaderboard()
news = fetch_news()
portfolio = fetch_portfolio(team_name)

# ---------- PORTFOLIO / TRADE UI ----------
st.subheader(f"📊 Portfolio — {team_name}")

if portfolio:
    st.metric("Total Portfolio Value", f"₹{portfolio.get('portfolio_value',0):,.2f}")
    st.write(f"💵 **Cash:** ₹{portfolio.get('cash',0):,.2f}")

    if portfolio.get("holdings"):
        holdings_df = pd.DataFrame.from_dict(portfolio["holdings"], orient="index")
        holdings_df.index.name = "Stock"
        st.dataframe(holdings_df, use_container_width=True)
    else:
        st.info("No holdings yet. Buy some stocks!")

    # Trade widget
    st.subheader("💸 Place Trade")
    if stocks:
        col1, col2, col3, col4 = st.columns([2,2,1,1])
        with col1:
            selected_stock = st.selectbox("Select Stock", [s["symbol"] for s in stocks])
        with col2:
            qty = st.number_input("Quantity", min_value=1, step=1, value=1)
        with col3:
            if st.button("Buy"):
                allowed = is_trading_allowed_server_side()
                if not allowed:
                    st.warning("Trading not allowed (round not active or paused).")
                else:
                    res = trade(team_name, selected_stock, int(qty))
                    if res and res.get("success", True):
                        st.success(f"✅ Bought {qty} of {selected_stock}")
                    else:
                        st.error("❌ Buy failed — check cash balance or backend.")
        with col4:
            if st.button("Sell"):
                allowed = is_trading_allowed_server_side()
                if not allowed:
                    st.warning("Trading not allowed (round not active or paused).")
                else:
                    res = trade(team_name, selected_stock, -int(qty))
                    if res and res.get("success", True):
                        st.success(f"✅ Sold {qty} of {selected_stock}")
                    else:
                        st.error("❌ Sell failed — check holdings or backend.")
    else:
        st.info("No stock data available right now.")
else:
    st.warning("Portfolio not found. Try creating a new team or check backend.")

# ---------- STOCK LIST ----------
st.subheader("💹 Live Stock Prices")
if stocks:
    df = pd.DataFrame(stocks)
    if "pct_change" not in df.columns:
        df["pct_change"] = 0
    df["Trend"] = df["pct_change"].apply(lambda x: "🟢" if x >= 0 else "🔴")
    st.dataframe(
        df[["symbol","name","price","pct_change","Trend"]]
        .rename(columns={"symbol":"Symbol","name":"Company","price":"Price","pct_change":"% Change"}),
        use_container_width=True
    )

    # 3D scatter (visual)
    df['volume'] = [i*1000 for i in range(1, len(df)+1)]
    fig3d = px.scatter_3d(df, x='price', y='pct_change', z='volume', color='Trend',
                          hover_name='name', size='price', size_max=18, opacity=0.8)
    fig3d.update_traces(marker=dict(line=dict(width=1,color='DarkSlateGrey')))
    fig3d.update_layout(scene=dict(xaxis_title="Price", yaxis_title="% Change", zaxis_title="Volume"),
                        margin=dict(l=0,r=0,b=0,t=30))
    st.plotly_chart(fig3d, use_container_width=True)
else:
    st.warning("No stock data available right now.")

# ---------- LEADERBOARD ----------
st.subheader("🏆 Live Leaderboard")
if leaderboard:
    ldf = pd.DataFrame(leaderboard)
    st.dataframe(ldf.sort_values("value", ascending=False).reset_index(drop=True), use_container_width=True)
else:
    st.info("No teams yet.")

# ---------- NEWS ----------
st.subheader("📰 Market News")
if news and "articles" in news and news["articles"]:
    for article in news["articles"]:
        st.markdown(f"- [{article.get('title','(no title)')}]({article.get('url','#')})")
else:
    st.info("No news available.")
