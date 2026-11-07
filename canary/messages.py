"""Formats alert message with mention/pings"""

import hashlib
from html import escape

from .timeutils import format_timestamp

EVENT_STYLES = {
    "opened": ("ALERT", ":warning:"),
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


def short_id(key):
    """Stable per incident and across restarts; the key is already unique."""
    return f"inc-{hashlib.blake2s(key.encode(), digest_size=2).hexdigest()}"


def headline(config, incident):
    """A bare mount or coverage subject doesn't say which host it belongs to."""
    if incident.kind == "disk":
        return f"disk {incident.subject} on {config.host_service}"
    if incident.kind == "coverage":
        return f"{incident.subject} on {config.host_service}"
    return incident.subject


def notification(config, incident, event, now):
    label, emoji = EVENT_STYLES[event]
    mention = event == "opened" and incident.kind in {"service", "disk"}
    prefix = "<!channel> " if mention else ""

    title = escape(headline(config, incident), quote=False)
    severity = escape(incident.severity, quote=False)
    kind = escape(incident.kind, quote=False)

    context = (
        f":clock3: Opened {rich_ts(incident.opened_at)}"
        f" · incident `{short_id(incident.key)}`"
    )

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
                "text": f"{emoji} Canary {label}: {headline(config, incident)}"[:HEADER_LIMIT],
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
            f"{prefix}Canary {label}: {title} ({severity})"
            f" — observed {rich_ts(now)}"
        ),
        "blocks": blocks,
        "unfurl_links": False,
        "unfurl_media": False,
    }
