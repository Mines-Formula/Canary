"""Formats alert message with mention/pings"""

from html import escape

from .timeutils import format_timestamp

EVENT_STYLES = {
    "opened": ("ALERT", ":rotating_light:"),
    "resolved": ("RECOVERED", ":white_check_mark:"),
    "reminder": ("REMINDER", ":hourglass_flowing_sand:"),
}

HEADER_LIMIT = 150
SECTION_LIMIT = 3000
FIELD_LIMIT = 2000
FIELD_COUNT_LIMIT = 10


def rich_ts(ts, fmt="{date_short_pretty} at {time}"):
    fallback = escape(format_timestamp(ts), quote=False).replace("|", "-")
    return f"<!date^{int(ts)}^{fmt}|{fallback}>"


def fmt_duration(now, opened_at):
    elapsed = max(0, int(now - opened_at))
    return f"{elapsed // 60}m {elapsed % 60:02d}s"


def notification(config, incident, event, now):
    label, emoji = EVENT_STYLES[event]
    mention = event == "opened" and incident.kind in {"service", "disk"}
    prefix = "<!channel> " if mention else ""

    subject = escape(incident.subject, quote=False)
    severity = escape(incident.severity, quote=False)
    kind = escape(incident.kind, quote=False)

    context = f":clock3: Opened {rich_ts(incident.opened_at)}"
    incident_id = getattr(incident, "id", None)
    if incident_id is not None:
        context += f" · incident `{escape(str(incident_id), quote=False)}`"

    fields = [
        f"*Severity*\n{severity}",
        f"*Kind*\n{kind}",
        f"*Observed*\n{rich_ts(now)}",
        f"*Duration*\n{fmt_duration(now, incident.opened_at)}",
    ]

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"{emoji} Canary {label}: {incident.subject}"[:HEADER_LIMIT],
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"{prefix}{escape(incident.detail[:1000], quote=False)}"[:SECTION_LIMIT],
            },
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": field[:FIELD_LIMIT]}
                for field in fields[:FIELD_COUNT_LIMIT]
            ],
        },
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": context}],
        },
    ]

    return {
        "channel": config.channel_id,
        "text": (
            f"{prefix}Canary {label}: {subject} ({severity})"
            f" — observed {rich_ts(now)}"
        ),
        "blocks": blocks,
        "unfurl_links": False,
        "unfurl_media": False,
    }
