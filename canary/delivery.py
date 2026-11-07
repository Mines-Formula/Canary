"""Sends queued messaeges to slack"""

import json
import logging
import random
import time

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError, SlackClientError

from .storage import Store

logger = logging.getLogger(__name__)
CONFIGURATION_ERRORS = {
    "invalid_auth", "not_authed", "token_revoked", "account_inactive", "missing_scope",
    "channel_not_found", "not_in_channel", "no_permission", "restricted_action",
}


class Sender:
    def __init__(self, store, client):
        self.store = store
        self.client = client

    def deliver_one(self, now):
        """Attempt only the oldest pending item, preserving opening/recovery order."""
        row = self.store.next_notification()
        if row is None or row["next_attempt_at"] > now:
            return False
        try:
            self.client.chat_postMessage(**json.loads(row["payload"]))
        except SlackApiError as error:
            code = error.response.get("error", "unknown_error")
            if error.response.status_code == 429 or code == "ratelimited":
                headers = {key.lower(): value for key, value in error.response.headers.items()}
                try:
                    delay = max(1, float(headers.get("retry-after", 30)))
                except (ValueError, TypeError):
                    delay = 30
                logger.warning("Slack rate limited notification %s; retrying in %.0fs", row["id"], delay)
            elif code in CONFIGURATION_ERRORS:
                delay = 300
                logger.error("Slack configuration/permission error: %s; retrying in 5 minutes", code)
            else:
                delay = self._backoff(row["attempts"])
                logger.warning("Slack API failure: %s; notification remains queued", code)
            self.store.retry(row["id"], now + delay)
        except (SlackClientError, OSError):
            self.store.retry(row["id"], now + self._backoff(row["attempts"]))
            logger.warning("Slack connection failure; notification %s remains queued", row["id"])
        else:
            self.store.delivered(row["id"], now)
            logger.info("Delivered notification %s (%s)", row["id"], row["event"])
        return True

    @staticmethod
    def _backoff(attempts):
        return min(300, 2 ** min(attempts + 1, 9) * random.uniform(0.5, 1.5))


def run_sender(config, stop):
    store = Store(config.database_path)
    try:
        # The persisted queue owns retries, so SDK retries must not bypass its schedule.
        client = WebClient(token=config.slack_token, timeout=10, retry_handlers=[])
        sender = Sender(store, client)
        while not stop.is_set():
            started = time.monotonic()
            sender.deliver_one(time.time())
            # Pace all attempts to <= 1/sec; sleep is interruptible on shutdown.
            stop.wait(max(0, 1 - (time.monotonic() - started)))
    finally:
        store.close()