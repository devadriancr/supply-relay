import logging
from logging.handlers import RotatingFileHandler

from relay.config import Settings


def setup_logging(settings: Settings) -> None:
    root = logging.getLogger("relay")
    if root.handlers:
        return
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(settings.log_dir / "relay.log", maxBytes=1_000_000, backupCount=5, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root.addHandler(handler)
    root.setLevel(logging.INFO)
