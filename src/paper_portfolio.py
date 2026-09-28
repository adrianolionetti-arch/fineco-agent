"""
Portafoglio parallelo "paper": le decisioni che l'agente avrebbe preso davvero.

PERCHE' ESISTE
--------------
Il briefing produceva consigli lunghi che finivano quasi sempre in "valuta",
"monitora", "aspetta il dato di domani". Parole, nessuna decisione. Un consiglio
che non si puo' sbagliare non si puo' nemmeno valutare.

Qui l'agente e' costretto ogni giorno a una scelta netta - COMPRA tot, VENDI tot,
oppure NON FARE NULLA - su un portafoglio parallelo che parte da quello reale di
Adriano. La decisione viene scritta il giorno stesso, con i soli dati di quel
giorno, e non e' piu' modificabile. A fine mese si confronta.

LE REGOLE CHE LO TENGONO ONESTO
-------------------------------
1. Le decisioni sono CIFRATE. Adriano non le vede durante il mese, altrimenti
   agirebbe di conseguenza e a fine mese confronteremmo una strategia con se
   stessa invece che due strategie diverse.
2. Sono append-only e firmate con un hash che include la decisione precedente:
   riscrivere il passato spezza la catena e si vede.
3. Commissioni reali di Fineco (2.95 EUR) su ogni operazione. Una decisione che
   guadagna meno di quanto costa eseguirla e' una decisione sbagliata.
4. Universo limitato a strumenti realmente comprabili su Fineco in euro: niente
   proxy americani che Adriano non potrebbe acquistare.
5. Il confronto finale usa il rendimento TIME-WEIGHTED, che neutralizza i
   versamenti: chi mette piu' soldi non deve risultare piu' bravo per questo.

COSA PUO' E NON PUO' DIMOSTRARE
-------------------------------
Un mese e' troppo poco per dire se l'agente "batte il mercato": con ~22 giorni e
poche operazioni il risultato e' in larga parte rumore. Quello che misura davvero
e' il processo: quante decisioni nette produce, se sono eseguibili col capitale
disponibile, quanto spesso sa dire "non fare niente".
"""
import base64
import hashlib
import json
import os
from datetime import datetime, timezone

STATE_PATH = "data/paper_portfolio.enc"
COMMISSION_EUR = 2.95
MONTHLY_CONTRIBUTION_EUR = 500.0
CAPITAL_CEILING_EUR = 15000.0
# Sotto questa soglia la commissione pesa piu' dell'1.5% e l'operazione non ha senso
MIN_ORDER_EUR = 200.0

# Universo investibile: solo UCITS in euro acquistabili su Fineco.
# I proxy USA usati dal briefing (GLD, EEM, XLV...) NON entrano qui: servono a
# leggere il mercato, non sono strumenti che Adriano possa comprare.
UNIVERSE = {
    "VWCE.MI":  {"name": "Vanguard FTSE All-World",            "kind": "azionario globale"},
    "EQAC.MI":  {"name": "Invesco EQQQ Nasdaq-100",            "kind": "azionario tech USA"},
    "AGGH.MI":  {"name": "iShares Core Global Aggregate Bond", "kind": "obbligazionario globale"},
    "1NVDA.MI": {"name": "NVIDIA",                             "kind": "azione singola"},
    "SGLD.MI":  {"name": "Invesco Physical Gold",              "kind": "oro"},
    "EIMI.MI":  {"name": "iShares Core MSCI EM IMI",           "kind": "azionario emergenti"},
    "IBGL.MI":  {"name": "iShares Euro Govt Bond 15-30y",      "kind": "obbligazionario govt euro"},
    "IBTM.MI":  {"name": "iShares USD Treasury 7-10y",         "kind": "obbligazionario govt USA"},
    "XDWH.MI":  {"name": "Xtrackers MSCI World Health Care",   "kind": "azionario settoriale"},
}


# --- Cifratura -----------------------------------------------------------
# Lo stato sta in un repo che Adriano puo' leggere. Cifrarlo serve a proteggere
# l'esperimento da lui stesso: non e' una cassaforte (la chiave e' un secret del
# suo repo), e' un impedimento allo sguardo casuale su un commit.

def _fernet():
    from cryptography.fernet import Fernet
    secret = os.environ.get("PAPER_KEY")
    if not secret:
        raise RuntimeError("PAPER_KEY non configurata")
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
    return Fernet(key)


def load_state(path: str = STATE_PATH) -> dict | None:
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return json.loads(_fernet().decrypt(f.read()).decode())


def save_state(state: dict, path: str = STATE_PATH) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    blob = _fernet().encrypt(json.dumps(state, ensure_ascii=False).encode())
    with open(path, "wb") as f:
        f.write(blob)


# --- Catena di firme -----------------------------------------------------

def _chain_hash(prev_hash: str, decision: dict) -> str:
    """Ogni decisione include l'hash della precedente: la storia non si riscrive."""
    payload = json.dumps(
        {k: decision[k] for k in sorted(decision) if k != "hash"},
        sort_keys=True, ensure_ascii=False,
    )
    return hashlib.sha256((prev_hash + payload).encode()).hexdigest()


def verify_chain(state: dict) -> tuple[bool, str]:
    prev = "genesis"
    for i, d in enumerate(state.get("decisions", [])):
        expected = _chain_hash(prev, d)
        if d.get("hash") != expected:
            return False, f"catena rotta alla decisione {i} del {d.get('date')}"
        prev = d["hash"]
    return True, f"catena integra ({len(state.get('decisions', []))} decisioni)"


# --- Inizializzazione ----------------------------------------------------

def init_state(holdings: list, cash_eur: float, start_date: str) -> dict:
    """Fotografa il portafoglio reale di Adriano come punto di partenza."""
    positions = {}
    for h in holdings:
        t = h.get("ticker")
        if t in UNIVERSE and h.get("quantity"):
            positions[t] = {"qty": float(h["quantity"]), "avg_cost": float(h.get("current", 0))}
    return {
        "started_at": start_date,
        "config": {
            "monthly_contribution_eur": MONTHLY_CONTRIBUTION_EUR,
            "commission_eur": COMMISSION_EUR,
            "ceiling_eur": CAPITAL_CEILING_EUR,
            "min_order_eur": MIN_ORDER_EUR,
        },
        "cash_eur": float(cash_eur),
        "contributed_eur": 0.0,      # versamenti virtuali cumulati
        "positions": positions,
        "decisions": [],
        "nav_history": [],
    }


# --- Valorizzazione ------------------------------------------------------

def nav(state: dict, prices: dict) -> float | None:
    """Valore totale del paper. None se manca anche un solo prezzo."""
    total = state.get("cash_eur", 0.0)
    for t, p in state.get("positions", {}).items():
        if p["qty"] <= 0:
            continue
        if t not in prices or prices[t] is None:
            return None
        total += p["qty"] * prices[t]
    return round(total, 2)


def invested_eur(state: dict, prices: dict) -> float:
    return round(sum(p["qty"] * prices.get(t, 0) for t, p in state.get("positions", {}).items()), 2)


# --- Esecuzione ordini ---------------------------------------------------

def execute(state: dict, decision: dict, prices: dict) -> tuple[bool, str]:
    """
    Valida ed esegue. La validazione sta QUI e non nel prompt: un modello che si
    auto-certifica i fondi disponibili e' esattamente l'errore che questo
    progetto ha gia' fatto una volta col livello dei segnali.
    """
    action = (decision.get("action") or "HOLD").upper()
    if action == "HOLD":
        return True, "nessuna operazione"

    ticker = decision.get("ticker")
    amount = float(decision.get("amount_eur") or 0)

    if ticker not in UNIVERSE:
        return False, f"{ticker} non e' nell'universo investibile"
    price = prices.get(ticker)
    if not price:
        return False, f"prezzo di {ticker} non disponibile oggi"
    pos = state["positions"].setdefault(ticker, {"qty": 0.0, "avg_cost": 0.0})

    # La soglia minima serve a non sprecare commissioni su ordini troppo piccoli,
    # ma non deve trasformarsi in una trappola: se una posizione vale meno del
    # minimo, va comunque potuta liquidare per intero. Altrimenti da una piccola
    # posizione non si esce piu'.
    valore_posizione = pos["qty"] * price
    liquidazione = (action == "SELL" and valore_posizione > 0
                    and amount >= valore_posizione * 0.95)
    if amount < MIN_ORDER_EUR and not liquidazione:
        return False, (f"ordine da {amount:.2f} EUR sotto il minimo di {MIN_ORDER_EUR:.0f}: "
                       f"la commissione peserebbe il {COMMISSION_EUR/max(amount,1)*100:.1f}%")

    if action == "BUY":
        costo = amount + COMMISSION_EUR
        if costo > state["cash_eur"]:
            return False, (f"liquidita' insufficiente: servono {costo:.2f} EUR, "
                           f"disponibili {state['cash_eur']:.2f}")
        qty = amount / price
        nuovo_qty = pos["qty"] + qty
        pos["avg_cost"] = ((pos["avg_cost"] * pos["qty"]) + amount) / nuovo_qty if nuovo_qty else price
        pos["qty"] = nuovo_qty
        state["cash_eur"] = round(state["cash_eur"] - costo, 2)
        return True, f"comprati {qty:.4f} di {ticker} a {price:.2f} per {amount:.2f} EUR (+{COMMISSION_EUR} comm.)"

    if action == "SELL":
        valore_pos = valore_posizione
        if valore_pos <= 0:
            return False, f"nessuna posizione su {ticker} da vendere"
        amount = min(amount, valore_pos)
        qty = amount / price
        pos["qty"] = max(0.0, pos["qty"] - qty)
        state["cash_eur"] = round(state["cash_eur"] + amount - COMMISSION_EUR, 2)
        return True, f"venduti {qty:.4f} di {ticker} a {price:.2f} per {amount:.2f} EUR (-{COMMISSION_EUR} comm.)"

    return False, f"azione '{action}' non riconosciuta"


def record(state: dict, decision: dict, executed: bool, detail: str,
           prices: dict, nav_before: float | None) -> dict:
    """Scrive la decisione nel registro, firmata. Append-only."""
    prev = state["decisions"][-1]["hash"] if state["decisions"] else "genesis"
    entry = {
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": (decision.get("action") or "HOLD").upper(),
        "ticker": decision.get("ticker"),
        "amount_eur": decision.get("amount_eur"),
        "conviction": decision.get("conviction"),
        "rationale": (decision.get("rationale") or "")[:400],
        "executed": executed,
        "detail": detail,
        "nav_before": nav_before,
        "prices_seen": {t: prices.get(t) for t in sorted(UNIVERSE) if prices.get(t)},
    }
    entry["hash"] = _chain_hash(prev, entry)
    state["decisions"].append(entry)
    return entry


def apply_monthly_contribution(state: dict, today: datetime) -> float:
    """
    Versa la rata all'inizio di ogni mese, senza superare il tetto complessivo.
    Restituisce quanto e' stato versato (0 se non e' il momento o se il tetto e' pieno).
    """
    marker = today.strftime("%Y-%m")
    if state.get("last_contribution_month") == marker:
        return 0.0
    residuo = CAPITAL_CEILING_EUR - state.get("contributed_eur", 0.0) - state.get("initial_capital_eur", 0.0)
    versamento = round(max(0.0, min(MONTHLY_CONTRIBUTION_EUR, residuo)), 2)
    state["cash_eur"] = round(state.get("cash_eur", 0.0) + versamento, 2)
    state["contributed_eur"] = round(state.get("contributed_eur", 0.0) + versamento, 2)
    state["last_contribution_month"] = marker
    return versamento
