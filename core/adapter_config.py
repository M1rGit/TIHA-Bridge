from __future__ import annotations
import logging
from pathlib import Path
import yaml

logger = logging.getLogger(__name__)

CONFIG_PATH = Path("config.yaml")

_DEFAULT = {
    "adapters": {
        "max": True,
        "telegram": True,
        "discord": True,
    }
}


def _load() -> dict:
    if not CONFIG_PATH.exists():
        _save(_DEFAULT)
        return _DEFAULT
    try:
        with CONFIG_PATH.open(encoding="utf-8") as f:
            return yaml.safe_load(f) or _DEFAULT
    except Exception as e:
        logger.error("Failed to load config.yaml: %s", e)
        return _DEFAULT


def _save(data: dict) -> None:
    with CONFIG_PATH.open("w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True)


def is_enabled(platform: str) -> bool:
    """Читает актуальное состояние с диска — hot reload без перезапуска."""
    data = _load()
    return bool(data.get("adapters", {}).get(platform, True))


def set_enabled(platform: str, enabled: bool) -> None:
    data = _load()
    data.setdefault("adapters", {})[platform] = enabled
    _save(data)
    logger.info("Adapter '%s' set to %s", platform, "enabled" if enabled else "disabled")


def all_states() -> dict[str, bool]:
    return _load().get("adapters", {})
