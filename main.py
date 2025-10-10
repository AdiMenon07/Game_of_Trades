# backend/main.py
import time, json, random, threading, sqlite3, os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional

DB_FILE = "market.db"
ROUND_DURATION = 30*60  # 30 minutes
ROUND_START = None
ROUND_ACTIVE = False

app = FastAPI(title="Virtual Stock Market API")

# Enable CORS so Streamlit frontend can call backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# ---------- DB ----------
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS stocks (symbol TEXT PRIMARY KEY, name TEXT, price REAL, last_price REAL, updated_at INTEGER)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS portfolios (team TEXT PRIMARY KEY, cash REAL, holdings TEXT, last_updated INTEGER)""")
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
    qty: int  # +ve buy, -ve sell

class CreateTeamReq(BaseModel):
    team: str

# ---------- Seed initial stocks ----------
INITIAL_STOCKS = [
    ("APPL","Apple",1750.0), ("TSLA","Tesla",2650.0), ("GOGL","Google",2820.0),
    ("AMZN","Amazon",3300.0), ("INFY","Infosys",1500.0), ("TCS","TCS",3200.0),
    ("RELI","Reliance",2400.0), ("HDFC","HDFC Bank",1200.0)
]

@app.on_event("startup")
def startup():
    init_db()
    # Seed stocks if not present
    for sym, name, price in INITIAL_STOCKS:
        if not run_query("SELECT symbol FROM stocks WHERE symbol = ?", (sym,), fetch=True):
            run_query("INSERT INTO stocks(symbol,name,price,last_price,updated_at) VALUES(?,?,?,?,?)",
                      (sym,name,price,price,int(time.time())))
    # Start background threads
    threading.Thread(target=price_update_loop, daemon=True).start()

def price_update_loop():
    while True:
        time.sleep(2)
        if not ROUND_ACTIVE:
            continue
        rows = run_query("SELECT symbol, price FROM stocks", fetch=True)
        for sym, price in rows:
            pct = random.uniform(-0.01, 0.01)
            new_price = max(0.01, price*(1+pct))
            run_query("UPDATE stocks SET last_price=price, price=?, updated_at=? WHERE symbol=?",
                      (new_price, int(time.time()), sym))

def row_to_stockout(r):
    symbol,name,price,last_price,updated_at = r
    pct = ((price-last_price)/last_price*100) if last_price else 0
    return {"symbol":symbol,"name":name,"price":round(price,2),
            "last_price":round(last_price,2),"pct_change":round(pct,2),"updated_at":updated_at}

# ---------- Round control ----------
@app.post("/start_round")
def start_round():
    global ROUND_START, ROUND_ACTIVE
    ROUND_START = int(time.time())
    ROUND_ACTIVE = True
    return {"ok":True, "message":"Round started"}

@app.post("/end_round")
def end_round():
    global ROUND_ACTIVE
    ROUND_ACTIVE = False
    return {"ok":True, "message":"Round ended"}

# ---------- Endpoints ----------
@app.get("/stocks", response_model=List[StockOut])
def get_stocks():
    rows = run_query("SELECT symbol,name,price,last_price,updated_at FROM stocks", fetch=True)
    return [row_to_stockout(r) for r in rows]

@app.post("/init_team")
def init_team(req: CreateTeamReq):
    if run_query("SELECT team FROM portfolios WHERE team=?", (req.team,), fetch=True):
        raise HTTPException(status_code=400, detail="Team already exists")
    run_query("INSERT INTO portfolios(team,cash,holdings,last_updated) VALUES(?,?,?,?)",
              (req.team, 100000.0, "{}", int(time.time())))
    return {"ok":True, "cash":100000.0}

@app.get("/portfolio/{team}")
def get_portfolio(team: str):
    rows = run_query("SELECT cash, holdings FROM portfolios WHERE team=?", (team,), fetch=True)
    if not rows: raise HTTPException(status_code=404, detail="Team not found")
    cash, holdings_json = rows[0]
    holdings = json.loads(holdings_json) if holdings_json else {}
    stock_prices = {r[0]: r[2] for r in run_query("SELECT symbol,name,price FROM stocks", fetch=True)}
    holdings_detail = {}
    pv = cash
    for s,q in holdings.items():
        price = stock_prices.get(s,0)
        holdings_detail[s] = {"qty":q,"price":price,"value":round(q*price,2)}
        pv += q*price
    return {"team":team, "cash":round(cash,2), "holdings":holdings_detail, "portfolio_value":round(pv,2)}

@app.post("/trade")
def trade(req: TradeReq):
    global ROUND_ACTIVE, ROUND_START
    if not ROUND_ACTIVE or (ROUND_START and time.time()-ROUND_START>ROUND_DURATION):
        raise HTTPException(status_code=403, detail="Trading round has ended")
    if req.qty == 0: raise HTTPException(status_code=400, detail="qty cannot be 0")
    row = run_query("SELECT price FROM stocks WHERE symbol=?", (req.symbol,), fetch=True)
    if not row: raise HTTPException(status_code=404, detail="Stock not found")
    price = row[0][0]
    total = price*abs(req.qty)
    p = run_query("SELECT cash, holdings FROM portfolios WHERE team=?", (req.team,), fetch=True)
    if not p: raise HTTPException(status_code=404, detail="Team not found")
    cash, holdings_json = p[0]
    holdings = json.loads(holdings_json) if holdings_json else {}

    if req.qty>0:  # buy
        if cash<total: raise HTTPException(status_code=400, detail="Insufficient cash")
        cash -= total
        holdings[req.symbol] = holdings.get(req.symbol,0)+req.qty
    else:  # sell
        need = abs(req.qty)
        have = holdings.get(req.symbol,0)
        if have<need: raise HTTPException(status_code=400, detail="Insufficient holdings")
        holdings[req.symbol] -= need
        if holdings[req.symbol]==0: del holdings[req.symbol]
        cash += total
    run_query("UPDATE portfolios SET cash=?, holdings=?, last_updated=? WHERE team=?",
              (cash, json.dumps(holdings), int(time.time()), req.team))
    return {"ok":True, "cash":round(cash,2), "holdings":holdings}
