"""Denver time for reporting, monotonic for calculating elapsed time"""

from datetime import datetime
import logging
from zoneinfo import ZoneInfo

DENVER = ZoneInfo("America/Denver")
DISPLAY_TIME_FORMAT = "%Y-%m-%d %H:%M:%S %Z (%z)"


def format_timestamp(timestamp, datefmt=None):
    return datetime.fromtimestamp(timestamp, DENVER).strftime(datefmt or DISPLAY_TIME_FORMAT)


class DenverFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        return format_timestamp(record.created, datefmt)