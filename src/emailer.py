"""
Invia email di briefing con layout HTML che evidenzia
i segnali operativi con livelli di convinzione (GREEN/YELLOW/NONE).
Usa SMTP Gmail (gratis, richiede App Password).
"""
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

DASHBOARD_URL = os.environ.get("DASHBOARD_URL", "")

SIGNAL_STYLES = {
    "GREEN": {
        "emoji": "🟢",
        "label": "SEGNALE FORTE",
        "bg": "#e8f5e9",
        "border": "#2e7d32",
        "subject_prefix": "🟢 SEGNALE - ",
    },
    "YELLOW": {
        "emoji": "🟡",
        "label": "SPUNTO DA VALUTARE",
        "bg": "#fff8e1",
        "border": "#f9a825",
        "subject_prefix": "🟡 Spunto - ",
    },
    "NONE": {
        "emoji": "⚪",
        "label": "Nessun segnale",
        "bg": "#f5f7fa",
        "border": "#90a4ae",
        "subject_prefix": "📊 ",
    },
}


def _render_signal_box(b: dict) -> str:
    """Box HTML del segnale, in cima all'email."""
    level = b.get("signal_level", "NONE")
    style = SIGNAL_STYLES.get(level, SIGNAL_STYLES["NONE"])

    if level == "NONE":
        return f"""
        <div style="background:{style['bg']};padding:14px 18px;border-radius:8px;
                    margin:16px 0;border-left:4px solid {style['border']};">
            <div style="font-size:13px;color:#555;">
                {style['emoji']} {style['label']}: giornata tranquilla, nessuna azione suggerita.
            </div>
        </div>
        """

    asset = b.get("signal_asset") or ""
    action = b.get("signal_action") or ""
    reasoning = b.get("signal_reasoning") or ""
    counter = b.get("signal_counter") or ""
    amount = b.get("signal_suggested_amount_eur")
    amount_line = ""
    if amount:
        amount_line = f'<p style="margin:8px 0;"><strong>Importo suggerito:</strong> €{amount}</p>'

    return f"""
    <div style="background:{style['bg']};padding:18px;border-radius:8px;
                margin:16px 0;border-left:5px solid {style['border']};">
        <div style="font-size:13px;font-weight:bold;color:{style['border']};
                    text-transform:uppercase;letter-spacing:0.5px;">
            {style['emoji']} {style['label']}
        </div>
        <div style="font-size:18px;font-weight:bold;margin-top:8px;color:#1a1a2e;">
            {asset}: {action}
        </div>
        <div style="margin-top:12px;font-size:14px;line-height:1.5;">
            <p style="margin:8px 0;"><strong>Perché:</strong> {reasoning}</p>
            <p style="margin:8px 0;color:#b71c1c;"><strong>Attenzione:</strong> {counter}</p>
            {amount_line}
        </div>
    </div>
    """


def _render_dashboard_cta() -> str:
    """Pulsante CTA verso la dashboard. Vuoto se DASHBOARD_URL non e' configurata."""
    if not DASHBOARD_URL:
        return ""
    return f"""
    <div style="text-align:center;margin:24px 0;">
        <a href="{DASHBOARD_URL}" target="_blank"
           style="display:inline-block;background:#1a1a2e;color:#d4a574;
                  text-decoration:none;padding:14px 32px;border-radius:4px;
                  font-size:13px;font-weight:600;letter-spacing:0.08em;
                  text-transform:uppercase;
                  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',monospace;">
            Apri dashboard completa →
        </a>
    </div>
    """


def _render_pillola_box(b: dict) -> str:
    """Sezione pillola formativa nell'email (solo il lunedi)."""
    pillola = b.get("pillola_settimanale")
    if not pillola:
        return ""

    titolo = pillola.get("titolo", "")
    sottotitolo = pillola.get("sottotitolo", "")
    corpo = pillola.get("corpo", "").replace("\n\n", "</p><p style='margin:12px 0;'>")
    esercizio = pillola.get("esercizio", "").replace("\n", "<br>")
    riflessione = pillola.get("riflessione", "")
    numero = pillola.get("numero", "")

    return f"""
    <div style="background:#fefcf7;padding:24px;border-radius:8px;margin:32px 0;
                border:1px solid #e8d9b8;">
        <div style="font-size:11px;font-weight:600;color:#a08454;
                    text-transform:uppercase;letter-spacing:0.12em;margin-bottom:8px;">
            📚 Pillola della settimana #{numero}
        </div>
        <h3 style="margin:0;font-size:22px;color:#1a1a2e;font-weight:700;line-height:1.3;">
            {titolo}
        </h3>
        <p style="margin:4px 0 16px 0;font-size:14px;color:#888;font-style:italic;">
            {sottotitolo}
        </p>
        <div style="font-size:14px;line-height:1.65;color:#333;">
            <p style="margin:12px 0;">{corpo}</p>
        </div>
        <div style="background:#fff;padding:16px;border-radius:6px;margin-top:16px;
                    border-left:3px solid #a08454;">
            <div style="font-size:11px;font-weight:600;color:#a08454;
                        text-transform:uppercase;letter-spacing:0.1em;margin-bottom:6px;">
                Esercizio della settimana
            </div>
            <div style="font-size:14px;line-height:1.6;color:#333;">{esercizio}</div>
        </div>
        <div style="margin-top:14px;font-size:14px;color:#555;font-style:italic;">
            🤔 {riflessione}
        </div>
    </div>
    """


def send_email(briefing: dict, portfolio_data: dict) -> bool:
    """Invia email con briefing strutturato."""
    gmail_user = os.environ.get("GMAIL_USER")
    gmail_pass = os.environ.get("GMAIL_APP_PASSWORD")
    recipient = os.environ.get("RECIPIENT_EMAIL", gmail_user)

    if not gmail_user or not gmail_pass:
        print("[ERRORE] GMAIL_USER o GMAIL_APP_PASSWORD non configurati")
        return False

    today = datetime.now().strftime("%A %d %B %Y")
    level = briefing.get("signal_level", "NONE")
    style = SIGNAL_STYLES.get(level, SIGNAL_STYLES["NONE"])
    subject = f"{style['subject_prefix']}Briefing Fineco — {today}"

    holdings_rows = ""
    for h in portfolio_data.get("holdings", []):
        if "error" in h:
            continue
        color = "#2e7d32" if h.get("daily_change_pct", 0) >= 0 else "#c62828"
        holdings_rows += f"""
        <tr>
            <td style="padding:8px;border-bottom:1px solid #eee;">{h['name']}</td>
            <td style="padding:8px;border-bottom:1px solid #eee;">{h['current']} {h['currency']}</td>
            <td style="padding:8px;border-bottom:1px solid #eee;color:{color};font-weight:bold;">
                {h['daily_change_pct']:+.2f}%
            </td>
            <td style="padding:8px;border-bottom:1px solid #eee;">
                {h['weekly_change_pct']:+.2f}%
            </td>
            <td style="padding:8px;border-bottom:1px solid #eee;">
                {h['monthly_change_pct']:+.2f}%
            </td>
        </tr>
        """

    events_html = ""
    if briefing.get("events"):
        items = "".join(f"<li>{e}</li>" for e in briefing["events"])
        events_html = f"""
        <h3 style="margin-top:20px;">Eventi rilevanti</h3>
        <ul style="padding-left:20px;line-height:1.7;">{items}</ul>
        """

    error_banner = ""
    if briefing.get("error"):
        error_banner = f"""
        <div style="background:#ffebee;padding:10px;border-radius:4px;margin-bottom:12px;
                    color:#b71c1c;font-size:13px;">
            ⚠️ Errore AI: {briefing['error']}
        </div>
        """

    tokens_info = ""
    if briefing.get("_tokens"):
        t = briefing["_tokens"]
        tokens_info = f"Modello: {briefing.get('_model_used', 'n/a')} | Token in/out: {t['input']}/{t['output']}"

    html = f"""
    <html>
    <body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
                 max-width:620px;margin:0 auto;padding:20px;color:#222;">
        <h2 style="color:#1a1a2e;border-bottom:2px solid #1a1a2e;padding-bottom:8px;margin:0;">
            Briefing giornaliero
        </h2>
        <p style="color:#666;font-size:14px;margin:4px 0 0 0;">{today}</p>

        {error_banner}

        <p style="font-size:15px;margin-top:16px;">
            <strong>{briefing.get('summary', '')}</strong>
        </p>

        <p style="font-size:14px;color:#444;">{briefing.get('portfolio_note', '')}</p>

        {_render_signal_box(briefing)}

        {_render_dashboard_cta()}

        {events_html}

        <h3 style="margin-top:24px;">Portafoglio</h3>
        <p style="color:#666;margin:4px 0;">Valore approssimativo:
            <strong>€{portfolio_data.get('total_value_eur_approx', 0):.2f}</strong>
        </p>
        <table style="width:100%;border-collapse:collapse;font-size:13px;">
            <thead>
                <tr style="background:#f5f7fa;">
                    <th style="padding:8px;text-align:left;border-bottom:2px solid #ddd;">Asset</th>
                    <th style="padding:8px;text-align:left;border-bottom:2px solid #ddd;">Prezzo</th>
                    <th style="padding:8px;text-align:left;border-bottom:2px solid #ddd;">Oggi</th>
                    <th style="padding:8px;text-align:left;border-bottom:2px solid #ddd;">7g</th>
                    <th style="padding:8px;text-align:left;border-bottom:2px solid #ddd;">30g</th>
                </tr>
            </thead>
            <tbody>{holdings_rows}</tbody>
        </table>

        {_render_pillola_box(briefing)}

        <p style="margin-top:24px;font-size:13px;color:#555;font-style:italic;">
            {briefing.get('closing_note', '')}
        </p>

        <p style="margin-top:32px;font-size:11px;color:#999;border-top:1px solid #eee;padding-top:12px;">
            Briefing generato automaticamente. I segnali sono ragionamento AI su dati pubblici,
            non hanno edge predittivo garantito. Le decisioni di investimento sono tue responsabilità.
            <br>{tokens_info}
        </p>
    </body>
    </html>
    """

    plain = f"""{subject}

{briefing.get('summary', '')}

{briefing.get('portfolio_note', '')}

Segnale: {level}
"""
    if level != "NONE":
        plain += f"""
Asset: {briefing.get('signal_asset')}
Azione: {briefing.get('signal_action')}
Perché: {briefing.get('signal_reasoning')}
Attenzione: {briefing.get('signal_counter')}
"""
    if DASHBOARD_URL:
        plain += f"\nDashboard completa: {DASHBOARD_URL}\n"
    if briefing.get("pillola_settimanale"):
        p = briefing["pillola_settimanale"]
        plain += f"\n--- Pillola #{p.get('numero')}: {p.get('titolo')} ---\n{p.get('sottotitolo')}\n(apri in HTML per leggere il testo completo)\n"
    plain += f"\n{briefing.get('closing_note', '')}"

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
        print(f"  → Email inviata a {recipient}")
        return True
    except Exception as e:
        print(f"[ERRORE SMTP] {e}")
        return False
