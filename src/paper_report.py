"""
Verdetto mensile: cosa ha deciso l'agente, e se e' servito.

Gira il primo del mese. Fino a quel momento le decisioni restano cifrate e
Adriano non le vede: e' l'unica cosa che rende il confronto sensato.

METRICA
-------
Rendimento TIME-WEIGHTED, non variazione del valore. Il paper riceve 500 EUR al
mese di versamento virtuale: confrontare i valori finali premierebbe chi versa di
piu', non chi decide meglio. Il TWR isola l'effetto delle decisioni.
Per il portafoglio reale di Adriano usiamo 'cumulative_index' di history.json,
che e' costruito allo stesso modo (composizione dei rendimenti giornalieri).
"""
import json
import os
import sys
from datetime import datetime, timezone

import paper_portfolio as pp

HISTORY_FILE = "data/history.json"


def twr_from_navs(nav_history: list, start: str, end: str) -> float | None:
    """Rendimento time-weighted, neutralizzando i versamenti."""
    rows = [r for r in nav_history if start <= r["date"] <= end and r.get("nav")]
    if len(rows) < 2:
        return None
    fattore = 1.0
    for prima, dopo in zip(rows, rows[1:]):
        if not prima["nav"]:
            continue
        r = (dopo["nav"] - (dopo.get("contribution") or 0)) / prima["nav"] - 1
        fattore *= (1 + r)
    return (fattore - 1) * 100


def real_portfolio_twr(start: str, end: str) -> float | None:
    if not os.path.exists(HISTORY_FILE):
        return None
    with open(HISTORY_FILE, encoding="utf-8") as f:
        hist = json.load(f)
    rows = [h for h in hist if start <= h["date"] <= end and h.get("cumulative_index")]
    if len(rows) < 2:
        return None
    return (rows[-1]["cumulative_index"] / rows[0]["cumulative_index"] - 1) * 100


def benchmark_twr(start: str, end: str, ticker: str = "VWCE.MI") -> float | None:
    try:
        import yfinance as yf
        h = yf.Ticker(ticker).history(start=start, end=end, auto_adjust=True)["Close"]
        if len(h) < 2:
            return None
        return (float(h.iloc[-1]) / float(h.iloc[0]) - 1) * 100
    except Exception:
        return None


def build(month: str | None = None) -> dict:
    """month nel formato YYYY-MM; default = mese appena concluso."""
    state = pp.load_state()
    if not state:
        return {"error": "nessuno stato del portafoglio paper"}

    integra, msg = pp.verify_chain(state)

    if not month:
        oggi = datetime.now(timezone.utc)
        anno, mese = (oggi.year, oggi.month - 1) if oggi.month > 1 else (oggi.year - 1, 12)
        month = f"{anno:04d}-{mese:02d}"

    decisioni = [d for d in state.get("decisions", []) if d["date"].startswith(month)]
    navs = [r for r in state.get("nav_history", []) if r["date"].startswith(month)]
    if not decisioni:
        return {"error": f"nessuna decisione registrata per {month}"}

    start, end = min(d["date"] for d in decisioni), max(d["date"] for d in decisioni)
    operazioni = [d for d in decisioni if d["action"] != "HOLD" and d["executed"]]
    rifiutate = [d for d in decisioni if d["action"] != "HOLD" and not d["executed"]]
    hold = [d for d in decisioni if d["action"] == "HOLD"]

    paper = twr_from_navs(state.get("nav_history", []), start, end)
    reale = real_portfolio_twr(start, end)
    bench = benchmark_twr(start, end)

    commissioni = len(operazioni) * pp.COMMISSION_EUR
    return {
        "month": month, "start": start, "end": end,
        "integrita": msg, "integra": integra,
        "giorni": len(decisioni),
        "operazioni": operazioni, "n_operazioni": len(operazioni),
        "n_hold": len(hold), "n_rifiutate": len(rifiutate),
        "quota_hold": len(hold) / len(decisioni) * 100,
        "commissioni_eur": round(commissioni, 2),
        "twr_paper": paper, "twr_reale": reale, "twr_benchmark": bench,
        "alfa_vs_reale": (paper - reale) if (paper is not None and reale is not None) else None,
        "alfa_vs_benchmark": (paper - bench) if (paper is not None and bench is not None) else None,
        "nav_finale": navs[-1]["nav"] if navs else None,
        "versato_nel_mese": round(sum(r.get("contribution") or 0 for r in navs), 2),
    }


def _fmt(v, suffix="%"):
    return "n/d" if v is None else f"{v:+.2f}{suffix}"


def to_text(r: dict) -> str:
    if r.get("error"):
        return f"Report paper non disponibile: {r['error']}"

    righe = [
        f"PORTAFOGLIO PARALLELO — {r['month']}",
        f"Periodo {r['start']} → {r['end']} ({r['giorni']} giorni di decisione)",
        "",
        "DECISIONI",
        f"  Operazioni eseguite : {r['n_operazioni']}",
        f"  Giorni di HOLD      : {r['n_hold']} ({r['quota_hold']:.0f}%)",
        f"  Ordini rifiutati    : {r['n_rifiutate']} (fondi o soglia minima)",
        f"  Commissioni pagate  : €{r['commissioni_eur']:.2f}",
        "",
    ]
    if r["operazioni"]:
        righe.append("COSA HA FATTO")
        for d in r["operazioni"]:
            righe.append(f"  {d['date']}  {d['action']:4} {d['ticker']:9} "
                         f"€{d['amount_eur']:.2f}  (convinzione {d.get('conviction')}/5)")
            righe.append(f"            {d['rationale']}")
        righe.append("")

    righe += [
        "RENDIMENTO TIME-WEIGHTED (neutralizza i versamenti)",
        f"  Portafoglio paper (agente) : {_fmt(r['twr_paper'])}",
        f"  Portafoglio reale (Adriano): {_fmt(r['twr_reale'])}",
        f"  VWCE, non fare nulla       : {_fmt(r['twr_benchmark'])}",
        "",
        f"  Differenza agente − Adriano: {_fmt(r['alfa_vs_reale'])}",
        f"  Differenza agente − VWCE   : {_fmt(r['alfa_vs_benchmark'])}",
        "",
        f"Integrita' del registro: {r['integrita']}",
        "",
        "COME LEGGERE QUESTI NUMERI",
        "Un mese non basta per dire chi e' piu' bravo: con pochi giorni e poche",
        "operazioni la differenza e' in larga parte casuale. Quello che questo mese",
        "misura davvero e' il processo — quante decisioni nette l'agente produce,",
        "quanto spesso sa stare fermo, se gli ordini erano eseguibili col capitale",
        "disponibile. Il giudizio sulla performance ha senso dal terzo mese in poi.",
    ]
    return "\n".join(righe)


def to_html(r: dict) -> str:
    if r.get("error"):
        return f"<p>Report paper non disponibile: {r['error']}</p>"

    ops = "".join(
        f"""<tr><td style="padding:6px 8px;font-family:monospace;font-size:12px;">{d['date']}</td>
            <td style="padding:6px 8px;font-weight:600;color:{'#2e7d32' if d['action']=='BUY' else '#c62828'};">{d['action']}</td>
            <td style="padding:6px 8px;font-family:monospace;">{d['ticker']}</td>
            <td style="padding:6px 8px;text-align:right;">€{d['amount_eur']:.2f}</td>
            <td style="padding:6px 8px;font-size:12px;color:#555;">{d['rationale']}</td></tr>"""
        for d in r["operazioni"]
    ) or '<tr><td colspan="5" style="padding:10px;color:#666;">Nessuna operazione: l\'agente è rimasto fermo tutto il mese.</td></tr>'

    def riga(label, val, forte=False):
        col = "#666" if val is None else ("#2e7d32" if val >= 0 else "#c62828")
        peso = "700" if forte else "400"
        return (f'<tr><td style="padding:6px 8px;">{label}</td>'
                f'<td style="padding:6px 8px;text-align:right;font-family:monospace;'
                f'font-weight:{peso};color:{col};">{_fmt(val)}</td></tr>')

    return f"""
    <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
                max-width:680px;margin:0 auto;padding:20px;color:#222;">
      <div style="font-size:11px;text-transform:uppercase;letter-spacing:0.12em;
                  color:#8a6db0;font-weight:600;">Verdetto mensile</div>
      <h2 style="margin:6px 0 2px;color:#1a1a2e;">Portafoglio parallelo — {r['month']}</h2>
      <p style="color:#666;font-size:13px;margin:0 0 18px;">
        {r['start']} → {r['end']} · {r['giorni']} giorni di decisione ·
        {r['n_operazioni']} operazioni · {r['quota_hold']:.0f}% di giorni fermo ·
        €{r['commissioni_eur']:.2f} di commissioni
      </p>

      <h3 style="font-size:15px;margin:18px 0 6px;">Cosa ha fatto</h3>
      <table cellpadding="0" cellspacing="0" width="100%"
             style="border-collapse:collapse;font-size:13px;background:#fafafa;border-radius:8px;">
        {ops}
      </table>

      <h3 style="font-size:15px;margin:22px 0 6px;">Rendimento time-weighted</h3>
      <table cellpadding="0" cellspacing="0" width="100%"
             style="border-collapse:collapse;font-size:14px;">
        {riga("Portafoglio paper (agente)", r['twr_paper'])}
        {riga("Portafoglio reale (tuo)", r['twr_reale'])}
        {riga("VWCE, non fare nulla", r['twr_benchmark'])}
        <tr><td colspan="2" style="border-top:1px solid #ddd;height:6px;"></td></tr>
        {riga("Differenza agente − tuo", r['alfa_vs_reale'], forte=True)}
        {riga("Differenza agente − VWCE", r['alfa_vs_benchmark'], forte=True)}
      </table>
      <p style="font-size:11px;color:#888;margin:6px 0 0;">
        Il time-weighted neutralizza i versamenti: i 500 €/mese del paper non lo
        fanno sembrare più bravo di quanto sia.
      </p>

      <div style="background:#f5f7fa;padding:14px 16px;border-radius:8px;margin:22px 0;
                  border-left:4px solid #90a4ae;">
        <div style="font-size:12px;color:#444;line-height:1.55;">
          <strong>Come leggere questi numeri.</strong> Un mese non basta per dire chi è
          più bravo: con pochi giorni e poche operazioni la differenza è in larga parte
          casuale. Questo mese misura il <em>processo</em> — quante decisioni nette
          produce, quanto spesso sa stare fermo, se gli ordini erano eseguibili col
          capitale che hai. Il giudizio sulla performance ha senso dal terzo mese.
        </div>
      </div>

      <p style="font-size:11px;color:#999;border-top:1px solid #eee;padding-top:10px;">
        Registro: {r['integrita']}. Ogni decisione è firmata con l'hash della precedente
        e non è stata modificata dopo la scrittura.
      </p>
    </div>
    """


if __name__ == "__main__":
    mese = sys.argv[1] if len(sys.argv) > 1 else None
    rep = build(mese)
    print(to_text(rep))
    if "--email" in sys.argv and not rep.get("error"):
        from weekend_quiz import send_email
        send_email(f"📊 Verdetto mensile — portafoglio parallelo {rep['month']}",
                   to_html(rep), to_text(rep))
