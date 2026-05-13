"""
Recupera prezzi attuali e performance del portafoglio.
Strategia ibrida:
  - Azioni USA → Twelve Data API (gratuita, affidabile)
  - ETF Borsa Italiana → API ufficiale Borsa Italiana (gratuita, ufficiale)
"""
import os
import requests
from datetime import datetime, timedelta
import json
import time

API_KEY = os.environ.get("TWELVE_DATA_API_KEY", "")

PORTFOLIO = [
    # Source: "twelvedata" per USA, "borsaitaliana" per ETF Milano
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
        "symbol": "IE00BK5BQT80",  # ISIN
        "display_ticker": "VWCE.MI",
        "quantity": 10,
        "name": "Vanguard FTSE All-World",
        "type": "etf_equity",
        "currency": "EUR",
    },
    {
        "source": "borsaitaliana",
        "symbol": "IE0032077012",  # ISIN
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


def fetch_twelvedata(symbol: str, display: str, currency: str) -> dict:
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
    response = requests.get(url, params=params, timeout=15)
    response.raise_for_status()
    data = response.json()

    if data.get("status") == "error":
        return {"error": f"TwelveData: {data.get('message', 'errore')}", "ticker": display}

    values = data.get("values", [])
    if not values or len(values) < 2:
        return {"error": f"Dati insufficienti per {display}", "ticker": display}

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


def fetch_borsaitaliana(isin: str, display: str, currency: str) -> dict:
    """Scarica dati storici di un ETF da Borsa Italiana via endpoint pubblico."""
    # Borsa Italiana espone endpoint pubblici per i grafici degli ETF.
    # Usiamo l'endpoint che restituisce JSON con i prezzi storici.
    end = datetime.now()
    start = end - timedelta(days=45)

    url = f"https://charts.borsaitaliana.it/charts/services/ChartWService.asmx/GetPricesWithVolume"
    params = {
        "request": json.dumps({
            "SampleTime": "1d",
            "TimeFrame": "1m",
            "RequestedDataSetType": "ohlc",
            "ChartPriceType": "price",
            "Key": f"{isin}.MOT",  # MOT = mercato obbligazionario, ma funziona anche per ETF
            "OffSet": 0,
            "FromDate": None,
            "ToDate": None,
            "UseDelay": True,
            "KeyType": "Topic",
            "KeyType2": "Topic",
            "Language": "it-IT",
        })
    }

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
    }

    try:
        response = requests.get(url, params=params, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()

        # L'endpoint potrebbe non funzionare per ETF, fallback all'approccio "scrape page"
        prices = data.get("d", [])
        if not prices:
            return _fetch_borsaitaliana_fallback(isin, display, currency)

        closes = [float(p[4]) for p in prices if len(p) >= 5]
        if len(closes) < 2:
            return _fetch_borsaitaliana_fallback(isin, display, currency)

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
            "volume": 0,
        }
    except Exception as e:
        return _fetch_borsaitaliana_fallback(isin, display, currency, error=str(e))


def _fetch_borsaitaliana_fallback(isin: str, display: str, currency: str, error: str = "") -> dict:
    """
    Fallback: scarica la pagina pubblica dell'ETF su Borsa Italiana e parsa il prezzo.
    Endpoint non-API ma stabile, simile a quello che apri nel browser.
    """
    try:
        url = f"https://www.borsaitaliana.it/borsa/etf/scheda/{isin}.html"
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "it-IT,it;q=0.9",
        }
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        html = response.text

        # Cerca il prezzo nella pagina HTML — pattern stabile su Borsa Italiana
        import re
        match = re.search(r'<span class="t-text -right -bold">\s*([\d\.,]+)\s*</span>', html)
        if not match:
            # Pattern alternativo
            match = re.search(r'<strong>([\d]+,\d+)</strong>\s*<span[^>]*>EUR</span>', html)

        if not match:
            return {"error": f"Non sono riuscito a parsare il prezzo da Borsa Italiana per {display}", "ticker": display}

        price_str = match.group(1).replace(".", "").replace(",", ".")
        current = float(price_str)

        # Per ora restituiamo solo il prezzo attuale senza storico
        # (Borsa Italiana non espone facilmente storici in modo affidabile)
        return {
            "ticker": display,
            "current": round(current, 2),
            "currency": currency,
            "daily_change_pct": 0.0,
            "weekly_change_pct": 0.0,
            "monthly_change_pct": 0
