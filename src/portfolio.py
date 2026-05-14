"""
portfolio.py — recupera prezzi attuali e performance del portafoglio.

Strategia:
  - Fonte: yfinance (gratis, no API key). Listing primario Borsa Italiana (.MI),
    fallback Xetra (.DE) o NASDAQ (NVDA) se Milano non risponde.
  - Retry 3x con backoff esponenziale per gestire i blip transitori di Yahoo.
  - Conversione USD->EUR live (niente cambi hardcoded).
  - Se proprio non c'è dato: record con "error" esplicito, NON inventiamo prezzi.

Schema di ritorno IDENTICO al vecchio file (analyze_portfolio) per compatibilità
con briefing.py, journal.py, dashboard_builder.py, emailer.py.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from typing import Optional

import yfinance as yf

log = logging.getLogger(__name__)


# Portafoglio: stesso schema concettuale di prima.
# - "primary" : ticker preferito (la borsa dove ho comprato, di solito Milano)
# - "fallback": ticker alternativo se il primario non risponde
# - "fx_convert": True se il fallback è in valuta diversa da EUR
PORTFOLIO = [
    {
        "symbol": "NVDA",
        "display_ticker": "1NVDA.MI",
        "primary": "1NVDA.MI",             # NVIDIA su Borsa Italiana
        "fallback": "NVDA",                # NASDAQ in USD se Milano non risponde
        "fx_convert": True,
        "quantity": 1,
        "name": "NVIDIA",
        "type": "stock",
        "currency": "EUR",                 # valuta di display, post-conversione
    },
    {
        "symbol": "IE00BK5BQT80",
        "display_ticker": "VWCE.MI",
        "primary": "VWCE.MI",
        "fallback": "VWCE.DE",             # Xetra in EUR
        "fx_convert": False,
        "quantity": 10,
        "name": "Vanguard FTSE All-World",
        "type": "etf_equity",
        "currency": "EUR",
    },
    {
        # Invesco EQQQ Nasdaq-100 UCITS ETF Acc - ISIN IE00BFZXGZ54
        # NB: versione ad accumulazione (Acc).
        # NON la versione a distribuzione (ISIN IE0032077012, ticker EQQQ.MI).
        "symbol": "IE00BFZXGZ54",
        "display_ticker": "EQAC.MI",
        "primary": "EQAC.MI",
        "fallback": "EQQB.DE",             # stessa quota su Xetra, in EUR
        "fx_convert": False,
        "quantity": 1,
        "name": "Invesco EQQQ Nasdaq-100 (Acc)",
        "type": "etf_equity",
        "currency": "EUR",
    },
]

ALERT_THRESHOLDS = {
    "daily_change_pct": 5.0,
    "weekly_change_pct": 10.0,
    "portfolio_change_pct": 3.0,
}


# --- helpers di fetch -----------------------------------------------------

def _fetch_history(ticker: str, period: str = "1mo", attempts: int = 3,
                   backoff: float = 1.5):
    """
    Scarica lo storico di un ticker da yfinance, con retry.
    Ritorna (DataFrame|None, currency|None, error|None).
    Lo storico serve per calcolare daily/weekly/monthly change.
    """
    last_err: Optional[str] = None
    for i in range(attempts):
        try:
            tk = yf.Ticker(ticker)
            hist = tk.history(period=period, auto_adjust=False)
            if not hist.empty:
                # Yahoo a volte ritorna l'ultima riga del giorno corrente con Close=NaN
                # (il dato di chiusura non e' ancora consolidato). Scarto le righe
                # con Close NaN in coda per non leggere prezzi sporchi.
                hist = hist.dropna(subset=["Close"])
            if hist is not None and not hist.empty:
                currency = (tk.fast_info.get("currency") or "EUR").upper()
                return hist, currency, None
            last_err = "empty history"
        except Exception as e:
            last_err = str(e)[:150]
        if i < attempts - 1:
            time.sleep(backoff * (i + 1))
    return None, None, last_err


def _get_fx_rate(currency: str) -> Optional[float]:
    """Cambio LIVE da Yahoo, non hardcoded. Ritorna None se Yahoo non risponde."""
    if currency == "EUR":
        return 1.0
    pair = f"{currency}EUR=X"
    hist, _, err = _fetch_history(pair, period="5d", attempts=2)
    if hist is None or hist.empty:
        log.warning("FX %s->EUR non disponibile (%s)", currency, err)
        return None
    return float(hist["Close"].iloc[-1])


def _compute_changes(hist) -> tuple[float, float, float]:
    """
    Da uno storico di chiusure calcola le variazioni daily/weekly/monthly in %.
    Se non ci sono abbastanza punti, la variazione corrispondente e' 0.0.
    """
    closes = hist["Close"].tolist()
    if len(closes) < 2:
        return 0.0, 0.0, 0.0
    current = closes[-1]
    daily = ((current - closes[-2]) / closes[-2]) * 100
    week_ago = closes[-6] if len(closes) >= 6 else closes[0]
    weekly = ((current - week_ago) / week_ago) * 100 if week_ago else 0.0
    month_ago = closes[0]
    monthly = ((current - month_ago) / month_ago) * 100 if month_ago else 0.0
    return daily, weekly, monthly


# --- fetcher per singola posizione ---------------------------------------

def fetch_asset_data(holding: dict) -> dict:
    """
    Recupera prezzo + variazioni per una posizione del portafoglio.
    Ritorna un dict con LE STESSE chiavi del vecchio fetch_asset_data:
    ticker, current, currency, daily_change_pct, weekly_change_pct,
    monthly_change_pct, volume, note?, error?
    """
    display = holding["display_ticker"]
    primary = holding["primary"]
    fallback = holding["fallback"]

    # 1deg tentativo: ticker primario (.MI)
    hist, native_ccy, err = _fetch_history(primary)
    source_used = "primary"
    ticker_used = primary

    # 2deg tentativo: fallback exchange
    if hist is None or hist.empty:
        log.warning("Primario %s fallito (%s); provo fallback %s",
                    primary, err, fallback)
        hist, native_ccy, err = _fetch_history(fallback)
        source_used = "fallback"
        ticker_used = fallback

    if hist is None or hist.empty:
        return {
            "error": f"Prezzo non disponibile (ultimo: {err})",
            "ticker": display,
        }

    # Estraggo prezzo + variazioni in valuta nativa
    price_native = float(hist["Close"].iloc[-1])
    daily, weekly, monthly = _compute_changes(hist)
    volume = int(hist["Volume"].iloc[-1]) if "Volume" in hist.columns else 0

    # Conversione in EUR se necessario
    if native_ccy != "EUR" and holding.get("fx_convert"):
        fx = _get_fx_rate(native_ccy)
        if fx is None:
            return {
                "error": f"Cambio {native_ccy}->EUR non disponibile",
                "ticker": display,
            }
        price_eur = price_native * fx
        # Le variazioni % restano valide anche dopo conversione (sono adimensionali).
        currency_out = "EUR"
    elif native_ccy == "EUR":
        price_eur = price_native
        currency_out = "EUR"
    else:
        # Caso edge: fallback in valuta non EUR ma fx_convert=False.
        # Non dovrebbe succedere con la PORTFOLIO attuale, ma ci tuteliamo.
        log.warning("Currency inattesa %s per %s - niente conversione configurata",
                    native_ccy, ticker_used)
        price_eur = price_native
        currency_out = native_ccy

    note = None
    if source_used == "fallback":
        note = f"Prezzo da fallback {ticker_used} (primary {primary} non disponibile)"

    out = {
        "ticker": display,
        "current": round(price_eur, 2),
        "currency": currency_out,
        "daily_change_pct": round(daily, 2),
        "weekly_change_pct": round(weekly, 2),
        "monthly_change_pct": round(monthly, 2),
        "volume": volume,
        "_source": source_used,            # campo extra utile per debug, non breaking
        "_ticker_used": ticker_used,
    }
    if note:
        out["note"] = note
    return out


# --- entrypoint principale (stesso nome di prima) -------------------------

def analyze_portfolio() -> dict:
    """
    Analizza l'intero portafoglio.
    Ritorna lo stesso schema del vecchio analyze_portfolio:
    {holdings: [...], alerts: [...], total_value_eur_approx: ..., timestamp: ...}
    """
    results: list[dict] = []
    alerts: list[str] = []
    total_value_eur = 0.0

    for holding in PORTFOLIO:
        print(f"  Scarico {holding['display_ticker']} "
              f"(primary={holding['primary']}, fallback={holding['fallback']})...")
        data = fetch_asset_data(holding)
        # Niente sleep aggressivo: yfinance non ha rate limit stretto come Twelve Data.

        if "error" in data:
            results.append({**holding, **data})
            print(f"    ERRORE: {data['error'][:120]}")
            # Aggiungo un alert: una posizione "muta" e' informazione, non silenzio.
            alerts.append(
                f"Prezzo non disponibile per {holding['name']} "
                f"({holding['display_ticker']}): {data['error']}"
            )
            continue

        # Calcolo valore posizione (price_eur e' gia' in EUR a questo punto)
        position_value = data["current"] * holding["quantity"]
        position_value_eur = position_value  # gia' in EUR
        total_value_eur += position_value_eur

        enriched = {**holding, **data}
        enriched["position_value"] = round(position_value, 2)
        enriched["position_value_eur_approx"] = round(position_value_eur, 2)
        results.append(enriched)

        note_str = f" -- {data['note']}" if data.get("note") else ""
        sign = "+" if data["daily_change_pct"] >= 0 else ""
        print(f"    OK: {data['current']} {data['currency']} "
              f"({sign}{data['daily_change_pct']}%){note_str}")

        # Alert di soglia (stessa logica del vecchio file)
        if abs(data["daily_change_pct"]) >= ALERT_THRESHOLDS["daily_change_pct"]:
            alerts.append(
                f"Attenzione: {holding['name']} ({holding['display_ticker']}) "
                f"ha fatto {data['daily_change_pct']}% oggi"
            )
        if abs(data["weekly_change_pct"]) >= ALERT_THRESHOLDS["weekly_change_pct"]:
            alerts.append(
                f"Trend: {holding['name']} ({holding['display_ticker']}) "
                f"ha fatto {data['weekly_change_pct']}% in 5 giorni"
            )

    return {
        "holdings": results,
        "alerts": alerts,
        "total_value_eur_approx": round(total_value_eur, 2),
        "timestamp": datetime.now().isoformat(),
    }


# --- esecuzione locale ----------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    data = analyze_portfolio()
    print()
    print(json.dumps(data, indent=2, ensure_ascii=False))
