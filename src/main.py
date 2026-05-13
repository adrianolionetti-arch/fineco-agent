"""
Orchestratore principale, eseguito da GitHub Actions ogni mattina.
Flusso:
1. Portafoglio → 2. News → 3. Eventi → 4. Briefing AI strutturato
→ 5. Diario segnali → 6. Email
"""
import json
from portfolio import analyze_portfolio, PORTFOLIO
from news import fetch_news
from events import get_all_events
from briefing import generate_briefing
from emailer import send_email
from journal import log_signal, read_journal_stats
from dashboard_builder import build_dashboard_data


def main():
    print("=" * 60)
    print("FINECO DAILY BRIEFING AGENT")
    print("=" * 60)

    print("\n[1/7] Analisi portafoglio...")
    portfolio_data = analyze_portfolio()
    print(f"  → {len(portfolio_data['holdings'])} holdings")
    print(f"  → {len(portfolio_data['alerts'])} alert soglia")

    print("\n[2/7] Fetch news finanziarie...")
    tickers = [h["display_ticker"] for h in PORTFOLIO]
    news = fetch_news(hours_back=24, portfolio_tickers=tickers)
    print(f"  → {len(news)} news raccolte")

    print("\n[3/7] Eventi aziendali/macro...")
    events = get_all_events(tickers)
    print(f"  → {len(events.get('earnings', []))} earnings in 14gg")

    print("\n[4/7] Briefing AI strutturato...")
    briefing = generate_briefing(portfolio_data, news, events)
    print(f"  → Segnale: {briefing.get('signal_level')}")
    if briefing.get("signal_level") in ("GREEN", "YELLOW"):
        print(f"  → Asset: {briefing.get('signal_asset')} "
              f"— {briefing.get('signal_action')}")
    if briefing.get("_tokens"):
        t = briefing["_tokens"]
        print(f"  → Tokens: {t['input']} in / {t['output']} out "
              f"({briefing.get('_model_used')})")

    print("\n[5/7] Salvataggio nel diario segnali...")
    log_signal(briefing, portfolio_data)
    stats = read_journal_stats()
    print(f"  → Storico totale: {stats['total']} segnali {stats['by_level']}")

    print("\n[6/7] Build dashboard data...")
    build_dashboard_data(portfolio_data, briefing, news, events)

    print("\n[7/7] Invio email...")
    ok = send_email(briefing, portfolio_data)
    print("\n" + ("✅ Completato" if ok else "⚠️  Email fallita"))

    # Dump per debug nei log di GitHub Actions
    print("\n--- BRIEFING JSON ---")
    print(json.dumps(briefing, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
