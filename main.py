from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def home():
    return {"message": "Stock Screener is running!"}

@app.get("/scan/")
def get_latest_scan():
    return {"message": "Scanning stocks..."}  # Replace with actual stock scanner response
import requests
from bs4 import BeautifulSoup
import yfinance as yf
import pandas as pd
import uvicorn
from apscheduler.schedulers.background import BackgroundScheduler
import json
import os

app = FastAPI()

# ✅ File to store last valid results
RESULTS_FILE = "latest_results.json"

# ✅ Load last results if available
if os.path.exists(RESULTS_FILE):
    with open(RESULTS_FILE, "r") as f:
        latest_results = json.load(f)
else:
    latest_results = {"gainers": [], "losers": []}

# ✅ Function to fetch latest Nifty F&O stocks
def fetch_nifty_fo_stocks():
    url = "https://www.nseindia.com/products-services/equity-derivatives-list-underlyings-information"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    with requests.Session() as session:
        session.get(url, headers=headers)  # Establish session
        response = session.get(url, headers=headers)
        if response.status_code != 200:
            return []

        soup = BeautifulSoup(response.content, "html.parser")
        table = soup.find("table")
        if not table:
            return []

        stocks = []
        for row in table.find_all("tr")[1:]:  # Skip the header row
            columns = row.find_all("td")
            if columns:
                symbol = columns[1].text.strip()
                stocks.append(symbol + ".NS")  # Append '.NS' for NSE format

        return stocks

# Function to fetch stock data
def get_stock_data(ticker: str):
    stock = yf.Ticker(ticker)
    df = stock.history(period="10d")  # Fetch last 10 days data
    return df

# Function to calculate Camarilla levels
def calculate_camarilla_levels(df):
    last_close = df["Close"].iloc[-2]
    last_high = df["High"].iloc[-2]
    last_low = df["Low"].iloc[-2]

    r4 = last_close + (1.1 * (last_high - last_low))
    s4 = last_close - (1.1 * (last_high - last_low))

    return r4, s4

# Function to check stock conditions
def check_stock_conditions(ticker):
    df = get_stock_data(ticker)
    if len(df) < 4:
        return None  # Not enough data

    last_3_volumes = df["Volume"].iloc[-4:-1]
    current_volume = df["Volume"].iloc[-1]

    r4, s4 = calculate_camarilla_levels(df)
    last_close = df["Close"].iloc[-1]

    print(f"Checking {ticker}: Close={last_close}, Volume={current_volume}, Avg 3-Day Vol={last_3_volumes.mean()}, R4={r4}, S4={s4}")

    if current_volume > last_3_volumes.mean():
        if last_close > r4:
            return {
                "ticker": ticker.replace(".NS", ""),
                "last_close": last_close,
                "current_volume": current_volume,
                "avg_last_3_volume": last_3_volumes.mean(),
                "r4": r4,
                "s4": s4,
                "status": "gainer"
            }
        elif last_close < s4:
            return {
                "ticker": ticker.replace(".NS", ""),
                "last_close": last_close,
                "current_volume": current_volume,
                "avg_last_3_volume": last_3_volumes.mean(),
                "r4": r4,
                "s4": s4,
                "status": "loser"
            }
    return None

# ✅ Background Task: Automatically scan stocks every 3 minutes
def update_stock_scanner():
    global latest_results
    nifty_fo_stocks = fetch_nifty_fo_stocks()

    if not nifty_fo_stocks:
        print("❌ Failed to fetch Nifty F&O stocks")
        return

    gainers, losers = [], []

    for stock in nifty_fo_stocks:
        result = check_stock_conditions(stock)
        if result:
            if result["status"] == "gainer":
                gainers.append(result)
            elif result["status"] == "loser":
                losers.append(result)

    # Save last valid results
    if gainers or losers:
        latest_results = {"gainers": gainers, "losers": losers}
        with open(RESULTS_FILE, "w") as f:
            json.dump(latest_results, f, indent=4)

    print("✅ Stock scanner updated successfully!")

# ✅ Start the scheduler
scheduler = BackgroundScheduler()
scheduler.add_job(update_stock_scanner, "interval", minutes=3)
scheduler.start()

# ✅ API Endpoint: Get Latest Results
@app.get("/scan/")
def get_latest_scan():
    return latest_results if latest_results["gainers"] or latest_results["losers"] else {"message": "No stocks met the criteria yet"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
