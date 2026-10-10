from fastapi import FastAPI
from pydantic import BaseModel
from datetime import datetime, timezone

app = FastAPI()

heartbeats = {}

class Heartbeat(BaseModel):
    service: str
    status: str = "ok"
    message: str | None = None


@app.post("/heartbeat")
def heartbeat(hb: Heartbeat):
    heartbeats[hb.service] = {
        "last_seen": datetime.now(timezone.utc),
        "status": hb.status,
        "message": hb.message,
    }

    return {"received": True}


@app.get("/status")
def status():
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

        output[service] = {
            "state": state,
            "seconds_since_heartbeat": age,
            "status": data["status"],
            "message": data["message"],
        }

    return output