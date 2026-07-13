"""
Centralized logging configuration.
- Colored console output for dev terminals (ANSI)
- JSON Lines output for production / Docker (non-TTY)
- Request ID injection via contextvar
- Rotating file handler for persistent logs
"""

import logging
import sys
import json
import os
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from typing import Optional


class Colors:
    RESET     = "\033[0m"
    BOLD      = "\033[1m"
    DIM       = "\033[2m"
    RED       = "\033[31m"
    GREEN     = "\033[32m"
    YELLOW    = "\033[33m"
    BLUE      = "\033[34m"
    MAGENTA   = "\033[35m"
    CYAN      = "\033[36m"
    WHITE     = "\033[37m"
    RED_BG    = "\033[41m\033[37m"

    @classmethod
    def level_color(cls, levelname: str) -> str:
        return {
            "DEBUG":    cls.BLUE,
            "INFO":     cls.GREEN,
            "WARNING":  cls.YELLOW,
            "WARN":     cls.YELLOW,
            "ERROR":    cls.RED + cls.BOLD,
            "CRITICAL": cls.RED_BG,
        }.get(levelname, cls.WHITE)

    @classmethod
    def duration_color(cls, ms: float) -> str:
        if ms < 100:
            return cls.GREEN
        elif ms < 1000:
            return cls.YELLOW
        return cls.RED


class RequestIDFilter(logging.Filter):
    """Inject request_id from contextvar into every log record."""

    def filter(self, record):
        import contextvars
        try:
            req_id = contextvars.ContextVar("request_id").get()
        except LookupError:
            req_id = "-"
        record.request_id = str(req_id) if req_id and req_id != "-" else ""
        return True


class ColoredFormatter(logging.Formatter):
    """Human-readable colored output for dev terminals."""

    def format(self, record: logging.LogRecord) -> str:
        ts   = f"{Colors.DIM}{self.formatTime(record, '%H:%M:%S')}{Colors.RESET}"
        lvl  = f"{Colors.level_color(record.levelname)}{record.levelname:<7}{Colors.RESET}"
        parts = record.name.rsplit(".", 1)
        mod  = f"{Colors.MAGENTA}{parts[-1]:<16}{Colors.RESET}"
        rid  = f"{Colors.CYAN}[{record.request_id}]{Colors.RESET} " if record.request_id else ""
        msg  = record.getMessage()

        if record.exc_info and record.exc_info[1]:
            msg += f"\n    {Colors.RED}{self.formatException(record.exc_info)}{Colors.RESET}"

        return f"{ts}  {lvl}  {mod}  {rid}{msg}"

    def formatTime(self, record, datefmt=None):
        dt = datetime.fromtimestamp(record.created)
        return dt.strftime("%H:%M:%S") + f".{dt.microsecond // 1000:03d}"


class JSONFormatter(logging.Formatter):
    """Structured JSON Lines output for log aggregation tools."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "ts":        datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "level":     record.levelname,
            "module":    record.name,
            "req_id":    getattr(record, "request_id", ""),
            "message":   record.getMessage(),
        }
        if record.exc_info and record.exc_info[1]:
            log_entry["error"] = str(record.exc_info[1])
            log_entry["traceback"] = self.formatException(record.exc_info)

        for attr in ("step", "duration_ms", "candidates", "province", "score",
                     "distance_km", "itinerary_id", "solver", "fallback"):
            val = getattr(record, attr, None)
            if val is not None:
                log_entry[attr] = val

        return json.dumps(log_entry, ensure_ascii=False, default=str)


def setup_logging(
    level: str = "INFO",
    log_dir: Optional[str] = None,
    log_file: str = "heritage.log",
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 5,
):
    """
    Configure application-wide logging.
    Called once at startup in api_gateway and ai_service.
    """
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.handlers.clear()

    req_filter = RequestIDFilter()

    is_tty = sys.stdout.isatty()
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.DEBUG)
    console.addFilter(req_filter)
    console.setFormatter(ColoredFormatter() if is_tty else JSONFormatter())
    root.addHandler(console)

    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
        file_path = os.path.join(log_dir, log_file)
        fh = RotatingFileHandler(file_path, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.addFilter(req_filter)
        fh.setFormatter(JSONFormatter())
        root.addHandler(fh)

    for noisy in ("uvicorn.access", "uvicorn.error", "httpx", "httpcore", "urllib3", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    logger = logging.getLogger("heritage")
    logger.info("Logging initialized  level=%s  tty=%s  file_dir=%s",
                level, is_tty, log_dir or "none")
    return logger
