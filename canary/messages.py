"""Formats alert message with mention/pings"""

from html import escape

from .timeutils import format_timestamp


def notification(config, incident, event, now):
    labels = {
        "opened": "ALERT",
        "resolved": "RECOVERED", "reminder": "REMINDER",
    }
    mention = event == "opened" and incident.kind in {"service", "disk"}
    title = f"Canary {labels[event]}: {incident.subject} ({incident.severity})"
    timestamp = format_timestamp(now)
    duration = max(0, int(now - incident.opened_at))
    body = (
        f"*{escape(title[:200], quote=False)}*\n"
        f"{escape(incident.detail[:1000], quote=False)}\n"
        f"Observed: {timestamp} | Incident duration: {duration // 60}m {duration % 60}s"
    )
    if mention:
        body = f"<!channel> {body}"
    return {
        "channel": config.channel_id,
        "text": body,
        "blocks": [{"type": "section", "text": {"type": "mrkdwn", "text": body}}],
        "unfurl_links": False,
        "unfurl_media": False,
    }
