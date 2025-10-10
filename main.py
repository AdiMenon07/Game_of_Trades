import asyncio
import random
import time
from typing import List, Optional
from fastapi import FastAPI, HTTPException
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
lock = threading.Lock()

# ---------- DB utilities ----------
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
    qty: int

class CreateTeamReq(BaseModel):
    team: str

# ---------- Initial stock data ----------
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

# ---------- Background threads ----------
def price_update_loop():
    while True:
        time.sleep(random.randint(60, 120))
        with lock:
            rows = run_query("SELECT symbol, price FROM stocks", fetch=True)
            if not rows:
                continue
            for symbol, price in random.sample(rows, random.randint(1, len(rows))):
                pct = random.uniform(-0.02, 0.02)
                new_price = round(max(1, price * (1 + pct)), 2)
                run_query(
                    "UPDATE stocks SET last_price = price, price = ?, updated_at = ? WHERE symbol = ?",
                    (new_price, int(time.time()), symbol)
                )

def live_price_update_loop():
    global ROUND_ACTIVE, ROUND_START
    while True:
        time.sleep(2)
        if not ROUND_ACTIVE:
            continue
        with lock:
            if ROUND_START and time.time() - ROUND_START > ROUND_DURATION:
                ROUND_ACTIVE = False
                continue
            rows = run_query("SELECT symbol, price FROM stocks", fetch=True)
            for symbol, price in rows:
                pct = random.uniform(-0.005, 0.005)
                new_price = round(max(1, price * (1 + pct)), 2)
                run_query(
                    "UPDATE stocks SET last_price = price, price = ?, updated_at = ? WHERE symbol = ?",
                    (new_price, int(time.time()), symbol)
                )

# ---------- Round control ----------
@app.post("/start_round")
def start_round():
    global ROUND_START, ROUND_ACTIVE
    ROUND_START = time.time()
    ROUND_ACTIVE = True
    return {"ok": True, "message": "Trading round started."}

@app.post("/force_start")
def force_start():
    global ROUND_ACTIVE, ROUND_START
    ROUND_ACTIVE = True
    ROUND_START = time.time()
    return {"ok": True, "message": "Force started trading round."}

@app.post("/end_round")
def end_round():
    global ROUND_ACTIVE
    ROUND_ACTIVE = False
    return {"ok": True, "message": "Trading round ended."}

# ---------- Startup ----------
@app.on_event("startup")
def startup():
    init_db()
    for sym, name, price in INITIAL_STOCKS:
        existing = run_query("SELECT symbol FROM stocks WHERE symbol=?", (sym,), fetch=True)
        if not existing:
            run_query(
                "INSERT INTO stocks(symbol,name,price,last_price,updated_at) VALUES (?,?,?,?,?)",
                (sym, name, price, price, int(time.time()))
            )
    # Start threads
    threading.Thread(target=price_update_loop, daemon=True).start()
    threading.Thread(target=live_price_update_loop, daemon=True).start()

    # Auto start round
    global ROUND_ACTIVE, ROUND_START
    ROUND_ACTIVE = True
    ROUND_START = time.time()

# ---------- Endpoints ----------
@app.get("/stocks", response_model=List[StockOut])
def get_stocks():
    rows = run_query("SELECT symbol,name,price,last_price,updated_at FROM stocks", fetch=True)
    return [{
        "symbol": r[0],
        "name": r[1],
        "price": r[2],
        "last_price": r[3],
        "pct_change": round(((r[2] - r[3]) / r[3] * 100) if r[3] else 0, 2),
        "updated_at": r[4]
    } for r in rows]

@app.post("/init_team")
def init_team(req: CreateTeamReq):
    existing = run_query("SELECT team FROM portfolios WHERE team=?", (req.team,), fetch=True)
    if existing:
        raise HTTPException(status_code=400, detail="Team already exists")
    run_query("INSERT INTO portfolios(team,cash,holdings,last_updated) VALUES(?,?,?,?)",
              (req.team, 100000.0, "{}", int(time.time())))
    return {"ok": True, "cash": 100000.0}

@app.post("/trade")
def trade(req: TradeReq):
    global ROUND_ACTIVE, ROUND_START
    if not ROUND_ACTIVE or (ROUND_START and time.time() - ROUND_START > ROUND_DURATION):
        raise HTTPException(status_code=403, detail="Trading round has ended.")
    if req.qty == 0:
        raise HTTPException(status_code=400, detail="Quantity cannot be 0")

    row = run_query("SELECT price FROM stocks WHERE symbol=?", (req.symbol,), fetch=True)
    if not row:
        raise HTTPException(status_code=404, detail="Stock not found")

    price = row[0][0]
    total = price * abs(req.qty)
    p = run_query("SELECT cash, holdings FROM portfolios WHERE team=?", (req.team,), fetch=True)
    if not p:
        raise HTTPException(status_code=404, detail="Team not found")

    cash, holdings_json = p[0]
    holdings = json.loads(holdings_json or "{}")

    if req.qty > 0:  # Buy
        if cash < total:
            raise HTTPException(status_code=400, detail="Insufficient cash")
        cash -= total
        holdings[req.symbol] = holdings.get(req.symbol, 0) + req.qty
    else:  # Sell
        need = abs(req.qty)
        have = holdings.get(req.symbol, 0)
        if have < need:
            raise HTTPException(status_code=400, detail="Insufficient holdings")
        holdings[req.symbol] = have - need
        if holdings[req.symbol] == 0:
            del holdings[req.symbol]
        cash += total

    run_query("UPDATE portfolios SET cash=?, holdings=?, last_updated=? WHERE team=?",
              (cash, json.dumps(holdings), int(time.time()), req.team))
    return {"ok": True, "cash": cash, "holdings": holdings}

@app.get("/portfolio/{team}")
def get_portfolio(team: str):
    p = run_query("SELECT cash, holdings FROM portfolios WHERE team=?", (team,), fetch=True)
    if not p:
        raise HTTPException(status_code=404, detail="Team not found")
    cash, holdings_json = p[0]
    holdings = json.loads(holdings_json or "{}")
    stock_prices = {r[0]: r[2] for r in run_query("SELECT symbol,name,price FROM stocks", fetch=True)}
    details = {s: {"qty": q, "price": stock_prices.get(s, 0), "value": round(stock_prices.get(s, 0) * q, 2)}
               for s, q in holdings.items()}
    value = cash + sum(v["value"] for v in details.values())
    return {"team": team, "cash": round(cash, 2), "holdings": details, "portfolio_value": round(value, 2)}

@app.get("/leaderboard")
def leaderboard():
    teams = run_query("SELECT team,cash,holdings FROM portfolios", fetch=True)
    prices = {r[0]: r[2] for r in run_query("SELECT symbol,name,price FROM stocks", fetch=True)}
    board = []
    for t, c, h in teams:
        holdings = json.loads(h or "{}")
        value = c + sum(prices.get(s, 0) * q for s, q in holdings.items())
        board.append({"team": t, "value": round(value, 2)})
    board.sort(key=lambda x: x["value"], reverse=True)
    return board
