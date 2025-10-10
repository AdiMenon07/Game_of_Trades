# backend/main.py
import asyncio
import random
import time
from typing import List, Optional
from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
import sqlite3
import threading
import requests
import os
import json

DB_FILE = "market.db"

app = FastAPI(title="Simulated Stock Market API")

# ---------- Round state ----------
ROUND_DURATION = 30 * 60  # 30 minutes
ROUND_START = None
ROUND_ACTIVE = False

# ---------- DB utilities (simple SQLite) ----------
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS stocks (
        symbol TEXT PRIMARY KEY,
        name TEXT,
        price REAL,
        last_price REAL,
        updated_at INTEGER
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS portfolios (
        team TEXT PRIMARY KEY,
        cash REAL,
        holdings TEXT,
        last_updated INTEGER
    )
    """)
    conn.commit()
    conn.close()

def run_query(query, params=(), fetch=False):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute(query, params)
    if fetch:
        rows = cur.fetchall()
        conn.close()
        return rows
    conn.commit()
    conn.close()
    return None

# ---------- Models ----------
class StockOut(BaseModel):
    symbol: str
    name: str
    price: float
    last_price: float
    pct_change: float
    updated_at: int

class TradeReq(BaseModel):
    team: str
    symbol: str
    qty: int  # positive to buy, negative to sell

class CreateTeamReq(BaseModel):
    team: str

# ---------- Seed initial stocks ----------
INITIAL_STOCKS = [
    ("APPL", "Apple (sim)", 1750.0),
    ("TSLA", "Tesla (sim)", 2650.0),
    ("GOGL", "Google (sim)", 2820.0),
    ("AMZN", "Amazon (sim)", 3300.0),
    ("INFY", "Infosys (sim)", 1500.0),
    ("TCS", "TCS (sim)", 3200.0),
    ("RELI", "Reliance (sim)", 2400.0),
    ("HDFC", "HDFC Bank (sim)", 1200.0),
]

@app.on_event("startup")
def startup():
    init_db()
    # seed stocks if not present
    for sym, name, price in INITIAL_STOCKS:
        existing = run_query("SELECT symbol FROM stocks WHERE symbol = ?", (sym,), fetch=True)
        if not existing:
            run_query("INSERT INTO stocks(symbol,name,price,last_price,updated_at) VALUES (?, ?, ?, ?, ?)",
                      (sym, name, price, price, int(time.time())))
    # start background updater threads
    updater_thread = threading.Thread(target=price_update_loop, daemon=True)
    updater_thread.start()
    live_thread = threading.Thread(target=live_price_update_loop, daemon=True)
    live_thread.start()

# ---------- Background price updater ----------
def price_update_loop():
    while True:
        wait = random.randint(60, 120)
        time.sleep(wait)
        rows = run_query("SELECT symbol, price FROM stocks", fetch=True)
        if not rows:
            continue
        count = random.randint(1, max(1, min(4, len(rows))))
        picks = random.sample(rows, count)
        for symbol, current_price in picks:
            pct = random.uniform(-0.02, 0.02)
            new_price = max(0.01, current_price * (1 + pct))
            run_query("UPDATE stocks SET last_price = price, price = ?, updated_at = ? WHERE symbol = ?",
                      (new_price, int(time.time()), symbol))

# ---------- Live frequent updater (every 2 sec) ----------
def live_price_update_loop():
    global ROUND_ACTIVE, ROUND_START
    while True:
        time.sleep(2)
        if not ROUND_ACTIVE or (ROUND_START and time.time() - ROUND_START > ROUND_DURATION):
            ROUND_ACTIVE = False
            continue
        rows = run_query("SELECT symbol, price FROM stocks", fetch=True)
        if not rows:
            continue
        with threading.Lock():
            for symbol, current_price in rows:
                pct = random.uniform(-0.005, 0.005)
                new_price = max(0.01, current_price * (1 + pct))
                run_query(
                    "UPDATE stocks SET last_price = price, price = ?, updated_at = ? WHERE symbol = ?",
                    (new_price, int(time.time()), symbol)
                )

# ---------- Helper: compute pct change ----------
def row_to_stockout(r):
    symbol, name, price, last_price, updated_at = r
    pct = 0.0
    if last_price and last_price != 0:
        pct = ((price - last_price) / last_price) * 100.0
    return {
        "symbol": symbol,
        "name": name,
        "price": round(price, 2),
        "last_price": round(last_price, 2),
        "pct_change": round(pct, 2),
        "updated_at": updated_at
    }

# ---------- Round control endpoints ----------
@app.post("/start_round")
def start_round():
    global ROUND_START, ROUND_ACTIVE
    ROUND_START = int(time.time())
    ROUND_ACTIVE = True
    return {"ok": True, "message": "Round started."}

@app.post("/end_round")
def end_round():
    global ROUND_ACTIVE
    ROUND_ACTIVE = False
    return {"ok": True, "message": "Round ended."}

# ---------- Endpoints ----------
@app.get("/stocks", response_model=List[StockOut])
def get_stocks():
    rows = run_query("SELECT symbol,name,price,last_price,updated_at FROM stocks", fetch=True)
    return [row_to_stockout(r) for r in rows]

@app.post("/init_team")
def init_team(req: CreateTeamReq):
    existing = run_query("SELECT team FROM portfolios WHERE team = ?", (req.team,), fetch=True)
    if existing:
        raise HTTPException(status_code=400, detail="Team already exists")
    run_query("INSERT INTO portfolios(team,cash,holdings,last_updated) VALUES(?,?,?,?)",
              (req.team, 100000.0, "{}", int(time.time())))
    return {"ok": True, "cash": 100000.0}

@app.get("/portfolio/{team}")
def get_portfolio(team: str):
    rows = run_query("SELECT cash, holdings FROM portfolios WHERE team = ?", (team,), fetch=True)
    if not rows:
        raise HTTPException(status_code=404, detail="Team not found")
    cash, holdings_json = rows[0]
    holdings = json.loads(holdings_json) if holdings_json else {}
    stock_prices = {r[0]: r[2] for r in run_query("SELECT symbol,name,price FROM stocks", fetch=True)}
    holdings_detail = {}
    pv = cash
    for sym, qty in holdings.items():
        price = stock_prices.get(sym,0)
        value = price*qty
        holdings_detail[sym] = {"qty": qty, "price": price, "value": round(value,2)}
        pv += value
    return {"team": team, "cash": round(cash,2), "holdings": holdings_detail, "portfolio_value": round(pv,2)}

@app.post("/trade")
def trade(req: TradeReq):
    global ROUND_ACTIVE, ROUND_START
    if not ROUND_ACTIVE or (ROUND_START and time.time() - ROUND_START > ROUND_DURATION):
        raise HTTPException(status_code=403, detail="Trading round has ended.")
    team = req.team
    sym = req.symbol
    qty = req.qty
    if qty == 0:
        raise HTTPException(status_code=400, detail="qty cannot be 0")
    row = run_query("SELECT price FROM stocks WHERE symbol = ?", (sym,), fetch=True)
    if not row:
        raise HTTPException(status_code=404, detail="Stock not found")
    price = row[0][0]
    total = price * abs(qty)
    p = run_query("SELECT cash, holdings FROM portfolios WHERE team = ?", (team,), fetch=True)
    if not p:
        raise HTTPException(status_code=404, detail="Team not found")
    cash, holdings_json = p[0]
    holdings = json.loads(holdings_json) if holdings_json else {}
    if qty > 0:
        if cash < total:
            raise HTTPException(status_code=400, detail="Insufficient cash")
        cash -= total
        holdings[sym] = holdings.get(sym,0)+qty
    else:
        need = abs(qty)
        have = holdings.get(sym,0)
        if have<need:
            raise HTTPException(status_code=400, detail="Insufficient holdings to sell")
        holdings[sym]=have-need
        if holdings[sym]==0:
            del holdings[sym]
        cash += total
    run_query("UPDATE portfolios SET cash=?, holdings=?, last_updated=? WHERE team=?",
              (cash, json.dumps(holdings), int(time.time()), team))
    return {"ok": True, "cash": round(cash,2), "holdings": holdings}

@app.get("/leaderboard")
def leaderboard():
    teams = run_query("SELECT team,cash,holdings FROM portfolios", fetch=True)
    stock_prices = {r[0]: r[2] for r in run_query("SELECT symbol,name,price FROM stocks", fetch=True)}
    board = []
    for team, cash, holdings_json in teams:
        holdings = json.loads(holdings_json) if holdings_json else {}
        total_value = cash
        for s,q in holdings.items():
            total_value += stock_prices.get(s,0)*q
        board.append({"team":team,"cash":round(cash,2),"holdings":holdings,"value":round(total_value,2)})
    board.sort(key=lambda x:x["value"], reverse=True)
    return board

@app.get("/portfolio_value/{team}")
def portfolio_value(team: str):
    rows = run_query("SELECT cash, holdings FROM portfolios WHERE team = ?", (team,), fetch=True)
    if not rows:
        raise HTTPException(status_code=404, detail="Team not found")
    cash, holdings_json = rows[0]
    holdings = json.loads(holdings_json) if holdings_json else {}
    stock_prices = {r[0]: r[2] for r in run_query("SELECT symbol,name,price FROM stocks", fetch=True)}
    total_value = cash
    for s,q in holdings.items():
        total_value += stock_prices.get(s,0)*q
    return {"team": team, "value": round(total_value,2)}

@app.get("/news")
def get_news(q: Optional[str]="stock market"):
    NEWS_API_KEY = os.environ.get("NEWS_API_KEY", "")
    if NEWS_API_KEY:
        try:
            r = requests.get("https://newsapi.org/v2/everything", params={"q": q, "pageSize": 8, "apiKey": NEWS_API_KEY, "sortBy": "publishedAt", "language": "en"}, timeout=8)
            j = r.json()
            articles=[{"title":a["title"],"url":a["url"],"source":a["source"]["name"]} for a in j.get("articles",[])]
            return {"source":"newsapi","articles":articles}
        except:
            pass
    try:
        rss_url=f"https://news.google.com/rss/search?q={requests.utils.requote_uri(q)}&hl=en-IN&gl=IN&ceid=IN:en"
        r=requests.get(rss_url,timeout=6)
        items=[]
        txt=r.text
        parts=txt.split("<item>")
        for p in parts[1:9]:
            t=p.split("<title>")[1].split("</title>")[0]
            link=""
            if "<link>" in p:
                link=p.split("<link>")[1].split("</link>")[0]
            items.append({"title":t,"url":link})
        return {"source":"google_rss","articles":items}
    except Exception as e:
        return {"source":"none","articles":[],"error":str(e)}
