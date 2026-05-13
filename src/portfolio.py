"""
Recupera prezzi attuali e performance del portafoglio.
Fonte dati: Yahoo Finance (gratuito, nessuna API key).
"""
import yfinance as yf
from datetime import datetime, timedelta
import json
import os

# CONFIGURAZIONE PORTAFOGLIO
# Modifica questa lista con i TUOI effettivi ticker/quantità.
# I ticker qui sotto sono ESEMPI — sostituiscili con quelli reali dei tuoi ETF su Fineco.
# Come trovare il ticker: su Fineco ogni strumento ha un codice ISIN, cerchialo su finance.yahoo.com
# e usa il simbolo (es. "VWCE.DE", "IWDA.AS", "NVDA").
PORTFOLIO = [
    {"ticker": "1NVDA.MI", "quantity": 1, "name": "NVIDIA", "type": "stock"},
    {"ticker": "VWCE.MI", "quantity": 10, "name": "Vanguard FTSE All-World", "type": "etf_equity"},
    {"ticker": "EQQQ.MI", "quantity": 1, "name": "Invesco EQQQ Nasdaq-100", "type": "etf_equity"},
]

# Soglie per triggerare un alert
ALERT_THRESHOLDS = {
    "daily_change_pct": 5.0,      # Alert se un asset fa +/- 5% in un giorno
    "weekly_change_pct": 10.0,    # Alert se +/- 10% in una settimana
    "portfolio_change_pct": 3.0,  # Alert se l'intero portafoglio varia più del 3% in un giorno
}


def fetch_asset_data(ticker: str) -> dict:
    """Scarica dati attuali e storici di un asset."""
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="1mo")
        if hist.empty:
            return {"error": f"Nessun dato per {ticker}"}

        current = float(hist["Close"].iloc[-1])
        prev_close = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else current
        week_ago = float(hist["Close"].iloc[-6]) if len(hist) >= 6 else current
        month_ago = float(hist["Close"].iloc[0])

        daily_change = ((current - prev_close) / prev_close) * 100
        weekly_change = ((current - week_ago) / week_ago) * 100
        monthly_change = ((current - month_ago) / month_ago) * 100

        info = t.info
        currency = info.get("currency", "USD")

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
        return {"error": str(e), "ticker": ticker}


def analyze_portfolio() -> dict:
    """Analizza l'intero portafoglio e identifica eventuali alert."""
    results = []
    alerts = []
    total_value_eur_approx = 0.0

    for holding in PORTFOLIO:
        data = fetch_asset_data(holding["ticker"])
        if "error" in data:
            results.append({**holding, **data})
            continue

        position_value = data["current"] * holding["quantity"]
        # conversione grezza USD->EUR (solo per display, usa 1 per EUR, 0.92 per USD)
        fx = 0.92 if data["currency"] == "USD" else 1.0
        position_value_eur = position_value * fx
        total_value_eur_approx += position_value_eur

        enriched = {
            **holding,
            **data,
            "position_value": round(position_value, 2),
            "position_value_eur_approx": round(position_value_eur, 2),
        }
        results.append(enriched)

        # Check alert soglie
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
