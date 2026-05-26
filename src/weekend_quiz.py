"""
Quiz weekend: sabato manda email con la domanda dell'esercizio,
domenica manda l'email di soluzione e aggiorna learning_progress.json.

Le risposte dell'utente vengono raccolte dal Cloudflare Worker
(fineco-quiz.adriano-lionetti.workers.dev), che le salva in KV.
Lo script della domenica le legge da lì per generare il feedback.

Uso:
  python src/weekend_quiz.py --mode saturday
  python src/weekend_quiz.py --mode sunday

Variabili d'ambiente richieste:
  GMAIL_USER, GMAIL_APP_PASSWORD, RECIPIENT_EMAIL
  DASHBOARD_URL (es. https://adrianolionetti-arch.github.io/fineco-agent/)
  QUIZ_WORKER_URL (es. https://fineco-quiz.adriano-lionetti.workers.dev)
  QUIZ_TOKEN (token di autenticazione del Worker)
"""

import argparse
import json
import os
import smtplib
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PROGRESS_FILE = REPO_ROOT / "data" / "learning_progress.json"
EXERCISES_FILE = REPO_ROOT / "esercizi" / "livello_1_basi.json"
EXERCISES_MD = REPO_ROOT / "esercizi" / "livello_1_basi.md"

POINTS_CORRECT = 10
POINTS_STREAK_BONUS = 15
STREAK_BONUS_THRESHOLD = 5
POINTS_LEVEL_COMPLETION = 50

BADGE_THRESHOLDS = [
    (500, "🦉 Saggio della finanza"),
    (300, "🎯 Trader razionale"),
    (150, "📈 Investitore informato"),
    (50, "📘 Risparmiatore consapevole"),
    (0, "🌱 Apprendista"),
]


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data: dict) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def badge_for_points(points: int) -> str:
    for threshold, name in BADGE_THRESHOLDS:
        if points >= threshold:
            return name
    return BADGE_THRESHOLDS[-1][1]


def next_exercise(progress: dict, exercises: list) -> dict | None:
    """Trova il prossimo esercizio non ancora inviato."""
    sent_ids = {h["exercise_id"] for h in progress.get("history", [])}
    last_sent = progress.get("last_exercise_sent")
    if last_sent:
        sent_ids.add(last_sent)
    for ex in exercises:
        if ex["id"] not in sent_ids:
            return ex
    return None


def parse_solution_block(exercise_id: str) -> dict:
    """Estrae la spiegazione completa dal file markdown per l'email di soluzione.
    Cerca la sezione `## {exercise_id} — ...` e ne ricava lezione operativa e spiegazioni."""
    if not EXERCISES_MD.exists():
        return {}

    text = EXERCISES_MD.read_text(encoding="utf-8")
    # Trova la sezione dell'esercizio
    marker = f"## {exercise_id}"
    start = text.find(marker)
    if start == -1:
        return {}
    # Fine: prossimo "## L" o "## Tracking" o fine file
    rest = text[start + len(marker):]
    next_section = rest.find("\n## ")
    section = rest[:next_section] if next_section != -1 else rest

    # Estrazione semplice: tutto ciò che sta dopo "**Spiegazione**:" diventa il blocco da mostrare
    explanation_marker = "**Spiegazione**:"
    lesson_marker = "**Lezione operativa**:"
    expl = ""
    lesson = ""
    if explanation_marker in section:
        after_expl = section.split(explanation_marker, 1)[1]
        if lesson_marker in after_expl:
            expl, lesson_block = after_expl.split(lesson_marker, 1)
            lesson = lesson_block.strip().split("\n---")[0].strip()
        else:
            expl = after_expl.strip().split("\n---")[0].strip()
    return {"explanation": expl.strip(), "lesson": lesson.strip()}


def build_progress_widget(progress: dict) -> str:
    """HTML inline del widget statistiche per le email."""
    stats = progress.get("stats", {})
    points = stats.get("total_points", 0)
    streak = stats.get("current_streak", 0)
    attempted = stats.get("exercises_attempted", 0)
    badge = badge_for_points(points)
    streak_html = f"🔥 {streak}" if streak else "—"
    return f"""
    <table cellpadding="0" cellspacing="0" border="0" width="100%"
           style="margin:18px 0;background:#f7f5fb;border-radius:8px;padding:14px;">
        <tr>
            <td style="text-align:center;padding:6px;font-family:'JetBrains Mono',monospace;">
                <div style="font-size:22px;font-weight:600;color:#1a1a2e;">{points}</div>
                <div style="font-size:10px;text-transform:uppercase;letter-spacing:0.08em;color:#666;margin-top:4px;">Punti</div>
            </td>
            <td style="text-align:center;padding:6px;">
                <div style="font-size:22px;font-weight:600;color:#1a1a2e;">{streak_html}</div>
                <div style="font-size:10px;text-transform:uppercase;letter-spacing:0.08em;color:#666;margin-top:4px;">Streak</div>
            </td>
            <td style="text-align:center;padding:6px;font-family:'JetBrains Mono',monospace;">
                <div style="font-size:22px;font-weight:600;color:#1a1a2e;">{attempted}/15</div>
                <div style="font-size:10px;text-transform:uppercase;letter-spacing:0.08em;color:#666;margin-top:4px;">Progresso L1</div>
            </td>
            <td style="text-align:center;padding:6px;">
                <div style="font-size:14px;font-weight:600;color:#1a1a2e;">{badge}</div>
                <div style="font-size:10px;text-transform:uppercase;letter-spacing:0.08em;color:#666;margin-top:4px;">Badge</div>
            </td>
        </tr>
    </table>
    """


def send_email(subject: str, html: str, plain: str) -> bool:
    """Invio SMTP Gmail riusando i secrets del briefing quotidiano."""
    if os.environ.get("SKIP_EMAIL"):
        print(f"  → Email saltata (SKIP_EMAIL): {subject}")
        return True

    gmail_user = os.environ.get("GMAIL_USER")
    gmail_pass = os.environ.get("GMAIL_APP_PASSWORD")
    recipient = os.environ.get("RECIPIENT_EMAIL", gmail_user)
    if not gmail_user or not gmail_pass:
        print("[ERRORE] GMAIL_USER / GMAIL_APP_PASSWORD mancanti")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = gmail_user
    msg["To"] = recipient
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(gmail_user, gmail_pass)
            server.send_message(msg)
        print(f"  → Email inviata a {recipient}: {subject}")
        return True
    except Exception as e:
        print(f"[ERRORE SMTP] {e}")
        return False


def worker_get(path: str) -> dict | None:
    base = os.environ.get("QUIZ_WORKER_URL", "").rstrip("/")
    token = os.environ.get("QUIZ_TOKEN", "")
    if not base:
        print("[ERRORE] QUIZ_WORKER_URL non configurato")
        return None
    req = urllib.request.Request(
        base + path,
        headers={
            "X-Quiz-Token": token,
            "User-Agent": "fineco-agent-weekend-quiz/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        print(f"[ERRORE Worker GET {path}] HTTP {e.code}")
        return None
    except Exception as e:
        print(f"[ERRORE Worker GET {path}] {e}")
        return None


def run_saturday() -> int:
    progress = load_json(PROGRESS_FILE)
    curriculum = load_json(EXERCISES_FILE)
    exercises = curriculum.get("exercises", [])

    ex = next_exercise(progress, exercises)
    if not ex:
        print("Nessun esercizio rimanente nel Livello 1. Tracking aggiornato.")
        return 0

    dashboard_url = os.environ.get("DASHBOARD_URL", "").rstrip("/")
    quiz_link = f"{dashboard_url}/?ex={ex['id']}#pillole" if dashboard_url else ""

    options_html = ""
    for letter in ["A", "B", "C", "D"]:
        options_html += f"""
        <tr><td style="padding:8px 0;font-size:14px;line-height:1.5;color:#333;">
            <span style="display:inline-block;width:24px;height:24px;border-radius:50%;
                         background:#e8e2f5;color:#5a3d8a;text-align:center;line-height:24px;
                         font-weight:600;font-family:'JetBrains Mono',monospace;font-size:12px;margin-right:10px;">{letter}</span>
            {ex['options'][letter]}
        </td></tr>
        """

    progress_widget = build_progress_widget(progress)
    today = datetime.now().strftime("%A %d %B")

    html = f"""
    <html><body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
                       max-width:620px;margin:0 auto;padding:20px;color:#222;">
        <div style="font-size:11px;text-transform:uppercase;letter-spacing:0.12em;color:#8a6db0;font-weight:600;">
            🎓 Esercizio del weekend · Livello 1 · {ex['id']}
        </div>
        <h2 style="color:#1a1a2e;margin:6px 0 4px;font-size:22px;">{ex['topic']}</h2>
        <p style="color:#666;font-size:13px;margin:0 0 16px;">{today} — mercati chiusi, si studia</p>

        <div style="background:#fafafa;padding:20px;border-radius:10px;border-left:4px solid #b890d4;margin:16px 0;">
            <div style="font-size:11px;text-transform:uppercase;letter-spacing:0.1em;color:#8a6db0;font-weight:600;margin-bottom:10px;">
                Domanda
            </div>
            <div style="font-size:16px;line-height:1.5;color:#1a1a2e;font-family:Georgia,serif;">
                {ex['question']}
            </div>
        </div>

        <table cellpadding="0" cellspacing="0" border="0" width="100%" style="margin:16px 0;">
            {options_html}
        </table>

        <div style="text-align:center;margin:28px 0;">
            <a href="{quiz_link}" style="display:inline-block;background:#1a1a2e;color:#d4a574;
                                       text-decoration:none;padding:14px 32px;border-radius:6px;
                                       font-size:13px;font-weight:600;letter-spacing:0.08em;
                                       text-transform:uppercase;">
                🎯 Rispondi sulla dashboard →
            </a>
        </div>

        <p style="font-size:13px;color:#666;text-align:center;line-height:1.5;">
            1 click sul bottone, scegli l'opzione e clicca "Risposta registrata".<br>
            La soluzione completa arriva domani mattina via email.
        </p>

        {progress_widget}

        <p style="margin-top:32px;font-size:11px;color:#999;border-top:1px solid #eee;padding-top:12px;">
            Tempo medio: 30 secondi. Pensaci prima di rispondere.
        </p>
    </body></html>
    """

    options_plain = "\n".join(f"  {L}) {ex['options'][L]}" for L in ["A","B","C","D"])
    plain = f"""Esercizio del weekend — {ex['id']} ({ex['topic']})

{ex['question']}

{options_plain}

Rispondi sulla dashboard:
{quiz_link}

La soluzione arriva domani mattina.
"""

    subject = f"🎓 Esercizio del weekend — {ex['id']} ({ex['topic']})"
    if not send_email(subject, html, plain):
        return 1

    # Aggiorna lo stato: registra che L'esercizio è stato inviato
    now = datetime.now(timezone.utc).isoformat()
    progress["last_exercise_sent"] = ex["id"]
    progress["last_exercise_date"] = now
    progress["last_updated"] = now
    save_json(PROGRESS_FILE, progress)
    print(f"  → Stato aggiornato: last_exercise_sent={ex['id']}")
    return 0


def run_sunday() -> int:
    progress = load_json(PROGRESS_FILE)
    curriculum = load_json(EXERCISES_FILE)
    exercises_by_id = {e["id"]: e for e in curriculum.get("exercises", [])}

    last_id = progress.get("last_exercise_sent")
    if not last_id:
        print("Nessun esercizio in attesa di feedback. Skip.")
        return 0

    # Evita di mandare la stessa soluzione due volte
    history_ids = {h["exercise_id"] for h in progress.get("history", [])}
    if last_id in history_ids:
        print(f"Esercizio {last_id} già nello storico. Skip.")
        return 0

    ex = exercises_by_id.get(last_id)
    if not ex:
        print(f"[ERRORE] Esercizio {last_id} non trovato nel curriculum.")
        return 1

    answered = worker_get(f"/answer/{last_id}")
    user_answer = answered.get("answer") if answered else None
    answered_at = answered.get("answered_at") if answered else None
    correct = ex["correct"]
    is_correct = user_answer == correct

    # Calcolo punti + streak
    stats = progress.get("stats", {})
    points_earned = 0
    streak_bonus = 0
    if user_answer is None:
        stats["exercises_missed"] = stats.get("exercises_missed", 0) + 1
        stats["current_streak"] = 0
    else:
        stats["exercises_attempted"] = stats.get("exercises_attempted", 0) + 1
        if is_correct:
            points_earned = POINTS_CORRECT
            stats["exercises_correct"] = stats.get("exercises_correct", 0) + 1
            new_streak = stats.get("current_streak", 0) + 1
            stats["current_streak"] = new_streak
            stats["longest_streak"] = max(stats.get("longest_streak", 0), new_streak)
            if new_streak > 0 and new_streak % STREAK_BONUS_THRESHOLD == 0:
                streak_bonus = POINTS_STREAK_BONUS
        else:
            stats["current_streak"] = 0

    # Bonus completamento livello (15/15 attempted)
    level_bonus = 0
    if stats.get("exercises_attempted", 0) >= 15 and user_answer is not None:
        already_bonus = "level_1_completion" in (progress.get("badges_earned") or [])
        if not already_bonus:
            level_bonus = POINTS_LEVEL_COMPLETION
            progress.setdefault("badges_earned", []).append("level_1_completion")

    total_added = points_earned + streak_bonus + level_bonus
    stats["total_points"] = stats.get("total_points", 0) + total_added
    progress["stats"] = stats

    # Aggiungi entry allo storico
    entry = {
        "exercise_id": last_id,
        "topic": ex["topic"],
        "sent_at": progress.get("last_exercise_date"),
        "answered_at": answered_at,
        "user_answer": user_answer,
        "correct_answer": correct,
        "is_correct": is_correct if user_answer else None,
        "points_earned": points_earned,
        "streak_bonus": streak_bonus,
        "level_completion_bonus": level_bonus,
    }
    progress.setdefault("history", []).append(entry)
    progress["last_updated"] = datetime.now(timezone.utc).isoformat()

    # Email di soluzione
    solution = parse_solution_block(last_id)
    explanation_html = (solution.get("explanation", "") or "Spiegazione non disponibile.").replace("\n", "<br>")
    lesson_html = (solution.get("lesson", "") or "").replace("\n", "<br>")

    # Banner di esito
    if user_answer is None:
        banner_color, banner_bg, banner_text = "#90a4ae", "#f5f7fa", "— Non hai risposto. La streak è stata interrotta, ma la spiegazione è qui sotto."
    elif is_correct:
        banner_color, banner_bg, banner_text = "#2e7d32", "#e8f5e9", f"✅ Hai risposto {user_answer} — CORRETTA! (+{points_earned} punti)"
    else:
        banner_color, banner_bg, banner_text = "#c62828", "#ffebee", f"❌ Hai risposto {user_answer}, la risposta corretta era {correct}."

    bonus_lines = []
    if streak_bonus:
        bonus_lines.append(f"🔥 Bonus streak (+{streak_bonus})")
    if level_bonus:
        bonus_lines.append(f"🏆 Bonus completamento Livello 1 (+{level_bonus})")
    bonus_html = "<br>".join(bonus_lines)
    if bonus_html:
        bonus_html = f'<div style="margin-top:8px;font-size:13px;color:{banner_color};">{bonus_html}</div>'

    progress_widget = build_progress_widget(progress)
    dashboard_url = os.environ.get("DASHBOARD_URL", "").rstrip("/")
    dashboard_link = f'<a href="{dashboard_url}" style="color:#d4a574;">Apri dashboard →</a>' if dashboard_url else ""

    html = f"""
    <html><body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
                       max-width:620px;margin:0 auto;padding:20px;color:#222;">
        <div style="font-size:11px;text-transform:uppercase;letter-spacing:0.12em;color:#8a6db0;font-weight:600;">
            ✅ Soluzione · {ex['id']} · {ex['topic']}
        </div>
        <h2 style="color:#1a1a2e;margin:6px 0 16px;font-size:22px;">{ex['question']}</h2>

        <div style="background:{banner_bg};padding:14px 18px;border-radius:8px;border-left:4px solid {banner_color};margin:16px 0;">
            <div style="font-size:15px;font-weight:600;color:{banner_color};">{banner_text}</div>
            {bonus_html}
        </div>

        <div style="margin:24px 0;">
            <div style="font-size:11px;text-transform:uppercase;letter-spacing:0.1em;color:#8a6db0;font-weight:600;margin-bottom:8px;">
                💡 Spiegazione
            </div>
            <div style="font-size:14px;line-height:1.7;color:#333;">{explanation_html}</div>
        </div>

        {f'<div style="background:#fffbf0;padding:14px 18px;border-radius:8px;border-left:3px solid #d4a574;margin:24px 0;"><div style="font-size:11px;text-transform:uppercase;letter-spacing:0.1em;color:#a08454;font-weight:600;margin-bottom:6px;">🎯 Lezione operativa</div><div style="font-size:14px;line-height:1.6;color:#333;">{lesson_html}</div></div>' if lesson_html else ''}

        {progress_widget}

        <p style="text-align:center;margin-top:24px;font-size:13px;color:#666;">
            Prossimo esercizio: <strong>sabato prossimo</strong>.<br>{dashboard_link}
        </p>

        <p style="margin-top:32px;font-size:11px;color:#999;border-top:1px solid #eee;padding-top:12px;">
            Lezione operativa di oggi: l'errore non costa nulla in punti, ma la lettura della spiegazione conta più della risposta giusta a caso.
        </p>
    </body></html>
    """

    plain = f"""Soluzione {last_id} — {ex['topic']}

{banner_text}

Risposta corretta: {correct}

Spiegazione:
{(solution.get('explanation') or '').strip()}

Lezione operativa:
{(solution.get('lesson') or '').strip()}

Punti totali: {stats.get('total_points', 0)}
Streak: {stats.get('current_streak', 0)}
"""

    subject = f"✅ Soluzione {last_id} — {'Corretta!' if is_correct else ('Non hai risposto' if user_answer is None else 'Non corretta')}"
    if not send_email(subject, html, plain):
        return 1

    save_json(PROGRESS_FILE, progress)
    print(f"  → Storico aggiornato. Punti totali: {stats.get('total_points', 0)}")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Quiz weekend (saturday/sunday)")
    parser.add_argument("--mode", choices=["saturday", "sunday"], required=True)
    args = parser.parse_args()

    if args.mode == "saturday":
        sys.exit(run_saturday())
    else:
        sys.exit(run_sunday())


if __name__ == "__main__":
    main()
