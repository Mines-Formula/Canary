"""Heartbeat transport and Denver logging shared by Windows and Linux."""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

import requests

from canary.timeutils import DenverFormatter

logger = logging.getLogger(__name__)


def configure_logging(log_file=None):
    handlers = [logging.StreamHandler()]
    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        handlers.append(RotatingFileHandler(log_file, maxBytes=5 * 1024**2, backupCount=3, encoding="utf-8"))
    for handler in handlers:
        handler.setFormatter(DenverFormatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=handlers)


def send_heartbeat(url, api_key, service, status="ok", message=None):
    try:
        response = requests.post(url, json={"service": service, "status": status, "message": message},
                                 headers={"X-API-Key": api_key}, timeout=(3, 5))
        response.raise_for_status()
    except requests.RequestException as error:
        # Exceptions/response bodies can contain private URLs or headers.
        code = getattr(getattr(error, "response", None), "status_code", None)
        logger.warning("Heartbeat failed for %s (%s, HTTP status: %s)", service, type(error).__name__, code or "unavailable")
        return False
    logger.info("Heartbeat sent (%s: %s)", service, status)
    return True
