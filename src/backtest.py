"""
Analisi retrospettiva del diario.
Lanciabile in locale con: python src/backtest.py

Per ogni segnale storico:
1. Legge prezzo al momento del segnale
2. Recupera prezzo attuale
3. Calcola performance "se avessi seguito"
4. Mostra se i segnali dell'AI ti sarebbero convenuti

Non è un backtest statisticamente rigoroso (non considera drawdown, timing di uscita, etc)
ma dà un'idea onesta di quanto fidarsi dell'agente dopo N mesi.
"""
import csv
import os
from datetime import datetime
import yfinance as yf

JOURNAL = "journal/signals.csv"


def analyze():
    if not os.path.exists(JOURNAL):
        print("Nessun diario ancora. Fai girare l'agente per qualche settimana.")
        return

    with open(JOURNAL, encoding="utf-8") as f:
        signals = list(csv.DictReader(f))

    if not signals:
        print("Diario vuoto.")
        return

    print(f"\n{'='*70}")
    print(f"ANALISI DIARIO SEGNALI - {len(signals)} segnali totali")
    print(f"{'='*70}\n")

    tickers = {s["asset_ticker"] for s in signals if s["asset_ticker"]}
    current_prices = {}
    print("Recupero prezzi attuali...")
    for t in tickers:
        try:
            data = yf.Ticker(t).history(period="1d")
            if not data.empty:
                current_prices[t] = float(data["Close"].iloc[-1])
        except Exception as e:
            print(f"  errore {t}: {e}")

    total_return = 0.0
    count_by_level = {"GREEN": 0, "YELLOW": 0}
    wins = 0
    losses = 0

    print(f"\n{'Data':<12} {'Livello':<8} {'Asset':<8} {'Prezzo@segnale':<16} "
          f"{'Attuale':<10} {'Performance':<12}")
    print("-" * 75)

    for s in signals:
        ticker = s["asset_ticker"]
        level = s["signal_level"]
        try:
            price_then = float(s["asset_price_at_signal"])
        except (ValueError, TypeError):
            continue

        price_now = current_prices.get(ticker)
        if price_now is None:
            continue

        perf = ((price_now - price_then) / price_then) * 100
        total_return += perf
        count_by_level[level] = count_by_level.get(level, 0) + 1
        if perf > 0:
            wins += 1
        else:
            losses += 1

        date = s["date"][:10]
        print(f"{date:<12} {level:<8} {ticker:<8} {price_then:<16.2f} "
              f"{price_now:<10.2f} {perf:+.2f}%")

    actionable = wins + losses
    if actionable == 0:
        print("\nNessun segnale analizzabile.")
        return

    print("\n" + "=" * 70)
    print(f"Segnali GREEN: {count_by_level.get('GREEN', 0)}")
    print(f"Segnali YELLOW: {count_by_level.get('YELLOW', 0)}")
    print(f"Hit rate: {wins}/{actionable} = {100*wins/actionable:.1f}%")
    print(f"Performance media per segnale: {total_return/actionable:+.2f}%")
    print("=" * 70)
    print("""
NOTA: questo è un confronto ingenuo (segnale vs prezzo oggi).
Non considera:
- commissioni (~3€/op su Fineco, che su 150€ = 2%)
- timing di uscita (un segnale non specifica quando vendere)
- tasse su eventuali plusvalenze (26%)
- cosa sarebbe successo facendo semplicemente buy-and-hold del tuo ETF World

Per un giudizio completo confronta questa performance media con il tuo
ETF azionario di riferimento sullo stesso periodo.
""")


if __name__ == "__main__":
    analyze()
