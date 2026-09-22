"""
Gate oggettivo sui segnali dell'AI.

PERCHE' ESISTE QUESTO FILE
--------------------------
Da maggio a settembre 2026 l'agente ha emesso 97 segnali: 97 YELLOW, zero GREEN,
zero NONE. Il system prompt chiedeva esplicitamente "usa NONE spesso, la maggior
parte dei giorni non succede niente" e non e' mai stato ascoltato nemmeno una volta.
Stessa storia per l'importanza: prima inchiodata a 2/5, poi (dopo un fix che
aggiungeva istruzioni al prompt) inchiodata a 3/5.

La lezione: la soglia di un segnale non puo' stare in un prompt. Un modello che
deve scegliere fra "dire qualcosa" e "dire che non c'e' niente da dire" sceglie
sempre la prima. Quindi il livello NON lo decide piu' l'AI: l'AI propone, il
codice verifica contro condizioni misurabili e puo' solo DECLASSARE.

Il gate non promuove mai. Se l'AI dice NONE, resta NONE.
"""
from datetime import datetime, timedelta
import csv
import os

JOURNAL_PATH = "journal/signals.csv"

# --- Soglie di movimento (in valore assoluto, %) --------------------------
# Un segnale deve poggiare su un movimento di prezzo che esista davvero.
GREEN_MIN_DAILY = 5.0       # oppure...
GREEN_MIN_WEEKLY = 8.0
YELLOW_MIN_DAILY = 2.0      # oppure...
YELLOW_MIN_WEEKLY = 3.0     # oppure...
YELLOW_MIN_MONTHLY = 5.0

# --- Anti-ripetizione -----------------------------------------------------
# Non riproporre lo stesso asset se non e' successo nulla di nuovo nel prezzo.
COOLDOWN_DAYS = 10          # giorni di silenzio richiesti sullo stesso ticker
COOLDOWN_MOVE_PCT = 3.0     # a meno che il prezzo non si sia mosso di almeno tanto


def _f(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _find_holding(holdings: list, ticker: str) -> dict | None:
    for h in holdings or []:
        if h.get("ticker") == ticker:
            return h
    return None


def _last_signal_for(ticker: str, path: str = JOURNAL_PATH) -> dict | None:
    """Ultimo segnale registrato su quel ticker, se esiste."""
    if not ticker or not os.path.exists(path):
        return None
    last = None
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r.get("asset_ticker") == ticker:
                last = r
    return last


def compute_importance(daily: float, weekly: float, monthly: float,
                       has_catalyst: bool) -> int:
    """
    Importanza calcolata, non dichiarata. Deterministica: stessi input,
    stesso numero. Sostituisce il valore proposto dall'AI, che in 97 segnali
    su 97 e' stato una costante.
    """
    d, w, m = abs(daily or 0), abs(weekly or 0), abs(monthly or 0)
    # Quanto e' "grosso" il movimento rispetto alle soglie tipiche di ogni finestra
    strength = max(d / 2.0, w / 3.0, m / 5.0)

    if strength >= 3.0:
        score = 5
    elif strength >= 2.0:
        score = 4
    elif strength >= 1.0:
        score = 3
    elif strength >= 0.5:
        score = 2
    else:
        score = 1

    if has_catalyst and score < 5:
        score += 1
    return max(1, min(5, score))


def apply_gate(briefing: dict, holdings: list, events: dict | None = None,
               journal_path: str = JOURNAL_PATH) -> dict:
    """
    Applica il gate al briefing. Modifica il dict in place e vi aggiunge
    '_gate' con la spiegazione di cosa e' successo (finisce nei log e nella
    dashboard, cosi' le declassature sono sempre visibili).
    """
    proposed = briefing.get("signal_level", "NONE")
    ticker = briefing.get("signal_asset")
    notes = []

    def demote(level: str, why: str):
        notes.append(why)
        briefing["signal_level"] = level
        if level == "NONE":
            for k in ("signal_asset", "signal_action", "signal_reasoning",
                      "signal_counter", "signal_suggested_amount_eur",
                      "signal_what_to_do", "signal_what_to_watch"):
                briefing[k] = None
            briefing["signal_importance"] = 1

    briefing["_gate"] = {"proposed_level": proposed, "notes": notes}

    if proposed not in ("GREEN", "YELLOW"):
        notes.append("NONE proposto dall'AI: nessuna verifica necessaria.")
        return briefing

    # 1) Serve un asset identificabile e con dati di prezzo veri
    h = _find_holding(holdings, ticker)
    if h is None:
        demote("NONE", f"Asset '{ticker}' non presente nei dati di oggi: "
                       "impossibile verificare il movimento.")
        return briefing

    daily = _f(h.get("daily_change_pct")) or 0.0
    weekly = _f(h.get("weekly_change_pct")) or 0.0
    monthly = _f(h.get("monthly_change_pct")) or 0.0

    # 2) Anti-ripetizione: stesso ticker, troppo presto, prezzo fermo
    last = _last_signal_for(ticker, journal_path)
    if last:
        try:
            last_dt = datetime.strptime(last["date"][:10], "%Y-%m-%d")
            days = (datetime.now() - last_dt).days
        except (ValueError, KeyError):
            days = None
        last_price = _f(last.get("asset_price_at_signal"))
        now_price = _f(h.get("current"))
        if days is not None and days < COOLDOWN_DAYS and last_price and now_price:
            move = abs(now_price / last_price - 1) * 100
            if move < COOLDOWN_MOVE_PCT:
                demote("NONE",
                       f"Gia' segnalato {ticker} {days} giorni fa a {last_price:.2f}; "
                       f"oggi {now_price:.2f} (variazione {move:.1f}%, sotto la soglia "
                       f"del {COOLDOWN_MOVE_PCT}%). Nessun fatto nuovo: si tace.")
                return briefing

    # 3) Soglie di movimento
    green_ok = abs(daily) >= GREEN_MIN_DAILY or abs(weekly) >= GREEN_MIN_WEEKLY
    yellow_ok = (abs(daily) >= YELLOW_MIN_DAILY
                 or abs(weekly) >= YELLOW_MIN_WEEKLY
                 or abs(monthly) >= YELLOW_MIN_MONTHLY)

    movimento = (f"{ticker}: giorno {daily:+.2f}%, settimana {weekly:+.2f}%, "
                 f"mese {monthly:+.2f}%")

    if proposed == "GREEN" and not green_ok:
        if yellow_ok:
            demote("YELLOW", f"GREEN chiede |giorno|>={GREEN_MIN_DAILY}% o "
                             f"|settimana|>={GREEN_MIN_WEEKLY}%. {movimento}. "
                             "Declassato a YELLOW.")
        else:
            demote("NONE", f"GREEN senza movimento sufficiente. {movimento}.")
            return briefing
    elif proposed == "YELLOW" and not yellow_ok:
        demote("NONE", f"YELLOW chiede |giorno|>={YELLOW_MIN_DAILY}% o "
                       f"|settimana|>={YELLOW_MIN_WEEKLY}% o "
                       f"|mese|>={YELLOW_MIN_MONTHLY}%. {movimento}. "
                       "Giornata normale: nessun segnale.")
        return briefing

    # 4) Importanza calcolata, non dichiarata
    has_catalyst = False
    for ev in (events or {}).get("earnings", []) or []:
        if ticker and ticker.split(".")[0].upper() in str(ev).upper():
            has_catalyst = True
            break

    briefing["_importance_model"] = briefing.get("signal_importance")
    briefing["signal_importance"] = compute_importance(
        daily, weekly, monthly, has_catalyst)
    notes.append(
        f"Confermato {briefing['signal_level']}. {movimento}. "
        f"Importanza calcolata: {briefing['signal_importance']}/5"
        f"{' (catalizzatore a calendario)' if has_catalyst else ''}."
    )
    return briefing
