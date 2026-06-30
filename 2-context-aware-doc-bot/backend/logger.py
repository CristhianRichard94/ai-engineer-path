import logging
import json
import os
from logging.handlers import RotatingFileHandler


class _JsonFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            **({"exc": self.formatException(record.exc_info)} if record.exc_info else {}),
        })


def get_logger(name="doc_bot"):
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    env = os.getenv("APP_ENV", "development")
    logger.setLevel(logging.DEBUG)

    if env == "production":
        # stdout JSON — let container/aggregator handle it
        handler = logging.StreamHandler()
        handler.setLevel(logging.INFO)
        handler.setFormatter(_JsonFormatter())
    else:
        fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

        handler = RotatingFileHandler("app.log", maxBytes=5 * 1024 * 1024, backupCount=3)
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(fmt)

        console = logging.StreamHandler()
        console.setLevel(logging.DEBUG)
        console.setFormatter(fmt)
        logger.addHandler(console)

    logger.addHandler(handler)
    return logger
