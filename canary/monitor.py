"""Incident decisions"""

import json
import logging

from .messages import notification
from .storage import Incident

logger = logging.getLogger(__name__)
API_INCIDENT_KEY = "monitor:status-api"
COVERAGE_KEY = "coverage:storage"


class Monitor:
    def __init__(self, config, store):
        self.config = config
        self.store = store
        # Resets on restart
        self.candidates = {}
        self.recoveries = {}
        with store.transaction():
            store.retire_services(config.ignored_services)
            services = {*config.expected_services, config.host_service} - config.ignored_services
            store.remember("services", services)

    def _send(self, incident, event, now):
        self.store.enqueue(incident.key, event, notification(self.config, incident, event, now), now)
        logger.info("Incident %s: %s (%s)", event, incident.key, incident.severity)

    def _pause(self, key):
        self.candidates.pop(key, None)
        self.recoveries.pop(key, None)

    def _activate(self, key, kind, subject, severity, detail, now, tick, *,
                  delay=None, suppressed=False, eligible=True, reminders=True):
        self.recoveries.pop(key, None)
        incident = self.store.incident(key)
        if incident is None:
            since = self.candidates.setdefault(key, tick)
            delay = self.config.confirmation_seconds if delay is None else delay
            if not eligible or tick - since < delay:
                return
            incident = Incident(key, kind, subject, severity, now, now, False, detail)
            self.candidates.pop(key, None)
        incident.severity = severity
        incident.detail = detail
        if not suppressed:
            if not incident.announced:
                self._send(incident, "opened", now)
                incident.announced = True
                incident.last_reminder_at = now
            elif reminders and now - incident.last_reminder_at >= self.config.reminder_seconds:
                self._send(incident, "reminder", now)
                incident.last_reminder_at = now
        self.store.save(incident)

    def _healthy(self, key, now, detail, *, polls=2):
        self.candidates.pop(key, None)
        incident = self.store.incident(key)
        if incident is None:
            self.recoveries.pop(key, None)
            return
        count = self.recoveries.get(key, 0) + 1
        self.recoveries[key] = count
        if count >= polls:
            if incident.announced:
                incident.detail = detail
                self._send(incident, "resolved", now)
            self.store.resolve(key)
            self.recoveries.pop(key, None)

    def failure(self, now, tick, reason):
        """Unknown health is not always an outage"""
        with self.store.transaction():
            for key in set(self.candidates) | set(self.recoveries):
                if key != API_INCIDENT_KEY:
                    self._pause(key)
            self._activate(API_INCIDENT_KEY, "monitor", "Status API", "warning", reason, now, tick)

    def observe(self, snapshot, now, tick):
        snapshot = {name: entry for name, entry in snapshot.items() if name not in self.config.ignored_services}
        with self.store.transaction():
            self._healthy(API_INCIDENT_KEY, now, "Status API is returning valid data again.", polls=1)
            self.store.remember("services", snapshot)
            services = self.store.known("services") - self.config.ignored_services
            host_name = self.config.host_service
            host = snapshot.get(host_name)
            affected = sorted(
                name for name in services - {host_name}
                if name not in snapshot or (snapshot[name].status == "ok" and snapshot[name].state != "UP")
            )
            self._service(host_name, host, now, tick, affected=affected)
            host_lost = self.store.incident(f"service:{host_name}") is not None and (
                host is None or (host.status == "ok" and host.state != "UP")
            )
            for name in sorted(services - {host_name}):
                entry = snapshot.get(name)
                suppressed = host_lost and (entry is None or entry.status == "ok")
                self._service(name, entry, now, tick, suppressed=suppressed)
            self._storage(host, now, tick)

    def _service(self, name, entry, now, tick, *, suppressed=False, affected=()):
        key = f"service:{name}"
        if entry is not None and entry.state == "UP":
            self._healthy(key, now, "Fresh healthy heartbeats have resumed.")
            return
        if entry is None:
            detail = "No heartbeat is present, reporting has been lost."
        elif entry.status != "ok":
            reason = json.dumps(entry.message, sort_keys=True) if isinstance(entry.message, dict) else entry.message
            detail = f"Emitter reported status `{entry.status}`: {reason or 'No additional detail'}"
        else:
            detail = f"Heartbeat reporting is delayed; last received {entry.age:.0f}s ago."
        if affected and name == self.config.host_service:
            detail += (" Affected services with delayed/missing reporting: "
                       + ", ".join(f"`{service}`" for service in affected))
        self._activate(
            key, "service", name, "outage", detail, now, tick,
            suppressed=suppressed, eligible=entry is None or entry.state == "DOWN",
        )

    def _storage(self, host, now, tick):
        if host is None or host.state != "UP":
            for key in set(self.candidates) | set(self.recoveries):
                if key.startswith("disk:") or key == COVERAGE_KEY:
                    self._pause(key)
            return
        self.store.remember("mounts", host.disks.keys() | host.invalid_mounts)
        missing = self.store.known("mounts") - host.disks.keys()
        if missing or not host.disks:
            detail = "Storage metrics are missing or invalid"
            detail += (" for: " + ", ".join(f"`{name}`" for name in sorted(missing))
                       if missing else " for all mounts.")
            self._activate(COVERAGE_KEY, "coverage", "Storage coverage", "warning", detail, now, tick)
        else:
            self._healthy(COVERAGE_KEY, now, "All known mounts are reporting valid metrics.", polls=1)
        for mount in missing:
            self._pause(f"disk:{mount}")
        for mount, disk in sorted(host.disks.items()):
            key = f"disk:{mount}"
            capacity = f"{disk.free_gib:.1f} GiB free of {disk.total_gib:.1f} GiB."
            if disk.percent < self.config.disk_clear:
                self._healthy(key, now, f"Usage on `{mount}` is back to {disk.percent:.1f}%. {capacity}")
                continue
            detail = (
                f"Disk usage on `{mount}` reached {disk.percent:.1f}% "
                f"(threshold {self.config.disk_threshold:g}%). {capacity}"
            )
            incident = self.store.incident(key)
            if disk.percent >= self.config.disk_threshold:
                self._activate(key, "disk", mount, "critical", detail, now, tick, delay=0, reminders=False)
            else:
                self._pause(key)
                if incident is not None:
                    incident.detail = detail
                    self.store.save(incident)
