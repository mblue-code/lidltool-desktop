from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from lidltool.config import AppConfig
from lidltool.connectors.sdk.manifest import ConnectorManifest
from lidltool.connectors.sdk.offer import (
    DiagnosticsOutput,
    DiscoverOffersResponse,
    FetchOfferDetailResponse,
    GetManifestResponse,
    GetOfferDiagnosticsResponse,
    GetOfferScopeResponse,
    HealthcheckResponse,
    NormalizeOfferResponse,
    OfferReference,
    OfferScopeOutput,
    OfferScopeStore,
    validate_offer_action_request,
)
from lidltool.offers.ingest import derive_offer_fingerprint


class OfferFileFeedConnectorAdapter:
    """Offer connector that reads merchant offers from a local JSON feed."""

    def __init__(self, *, manifest: ConnectorManifest, source_config: AppConfig) -> None:
        self._manifest = manifest
        self._config = source_config

    def invoke_action(self, request: object) -> object:
        validated = validate_offer_action_request(request)
        if validated.action == "get_manifest":
            return GetManifestResponse(output={"manifest": self._manifest})
        if validated.action == "healthcheck":
            return self._healthcheck()
        if validated.action == "discover_offers":
            return self._discover(limit=validated.input.limit)
        if validated.action == "fetch_offer_detail":
            return self._fetch_offer_detail(offer_ref=validated.input.offer_ref)
        if validated.action == "normalize_offer":
            return self._normalize_offer(validated.input.offer)
        if validated.action == "get_offer_scope":
            return self._get_offer_scope()
        if validated.action == "get_offer_diagnostics":
            return self._get_offer_diagnostics()
        raise RuntimeError(f"unsupported offer action: {validated.action}")

    def _healthcheck(self) -> HealthcheckResponse:
        feed_path = self._feed_path()
        if not feed_path.exists():
            return HealthcheckResponse(
                output={
                    "healthy": False,
                    "detail": f"offer feed file missing: {feed_path}",
                    "sample_size": 0,
                    "diagnostics": {"feed_path": str(feed_path)},
                }
            )
        _, offers = self._load_feed()
        return HealthcheckResponse(
            output={
                "healthy": True,
                "detail": f"loaded {len(offers)} offers",
                "sample_size": len(offers),
                "diagnostics": {"feed_path": str(feed_path)},
            }
        )

    def _discover(self, *, limit: int | None) -> DiscoverOffersResponse:
        defaults, offers = self._load_feed()
        selected = offers[:limit] if limit is not None else offers
        references = [
            OfferReference(
                offer_ref=self._offer_ref(offer),
                discovered_at=self._parse_datetime(offer.get("discovered_at")) or datetime.now(tz=UTC),
                valid_from=self._parse_datetime(
                    offer.get("validity_start") or offer.get("valid_from") or defaults.get("validity_start")
                ),
                valid_until=self._parse_datetime(
                    offer.get("validity_end") or offer.get("validity_end_at") or defaults.get("validity_end")
                ),
                metadata={"feed_path": str(self._feed_path())},
            )
            for offer in selected
        ]
        return DiscoverOffersResponse(output={"offers": references, "next_cursor": None})

    def _fetch_offer_detail(self, *, offer_ref: str) -> FetchOfferDetailResponse:
        defaults, offers = self._load_feed()
        for offer in offers:
            if self._offer_ref(offer) == offer_ref:
                merged = {
                    **defaults,
                    **offer,
                    "offer_ref": offer_ref,
                }
                return FetchOfferDetailResponse(output={"offer_ref": offer_ref, "offer": merged})
        raise RuntimeError(f"offer not found: {offer_ref}")

    def _normalize_offer(self, offer: dict[str, Any]) -> NormalizeOfferResponse:
        raw_scope = self._merged_scope(offer)
        validity_start = self._required_datetime(offer, "validity_start")
        validity_end = self._required_datetime(offer, "validity_end")
        merchant_name = self._string(offer, "merchant_name", default=self._manifest.merchant_name)
        source_offer_id = self._offer_ref(offer)
        title = self._string(offer, "title")
        items_in = offer.get("items")
        if not isinstance(items_in, list) or not items_in:
            raise RuntimeError("offer feed record must include a non-empty items list")

        items: list[dict[str, Any]] = []
        for index, raw_item in enumerate(items_in, start=1):
            if not isinstance(raw_item, dict):
                raise RuntimeError("offer items must be objects")
            item_title = self._string(raw_item, "title", default=title)
            alias_candidates = raw_item.get("alias_candidates")
            normalized_aliases = self._normalize_alias_candidates(alias_candidates, fallback=item_title)
            items.append(
                {
                    "line_no": int(raw_item.get("line_no") or index),
                    "source_item_id": raw_item.get("source_item_id"),
                    "title": item_title,
                    "brand": raw_item.get("brand"),
                    "canonical_product_id": raw_item.get("canonical_product_id"),
                    "gtin_ean": raw_item.get("gtin_ean"),
                    "alias_candidates": normalized_aliases,
                    "quantity_text": raw_item.get("quantity_text"),
                    "unit": raw_item.get("unit"),
                    "size_text": raw_item.get("size_text"),
                    "price_cents": self._optional_int(raw_item.get("price_cents")),
                    "original_price_cents": self._optional_int(raw_item.get("original_price_cents")),
                    "discount_percent": self._optional_float(raw_item.get("discount_percent")),
                    "bundle_terms": raw_item.get("bundle_terms"),
                    "raw_payload": dict(raw_item),
                }
            )

        price_cents = self._optional_int(offer.get("price_cents"))
        original_price_cents = self._optional_int(offer.get("original_price_cents"))
        discount_percent = self._optional_float(offer.get("discount_percent"))
        if discount_percent is None and price_cents is not None and original_price_cents:
            discount_percent = round((1 - (price_cents / original_price_cents)) * 100, 3)

        normalized_offer = {
            "source_offer_id": source_offer_id,
            "fingerprint": derive_offer_fingerprint(
                source_id=self._manifest.source_id,
                source_offer_id=source_offer_id,
                merchant_name=merchant_name,
                title=title,
                validity_start=validity_start,
                validity_end=validity_end,
            ),
            "merchant_name": merchant_name,
            "merchant_id": offer.get("merchant_id"),
            "title": title,
            "summary": offer.get("summary"),
            "offer_type": offer.get("offer_type") or "sale",
            "validity_start": validity_start,
            "validity_end": validity_end,
            "currency": self._string(offer, "currency", default="EUR").upper(),
            "price_cents": price_cents,
            "original_price_cents": original_price_cents,
            "discount_percent": discount_percent,
            "bundle_terms": offer.get("bundle_terms"),
            "offer_url": offer.get("offer_url"),
            "image_url": offer.get("image_url"),
            "scope": raw_scope,
            "items": items,
            "raw_payload": dict(offer),
            "metadata": {
                "feed_path": str(self._feed_path()),
                "source_kind": "offer_file_feed",
            },
        }
        return NormalizeOfferResponse(output={"normalized_offer": normalized_offer})

    def _get_offer_scope(self) -> GetOfferScopeResponse:
        defaults, offers = self._load_feed()
        regions: set[str] = set()
        stores: dict[str, OfferScopeStore] = {}
        for offer in offers:
            scope = self._merged_scope({**defaults, **offer})
            region_code = str(scope.get("region_code") or "").strip()
            if region_code:
                regions.add(region_code)
            store_id = str(scope.get("store_id") or "").strip()
            if store_id:
                stores[store_id] = OfferScopeStore(
                    store_id=store_id,
                    store_name=str(scope.get("store_name") or "").strip() or None,
                    region_code=region_code or None,
                )
        output = OfferScopeOutput(
            merchant_name=defaults.get("merchant_name") or self._manifest.merchant_name,
            merchant_id=defaults.get("merchant_id"),
            country_code=str(defaults.get("country_code") or self._manifest.country_code).upper(),
            scope_kind="store" if stores else ("region" if regions else "merchant"),
            regions=tuple(sorted(regions)),
            stores=tuple(sorted(stores.values(), key=lambda store: store.store_id)),
            metadata={"feed_path": str(self._feed_path())},
        )
        return GetOfferScopeResponse(output=output.model_dump(mode="python"))

    def _get_offer_diagnostics(self) -> GetOfferDiagnosticsResponse:
        _, offers = self._load_feed()
        output = DiagnosticsOutput(
            diagnostics={
                "feed_path": str(self._feed_path()),
                "offer_count": len(offers),
                "source_id": self._manifest.source_id,
                "plugin_family": self._manifest.plugin_family,
            }
        )
        return GetOfferDiagnosticsResponse(output=output.model_dump(mode="python"))

    def _feed_path(self) -> Path:
        configured = self._manifest.metadata.get("feed_path")
        if isinstance(configured, str) and configured.strip():
            return Path(configured).expanduser().resolve()
        return (self._config.config_dir / "offers" / f"{self._manifest.source_id}.json").resolve()

    def _load_feed(self) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        feed_path = self._feed_path()
        if not feed_path.exists():
            raise RuntimeError(f"offer feed file missing: {feed_path}")
        payload = json.loads(feed_path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            defaults: dict[str, Any] = {
                "merchant_name": self._manifest.merchant_name,
                "country_code": self._manifest.country_code,
            }
            offers = payload
        elif isinstance(payload, dict):
            defaults = {
                key: value
                for key, value in payload.items()
                if key not in {"offers", "items"}
            }
            offers = payload.get("offers")
        else:
            raise RuntimeError("offer feed file must contain an object or array payload")
        if not isinstance(offers, list):
            raise RuntimeError("offer feed file must contain an offers array")
        normalized_offers: list[dict[str, Any]] = []
        for offer in offers:
            if not isinstance(offer, dict):
                raise RuntimeError("offer feed entries must be objects")
            normalized_offers.append(dict(offer))
        return defaults, normalized_offers

    def _offer_ref(self, offer: dict[str, Any]) -> str:
        for key in ("offer_ref", "source_offer_id", "id"):
            value = offer.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        raise RuntimeError("offer feed record must include offer_ref, source_offer_id, or id")

    def _merged_scope(self, offer: dict[str, Any]) -> dict[str, Any]:
        scope = offer.get("scope")
        if scope is None:
            scope = {}
        if not isinstance(scope, dict):
            raise RuntimeError("offer scope must be an object")
        return {
            "country_code": str(scope.get("country_code") or offer.get("country_code") or self._manifest.country_code).upper(),
            "region_code": scope.get("region_code") or offer.get("region_code"),
            "store_id": scope.get("store_id") or offer.get("store_id"),
            "store_name": scope.get("store_name") or offer.get("store_name"),
        }

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
        if isinstance(value, str) and value.strip():
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
            return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
        return None

    def _required_datetime(self, offer: dict[str, Any], key: str) -> datetime:
        value = self._parse_datetime(offer.get(key))
        if value is None:
            raise RuntimeError(f"offer feed record missing required datetime field: {key}")
        return value

    @staticmethod
    def _string(payload: dict[str, Any], key: str, *, default: str | None = None) -> str:
        value = payload.get(key, default)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if default is not None and default.strip():
            return default.strip()
        raise RuntimeError(f"offer feed record missing required field: {key}")

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        if value is None or value == "":
            return None
        return int(value)

    @staticmethod
    def _optional_float(value: Any) -> float | None:
        if value is None or value == "":
            return None
        return float(value)

    @staticmethod
    def _normalize_alias_candidates(value: Any, *, fallback: str) -> list[str]:
        candidates = value if isinstance(value, list) else []
        normalized: list[str] = []
        seen: set[str] = set()
        for raw in [*candidates, fallback]:
            if not isinstance(raw, str):
                continue
            candidate = raw.strip()
            if not candidate:
                continue
            lowered = candidate.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            normalized.append(candidate)
        return normalized
