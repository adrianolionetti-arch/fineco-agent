"""
Orchestratore principale, eseguito da GitHub Actions ogni mattina.
Flusso:
1. Portafoglio → 2. News → 3. Eventi → 4. Briefing AI strutturato
→ 5. Pillola formativa (solo lunedì) → 6. Diario segnali → 7. Dashboard → 8. Email
"""
import json
from portfolio import analyze_portfolio, analyze_watchlist, PORTFOLIO
from news import fetch_news
from events import get_all_events
from briefing import generate_briefing
from emailer import send_email
from journal import log_signal, read_journal_stats
from dashboard_builder import build_dashboard_data
from pillole import get_pillola_della_settimana
from micro_tip import get_micro_tip_del_giorno


def main():
    print("=" * 60)
    print("FINECO DAILY BRIEFING AGENT")
    print("=" * 60)

    print("\n[1/8] Analisi portafoglio...")
    portfolio_data = analyze_portfolio()
    print(f"  → {len(portfolio_data['holdings'])} holdings")
    print(f"  → {len(portfolio_data['alerts'])} alert soglia")

    print("\n[2/8] Analisi watchlist...")
    watchlist_data = analyze_watchlist()
    ok_w = sum(1 for w in watchlist_data if "error" not in w)
    print(f"  → {ok_w}/{len(watchlist_data)} asset in watchlist letti correttamente")

    print("\n[3/8] Fetch news finanziarie...")
    tickers = [h["display_ticker"] for h in PORTFOLIO]
    news = fetch_news(hours_back=24, portfolio_tickers=tickers)
    print(f"  → {len(news)} news raccolte")

    print("\n[4/8] Eventi aziendali/macro...")
    earnings_tickers = [h["earnings_ticker"] for h in PORTFOLIO if h.get("earnings_ticker")]
    events = get_all_events(earnings_tickers)
    print(f"  → {len(events.get('earnings', []))} earnings in 14gg (su {len(earnings_tickers)} ticker)")

    print("\n[5/8] Briefing AI strutturato...")
    briefing = generate_briefing(portfolio_data, news, events, watchlist=watchlist_data)
    print(f"  → Segnale: {briefing.get('signal_level')}")
    if briefing.get("signal_level") in ("GREEN", "YELLOW"):
        print(f"  → Asset: {briefing.get('signal_asset')} "
              f"— {briefing.get('signal_action')}")
    if briefing.get("_tokens"):
        t = briefing["_tokens"]
        print(f"  → Tokens: {t['input']} in / {t['output']} out "
              f"({briefing.get('_model_used')})")

    # Pillola formativa (solo il lunedì, None altrimenti)
    pillola = get_pillola_della_settimana()
    if pillola:
        print(f"  → Pillola della settimana {pillola['settimana_corrente']}: "
              f"{pillola['titolo']}")
        briefing["pillola_settimanale"] = pillola

    # Micro-tip giornaliero (sempre presente)
    micro_tip = get_micro_tip_del_giorno()
    briefing["micro_tip"] = micro_tip
    print(f"  → Micro-tip del giorno: {micro_tip['termine']}")

    print("\n[6/8] Salvataggio nel diario segnali...")
    # Combina portfolio + watchlist per il match prezzo nel log (un segnale
    # su un asset di watchlist deve ancora trovare il prezzo per il journal).
    combined_data = dict(portfolio_data)
    combined_data["holdings"] = portfolio_data["holdings"] + [
        w for w in watchlist_data if "error" not in w
    ]
    log_signal(briefing, combined_data)
    stats = read_journal_stats()
    print(f"  → Storico totale: {stats['total']} segnali {stats['by_level']}")

    print("\n[7/8] Build dashboard data...")
    build_dashboard_data(portfolio_data, briefing, news, events, watchlist=watchlist_data)

    print("\n[8/8] Invio email...")
    ok = send_email(briefing, portfolio_data)
    print("\n" + ("✅ Completato" if ok else "⚠️  Email fallita"))

    # Dump per debug nei log di GitHub Actions
    print("\n--- BRIEFING JSON ---")
    print(json.dumps(briefing, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
