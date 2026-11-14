from fastapi import Depends, FastAPI, Header, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
from datetime import datetime, timezone
from html import escape
from os import getenv
import time
from zoneinfo import ZoneInfo

from canary.storage import Store

API_KEY = getenv("API_KEY")

assert API_KEY, "API_KEY is required and not set!"

SLACK_CHANNEL_ID = getenv("SLACK_CHANNEL_ID")
DB_PATH = getenv("CANARY_DB_PATH", "/app/data/canary.sqlite3")

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
async def publish(topic: str, request: Request, title: str | None = Header(None)):
    """ntfy-style publish: the raw body is queued for Canary's Slack sender."""
    text = (await request.body()).decode(errors="replace").strip()

    if not text:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Empty message")
    
    if not SLACK_CHANNEL_ID:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "SLACK_CHANNEL_ID is not set")
    
    # Escaping keeps publishers from injecting <!channel> pings or links.
    heading = escape(f"[{topic}] {title}" if title else f"[{topic}]", quote=False)
    payload = {
        "channel": SLACK_CHANNEL_ID,
        "text": f"*{heading}*\n{escape(text[:3000], quote=False)}",
        "unfurl_links": False,
        "unfurl_media": False,
    }

    store = Store(DB_PATH)
    
    try:
        with store.transaction():
            store.enqueue(f"ntfy:{topic}", "message", payload, time.time())
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