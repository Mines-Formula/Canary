"""Validate /status endpoint response"""

from dataclasses import dataclass, field
import math


def number(value, *, maximum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Expected a finite nonnegative number")
    if not math.isfinite(value) or value < 0 or (maximum is not None and value > maximum):
        raise ValueError("Number outside its valid range")
    return float(value)


@dataclass(frozen=True)
class Disk:
    percent: float
    free_gib: float
    total_gib: float


@dataclass(frozen=True)
class Service:
    state: str
    status: str
    age: float
    message: str | dict | None = None
    disks: dict[str, Disk] = field(default_factory=dict)
    invalid_mounts: frozenset[str] = frozenset()


def parse_status(payload) -> dict[str, Service]:
    if not isinstance(payload, dict):
        raise ValueError("Status response must be an object")
    result = {}
    for name, entry in payload.items():
        if not isinstance(name, str) or not name.strip() or not isinstance(entry, dict):
            raise ValueError("Invalid service entry")
        state = entry.get("state")
        status = entry.get("status")
        if state not in ("UP", "STALE", "DOWN") or not isinstance(status, str) or not status:
            raise ValueError("Invalid service state/status")
        age = number(entry.get("seconds_since_heartbeat"))
        if state == "UP" and status != "ok":
            raise ValueError("UP service cannot have a failure status")
        message = entry.get("message")
        if message is not None and not isinstance(message, (str, dict)):
            raise ValueError("Invalid service message")
        specs = entry.get("specs") or {}
        if not isinstance(specs, dict):
            raise ValueError("Invalid service specifications")
        disks, invalid = {}, set()
        raw_disks = specs.get("disks")
        if isinstance(raw_disks, dict):
            for mount, raw in raw_disks.items():
                if not isinstance(mount, str) or not mount:
                    continue
                try:
                    if not isinstance(raw, dict):
                        raise ValueError("Invalid disk")
                    percent = number(raw.get("percent_used"), maximum=100)
                    total = number(raw.get("total_gb"))
                    free = number(raw.get("free_gb"), maximum=total)
                    if total == 0:
                        raise ValueError("Disk capacity must be positive")
                    disks[mount] = Disk(percent, free, total)
                except ValueError:
                    invalid.add(mount)
        result[name] = Service(state, status, age, message, disks, frozenset(invalid))
    return result
