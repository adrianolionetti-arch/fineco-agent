"""Test del gate sui segnali. Lanciare con: python tests/test_signal_gate.py"""
import sys, csv, os
from datetime import datetime, timedelta
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
import signal_gate as sg

import tempfile
TMP = os.path.join(tempfile.gettempdir(), 'fineco_test_journal.csv')
def journal(entries):
    with open(TMP,'w',newline='') as f:
        w=csv.writer(f); w.writerow(['date','signal_level','asset_ticker','asset_price_at_signal'])
        for d,t,p in entries: w.writerow([d,'YELLOW',t,p])

def hold(t,d,w,m,cur=100.0):
    return {'ticker':t,'current':cur,'daily_change_pct':d,'weekly_change_pct':w,'monthly_change_pct':m}

def run(level, holdings, entries=(), ticker='AGGH.MI'):
    journal(list(entries))
    b={'signal_level':level,'signal_asset':ticker,'signal_importance':3,
       'signal_action':'x','signal_what_to_do':'y'}
    sg.apply_gate(b, holdings, events={}, journal_path=TMP)
    return b

ieri=(datetime.now()-timedelta(days=2)).strftime('%Y-%m-%d')
vecchio=(datetime.now()-timedelta(days=40)).strftime('%Y-%m-%d')
ok=0; ko=0
def check(name, got, want):
    global ok,ko
    if got==want: ok+=1; print(f"  PASS  {name}")
    else: ko+=1; print(f"  FAIL  {name}: atteso {want}, ottenuto {got}")

print("ANTI-RIPETIZIONE")
b=run('YELLOW',[hold('AGGH.MI',0.3,-0.4,-1.1,cur=4.85)],[(ieri,'AGGH.MI','4.84')])
check("stesso ticker 2gg fa, prezzo fermo -> NONE", b['signal_level'],'NONE')
print(f"        motivo: {b['_gate']['notes'][0]}")

b=run('YELLOW',[hold('AGGH.MI',0.3,-0.4,-6.0,cur=5.20)],[(ieri,'AGGH.MI','4.84')])
check("stesso ticker 2gg fa ma prezzo +7% -> passa", b['signal_level'],'YELLOW')

b=run('YELLOW',[hold('AGGH.MI',0.3,-0.4,-6.0,cur=4.85)],[(vecchio,'AGGH.MI','4.84')])
check("stesso ticker 40gg fa, cooldown scaduto -> passa", b['signal_level'],'YELLOW')

print("\nSOGLIE")
check("YELLOW senza movimento -> NONE", run('YELLOW',[hold('AGGH.MI',0.3,-0.4,-1.1)])['signal_level'],'NONE')
check("YELLOW con mese -6% -> resta YELLOW", run('YELLOW',[hold('AGGH.MI',0.3,-0.4,-6.0)])['signal_level'],'YELLOW')
check("GREEN debole -> declassato a YELLOW", run('GREEN',[hold('AGGH.MI',0.3,-4.0,-6.0)])['signal_level'],'YELLOW')
check("GREEN forte (-9% sett) -> resta GREEN", run('GREEN',[hold('AGGH.MI',-1.0,-9.0,-6.0)])['signal_level'],'GREEN')
check("asset sconosciuto -> NONE", run('YELLOW',[hold('ALTRO',9,9,9)])['signal_level'],'NONE')
check("NONE non viene mai promosso", run('NONE',[hold('AGGH.MI',9,9,9)])['signal_level'],'NONE')

print("\nIMPORTANZA (era costante: 2/5, poi 3/5)")
vals=[]
for d,w,m in [(0.3,-0.5,-1.0),(2.1,-3.2,-5.0),(-3.0,-6.0,-9.0),(-6.0,-12.0,-18.0),(-9.0,-20.0,-30.0)]:
    v=sg.compute_importance(d,w,m,False); vals.append(v); print(f"  giorno {d:+5.1f}% sett {w:+6.1f}% mese {m:+6.1f}% -> {v}/5")
check("l'importanza varia e copre la scala", len(set(vals))>=4, True)
check("catalizzatore alza di 1", sg.compute_importance(-3.0,-6.0,-9.0,True), sg.compute_importance(-3.0,-6.0,-9.0,False)+1)

print(f"\n{ok} pass, {ko} fail")
sys.exit(1 if ko else 0)
