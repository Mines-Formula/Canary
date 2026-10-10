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

# Services we want to monitor on fsaelinux
HTTP_SERVICES = [
    {"name": "MFHome", "url": "http://fsaelinux.mines.edu:80"},
    {"name": "InfluxDB", "url": "http://fsaelinux.mines.edu:8086"},
    {"name": "Wiki", "url": "http://fsaelinux.mines.edu:4000"},
    {"name": "ThePipeline", "url": "http://fsaelinux.mines.edu:6767"},
    {"name": "Grafana", "url": "http://fsaelinux.mines.edu:3000/healthz"}, # Healthz is the health/status endpoint for grafana
    {"name": "MockService", "url": "http://localhost:9999"} # Mock server for testing 
]


def get_disk_usage() -> float:
    """Returns storage usage percentage of fsaelinux (mounts container to /host)"""
    if os.path.exists("/host"):
        path = "/host"
    elif os.name == "nt":
        path = "C:\\"
    else:
        path = "/"
    total, used, free = shutil.disk_usage(path)
    return round((used / total) * 100, 1)


def send_heartbeat(service: str, status: str = "ok", message: str = "") -> None:
    payload = {
        "service": service,
        "status": status,
        "message": message,
    }

    try:
        resp = requests.post(CANARY_URL, json=payload, timeout=5)
        if resp.ok:
            print(f"[Canary] Heartbeat sent ({service}: {status} - {message})")
        else:
            print(f"[Canary Error] Server returned {resp.status_code} for {service}: {resp.text}")
    except requests.RequestException as e:
        print(f"[Canary Error] Failed to send heartbeat for {service} to {CANARY_URL}: {e}")


def check_host() -> None:
    disk_pct = get_disk_usage()
    send_heartbeat(
        service=SERVICE_NAME,
        status="ok",
        message=f"Disk usage: {disk_pct}%",
    )


def check_http_service(name: str, url: str) -> None:
    try:
        resp = requests.get(url, timeout=3)
        # Any response code < 500 means web server is alive
        if resp.status_code < 500:
            send_heartbeat(service=name, status="ok", message=f"HTTP {resp.status_code}")
        else:
            send_heartbeat(service=name, status="down", message=f"HTTP {resp.status_code}")
    except requests.RequestException as e:
        send_heartbeat(service=name, status="down", message=f"Unreachable: {type(e).__name__}")


def main() -> None:
    print(f"Starting Emitter, targeting {CANARY_URL} every {INTERVAL_SECONDS}s")
    try:
        while True:
            # Check host system fsaelinux stats
            check_host()

            # Check each HTTP service
            for svc in HTTP_SERVICES:
                check_http_service(svc["name"], svc["url"])

            time.sleep(INTERVAL_SECONDS)
    except KeyboardInterrupt:
        print("\nCanary Emitter stopped.")


if __name__ == "__main__":
    main()
