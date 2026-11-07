import enum
import json
import logging
import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo
import psutil
import requests

from canary.services import DEFAULT_SERVICES_FILE, load_services

DENVER = ZoneInfo("America/Denver")


class DenverFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        return datetime.fromtimestamp(record.created, DENVER).strftime(
            datefmt or "%Y-%m-%d %H:%M:%S %Z (%z)"
        )


handler = logging.StreamHandler()
handler.setFormatter(DenverFormatter("%(asctime)s [%(levelname)s] %(message)s"))
logging.basicConfig(
    level=logging.INFO,
    handlers=[handler],
)
logger = logging.getLogger(__name__)

# Configuration via environment variables
CANARY_URL = os.getenv("CANARY_URL")
API_KEY = os.getenv("API_KEY")
SERVICE_NAME = os.getenv("SERVICE_NAME", "fsaelinux")
INTERVAL_SECONDS = int(os.getenv("PING_INTERVAL", "10"))


class Status(enum.StrEnum):
    OK = "ok"
    DOWN = "down"


HTTP_HEADERS = {"X-API-Key": API_KEY}


def get_disk_usage(
    host_prefix: str = "/host" if os.path.exists("/host") else "",
) -> dict[str, tuple[int, int, int]]:
    """Return raw (total, used, free) bytes for mounted physical device filesystems."""
    host_prefix = host_prefix.rstrip("/")

    disks = {}

    for part in psutil.disk_partitions():
        # Makes sure we only get the storage of drives we care about
        if not part.device.startswith("/dev/") or part.device.startswith("/dev/loop"):
            continue

        # Report the host's own paths, not the container's view of them
        mount = part.mountpoint
        if host_prefix:
            if mount != host_prefix and not mount.startswith(f"{host_prefix}/"):
                continue
            mount = mount[len(host_prefix):] or "/"

        if mount == "/boot" or mount.startswith("/boot/"):
            continue

        try:
            usage = psutil.disk_usage(part.mountpoint)
        except OSError as exc:
            logger.warning("Cannot read disk usage for %s: %s", part.mountpoint, exc)
            continue

        # Raw bytes (total, used, free)
        disks[mount] = (usage.total, usage.used, usage.free)

    return disks


def send_heartbeat(
    service: str,
    status: Status = Status.OK,
    message: dict = {},
) -> None:
    payload = {
        "service": service,
        "status": status,
        "message": message,
    }

    try:
        resp = requests.post(CANARY_URL, json=payload, headers=HTTP_HEADERS, timeout=5)
        if resp.ok:
            logger.info("Heartbeat sent (%s: %s - %s)", service, status, message)
        else:
            logger.error("Server returned %d for %s: %s", resp.status_code, service, resp.text)
    except requests.RequestException as e:
        logger.error("Failed to send heartbeat for %s to %s: %s", service, CANARY_URL, e)


def check_host() -> None:
    memory = psutil.virtual_memory()

    payload = {
        "disks": get_disk_usage(),
        "memory": (memory.total, memory.used, memory.available),
        "load": psutil.getloadavg(),
        "boot_time": psutil.boot_time(),
    }

    send_heartbeat(
        service=SERVICE_NAME,
        status=Status.OK,
        message=payload,
    )


def check_http_service(name: str, url: str) -> None:
    try:
        resp = requests.get(url, timeout=3)
        # Any response code < 500 means web server is alive
        if resp.status_code < 500:
            send_heartbeat(service=name, status=Status.OK, message={"status_code": resp.status_code})
        else:
            send_heartbeat(service=name, status=Status.DOWN, message={"status_code": resp.status_code})
    except requests.RequestException as e:
        send_heartbeat(service=name, status=Status.DOWN, message=f"Unreachable: {type(e).__name__}")


def main() -> None:
    for name, value in ("CANARY_URL", CANARY_URL), ("API_KEY", API_KEY):
        if not value:
            logger.critical("%s is required and not set", name)
            raise SystemExit(1)

    try:
        services = load_services(os.getenv("CANARY_SERVICES_FILE", DEFAULT_SERVICES_FILE), host_name=SERVICE_NAME)
    except ValueError as error:
        logger.critical("Configuration error: %s", error)
        raise SystemExit(1) from error
    http_services = [service for service in services if service["enabled"]]

    logger.info("Starting Emitter, targeting %s every %ds (%d HTTP services)",
                CANARY_URL, INTERVAL_SECONDS, len(http_services))

    try:
        while True:
            # Check host system fsaelinux stats
            check_host()

            # Check each HTTP service
            for service in http_services:
                check_http_service(service["name"], service["url"])

            time.sleep(INTERVAL_SECONDS)
    except KeyboardInterrupt:
        logger.info("Canary Emitter stopped.")


if __name__ == "__main__":
    main()
