from __future__ import annotations

from pathlib import Path

from lidltool.config import AppConfig, resolve_config_dir


def default_amazon_state_file(
    config: AppConfig | None = None,
    *,
    source_id: str = "amazon_de",
) -> Path:
    config_dir = config.config_dir if config is not None else resolve_config_dir()
    filename = "amazon_storage_state.json" if source_id == "amazon_de" else f"{source_id}_storage_state.json"
    return (config_dir / filename).expanduser().resolve()


def ensure_state_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
