import logging
import sys
from typing import Optional


_DEFAULT_FORMAT = "%(asctime)s %(levelname)s %(message)s"


def _ensure_root_handler() -> None:
    root_logger = logging.getLogger()
    if root_logger.handlers:
        return
    handler = logging.StreamHandler(stream=sys.stdout)
    formatter = logging.Formatter(_DEFAULT_FORMAT)
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)


class _TaggedAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        tag = self.extra.get("tag", "")
        if tag and not str(msg).startswith(tag):
            msg = f"{tag} {msg}"
        return msg, kwargs


def get_logger(tag: str, name: Optional[str] = None) -> logging.Logger:
    """
    Return a logger that injects a [TAG] prefix into records.
    Example: logger = get_logger("APP") → logs like: [APP] message
    """
    _ensure_root_handler()
    logger_name = name or __name__
    base = logging.getLogger(logger_name)
    return _TaggedAdapter(base, {"tag": f"[{tag}]"})


