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

# ---------- ROUND STATE ----------
ROUND_DURATION = 30 * 60  # 30 minutes
ROUND_START = None
ROUND_ACTIVE = False

# ---------- DATABASE ----------
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS teams (
            name TEXT PRIMARY KEY,
            cash REAL DEFAULT 100000
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS holdings (
            team TEXT,
            symbol TEXT,
            qty INTEGER,
            PRIMARY KEY (team, symbol)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS stocks (
            symbol TEXT PRIMARY KEY,
            name TEXT,
            price REAL,
            pct_change REAL
        )
    """)
    conn.commit()
    conn.close()

# ---------- STOCK INITIALIZATION ----------
STOCKS = [
    ("AAPL", "Apple Inc."),
    ("GOOG", "Alphabet Inc."),
    ("AMZN", "Amazon.com Inc."),
    ("TSLA", "Tesla Inc."),
    ("MSFT", "Microsoft Corp."),
    ("META", "Meta Platforms"),
    ("NFLX", "Netflix Inc."),
    ("NVDA", "NVIDIA Corp.")
]

def seed_stocks():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    for s, name in STOCKS:
        c.execute("INSERT OR IGNORE INTO stocks (symbol, name, price, pct_change) VALUES (?, ?, ?, ?)",
                  (s, name, random.uniform(800, 2000), 0))
    conn.commit()
    conn.close()

# ---------- UTILITIES ----------
def get_stocks():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT symbol, name, price, pct_change FROM stocks")
    rows = c.fetchall()
    conn.close()
    return [{"symbol": r[0], "name": r[1], "price": r[2], "pct_change": r[3]} for r in rows]

def update_stock_prices():
    while True:
        if ROUND_ACTIVE:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT symbol, price FROM stocks")
            rows = c.fetchall()
            for sym, price in rows:
                change = random.uniform(-3, 3)
                new_price = max(10, price * (1 + change / 100))
                c.execute("UPDATE stocks SET price=?, pct_change=? WHERE symbol=?", (new_price, change, sym))
            conn.commit()
            conn.close()
        time.sleep(10)

# ---------- API MODELS ----------
class TradeRequest(BaseModel):
    team: str
    symbol: str
    qty: int  # positive for buy, negative for sell

class InitTeam(BaseModel):
    team: str

# ---------- ENDPOINTS ----------
@app.on_event("startup")
def startup_event():
    init_db()
    seed_stocks()
    threading.Thread(target=update_stock_prices, daemon=True).start()

@app.get("/stocks")
def stocks():
    return get_stocks()

@app.post("/init_team")
def init_team(data: InitTeam):
    team = data.team.strip()
    if not team:
        raise HTTPException(status_code=400, detail="Invalid team name")
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO teams (name, cash) VALUES (?, ?)", (team, 100000))
    conn.commit()
    c.execute("SELECT cash FROM teams WHERE name=?", (team,))
    cash = c.fetchone()[0]
    conn.close()
    return {"team": team, "cash": cash}

@app.post("/trade")
def trade(data: TradeRequest):
    team, symbol, qty = data.team.strip(), data.symbol.strip(), int(data.qty)
    if qty == 0:
        raise HTTPException(status_code=400, detail="Quantity must not be zero")

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    # Get stock price
    c.execute("SELECT price FROM stocks WHERE symbol=?", (symbol,))
    stock = c.fetchone()
    if not stock:
        conn.close()
        raise HTTPException(status_code=404, detail="Stock not found")

    price = stock[0]
    total = price * abs(qty)

    # Get team info
    c.execute("SELECT cash FROM teams WHERE name=?", (team,))
    row = c.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Team not found")
    cash = row[0]

    # --- BUY ---
    if qty > 0:
        if cash < total:
            conn.close()
            raise HTTPException(status_code=400, detail="Insufficient funds")
        cash -= total
        c.execute("UPDATE teams SET cash=? WHERE name=?", (cash, team))
        c.execute("INSERT OR IGNORE INTO holdings (team, symbol, qty) VALUES (?, ?, 0)", (team, symbol))
        c.execute("UPDATE holdings SET qty = qty + ? WHERE team=? AND symbol=?", (qty, team, symbol))

    # --- SELL ---
    else:
        qty = abs(qty)
        c.execute("SELECT qty FROM holdings WHERE team=? AND symbol=?", (team, symbol))
        row = c.fetchone()
        if not row or row[0] < qty:
            conn.close()
            raise HTTPException(status_code=400, detail="Not enough shares to sell")
        new_qty = row[0] - qty
        if new_qty == 0:
            c.execute("DELETE FROM holdings WHERE team=? AND symbol=?", (team, symbol))
        else:
            c.execute("UPDATE holdings SET qty=? WHERE team=? AND symbol=?", (new_qty, team, symbol))
        cash += total
        c.execute("UPDATE teams SET cash=? WHERE name=?", (cash, team))

    conn.commit()
    conn.close()
    return {"success": True, "team": team, "symbol": symbol, "qty": qty}

@app.get("/portfolio/{team}")
def portfolio(team: str):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT cash FROM teams WHERE name=?", (team,))
    row = c.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Team not found")
    cash = row[0]
    c.execute("SELECT symbol, qty FROM holdings WHERE team=?", (team,))
    holdings = dict(c.fetchall())
    conn.close()
    return {"team": team, "cash": cash, "holdings": holdings}

@app.get("/leaderboard")
def leaderboard():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT name, cash FROM teams")
    teams = c.fetchall()

    lb = []
    for name, cash in teams:
        c.execute("SELECT h.symbol, h.qty, s.price FROM holdings h JOIN stocks s ON h.symbol=s.symbol WHERE h.team=?", (name,))
        total_value = sum(q * p for _, q, p in c.fetchall())
        lb.append({"team": name, "value": cash + total_value})

    conn.close()
    return sorted(lb, key=lambda x: x["value"], reverse=True)

@app.get("/news")
def news():
    sample_news = [
        {"title": "Tech stocks surge amid AI breakthroughs", "url": "#"},
        {"title": "Tesla shares jump after earnings beat", "url": "#"},
        {"title": "Market shows resilience after global slowdown", "url": "#"},
        {"title": "Analysts bullish on cloud computing sector", "url": "#"}
    ]
    return {"articles": random.sample(sample_news, k=min(3, len(sample_news)))}

