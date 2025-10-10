import random
import sqlite3
import threading
import time
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import requests
import os

DB_FILE = "market.db"
PRICE_UPDATE_INTERVAL = 20  # seconds

app = FastAPI(title="Game of Trades - Stock Market API")
db_lock = threading.Lock()

# ---------- MODELS ----------
class TradeRequest(BaseModel):
    team: str
    symbol: str
    qty: int

class InitTeamRequest(BaseModel):
    team: str

# ---------- DATABASE ----------
def init_db():
    with db_lock:
        conn = sqlite3.connect(DB_FILE)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS teams (
                name TEXT PRIMARY KEY,
                cash REAL DEFAULT 100000.0
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS holdings (
                team TEXT,
                symbol TEXT,
                qty INTEGER,
                FOREIGN KEY(team) REFERENCES teams(name)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS stocks (
                symbol TEXT PRIMARY KEY,
                name TEXT,
                price REAL,
                pct_change REAL
            )
        """)
        conn.commit()
        conn.close()
    seed_stocks()

def seed_stocks():
    with db_lock:
        conn = sqlite3.connect(DB_FILE)
        cur = conn.cursor()
        stocks = [
            ("INFY", "Infosys", 1600.0),
            ("TCS", "TCS", 3500.0),
            ("HDFC", "HDFC Bank", 1700.0),
            ("RELI", "Reliance", 2700.0),
            ("ADAN", "Adani Ent.", 2900.0)
        ]
        for s in stocks:
            cur.execute("INSERT OR IGNORE INTO stocks(symbol, name, price, pct_change) VALUES (?, ?, ?, 0)", s)
        conn.commit()
        conn.close()

init_db()

# ---------- STOCK UPDATER THREAD ----------
def update_stock_prices():
    while True:
        with db_lock:
            conn = sqlite3.connect(DB_FILE)
            cur = conn.cursor()
            cur.execute("SELECT symbol, price FROM stocks")
            for sym, price in cur.fetchall():
                change = random.uniform(-0.02, 0.02)
                new_price = max(10.0, price * (1 + change))
                cur.execute("UPDATE stocks SET price=?, pct_change=? WHERE symbol=?", (new_price, round(change*100, 2), sym))
            conn.commit()
            conn.close()
        time.sleep(PRICE_UPDATE_INTERVAL)

threading.Thread(target=update_stock_prices, daemon=True).start()

# ---------- HELPERS ----------
def get_team_portfolio(team):
    with db_lock:
        conn = sqlite3.connect(DB_FILE)
        cur = conn.cursor()
        cur.execute("SELECT cash FROM teams WHERE name=?", (team,))
        row = cur.fetchone()
        if not row:
            conn.close()
            return None
        cash = row[0]
        cur.execute("SELECT symbol, qty FROM holdings WHERE team=?", (team,))
        holdings = {sym: {"qty": qty} for sym, qty in cur.fetchall()}
        conn.close()
        return {"cash": cash, "holdings": holdings}

# ---------- API ENDPOINTS ----------

@app.get("/")
def home():
    return {"message": "Game of Trades API is running"}

@app.post("/init_team")
def init_team(req: InitTeamRequest):
    team = req.team.strip()
    if not team:
        raise HTTPException(status_code=400, detail="Invalid team name")

    with db_lock:
        conn = sqlite3.connect(DB_FILE)
        cur = conn.cursor()
        cur.execute("INSERT OR IGNORE INTO teams(name, cash) VALUES (?, 100000.0)", (team,))
        conn.commit()
        conn.close()

    return {"team": team, "cash": 100000.0}

@app.get("/portfolio/{team}")
def get_portfolio(team: str):
    portfolio = get_team_portfolio(team)
    if not portfolio:
        raise HTTPException(status_code=404, detail="Team not found")
    return portfolio

@app.post("/trade")
def trade(req: TradeRequest):
    team, symbol, qty = req.team, req.symbol, req.qty
    with db_lock:
        conn = sqlite3.connect(DB_FILE)
        cur = conn.cursor()

        # Verify team and stock
        cur.execute("SELECT cash FROM teams WHERE name=?", (team,))
        row = cur.fetchone()
        if not row:
            conn.close()
            raise HTTPException(status_code=404, detail="Team not found")
        cash = row[0]

        cur.execute("SELECT price FROM stocks WHERE symbol=?", (symbol,))
        row = cur.fetchone()
        if not row:
            conn.close()
            raise HTTPException(status_code=404, detail="Stock not found")
        price = row[0]

        cost = qty * price

        # BUY
        if qty > 0:
            if cash < cost:
                conn.close()
                raise HTTPException(status_code=400, detail="Insufficient funds")
            cur.execute("UPDATE teams SET cash = cash - ? WHERE name=?", (cost, team))
            cur.execute("INSERT OR IGNORE INTO holdings(team, symbol, qty) VALUES (?, ?, 0)", (team, symbol))
            cur.execute("UPDATE holdings SET qty = qty + ? WHERE team=? AND symbol=?", (qty, team, symbol))
        else:  # SELL
            cur.execute("SELECT qty FROM holdings WHERE team=? AND symbol=?", (team, symbol))
            row = cur.fetchone()
            if not row or row[0] < abs(qty):
                conn.close()
                raise HTTPException(status_code=400, detail="Not enough holdings")
            cur.execute("UPDATE holdings SET qty = qty + ? WHERE team=? AND symbol=?", (qty, team, symbol))
            cur.execute("UPDATE teams SET cash = cash + ? WHERE name=?", (abs(cost), team))
        conn.commit()
        conn.close()

    return {"success": True, "symbol": symbol, "qty": qty}

@app.get("/stocks")
def get_stocks():
    with db_lock:
        conn = sqlite3.connect(DB_FILE)
        cur = conn.cursor()
        cur.execute("SELECT symbol, name, price, pct_change FROM stocks")
        data = [{"symbol": s, "name": n, "price": round(p, 2), "pct_change": c} for s, n, p, c in cur.fetchall()]
        conn.close()
    return data

@app.get("/leaderboard")
def leaderboard():
    with db_lock:
        conn = sqlite3.connect(DB_FILE)
        cur = conn.cursor()
        cur.execute("SELECT name, cash FROM teams")
        teams = cur.fetchall()
        leaderboard = []
        for name, cash in teams:
            cur.execute("""
                SELECT h.symbol, h.qty, s.price 
                FROM holdings h JOIN stocks s ON h.symbol = s.symbol
                WHERE h.team=?
            """, (name,))
            total = cash + sum(q * p for _, q, p in cur.fetchall())
            leaderboard.append({"team": name, "value": round(total, 2)})
        conn.close()
    leaderboard.sort(key=lambda x: x["value"], reverse=True)
    return leaderboard

@app.get("/news")
def market_news():
    try:
        res = requests.get("https://newsapi.org/v2/top-headlines?category=business&language=en&apiKey=demo", timeout=5)
        return res.json()
    except:
        return {"articles": [
            {"title": "Markets open steady amid tech rally", "url": "#"},
            {"title": "Energy stocks surge after oil price hike", "url": "#"}
        ]}
