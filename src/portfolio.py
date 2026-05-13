"""
Recupera prezzi attuali e performance del portafoglio.
Strategia ibrida:
  - Azioni USA -> Twelve Data API (gratuita, affidabile)
  - ETF Borsa Italiana -> scraping pagina pubblica borsaitaliana.it
"""
import os
import re
import requests
from datetime import datetime
import json
import time

API_KEY = os.environ.get("TWELVE_DATA_API_KEY", "")

PORTFOLIO = [
    {
        "source": "twelvedata",
        "symbol": "NVDA",
        "display_ticker": "NVDA",
        "quantity": 1,
        "name": "NVIDIA",
        "type": "stock",
        "currency": "USD",
    },
    {
        "source": "borsaitaliana",
        "symbol": "IE00BK5BQT80",
        "display_ticker": "VWCE.MI",
        "quantity": 10,
        "name": "Vanguard FTSE All-World",
        "type": "etf_equity",
        "currency": "EUR",
    },
    {
        "source": "borsaitaliana",
        "symbol": "IE0032077012",
        "display_ticker": "EQQQ.MI",
        "quantity": 1,
        "name": "Invesco EQQQ Nasdaq-100",
        "type": "etf_equity",
        "currency": "EUR",
    },
]

ALERT_THRESHOLDS = {
    "daily_change_pct": 5.0,
    "weekly_change_pct": 10.0,
    "portfolio_change_pct": 3.0,
}


def fetch_twelvedata(symbol, display, currency):
    """Scarica dati storici 30gg da Twelve Data."""
    if not API_KEY:
        return {"error": "TWELVE_DATA_API_KEY non configurata", "ticker": display}

    url = "https://api.twelvedata.com/time_series"
    params = {
        "symbol": symbol,
        "interval": "1day",
        "outputsize": 30,
        "apikey": API_KEY,
    }

    try:
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        return {"error": "TwelveData HTTP: " + str(e)[:150], "ticker": display}

    if data.get("status") == "error":
        return {"error": "TwelveData: " + str(data.get("message", "errore")), "ticker": display}

    values = data.get("values", [])
    if not values or len(values) < 2:
        return {"error": "Dati insufficienti per " + display, "ticker": display}

    values = list(reversed(values))
    closes = [float(v["close"]) for v in values]

    current = closes[-1]
    prev_close = closes[-2]
    week_ago = closes[-6] if len(closes) >= 6 else current
    month_ago = closes[0]

    return {
        "ticker": display,
        "current": round(current, 2),
        "currency": currency,
        "daily_change_pct": round(((current - prev_close) / prev_close) * 100, 2),
        "weekly_change_pct": round(((current - week_ago) / week_ago) * 100, 2),
        "monthly_change_pct": round(((current - month_ago) / month_ago) * 100, 2),
        "volume": int(values[-1].get("volume", 0)),
    }


def fetch_borsaitaliana(isin, display, currency):
    """Scarica prezzo attuale di un ETF dalla pagina pubblica di Borsa Italiana."""
    url = "https://www.borsaitaliana.it/borsa/etf/scheda/" + isin + ".html"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "it-IT,it;q=0.9",
    }

    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        html = response.text
    except Exception as e:
        return {"error": "BorsaItaliana HTTP: " + str(e)[:150], "ticker": display}

    # Cerca il prezzo nella pagina HTML con vari pattern noti
    current = None

    # Pattern 1: span con classe specifica
    m = re.search(r'<span class="t-text -right -bold">\s*([\d\.,]+)\s*</span>', html)
    if m:
        current = m.group(1)

    # Pattern 2: cerca un numero in formato italiano dentro un tag <strong>
    if not current:
        m = re.search(r'<strong>([\d]+,\d+)</strong>\s*<span[^>]*>\s*EUR', html)
        if m:
            current = m.group(1)

    # Pattern 3: cerca "Prezzo Ultimo Contratto" o simile
    if not current:
        m = re.search(r'Ultimo Contratto[\s\S]{0,500}?([\d]+[\.,][\d]+)', html)
        if m:
            current = m.group(1)

    if not current:
        return {
            "error": "Non sono riuscito a parsare il prezzo per " + display,
            "ticker": display,
        }

    # Normalizza formato italiano (1.234,56) -> float
    price_str = current.replace(".", "").replace(",", ".")
    try:
        current_price = float(price_str)
    except ValueError:
        return {
            "error": "Prezzo non parsabile: " + current,
            "ticker": display,
        }

    return {
        "ticker": display,
        "current": round(current_price, 2),
        "currency": currency,
        "daily_change_pct": 0.0,
        "weekly_change_pct": 0.0,
        "monthly_change_pct": 0.0,
        "volume": 0,
        "note": "Prezzo da Borsa Italiana (storico non disponibile)",
    }


def fetch_asset_data(holding):
    """Dispatcher che chiama la source corretta in base al campo 'source'."""
    source = holding["source"]
    symbol = holding["symbol"]
    display = holding["display_ticker"]
    currency = holding["currency"]

    if source == "twelvedata":
        return fetch_twelvedata(symbol, display, currency)
    elif source == "borsaitaliana":
        return fetch_borsaitaliana(symbol, display, currency)
    else:
        return {"error": "Source sconosciuta: " + source, "ticker": display}


def analyze_portfolio():
    """Analizza l'intero portafoglio."""
    results = []
    alerts = []
    total_value_eur_approx = 0.0

    for holding in PORTFOLIO:
        print("  Scarico " + holding["display_ticker"] + " (" + holding["source"] + ": " + holding["symbol"] + ")...")
        data = fetch_asset_data(holding)
        time.sleep(1)

        if "error" in data:
            results.append({**holding, **data})
            print("    ERRORE: " + data["error"][:120])
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

        enriched = {**holding, **data}
        enriched["position_value"] = round(position_value, 2)
        enriched["position_value_eur_approx"] = round(position_value_eur, 2)
        results.append(enriched)

        note = ""
        if data.get("note"):
            note = " -- " + data["note"]
        print("    OK: " + str(data["current"]) + " " + data["currency"] +
              " (" + ("+" if data["daily_change_pct"] >= 0 else "") +
              str(data["daily_change_pct"]) + "%)" + note)

        if abs(data["daily_change_pct"]) >= ALERT_THRESHOLDS["daily_change_pct"]:
            alerts.append(
                "Attenzione: " + holding["name"] + " (" + holding["display_ticker"] +
                ") ha fatto " + str(data["daily_change_pct"]) + "% oggi"
            )
        if abs(data["weekly_change_pct"]) >= ALERT_THRESHOLDS["weekly_change_pct"]:
            alerts.append(
                "Trend: " + holding["name"] + " (" + holding["display_ticker"] +
                ") ha fatto " + str(data["weekly_change_pct"]) + "% in 5 giorni"
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
