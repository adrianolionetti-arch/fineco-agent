"""
Analisi retrospettiva del diario segnali.
Lanciabile in locale con: python src/backtest.py
Usato anche da briefing.py per reimmettere l'esito storico nel prompt.

Per ogni segnale storico confronta il prezzo del giorno del segnale con quello
di oggi, E con quello che avrebbe fatto negli stessi giorni il benchmark
(VWCE, l'ETF azionario globale che Adriano ha gia' in portafoglio).

La domanda vera non e' "il segnale e' salito?" - in un mercato che sale, sale
quasi tutto. La domanda e' "il segnale ha fatto meglio del non fare nulla?".

--------------------------------------------------------------------------
NOTA SUL BUG DI VALUTA (corretto il 2026-09-22)
--------------------------------------------------------------------------
La versione precedente leggeva 'asset_price_at_signal' dal CSV e lo confrontava
col prezzo attuale preso da yfinance. Ma il CSV registra il prezzo CONVERTITO IN
EURO, mentre yfinance restituisce i ticker USA (GLD, EEM, NVDA...) IN DOLLARI.
Il confronto sommava quindi il tasso di cambio alla performance: ogni segnale su
ticker americano risultava gonfiato di circa il 14-17%.
Esempio verificato: GLD il 2026-07-20 valeva 367.60 USD e 322.17 EUR (cambio
1.1428). Il vecchio codice leggeva 322.17 e lo confrontava con ~398 USD di oggi,
dichiarando +23.66% di guadagno che semplicemente non esisteva.
Risultato: 83% di hit rate e +12.58% medio, entrambi fantasmi.

La correzione: prendere ENTRAMBI gli estremi dalla stessa fonte e nella stessa
valuta (yfinance per tutti e due), ignorando il prezzo salvato nel CSV.
--------------------------------------------------------------------------
"""
import csv
import json
import os
from datetime import datetime

import yfinance as yf

JOURNAL = "journal/signals.csv"
CACHE_PATH = "data/signal_performance.json"
BENCHMARK = "VWCE.MI"   # l'alternativa reale: tenere l'ETF globale e non fare nulla


def _load_history(tickers: set, start: str) -> dict:
    """Serie storiche giornaliere (Close) per ticker, dalla stessa fonte."""
    hist = {}
    for t in sorted(tickers):
        try:
            h = yf.Ticker(t).history(start=start, auto_adjust=True)["Close"]
            if len(h):
                hist[t] = h
        except Exception as e:
            print(f"  [skip] {t}: {e}")
    return hist


def _price_on(hist: dict, ticker: str, day: str):
    """Ultima chiusura disponibile fino a 'day' incluso (gestisce weekend/festivi)."""
    if ticker not in hist:
        return None
    s = hist[ticker][:day]
    return float(s.iloc[-1]) if len(s) else None


def _price_last(hist: dict, ticker: str):
    return float(hist[ticker].iloc[-1]) if ticker in hist else None


def evaluate(limit: int = None) -> dict:
    """
    Valuta i segnali storici contro il benchmark.
    Restituisce un dict riassuntivo (usato anche da briefing.py).
    'limit' = considera solo gli ultimi N segnali.
    """
    if not os.path.exists(JOURNAL):
        return {"error": "Nessun diario ancora.", "signals": []}

    with open(JOURNAL, encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f)
                if r.get("asset_ticker") and r.get("date")]
    if not rows:
        return {"error": "Diario vuoto.", "signals": []}

    if limit:
        rows = rows[-limit:]

    start = min(r["date"][:10] for r in rows)
    hist = _load_history({r["asset_ticker"] for r in rows} | {BENCHMARK}, start)

    results = []
    for r in rows:
        t, day = r["asset_ticker"], r["date"][:10]
        p0, p1 = _price_on(hist, t, day), _price_last(hist, t)
        b0, b1 = _price_on(hist, BENCHMARK, day), _price_last(hist, BENCHMARK)
        if None in (p0, p1, b0, b1):
            continue
        sig = (p1 / p0 - 1) * 100
        bench = (b1 / b0 - 1) * 100
        results.append({
            "date": day,
            "ticker": t,
            "level": r.get("signal_level", ""),
            "signal_pct": sig,
            "bench_pct": bench,
            "alpha_pct": sig - bench,
            "beat": sig > bench,
        })

    if not results:
        return {"error": "Nessun segnale valutabile.", "signals": []}

    n = len(results)
    avg_s = sum(x["signal_pct"] for x in results) / n
    avg_b = sum(x["bench_pct"] for x in results) / n
    beats = sum(1 for x in results if x["beat"])

    by_ticker = {}
    for x in results:
        by_ticker.setdefault(x["ticker"], []).append(x)

    return {
        "n": n,
        "avg_signal_pct": avg_s,
        "avg_bench_pct": avg_b,
        "avg_alpha_pct": avg_s - avg_b,
        "beat_count": beats,
        "beat_rate": beats / n,
        "by_ticker": {
            t: {
                "n": len(xs),
                "avg_signal_pct": sum(x["signal_pct"] for x in xs) / len(xs),
                "avg_bench_pct": sum(x["bench_pct"] for x in xs) / len(xs),
                "avg_alpha_pct": sum(x["alpha_pct"] for x in xs) / len(xs),
                "beat_count": sum(1 for x in xs if x["beat"]),
            }
            for t, xs in by_ticker.items()
        },
        "signals": results,
    }


def write_cache(limit: int = 30, path: str = CACHE_PATH) -> dict:
    """
    Calcola l'esito dei segnali recenti e lo salva su file.
    Gira una volta a settimana (workflow dedicato), NON a ogni briefing:
    scaricare 10+ serie storiche ogni mattina significherebbe sbattere contro
    lo stesso rate limit che stiamo cercando di evitare altrove.
    """
    res = evaluate(limit=limit)
    res.pop("signals", None)          # il dettaglio non serve nel prompt
    res["_generated_at"] = datetime.now().isoformat()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(res, f, indent=2, ensure_ascii=False)
    print(f"Cache performance segnali scritta in {path}")
    return res


def summary_for_prompt(path: str = CACHE_PATH) -> str:
    """
    Riga(e) di testo da iniettare nel prompt del briefing, cosi' che l'AI sappia
    come sono andati i suoi consigli precedenti. Senza questo, l'agente ripete
    all'infinito le tesi che stanno perdendo.

    Legge SOLO dalla cache su file: nessuna chiamata di rete nel percorso del
    briefing quotidiano. Se la cache manca, restituisce stringa vuota e il
    briefing prosegue senza questa sezione.
    """
    if not os.path.exists(path):
        return ""
    try:
        with open(path, encoding="utf-8") as f:
            res = json.load(f)
    except (json.JSONDecodeError, OSError):
        return ""
    if res.get("error") or not res.get("n"):
        return ""

    lines = [
        f"Sui tuoi ultimi {res['n']} segnali: rendimento medio {res['avg_signal_pct']:+.2f}%, "
        f"mentre non fare nulla e tenere VWCE avrebbe reso {res['avg_bench_pct']:+.2f}% "
        f"(differenza {res['avg_alpha_pct']:+.2f}%). "
        f"Hanno battuto il non-fare-nulla {res['beat_count']} volte su {res['n']}."
    ]
    perdenti = sorted(
        ((t, d) for t, d in (res.get("by_ticker") or {}).items()
         if d["n"] >= 3 and d["avg_alpha_pct"] < 0),
        key=lambda kv: kv[1]["avg_alpha_pct"],
    )
    for t, d in perdenti[:4]:
        lines.append(
            f"- {t}: {d['n']} segnali, hanno battuto il benchmark {d['beat_count']}/{d['n']} "
            f"volte, in media {d['avg_alpha_pct']:+.2f}% contro VWCE. "
            f"Non riproporre la stessa tesi senza un fatto NUOVO."
        )
    return "\n".join(lines)


def analyze():
    print(f"\n{'='*78}")
    print("ANALISI DIARIO SEGNALI - confronto contro benchmark VWCE")
    print(f"{'='*78}\n")
    print("Recupero serie storiche...")

    res = evaluate()
    if res.get("error"):
        print(res["error"])
        return

    print(f"\n{'Data':<12} {'Livello':<8} {'Asset':<10} {'Segnale':>9} "
          f"{'VWCE':>9} {'Alfa':>9}  Batte")
    print("-" * 78)
    for x in res["signals"]:
        print(f"{x['date']:<12} {x['level']:<8} {x['ticker']:<10} "
              f"{x['signal_pct']:+8.2f}% {x['bench_pct']:+8.2f}% "
              f"{x['alpha_pct']:+8.2f}%  {'si' if x['beat'] else 'NO'}")

    print("\n" + "=" * 78)
    print(f"Segnali valutati              : {res['n']}")
    print(f"Rendimento medio segnale      : {res['avg_signal_pct']:+.2f}%")
    print(f"Rendimento medio VWCE         : {res['avg_bench_pct']:+.2f}%")
    print(f"ALFA medio (segnale - VWCE)   : {res['avg_alpha_pct']:+.2f}%")
    print(f"Segnali che battono VWCE      : {res['beat_count']}/{res['n']} "
          f"= {res['beat_rate']*100:.0f}%")
    print("=" * 78)

    print(f"\n{'Per ticker':<12} {'n':>4} {'segnale':>9} {'VWCE':>9} {'alfa':>9}  batte")
    print("-" * 78)
    for t, d in sorted(res["by_ticker"].items(), key=lambda kv: -kv[1]["n"]):
        print(f"{t:<12} {d['n']:>4} {d['avg_signal_pct']:+8.2f}% "
              f"{d['avg_bench_pct']:+8.2f}% {d['avg_alpha_pct']:+8.2f}%  "
              f"{d['beat_count']}/{d['n']}")

    print("""
NOTA: confronto prezzo-al-segnale vs prezzo-oggi, a valuta coerente. Non considera
commissioni (~2.95€/op su Fineco), timing di uscita, ne' tasse (26% sulle plusvalenze).
I segnali piu' vecchi hanno avuto piu' tempo per muoversi: e' proprio per questo che
il confronto col benchmark sugli STESSI giorni e' l'unico numero che significhi qualcosa.
""")


if __name__ == "__main__":
    import sys
    if "--write-cache" in sys.argv:
        write_cache()
    else:
        analyze()
