import os
import shutil
import time
import requests

# Configuration via environment variables
CANARY_URL = os.getenv(
    "CANARY_URL",
    "http://ec2-54-196-50-201.compute-1.amazonaws.com:8000/heartbeat",
)
SERVICE_NAME = os.getenv("SERVICE_NAME", "fsaelinux")
INTERVAL_SECONDS = int(os.getenv("PING_INTERVAL", "10"))


def get_disk_usage() -> float:
    """Returns storage usage percentage"""
    path = "C:\\" if os.name == "nt" else "/"
    total, used, free = shutil.disk_usage(path)
    return round((used / total) * 100, 1)


def send_heartbeat() -> None:
    disk_pct = get_disk_usage()
    payload = {
        "service": SERVICE_NAME,
        "status": "ok",
        "message": f"Disk usage: {disk_pct}%",
    }

    try:
        resp = requests.post(CANARY_URL, json=payload, timeout=5)
        if resp.ok:
            print(f"[Canary] Heartbeat sent ({SERVICE_NAME}, {disk_pct}% disk)")
        else:
            print(f"[Canary Error] Server returned {resp.status_code}: {resp.text}")
    except requests.RequestException as e:
        print(f"[Canary Error] Failed to send heartbeat to {CANARY_URL}: {e}")


def main() -> None:
    print(f"Starting Emitter, targeting {CANARY_URL} every {INTERVAL_SECONDS}s")
    try:
        while True:
            send_heartbeat()
            time.sleep(INTERVAL_SECONDS)
    except KeyboardInterrupt:
        print("\nCanary Emitter stopped.")


if __name__ == "__main__":
    main()
