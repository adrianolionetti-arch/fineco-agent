"""
Esecuzione quotidiana del portafoglio paper: prezzi, decisione, registrazione.
La logica pura (validazione ordini, firme, NAV) sta in paper_portfolio.py.
"""
import json
import os
from datetime import datetime, timezone

import anthropic

import paper_portfolio as pp
from portfolio import _cache_recover, _cache_store, _fetch_yfinance

MODEL = os.environ.get("PAPER_MODEL", os.environ.get("CLAUDE_MODEL", "claude-opus-5"))

SYSTEM = """Gestisci un portafoglio reale di un investitore privato italiano, profilo
medio/medio-basso, che opera su Fineco. Non stai scrivendo a lui: stai prendendo una
decisione operativa che verra' eseguita cosi' com'e' e misurata a fine mese.

OGNI GIORNO DEVI SCEGLIERE UNA COSA SOLA:
- BUY <ticker> <importo in EUR>
- SELL <ticker> <importo in EUR>
- HOLD (non fare nulla)

REGOLE NON NEGOZIABILI
1. HOLD e' la risposta corretta nella maggior parte dei giorni. Non e' una resa:
   e' una decisione. Operare senza motivo distrugge valore via commissioni.
2. NON esistono "valuta", "monitora", "aspetta il dato di domani". Se aspetti,
   quella e' HOLD e lo dici. Se compri, compri oggi a questo prezzo.
3. Ogni operazione costa 2.95 EUR di commissione. Su un ordine da 200 EUR e' l'1.5%:
   devi crederci abbastanza da superare quel costo. L'ordine minimo e' 200 EUR,
   con una sola eccezione: puoi sempre liquidare per intero una posizione, anche
   se vale meno di 200 EUR.
4. Puoi operare SOLO sui ticker dell'universo che ti viene dato, e solo con la
   liquidita' disponibile. Non puoi andare a debito.
5. Il portafoglio e' gia' molto concentrato su azionario USA e tecnologia. Tienine
   conto: aggiungere altro tech aumenta un rischio gia' alto.
6. La motivazione sta in DUE FRASI. Non e' un tema d'italiano, e' un ordine.

Rispondi SOLO con JSON valido:
{"action":"BUY"|"SELL"|"HOLD","ticker":"<ticker o null>","amount_eur":<numero o null>,
 "conviction":1-5,"rationale":"max due frasi"}"""


def fetch_universe_prices(known: dict | None = None) -> dict:
    """
    Prezzi dell'universo paper. Riusa i prezzi gia' scaricati dal briefing dove
    possibile, poi yfinance, poi la cache locale: ogni chiamata in meno e' un 429
    in meno.
    """
    prices = {}
    known = known or {}
    for ticker in pp.UNIVERSE:
        if ticker in known and known[ticker]:
            prices[ticker] = known[ticker]
            continue
        data = _fetch_yfinance(ticker)
        if "error" not in data and data.get("current"):
            prices[ticker] = round(float(data["current"]), 4)
            _cache_store(ticker, {"current": prices[ticker], "currency": "EUR",
                                  "daily_change_pct": data.get("daily_change_pct"),
                                  "weekly_change_pct": data.get("weekly_change_pct"),
                                  "monthly_change_pct": data.get("monthly_change_pct")})
        else:
            rec = _cache_recover(ticker, data.get("error", "fonte non disponibile"))
            if rec:
                prices[ticker] = rec["current"]
    return prices


def _build_user_content(state: dict, prices: dict, market: str) -> str:
    navv = pp.nav(state, prices)
    inv = pp.invested_eur(state, prices)
    righe = []
    for t, meta in pp.UNIVERSE.items():
        p = prices.get(t)
        pos = state["positions"].get(t, {"qty": 0})
        val = (pos["qty"] * p) if p and pos["qty"] else 0
        peso = f"{val / navv * 100:5.1f}%" if navv and val else "    -"
        righe.append(f"  {t:9} {meta['kind']:28} prezzo {p if p else 'n/d':>9} "
                     f"posseduto €{val:8.2f} peso {peso}  — {meta['name']}")

    versato = state.get("contributed_eur", 0.0)
    iniziale = state.get("initial_capital_eur", 0.0)
    residuo_tetto = pp.CAPITAL_CEILING_EUR - versato - iniziale

    return f"""STATO DEL PORTAFOGLIO — {datetime.now().strftime('%d/%m/%Y')}

Valore totale: €{navv if navv else 'n/d'}
Investito: €{inv}
Liquidita' disponibile: €{state['cash_eur']:.2f}
Spazio residuo sotto il tetto di €{pp.CAPITAL_CEILING_EUR:.0f}: €{residuo_tetto:.2f}
Ordine minimo: €{pp.MIN_ORDER_EUR:.0f} — commissione €{pp.COMMISSION_EUR}

UNIVERSO INVESTIBILE (solo questi, tutti comprabili su Fineco in euro)
{chr(10).join(righe)}

{market}

Decidi per oggi. Ricorda: HOLD e' una decisione legittima e frequente."""


def ask_decision(state: dict, prices: dict, market: str) -> dict:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return {"action": "HOLD", "rationale": "ANTHROPIC_API_KEY assente", "conviction": 1}
    client = anthropic.Anthropic(api_key=api_key)
    resp = client.messages.create(
        model=MODEL, max_tokens=4000, system=SYSTEM,
        messages=[{"role": "user", "content": _build_user_content(state, prices, market)}],
    )
    raw = next((b.text for b in resp.content if getattr(b, "type", None) == "text"), "").strip()
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip().rstrip("`").strip()
    try:
        d = json.loads(raw)
    except json.JSONDecodeError:
        return {"action": "HOLD", "rationale": f"risposta non parsabile: {raw[:120]}",
                "conviction": 1}
    d["_model"] = MODEL
    return d


def market_summary(portfolio_data: dict, watchlist: list, events: dict) -> str:
    """Contesto di mercato compatto: le stesse letture che vede il briefing."""
    out = ["DATI DI MERCATO DI OGGI"]
    for h in (portfolio_data.get("holdings", []) + list(watchlist or [])):
        if "error" in h or not h.get("ticker"):
            continue
        out.append(f"  {h['ticker']:9} oggi {h.get('daily_change_pct', 0):+6.2f}%  "
                   f"settimana {h.get('weekly_change_pct', 0):+6.2f}%  "
                   f"mese {h.get('monthly_change_pct', 0):+6.2f}%")
    for e in (events or {}).get("earnings", [])[:5]:
        out.append(f"  [earnings] {e.get('description')} ({e.get('date')})")
    for m in (events or {}).get("macro_calendar", [])[:5]:
        out.append(f"  [macro] {m.get('description')}")
    return "\n".join(out)


def daily_run(portfolio_data: dict, watchlist: list, events: dict) -> dict:
    """
    Entrypoint del briefing. Non solleva mai: se qualcosa non va, il paper salta
    la giornata e il briefing prosegue.
    Restituisce un riepilogo NON sensibile (nessun dettaglio della decisione).
    """
    try:
        if not os.environ.get("PAPER_KEY"):
            return {"skipped": "PAPER_KEY non configurata"}

        # L'esperimento comincia il primo di ottobre. Prima di quella data il
        # codice gira a vuoto: i giorni di rodaggio servivano a scoprire i bug,
        # non devono finire nel registro ne' far scattare un versamento in
        # anticipo (il paper riceve 500 EUR al mese, non 500 ogni volta che
        # provo il workflow a fine settembre).
        start = os.environ.get("PAPER_START_DATE", "2026-10-01")
        oggi = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if oggi < start:
            return {"skipped": f"l'esperimento parte il {start}"}

        known = {h["ticker"]: h.get("current")
                 for h in portfolio_data.get("holdings", []) if h.get("ticker")}
        prices = fetch_universe_prices(known)
        if not prices:
            return {"skipped": "nessun prezzo disponibile"}

        state = pp.load_state()
        if state is None:
            cash = float(os.environ.get("PAPER_START_CASH", "173.76"))
            state = pp.init_state(portfolio_data.get("holdings", []), cash,
                                  datetime.now(timezone.utc).strftime("%Y-%m-%d"))
            state["initial_capital_eur"] = pp.invested_eur(state, prices) + cash
            print(f"  → Paper: stato iniziale creato "
                  f"(capitale €{state['initial_capital_eur']:.2f})")

        ok, msg = pp.verify_chain(state)
        if not ok:
            return {"skipped": f"integrita' compromessa: {msg}"}

        versato = pp.apply_monthly_contribution(state, datetime.now(timezone.utc))

        nav_before = pp.nav(state, prices)
        decision = ask_decision(state, prices, market_summary(portfolio_data, watchlist, events))
        executed, detail = pp.execute(state, decision, prices)
        entry = pp.record(state, decision, executed, detail, prices, nav_before)

        state["nav_history"].append({
            "date": entry["date"],
            "nav": pp.nav(state, prices),
            "contribution": versato,
        })
        pp.save_state(state)

        mese = datetime.now(timezone.utc).strftime("%Y-%m")
        ops = sum(1 for d in state["decisions"]
                  if d["date"].startswith(mese) and d["action"] != "HOLD" and d["executed"])
        return {
            "decisioni_totali": len(state["decisions"]),
            "operazioni_questo_mese": ops,
            "versamento_oggi": versato,
            "azione_registrata": True,
        }
    except Exception as e:
        print(f"  [paper] saltato: {type(e).__name__}: {e}")
        return {"skipped": f"{type(e).__name__}"}
