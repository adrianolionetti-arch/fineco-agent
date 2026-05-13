"""
Recupera prezzi attuali e performance del portafoglio.
Fonte dati: Yahoo Finance (gratuito, nessuna API key).
Con retry per gestire rate limit di GitHub Actions.
"""
import yfinance as yf
from datetime import datetime, timedelta
import json
import os
import time
import random

PORTFOLIO = [
    {"ticker": "NVDA", "quantity": 1, "name": "NVIDIA", "type": "stock"},
    {"ticker": "VWCE.MI", "quantity": 10, "name": "Vanguard FTSE All-World", "type": "etf_equity"},
    {"ticker": "EQQQ.MI", "quantity": 1, "name": "Invesco EQQQ Nasdaq-100", "type": "etf_equity"},
]

ALERT_THRESHOLDS = {
    "daily_change_pct": 5.0,
    "weekly_change_pct": 10.0,
    "portfolio_change_pct": 3.0,
}


def fetch_asset_data(ticker: str, max_retries: int = 4) -> dict:
    """Scarica dati di un asset con retry per gestire rate limit Yahoo Finance."""
    for attempt in range(max_retries):
        try:
            # Pausa progressiva tra tentativi per evitare rate limit
            if attempt > 0:
                wait = (2 ** attempt) + random.uniform(0, 2)
                print(f"  Retry {attempt}/{max_retries-1} per {ticker} tra {wait:.1f}s...")
                time.sleep(wait)
            else:
                # Piccola pausa iniziale tra ticker per non saturare
                time.sleep(random.uniform(1, 3))

            t = yf.Ticker(ticker)
            hist = t.history(period="1mo")

            if hist.empty:
                if attempt < max_retries - 1:
                    continue
                return {"error": f"Nessun dato per {ticker} dopo {max_retries} tentativi"}

            current = float(hist["Close"].iloc[-1])
            prev_close = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else current
            week_ago = float(hist["Close"].iloc[-6]) if len(hist) >= 6 else current
            month_ago = float(hist["Close"].iloc[0])

            daily_change = ((current - prev_close) / prev_close) * 100
            weekly_change = ((current - week_ago) / week_ago) * 100
            monthly_change = ((current - month_ago) / month_ago) * 100

            # info() può fallire indipendentemente
            currency = "USD"
            try:
                info = t.info
                currency = info.get("currency", "USD")
            except Exception:
                # Inferenza dal ticker
                if ticker.endswith(".MI") or ticker.endswith(".DE"):
                    currency = "EUR"
                elif ticker.endswith(".L"):
                    currency = "GBP"

            return {
                "ticker": ticker,
                "current": round(current, 2),
                "currency": currency,
                "daily_change_pct": round(daily_change, 2),
                "weekly_change_pct": round(weekly_change, 2),
                "monthly_change_pct": round(monthly_change, 2),
                "volume": int(hist["Volume"].iloc[-1]) if "Volume" in hist else 0,
            }
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"  Errore {ticker} tentativo {attempt+1}: {str(e)[:100]}")
                continue
            return {"error": str(e), "ticker": ticker}

    return {"error": f"Esaurito i retry per {ticker}", "ticker": ticker}


def analyze_portfolio() -> dict:
    """Analizza l'intero portafoglio e identifica eventuali alert."""
    results = []
    alerts = []
    total_value_eur_approx = 0.0

    for holding in PORTFOLIO:
        print(f"  Scarico {holding['ticker']}...")
        data = fetch_asset_data(holding["ticker"])
        if "error" in data:
            results.append({**holding, **data})
            print(f"    ERRORE: {data['error'][:100]}")
            continue

        position_value = data["current"] * holding["quantity"]
        # Conversione approssimativa
        if data["currency"] == "USD":
            fx = 0.92
        elif data["currency"] == "GBP":
            fx = 1.17
        else:
            fx = 1.0
        position_value_eur = position_value * fx
        total_value_eur_approx += position_value_eur

        enriched = {
            **holding,
            **data,
            "position_value": round(position_value, 2),
            "position_value_eur_approx": round(position_value_eur, 2),
        }
        results.append(enriched)
        print(f"    OK: {data['current']} {data['currency']} ({data['daily_change_pct']:+.2f}%)")

        if abs(data["daily_change_pct"]) >= ALERT_THRESHOLDS["daily_change_pct"]:
            alerts.append(
                f"⚠️ {holding['name']} ({holding['ticker']}) ha fatto "
                f"{data['daily_change_pct']:+.2f}% oggi"
            )
        if abs(data["weekly_change_pct"]) >= ALERT_THRESHOLDS["weekly_change_pct"]:
            alerts.append(
                f"📈 {holding['name']} ({holding['ticker']}) ha fatto "
                f"{data['weekly_change_pct']:+.2f}% negli ultimi 5 giorni"
            )

    return {
        "holdings": results,
        "alerts": alerts,
        "total_value_eur_approx": round(total_value_eur_approx, 2),
        "timestamp": datetime.now().isoformat(),
    }


if __name__ == "__main__":
    data = analyze_portfolio()
    print(json.dumps(data, indent=2, ensure_ascii=False))
