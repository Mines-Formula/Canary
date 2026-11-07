"""Config shared by the poller and notification sender"""

from dataclasses import dataclass, field
import math
import os
from urllib.parse import urlsplit

from .services import DEFAULT_SERVICES_FILE, load_services


@dataclass(frozen=True)
class Config:
    slack_token: str = field(repr=False)
    channel_id: str
    status_url: str = "http://heartbeat:8000/status"
    host_service: str = "fsaelinux"
    expected_services: tuple[str, ...] = ()
    database_path: str = "/app/data/canary.sqlite3"
    poll_interval: float = 10
    confirmation_seconds: float = 60
    reminder_seconds: float = 3600
    disk_threshold: float = 90
    disk_clear: float = 85
    ignored_services: frozenset[str] = frozenset()

    def __post_init__(self):
        if not self.slack_token.startswith("xoxp-"):
            raise ValueError("SLACK_ADMIN_USER_TOKEN must be a user OAuth token (xoxp-)")
        if not self.channel_id.strip():
            raise ValueError("SLACK_CHANNEL_ID is required")
        url = urlsplit(self.status_url)
        if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password:
            raise ValueError("CANARY_STATUS_URL must be an HTTP(S) URL without embedded credentials")
        if not self.host_service.strip() or not self.database_path.strip():
            raise ValueError("CANARY_HOST_SERVICE and CANARY_DB_PATH must not be empty")
        if self.host_service in self.ignored_services:
            raise ValueError("The host service cannot be retired")
        for name in ("poll_interval", "confirmation_seconds", "reminder_seconds"):
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be a positive finite number")
        thresholds = (self.disk_clear, self.disk_threshold)
        if not all(math.isfinite(value) for value in thresholds) or not (
            0 <= self.disk_clear < self.disk_threshold <= 100
        ):
            raise ValueError("Disk thresholds must satisfy 0 <= clear < threshold <= 100")

    @classmethod
    def from_env(cls, env=None):
        env = os.environ if env is None else env
        numbers = {
            "poll_interval": ("CANARY_POLL_INTERVAL", 10),
            "confirmation_seconds": ("CANARY_CONFIRMATION_SECONDS", 60),
            "reminder_seconds": ("CANARY_REMINDER_SECONDS", 3600),
            "disk_threshold": ("CANARY_DISK_THRESHOLD", 90),
            "disk_clear": ("CANARY_DISK_CLEAR", 85),
        }
        values = {}
        for name, (variable, default) in numbers.items():
            try:
                values[name] = float(env.get(variable, default))
            except (TypeError, ValueError):
                raise ValueError(f"{variable} must be a number") from None
        host_service = env.get("CANARY_HOST_SERVICE", cls.host_service).strip()
        services = load_services(env.get("CANARY_SERVICES_FILE", DEFAULT_SERVICES_FILE), host_name=host_service)
        return cls(
            slack_token=env.get("SLACK_ADMIN_USER_TOKEN", "").strip(),
            channel_id=env.get("SLACK_CHANNEL_ID", "").strip(),
            status_url=env.get("CANARY_STATUS_URL", cls.status_url).strip(),
            host_service=host_service,
            expected_services=tuple(s["name"] for s in services if s["enabled"]),
            ignored_services=frozenset(s["name"] for s in services if not s["enabled"]),
            database_path=env.get("CANARY_DB_PATH", cls.database_path).strip(),
            **values,
        )
