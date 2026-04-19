from __future__ import annotations

from pathlib import Path

from lidltool.connectors.runtime.runner import load_entrypoint


def test_load_entrypoint_allows_sibling_module_imports_for_file_entrypoints(tmp_path: Path) -> None:
    payload_dir = tmp_path / "payload"
    payload_dir.mkdir(parents=True, exist_ok=True)
    (payload_dir / "helper.py").write_text("VALUE = 'rossmann-ok'\n", encoding="utf-8")
    (payload_dir / "plugin.py").write_text(
        "\n".join(
            (
                "from helper import VALUE",
                "",
                "class FixtureRuntime:",
                "    def __init__(self) -> None:",
                "        self.value = VALUE",
            )
        )
        + "\n",
        encoding="utf-8",
    )

    runtime = load_entrypoint(f"{payload_dir / 'plugin.py'}:FixtureRuntime")

    assert getattr(runtime, "value") == "rossmann-ok"
