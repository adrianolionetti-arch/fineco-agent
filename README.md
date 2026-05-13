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

| Livello | Criterio | Frequenza attesa |
|---|---|---|
| 🟢 GREEN | 3+ fattori convergenti oggettivi | 1-3/mese |
| 🟡 YELLOW | Spunto interessante ma non decisivo | 3-8/mese |
| ⚪ NONE | Giornata normale | Maggior parte dei giorni |

Ogni segnale include sempre ragionamento, contro-argomento e rischio.

---

## Analisi retrospettiva

Il diario salva ogni segnale in `journal/signals.csv`. Per analisi approfondita in locale:

```bash
git pull
pip install -r requirements.txt
python src/backtest.py
```

**Usa il diario onestamente**: dopo 2-3 mesi guarda i numeri. Se l'hit rate è <55% o la performance è sotto VWCE, sai che l'AI non ha edge su questi mercati e puoi tenerlo solo come radar informativo.

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
