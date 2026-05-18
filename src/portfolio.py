"""
portfolio.py - recupera prezzi attuali e performance del portafoglio.

Architettura a 3 livelli (per evitare single-point-of-failure):
  1. PRIMARIO:
     - NVIDIA  -> Twelve Data (azioni USA, copertura eccellente)
     - VWCE    -> EODHD (VWCE.XETRA, copertura UCITS europei eccellente)
     - EQAC    -> EODHD (EQQB.XETRA, idem)
  2. FALLBACK: yfinance (gratis, no API key, ma rate-limitato da GitHub Actions)
  3. ERRORE ESPLICITO se anche il fallback fallisce - NIENTE prezzi inventati.

Schema di ritorno IDENTICO al vecchio analyze_portfolio() per compatibilita'
con briefing.py, journal.py, dashboard_builder.py, emailer.py.
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Optional

log = logging.getLogger(__name__)


# --- Configurazione portafoglio ------------------------------------------

# Ticker primari (Twelve Data / EODHD) + fallback yfinance.
# NB: VWCE e EQAC vengono prezzati su Xetra, non su Milano. La differenza con
# il prezzo Fineco e' di pochi centesimi (stesso ETF UCITS, valuta EUR uguale).
PORTFOLIO = [
    {
        "symbol": "NVDA",
        "display_ticker": "1NVDA.MI",
        "primary_source": "twelvedata",
        "primary_symbol": "NVDA",
        "primary_currency": "USD",
        "fallback_yf": "1NVDA.MI",
        "fallback_yf_2": "NVDA",
        "fx_convert_from_primary": True,
        "quantity": 1,
        "name": "NVIDIA",
        "type": "stock",
        "currency": "EUR",
        # Ticker da usare per gli earnings (events.py via yfinance).
        # ETF non hanno earnings -> il campo è omesso negli altri holding.
        "earnings_ticker": "NVDA",
    },
    {
        "symbol": "IE00BK5BQT80",
        "display_ticker": "VWCE.MI",
        "primary_source": "eodhd",
        "primary_symbol": "VWCE.XETRA",
        "primary_currency": "EUR",
        "fallback_yf": "VWCE.MI",
        "fallback_yf_2": "VWCE.DE",
        "fx_convert_from_primary": False,
        "quantity": 10,
        "name": "Vanguard FTSE All-World",
        "type": "etf_equity",
        "currency": "EUR",
    },
    {
        # Invesco EQQQ Nasdaq-100 UCITS ETF Acc - ISIN IE00BFZXGZ54.
        # NB: Acc, NON la versione Dist (ISIN IE0032077012, ticker EQQQ.MI).
        "symbol": "IE00BFZXGZ54",
        "display_ticker": "EQAC.MI",
        "primary_source": "eodhd",
        "primary_symbol": "EQQB.XETRA",
        "primary_currency": "EUR",
        "fallback_yf": "EQAC.MI",
        "fallback_yf_2": "EQQB.DE",
        "fx_convert_from_primary": False,
        "quantity": 1,
        "name": "Invesco EQQQ Nasdaq-100 (Acc)",
        "type": "etf_equity",
        "currency": "EUR",
    },
]


# --- WATCHLIST -----------------------------------------------------------
# Asset NON posseduti ma monitorati per generare segnali di ingresso.
# L'AI riceve sia PORTFOLIO che WATCHLIST e può suggerire acquisti su
# entrambi. Niente quantity, niente alert su soglie (eviterebbero rumore).
# Schema compatibile con PORTFOLIO per riutilizzare fetch_asset_data,
# ma quantity = 0 segnala "non posseduto".

WATCHLIST = [
    # === Titoli di stato e bond (sicurezza/decorrelazione) ===
    # NB: primary_symbol usa .XETRA (Deutsche Börse) o .L (London) perché
    # EODHD non copre bene Borsa Italiana (.MI restituisce 404). Lo stesso
    # ETF UCITS è quotato su più borse: scegliamo quella con copertura EODHD.
    # Il display_ticker resta .MI per coerenza con Fineco.
    {
        "symbol": "IE00B7K1G870", "display_ticker": "IBGS.MI",
        "primary_source": "eodhd", "primary_symbol": "IBGS.XETRA",
        "primary_currency": "EUR", "fallback_yf": "IBGS.MI", "fallback_yf_2": "IBGS.L",
        "fx_convert_from_primary": False, "quantity": 0,
        "name": "iShares Italy Govt Bond (BTP)", "type": "etf_bond",
        "currency": "EUR", "category": "bond_govt",
    },
    {
        "symbol": "IE00B1FZS798", "display_ticker": "IBTL.MI",
        "primary_source": "eodhd", "primary_symbol": "IBTL.XETRA",
        "primary_currency": "EUR", "fallback_yf": "IBTL.L", "fallback_yf_2": "IBTL.MI",
        "fx_convert_from_primary": False, "quantity": 0,
        "name": "iShares Treasury USA 7-10Y", "type": "etf_bond",
        "currency": "EUR", "category": "bond_govt",
    },
    {
        "symbol": "IE00B1FZS681", "display_ticker": "IBGM.MI",
        "primary_source": "eodhd", "primary_symbol": "IBGM.XETRA",
        "primary_currency": "EUR", "fallback_yf": "IBGM.L", "fallback_yf_2": "IBGM.MI",
        "fx_convert_from_primary": False, "quantity": 0,
        "name": "iShares Germany Govt Bond (Bund)", "type": "etf_bond",
        "currency": "EUR", "category": "bond_govt",
    },
    {
        "symbol": "IE00BDBRDM35", "display_ticker": "AGGH.MI",
        "primary_source": "eodhd", "primary_symbol": "AGGH.XETRA",
        "primary_currency": "EUR", "fallback_yf": "AGGH.L", "fallback_yf_2": "AGGH.MI",
        "fx_convert_from_primary": False, "quantity": 0,
        "name": "iShares Global Aggregate Bond (EUR hedged)", "type": "etf_bond",
        "currency": "EUR", "category": "bond_globale",
    },
    # === Oro fisico ===
    {
        "symbol": "IE00B4ND3602", "display_ticker": "SGLD.MI",
        "primary_source": "eodhd", "primary_symbol": "SGLD.L",
        "primary_currency": "USD", "fallback_yf": "SGLD.MI", "fallback_yf_2": "SGLD.L",
        "fx_convert_from_primary": True, "quantity": 0,
        "name": "iShares Physical Gold", "type": "etc_commodity",
        "currency": "EUR", "category": "oro",
    },
    # === Emerging markets ===
    {
        "symbol": "IE00BKM4GZ66", "display_ticker": "EIMI.MI",
        "primary_source": "eodhd", "primary_symbol": "EIMI.XETRA",
        "primary_currency": "EUR", "fallback_yf": "EIMI.MI", "fallback_yf_2": "EIMI.L",
        "fx_convert_from_primary": False, "quantity": 0,
        "name": "iShares MSCI Emerging Markets", "type": "etf_equity",
        "currency": "EUR", "category": "azionario_em",
    },
    # === Settoriali difensivi ===
    {
        "symbol": "IE00B43HR379", "display_ticker": "HEAL.MI",
        "primary_source": "eodhd", "primary_symbol": "HEAL.XETRA",
        "primary_currency": "EUR", "fallback_yf": "HEAL.MI", "fallback_yf_2": "HEAL.L",
        "fx_convert_from_primary": False, "quantity": 0,
        "name": "iShares Healthcare Innovation", "type": "etf_equity",
        "currency": "EUR", "category": "settoriale_healthcare",
    },
    {
        "symbol": "DE000A0F5UJ7", "display_ticker": "EXV1.MI",
        "primary_source": "eodhd", "primary_symbol": "EXV1.XETRA",
        "primary_currency": "EUR", "fallback_yf": "EXV1.DE", "fallback_yf_2": "EXV1.MI",
        "fx_convert_from_primary": False, "quantity": 0,
        "name": "iShares STOXX 600 Banks", "type": "etf_equity",
        "currency": "EUR", "category": "settoriale_banche",
    },
    # === Big tech singoli (azioni US, via Twelve Data) ===
    {
        "symbol": "AAPL", "display_ticker": "AAPL",
        "primary_source": "twelvedata", "primary_symbol": "AAPL",
        "primary_currency": "USD", "fallback_yf": "AAPL", "fallback_yf_2": "AAPL",
        "fx_convert_from_primary": True, "quantity": 0,
        "name": "Apple", "type": "stock",
        "currency": "EUR", "category": "azione_tech_usa",
    },
    {
        "symbol": "MSFT", "display_ticker": "MSFT",
        "primary_source": "twelvedata", "primary_symbol": "MSFT",
        "primary_currency": "USD", "fallback_yf": "MSFT", "fallback_yf_2": "MSFT",
        "fx_convert_from_primary": True, "quantity": 0,
        "name": "Microsoft", "type": "stock",
        "currency": "EUR", "category": "azione_tech_usa",
    },
    {
        "symbol": "GOOGL", "display_ticker": "GOOGL",
        "primary_source": "twelvedata", "primary_symbol": "GOOGL",
        "primary_currency": "USD", "fallback_yf": "GOOGL", "fallback_yf_2": "GOOGL",
        "fx_convert_from_primary": True, "quantity": 0,
        "name": "Alphabet (Google)", "type": "stock",
        "currency": "EUR", "category": "azione_tech_usa",
    },
    {
        "symbol": "META", "display_ticker": "META",
        "primary_source": "twelvedata", "primary_symbol": "META",
        "primary_currency": "USD", "fallback_yf": "META", "fallback_yf_2": "META",
        "fx_convert_from_primary": True, "quantity": 0,
        "name": "Meta Platforms", "type": "stock",
        "currency": "EUR", "category": "azione_tech_usa",
    },
    # === Azioni single non-tech (diversificazione settoriale) ===
    {
        "symbol": "JPM", "display_ticker": "JPM",
        "primary_source": "twelvedata", "primary_symbol": "JPM",
        "primary_currency": "USD", "fallback_yf": "JPM", "fallback_yf_2": "JPM",
        "fx_convert_from_primary": True, "quantity": 0,
        "name": "JPMorgan Chase", "type": "stock",
        "currency": "EUR", "category": "azione_banche_usa",
    },
    {
        "symbol": "BRK.B", "display_ticker": "BRK-B",
        "primary_source": "twelvedata", "primary_symbol": "BRK.B",
        "primary_currency": "USD", "fallback_yf": "BRK-B", "fallback_yf_2": "BRK-B",
        "fx_convert_from_primary": True, "quantity": 0,
        "name": "Berkshire Hathaway B", "type": "stock",
        "currency": "EUR", "category": "azione_holding_diversificata",
    },
    {
        "symbol": "UNH", "display_ticker": "UNH",
        "primary_source": "twelvedata", "primary_symbol": "UNH",
        "primary_currency": "USD", "fallback_yf": "UNH", "fallback_yf_2": "UNH",
        "fx_convert_from_primary": True, "quantity": 0,
        "name": "UnitedHealth", "type": "stock",
        "currency": "EUR", "category": "azione_healthcare_usa",
    },
]


ALERT_THRESHOLDS = {
    "daily_change_pct": 5.0,
    "weekly_change_pct": 10.0,
    "portfolio_change_pct": 3.0,
}

TWELVE_DATA_API_KEY = os.environ.get("TWELVE_DATA_API_KEY", "")
EOD_API_KEY = os.environ.get("EOD_API_KEY", "")


# --- HTTP helper con retry -----------------------------------------------

def _http_json(url: str, attempts: int = 3, backoff: float = 1.5,
               timeout: int = 15):
    """GET di un endpoint che ritorna JSON, con retry esponenziale."""
    last_err = None
    for i in range(attempts):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "Mozilla/5.0 (fineco-agent)"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8")), None
        except Exception as e:
            last_err = str(e)[:200]
        if i < attempts - 1:
            time.sleep(backoff * (i + 1))
    return None, last_err


# --- Fonte 1: Twelve Data (NVIDIA) ---------------------------------------

def _fetch_twelvedata(symbol: str) -> dict:
    if not TWELVE_DATA_API_KEY:
        return {"error": "TWELVE_DATA_API_KEY non configurata"}

    qs = urllib.parse.urlencode({
        "symbol": symbol,
        "interval": "1day",
        "outputsize": 30,
        "apikey": TWELVE_DATA_API_KEY,
    })
    url = f"https://api.twelvedata.com/time_series?{qs}"
    data, err = _http_json(url)
    if data is None:
        return {"error": f"TwelveData HTTP: {err}"}
    if data.get("status") == "error":
        return {"error": f"TwelveData: {data.get('message', 'errore')}"}

    values = data.get("values", [])
    if not values or len(values) < 2:
        return {"error": f"TwelveData: dati insufficienti per {symbol}"}

    # values e' in ordine reverse-chronological -> inverto
    values = list(reversed(values))
    closes = [float(v["close"]) for v in values]
    price_series = [
        {"date": v["datetime"], "close": float(v["close"])} for v in values
    ]

    current = closes[-1]
    prev = closes[-2]
    week_ago = closes[-6] if len(closes) >= 6 else closes[0]
    month_ago = closes[0]

    return {
        "current": current,
        "daily_change_pct": ((current - prev) / prev) * 100,
        "weekly_change_pct": ((current - week_ago) / week_ago) * 100 if week_ago else 0.0,
        "monthly_change_pct": ((current - month_ago) / month_ago) * 100 if month_ago else 0.0,
        "volume": int(values[-1].get("volume") or 0),
        "price_series": price_series,
    }


# --- Fonte 2: EODHD (ETF UCITS) ------------------------------------------

def _fetch_eodhd(symbol: str) -> dict:
    """Combina real-time + EOD storico. Costa 2 chiamate/asset su 20/giorno."""
    if not EOD_API_KEY:
        return {"error": "EOD_API_KEY non configurata"}

    # 1) Real-time
    rt_url = f"https://eodhd.com/api/real-time/{symbol}?api_token={EOD_API_KEY}&fmt=json"
    rt, err = _http_json(rt_url)
    if rt is None:
        return {"error": f"EODHD real-time HTTP: {err}"}
    if not isinstance(rt, dict) or "close" not in rt:
        return {"error": f"EODHD real-time: risposta inattesa {str(rt)[:120]}"}

    # EODHD può ritornare "NA" come close se l'asset esiste ma non
    # ha avuto scambi recenti (ETF poco liquidi su Xetra).
    try:
        current = float(rt["close"])
    except (ValueError, TypeError):
        return {"error": f"EODHD: prezzo close={rt.get('close')!r} non numerico per {symbol}"}
    try:
        daily_pct = float(rt.get("change_p") or 0.0)
    except (ValueError, TypeError):
        daily_pct = 0.0
    try:
        volume = int(rt.get("volume") or 0)
    except (ValueError, TypeError):
        volume = 0

    # 2) Storico EOD (per weekly, monthly e serie per il grafico)
    eod_url = (f"https://eodhd.com/api/eod/{symbol}"
               f"?api_token={EOD_API_KEY}&fmt=json&period=d&order=d")
    hist, err = _http_json(eod_url)
    weekly_pct = 0.0
    monthly_pct = 0.0
    price_series = []
    if isinstance(hist, list) and len(hist) >= 2:
        # ordinato desc per data -> hist[0] e' il piu' recente
        closes = [float(h["close"]) for h in hist if h.get("close") is not None]
        if len(closes) >= 6:
            weekly_pct = ((closes[0] - closes[5]) / closes[5]) * 100
        if len(closes) >= 21:
            monthly_pct = ((closes[0] - closes[20]) / closes[20]) * 100
        elif len(closes) >= 2:
            monthly_pct = ((closes[0] - closes[-1]) / closes[-1]) * 100
        # Serie cronologica per il grafico (inverto a chronological, ultimi 90gg)
        price_series = [
            {"date": h["date"], "close": float(h["close"])}
            for h in reversed(hist[:90])
            if h.get("close") is not None
        ]
    else:
        log.warning("EODHD storico non disponibile per %s (%s)", symbol, err)

    return {
        "current": current,
        "daily_change_pct": daily_pct,
        "weekly_change_pct": weekly_pct,
        "monthly_change_pct": monthly_pct,
        "volume": volume,
        "price_series": price_series,
    }


# --- Fonte 3 (fallback): yfinance ----------------------------------------

def _fetch_yfinance(ticker: str) -> dict:
    """Fallback gratis senza API key. Rate-limitato da GitHub ma a volte regge."""
    try:
        import yfinance as yf
    except ImportError:
        return {"error": "yfinance non installato"}

    last_err = None
    for i in range(3):
        try:
            tk = yf.Ticker(ticker)
            hist = tk.history(period="1mo", auto_adjust=False)
            if not hist.empty:
                hist = hist.dropna(subset=["Close"])
            if hist is None or hist.empty:
                last_err = "empty history"
            else:
                closes = hist["Close"].tolist()
                current = float(closes[-1])
                prev = closes[-2] if len(closes) >= 2 else current
                week_ago = closes[-6] if len(closes) >= 6 else closes[0]
                month_ago = closes[0]
                return {
                    "current": current,
                    "daily_change_pct": ((current - prev) / prev) * 100 if prev else 0.0,
                    "weekly_change_pct": ((current - week_ago) / week_ago) * 100 if week_ago else 0.0,
                    "monthly_change_pct": ((current - month_ago) / month_ago) * 100 if month_ago else 0.0,
                    "volume": int(hist["Volume"].iloc[-1]) if "Volume" in hist.columns else 0,
                    "_yf_currency": (tk.fast_info.get("currency") or "EUR").upper(),
                }
        except Exception as e:
            last_err = str(e)[:150]
        if i < 2:
            time.sleep(1.5 * (i + 1))
    return {"error": f"yfinance: {last_err}"}


# --- FX live (per NVIDIA USD -> EUR) -------------------------------------

def _get_fx_eur(from_ccy: str) -> Optional[float]:
    if from_ccy == "EUR":
        return 1.0

    # Tentativo 1: EODHD FX
    if EOD_API_KEY:
        pair = f"{from_ccy}EUR.FOREX"
        url = f"https://eodhd.com/api/real-time/{pair}?api_token={EOD_API_KEY}&fmt=json"
        data, _ = _http_json(url, attempts=2)
        if isinstance(data, dict) and data.get("close"):
            try:
                return float(data["close"])
            except (TypeError, ValueError):
                pass

    # Tentativo 2: Twelve Data FX
    if TWELVE_DATA_API_KEY:
        qs = urllib.parse.urlencode({
            "symbol": f"{from_ccy}/EUR",
            "apikey": TWELVE_DATA_API_KEY,
        })
        url = f"https://api.twelvedata.com/price?{qs}"
        data, _ = _http_json(url, attempts=2)
        if isinstance(data, dict) and data.get("price"):
            try:
                return float(data["price"])
            except (TypeError, ValueError):
                pass

    log.warning("Nessuna fonte FX disponibile per %s->EUR", from_ccy)
    return None


# --- Orchestratore per singola posizione ---------------------------------

def fetch_asset_data(holding: dict) -> dict:
    display = holding["display_ticker"]
    primary_source = holding["primary_source"]
    primary_symbol = holding["primary_symbol"]
    primary_ccy = holding["primary_currency"]

    log.info("[%s] tento primary=%s (%s)", display, primary_source, primary_symbol)

    # === LIVELLO 1: fonte primaria ===
    if primary_source == "twelvedata":
        primary_data = _fetch_twelvedata(primary_symbol)
    elif primary_source == "eodhd":
        primary_data = _fetch_eodhd(primary_symbol)
    else:
        primary_data = {"error": f"primary_source sconosciuta: {primary_source}"}

    source_used = "primary"
    ticker_used = primary_symbol
    native_ccy = primary_ccy

    # === LIVELLO 2: fallback yfinance ===
    if "error" in primary_data:
        log.warning("[%s] primary fallita (%s); provo yfinance %s",
                    display, primary_data["error"], holding["fallback_yf"])
        yf_data = _fetch_yfinance(holding["fallback_yf"])
        if "error" in yf_data:
            log.warning("[%s] yfinance 1 fallita (%s); provo %s",
                        display, yf_data["error"], holding["fallback_yf_2"])
            yf_data = _fetch_yfinance(holding["fallback_yf_2"])
            ticker_used = holding["fallback_yf_2"]
        else:
            ticker_used = holding["fallback_yf"]

        if "error" in yf_data:
            return {
                "ticker": display,
                "error": f"Tutte le fonti fallite. Primary: {primary_data['error']}. "
                         f"Yfinance: {yf_data['error']}",
            }

        primary_data = yf_data
        native_ccy = yf_data.get("_yf_currency", "EUR")
        source_used = "fallback"

    # === CONVERSIONE IN EUR ===
    current_native = primary_data["current"]
    if native_ccy == "EUR":
        current_eur = current_native
    elif holding.get("fx_convert_from_primary") or source_used == "fallback":
        fx = _get_fx_eur(native_ccy)
        if fx is None:
            return {
                "ticker": display,
                "error": f"Cambio {native_ccy}->EUR non disponibile",
            }
        current_eur = current_native * fx
    else:
        current_eur = current_native
        log.warning("[%s] currency inattesa %s, no conversion", display, native_ccy)

    note = None
    if source_used == "fallback":
        note = f"Prezzo da fallback yfinance ({ticker_used})"

    # Propaga la serie storica di chiusure per il grafico "andamento per
    # singolo asset". Se l'asset è in valuta non-EUR (es. NVDA in USD),
    # applico lo stesso fx rate a tutta la serie. Approssimazione ok perché
    # il chart normalizza tutto a base 100: il rapporto tra prezzi resta
    # identico anche con un singolo fx applicato a tutti.
    price_series = primary_data.get("price_series") or []
    if price_series and native_ccy != "EUR":
        fx_factor = current_eur / current_native if current_native else 1
        price_series = [
            {"date": p["date"], "close": round(p["close"] * fx_factor, 4)}
            for p in price_series
        ]

    out = {
        "ticker": display,
        "current": round(current_eur, 2),
        "currency": "EUR",
        "daily_change_pct": round(primary_data["daily_change_pct"], 2),
        "weekly_change_pct": round(primary_data["weekly_change_pct"], 2),
        "monthly_change_pct": round(primary_data["monthly_change_pct"], 2),
        "volume": primary_data.get("volume", 0),
        "price_series": price_series,
        "_source": source_used,
        "_ticker_used": ticker_used,
    }
    if note:
        out["note"] = note
    return out


# --- Entrypoint pubblico (nome identico al vecchio file) ------------------

def analyze_portfolio() -> dict:
    results: list[dict] = []
    alerts: list[str] = []
    total_value_eur = 0.0

    for holding in PORTFOLIO:
        print(f"  Scarico {holding['display_ticker']} "
              f"(primary={holding['primary_source']}:{holding['primary_symbol']})...")
        data = fetch_asset_data(holding)

        if "error" in data:
            results.append({**holding, **data})
            print(f"    ERRORE: {data['error'][:150]}")
            alerts.append(
                f"Prezzo non disponibile per {holding['name']} "
                f"({holding['display_ticker']}): {data['error']}"
            )
            continue

        position_value = data["current"] * holding["quantity"]
        position_value_eur = position_value
        total_value_eur += position_value_eur

        enriched = {**holding, **data}
        enriched["position_value"] = round(position_value, 2)
        enriched["position_value_eur_approx"] = round(position_value_eur, 2)
        results.append(enriched)

        note_str = f" -- {data['note']}" if data.get("note") else ""
        sign = "+" if data["daily_change_pct"] >= 0 else ""
        print(f"    OK [{data['_source']}]: {data['current']} EUR "
              f"({sign}{data['daily_change_pct']}%){note_str}")

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


def analyze_watchlist() -> list:
    """Fetcha prezzi degli asset in WATCHLIST (non posseduti, monitorati).
    Niente alert/posizione: solo dati di prezzo+performance per il prompt AI
    e la sezione 'Watchlist' della dashboard. Errori (anche eccezioni non
    gestite a livello di singolo asset) vengono loggati ma il fetch degli
    altri continua — nessun bug su un ticker deve bloccare gli altri 14."""
    results: list[dict] = []
    for item in WATCHLIST:
        print(f"  [watchlist] {item['display_ticker']} "
              f"(primary={item['primary_source']}:{item['primary_symbol']})...")
        try:
            data = fetch_asset_data(item)
        except Exception as e:
            print(f"    [watchlist] CRASH: {type(e).__name__}: {str(e)[:120]}")
            results.append({**item, "error": f"crash {type(e).__name__}: {str(e)[:120]}"})
            continue
        if "error" in data:
            print(f"    [watchlist] ERRORE: {data['error'][:120]}")
            results.append({**item, **data})
            continue
        sign = "+" if data["daily_change_pct"] >= 0 else ""
        print(f"    [watchlist] OK: {data['current']} EUR "
              f"({sign}{data['daily_change_pct']}%)")
        results.append({**item, **data})
    return results


# --- Esecuzione locale ----------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    data = analyze_portfolio()
    print()
    print(json.dumps(data, indent=2, ensure_ascii=False))
