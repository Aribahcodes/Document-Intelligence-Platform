"""
Application-wide logging configuration.

Logs go to stdout (captured by the deployment platform) and to a
rotating file under data/logs for local troubleshooting. Never logs
secrets or full stack traces to API responses - only to the log sink.
"""
import logging
import sys
from logging.handlers import RotatingFileHandler

from app.core.config import Config


def configure_logging():
    root_logger = logging.getLogger()
    root_logger.setLevel(Config.LOG_LEVEL)

    if root_logger.handlers:
        return root_logger

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    root_logger.addHandler(stream_handler)

    try:
        file_handler = RotatingFileHandler(
            Config.LOG_DIR / "app.log", maxBytes=2_000_000, backupCount=3
        )
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    except OSError:
        root_logger.warning("Could not attach file log handler; continuing with stdout logging only")

    return root_logger


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
