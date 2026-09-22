"""
Recupero degli esercizi rimasti senza risposta.

PERCHE' ESISTE
--------------
Il quiz del weekend si e' fermato il 6 settembre 2026 perche' il Livello 1 e'
finito: 15 esercizi inviati, 15/15. Ma il problema vero e' arrivato prima. Dal
1 agosto in poi Adriano non ha piu' risposto a nessun esercizio: sette sono
rimasti in sospeso (E02, E10, E11, E12, E13, E14, E15), non per disinteresse
ma perche' l'email del sabato passava inosservata.

Mandare una SECONDA email dedicata avrebbe avuto la stessa sorte. Il briefing
quotidiano invece viene aperto ogni mattina: e' li' che va messo il recupero.
Un esercizio pendente al giorno, a rotazione, finche' non ricevono risposta.

COME SI CHIUDE IL CERCHIO
-------------------------
Le risposte arrivano sulla dashboard e finiscono nel KV del Worker Cloudflare.
run_sunday() legge il KV solo per l'ULTIMO esercizio inviato, quindi non vedrebbe
mai una risposta data in ritardo a un esercizio vecchio. reconcile() qui sotto
interroga il Worker per TUTTI i pendenti e aggiorna lo storico.
"""
import os
from datetime import datetime, timezone

from weekend_quiz import (
    EXERCISES_FILE,
    POINTS_CORRECT,
    POINTS_LEVEL_COMPLETION,
    PROGRESS_FILE,
    load_json,
    save_json,
    worker_get,
)


def _exercises_by_id() -> dict:
    return {e["id"]: e for e in load_json(EXERCISES_FILE).get("exercises", [])}


def pending_entries(progress: dict) -> list:
    """Esercizi inviati ma mai risposti, dal piu' vecchio."""
    return [h for h in progress.get("history", [])
            if h.get("answered_at") is None and h.get("user_answer") is None]


def reconcile(progress: dict, verbose: bool = True) -> list:
    """
    Chiede al Worker se nel frattempo e' arrivata una risposta per ciascun
    esercizio pendente e, in caso, aggiorna storico, punti e statistiche.
    Restituisce la lista degli id recuperati.
    """
    if not os.environ.get("QUIZ_WORKER_URL"):
        # Senza Worker non si possono leggere le risposte: si mostra comunque
        # l'esercizio arretrato, semplicemente non se ne riconcilia l'esito.
        return []

    by_id = _exercises_by_id()
    recovered = []

    for entry in pending_entries(progress):
        ex_id = entry["exercise_id"]
        ex = by_id.get(ex_id)
        if not ex:
            continue

        answered = worker_get(f"/answer/{ex_id}")
        if not answered or not answered.get("answer"):
            continue

        user_answer = answered["answer"]
        is_correct = user_answer == ex["correct"]

        entry["user_answer"] = user_answer
        entry["answered_at"] = answered.get("answered_at")
        entry["is_correct"] = is_correct
        entry["recovered"] = True      # risposto in ritardo, fuori dal ciclo weekend

        stats = progress.setdefault("stats", {})
        stats["exercises_attempted"] = stats.get("exercises_attempted", 0) + 1
        stats["exercises_missed"] = max(0, stats.get("exercises_missed", 0) - 1)

        # Punti pieni sulla risposta corretta: l'obiettivo e' che risponda.
        # Nessun bonus streak pero': la streak premia la costanza settimanale,
        # e un recupero in ritardo non e' costanza.
        if is_correct:
            entry["points_earned"] = POINTS_CORRECT
            stats["exercises_correct"] = stats.get("exercises_correct", 0) + 1
            stats["total_points"] = stats.get("total_points", 0) + POINTS_CORRECT

        # Bonus completamento livello, stessa regola di run_sunday()
        if stats.get("exercises_attempted", 0) >= 15:
            if "level_1_completion" not in (progress.get("badges_earned") or []):
                progress.setdefault("badges_earned", []).append("level_1_completion")
                stats["total_points"] = stats.get("total_points", 0) + POINTS_LEVEL_COMPLETION
                entry["level_completion_bonus"] = POINTS_LEVEL_COMPLETION
                if verbose:
                    print(f"  → Livello 1 completato: +{POINTS_LEVEL_COMPLETION} punti")

        recovered.append(ex_id)
        if verbose:
            esito = "corretta" if is_correct else f"sbagliata (era {ex['correct']})"
            print(f"  → Recuperato {ex_id}: risposta {user_answer}, {esito}")

    if recovered:
        progress["last_updated"] = datetime.now(timezone.utc).isoformat()
    return recovered


def pick_for_today(progress: dict) -> dict | None:
    """
    Sceglie l'esercizio pendente da riproporre oggi, a rotazione: insistere
    sempre sullo stesso finirebbe per bruciarlo. Con 7 pendenti, in una
    settimana li vede tutti.
    """
    pend = pending_entries(progress)
    if not pend:
        return None
    by_id = _exercises_by_id()
    idx = datetime.now().timetuple().tm_yday % len(pend)
    return by_id.get(pend[idx]["exercise_id"])


def render_html(ex: dict, progress: dict) -> str:
    """Box da innestare nell'email del briefing quotidiano."""
    if not ex:
        return ""

    dashboard_url = os.environ.get("DASHBOARD_URL", "").rstrip("/")
    link = f"{dashboard_url}/?ex={ex['id']}#pillole" if dashboard_url else ""
    arretrati = len(pending_entries(progress))
    punti = progress.get("stats", {}).get("total_points", 0)

    opzioni = "".join(
        f"""<tr><td style="padding:6px 0;font-size:13px;line-height:1.45;color:#333;">
            <span style="display:inline-block;width:20px;height:20px;border-radius:50%;
                         background:#e8e2f5;color:#5a3d8a;text-align:center;line-height:20px;
                         font-weight:600;font-size:11px;margin-right:8px;">{L}</span>{ex['options'][L]}
        </td></tr>"""
        for L in ("A", "B", "C", "D")
    )

    coda = ("" if arretrati <= 1 else
            f"<br>Ne hai {arretrati} in sospeso: te ne ripropongo uno al giorno.")

    return f"""
    <div style="background:#faf8fd;padding:18px 20px;border-radius:10px;
                border-left:4px solid #b890d4;margin:20px 0;">
        <div style="font-size:11px;text-transform:uppercase;letter-spacing:0.1em;
                    color:#8a6db0;font-weight:600;margin-bottom:8px;">
            🎓 Esercizio da recuperare · {ex['id']}
        </div>
        <div style="font-size:15px;font-weight:600;color:#1a1a2e;margin-bottom:8px;">
            {ex['topic']}
        </div>
        <div style="font-size:14px;line-height:1.5;color:#1a1a2e;
                    font-family:Georgia,serif;margin-bottom:10px;">
            {ex['question']}
        </div>
        <table cellpadding="0" cellspacing="0" border="0" width="100%">{opzioni}</table>
        <div style="text-align:center;margin:16px 0 6px;">
            <a href="{link}" style="display:inline-block;background:#1a1a2e;color:#d4a574;
                                    text-decoration:none;padding:11px 26px;border-radius:6px;
                                    font-size:12px;font-weight:600;letter-spacing:0.06em;
                                    text-transform:uppercase;">
                Rispondi in 30 secondi →
            </a>
        </div>
        <div style="font-size:11px;color:#888;text-align:center;line-height:1.5;">
            {punti} punti finora.{coda}
        </div>
    </div>
    """


def run(progress_path=None) -> tuple:
    """
    Entrypoint usato dal briefing quotidiano.
    Restituisce (html_del_box, id_recuperati). Non solleva mai: se il Worker
    non risponde o il file di progresso manca, il briefing deve partire lo stesso.
    """
    try:
        progress = load_json(progress_path or PROGRESS_FILE)
        if not progress:
            return "", []
        recovered = reconcile(progress)
        ex = pick_for_today(progress)
        if recovered:
            save_json(progress_path or PROGRESS_FILE, progress)
        return render_html(ex, progress), recovered
    except Exception as e:
        print(f"  [quiz_recap] saltato: {type(e).__name__}: {e}")
        return "", []
