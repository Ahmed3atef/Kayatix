"""
Kayatix System Timezone Manager.
Handles reading, validating, and formatting datetimes and logs according to the
country timezone configured in .env (e.g., Africa/Cairo, Asia/Riyadh, UTC, Europe/London).
"""

from datetime import datetime, timezone
import functools
import logging
import sys
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.config import settings

logger = logging.getLogger("kayatix.timezone")


@functools.lru_cache(maxsize=64)
def get_timezone_obj(tz_name: Optional[str]) -> ZoneInfo:
    """
    Returns a cached ZoneInfo instance for the given timezone name.
    Gracefully falls back to UTC if the timezone string is invalid, unparseable, or empty.
    """
    if not tz_name:
        return ZoneInfo("UTC")

    cleaned = str(tz_name).strip().strip("'\"")
    try:
        return ZoneInfo(cleaned)
    except (ZoneInfoNotFoundError, Exception) as exc:
        logger.warning(
            f"[Timezone] Unrecognized or invalid timezone '{cleaned}': {exc}. Falling back to UTC."
        )
        return ZoneInfo("UTC")


def get_app_timezone() -> ZoneInfo:
    """
    Returns the active application ZoneInfo based on the configured TIMEZONE in settings.
    """
    tz_name = getattr(settings, "TIMEZONE", None) or "UTC"
    return get_timezone_obj(tz_name)


def get_current_time(tz: Optional[ZoneInfo] = None) -> datetime:
    """
    Returns the current datetime in the configured application country timezone.
    Returned as a naive datetime representing the country's local wall-clock time,
    ensuring 100% seamless database insertion across PostgreSQL (asyncpg), SQLite,
    and SQLAlchemy without timezone mismatch errors.
    """
    active_tz = tz or get_app_timezone()
    return datetime.now(active_tz).replace(tzinfo=None)


def get_current_aware_time(tz: Optional[ZoneInfo] = None) -> datetime:
    """
    Returns current datetime with active timezone information attached.
    """
    active_tz = tz or get_app_timezone()
    return datetime.now(active_tz)


def format_localized_time(
    dt: Optional[datetime], fmt: str = "%Y-%m-%d %H:%M"
) -> str:
    """
    Formats a datetime object to a localized string.
    """
    if dt is None:
        return "N/A"
    return dt.strftime(fmt)


class TimezoneFormatter(logging.Formatter):
    """
    Custom logging formatter that renders timestamps in the configured country timezone.
    """

    def __init__(
        self,
        fmt: Optional[str] = None,
        datefmt: Optional[str] = None,
        style: str = "%",
        validate: bool = True,
        tz_name: Optional[str] = None,
    ):
        super().__init__(fmt=fmt, datefmt=datefmt, style=style, validate=validate)
        self.tz_name = tz_name

    def formatTime(self, record: logging.LogRecord, datefmt: Optional[str] = None) -> str:
        tz = get_timezone_obj(self.tz_name) if self.tz_name else get_app_timezone()
        dt = datetime.fromtimestamp(record.created, tz=tz)
        if datefmt:
            return dt.strftime(datefmt)
        return dt.strftime("%Y-%m-%d %H:%M:%S %Z")


def configure_timezone_logging(
    level: int = logging.INFO,
    datefmt: str = "%Y-%m-%d %H:%M:%S",
    fmt: str = "%(asctime)s | %(levelname)-7s | [%(name)s] %(message)s",
) -> logging.Handler:
    """
    Configures root console handler with TimezoneFormatter so all loggers
    format timestamps in the configured country timezone.
    """
    handler = logging.StreamHandler(sys.stdout)
    formatter = TimezoneFormatter(fmt=fmt, datefmt=datefmt)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.handlers = [h for h in root_logger.handlers if not isinstance(h, logging.StreamHandler)]
    root_logger.addHandler(handler)
    return handler
