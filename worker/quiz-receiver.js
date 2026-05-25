/**
 * Cloudflare Worker — riceve risposte del quiz weekend dalla dashboard
 * e le salva in KV. Il workflow GitHub Actions della domenica legge
 * da qui per generare l'email di soluzione.
 *
 * Endpoint: https://fineco-quiz.adriano-lionetti.workers.dev/
 *
 * Routes:
 *   POST /answer         → salva risposta { exercise_id, answer }
 *   GET  /answer/:id     → legge risposta per un exercise_id
 *   GET  /answers/recent → lista delle ultime 30 risposte (usata dal workflow)
 *   GET  /health         → ping
 */

const ALLOWED_ORIGIN = "https://adrianolionetti-arch.github.io";

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
    headers: {
      "Content-Type": "application/json",
      ...corsHeaders(origin),
    },
  });
}

function isValidExerciseId(id) {
  return typeof id === "string" && /^L\d+-E\d{2}$/.test(id);
}

function isValidAnswer(a) {
  return ["A", "B", "C", "D"].includes(a);
}

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

    if (request.method === "POST" && url.pathname === "/answer") {
      let payload;
      try {
        payload = await request.json();
      } catch {
        return json(400, { error: "Invalid JSON" }, origin);
      }

      const { exercise_id, answer } = payload;
      if (!isValidExerciseId(exercise_id)) {
        return json(400, { error: "Invalid exercise_id (expected like L1-E05)" }, origin);
      }
      if (!isValidAnswer(answer)) {
        return json(400, { error: "Invalid answer (expected A/B/C/D)" }, origin);
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
      const trimmed = recent.slice(0, 30);
      await env.QUIZ_KV.put("recent_answers", JSON.stringify(trimmed));

      return json(200, { ok: true, saved: record }, origin);
    }

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

    if (request.method === "GET" && url.pathname === "/answers/recent") {
      const stored = (await env.QUIZ_KV.get("recent_answers")) || "[]";
      return json(200, JSON.parse(stored), origin);
    }

    return json(404, { error: "Not found" }, origin);
  },
};
