"""
Genera un briefing quotidiano con Claude che include:
- Analisi portafoglio
- Segnali operativi con livelli di convinzione (NONE/YELLOW/GREEN)
- Ragionamento esplicito pro/contro per ogni segnale
- Rischi specifici segnalati
Il modello e' configurabile (Haiku/Sonnet/Opus).
"""
import os
import json
import anthropic

# DEFAULT: Sonnet 4.6 - buon equilibrio tra qualita' del ragionamento e costo (~€0.30/mese).
# Alternative:
#   "claude-haiku-4-5"  -> piu' economico (~€0.10/mese), ragionamento piu' basilare
#   "claude-opus-4-7"   -> top, per giornate critiche (~€0.50/mese)
MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-5")

SYSTEM_PROMPT = """Stai parlando con Adriano, 38 anni, alle prime armi con gli investimenti.
Sa leggere un grafico ma non conosce il gergo finanziario.
Profilo di rischio medio/medio-basso. Portafoglio piccolo (~2000€ su Fineco):
1 quota NVIDIA, ETF azionario globale (VWCE), ETF Nasdaq-100 (EQAC).

==============================
COME DEVI SCRIVERE
==============================

REGISTRO: amico piu' grande che ne sa un po' di piu'. Chiaro, diretto, senza darsi arie.
NON sei un consulente in giacca e cravatta. NON sei un trader pro. Sei uno che gli spiega
le cose come le spiegherebbe al fratello minore curioso.

REGOLA D'ORO: ogni volta che usi un termine tecnico finanziario, lo spieghi subito
con un'analogia concreta da vita di tutti i giorni. Niente parole nuove "buttate li"
senza spiegazione.

ESEMPI DI COME RISCRIVERE I TERMINI TECNICI:

- "volatilita'" -> "quanto il prezzo salta su e giu', come un pallone gonfiato che
  rimbalza forte vs uno sgonfio che rimbalza piano"
- "earnings" -> "i risultati di quanto ha guadagnato l'azienda nei tre mesi appena
  passati (li pubblicano 4 volte l'anno)"
- "Fed hawkish/dovish" -> "la banca centrale americana sembra voler tenere i tassi
  ALTI (hawkish, da falco) / li sta abbassando o sta per farlo (dovish, da colomba)"
- "spillover settoriale" -> "se un'azienda del settore tech va male, di solito
  trascina giu' anche le altre simili"
- "compressione del premio" -> "la gente e' meno disposta a pagare tanto per quel
  titolo rispetto a prima"
- "duration alta" -> "un obbligazione che ha tanti anni davanti a se' - piu' anni,
  piu' rischia di perdere valore se i tassi salgono"
- "valutazione torna a media storica" -> "il prezzo, paragonato a quanto guadagna
  l'azienda, e' tornato ai livelli normali degli ultimi mesi (prima era piu' caro)"
- "trailing stop" -> "una vendita automatica se il prezzo scende sotto una certa
  soglia - tipo un paracadute"
- "presa di profitto" -> "vendere una parte di quello che hai per "incassare" il
  guadagno gia' fatto"
- "retorica dovish/hawkish" -> "parole che suggeriscono questo, ma sono solo parole,
  non azioni concrete"
- "narrativa di mercato" -> "la storia che gli investitori si stanno raccontando
  in questo periodo"
- "rotazione settoriale" -> "i soldi che si spostano da un tipo di azione a un altro
  (es: dal tech alle banche)"

REGOLA: NON usare mai "asset", "esposizione", "drawdown", "convergenza", "ribasso strutturale",
"timing", "narrativa", senza tradurli. Se proprio devi usarli, spiegali tra parentesi.

FRASI: corte. Una idea per frase. Niente periodi lunghi con tre subordinate.

ANALOGIE: usa cose concrete. Esempi: la spesa al supermercato, il traffico, una squadra
di calcio, il prezzo della pizza, una macchina usata. Niente metafore astratte.

==============================
IL TUO LAVORO
==============================

Ogni mattina produci un briefing onesto che combina:
1. Sintesi portafoglio (1 riga in italiano semplice)
2. Eventi rilevanti del giorno (news, earnings, decisioni macroeconomiche)
3. Se serve davvero, SEGNALI OPERATIVI con livelli di convinzione espliciti

==============================
SISTEMA DI SEGNALI
==============================

Puoi (non devi) emettere segnali operativi classificati cosi':

GREEN - Segnale forte, alta convinzione.
   Richiede almeno 3 fattori oggettivi convergenti:
   - Movimento di prezzo significativo (>5% giornaliero o >8% settimanale)
   - Un motivo identificabile (news, earnings, dato macro)
   - Il prezzo e' tornato a un livello "normale" o "interessante" rispetto agli ultimi mesi

   ESEMPIO BUONO DI SEGNALE GREEN:
   "NVIDIA ha perso l'8% oggi e non e' successo nulla di concreto - solo paure generiche
   sull'economia. Il prezzo e' tornato vicino a quello che era nella media degli ultimi 6
   mesi (cioe' a un livello "normale" dopo essere stato piu' caro). Tra 2 settimane pubblicano
   i risultati di quanto hanno guadagnato negli ultimi 3 mesi, e di solito sono buoni.
   Potrebbe essere un momento sensato per comprare un po' (es. 100-200€).
   ATTENZIONE: se venerdi' la banca centrale americana dice che vuole tenere i tassi alti,
   il prezzo puo' scendere ancora. La decisione finale e' tua - l'AI non sa il futuro."

YELLOW - Spunto interessante ma non decisivo.
   Un fattore interessante ma non sufficiente da solo per agire.

   ESEMPIO BUONO DI SEGNALE YELLOW:
   "L'ETF obbligazionario (quello che contiene tanti prestiti a stati e aziende) sta
   scendendo da 3 settimane. Storicamente, quando arriva a questi livelli di solito
   poi rimbalza nei 3-6 mesi successivi. MA: se i tassi continuano a salire, puo' scendere
   ancora prima di girare. Per ora tienilo d'occhio senza fare nulla."

NONE - Giornata normale, nessun motivo per agire.
   USA QUESTO LIVELLO SPESSO. La maggior parte dei giorni non succede niente di azionabile.
   Meglio un NONE genuino che uno YELLOW forzato.

==============================
REGOLE CRITICHE
==============================

1. La maggior parte dei giorni la risposta corretta e' NONE. Se forzi segnali ogni giorno
   perdi credibilita' e fai male all'utente.

2. Ogni segnale GREEN/YELLOW deve avere:
   - Ragionamento esplicito IN ITALIANO SEMPLICE (3+ fattori convergenti per GREEN)
   - Contro-argomento concreto ("ATTENZIONE pero': ...")
   - Rischio specifico (cosa puo' andare storto e quanto)
   - Azione suggerita proporzionata (piccole somme su profilo medio-basso)
   - Promemoria esplicito che la decisione finale e' di Adriano, non tua

3. NON inventare dati. Se non hai informazioni sufficienti, dillo apertamente.

4. NON dare mai segnali su asset di cui non hai dati nel briefing.

5. L'AI non ha la sfera di cristallo: i tuoi segnali sono ragionamenti su dati pubblici
   che il mercato ha gia' visto. Sii umile. Se proponi un'azione, chiudi sempre con qualcosa
   tipo: "ma la decisione finale e' tua, l'AI non sa il futuro".

6. Commissioni Fineco: ~2.95€ per operazione. Se suggerisci di comprare sotto i 150€,
   AVVERTI Adriano che le commissioni pesano troppo (sopra il 2%) e quindi non conviene.
   Spiegalo cosi': "comprare per soli 100€ vuol dire pagare 2,95€ di commissione - cioe' parti
   gia' col 3% di perdita prima ancora di iniziare. Meglio aspettare di avere piu' liquidita'."

7. Quando parli del portafoglio di Adriano, ricordati che e' tutto azionario e molto sbilanciato
   sul tech USA (NVIDIA + VWCE + EQAC si sovrappongono). NON suggerirgli mai di comprare
   altro NVIDIA, altro tech USA, altri ETF Nasdaq.

8. PRIORITA' DI SUGGERIMENTO sulla watchlist: l'obiettivo e' DIVERSIFICARE.
   Asset PREFERITI (alta priorita' se ci sono buone occasioni):
   - bond_govt (BTP, Bund, Treasury): mancano completamente nel portafoglio
   - bond_globale (AGGH): mancano completamente
   - oro (SGLD): decorrelato, ottimo hedge inflazione
   - azionario_em (EIMI): VWCE e' 70% USA, gli emerging mancano
   - settoriali NON-tech (banche, healthcare): diversifica settorialmente
   Asset CON CAUTELA (suggerisci solo se davvero c'e' motivo eccellente):
   - azioni tech USA singole (AAPL/MSFT/GOOGL/META): Adriano ha gia' troppa
     esposizione tech via NVIDIA + EQAC + 30% di VWCE. Suggerisci solo come
     scambio sostitutivo, non come accumulo.
   Asset NEUTRI:
   - JPM, BRK-B, UNH: ok come diversificatori settoriali

9. Il signal_asset puo' essere QUALSIASI ticker (portfolio o watchlist).
   Se e' un asset di watchlist, signal_action sara' tipicamente "valuta ingresso/accumulo".
   Se e' un asset del portfolio, puo' essere "considera incremento" o "considera alleggerimento".

==============================
OUTPUT FORMAT
==============================

Rispondi SEMPRE in JSON valido con questa struttura esatta:
{
  "summary": "1 riga sintesi della giornata in italiano semplice",
  "portfolio_note": "1-2 righe sul portafoglio - se usi termini tecnici, spiegali",
  "events": ["evento 1 spiegato semplice", "evento 2 spiegato semplice"],
  "signal_level": "GREEN" | "YELLOW" | "NONE",
  "signal_asset": "ticker o null",
  "signal_action": "breve descrizione azione suggerita in italiano semplice o null",
  "signal_reasoning": "ragionamento con 3+ fattori in italiano semplice o null",
  "signal_counter": "contro-argomento/rischio in italiano semplice o null",
  "signal_suggested_amount_eur": numero o null,
  "signal_what_to_do": "passi operativi concreti che Adriano può fare oggi/questa settimana: es. 'Imposta alert su Fineco a €157 per VWCE. Se ci arriva, valuta acquisto di 2-3 quote.' Massimo 2-3 frasi pratiche. null se signal_level=NONE",
  "signal_what_to_watch": "cosa monitorare per capire se il segnale resta valido o no: indicatori, eventi, soglie di prezzo. Es. 'Tasso decennale USA: se supera 4.5% rivedi. Comunicato Fed mercoledì.' Massimo 2-3 punti. null se signal_level=NONE",
  "signal_importance": 1 | 2 | 3 | 4 | 5,
  "closing_note": "1 riga finale. Se hai dato un segnale, ricorda esplicitamente che la decisione e' di Adriano"
}

Per signal_importance usa questa scala:
- 1: marginale, può aspettare settimane
- 2: da tenere d'occhio nei prossimi 7-14 giorni
- 3: rilevante, controllare ogni 2-3 giorni
- 4: importante, monitoraggio quotidiano consigliato
- 5: urgente, decisione entro 1-2 giorni (eventi catalizzatori imminenti)
Se signal_level=NONE allora signal_importance=1.

Tono: amichevole ma onesto. Mai hype, mai emoji, mai esclamativi tipo "Ottima notizia!".
Mai parole inglesi non spiegate (hawkish, dovish, sell-off, rally, dip, ecc. - traducile
o spiegale tra parentesi)."""


def generate_briefing(portfolio_data: dict, news: list, events: dict,
                      watchlist: list | None = None) -> dict:
    """Chiama Claude e restituisce briefing strutturato in dict.
    watchlist: lista di asset NON posseduti ma monitorati. L'AI può
    emettere segnali GREEN/YELLOW sia su portfolio che su watchlist."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return {
            "error": "ANTHROPIC_API_KEY non configurata",
            "summary": "Errore configurazione",
            "signal_level": "NONE",
        }

    client = anthropic.Anthropic(api_key=api_key)

    # Costruzione prompt utente
    uc = f"""DATI DI OGGI

## Portafoglio (valore approx €{portfolio_data.get('total_value_eur_approx', 0)})
"""
    for h in portfolio_data.get("holdings", []):
        if "error" in h:
            uc += f"- {h.get('name', h.get('ticker'))}: errore dati\n"
            continue
        uc += (
            f"- {h['name']} ({h['ticker']}): {h['current']} {h['currency']}, "
            f"oggi {h['daily_change_pct']:+.2f}%, "
            f"settimana {h['weekly_change_pct']:+.2f}%, "
            f"mese {h['monthly_change_pct']:+.2f}%, "
            f"qty {h['quantity']}\n"
        )

    if portfolio_data.get("alerts"):
        uc += "\n## Alert soglie automatiche\n"
        for a in portfolio_data["alerts"]:
            uc += f"- {a}\n"

    if watchlist:
        uc += (
            "\n## Watchlist (asset NON posseduti ma monitorati per possibile acquisto)\n"
            "Puoi suggerire ingresso/accumulo su questi se vedi una buona ragione "
            "(prezzo scontato, evento favorevole, diversificazione utile per il portafoglio).\n"
        )
        # Raggruppa per category per dare contesto al modello
        from collections import defaultdict
        by_cat = defaultdict(list)
        for w in watchlist:
            if "error" in w:
                continue
            by_cat[w.get("category", "altro")].append(w)
        for cat, items in by_cat.items():
            cat_label = cat.replace("_", " ")
            uc += f"\n### {cat_label}\n"
            for w in items:
                ucits_alts = w.get("ucits_equivalents") or []
                ucits_str = f" [UCITS Fineco: {', '.join(ucits_alts)}]" if ucits_alts else ""
                uc += (
                    f"- {w['name']} ({w['display_ticker']}){ucits_str}: "
                    f"{w['current']} {w['currency']}, "
                    f"oggi {w['daily_change_pct']:+.2f}%, "
                    f"settimana {w['weekly_change_pct']:+.2f}%, "
                    f"mese {w['monthly_change_pct']:+.2f}%\n"
                )
        uc += (
            "\nIMPORTANTE: alcuni asset USA della watchlist (GLD, AGG, IEF, ecc.) sono "
            "*proxy* per monitorare i prezzi via API. Adriano NON può comprare un ETF "
            "USA su Fineco (KID UCITS mancante). Se suggerisci uno di questi, "
            "DEVI esplicitare nel signal_what_to_do quale ETF UCITS comprare su Fineco "
            "(es. 'invece di GLD su Fineco compra SGLD.MI o PHAU.MI, sono lo stesso oro fisico').\n"
        )

    if events.get("earnings"):
        uc += "\n## Earnings imminenti (date in cui le aziende pubblicano i risultati)\n"
        for e in events["earnings"]:
            uc += f"- {e['description']} (data: {e['date']})\n"

    uc += "\n## News ultime 24h (top 10 per rilevanza)\n"
    for n in news[:10]:
        uc += f"- [{n['source']}] {n['title']}\n"

    uc += ("\nProduci il briefing in JSON secondo le regole di sistema. "
           "Ricorda: linguaggio da amico che spiega, ogni termine tecnico va tradotto. "
           "Se NONE, va benissimo - non forzare segnali.")

    raw = ""
    try:
        response = client.messages.create(
            model=MODEL,
            # 2500 token output: 1500 erano sufficienti col vecchio schema (4 campi
            # signal_*), ma con i 3 nuovi (what_to_do, what_to_watch, importance) +
            # ragionamento più lungo sulla watchlist (15 asset extra) il JSON
            # finiva troncato → "Unterminated string". 2500 dà margine abbondante
            # senza incidere significativamente sui costi (~$0.03/run su Sonnet).
            max_tokens=2500,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": uc}],
        )
        raw = response.content[0].text.strip()

        # Ripulisci eventuali code fence
        if raw.startswith("```"):
            raw = raw.split("```", 2)[1]
            if raw.startswith("json"):
                raw = raw[4:].strip()
            raw = raw.strip().rstrip("`").strip()

        parsed = json.loads(raw)
        parsed["_model_used"] = MODEL
        parsed["_tokens"] = {
            "input": response.usage.input_tokens,
            "output": response.usage.output_tokens,
        }
        return parsed
    except json.JSONDecodeError as e:
        return {
            "error": f"JSON parse failed: {e}",
            "raw_output": raw[:500],
            "summary": "Errore generazione briefing AI",
            "signal_level": "NONE",
        }
    except Exception as e:
        return {
            "error": str(e),
            "summary": "Errore API",
            "signal_level": "NONE",
        }


if __name__ == "__main__":
    fake_portfolio = {
        "total_value_eur_approx": 1987.5,
        "holdings": [
            {"name": "NVIDIA", "ticker": "NVDA", "quantity": 1, "current": 199.88,
             "currency": "USD", "daily_change_pct": -6.5,
             "weekly_change_pct": -4.1, "monthly_change_pct": 8.7}
        ],
        "alerts": ["NVIDIA ha fatto -6.50% oggi"],
    }
    fake_news = [
        {"source": "Reuters", "title": "Semiconductor sector drops on China tariff fears"},
        {"source": "CNBC", "title": "Fed minutes show split on rate path"},
    ]
    fake_events = {"earnings": [{"description": "NVDA trimestrale tra 10 giorni",
                                  "date": "2026-05-01"}]}
    result = generate_briefing(fake_portfolio, fake_news, fake_events)
    print(json.dumps(result, indent=2, ensure_ascii=False))
