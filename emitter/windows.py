"""Selected-drive Windows emitter. Run with python -m emitter.windows --config PATH."""

import argparse
import ctypes
import logging
import math
import os
from pathlib import Path
import signal
import threading
import time
import tomllib
from urllib.parse import urlsplit

import psutil

from canary.services import DEFAULT_SERVICES_FILE, load_catalog
from .common import configure_logging, send_heartbeat

logger = logging.getLogger(__name__)


def load_config(path):
    path = Path(path).resolve()
    try:
        with path.open("rb") as file:
            config = tomllib.load(file)
        try:
            url = urlsplit(config.get("heartbeat_url", ""))
            if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password:
                raise ValueError()
            url.port
        except (ValueError, TypeError):
            raise ValueError("heartbeat_url must be a valid HTTP(S) URL without embedded credentials") from None
        if not isinstance(config.get("api_key"), str) or not config["api_key"].strip():
            raise ValueError("api_key is required")
        name = config.get("host_name", "pdm-windows")
        if not isinstance(name, str) or not name or name != name.strip():
            raise ValueError("host_name must be a nonempty name without surrounding spaces")
        interval = config.get("interval_seconds", 10)
        if isinstance(interval, bool) or not isinstance(interval, (float, int)) or not math.isfinite(interval) or interval <= 0:
            raise ValueError("interval_seconds must be positive and finite")
        catalog = Path(config.get("services_file", str(DEFAULT_SERVICES_FILE)))
        if not catalog.is_absolute():
            catalog = path.parent / catalog
        _, hosts = load_catalog(catalog)
        host = next((host for host in hosts if host["name"] == name), None)
        if host is None or not host["drives"]:
            raise ValueError("host_name must match a [[hosts]] entry with selected drives")
        config.update(host_name=name, interval_seconds=interval, drives=host["drives"])
        config["log_file"] = str(path.parent / "logs" / "emitter.log")
        return config
    except (OSError, ValueError, TypeError) as error:
        # Don't echo TOML decoder text, which can include secret-containing lines.
        if isinstance(error, tomllib.TOMLDecodeError):
            raise ValueError("Invalid TOML in private Windows configuration") from None
        if isinstance(error, OSError):
            raise ValueError("Cannot read Windows configuration/catalog; check paths and permissions") from None
        raise ValueError(str(error)) from None


def collect_disks(drives, *, strict=False):
    disks = {}
    for drive in drives:
        try:
            # DRIVE_FIXED = 3; excludes mapped network/removable drives.
            if ctypes.windll.kernel32.GetDriveTypeW(ctypes.c_wchar_p(drive)) != 3:
                raise OSError("Drive is unavailable or is not local fixed storage")
            usage = psutil.disk_usage(drive)
            if usage.total <= 0:
                raise OSError("Drive capacity is unavailable")
            disks[drive] = (usage.total, usage.used, usage.free)
        except OSError:
            logger.warning("Selected drive unavailable: %s", drive)
            if strict:
                raise ValueError(f"Selected drive must be accessible local fixed storage: {drive}") from None
    return disks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, help="Private Windows TOML configuration")
    parser.add_argument("--check", action="store_true", help="Validate all drives and send one preflight heartbeat")
    parser.add_argument("--once", action="store_true", help="Send one observation and exit")
    args = parser.parse_args()
    if os.name != "nt":
        parser.error("The Windows emitter requires Windows")
    try:
        configure_logging(Path(args.config).resolve().parent / "logs" / "emitter.log")
        config = load_config(args.config)
        if args.check:
            collect_disks(config["drives"], strict=True)
    except (ValueError, OSError) as error:
        logger.error("Emitter configuration/preflight failed: %s", error)
        return 1
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    logger.info("Windows emitter started for %s", config["host_name"])
    while not stop.is_set():
        started = time.monotonic()
        disks = collect_disks(config["drives"])
        success = send_heartbeat(config["heartbeat_url"], config["api_key"], config["host_name"], message={"disks": disks})
        if args.check or args.once:
            return 0 if success else 1
        stop.wait(max(0, config["interval_seconds"] - (time.monotonic() - started)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
