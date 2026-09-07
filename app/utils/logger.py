"""Basit dosya loglama sistemi."""
import logging
import os
from logging.handlers import RotatingFileHandler

from app.utils.paths import logs_dir

LOGGER_NAME = "yt_ara"


def setup_logger() -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    os.makedirs(logs_dir(), exist_ok=True)
    handler = RotatingFileHandler(
        os.path.join(logs_dir(), "uygulama.log"),
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    logger.addHandler(handler)
    logger.propagate = False
    return logger


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"{LOGGER_NAME}.{name}")
