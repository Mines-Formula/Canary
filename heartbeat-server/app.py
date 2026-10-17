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


class Heartbeat(BaseModel):
    service: str
    status: str = "ok"
    message: str | None = None


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

        output[service] = {
            "state": state,
            "seconds_since_heartbeat": age,
            "status": data["status"],
            "message": data["message"],
        }

    return output