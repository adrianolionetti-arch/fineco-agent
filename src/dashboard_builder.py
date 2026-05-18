"""
Costruisce i dati JSON che alimentano la dashboard HTML statica.
Output: docs/data.json (consumato da docs/index.html via fetch).

Include:
- snapshot portafoglio corrente (solo %, no valori assoluti per privacy)
- storico performance cumulativa (appeso giorno per giorno in data/history.json)
- lista segnali dal diario con esito attuale
- benchmark comparison (VWCE via EODHD)
- pillola formativa corrente + archivio (Tappa 4)

NB: i prezzi (benchmark e prezzo attuale segnali) vengono presi da EODHD,
non da yfinance, perché i runner GitHub Actions sono rate-limitati da
Yahoo e tornano vuoti quasi sempre.
"""
import json
import os
import csv
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from pillole import get_pillola_della_settimana, get_archivio_pillole
from portfolio import PORTFOLIO

HISTORY_FILE = "data/history.json"
DASHBOARD_JSON = "docs/data.json"
JOURNAL_FILE = "journal/signals.csv"
BENCHMARK_SYMBOL = "VWCE.XETRA"  # EODHD symbol per Vanguard FTSE All-World
BENCHMARK_DISPLAY = "VWCE"  # nome visualizzato in dashboard
EOD_API_KEY = os.environ.get("EOD_API_KEY", "")


def _append_history(portfolio_data: dict):
    """Appende una riga nello storico del portafoglio (solo performance %, non valore assoluto)."""
    os.makedirs("data", exist_ok=True)

    history = []
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                history = json.load(f)
        except json.JSONDecodeError:
            history = []

    # Calcola % performance portafoglio (media pesata approx delle daily changes)
    holdings = [h for h in portfolio_data.get("holdings", []) if "error" not in h]
    if not holdings:
        return history

    total_value = sum(h["current"] * h["quantity"] for h in holdings)
    weighted_daily = sum(
        (h["current"] * h["quantity"] / total_value) * h["daily_change_pct"]
        for h in holdings
    ) if total_value > 0 else 0

    today_str = datetime.now().strftime("%Y-%m-%d")

    # Evita duplicati per stessa data (sovrascrive)
    history = [h for h in history if h.get("date") != today_str]

    entry = {
        "date": today_str,
        "daily_change_pct": round(weighted_daily, 2),
        "holdings_snapshot": [
            {
                "ticker": h["ticker"],
                "daily_pct": h["daily_change_pct"],
                "weekly_pct": h["weekly_change_pct"],
                "monthly_pct": h["monthly_change_pct"],
            }
            for h in holdings
        ],
    }
    history.append(entry)

    # Mantieni ultimi 365 giorni
    history = sorted(history, key=lambda x: x["date"])[-365:]

    # Calcola performance cumulativa "indicizzata" a 100 al primo giorno registrato
    cum = 100.0
    for h in history:
        cum *= (1 + h["daily_change_pct"] / 100)
        h["cumulative_index"] = round(cum, 2)

    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)

    return history


def _get_benchmark_history(days: int = 90):
    """Scarica serie storica benchmark via EODHD, indicizzata a 100 al primo giorno."""
    if not EOD_API_KEY:
        print("[WARN] benchmark: EOD_API_KEY non configurata")
        return []
    try:
        qs = urllib.parse.urlencode({
            "api_token": EOD_API_KEY,
            "fmt": "json",
            "period": "d",
            "order": "a",  # ascending: oldest first
        })
        url = f"https://eodhd.com/api/eod/{BENCHMARK_SYMBOL}?{qs}"
        req = urllib.request.Request(url, headers={"User-Agent": "fineco-agent"})
        with urllib.request.urlopen(req, timeout=15) as r:
            hist = json.loads(r.read().decode("utf-8"))
        if not isinstance(hist, list) or not hist:
            print(f"[WARN] benchmark EODHD: risposta vuota o malformata")
            return []
        # Prendi solo ultimi `days` giorni di trading
        hist = hist[-days:]
        first_price = float(hist[0]["close"])
        if first_price == 0:
            return []
        data = []
        for h in hist:
            close = float(h.get("close") or 0)
            if close <= 0:
                continue
            data.append({
                "date": h["date"],
                "cumulative_index": round((close / first_price) * 100, 2),
            })
        return data
    except Exception as e:
        print(f"[WARN] benchmark: {e}")
        return []


def _read_journal_with_performance(portfolio_data: dict):
    """Legge il diario e calcola la performance attuale di ogni segnale.

    Usa i prezzi già caricati in portfolio_data (via EODHD/Twelvedata)
    invece di rifare fetch via yfinance (che è rate-limitato sui runner
    GitHub Actions). I segnali sono sempre su asset del nostro portfolio,
    quindi i prezzi attuali sono già disponibili.
    """
    if not os.path.exists(JOURNAL_FILE):
        return []

    with open(JOURNAL_FILE, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        return []

    # Costruisci mappa ticker → prezzo attuale dai dati già caricati.
    # I segnali storici usano vari alias (display "1NVDA.MI", primary
    # "NVDA", a volte "VWCE.MI" o "VWCE.XETRA"). Registro tutti gli alias
    # noti dalla config PORTFOLIO con lo stesso prezzo del display_ticker.
    current_prices = {}
    holdings_by_display = {
        h["ticker"]: h["current"]
        for h in portfolio_data.get("holdings", [])
        if "error" not in h
    }
    for cfg in PORTFOLIO:
        display = cfg["display_ticker"]
        price = holdings_by_display.get(display)
        if price is None:
            continue
        # Tutti i possibili alias per questo asset
        for alias in {
            cfg.get("display_ticker"),
            cfg.get("primary_symbol"),
            cfg.get("symbol"),
            cfg.get("fallback_yf"),
            cfg.get("fallback_yf_2"),
            cfg.get("earnings_ticker"),
        }:
            if alias:
                current_prices[alias] = price

    enriched = []
    for r in rows:
        ticker = r["asset_ticker"]
        try:
            price_then = float(r["asset_price_at_signal"])
        except (ValueError, TypeError):
            price_then = None

        price_now = current_prices.get(ticker)
        perf = None
        if price_then and price_now:
            perf = round(((price_now - price_then) / price_then) * 100, 2)

        # Importance può essere int, stringa o vuoto se segnale pre-feature
        try:
            importance = int(r.get("importance") or 0) or None
        except (TypeError, ValueError):
            importance = None

        enriched.append({
            "date": r["date"],
            "level": r["signal_level"],
            "ticker": ticker,
            "action": r["action_suggested"],
            "reasoning": r["reasoning"],
            "counter": r["counter_argument"],
            "price_at_signal": price_then,
            "price_now": price_now,
            "performance_pct": perf,
            "model": r.get("model_used", ""),
            "what_to_do": r.get("what_to_do") or "",
            "what_to_watch": r.get("what_to_watch") or "",
            "importance": importance,
        })

    # Più recenti in alto
    return sorted(enriched, key=lambda x: x["date"], reverse=True)


def _compute_backtest_summary(signals: list) -> dict:
    """Statistiche aggregate dei segnali per la dashboard."""
    actionable = [s for s in signals if s["performance_pct"] is not None]
    if not actionable:
        return {
            "total_signals": len(signals),
            "analyzable": 0,
            "hit_rate": None,
            "avg_performance": None,
            "green_count": 0,
            "yellow_count": 0,
        }

    wins = sum(1 for s in actionable if s["performance_pct"] > 0)
    greens = [s for s in actionable if s["level"] == "GREEN"]
    yellows = [s for s in actionable if s["level"] == "YELLOW"]

    return {
        "total_signals": len(signals),
        "analyzable": len(actionable),
        "hit_rate": round(100 * wins / len(actionable), 1),
        "avg_performance": round(sum(s["performance_pct"] for s in actionable) / len(actionable), 2),
        "green_count": len(greens),
        "yellow_count": len(yellows),
        "green_avg_perf": round(sum(s["performance_pct"] for s in greens) / len(greens), 2) if greens else None,
        "yellow_avg_perf": round(sum(s["performance_pct"] for s in yellows) / len(yellows), 2) if yellows else None,
    }


def _sanitize_watchlist(watchlist: list) -> list:
    """Sanitizza la watchlist per esporla in dashboard (no posizione, niente assoluti)."""
    out = []
    for w in watchlist or []:
        if "error" in w:
            continue
        out.append({
            "name": w["name"],
            "ticker": w["display_ticker"],
            "type": w.get("type", "unknown"),
            "category": w.get("category", "altro"),
            "currency": w["currency"],
            "current_price": w["current"],
            "daily_pct": w["daily_change_pct"],
            "weekly_pct": w["weekly_change_pct"],
            "monthly_pct": w["monthly_change_pct"],
            "ucits_equivalents": w.get("ucits_equivalents") or [],
        })
    return out


def build_dashboard_data(portfolio_data: dict, briefing: dict, news: list, events: dict,
                          watchlist: list | None = None):
    """Genera docs/data.json con tutto quello che serve alla dashboard."""
    os.makedirs("docs", exist_ok=True)

    # 1. Aggiorna storico e recupera serie
    history = _append_history(portfolio_data)
    benchmark = _get_benchmark_history(days=90)

    # 2. Holdings sanitizzate (solo %, no valore assoluto della posizione)
    # Include serie storica prezzi unitari (ok da esporre, sono dati pubblici).
    holdings_public = []
    for h in portfolio_data.get("holdings", []):
        if "error" in h:
            continue
        # Ultimi 60 giorni di chiusure per il grafico "prezzi assoluti"
        price_series = h.get("price_series") or []
        if price_series:
            price_series = price_series[-60:]
        quantity = h.get("quantity", 0)
        position_value = round(h.get("current", 0) * quantity, 2)
        holdings_public.append({
            "name": h["name"],
            "ticker": h["ticker"],
            "type": h.get("type", "unknown"),
            "currency": h["currency"],
            "current_price": h["current"],
            "quantity": quantity,
            "position_value": position_value,
            "daily_pct": h["daily_change_pct"],
            "weekly_pct": h["weekly_change_pct"],
            "monthly_pct": h["monthly_change_pct"],
            "price_history": price_series,
        })

    # 3. Segnali storici con performance
    signals = _read_journal_with_performance(portfolio_data)
    backtest = _compute_backtest_summary(signals)

    # 4. Pillole formative (Tappa 4)
    # La dashboard mostra sempre la pillola della settimana corrente,
    # indipendentemente dal giorno della settimana (l'email invece solo il lunedì).
    # Prima di START_DATE entrambe sono None / [].
    pillola_corrente = get_pillola_della_settimana()
    archivio_pillole = get_archivio_pillole()

    # 5. Payload finale
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_value_eur": portfolio_data.get("total_value_eur_approx", 0),
        "briefing": {
            "summary": briefing.get("summary"),
            "portfolio_note": briefing.get("portfolio_note"),
            "events": briefing.get("events", []),
            "signal_level": briefing.get("signal_level", "NONE"),
            "signal_asset": briefing.get("signal_asset"),
            "signal_action": briefing.get("signal_action"),
            "signal_reasoning": briefing.get("signal_reasoning"),
            "signal_counter": briefing.get("signal_counter"),
            "signal_suggested_amount_eur": briefing.get("signal_suggested_amount_eur"),
            "signal_what_to_do": briefing.get("signal_what_to_do"),
            "signal_what_to_watch": briefing.get("signal_what_to_watch"),
            "signal_importance": briefing.get("signal_importance"),
            "closing_note": briefing.get("closing_note"),
            "model_used": briefing.get("_model_used"),
        },
        "holdings": holdings_public,
        "portfolio_history": history,
        "benchmark": {
            "ticker": BENCHMARK_DISPLAY,
            "series": benchmark,
        },
        "signals": signals[:50],  # max 50 più recenti
        "backtest": backtest,
        "news": [
            {"source": n["source"], "title": n["title"], "link": n.get("link", "")}
            for n in news[:8]
        ],
        "events_upcoming": events.get("earnings", []),
        "watchlist": _sanitize_watchlist(watchlist or []),
        # Tappa 4: pillole formative
        "pillola_corrente": pillola_corrente,
        "archivio_pillole": archivio_pillole,
    }

    with open(DASHBOARD_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False, default=str)

    print(f"  → Dashboard data scritto in {DASHBOARD_JSON}")
    if pillola_corrente:
        print(f"  → Pillola corrente: settimana {pillola_corrente.get('settimana_corrente')} — {pillola_corrente.get('titolo')}")
        print(f"  → Archivio: {len(archivio_pillole)} pillole uscite")
    else:
        print("  → Pillole: prima di START_DATE, nessuna pillola attiva")
    return payload


if __name__ == "__main__":
    # dry test
    fake_portfolio = {
        "holdings": [
            {"name": "NVIDIA", "ticker": "NVDA", "type": "stock", "quantity": 1,
             "current": 199.88, "currency": "USD", "daily_change_pct": -1.08,
             "weekly_change_pct": 1.71, "monthly_change_pct": 13.8}
        ],
    }
    fake_briefing = {"summary": "test", "signal_level": "NONE"}
    build_dashboard_data(fake_portfolio, fake_briefing, [], {})
