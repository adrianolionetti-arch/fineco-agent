"""
Modulo pillole formative.
Ogni lunedì il sistema seleziona la pillola della settimana corrente
e la include nell'email + nella dashboard.

Le pillole sono "indicizzate per numero di settimana dal lancio".
START_DATE è il primo lunedì in cui parte il sistema.
Settimana 1 = la settimana di START_DATE.
Se oggi è dopo l'ultima pillola disponibile, ripete l'ultima.
"""
from datetime import date

# Data del primo lunedì in cui parte il percorso formativo.
# Cambiala se vuoi spostare l'inizio.
START_DATE = date(2026, 5, 18)  # lunedì 18 maggio 2026

PILLOLE = [
    {
        "numero": 1,
        "titolo": "Hai NVIDIA in 3 posti diversi e non lo sai",
        "sottotitolo": "Cos'è davvero un ETF",
        "corpo": """Ciao Adriano, oggi parliamo di una cosa che ti riguarda direttamente. Hai 3 strumenti nel tuo portafoglio Fineco: NVIDIA, VWCE e EQAC. Ma in realtà tu possiedi NVIDIA <strong>tre volte</strong>. Ti spiego come.

NVIDIA è un'azione singola: 1 quota = un pezzettino dell'azienda NVIDIA. Fin qui chiaro.

<strong>VWCE</strong> è un ETF. ETF in italiano si dice "fondo a gestione passiva" ma chiamarlo così non aiuta. Pensa a un ETF come a una <strong>cassetta di frutta mista del fruttivendolo</strong>: invece di comprare 1 mela, 1 pera, 1 banana presi singolarmente, compri una cassetta in cui c'è già un po' di tutto. VWCE è la "cassetta mista" delle aziende mondiali: dentro ci sono ~3.700 aziende di tutto il mondo, comprese le grandi del tech americano. NVIDIA è dentro per circa il <strong>4%</strong> del peso totale.

<strong>EQAC</strong> è un altro ETF, ma più "stretto": dentro ci sono solo le 100 più grandi del Nasdaq americano. NVIDIA dentro questo pesa <strong>~8-9%</strong>.

<strong>Quindi cosa vuol dire per te?</strong> Quando vedi che NVIDIA è salita del +5% in un giorno, ti senti contento perché la tua quota singola di NVIDIA è salita. Ma in realtà sono salite <em>anche</em> le frazioni di NVIDIA dentro VWCE e EQAC. Una buona giornata di NVIDIA è una <em>tripla</em> buona giornata per te.

Il rovescio della medaglia: se NVIDIA crolla, perdi 3 volte. Il tuo portafoglio è "sbilanciato sul tech USA" non perché hai comprato male, ma perché molti ETF "globali" sono in realtà 60-70% americani: le aziende USA pesano tanto sui mercati mondiali.""",
        "esercizio": """1. Vai su <a href="https://www.justetf.com/it/etf-profile.html?isin=IE00BK5BQT80">justetf - scheda VWCE</a>
2. Scorri fino alla sezione "Top 10 Holdings"
3. Trovi NVIDIA? Che peso ha? Quali altre aziende vedi nelle prime 10?
4. Fai la stessa cosa per EQAC: <a href="https://www.justetf.com/it/etf-profile.html?isin=IE00BFZXGZ54">justetf - scheda EQAC</a>""",
        "riflessione": "Se NVIDIA, Apple e Microsoft messe insieme pesassero il 30% del tuo VWCE, sei davvero \"diversificato a livello mondiale\" come pensavi?",
    },
    {
        "numero": 2,
        "titolo": "Perché un titolo \"balla\" e l'altro no",
        "sottotitolo": "La volatilità: il pallone gonfiato",
        "corpo": """Hai presente quando lanci un pallone gonfio e uno mezzo sgonfio? Il gonfio rimbalza alto, fa rumore, esce dalla portata in fretta. Lo sgonfio rimbalza piano, resta lì. Le azioni funzionano uguale, e questa caratteristica si chiama <strong>volatilità</strong>.

<strong>Volatilità</strong> vuol dire: quanto un prezzo salta su e giù in un periodo di tempo. NVIDIA è un titolo "molto volatile": può fare +10% e -10% nella stessa settimana. VWCE è "poco volatile": si muove di solito tra +0,5% e -0,5% al giorno.

Volatilità alta non vuol dire "cattivo". Vuol dire <strong>stomaco</strong>. Se sei una persona che apre Fineco ogni 10 minuti, un titolo volatile come NVIDIA ti farà soffrire: vedi rossi grossi, ti viene voglia di vendere, fai operazioni di pancia.

Se sei una persona che apre Fineco una volta al mese, NVIDIA volatile ti scivola addosso: oggi -8%, domani +5%, alla fine del mese magari sei a +3% e non hai sofferto niente.

<strong>La volatilità è la tassa che paghi per avere rendimenti più alti</strong>. Le azioni rendono storicamente di più delle obbligazioni proprio perché ti fanno passare brutti momenti. Se vuoi solo cose calme, prendi un conto deposito al 3%: zero stress, ma anche zero crescita reale (l'inflazione si mangia tutto).""",
        "esercizio": """Per 5 giorni di fila (lun-ven), apri <a href="https://www.borsaitaliana.it/borsa/etf/scheda/IE00BK5BQT80-ETFP.html?lang=it">la scheda di VWCE su Borsa Italiana</a> alle 9:30, 13:00 e 18:00. Annotati i 3 prezzi in un foglio.

A fine settimana fai il conto:
<ul>
  <li>Qual è stato il prezzo <strong>più alto</strong> della settimana?</li>
  <li>Qual è stato il prezzo <strong>più basso</strong>?</li>
  <li>Differenza in percentuale? <em>(esempio: max 158, min 155, differenza = 1,9%)</em></li>
</ul>""",
        "riflessione": "L'oscillazione che hai visto su VWCE in 1 settimana, ti ha fatto venire voglia di \"fare qualcosa\"? Se sì, immagina la stessa cosa con NVIDIA, che balla 5-10 volte di più.",
    },
    {
        "numero": 3,
        "titolo": "Quanto ti costa davvero comprare su Fineco",
        "sottotitolo": "Commissioni: il nemico silenzioso",
        "corpo": """Fineco ti fa pagare <strong>€2,95 ogni volta che compri o vendi un'azione o ETF</strong>. Sembra poco, ma non lo è. Ti spiego con un esempio reale del tuo portafoglio.

Quando hai comprato la tua quota di EQAC a €368,36, Fineco si è preso €2,95 di commissione. Vuol dire che il tuo "punto di pareggio" non era €368,36, ma €371,31. Per andare in guadagno, EQAC doveva salire <strong>dello 0,8%</strong> solo per coprire la commissione.

<strong>Adesso il caso che ti riguarda di più</strong>: hai €75 di liquidità su Fineco. Diciamo che domani vorresti aggiungere altri €75 su VWCE.

<ul>
  <li>Investi: €75</li>
  <li>Commissione: €2,95</li>
  <li>Già perso prima di iniziare: <strong>3,9%</strong></li>
</ul>

Per andare in pari, VWCE deve salire del 4%. Storicamente VWCE rende ~8% all'anno, quindi quel 4% di commissione ti mangia <strong>6 mesi di rendimento medio</strong>. Solo per comprare 75 euro.

<strong>Regola pratica</strong>: la commissione dovrebbe essere <strong>massimo l'1%</strong> della cifra che investi. Quindi:
<ul>
  <li>€100 → 2,95% = troppo</li>
  <li>€300 → 0,98% = appena tollerabile</li>
  <li>€500 → 0,59% = ok</li>
  <li>€1000+ → 0,30% o meno = ottimo</li>
</ul>

Per questo il tuo agente Fineco ti ripete sempre che con €100-€200 non conviene fare singole operazioni: aspetta di accumulare almeno €300-500 sul conto, poi compri.""",
        "esercizio": """Calcola, per ogni tua attuale posizione, <strong>quanto la commissione iniziale ha pesato in percentuale</strong>:
<ul>
  <li>NVIDIA: 1 quota a ~€161 → commissione €2,95 → quanto è % di 161?</li>
  <li>VWCE: 10 quote totali, ipotizziamo comprate in 2 tranche da 5 → €2,95 × 2 = €5,90 → su quanto totale?</li>
  <li>EQAC: 1 quota a €368 → €2,95 → quanto è %?</li>
</ul>""",
        "riflessione": "Se Fineco ti facesse pagare €15 invece di €3 a operazione, faresti comunque queste compere? Probabilmente no. Quindi la prossima volta che ti viene voglia di comprare \"una piccola cosa\", ricorda: la commissione fissa è il tuo vero nemico.",
    },
    {
        "numero": 4,
        "titolo": "Aspettare il momento giusto è una pessima idea",
        "sottotitolo": "PAC vs Timing: chi vince davvero",
        "corpo": """C'è una domanda che fanno tutti i principianti: <em>"meglio aspettare che il mercato scenda e comprare a poco, o iniziare subito?"</em>. La risposta scientifica esiste. Ti spiego senza usare termini complicati.

<strong>Strategia 1 — Il timing</strong> ("aspetto il momento giusto"): aspetti che il mercato crolli, poi compri tanto in un colpo solo.

<strong>Strategia 2 — Il PAC</strong> (Piano di Accumulo Capitale): ogni mese compri sempre la stessa cifra, indipendentemente dal prezzo. Se il mercato è alto compri poco. Se è basso compri tanto. Senza pensarci.

Ti dico chi vince: <strong>il PAC vince nell'85% dei casi su periodi lunghi</strong>. Non lo dico io, lo dicono studi accademici fatti su 30+ anni di mercati USA, Europa, Asia.

Perché?
<ol>
  <li><strong>Nessuno sa quando il mercato è "basso"</strong>. Quello che oggi sembra basso domani può essere il nuovo "massimo" prima di un altro crollo. O viceversa: quello che ti sembra "alto e da non comprare" può essere solo l'inizio di una salita di 10 anni.</li>
  <li><strong>Il PAC ti toglie le emozioni</strong>. Compri a prescindere. Non leggi le news, non guardi il grafico. Bonifico automatico, fine.</li>
</ol>

<strong>Esempio numerico</strong> (da gennaio 2020 a oggi, su VWCE):
<ul>
  <li>Timing perfetto ("dio del mercato"): aspetti il minimo COVID di marzo 2020 e investi €12.000 lì → oggi avresti ~€26.000.</li>
  <li>PAC stupido (€100/mese da gennaio 2020, totale €6.500 investito): oggi avresti ~€10.500.</li>
  <li>"Tutto subito gennaio 2020" (€6.500 a gennaio): oggi avresti ~€12.800.</li>
</ul>

Il timing perfetto vince <em>se sei un dio</em>. Ma nella realtà nessuno azzecca il minimo. Il "tutto subito da subito" batte spesso il PAC, ma richiede di avere già i soldi pronti. <strong>Il PAC batte chiunque aspetti "il momento giusto" senza investire</strong>, che è quello che la maggior parte delle persone finisce per fare.""",
        "esercizio": """Vai su <a href="https://www.justetf.com/it/etf-profile.html?isin=IE00BK5BQT80">la scheda di VWCE su justetf</a> e cerca la sezione "Calcolatore di Investimento" o "Simulatore PAC".

Confronta:
<ul>
  <li>PAC: €100 al mese su VWCE dal 1° gennaio 2020 a oggi</li>
  <li>Lump sum: €6.000 il 1° gennaio 2020 in unica soluzione</li>
</ul>

Quale ha funzionato meglio? Di quanto? <strong>Annota la cifra</strong>, ti servirà più avanti.""",
        "riflessione": "Il tuo portafoglio attuale è stato costruito \"a botte\" senza un PAC. Tra 6 mesi vorresti aver attivato un PAC mensile automatico da €50-100? Pensaci, ne riparliamo a giugno.",
    },
]


def get_pillola_della_settimana(today: date | None = None) -> dict | None:
    """
    Ritorna la pillola della settimana corrente.
    - Se oggi NON è lunedì, ritorna None (le pillole arrivano solo il lunedì).
    - Se oggi è prima di START_DATE, ritorna None.
    - Se oggi è dopo l'ultima pillola disponibile, ripete l'ultima (per non lasciare la dashboard vuota).
    """
    if today is None:
        today = date.today()

    # Le pillole escono solo il lunedì
    if today.weekday() != 0:  # 0 = lunedì
        return None

    # Prima di iniziare il percorso
    if today < START_DATE:
        return None

    delta_days = (today - START_DATE).days
    settimana = (delta_days // 7) + 1  # settimana 1, 2, 3, ...

    # Trova la pillola corrispondente, altrimenti ripete l'ultima
    pillola = next((p for p in PILLOLE if p["numero"] == settimana), None)
    if pillola is None:
        pillola = PILLOLE[-1]  # ripete l'ultima disponibile

    return {**pillola, "settimana_corrente": settimana}


def get_pillola_corrente_o_ultima_passata(today: date | None = None) -> dict | None:
    """
    Per la dashboard: ritorna SEMPRE la pillola più recente disponibile,
    indipendentemente dal giorno della settimana. Così la tab "Allenamento"
    mostra sempre qualcosa (a partire da START_DATE).
    """
    if today is None:
        today = date.today()

    if today < START_DATE:
        return None

    delta_days = (today - START_DATE).days
    settimana = (delta_days // 7) + 1

    pillola = next((p for p in PILLOLE if p["numero"] == settimana), None)
    if pillola is None:
        pillola = PILLOLE[-1]

    return {**pillola, "settimana_corrente": settimana}


def get_archivio_pillole(today: date | None = None) -> list:
    """
    Ritorna la lista delle pillole già "uscite" finora, in ordine inverso
    (la più recente in cima). Usato per popolare l'archivio nella dashboard.
    """
    if today is None:
        today = date.today()

    if today < START_DATE:
        return []

    delta_days = (today - START_DATE).days
    settimana_attuale = (delta_days // 7) + 1

    uscite = [p for p in PILLOLE if p["numero"] <= settimana_attuale]
    return list(reversed(uscite))


if __name__ == "__main__":
    # test locale
    import json
    p = get_pillola_della_settimana()
    print("Pillola di oggi:", json.dumps(p, indent=2, ensure_ascii=False) if p else "Nessuna (non è lunedì o prima del lancio)")
    print()
    print(f"Archivio: {len(get_archivio_pillole())} pillole uscite")
