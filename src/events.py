"""
Recupera eventi economici e aziendali imminenti.
- Earnings date dei ticker del portafoglio (via EODHD calendar, fallback yfinance)
- Calendario macro (Fed, BCE, CPI, NFP) - opzionale via scraping light

NB: EODHD è la fonte primaria perché yfinance è rate-limitato sui runner
GitHub Actions e ritorna quasi sempre 429 Too Many Requests.
"""
import json
import os
import urllib.parse
import urllib.request
import yfinance as yf
from datetime import datetime, timedelta, timezone

EOD_API_KEY = os.environ.get("EOD_API_KEY", "")
FRED_API_KEY = os.environ.get("FRED_API_KEY", "")

# Release ID FRED dei dati macro USA che muovono davvero i mercati.
# (gli ID si trovano su https://fred.stlouisfed.org/releases)
FRED_RELEASES = {
    10: "Inflazione USA - CPI (indice prezzi al consumo)",
    21: "Reddito e spese USA - include l'indice prezzi PCE (quello che la Fed guarda di piu')",
    50: "Report sul lavoro USA (Employment Situation / Non-Farm Payrolls)",
    46: "Prezzi alla produzione USA - PPI",
}


def get_macro_calendar(days_ahead: int = 21) -> list:
    """Prossime date di rilascio REALI dei dati macro USA chiave, via FRED.
    Per ogni release prende la prossima data futura entro la finestra.
    Restituisce [] se la chiave manca o la chiamata fallisce (degrada pulito,
    l'agente non si rompe e il prompt torna a vietare le date inventate)."""
    if not FRED_API_KEY:
        return []
    today = datetime.now(timezone.utc).date()
    cutoff = today + timedelta(days=days_ahead)
    out = []
    for rid, label in FRED_RELEASES.items():
        qs = urllib.parse.urlencode({
            "release_id": rid,
            "api_key": FRED_API_KEY,
            "file_type": "json",
            # include anche le date programmate per cui non c'e' ancora il dato:
            # e' cosi' che FRED espone il calendario FUTURO dei rilasci.
            "include_release_dates_with_no_data": "true",
            "sort_order": "asc",
            "realtime_start": today.isoformat(),
            "realtime_end": cutoff.isoformat(),
        })
        url = f"https://api.stlouisfed.org/fred/release/dates?{qs}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "fineco-agent"})
            with urllib.request.urlopen(req, timeout=15) as r:
                data = json.loads(r.read().decode("utf-8"))
        except Exception as e:
            print(f"[WARN] FRED release {rid}: {e}")
            continue
        # Prendi la prossima data >= oggi entro la finestra (filtra per VALORE
        # della data, robusto a prescindere dalla semantica realtime di FRED).
        for d in data.get("release_dates", []):
            ds = d.get("date")
            if not ds:
                continue
            try:
                dobj = datetime.fromisoformat(ds).date()
            except ValueError:
                continue
            if today <= dobj <= cutoff:
                days_to = (dobj - today).days
                when = "oggi" if days_to == 0 else f"tra {days_to} giorni"
                out.append({
                    "type": "macro",
                    "date": dobj.isoformat(),
                    "days_until": days_to,
                    "description": f"{label} - {when} ({dobj.strftime('%d/%m/%Y')})",
                })
                break  # solo la prossima per ogni release
    out.sort(key=lambda x: x["date"])
    return out


def _get_earnings_eodhd(ticker: str, days_ahead: int = 14) -> list:
    """Recupera earnings via EODHD calendar API. Ticker formato 'NVDA.US'."""
    if not EOD_API_KEY:
        return []
    # EODHD vuole il suffisso exchange (.US per ticker americani)
    eod_symbol = ticker if "." in ticker else f"{ticker}.US"
    today = datetime.now().date()
    cutoff = today + timedelta(days=days_ahead)
    qs = urllib.parse.urlencode({
        "api_token": EOD_API_KEY,
        "symbols": eod_symbol,
        "from": today.isoformat(),
        "to": cutoff.isoformat(),
        "fmt": "json",
    })
    url = f"https://eodhd.com/api/calendar/earnings?{qs}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "fineco-agent"})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"[WARN] EODHD earnings {ticker}: {e}")
        return []

    earnings = (data or {}).get("earnings") or []
    out = []
    for e in earnings:
        date_str = e.get("report_date") or e.get("date")
        if not date_str:
            continue
        try:
            date_obj = datetime.fromisoformat(date_str)
        except ValueError:
            continue
        days_to = (date_obj.date() - today).days
        if 0 <= days_to <= days_ahead:
            out.append({
                "ticker": ticker,
                "type": "earnings",
                "date": date_obj.strftime("%Y-%m-%d"),
                "days_until": days_to,
                "description": f"{ticker} pubblica la trimestrale {'oggi' if days_to == 0 else f'tra {days_to} giorni'} ({date_obj.strftime('%d %B')})",
            })
    return out


def get_upcoming_earnings(tickers: list, days_ahead: int = 14) -> list:
    """Earnings nei prossimi N giorni per i ticker dati.
    Prova prima EODHD (affidabile sui runner GitHub), poi fallback yfinance."""
    events = []
    for ticker in tickers:
        eod_events = _get_earnings_eodhd(ticker, days_ahead)
        if eod_events:
            events.extend(eod_events)
            continue
        # Fallback yfinance - quasi sempre fallisce su GitHub Actions per
        # rate limit, ma tentiamo perché in locale può funzionare.
        events.extend(_get_earnings_yfinance(ticker, days_ahead))
    return events


def _get_earnings_yfinance(ticker: str, days_ahead: int = 14) -> list:
    """Fallback gratis tramite yfinance.Ticker.calendar (singolo ticker)."""
    cutoff = datetime.now() + timedelta(days=days_ahead)
    try:
        t = yf.Ticker(ticker)
        cal = t.calendar
        if cal is None or (hasattr(cal, "empty") and cal.empty):
            return []

        earnings_date = None
        if isinstance(cal, dict):
            earnings_date = cal.get("Earnings Date")
            if isinstance(earnings_date, list) and earnings_date:
                earnings_date = earnings_date[0]
        else:
            try:
                earnings_date = cal.loc["Earnings Date"].iloc[0]
            except Exception:
                pass

        if not earnings_date:
            return []
        if not isinstance(earnings_date, datetime):
            try:
                earnings_date = datetime.fromisoformat(str(earnings_date))
            except Exception:
                return []
        if datetime.now() <= earnings_date <= cutoff:
            days_to = (earnings_date - datetime.now()).days
            return [{
                "ticker": ticker,
                "type": "earnings",
                "date": earnings_date.strftime("%Y-%m-%d"),
                "days_until": days_to,
                "description": f"{ticker} pubblica la trimestrale tra {days_to} giorni",
            }]
    except Exception as e:
        print(f"[WARN] yfinance earnings {ticker}: {e}")
    return []


# Eventi macro ricorrenti noti (da espandere se vuoi precisione)
# Per una lista veramente aggiornata servirebbe un'API a pagamento
# (Trading Economics, FRED funziona gratis ma è USA-centric).
# Qui ci accontentiamo di una euristica + AI che lo sa.
MACRO_HINTS = """
Eventi macro da monitorare mensilmente (indicativi):
- Primo venerdì del mese: Non-Farm Payrolls USA
- Metà mese: CPI USA (inflazione)
- 8 volte l'anno: riunioni Fed (FOMC) e BCE
- Trimestralmente: earnings season (gennaio, aprile, luglio, ottobre)
"""


def get_all_events(portfolio_tickers: list) -> dict:
    return {
        "earnings": get_upcoming_earnings(portfolio_tickers, days_ahead=14),
        "macro_calendar": get_macro_calendar(days_ahead=21),
        "macro_hints": MACRO_HINTS.strip(),
    }


if __name__ == "__main__":
    import json
    events = get_all_events(["NVDA"])
    print(json.dumps(events, indent=2, default=str))
