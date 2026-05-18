"""
Diario dei segnali emessi dall'agente.
Salva ogni segnale GREEN/YELLOW in un CSV committato nel repo,
così dopo 3-6 mesi puoi confrontare cosa sarebbe successo seguendoli vs hold.
"""
import csv
import os
from datetime import datetime

JOURNAL_PATH = "journal/signals.csv"
JOURNAL_HEADERS = [
    "date",
    "signal_level",
    "asset_ticker",
    "asset_price_at_signal",
    "asset_currency",
    "action_suggested",
    "suggested_amount_eur",
    "reasoning",
    "counter_argument",
    "portfolio_value_eur",
    "model_used",
    # Aggiunti per la cronologia con "cosa fare / cosa monitorare / importanza".
    # Righe storiche pre-rilascio hanno questi campi vuoti.
    "what_to_do",
    "what_to_watch",
    "importance",
]


def _ensure_journal_exists():
    """Crea la cartella e il file CSV con headers se non esistono.
    Se l'header esiste ma è obsoleto (manca qualche colonna), lo aggiorna
    aggiungendo le colonne nuove con valori vuoti per le righe pregresse."""
    os.makedirs(os.path.dirname(JOURNAL_PATH), exist_ok=True)
    if not os.path.exists(JOURNAL_PATH):
        with open(JOURNAL_PATH, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(JOURNAL_HEADERS)
        return

    # Migration: se il CSV esistente non ha tutte le colonne nuove, riscrivilo
    with open(JOURNAL_PATH, "r", newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        try:
            current_headers = next(reader)
        except StopIteration:
            current_headers = []
        rows = list(reader)

    if current_headers == JOURNAL_HEADERS:
        return  # già aggiornato

    missing = [h for h in JOURNAL_HEADERS if h not in current_headers]
    if not missing:
        return

    # Padding di righe esistenti con stringa vuota per le nuove colonne
    padded_rows = [row + [""] * len(missing) for row in rows]
    with open(JOURNAL_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(JOURNAL_HEADERS)
        writer.writerows(padded_rows)
    print(f"  → Journal migrato: +{len(missing)} colonne ({', '.join(missing)})")


def log_signal(briefing: dict, portfolio_data: dict) -> bool:
    """
    Registra un segnale nel diario solo se è GREEN o YELLOW.
    Salta i NONE per non inquinare il file.
    Restituisce True se ha scritto una riga.
    """
    level = briefing.get("signal_level", "NONE")
    if level not in ("GREEN", "YELLOW"):
        return False

    _ensure_journal_exists()

    # Recupera prezzo attuale dell'asset segnalato, se presente nel portafoglio
    ticker = briefing.get("signal_asset")
    price = None
    currency = None
    if ticker:
        for h in portfolio_data.get("holdings", []):
            if h.get("ticker") == ticker:
                price = h.get("current")
                currency = h.get("currency")
                break

    row = [
        datetime.now().strftime("%Y-%m-%d %H:%M"),
        level,
        ticker or "",
        price if price is not None else "",
        currency or "",
        briefing.get("signal_action") or "",
        briefing.get("signal_suggested_amount_eur") or "",
        (briefing.get("signal_reasoning") or "").replace("\n", " ")[:500],
        (briefing.get("signal_counter") or "").replace("\n", " ")[:300],
        portfolio_data.get("total_value_eur_approx", ""),
        briefing.get("_model_used", ""),
        (briefing.get("signal_what_to_do") or "").replace("\n", " ")[:600],
        (briefing.get("signal_what_to_watch") or "").replace("\n", " ")[:600],
        briefing.get("signal_importance") or "",
    ]

    with open(JOURNAL_PATH, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(row)
    print(f"  → Segnale {level} registrato nel diario")
    return True


def read_journal_stats() -> dict:
    """
    Statistiche veloci dal diario: quanti segnali totali, per livello,
    per asset. Utile per capire se l'AI è 'trigger-happy'.
    """
    if not os.path.exists(JOURNAL_PATH):
        return {"total": 0, "by_level": {}, "by_asset": {}}

    counts_level = {}
    counts_asset = {}
    total = 0
    with open(JOURNAL_PATH, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            total += 1
            counts_level[r["signal_level"]] = counts_level.get(r["signal_level"], 0) + 1
            a = r["asset_ticker"] or "?"
            counts_asset[a] = counts_asset.get(a, 0) + 1

    return {"total": total, "by_level": counts_level, "by_asset": counts_asset}


if __name__ == "__main__":
    # test
    fake_briefing = {
        "signal_level": "GREEN",
        "signal_asset": "NVDA",
        "signal_action": "Considerare ingresso piccola somma",
        "signal_reasoning": "Calo 7% su news macro, earnings favorevoli in vista",
        "signal_counter": "Possibile ulteriore calo se Fed hawkish",
        "signal_suggested_amount_eur": 150,
        "_model_used": "claude-sonnet-4-5",
    }
    fake_portfolio = {
        "total_value_eur_approx": 1987.5,
        "holdings": [{"ticker": "NVDA", "current": 199.88, "currency": "USD"}],
    }
    log_signal(fake_briefing, fake_portfolio)
    print(read_journal_stats())
