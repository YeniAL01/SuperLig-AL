"""Structured application logging."""
import logging
from config.settings import Settings

def configure_logging(settings: Settings) -> logging.Logger:
    """Configure console and rotating file logging once per process."""
    settings.ensure_directories()
    logger = logging.getLogger("superlig_al")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    file_handler = logging.FileHandler(settings.log_dir / "superlig-al.log", encoding="utf-8")
    stream_handler = logging.StreamHandler()
    for handler in (file_handler, stream_handler):
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return logger
