"""
Recupera prezzi attuali e performance del portafoglio.
Fonte dati: Stooq (gratuito, illimitato, nessuna API key, stabile su GitHub Actions).
"""
import pandas_datareader.data as pdr
from datetime import datetime, timedelta
import json
import time

# Mapping ticker locali → ticker Stooq
# Stooq usa convenzioni leggermente diverse da Yahoo Finance:
# - Azioni USA: ticker minuscolo + ".us" (es. nvda.us)
# - ETF su Borsa Italiana: ticker minuscolo + ".it"
# - Indici globali / borse europee: vedi documentazione stooq.com
PORTFOLIO = [
    {"ticker": "nvda.us", "display_ticker": "NVDA", "quantity": 1,
     "name": "NVIDIA", "type": "stock", "currency": "USD"},
    {"ticker": "vwce.it", "display_ticker": "VWCE.MI", "quantity": 10,
     "name": "Vanguard FTSE All-World", "type": "etf_equity", "currency": "EUR"},
    {"ticker": "eqqq.it", "display_ticker": "EQQQ.MI", "quantity": 1,
     "name": "Invesco EQQQ Nasdaq-100", "type": "etf_equity", "currency": "EUR"},
]

ALERT_THRESHOLDS = {
    "daily_change_pct": 5.0,
    "weekly_change_pct": 10.0,
    "portfolio_change_pct": 3.0,
}


def fetch_asset_data(holding: dict) -> dict:
    """Scarica dati di un asset da Stooq."""
    ticker = holding["ticker"]
    display = holding["display_ticker"]

    try:
        end = datetime.now()
        start = end - timedelta(days=45)

        df = pdr.DataReader(ticker, "stooq", start=start, end=end)

        if df.empty:
            return {"error": f"Nessun dato per {display}", "ticker": display}

        # Stooq restituisce dati in ordine inverso (più recente in alto)
        df = df.sort_index()

        current = float(df["Close"].iloc[-1])
        prev_close = float(df["Close"].iloc[-2]) if len(df) >= 2 else current
        week_ago = float(df["Close"].iloc[-6]) if len(df) >= 6 else current
        month_ago = float(df["Close"].iloc[0])

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
            "volume": int(df["Volume"].iloc[-1]) if "Volume" in df else 0,
        }
    except Exception as e:
        return {"error": str(e)[:200], "ticker": display}


def analyze_portfolio() -> dict:
    """Analizza l'intero portafoglio e identifica eventuali alert."""
    results = []
    alerts = []
    total_value_eur_approx = 0.0

    for holding in PORTFOLIO:
        print(f"  Scarico {holding['display_ticker']} (via Stooq: {holding['ticker']})...")
        data = fetch_asset_data(holding)

        # Pausa minima tra richieste per cortesia
        time.sleep(0.5)

        if "error" in data:
            results.append({**holding, **data})
            print(f"    ERRORE: {data['error'][:100]}")
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
