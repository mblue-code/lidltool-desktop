from __future__ import annotations

from pathlib import Path

from lidltool.config import AppConfig, resolve_config_dir


def default_rewe_state_file(config: AppConfig | None = None) -> Path:
    config_dir = config.config_dir if config is not None else resolve_config_dir()
    return (config_dir / "rewe_storage_state.json").expanduser().resolve()


def ensure_state_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
