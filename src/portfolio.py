"""
Recupera prezzi attuali e performance del portafoglio.
Fonte dati: Twelve Data API (gratuita fino a 800 req/giorno con API key).
Affidabile da GitHub Actions, supporta ETF europei.
"""
import os
import requests
from datetime import datetime
import json
import time

API_KEY = os.environ.get("TWELVE_DATA_API_KEY", "")

# Mapping ticker → simbolo Twelve Data
# Convenzione Twelve Data:
#   - Azioni USA: solo ticker (es. NVDA)
#   - ETF Borsa Italiana: TICKER:MIL
#   - ETF Xetra: TICKER:XETR
#   - ETF Londra: TICKER:LSE
PORTFOLIO = [
    {"symbol": "NVDA", "display_ticker": "NVDA", "quantity": 1,
     "name": "NVIDIA", "type": "stock", "currency": "USD"},
    {"symbol": "VWCE:MIL", "display_ticker": "VWCE.MI", "quantity": 10,
     "name": "Vanguard FTSE All-World", "type": "etf_equity", "currency": "EUR"},
    {"symbol": "EQQQ:MIL", "display_ticker": "EQQQ.MI", "quantity": 1,
     "name": "Invesco EQQQ Nasdaq-100", "type": "etf_equity", "currency": "EUR"},
]

ALERT_THRESHOLDS = {
    "daily_change_pct": 5.0,
    "weekly_change_pct": 10.0,
    "portfolio_change_pct": 3.0,
}


def fetch_asset_data(holding: dict) -> dict:
    """Scarica prezzi storici 30 giorni da Twelve Data."""
    symbol = holding["symbol"]
    display = holding["display_ticker"]

    if not API_KEY:
        return {"error": "TWELVE_DATA_API_KEY non configurata", "ticker": display}

    try:
        url = "https://api.twelvedata.com/time_series"
        params = {
            "symbol": symbol,
            "interval": "1day",
            "outputsize": 30,
            "apikey": API_KEY,
        }
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()

        # Twelve Data restituisce un campo "status": "error" se qualcosa va storto
        if data.get("status") == "error":
            return {"error": f"TwelveData: {data.get('message', 'errore sconosciuto')}", "ticker": display}

        values = data.get("values", [])
        if not values or len(values) < 2:
            return {"error": f"Dati insufficienti per {display}", "ticker": display}

        # Twelve Data restituisce dal più recente al più vecchio: inverto
        values = list(reversed(values))

        closes = [float(v["close"]) for v in values]

        current = closes[-1]
        prev_close = closes[-2]
        week_ago = closes[-6] if len(closes) >= 6 else current
        month_ago = closes[0]

        daily_change = ((current - prev_close) / prev_close) * 100
        weekly_change = ((current - week_ago) / week_ago) * 100
        monthly_change = ((current - month_ago) / month_ago) * 100

        return {
            "ticker": display,
            "current": round(current, 2),
            "currency": holding["currency"],
            "daily_change_pct": round(daily_change, 2),
            "weekly_change_pct": round(weekly_change, 2),
            "monthly_change_pct": round(monthly_change, 2),
            "volume": int(values[-1].get("volume", 0)),
        }
    except Exception as e:
        return {"error": str(e)[:200], "ticker": display}


def analyze_portfolio() -> dict:
    """Analizza l'intero portafoglio e identifica eventuali alert."""
    results = []
    alerts = []
    total_value_eur_approx = 0.0

    for holding in PORTFOLIO:
        print(f"  Scarico {holding['display_ticker']} (TwelveData: {holding['symbol']})...")
        data = fetch_asset_data(holding)
        time.sleep(1)  # gentile col rate limit (max 8 req/min su free tier)

        if "error" in data:
            results.append({**holding, **data})
            print(f"    ERRORE: {data['error'][:120]}")
            continue

        position_value = data["current"] * holding["quantity"]
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
                f"⚠️ {holding['name']} ({holding['display_ticker']}) ha fatto "
                f"{data['daily_change_pct']:+.2f}% oggi"
            )
        if abs(data["weekly_change_pct"]) >= ALERT_THRESHOLDS["weekly_change_pct"]:
            alerts.append(
                f"📈 {holding['name']} ({holding['display_ticker']}) ha fatto "
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
