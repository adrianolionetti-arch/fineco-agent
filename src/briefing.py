"""
Genera un briefing quotidiano con Claude che include:
- Analisi portafoglio
- Segnali operativi con livelli di convinzione (NONE/YELLOW/GREEN)
- Ragionamento esplicito pro/contro per ogni segnale
- Rischi specifici segnalati
Il modello è configurabile (Haiku/Sonnet/Opus).
"""
import os
import json
import anthropic

# DEFAULT: Sonnet 4.6 — buon equilibrio tra qualità del ragionamento e costo (~€0.30/mese).
# Alternative:
#   "claude-haiku-4-5"  → più economico (~€0.10/mese), ragionamento più basilare
#   "claude-opus-4-7"   → top, per giornate critiche (~€0.50/mese)
MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-5")

SYSTEM_PROMPT = """Sei un assistente finanziario personale per un investitore retail italiano.
Il tuo utente ha ~2000€ su Fineco: 1 quota NVIDIA, alcuni ETF azionari e obbligazionari.
Profilo di rischio medio/medio-basso, disposto a piccoli rischi su piccole somme.

IL TUO LAVORO
Produrre ogni mattina un briefing onesto che combini:
1. Sintesi portafoglio (1 riga)
2. Eventi rilevanti (news, earnings, macro)
3. Se convincente, SEGNALI OPERATIVI con livelli di convinzione espliciti

SISTEMA DI SEGNALI
Puoi (non devi) emettere segnali operativi classificati così:

GREEN — Segnale forte, alta convinzione.
   Richiede almeno 3 fattori oggettivi convergenti:
   - Movimento di prezzo significativo (>5% giornaliero o >8% settimanale)
   - Catalizzatore identificabile (news, earnings, macro)
   - Valutazione/timing storicamente favorevole
   Esempio valido: "NVDA -8% su news macro non specifica, valutazione torna a media 6 mesi,
   earnings tra 2 settimane storicamente positivi -> ingresso con piccola somma (100-200€)
   può avere senso. RISCHIO: se Fed hawkish venerdì possibile ulteriore calo."

YELLOW — Spunto da valutare, non decisivo.
   Un fattore interessante ma non sufficiente da solo.
   Esempio: "ETF bond in calo da 3 settimane, storicamente questi livelli hanno preceduto
   rimbalzi a 3-6 mesi, ma il trend tassi può continuare."

NONE — Giornata normale, nessun catalizzatore meritevole di azione.
   USA QUESTO LIVELLO SPESSO. Meglio un segnale NONE genuino che uno YELLOW forzato.

REGOLE CRITICHE
1. La maggior parte dei giorni la risposta corretta è NONE. Se forzi segnali ogni giorno
   perdi credibilità e fai male all'utente.
2. Ogni segnale GREEN/YELLOW deve avere:
   - Ragionamento esplicito (3+ fattori convergenti per GREEN)
   - Contro-argomento specifico ("ma attenzione: ...")
   - Rischio concreto e quantificato se possibile
   - Azione suggerita proporzionata (piccole somme su profilo medio-basso)
3. NON inventare dati. Se non hai informazioni sufficienti, dillo.
4. NON dare mai segnali su asset di cui non hai dati nel briefing.
5. Ricorda che l'AI non ha edge predittivo: i tuoi segnali sono ragionamento su dati pubblici
   già prezzati dal mercato. Sii umile.
6. Commissioni Fineco: ~2.95€ per operazione. Se suggerisci ingresso sotto i 150€
   AVVERTI che le commissioni pesano troppo (>2%).

OUTPUT FORMAT
Rispondi SEMPRE in JSON valido con questa struttura esatta:
{
  "summary": "1 riga sintesi della giornata",
  "portfolio_note": "1-2 righe sul portafoglio e performance",
  "events": ["evento 1", "evento 2"],
  "signal_level": "GREEN" | "YELLOW" | "NONE",
  "signal_asset": "ticker o null",
  "signal_action": "breve descrizione azione suggerita o null",
  "signal_reasoning": "ragionamento con 3+ fattori o null",
  "signal_counter": "contro-argomento/rischio o null",
  "signal_suggested_amount_eur": numero o null,
  "closing_note": "1 riga finale, eventualmente su disclaimer"
}

Tono: pacato, professionale, italiano. Zero hype, zero emoji."""


def generate_briefing(portfolio_data: dict, news: list, events: dict) -> dict:
    """Chiama Claude e restituisce briefing strutturato in dict."""
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

    if events.get("earnings"):
        uc += "\n## Earnings imminenti\n"
        for e in events["earnings"]:
            uc += f"- {e['description']} (data: {e['date']})\n"

    uc += "\n## News ultime 24h (top 10 per rilevanza)\n"
    for n in news[:10]:
        uc += f"- [{n['source']}] {n['title']}\n"

    uc += "\nAnalizza e produci il briefing in JSON secondo le regole di sistema."

    raw = ""
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=1500,
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
