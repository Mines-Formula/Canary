import enum
import json
import logging
import os
import re
import shutil
import time
from typing import NamedTuple
import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Configuration via environment variables
CANARY_URL = os.getenv(
    "CANARY_URL",
    "http://ec2-54-196-50-201.compute-1.amazonaws.com:8000/heartbeat",
)
SERVICE_NAME = os.getenv("SERVICE_NAME", "fsaelinux")
INTERVAL_SECONDS = int(os.getenv("PING_INTERVAL", "10"))

BASE_URL = "http://fsaelinux.mines.edu"

class Status(enum.StrEnum):
    OK = "ok"
    DOWN = "down"

class HttpService(NamedTuple):
    name: str
    url: str


# Services we want to monitor on fsaelinux
HTTP_SERVICES = [
    HttpService(name="MFHome", url=f"{BASE_URL}:80"),
    HttpService(name="InfluxDB", url=f"{BASE_URL}:8086"),
    HttpService(name="Wiki", url=f"{BASE_URL}:4000"),
    HttpService(name="ThePipeline", url=f"{BASE_URL}:6767"),
    HttpService(name="Grafana", url=f"{BASE_URL}:3000/healthz"),  # Healthz is the health/status endpoint for grafana
    HttpService(name="MockService", url="http://localhost:9999"),  # Mock server for testing
]


def get_disk_usage(
    host_prefix: str = "/host" if os.path.exists("/host") else "",
) -> dict[str, tuple[int, int, int]]:
    """Return raw (total, used, free) bytes for mounted physical device filesystems."""
    host_prefix = host_prefix.rstrip("/")

    mounts_path = (
        f"{host_prefix}/proc/1/mounts"
        if host_prefix and os.path.exists(f"{host_prefix}/proc/1/mounts")
        else "/proc/self/mounts"
    )

    disks = {}

    def unescape(value: str) -> str:
        return re.sub(
            r"\\([0-7]{3})",
            lambda match: chr(int(match.group(1), 8)),
            value,
        )

    with open(mounts_path, encoding="utf-8") as mounts:
        for line in mounts:
            fields = line.split()
            if len(fields) < 2:
                continue

            dev, mount = map(unescape, fields[:2])

            # Makes sure we only get the storage of drives we care about
            if not dev.startswith("/dev/") or dev.startswith("/dev/loop"):
                continue

            if mount == "/boot" or mount.startswith("/boot/"):
                continue

            target = f"{host_prefix}{mount}"

            try:
                # Raw bytes (total, used, free)
                disks[mount] = tuple(shutil.disk_usage(target))
            except OSError as exc:
                logger.warning("Cannot read disk usage for %s: %s", target, exc)
                continue

    return disks


def send_heartbeat(
    service: str,
    status: Status = Status.OK,
    message: str = "",
) -> None:
    payload = {
        "service": service,
        "status": status,
        "message": message,
    }

    try:
        resp = requests.post(CANARY_URL, json=payload, timeout=5)
        if resp.ok:
            logger.info("Heartbeat sent (%s: %s - %s)", service, status, message)
        else:
            logger.error("Server returned %d for %s: %s", resp.status_code, service, resp.text)
    except requests.RequestException as e:
        logger.error("Failed to send heartbeat for %s to %s: %s", service, CANARY_URL, e)


def check_host() -> None:
    raw_disks = get_disk_usage()
    send_heartbeat(
        service=SERVICE_NAME,
        status=Status.OK,
        message=json.dumps(raw_disks),
    )


def check_http_service(name: str, url: str) -> None:
    try:
        resp = requests.get(url, timeout=3)
        # Any response code < 500 means web server is alive
        if resp.status_code < 500:
            send_heartbeat(service=name, status=Status.OK, message=f"HTTP {resp.status_code}")
        else:
            send_heartbeat(service=name, status=Status.DOWN, message=f"HTTP {resp.status_code}")
    except requests.RequestException as e:
        send_heartbeat(service=name, status=Status.DOWN, message=f"Unreachable: {type(e).__name__}")


def main() -> None:
    logger.info("Starting Emitter, targeting %s every %ds", CANARY_URL, INTERVAL_SECONDS)
    try:
        while True:
            # Check host system fsaelinux stats
            check_host()

            # Check each HTTP service
            for service in HTTP_SERVICES:
                check_http_service(service.name, service.url)

            time.sleep(INTERVAL_SECONDS)
    except KeyboardInterrupt:
        logger.info("Canary Emitter stopped.")


if __name__ == "__main__":
    main()
