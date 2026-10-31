"""Stores persistent memory via SQLite"""

from contextlib import contextmanager
from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3


@dataclass
class Incident:
    key: str
    kind: str
    subject: str
    severity: str
    opened_at: float
    last_reminder_at: float
    announced: bool
    detail: str


class Store:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, timeout=10)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS known_services (name TEXT PRIMARY KEY);
            CREATE TABLE IF NOT EXISTS known_mounts (name TEXT PRIMARY KEY);
            CREATE TABLE IF NOT EXISTS incidents (
                key TEXT PRIMARY KEY, kind TEXT NOT NULL, subject TEXT NOT NULL,
                severity TEXT NOT NULL, opened_at REAL NOT NULL,
                last_reminder_at REAL NOT NULL, announced INTEGER NOT NULL,
                detail TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                incident_key TEXT NOT NULL, event TEXT NOT NULL,
                payload TEXT NOT NULL, created_at REAL NOT NULL,
                delivered_at REAL, attempts INTEGER NOT NULL DEFAULT 0,
                next_attempt_at REAL NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS pending_notifications
                ON notifications(id) WHERE delivered_at IS NULL;
        """)

    @contextmanager
    def transaction(self):
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.connection.commit()
        except BaseException:
            self.connection.rollback()
            raise

    def close(self):
        self.connection.close()

    def remember(self, category, names):
        table = self._known_table(category)
        self.connection.executemany(f"INSERT OR IGNORE INTO {table}(name) VALUES (?)", ((n,) for n in names))

    def known(self, category):
        table = self._known_table(category)
        return {row[0] for row in self.connection.execute(f"SELECT name FROM {table}")}

    @staticmethod
    def _known_table(category):
        return {"services": "known_services", "mounts": "known_mounts"}[category]

    def incident(self, key):
        row = self.connection.execute("SELECT * FROM incidents WHERE key = ?", (key,)).fetchone()
        return Incident(**dict(row)) if row else None

    def save(self, incident):
        self.connection.execute(
            "INSERT OR REPLACE INTO incidents VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (incident.key, incident.kind, incident.subject, incident.severity,
             incident.opened_at, incident.last_reminder_at, int(incident.announced), incident.detail),
        )

    def resolve(self, key):
        self.connection.execute("DELETE FROM incidents WHERE key = ?", (key,))
        self.clear_reminders(key)

    def clear_reminders(self, key):
        self.connection.execute(
            "DELETE FROM notifications WHERE incident_key = ? AND event = 'reminder' AND delivered_at IS NULL",
            (key,),
        )

    def enqueue(self, key, event, payload, now):
        self.clear_reminders(key)
        self.connection.execute(
            "INSERT INTO notifications(incident_key, event, payload, created_at) VALUES (?, ?, ?, ?)",
            (key, event, json.dumps(payload), now),
        )

    def next_notification(self):
        return self.connection.execute(
            "SELECT * FROM notifications WHERE delivered_at IS NULL ORDER BY id LIMIT 1"
        ).fetchone()

    def delivered(self, notification_id, now):
        with self.transaction():
            self.connection.execute(
                "UPDATE notifications SET delivered_at = ? WHERE id = ?", (now, notification_id),
            )
            # Keep a small delivery audit trail, rather than accumulating reminders forever.
            self.connection.execute("DELETE FROM notifications WHERE delivered_at < ?", (now - 7 * 86400,))

    def retry(self, notification_id, next_attempt):
        with self.transaction():
            self.connection.execute(
                "UPDATE notifications SET attempts = attempts + 1, next_attempt_at = ? WHERE id = ?",
                (next_attempt, notification_id),
            )
