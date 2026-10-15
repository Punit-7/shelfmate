import contextvars
import json
import logging
import logging.config
import sys
import time
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from logging.handlers import SMTPHandler
from pathlib import Path

from shelfmate.config import settings

run_id = contextvars.ContextVar("run_id", default="-")

SECRET_WORDS = ("password", "secret", "token", "api_key", "authorization")
STANDARD = set(vars(logging.makeLogRecord({}))) | {
    "message",
    "asctime",
    "run_id",
    "service",
}


class ContextFilter(logging.Filter):
    """Adds the service name and run ID to every record, and hides secret values."""

    def __init__(self, service: str):
        super().__init__()
        self.service = service

    def filter(self, record: logging.LogRecord) -> bool:
        record.service = self.service
        record.run_id = run_id.get()
        for key in list(vars(record)):
            if key not in STANDARD and any(w in key.lower() for w in SECRET_WORDS):
                setattr(record, key, "***")
        return True


class JsonFormatter(logging.Formatter):
    """Writes each record as one JSON object on one line."""

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(
                timespec="milliseconds"
            ),
            "level": record.levelname,
            "service": getattr(record, "service", "-"),
            "run_id": getattr(record, "run_id", "-"),
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "process": record.process,
            "thread": record.threadName,
        }
        entry.update({k: v for k, v in vars(record).items() if k not in STANDARD})
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str, ensure_ascii=False)


class Throttle(logging.Filter):
    """Lets each message through at most once every `seconds`, so one fault cannot flood your inbox."""

    def __init__(self, seconds: int = 600):
        super().__init__()
        self.seconds = seconds
        self.last_sent: dict[str, float] = {}

    def filter(self, record: logging.LogRecord) -> bool:
        key = f"{record.name}:{record.msg}"
        now = time.monotonic()
        if now - self.last_sent.get(key, float("-inf")) < self.seconds:
            return False
        self.last_sent[key] = now
        return True


def _log_uncaught(exc_type, exc, tb) -> None:
    """Logs any error that nothing caught, just before the program stops."""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc, tb)
        return
    logging.getLogger("shelfmate").critical(
        "Uncaught error, program stopped", exc_info=(exc_type, exc, tb)
    )


def _email_alerts(service: str) -> None:
    """Emails you each ERROR or CRITICAL line, at most once per message every 10 minutes."""
    handler = SMTPHandler(
        mailhost=("smtp.gmail.com", 587),
        fromaddr=settings.email_address,
        toaddrs=[settings.email_address],
        subject=f"[Shelfmate] Error in {service}",
        credentials=(settings.email_address, settings.email_app_password),
        secure=(),
    )
    handler.setLevel(logging.ERROR)
    handler.addFilter(ContextFilter(service))
    handler.addFilter(Throttle(seconds=600))
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s\nservice=%(service)s run_id=%(run_id)s\n\n%(message)s"
        )
    )
    logging.getLogger("shelfmate").addHandler(handler)


def setup_logging(service: str) -> None:
    """Call once, at the start of each program: the API, a script or a flow."""
    log_dir = Path(settings.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "filters": {"context": {"()": ContextFilter, "service": service}},
            "formatters": {
                "console": {
                    "format": "%(asctime)s %(levelname)-8s %(name)s [%(run_id)s] %(message)s"
                },
                "json": {"()": JsonFormatter},
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "level": settings.log_level,
                    "formatter": "console",
                    "filters": ["context"],
                },
                "file": {
                    "class": "logging.handlers.RotatingFileHandler",
                    "level": "DEBUG",
                    "formatter": "json",
                    "filters": ["context"],
                    "filename": str(log_dir / f"{service}.jsonl"),
                    "maxBytes": 10_000_000,
                    "backupCount": 5,
                    "encoding": "utf-8",
                },
            },
            "loggers": {
                "shelfmate": {
                    "level": "DEBUG",
                    "handlers": ["console", "file"],
                    "propagate": False,
                },
                "httpx": {"level": "WARNING"},
            },
            "root": {"level": "WARNING", "handlers": ["console"]},
        }
    )
    sys.excepthook = _log_uncaught
    if settings.alert_errors_by_email and settings.email_address:
        _email_alerts(service)


def new_run(prefix: str) -> str:
    """Gives this run a short unique ID that appears on every log line."""
    rid = f"{prefix}-{uuid.uuid4().hex[:8]}"
    run_id.set(rid)
    return rid


@contextmanager
def timed(logger: logging.Logger, action: str, **fields):
    """Logs how long a block took. If the block fails, logs the error with its stack trace."""
    start = time.perf_counter()
    try:
        yield
    except Exception:
        ms = round((time.perf_counter() - start) * 1000, 1)
        logger.exception(
            "%s failed after %.1f ms",
            action,
            ms,
            extra={"action": action, "duration_ms": ms, **fields},
            stacklevel=3,
        )
        raise
    ms = round((time.perf_counter() - start) * 1000, 1)
    logger.info(
        "%s finished in %.1f ms",
        action,
        ms,
        extra={"action": action, "duration_ms": ms, **fields},
        stacklevel=3,
    )
