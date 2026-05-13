"""
Recupera prezzi attuali e performance del portafoglio.
Fonte dati: Stooq via HTTP diretto (CSV pubblico, gratuito, illimitato, no API key).
Funziona da GitHub Actions senza rate limit.
"""
import requests
import pandas as pd
from io import StringIO
from datetime import datetime, timedelta
import json
import time

# Mapping ticker locali → ticker Stooq
# Stooq convenzioni:
#   - Azioni USA: ticker minuscolo + ".us"  (es. nvda.us)
#   - ETF/azioni su Borsa Italiana: ticker minuscolo + ".it"
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


def fetch_stooq_csv(ticker: str) -> pd.DataFrame:
    """Scarica i dati storici di un ticker da Stooq come CSV."""
    url = f"https://stooq.com/q/d/l/?s={ticker}&i=d"
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; FinecoAgent/1.0)"
    }
    response = requests.get(url, headers=headers, timeout=15)
    response.raise_for_status()

    # Se Stooq non trova il ticker, restituisce un CSV vuoto o messaggio di errore
    if not response.text or "No data" in response.text or len(response.text) < 50:
        raise ValueError(f"Stooq non ha dati per {ticker}")

    df = pd.read_csv(StringIO(response.text))
    if df.empty or "Close" not in df.columns:
        raise ValueError(f"CSV malformato per {ticker}")

    df["Date"] = pd.to_datetime(df["Date"])
    df = df.sort_values("Date").reset_index(drop=True)
    return df


def fetch_asset_data(holding: dict) -> dict:
    """Scarica dati di un asset da Stooq con prezzi calcolati su finestra ~30gg."""
    ticker = holding["ticker"]
    display = holding["display_ticker"]

    try:
        df = fetch_stooq_csv(ticker)

        # Prendi solo gli ultimi 30 giorni di trading per i calcoli
        df_recent = df.tail(30)

        if len(df_recent) < 2:
            return {"error": f"Dati insufficienti per {display}", "ticker": display}

        current = float(df_recent["Close"].iloc[-1])
        prev_close = float(df_recent["Close"].iloc[-2])
        week_ago = float(df_recent["Close"].iloc[-6]) if len(df_recent) >= 6 else current
        month_ago = float(df_recent["Close"].iloc[0])

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
            "volume": int(df_recent["Volume"].iloc[-1]) if "Volume" in df_recent else 0,
        }
    except Exception as e:
        return {"error": str(e)[:200], "ticker": display}


def analyze_portfolio() -> dict:
    """Analizza l'intero portafoglio e identifica eventuali alert."""
    results = []
    alerts = []
    total_value_eur_approx = 0.0

    for holding in PORTFOLIO:
        print(f"  Scarico {holding['display_ticker']} (Stooq: {holding['ticker']})...")
        data = fetch_asset_data(holding)
        time.sleep(0.5)  # cortesia verso Stooq

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
