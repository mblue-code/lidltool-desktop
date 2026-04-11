from __future__ import annotations

from lidltool.connectors.stub_adapter import StubConnectorAdapter


class EdekaConnectorAdapter(StubConnectorAdapter):
    def __init__(self, *, source: str = "edeka_de", store_name: str = "EDEKA") -> None:
        super().__init__(source=source, store_name=store_name)
