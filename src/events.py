"""
Recupera eventi economici e aziendali imminenti.
- Earnings date dei ticker del portafoglio (via yfinance)
- Calendario macro (Fed, BCE, CPI, NFP) - opzionale via scraping light
"""
import yfinance as yf
from datetime import datetime, timedelta, timezone


def get_upcoming_earnings(tickers: list, days_ahead: int = 14) -> list:
    """Earnings nei prossimi N giorni per i ticker dati."""
    events = []
    cutoff = datetime.now() + timedelta(days=days_ahead)

    for ticker in tickers:
        try:
            t = yf.Ticker(ticker)
            cal = t.calendar
            if cal is None or (hasattr(cal, "empty") and cal.empty):
                continue

            # yfinance calendar può essere dict o DataFrame a seconda della versione
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

            if earnings_date:
                if isinstance(earnings_date, datetime):
                    date_obj = earnings_date
                else:
                    try:
                        date_obj = datetime.fromisoformat(str(earnings_date))
                    except Exception:
                        continue

                if datetime.now() <= date_obj <= cutoff:
                    days_to = (date_obj - datetime.now()).days
                    events.append({
                        "ticker": ticker,
                        "type": "earnings",
                        "date": date_obj.strftime("%Y-%m-%d"),
                        "days_until": days_to,
                        "description": f"{ticker} pubblica la trimestrale tra {days_to} giorni",
                    })
        except Exception as e:
            print(f"[WARN] earnings {ticker}: {e}")

    return events


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
        "macro_hints": MACRO_HINTS.strip(),
    }


if __name__ == "__main__":
    import json
    events = get_all_events(["NVDA"])
    print(json.dumps(events, indent=2, default=str))
