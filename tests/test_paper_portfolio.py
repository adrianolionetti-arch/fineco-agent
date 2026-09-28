"""Test del portafoglio paper. Lanciare con: python tests/test_paper_portfolio.py"""
import os, sys, tempfile
from datetime import datetime, timezone
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
os.environ.setdefault('PAPER_KEY', 'chiave-di-test')
import paper_portfolio as pp

ok = ko = 0
def check(nome, got, want):
    global ok, ko
    if got == want: ok += 1; print(f"  PASS  {nome}")
    else: ko += 1; print(f"  FAIL  {nome}: atteso {want!r}, ottenuto {got!r}")

PRICES = {"VWCE.MI":170.15,"EQAC.MI":455.34,"AGGH.MI":4.855,"1NVDA.MI":197.68,
          "SGLD.MI":348.66,"EIMI.MI":48.13,"IBGL.MI":149.13,"IBTM.MI":143.80,"XDWH.MI":54.90}
HOLD = [{"ticker":"VWCE.MI","quantity":16,"current":170.15},
        {"ticker":"EQAC.MI","quantity":2,"current":455.34},
        {"ticker":"AGGH.MI","quantity":54,"current":4.855},
        {"ticker":"1NVDA.MI","quantity":1,"current":197.68}]

def fresh():
    s = pp.init_state(HOLD, 173.76, "2026-10-01")
    s["initial_capital_eur"] = pp.invested_eur(s, PRICES) + 173.76
    return s

print("STATO INIZIALE")
s = fresh()
check("riprende le 4 posizioni reali", len(s["positions"]), 4)
check("NAV = portafoglio reale + liquidita'", pp.nav(s, PRICES), round(4092.93+173.76, 2))

print("\nVALIDAZIONE ORDINI")
s = fresh()
check("ordine sotto il minimo rifiutato", pp.execute(s, {"action":"BUY","ticker":"SGLD.MI","amount_eur":150}, PRICES)[0], False)
check("liquidita' insufficiente rifiutata", pp.execute(s, {"action":"BUY","ticker":"SGLD.MI","amount_eur":900}, PRICES)[0], False)
check("ticker fuori universo rifiutato", pp.execute(s, {"action":"BUY","ticker":"GLD","amount_eur":300}, PRICES)[0], False)
check("prezzo mancante rifiutato", pp.execute(s, {"action":"BUY","ticker":"SGLD.MI","amount_eur":300}, {})[0], False)
check("HOLD sempre valido", pp.execute(s, {"action":"HOLD"}, PRICES)[0], True)
check("nessuna operazione ha toccato la cassa", s["cash_eur"], 173.76)

print("\nACQUISTO E COMMISSIONI")
s = fresh(); s["cash_eur"] = 700.0
okx, det = pp.execute(s, {"action":"BUY","ticker":"EIMI.MI","amount_eur":500}, PRICES)
check("acquisto eseguito", okx, True)
check("cassa = 700 - 500 - 2.95", s["cash_eur"], 197.05)
check("quantita' corretta", round(s["positions"]["EIMI.MI"]["qty"], 4), round(500/48.13, 4))
check("NAV invariato a meno della commissione", round(pp.nav(s, PRICES), 2), round(4092.93+700-2.95, 2))

print("\nVENDITA")
s = fresh()
okx, det = pp.execute(s, {"action":"SELL","ticker":"AGGH.MI","amount_eur":262.17}, PRICES)
check("vendita eseguita", okx, True)
check("cassa aumentata al netto della commissione", s["cash_eur"], round(173.76+262.17-2.95, 2))
check("posizione azzerata", round(s["positions"]["AGGH.MI"]["qty"], 6), 0.0)
check("vendere piu' del posseduto viene limitato", pp.execute(fresh(), {"action":"SELL","ticker":"1NVDA.MI","amount_eur":99999}, PRICES)[0], True)
s2 = fresh()
check("si puo' liquidare una posizione sotto il minimo (197 < 200)", pp.execute(s2, {"action":"SELL","ticker":"1NVDA.MI","amount_eur":197.68}, PRICES)[0], True)
check("ma una vendita PARZIALE sotto il minimo resta rifiutata", pp.execute(fresh(), {"action":"SELL","ticker":"VWCE.MI","amount_eur":80}, PRICES)[0], False)
check("vendere cio' che non si ha e' rifiutato", pp.execute(fresh(), {"action":"SELL","ticker":"SGLD.MI","amount_eur":300}, PRICES)[0], False)

print("\nCATENA DI FIRME (immutabilita')")
s = fresh()
for i, d in enumerate([{"action":"HOLD","rationale":"niente"},
                       {"action":"BUY","ticker":"SGLD.MI","amount_eur":0},
                       {"action":"HOLD","rationale":"ancora niente"}]):
    pp.record(s, d, True, "test", PRICES, 100.0 + i)
check("catena integra", pp.verify_chain(s)[0], True)
s["decisions"][1]["rationale"] = "motivazione riscritta a posteriori"
check("manomissione rilevata", pp.verify_chain(s)[0], False)
print(f"        {pp.verify_chain(s)[1]}")

print("\nVERSAMENTO MENSILE E TETTO")
s = fresh()
v1 = pp.apply_monthly_contribution(s, datetime(2026,10,1,tzinfo=timezone.utc))
v2 = pp.apply_monthly_contribution(s, datetime(2026,10,15,tzinfo=timezone.utc))
v3 = pp.apply_monthly_contribution(s, datetime(2026,11,2,tzinfo=timezone.utc))
check("versa 500 il primo del mese", v1, 500.0)
check("non versa due volte nello stesso mese", v2, 0.0)
check("versa di nuovo il mese dopo", v3, 500.0)
s["contributed_eur"] = 15000 - s["initial_capital_eur"] - 100   # quasi al tetto
s["last_contribution_month"] = "2026-11"
check("il tetto di 15k tronca il versamento", pp.apply_monthly_contribution(s, datetime(2026,12,1,tzinfo=timezone.utc)), 100.0)

print("\nCIFRATURA")
path = os.path.join(tempfile.gettempdir(), 'paper_test.enc')
s = fresh(); pp.record(s, {"action":"BUY","ticker":"SGLD.MI","amount_eur":300}, True, "x", PRICES, 1.0)
pp.save_state(s, path)
blob = open(path,'rb').read()
check("il file su disco non e' leggibile in chiaro", b'SGLD' in blob or b'BUY' in blob, False)
check("rilettura fedele", pp.load_state(path)["decisions"][0]["ticker"], "SGLD.MI")
os.environ['PAPER_KEY'] = 'chiave-sbagliata'
try:
    pp.load_state(path); check("chiave sbagliata rifiutata", True, False)
except Exception: check("chiave sbagliata rifiutata", True, True)
os.environ['PAPER_KEY'] = 'chiave-di-test'
os.remove(path)

print(f"\n{ok} pass, {ko} fail")
sys.exit(1 if ko else 0)
