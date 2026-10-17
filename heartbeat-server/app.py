from fastapi import Depends, FastAPI, HTTPException, Security, status
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
from datetime import datetime, timezone
from os import getenv

API_KEY = getenv("API_KEY")
assert API_KEY, "API_KEY is required and not set!"

app = FastAPI()

heartbeats = {}
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


GIB = 1024**3


class Heartbeat(BaseModel):
    service: str
    status: str = "ok"
    message: dict | None = None


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
        specs["boot_time"] = datetime.fromtimestamp(boot_time, timezone.utc).isoformat()
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