"""
Costruisce i dati JSON che alimentano la dashboard HTML statica.
Output: docs/data.json (consumato da docs/index.html via fetch).

Include:
- snapshot portafoglio corrente (solo %, no valori assoluti per privacy)
- storico performance cumulativa (appeso giorno per giorno in data/history.json)
- lista segnali dal diario con esito attuale
- benchmark comparison (VWCE.DE come richiesto)
- news rilevanti
"""
import json
import os
import csv
from datetime import datetime, timezone
import yfinance as yf

HISTORY_FILE = "data/history.json"
DASHBOARD_JSON = "docs/data.json"
JOURNAL_FILE = "journal/signals.csv"
BENCHMARK_TICKER = "VWCE.DE"  # Vanguard FTSE All-World, ETF azionario globale


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
    """Scarica performance benchmark ETF World degli ultimi N giorni, indicizzata a 100."""
    try:
        t = yf.Ticker(BENCHMARK_TICKER)
        hist = t.history(period=f"{days}d")
        if hist.empty:
            return []
        first_price = float(hist["Close"].iloc[0])
        data = []
        for date, row in hist.iterrows():
            price = float(row["Close"])
            indexed = (price / first_price) * 100
            data.append({
                "date": date.strftime("%Y-%m-%d"),
                "cumulative_index": round(indexed, 2),
            })
        return data
    except Exception as e:
        print(f"[WARN] benchmark: {e}")
        return []


def _read_journal_with_performance():
    """Legge il diario e calcola la performance attuale di ogni segnale."""
    if not os.path.exists(JOURNAL_FILE):
        return []

    with open(JOURNAL_FILE, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        return []

    # Batch fetch prezzi attuali (uno per ticker unico)
    tickers = {r["asset_ticker"] for r in rows if r["asset_ticker"]}
    current_prices = {}
    for t in tickers:
        try:
            data = yf.Ticker(t).history(period="1d")
            if not data.empty:
                current_prices[t] = float(data["Close"].iloc[-1])
        except Exception:
            pass

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


def build_dashboard_data(portfolio_data: dict, briefing: dict, news: list, events: dict):
    """Genera docs/data.json con tutto quello che serve alla dashboard."""
    os.makedirs("docs", exist_ok=True)

    # 1. Aggiorna storico e recupera serie
    history = _append_history(portfolio_data)
    benchmark = _get_benchmark_history(days=90)

    # 2. Holdings sanitizzate (solo %, no valore assoluto)
    holdings_public = []
    for h in portfolio_data.get("holdings", []):
        if "error" in h:
            continue
        holdings_public.append({
            "name": h["name"],
            "ticker": h["ticker"],
            "type": h.get("type", "unknown"),
            "currency": h["currency"],
            "current_price": h["current"],  # prezzo unitario pubblico, non posizione
            "daily_pct": h["daily_change_pct"],
            "weekly_pct": h["weekly_change_pct"],
            "monthly_pct": h["monthly_change_pct"],
        })

    # 3. Segnali storici con performance
    signals = _read_journal_with_performance()
    backtest = _compute_backtest_summary(signals)

    # 4. Payload finale
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
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
            "closing_note": briefing.get("closing_note"),
            "model_used": briefing.get("_model_used"),
        },
        "holdings": holdings_public,
        "portfolio_history": history,
        "benchmark": {
            "ticker": BENCHMARK_TICKER,
            "series": benchmark,
        },
        "signals": signals[:50],  # max 50 più recenti
        "backtest": backtest,
        "news": [
            {"source": n["source"], "title": n["title"], "link": n.get("link", "")}
            for n in news[:8]
        ],
        "events_upcoming": events.get("earnings", []),
    }

    with open(DASHBOARD_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False, default=str)

    print(f"  → Dashboard data scritto in {DASHBOARD_JSON}")
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
