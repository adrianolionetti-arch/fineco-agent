"""
portfolio.py — recupera prezzi delle posizioni in portafoglio.

Strategia:
  1) yfinance come fonte primaria (gratis, no API key).
  2) Retry 3 volte con backoff in caso di errore transitorio.
  3) Fallback su exchange alternativo (Xetra) se quello primario (Milano) non risponde.
  4) Se tutto fallisce: stato 'unavailable' esplicito, NON inventiamo prezzi.

Output: lista di Quote, ognuna con prezzo in EUR, P/L, e tracciabilità della fonte.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, asdict
from typing import Optional

import yfinance as yf

log = logging.getLogger(__name__)


# Configurazione del portafoglio.
# - primary : ticker preferito (la borsa dove hai comprato, di solito Milano)
# - fallback: ticker alternativo se il primario non risponde
# - fx_convert: True se il fallback è in valuta diversa da EUR (richiede conversione)
PORTFOLIO = [
    {
        "id": "NVIDIA",
        "display_ticker": "1NVDA.MI",
        "primary": "1NVDA.MI",
        "fallback": "NVDA",          # NASDAQ in USD se Milano non risponde
        "fx_convert": True,
        "quantity": 1,
        "cost_basis_eur": 160.71,
    },
    {
        "id": "VWCE",
        "display_ticker": "VWCE.MI",
        "primary": "VWCE.MI",
        "fallback": "VWCE.DE",       # Xetra in EUR
        "fx_convert": False,
        "quantity": 10,
        "cost_basis_eur": 149.70,
    },
    {
        # Invesco EQQQ Nasdaq-100 UCITS ETF Acc — ISIN IE00BFZXGZ54
        # NB: versione ad accumulazione (Acc), NON la versione a distribuzione (ISIN IE0032077012, ticker EQQQ).
        "id": "EQQQ",
        "display_ticker": "EQAC.MI",
        "primary": "EQAC.MI",
        "fallback": "EQQB.DE",       # stessa quota su Xetra, in EUR
        "fx_convert": False,
        "quantity": 1,
        "cost_basis_eur": 368.36,
    },
]


@dataclass
class Quote:
    holding_id: str
    ticker_used: str
    price_eur: Optional[float]
    currency_native: str
    quantity: float
    cost_basis_eur: float
    market_value_eur: Optional[float]
    pl_eur: Optional[float]
    pl_pct: Optional[float]
    source: str               # "primary" | "fallback" | "unavailable"
    last_date: Optional[str]
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


# --- helpers ---------------------------------------------------------------

def _fetch_price(ticker: str, attempts: int = 3, backoff: float = 1.5):
    """
    Legge il prezzo di chiusura più recente da yfinance, con retry.
    Ritorna (price, currency, last_date_iso, error).
    """
    last_err = None
    for i in range(attempts):
        try:
            tk = yf.Ticker(ticker)
            hist = tk.history(period="5d", auto_adjust=False)
            if not hist.empty:
                price = float(hist["Close"].iloc[-1])
                last_date = hist.index[-1].strftime("%Y-%m-%d")
                currency = (tk.fast_info.get("currency") or "EUR").upper()
                return price, currency, last_date, None
            last_err = "empty history"
        except Exception as e:
            last_err = str(e)[:120]
        if i < attempts - 1:
            time.sleep(backoff * (i + 1))
    return None, None, None, last_err


def _to_eur(price: float, currency: str) -> Optional[float]:
    """Converte un prezzo in EUR usando il cambio spot di Yahoo."""
    if currency == "EUR":
        return price
    if currency == "GBP":
        pair = "GBPEUR=X"
    elif currency == "USD":
        pair = "USDEUR=X"
    else:
        pair = f"{currency}EUR=X"
    fx, _, _, err = _fetch_price(pair, attempts=2)
    if fx is None:
        log.warning("FX %s→EUR non disponibile (%s)", currency, err)
        return None
    return price * fx


# --- entrypoint pubblico --------------------------------------------------

def get_quotes() -> list[Quote]:
    """Recupera i prezzi correnti per tutte le posizioni in PORTFOLIO."""
    out: list[Quote] = []
    for h in PORTFOLIO:
        # 1° tentativo: ticker primario (.MI)
        price, ccy, last_date, err = _fetch_price(h["primary"])
        source = "primary"
        ticker_used = h["primary"]

        # 2° tentativo: ticker di fallback
        if price is None:
            log.warning("Primario %s fallito (%s); provo fallback %s",
                        h["primary"], err, h["fallback"])
            price, ccy, last_date, err = _fetch_price(h["fallback"])
            source = "fallback"
            ticker_used = h["fallback"]

        # Conversione in EUR
        price_eur = None
        if price is not None:
            if ccy == "EUR":
                price_eur = price
            elif h.get("fx_convert"):
                price_eur = _to_eur(price, ccy)
            else:
                log.warning("Currency inattesa %s per %s — niente conversione configurata",
                            ccy, ticker_used)

        # Compongo il risultato
        if price_eur is not None:
            mv = price_eur * h["quantity"]
            pl_eur = mv - (h["cost_basis_eur"] * h["quantity"])
            pl_pct = (price_eur / h["cost_basis_eur"] - 1) * 100
            quote = Quote(
                holding_id=h["id"],
                ticker_used=ticker_used,
                price_eur=round(price_eur, 4),
                currency_native=ccy or "EUR",
                quantity=h["quantity"],
                cost_basis_eur=h["cost_basis_eur"],
                market_value_eur=round(mv, 2),
                pl_eur=round(pl_eur, 2),
                pl_pct=round(pl_pct, 2),
                source=source,
                last_date=last_date,
            )
        else:
            quote = Quote(
                holding_id=h["id"],
                ticker_used=ticker_used,
                price_eur=None,
                currency_native=ccy or "?",
                quantity=h["quantity"],
                cost_basis_eur=h["cost_basis_eur"],
                market_value_eur=None,
                pl_eur=None,
                pl_pct=None,
                source="unavailable",
                last_date=last_date,
                error=err or "no price",
            )
            log.error("Prezzo NON disponibile per %s (ultimo errore: %s)", h["id"], err)
        out.append(quote)
    return out


# --- esecuzione locale ----------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    quotes = get_quotes()
    print()
    print(f"{'Holding':10s} {'Ticker':12s} {'Px EUR':>10s} "
          f"{'Valore':>10s} {'P/L %':>8s} {'Fonte':10s}")
    print("-" * 70)
    for q in quotes:
        px = f"{q.price_eur:.2f}" if q.price_eur is not None else "N/A"
        mv = f"{q.market_value_eur:.2f}" if q.market_value_eur is not None else "N/A"
        pl = f"{q.pl_pct:+.2f}" if q.pl_pct is not None else "N/A"
        print(f"{q.holding_id:10s} {q.ticker_used:12s} {px:>10s} "
              f"{mv:>10s} {pl:>8s} {q.source:10s}")
        if q.error:
            print(f"           └─ {q.error}")
    # Totali
    total_mv = sum(q.market_value_eur for q in quotes if q.market_value_eur is not None)
    total_cb = sum(q.cost_basis_eur * q.quantity for q in quotes)
    total_pl = total_mv - total_cb
    print("-" * 70)
    print(f"{'TOTALE':10s} {'':12s} {'':>10s} {total_mv:>10.2f} "
          f"{total_pl/total_cb*100:+.2f}%")
