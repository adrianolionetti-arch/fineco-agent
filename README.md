# Fineco Daily Briefing Agent

Agente AI che ogni mattina (lun-ven, 09:30 ora italiana):
- Ti manda un'email con briefing e segnali operativi
- Aggiorna una **dashboard web privata** con storico, grafici e backtest live

**Costo totale**: ~€0.30/mese (solo API Claude, il resto è gratis).

## Cosa vedrai

**Nell'email**: sintesi di 200 parole con eventuale segnale GREEN/YELLOW/NONE, ragionamento, contro-argomenti, portafoglio.

**Nella dashboard** (https://TUOUSERNAME.github.io/NOMEREPO/):
- Segnale del giorno in hero section
- Grafico performance portafoglio vs benchmark ETF World (VWCE)
- Backtest live: hit rate, performance media per segnale
- Cronologia di tutti i segnali con performance attuale di ognuno
- Holdings con variazioni 1d/7d/30d
- News del giorno ed eventi imminenti
- **Accesso protetto da password** (sessione)

Anteprima visiva: apri `docs/demo.html` nel browser dopo aver scaricato il progetto.

## ⚠️ Nota sulla sicurezza della dashboard

La password è controllata lato JavaScript con hash SHA-256. **Non è sicurezza crittografica vera**: chi sa cosa sta facendo può guardare il codice. Funziona contro curiosi casuali, motori di ricerca e scraper. I dati sono anonimizzati (solo % performance, mai valori in €), quindi anche in caso peggiore nessuno saprà il tuo patrimonio.

Se un domani vuoi sicurezza vera: migriamo a repo privato + Cloudflare Pages con Access (5 min in più).

---

## Setup completo — 25 minuti, una volta sola

### Step 1 — Crea repo GitHub **pubblico** (2 min)

Dashboard gratis richiede repo pubblico su GitHub. I tuoi dati sono anonimizzati, ma il codice sarà visibile. Se vuoi tutto privato, salta al paragrafo "Alternativa privata" in fondo.

Crea nuovo repo pubblico su github.com e carica tutti i file di questa cartella.

### Step 2 — API key Anthropic (3 min)

https://console.anthropic.com/ → account + $5 di credito → sezione "API Keys" → crea chiave → copiala.

### Step 3 — Gmail App Password (5 min)

1. Attiva 2FA su Google: https://myaccount.google.com/security
2. https://myaccount.google.com/apppasswords → crea app password (nome "fineco-briefing")
3. Copia la password a 16 caratteri.

### Step 4 — Secrets GitHub (5 min)

Repo → `Settings` → `Secrets and variables` → `Actions` → aggiungi 5 secret:

| Nome | Valore |
|---|---|
| `ANTHROPIC_API_KEY` | chiave step 2 |
| `GMAIL_USER` | tua email Gmail |
| `GMAIL_APP_PASSWORD` | password 16 caratteri step 3 |
| `RECIPIENT_EMAIL` | dove vuoi ricevere briefing |
| `DASHBOARD_PASSWORD` | una password a tua scelta per l'accesso dashboard |

### Step 5 — Abilita GitHub Pages (2 min)

Repo → `Settings` → `Pages`:
- Source: **GitHub Actions**
- Salva

La dashboard sarà live a `https://TUOUSERNAME.github.io/NOMEREPO/` dopo il primo run del workflow.

### Step 6 — Configura portafoglio (5 min)

Apri `src/portfolio.py` e modifica la lista `PORTFOLIO`.

**Trovare ticker ETF Fineco**:
1. Prendi l'ISIN dal tuo Fineco (es. `IE00BK5BQT80`)
2. Cercalo su https://finance.yahoo.com
3. Usa il simbolo Yahoo (es. `VWCE.DE`, `IWDA.AS`, `AGGH.MI`)

Esempio:
```python
PORTFOLIO = [
    {"ticker": "NVDA", "quantity": 1, "name": "NVIDIA", "type": "stock"},
    {"ticker": "VWCE.DE", "quantity": 3, "name": "Vanguard All-World", "type": "etf_equity"},
    {"ticker": "AGGH.MI", "quantity": 8, "name": "iShares Global Aggregate", "type": "etf_bond"},
]
```

### Step 7 — Test manuale (3 min)

Repo → tab `Actions` → `Daily Briefing` → `Run workflow` → attendi 2-3 min.

Verifica che:
1. L'email ti sia arrivata
2. La dashboard sia live (URL in step 5)
3. La tua password funzioni

Da domani tutto parte automaticamente ogni giorno feriale alle 09:30.

---

## Costi

| Componente | Costo |
|---|---|
| GitHub Actions + Pages | Gratis (<2% del limite mensile su account free) |
| Claude API Sonnet 4.6 | ~€0.015 × 22 giorni = €0.33/mese |
| Gmail SMTP, Yahoo Finance, RSS | Gratis |
| **Totale** | **~€4/anno** |

Cambio modello: modifica `MODEL` in `src/briefing.py` o usa tendina override nel workflow manuale.
- `claude-haiku-4-5`: €0.10/mese
- `claude-sonnet-4-5` (default): €0.30/mese
- `claude-opus-4-7`: €0.50/mese

---

## Sistema di segnali

| Livello | Criterio verificato in codice | Frequenza attesa |
|---|---|---|
| 🟢 GREEN | \|giorno\| ≥ 5% **oppure** \|settimana\| ≥ 8% | 1-3/mese |
| 🟡 YELLOW | \|giorno\| ≥ 2% **oppure** \|settimana\| ≥ 3% **oppure** \|mese\| ≥ 5% | 3-8/mese |
| ⚪ NONE | tutto il resto | Maggior parte dei giorni |

Ogni segnale include sempre ragionamento, contro-argomento e rischio.

### Il gate (`src/signal_gate.py`) — perché il livello non lo decide l'AI

Da maggio a settembre 2026 l'agente ha emesso **97 segnali: 97 YELLOW, zero GREEN,
zero NONE**. Il prompt chiedeva esplicitamente di usare NONE spesso e non è mai stato
ascoltato. Stessa cosa per l'importanza: prima sempre 2/5, poi — dopo un fix che
aggiungeva istruzioni al prompt — sempre 3/5.

Un modello che deve scegliere fra "dire qualcosa" e "dire che non c'è niente da dire"
sceglie sempre la prima. Quindi la soglia è uscita dal prompt ed è entrata nel codice:

- l'AI **propone** un livello, il gate lo **verifica** contro il movimento di prezzo reale;
- il gate può solo **declassare**, mai promuovere;
- **anti-ripetizione**: stesso ticker già segnalato negli ultimi 10 giorni con il prezzo
  fermo entro il 3% → NONE. Nasce dai 4 segnali identici su AGGH fra l'11 e il 21
  settembre, col prezzo che oscillava fra 4,84 e 4,85;
- l'**importanza** è calcolata da una funzione deterministica, non più dichiarata dall'AI.

Le declassature finiscono nei log del workflow (`[gate] ...`), quindi sono sempre ispezionabili.

Test: `python tests/test_signal_gate.py`

### Recupero esercizi (`src/quiz_recap.py`)

Il quiz del weekend si è fermato il 06/09/2026 perché il Livello 1 è finito (15/15
inviati), ma il problema era arrivato prima: dal 1° agosto nessun esercizio riceveva
più risposta. Sette sono rimasti in sospeso — non per disinteresse, ma perché l'email
del sabato passava inosservata.

Una seconda email dedicata avrebbe fatto la stessa fine. Il promemoria viaggia quindi
**dentro il briefing quotidiano**, che invece viene aperto: un arretrato al giorno, a
rotazione. Nel weekend, dove il briefing non gira, se ne occupa `weekend-quiz.yml`,
che invece di tacere ripropone un arretrato.

`reconcile()` interroga il Worker per **tutti** gli esercizi pendenti: `run_sunday()`
guardava solo l'ultimo inviato, quindi una risposta data in ritardo a un esercizio
vecchio non sarebbe mai stata registrata. I punti sul recupero sono pieni, il bonus
streak no: quello premia la costanza settimanale.

Quando i 7 arretrati saranno chiusi, servirà il **Livello 2** — oggi non esiste e
`weekend_quiz.py` punta a `livello_1_basi.json` in modo fisso.

### Feedback loop

`data/signal_performance.json` contiene l'esito reale dei segnali recenti misurato
**contro il benchmark VWCE**, e viene iniettato nel prompt del briefing. Senza questo
l'agente non aveva modo di sapere che una sua tesi stava perdendo — e infatti l'ha
ripetuta per mesi (14 segnali su AGGH, 0 volte meglio del non fare nulla).

Il file è rigenerato ogni domenica dal workflow `weekly-performance.yml`, non a ogni
briefing: il calcolo scarica una decina di serie storiche e la fonte è la stessa che
manda in 429 il job quotidiano.

---

## Analisi retrospettiva

Il diario salva ogni segnale in `journal/signals.csv`. Per analisi approfondita in locale:

```bash
git pull
pip install -r requirements.txt
python src/backtest.py                  # report completo a schermo
python src/backtest.py --write-cache    # aggiorna la cache letta dal briefing
```

Il confronto è sempre **segnale contro VWCE sugli stessi giorni**: in un mercato che sale,
sale quasi tutto, quindi "il segnale ha guadagnato" non vuol dire niente da solo. L'unica
domanda sensata è se abbia fatto meglio del non fare nulla.

> **Bug corretto il 2026-09-22 — se leggi vecchi numeri, diffida.** La versione precedente
> confrontava il prezzo salvato nel CSV (in **euro**) col prezzo attuale di yfinance (in
> **dollari** per i ticker USA), sommando di fatto il tasso di cambio alla performance.
> Dichiarava 83% di hit rate e +12,58% medio. A valuta coerente i numeri veri erano
> +2,19% contro +3,11% del benchmark: **alfa −0,93%**, con solo 23 segnali su 60 capaci
> di battere il semplice tenere VWCE.

**Usa il diario onestamente**: se l'alfa resta negativo, l'AI non ha edge su questi mercati
e va tenuta come radar informativo, non come consulente.

---

## Personalizzazioni comuni

### Cambiare orario invio
`.github/workflows/daily-briefing.yml` → modifica `cron: '30 7 * * 1-5'` (UTC!).

### Cambiare benchmark
`src/dashboard_builder.py` → modifica `BENCHMARK_TICKER`.

### Aggiungere fonti news
`src/news.py` → aggiungi URL a `RSS_FEEDS`.

### SMS (solo per GREEN, ~€0.08/sms)
Aggiungi account Twilio, import `twilio` in `emailer.py`, invia sms solo se `signal_level == "GREEN"`.

---

## Troubleshooting

- **Dashboard 404**: verifica che GitHub Pages sia attivato con source "GitHub Actions", attendi 2-3 min dopo il primo run.
- **Password non funziona**: cancella sessionStorage (F12 → Application → Session Storage → delete), riprova. Oppure rilancia workflow dopo aver aggiornato il secret.
- **Email non arriva**: controlla spam, verifica 4 secret. SMTP error 535 = App Password sbagliata.
- **Ticker not found**: prova suffissi `.DE` `.MI` `.AS` `.L` `.PA` in base alla borsa europea.
- **Journal/history non persistono**: verifica che il workflow abbia `permissions: contents: write`.

---

## Alternativa privata (repo privato + Cloudflare Pages)

Se vuoi tutto privato:
1. Crea repo privato GitHub
2. Crea account Cloudflare (gratis) → Pages → Connect to Git
3. Build command: vuoto. Output: `docs`
4. Abilita Cloudflare Access (gratis fino a 50 utenti) per email-based auth
5. Il workflow non deploya più su Pages, ma Cloudflare si sincronizza automaticamente ad ogni push

Setup extra: ~10 min. Sicurezza: vera (autenticazione serverside), non lato JS.

---

## Prossimi step suggeriti

1. **Osserva 2-3 mesi prima di agire**: lascia popolare il diario, guarda il backtest sulla dashboard, non eseguire trade.
2. **Misura, non credere**: se dopo 30+ segnali il tuo portafoglio virtuale dei segnali batte VWCE, puoi iniziare a seguirli con piccole somme (100-200€).
3. **PAC mensile automatico** su ETF world: per profilo medio-basso con 2k, matematicamente resta la migliore strategia. L'agente è un complemento, non un sostituto.
