from __future__ import annotations

from lidltool.connectors.stub_adapter import StubConnectorAdapter


class NettoConnectorAdapter(StubConnectorAdapter):
    def __init__(self, *, source: str = "netto_de", store_name: str = "Netto") -> None:
        super().__init__(source=source, store_name=store_name)
