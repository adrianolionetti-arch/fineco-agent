/**
 * Cloudflare Worker — Fineco Agent endpoints
 *
 * Endpoint: https://fineco-quiz.adriano-lionetti.workers.dev/
 *
 * Routes:
 *   POST /answer         → salva risposta del quiz { exercise_id, answer }
 *   GET  /answer/:id     → legge risposta per un exercise_id
 *   GET  /answers/recent → lista delle ultime 30 risposte (usata dal workflow)
 *   POST /chat           → chatbot consultivo (watchlist, segnali storici, glossario)
 *   GET  /health         → ping
 */

const ALLOWED_ORIGIN = "https://adrianolionetti-arch.github.io";
const REPO_RAW = "https://raw.githubusercontent.com/adrianolionetti-arch/fineco-agent/main";

function corsHeaders(origin) {
  const allow = origin === ALLOWED_ORIGIN ? origin : ALLOWED_ORIGIN;
  return {
    "Access-Control-Allow-Origin": allow,
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, X-Quiz-Token",
    "Access-Control-Max-Age": "86400",
  };
}

function json(status, body, origin) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...corsHeaders(origin) },
  });
}

function isValidExerciseId(id) {
  return typeof id === "string" && /^L\d+-E\d{2}$/.test(id);
}

function isValidAnswer(a) {
  return ["A", "B", "C", "D"].includes(a);
}

// ──────────────────────────── /chat helpers ────────────────────────────

const SYSTEM_PROMPT_BASE = `Sei l'assistente Fineco di Adriano. Lo aiuti a ragionare su quello che vede nella sua dashboard: portafoglio, watchlist (asset monitorati ma non posseduti), segnali storici, eventi, pillole formative.

CHI È ADRIANO
Tech PM, ~€2k investiti su Fineco, profilo di rischio medio/basso, orizzonte 10+ anni. Legge codice ma non è developer. Sta imparando finanza: principiante consapevole.

COME RISPONDI
- Italiano. Tono diretto, no preamboli ("ottima domanda" e simili sono vietati).
- Risposta calibrata alla domanda: domanda breve → risposta breve.
- Sempre alternative quando proponi una soluzione, con trade-off espliciti.
- Se ha torto, contraddiscilo educatamente. Non assensi di cortesia.
- Termini tecnici: se sono nel glossario li usi normalmente. Se non ci sono li spieghi la prima volta che li menzioni.

COSA PUOI FARE
1. Spiegare cosa significa un dato nella dashboard (segnale, importanza, watchlist asset, evento).
2. Fare follow-up su asset in watchlist: "come sta andando l'oro che mi avevi segnalato?" → rispondi usando i dati storici che hai sotto.
3. Collegare un esercizio del Livello 1 alla situazione attuale del portafoglio.
4. Sintetizzare cosa è successo nell'ultima settimana/mese nei segnali ricevuti.
5. Spiegare termini di finanza pescando dal glossario.

COSA NON FAI (guardrail importanti, leggi bene)
- ❌ Non dai segnali operativi nuovi su richiesta. I segnali Verdi/Gialli arrivano solo nel briefing della mattina. Se ti chiede "devo comprare X?" rispondi: "I segnali pianificati arrivano la mattina lun-ven. Se senti il bisogno di agire adesso, è probabilmente FOMO — vedi L1-E11."
- ❌ Non prezzi asset in tempo reale. Lavori solo sui dati che hai (aggiornati al briefing del giorno).
- ❌ Non fai previsioni di breve termine (settimane). Puoi commentare trend di lungo periodo.
- ❌ Non raccomandi singoli acquisti/vendite con un "compra X, vendi Y". Aiuti a ragionare, non sostituisci il briefing AI.
- ❌ Non incoraggi il monitoraggio compulsivo dei prezzi. Se chiede 10 volte al giorno "come va NVIDIA", a un certo punto dici: "Hai già controllato 3 volte oggi. Ricorda L1-E11 — controllare di più non fa salire i prezzi, fa solo venire ansia di fare qualcosa."

Quando rifiuti, spiega il perché in 1-2 frasi e proponi cosa fare invece. Non essere robotico.`;

function trimText(s, maxChars) {
  if (!s) return "";
  if (s.length <= maxChars) return s;
  return s.slice(0, maxChars) + "\n…[truncated]";
}

async function fetchRepoContext() {
  // Carica in parallelo i file di contesto dal repo
  const urls = [
    REPO_RAW + "/docs/data.json",
    REPO_RAW + "/data/history.json",
    REPO_RAW + "/journal/signals.csv",
    REPO_RAW + "/glossario_finanza.md",
    REPO_RAW + "/portafoglio_fineco.md",
    REPO_RAW + "/profilo_investitore.md",
  ];
  const results = await Promise.all(
    urls.map(u =>
      fetch(u, { cf: { cacheTtl: 300 } })
        .then(r => (r.ok ? r.text() : ""))
        .catch(() => "")
    )
  );
  const [data, history, signals, glossario, portafoglio, profilo] = results;

  // Trim per non esplodere il context
  return {
    data_today: trimText(data, 12000),
    history: trimText(history, 4000),
    signals_csv: trimText(signals, 6000),
    glossario: trimText(glossario, 8000),
    portafoglio: trimText(portafoglio, 4000),
    profilo: trimText(profilo, 3000),
  };
}

function buildContextMessage(ctx) {
  // Blocco contesto separato dal system prompt → cachabile a parte
  return `<contesto_dashboard>
Questo è lo stato corrente di Adriano. Usa SOLO questi dati per le risposte.

=== Profilo investitore ===
${ctx.profilo}

=== Portafoglio reale ===
${ctx.portafoglio}

=== Stato dashboard di oggi (briefing + watchlist + segnale del giorno) ===
${ctx.data_today}

=== Storico prezzi portafoglio ===
${ctx.history}

=== Storico segnali AI (signals.csv) ===
${ctx.signals_csv}

=== Glossario personalizzato di Adriano ===
${ctx.glossario}
</contesto_dashboard>`;
}

async function handleChat(request, env, origin) {
  let body;
  try {
    body = await request.json();
  } catch {
    return json(400, { error: "Invalid JSON" }, origin);
  }

  const messages = Array.isArray(body.messages) ? body.messages : null;
  if (!messages || messages.length === 0) {
    return json(400, { error: "Missing messages[]" }, origin);
  }

  // Validazione messaggi
  for (const m of messages) {
    if (!m || typeof m !== "object") return json(400, { error: "Invalid message" }, origin);
    if (m.role !== "user" && m.role !== "assistant") return json(400, { error: "Invalid role" }, origin);
    if (typeof m.content !== "string" || m.content.length === 0) {
      return json(400, { error: "Empty content" }, origin);
    }
    if (m.content.length > 4000) return json(400, { error: "Message too long" }, origin);
  }
  if (messages.length > 30) return json(400, { error: "Too many messages" }, origin);

  if (!env.ANTHROPIC_API_KEY) {
    return json(500, { error: "Server missing ANTHROPIC_API_KEY" }, origin);
  }

  const ctx = await fetchRepoContext();
  const contextMessage = buildContextMessage(ctx);

  // Anthropic API call con prompt caching su system + contesto
  const anthropicReq = {
    model: env.CHAT_MODEL || "claude-sonnet-4-5",
    max_tokens: 1024,
    system: [
      { type: "text", text: SYSTEM_PROMPT_BASE, cache_control: { type: "ephemeral" } },
      { type: "text", text: contextMessage, cache_control: { type: "ephemeral" } },
    ],
    messages: messages.map(m => ({ role: m.role, content: m.content })),
  };

  let aRes;
  try {
    aRes = await fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-api-key": env.ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
      },
      body: JSON.stringify(anthropicReq),
    });
  } catch (e) {
    return json(502, { error: "Anthropic API unreachable: " + e.message }, origin);
  }

  if (!aRes.ok) {
    const text = await aRes.text();
    return json(502, { error: "Anthropic API error", status: aRes.status, detail: text.slice(0, 500) }, origin);
  }

  const aData = await aRes.json();
  const reply = (aData.content || [])
    .filter(b => b.type === "text")
    .map(b => b.text)
    .join("\n");

  return json(200, {
    reply,
    model: aData.model,
    usage: aData.usage,
  }, origin);
}

// ──────────────────────────── main entry ────────────────────────────

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const origin = request.headers.get("Origin") || "";

    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: corsHeaders(origin) });
    }

    if (url.pathname === "/health") {
      return json(200, { ok: true, time: new Date().toISOString() }, origin);
    }

    const token = request.headers.get("X-Quiz-Token");
    if (env.QUIZ_TOKEN && token !== env.QUIZ_TOKEN) {
      return json(401, { error: "Unauthorized" }, origin);
    }

    // ─── Chat ───
    if (request.method === "POST" && url.pathname === "/chat") {
      return handleChat(request, env, origin);
    }

    // ─── Quiz: POST /answer ───
    if (request.method === "POST" && url.pathname === "/answer") {
      let payload;
      try {
        payload = await request.json();
      } catch {
        return json(400, { error: "Invalid JSON" }, origin);
      }
      const { exercise_id, answer } = payload;
      if (!isValidExerciseId(exercise_id)) {
        return json(400, { error: "Invalid exercise_id" }, origin);
      }
      if (!isValidAnswer(answer)) {
        return json(400, { error: "Invalid answer" }, origin);
      }
      const key = `answer:${exercise_id}`;
      const existing = await env.QUIZ_KV.get(key);
      if (existing) {
        const prev = JSON.parse(existing);
        return json(200, {
          ok: true,
          already_answered: true,
          previous_answer: prev.answer,
          previous_answered_at: prev.answered_at,
        }, origin);
      }
      const record = {
        exercise_id,
        answer,
        answered_at: new Date().toISOString(),
      };
      await env.QUIZ_KV.put(key, JSON.stringify(record));
      const recentRaw = (await env.QUIZ_KV.get("recent_answers")) || "[]";
      const recent = JSON.parse(recentRaw);
      recent.unshift(record);
      await env.QUIZ_KV.put("recent_answers", JSON.stringify(recent.slice(0, 30)));
      return json(200, { ok: true, saved: record }, origin);
    }

    // ─── Quiz: GET /answer/:id ───
    if (request.method === "GET" && url.pathname.startsWith("/answer/")) {
      const id = url.pathname.slice("/answer/".length);
      if (!isValidExerciseId(id)) {
        return json(400, { error: "Invalid exercise_id" }, origin);
      }
      const stored = await env.QUIZ_KV.get(`answer:${id}`);
      if (!stored) {
        return json(404, { error: "No answer for this exercise" }, origin);
      }
      return json(200, JSON.parse(stored), origin);
    }

    // ─── Quiz: GET /answers/recent ───
    if (request.method === "GET" && url.pathname === "/answers/recent") {
      const stored = (await env.QUIZ_KV.get("recent_answers")) || "[]";
      return json(200, JSON.parse(stored), origin);
    }

    return json(404, { error: "Not found" }, origin);
  },
};
