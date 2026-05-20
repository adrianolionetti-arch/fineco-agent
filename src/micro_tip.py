"""
Micro-tip giornaliero: una definizione/concetto breve in 2-3 righe.
Affianca la pillola settimanale (che è approfondita) con uno snack
quotidiano leggero, sostenibile e facile da digerire.

Rotazione deterministica per data: stessa data → stesso tip per
tutti (così se confrontiamo l'email di lunedì tra noi, vediamo lo
stesso contenuto).
"""
from datetime import date


MICRO_TIPS = [
    {
        "termine": "Drawdown",
        "definizione": "La peggiore perdita massima da un picco. Un ETF passato da 100 a 70 ha un drawdown del 30%. Serve per capire 'quanto può andare giù' un asset prima che torni a salire.",
        "categoria": "rischio",
    },
    {
        "termine": "TER (Total Expense Ratio)",
        "definizione": "La commissione annuale di un ETF, in %. VWCE ha TER 0,22% — su €10.000 investiti = €22/anno di costi nascosti. Sotto lo 0,30% è considerato 'economico'.",
        "categoria": "costi",
    },
    {
        "termine": "Volatilità (Standard Deviation)",
        "definizione": "Misura quanto un asset 'balla' nel tempo. Volatilità annua: NVIDIA ~40%, ETF azionari globali ~15%, bond ~5%, cash ~0%. Più volatile = più rendimento atteso, ma anche più stress.",
        "categoria": "rischio",
    },
    {
        "termine": "Beta",
        "definizione": "Quanto un'azione si muove rispetto al mercato. Beta 1,0 = si muove come l'indice; beta 1,5 = amplifica del 50%; beta 0,5 = la metà. NVIDIA ha beta ~1,7 → molto reattiva ai movimenti generali.",
        "categoria": "rischio",
    },
    {
        "termine": "Yield to Maturity (YTM)",
        "definizione": "Il rendimento totale annuo di un'obbligazione se la tieni fino a scadenza. Un BTP 10 anni a 4% YTM ti dà ~4%/anno fino al 2036. Cambia col prezzo: più scende il prezzo, più sale il YTM.",
        "categoria": "bond",
    },
    {
        "termine": "Dividend Yield",
        "definizione": "Dividendo annuale / prezzo. Un'azione a €100 che paga €4/anno = 4% di yield. Attenzione: yield molto alto (>8%) è spesso un segnale di azienda in difficoltà, non un affare.",
        "categoria": "azioni",
    },
    {
        "termine": "P/E ratio (Price/Earnings)",
        "definizione": "Prezzo / utile per azione. NVIDIA ha P/E ~35 = paghi 35€ per ogni 1€ di utile annuo. Sopra 30 = aspettative ottimistiche (e rischio se delude); sotto 15 = potenzialmente 'a sconto'.",
        "categoria": "valutazione",
    },
    {
        "termine": "Interesse composto",
        "definizione": "I guadagni che producono altri guadagni. €1.000 investiti al 7% annuo: in 10 anni diventano €1.967, in 30 anni €7.612, in 50 anni €29.457. È la magia del 'tempo nel mercato', non del 'timing del mercato'.",
        "categoria": "fondamentali",
    },
    {
        "termine": "Asset allocation",
        "definizione": "Come dividi il portafoglio per classe (azioni / bond / oro / cash). Studi accademici dicono che ~90% del risultato a lungo termine dipende da questa scelta, non dai singoli titoli che compri.",
        "categoria": "strategia",
    },
    {
        "termine": "Rebalancing",
        "definizione": "Riportare il portafoglio ai pesi target. Se hai pensato 70% azioni / 30% bond e dopo un rally sei a 80/20, vendi un po' di azioni e compri bond. È disciplina contro l'emotività.",
        "categoria": "strategia",
    },
    {
        "termine": "Sharpe ratio",
        "definizione": "Rendimento aggiustato per il rischio: (rendimento - tasso risk-free) / volatilità. Sharpe > 1 = buono, > 2 = ottimo. Aiuta a confrontare strategie con rendimenti simili ma rischi diversi.",
        "categoria": "rischio",
    },
    {
        "termine": "Correlation",
        "definizione": "Quanto due asset si muovono insieme. -1 = opposti, 0 = indipendenti, +1 = identici. Oro e azioni hanno correlazione vicina a 0 → mescolarli diversifica davvero, mentre due ETF azionari globali hanno correlazione ~0,95 (non diversificano).",
        "categoria": "diversificazione",
    },
    {
        "termine": "KID (Key Information Document)",
        "definizione": "Il documento UE di 3 pagine che spiega un ETF (rischi, costi, scenari). ETF americani (SPY, QQQ, VOO) non hanno KID UCITS → i broker italiani non te li fanno comprare. Per questo usiamo le versioni UCITS equivalenti (SGLD, EIMI, ecc.).",
        "categoria": "normativa",
    },
    {
        "termine": "Costi Fineco",
        "definizione": "~€2,95 per operazione su ETF/azioni italiane. Su un ordine da €100, fai €2,95/€100 = 3% di perdita istantanea. Sotto €150 le commissioni mangiano troppo: aspetta liquidità o accumula con PAC.",
        "categoria": "costi",
    },
    {
        "termine": "ETF accumulazione vs distribuzione",
        "definizione": "ETF 'Acc' reinveste i dividendi dentro (es. EQAC, VWCE), ETF 'Dist' te li paga in conto. Per investimento a lungo termine: Acc è fiscalmente più efficiente in Italia (paghi tassa solo alla vendita).",
        "categoria": "tasse",
    },
    {
        "termine": "Tassa di bollo",
        "definizione": "0,20% annuo sul valore del tuo portafoglio titoli (in Italia). Su €10.000 = €20/anno. Non puoi evitarla, ma sappi che esiste — è un costo silenzioso che ti taglia un po' di rendimento.",
        "categoria": "tasse",
    },
    {
        "termine": "Capital Gain Tax",
        "definizione": "26% sui guadagni dalla vendita di azioni/ETF (in Italia). 12,5% sui bond di Stato (BTP, Bund). Compensare le minusvalenze entro 4 anni può abbassare il conto: tienine traccia.",
        "categoria": "tasse",
    },
    {
        "termine": "Mean reversion",
        "definizione": "L'idea che prezzi estremi tornano alla media nel tempo. Spesso vera in archi lunghi, ma 'i mercati possono restare irrazionali più a lungo di quanto tu possa restare solvente' (Keynes). Non comprare al ribasso senza capire perché sta scendendo.",
        "categoria": "psicologia",
    },
    {
        "termine": "Dollar-cost averaging (DCA / PAC)",
        "definizione": "Comprare la stessa cifra a intervalli regolari (es. €200 ogni mese), invece di tutto in una volta. Smussa il rischio di entrare 'sul picco' e ti toglie lo stress del timing. Pattern classico per chi sta costruendo posizione.",
        "categoria": "strategia",
    },
    {
        "termine": "Bear market vs correzione",
        "definizione": "Correzione = calo del 10-20% dal picco. Bear market = calo oltre il 20%. Storicamente l'S&P500 ha una correzione ogni ~1,5 anni e un bear market ogni ~6 anni. Sono normali, non eccezioni.",
        "categoria": "psicologia",
    },
]


def get_micro_tip_del_giorno(today: date | None = None) -> dict:
    """Tip del giorno con rotazione deterministica sulla data.
    Stessa data → stesso tip (così email/dashboard sono coerenti tra
    invocazioni multiple nello stesso giorno)."""
    today = today or date.today()
    idx = today.toordinal() % len(MICRO_TIPS)
    return {**MICRO_TIPS[idx], "_indice": idx, "_data": today.isoformat()}


if __name__ == "__main__":
    import json
    tip = get_micro_tip_del_giorno()
    print(json.dumps(tip, indent=2, ensure_ascii=False))
