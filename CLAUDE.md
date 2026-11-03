# CLAUDE.md — fineco-agent

Briefing di trading e quiz del weekend. Repo git: `adrianolionetti-arch/fineco-agent`. Workflow GitHub in `.github/workflows/` (`daily-briefing.yml`, `weekend-quiz.yml`), dashboard in `docs/index.html`.

## Worker `fineco-quiz`
- Codice: `worker/quiz-receiver.js`, config `wrangler.toml`. Endpoint: `https://fineco-quiz.adriano-lionetti.workers.dev` (`/health`, `/answer`, `/answers/recent`, `/chat`).
- Dal 23/10/2026 gira sul **nuovo account Cloudflare personale**: stesso indirizzo (sottodominio `adriano-lionetti` trasferito), nuovo KV `QUIZ_KV` (ID aggiornato in `wrangler.toml`) con le 17 risposte importate da `quiz_kv_backup.json` (gitignored, si può cancellare a migrazione chiusa).
- Secret del Worker: `ANTHROPIC_API_KEY`, `QUIZ_TOKEN`; in locale in `.dev.vars` (gitignored). Deploy: `CLOUDFLARE_ACCOUNT_ID=<id nuovo account> npx wrangler deploy`.
- Da fare: le modifiche locali a `wrangler.toml` e `.gitignore` non sono committate. Il `QUIZ_TOKEN` è in chiaro in `docs/index.html` (pagina pubblica): chiunque può scrivere nel KV e usare la chiave Anthropic tramite `/chat`; va spostato o protetto.
