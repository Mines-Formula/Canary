"""Canary docker service lifecycle"""

import logging
import signal
import threading
import time

import requests

from .config import Config
from .delivery import run_sender
from .monitor import Monitor
from .status import parse_status
from .storage import Store
from .timeutils import DenverFormatter

logger = logging.getLogger(__name__)


def main():
    handler = logging.StreamHandler()
    handler.setFormatter(DenverFormatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler])
    try:
        config = Config.from_env()
    except ValueError as error:
        logger.error("Configuration error: %s", error)
        return 1
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    store = Store(config.database_path)
    sender = None
    try:
        monitor = Monitor(config, store)
        sender = threading.Thread(target=run_sender, args=(config, stop), name="slack-delivery", daemon=True)
        sender.start()
        logger.info("Canary started; polling every %gs", config.poll_interval)
        with requests.Session() as session:
            while not stop.is_set():
                started = time.monotonic()
                if not sender.is_alive():
                    raise RuntimeError("Slack delivery thread stopped, exiting so Docker can restart Canary")
                try:
                    response = session.get(config.status_url, timeout=(3, 5))
                    response.raise_for_status()
                    snapshot = parse_status(response.json())
                except (requests.RequestException, ValueError) as error:
                    # Log the class, not response bodies/URLs that might contain private data.
                    reason = f"Status API observation failed ({type(error).__name__}); service health is unknown."
                    logger.warning(reason)
                    monitor.failure(time.time(), time.monotonic(), reason)
                else:
                    monitor.observe(snapshot, time.time(), time.monotonic())
                stop.wait(max(0, config.poll_interval - (time.monotonic() - started)))
        return 0
    finally:
        stop.set()
        if sender is not None:
            sender.join(timeout=15)
        store.close()
