from fastapi import Depends, FastAPI, HTTPException, Security, status
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
from datetime import datetime, timezone
from os import getenv
import re
import time
from zoneinfo import ZoneInfo

from canary.messages import FIELD_COUNT_LIMIT, FIELD_LIMIT, HEADER_LIMIT, SECTION_LIMIT, rich_ts
from canary.storage import Store

API_KEY = getenv("API_KEY")
assert API_KEY, "API_KEY is required and not set!"

app = FastAPI()

heartbeats = {}
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


GIB = 1024**3
DENVER = ZoneInfo("America/Denver")


class Heartbeat(BaseModel):
    service: str
    status: str = "ok"
    message: dict | str | None = None


def format_specs(message: str | dict | None) -> dict | None:
    """Turn the emitter's raw host metrics into readable numbers."""
    if not isinstance(message, dict):
        return None

    specs = {}

    if disks := message.get("disks"):
        specs["disks"] = {
            mount: {
                "total_gb": round(total / GIB, 1),
                "used_gb": round(used / GIB, 1),
                "free_gb": round(free / GIB, 1),
                "percent_used": round(used / total * 100, 1) if total else 0.0,
            }
            for mount, (total, used, free) in disks.items()
        }

    if memory := message.get("memory"):
        total, used, available = memory
        specs["memory"] = {
            "total_gb": round(total / GIB, 1),
            "used_gb": round(used / GIB, 1),
            "available_gb": round(available / GIB, 1),
            "percent_used": round(used / total * 100, 1) if total else 0.0,
        }

    if load := message.get("load"):
        specs["load"] = [round(avg, 2) for avg in load]

    if boot_time := message.get("boot_time"):
        now = datetime.now(timezone.utc)
        specs["boot_time"] = datetime.fromtimestamp(boot_time, DENVER).isoformat()
        specs["uptime_hours"] = round((now.timestamp() - boot_time) / 3600, 1)

    return specs or None


def verify_api_key(api_key: str | None = Security(api_key_header)) -> None:
    if api_key is None or api_key != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )


@app.post("/heartbeat", dependencies=[Depends(verify_api_key)])
def heartbeat(hb: Heartbeat):
    heartbeats[hb.service] = {
        "last_seen": datetime.now(timezone.utc),
        "status": hb.status,
        "message": hb.message,
    }

    return {"received": True}


@app.post("/{topic}", dependencies=[Depends(verify_api_key)])
async def publish(
    topic: str,
    request: Request,
    title: str | None = Header(None),
    tags: str | None = Header(None),
    fields: str | None = Header(None),
):
    """ntfy-style publish: the raw body is queued for Canary's Slack sender.

    Laid out like Canary's own alerts (canary/messages.py). Optional headers:
    Title, Tags (first tag is the header emoji, as in ntfy) and
    Fields ("Host=fsaelinux, Exit=1") for the two-column grid.
    """
    body = (await request.body()).decode(errors="replace").strip()

    if not body:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Empty message")
    
    if not SLACK_CHANNEL_ID:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "SLACK_CHANNEL_ID is not set")
    
    # Escaping keeps publishers from injecting <!channel> pings or links.
    heading = escape(f"[{topic}] {title}" if title else f"[{topic}]", quote=False)
    now = time.time()

    emoji = re.sub(r"[^a-z0-9_+-]", "", (tags or "").split(",")[0].lower())
    pairs = [pair.split("=", 1) for pair in (fields or "").split(",") if "=" in pair]
    grid = [
        {"type": "mrkdwn", "text": f"*{escape(key.strip(), quote=False)}*\n{escape(value.strip(), quote=False)}"[:FIELD_LIMIT]}
        for key, value in pairs
        if key.strip() and value.strip()
    ][:FIELD_COUNT_LIMIT]
    safe_topic = escape(topic, quote=False).replace("`", "'")

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"{f':{emoji}: ' if emoji else ''}{title or topic}"[:HEADER_LIMIT],
            },
        },
        {"type": "section", "text": {"type": "mrkdwn", "text": body[:SECTION_LIMIT]}},
        *([{"type": "section", "fields": grid}] if grid else []),
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f":clock3: Received {rich_ts(now)} · topic `{safe_topic}`"}],
        },
    ]

    payload = {
        "channel": SLACK_CHANNEL_ID,
        "text": f"*{heading}*\n{body}",
        "blocks": blocks,
        "unfurl_links": False,
        "unfurl_media": False,
    }

    store = Store(DB_PATH)

    try:
        with store.transaction():
            store.enqueue(f"ntfy:{topic}", "message", payload, now)
    finally:
        store.close()
    
    return {"queued": True}


@app.get("/status")
def get_status():
    now = datetime.now(timezone.utc)

    output = {}

    for service, data in heartbeats.items():
        age = (now - data["last_seen"]).total_seconds()

        if data["status"] != "ok":
            state = "DOWN"
        elif age < 15:
            state = "UP"
        elif age < 30:
            state = "STALE"
        else:
            state = "DOWN"

        entry = {
            "state": state,
            "seconds_since_heartbeat": age,
            "status": data["status"],
        }

        if specs := format_specs(data["message"]):
            entry["specs"] = specs
        else:
            entry["message"] = data["message"]

        output[service] = entry

    return output