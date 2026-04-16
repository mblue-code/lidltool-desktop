from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any
from unittest.mock import Mock

from lidltool.connectors.runtime.host import (
    ConnectorRuntimeHost,
    ConnectorRuntimeTarget,
    RuntimeHostedReceiptConnector,
)
from lidltool.connectors.sdk.manifest import ConnectorManifest
from lidltool.connectors.sdk.version import RECEIPT_CONNECTOR_API_VERSION


class _StreamingConnector:
    def discover_new_records_with_progress(
        self,
        *,
        progress_cb: Callable[[int, int], None] | None = None,
    ) -> list[str]:
        if progress_cb is not None:
            progress_cb(2, 3)
        return ["alpha", "beta", "gamma"]

    def stream_record_details_with_progress(
        self,
        *,
        max_pages: int | None = None,
        progress_cb: Callable[[dict[str, Any]], None] | None = None,
    ) -> Iterator[tuple[str, dict[str, Any]]]:
        if progress_cb is not None:
            progress_cb({"pages": 2, "current_year": 2025, "current_page": 1})
        yield "alpha", {"id": "alpha", "max_pages": max_pages}
        yield "beta", {"id": "beta", "max_pages": max_pages}


def _manifest() -> ConnectorManifest:
    return ConnectorManifest(
        plugin_id="builtin.amazon_de",
        plugin_version="1.0.0",
        connector_api_version=RECEIPT_CONNECTOR_API_VERSION,
        plugin_family="receipt",
        source_id="amazon_de",
        display_name="Amazon",
        merchant_name="Amazon",
        country_code="DE",
        runtime_kind="builtin",
        entrypoint="builtin",
        auth_kind="browser_session",
        capabilities=("auth.session", "read.receipts"),
        trust_class="official",
        plugin_origin="builtin",
        install_status="bundled",
    )


def test_runtime_hosted_connector_forwards_discovery_progress_to_builtin_connector() -> None:
    connector = RuntimeHostedReceiptConnector(
        host=ConnectorRuntimeHost(),
        target=ConnectorRuntimeTarget(
            manifest=_manifest(),
            connector=_StreamingConnector(),
        ),
    )

    progress_updates: list[tuple[int, int]] = []
    records = connector.discover_new_records_with_progress(
        progress_cb=lambda page_count, receipt_count: progress_updates.append(
            (page_count, receipt_count)
        )
    )

    assert records == ["alpha", "beta", "gamma"]
    assert progress_updates == [(2, 3)]


def test_runtime_hosted_connector_forwards_streaming_records_to_builtin_connector() -> None:
    connector = RuntimeHostedReceiptConnector(
        host=ConnectorRuntimeHost(),
        target=ConnectorRuntimeTarget(
            manifest=_manifest(),
            connector=_StreamingConnector(),
        ),
    )

    progress_updates: list[dict[str, Any]] = []
    streamed = list(
        connector.stream_record_details_with_progress(
            max_pages=8,
            progress_cb=progress_updates.append,
        )
    )

    assert streamed == [
        ("alpha", {"id": "alpha", "max_pages": 8}),
        ("beta", {"id": "beta", "max_pages": 8}),
    ]
    assert progress_updates == [{"pages": 2, "current_year": 2025, "current_page": 1}]


def test_runtime_hosted_connector_falls_back_without_recursive_streaming_delegate() -> None:
    connector = RuntimeHostedReceiptConnector(
        host=ConnectorRuntimeHost(),
        target=ConnectorRuntimeTarget(
            manifest=_manifest().model_copy(
                update={
                    "plugin_id": "local.kaufland_de",
                    "source_id": "kaufland_de",
                    "runtime_kind": "subprocess_python",
                    "entrypoint": "payload/plugin.py:KauflandReceiptPlugin",
                    "plugin_origin": "local_path",
                    "trust_class": "local_custom",
                    "install_status": "installed",
                }
            ),
        ),
    )
    connector.discover_new_records = Mock(return_value=["alpha", "beta"])  # type: ignore[method-assign]
    connector.fetch_record_detail = Mock(  # type: ignore[method-assign]
        side_effect=lambda record_ref: {"id": record_ref, "source": "kaufland_de"}
    )

    progress_updates: list[tuple[int, int]] = []
    records = connector.discover_new_records_with_progress(
        progress_cb=lambda page_count, receipt_count: progress_updates.append((page_count, receipt_count))
    )
    streamed = list(connector.stream_record_details_with_progress(max_pages=4))

    assert records == ["alpha", "beta"]
    assert progress_updates == [(1, 2)]
    assert streamed == [
        ("alpha", {"id": "alpha", "source": "kaufland_de"}),
        ("beta", {"id": "beta", "source": "kaufland_de"}),
    ]
