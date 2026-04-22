from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from fastapi import FastAPI
from fastapi.routing import APIRoute, APIWebSocketRoute

RouteAuthCategory = Literal[
    "public",
    "authenticated_principal",
    "authenticated_user_session",
    "authenticated_api_key",
    "admin_only",
]


@dataclass(frozen=True, slots=True)
class RouteAuthPolicy:
    method: str
    path: str
    category: RouteAuthCategory


HTTP_ROUTE_AUTH_MATRIX: tuple[RouteAuthPolicy, ...] = (
    RouteAuthPolicy("GET", "/api/v1/health", "public"),
    RouteAuthPolicy("GET", "/api/v1/ready", "public"),
    RouteAuthPolicy("GET", "/api/v1/auth/setup-required", "public"),
    RouteAuthPolicy("POST", "/api/v1/auth/setup", "public"),
    RouteAuthPolicy("POST", "/api/v1/auth/login", "public"),
    RouteAuthPolicy("POST", "/api/v1/auth/logout", "authenticated_user_session"),
    RouteAuthPolicy("GET", "/api/v1/auth/me", "authenticated_user_session"),
    RouteAuthPolicy("GET", "/api/v1/auth/sessions", "authenticated_user_session"),
    RouteAuthPolicy("DELETE", "/api/v1/auth/sessions/{session_id}", "authenticated_user_session"),
    RouteAuthPolicy("PATCH", "/api/v1/users/me/preferences", "authenticated_user_session"),
    RouteAuthPolicy("GET", "/api/v1/mobile/devices", "authenticated_user_session"),
    RouteAuthPolicy("POST", "/api/v1/mobile/devices", "authenticated_user_session"),
    RouteAuthPolicy("PUT", "/api/v1/mobile/devices/current", "authenticated_user_session"),
    RouteAuthPolicy("DELETE", "/api/v1/mobile/devices/current", "authenticated_user_session"),
    RouteAuthPolicy("DELETE", "/api/v1/mobile/devices/{device_id}", "authenticated_user_session"),
    RouteAuthPolicy("GET", "/api/v1/auth/keys", "authenticated_user_session"),
    RouteAuthPolicy("POST", "/api/v1/auth/keys", "authenticated_user_session"),
    RouteAuthPolicy("DELETE", "/api/v1/auth/keys/{key_id}", "authenticated_user_session"),
    RouteAuthPolicy("GET", "/api/v1/users", "admin_only"),
    RouteAuthPolicy("POST", "/api/v1/users", "admin_only"),
    RouteAuthPolicy("PATCH", "/api/v1/users/{user_id}", "admin_only"),
    RouteAuthPolicy("DELETE", "/api/v1/users/{user_id}", "admin_only"),
    RouteAuthPolicy("POST", "/api/v1/system/backup", "admin_only"),
    RouteAuthPolicy("POST", "/api/v1/documents/upload", "authenticated_principal"),
    RouteAuthPolicy("POST", "/api/v1/documents/{document_id}/process", "authenticated_principal"),
    RouteAuthPolicy("GET", "/api/v1/documents/{document_id}/status", "authenticated_principal"),
    RouteAuthPolicy("GET", "/api/v1/review-queue", "authenticated_principal"),
    RouteAuthPolicy("GET", "/api/v1/transactions", "authenticated_principal"),
    RouteAuthPolicy("GET", "/api/v1/items/search", "authenticated_principal"),
    RouteAuthPolicy("GET", "/api/v1/items/aggregate", "authenticated_principal"),
    RouteAuthPolicy("POST", "/api/v1/transactions/manual", "authenticated_principal"),
    RouteAuthPolicy("GET", "/api/v1/transactions/{transaction_id}", "authenticated_principal"),
    RouteAuthPolicy("GET", "/api/v1/transactions/{transaction_id}/history", "authenticated_principal"),
    RouteAuthPolicy("GET", "/api/v1/documents/{document_id}/preview", "authenticated_principal"),
    RouteAuthPolicy("PATCH", "/api/v1/transactions/{transaction_id}/overrides", "authenticated_principal"),
    RouteAuthPolicy("POST", "/api/v1/chat/threads", "authenticated_principal"),
    RouteAuthPolicy("GET", "/api/v1/chat/threads", "authenticated_principal"),
    RouteAuthPolicy("GET", "/api/v1/chat/threads/{thread_id}", "authenticated_principal"),
    RouteAuthPolicy("PATCH", "/api/v1/chat/threads/{thread_id}", "authenticated_principal"),
    RouteAuthPolicy("DELETE", "/api/v1/chat/threads/{thread_id}", "authenticated_principal"),
    RouteAuthPolicy("GET", "/api/v1/chat/threads/{thread_id}/messages", "authenticated_principal"),
    RouteAuthPolicy("POST", "/api/v1/chat/threads/{thread_id}/messages", "authenticated_principal"),
    RouteAuthPolicy("POST", "/api/v1/chat/threads/{thread_id}/stream", "authenticated_principal"),
    RouteAuthPolicy("POST", "/api/v1/chat/threads/{thread_id}/runs", "authenticated_principal"),
    RouteAuthPolicy("GET", "/api/v1/automations", "admin_only"),
    RouteAuthPolicy("POST", "/api/v1/automations", "admin_only"),
    RouteAuthPolicy("GET", "/api/v1/automations/executions", "admin_only"),
    RouteAuthPolicy("GET", "/api/v1/automations/{rule_id}", "admin_only"),
    RouteAuthPolicy("PATCH", "/api/v1/automations/{rule_id}", "admin_only"),
    RouteAuthPolicy("DELETE", "/api/v1/automations/{rule_id}", "admin_only"),
    RouteAuthPolicy("POST", "/api/v1/automations/{rule_id}/run", "admin_only"),
    RouteAuthPolicy("GET", "/api/v1/offers", "authenticated_principal"),
    RouteAuthPolicy("GET", "/api/v1/offers/sources", "authenticated_principal"),
    RouteAuthPolicy("POST", "/api/v1/offers/sources", "authenticated_principal"),
    RouteAuthPolicy("PATCH", "/api/v1/offers/sources/{source_id}", "authenticated_principal"),
    RouteAuthPolicy("DELETE", "/api/v1/offers/sources/{source_id}", "authenticated_principal"),
    RouteAuthPolicy("GET", "/api/v1/offers/merchant-items", "authenticated_principal"),
    RouteAuthPolicy("POST", "/api/v1/offers/refresh", "authenticated_principal"),
    RouteAuthPolicy("GET", "/api/v1/offers/refresh-runs", "authenticated_principal"),
    RouteAuthPolicy("GET", "/api/v1/offers/watchlists", "authenticated_principal"),
    RouteAuthPolicy("POST", "/api/v1/offers/watchlists", "authenticated_principal"),
    RouteAuthPolicy("PATCH", "/api/v1/offers/watchlists/{watchlist_id}", "authenticated_principal"),
    RouteAuthPolicy("DELETE", "/api/v1/offers/watchlists/{watchlist_id}", "authenticated_principal"),
    RouteAuthPolicy("GET", "/api/v1/offers/matches", "authenticated_principal"),
    RouteAuthPolicy("GET", "/api/v1/offers/alerts", "authenticated_principal"),
    RouteAuthPolicy("PATCH", "/api/v1/offers/alerts/{alert_id}", "authenticated_principal"),
    RouteAuthPolicy("GET", "/api/v1/recurring-bills", "authenticated_principal"),
    RouteAuthPolicy("POST", "/api/v1/recurring-bills", "authenticated_principal"),
    RouteAuthPolicy("GET", "/api/v1/recurring-bills/analytics/overview", "authenticated_principal"),
    RouteAuthPolicy("GET", "/api/v1/recurring-bills/analytics/calendar", "authenticated_principal"),
    RouteAuthPolicy("GET", "/api/v1/recurring-bills/analytics/forecast", "authenticated_principal"),
    RouteAuthPolicy("GET", "/api/v1/recurring-bills/analytics/gaps", "authenticated_principal"),
    RouteAuthPolicy("PATCH", "/api/v1/recurring-bills/occurrences/{occ_id}/status", "authenticated_principal"),
    RouteAuthPolicy("POST", "/api/v1/recurring-bills/occurrences/{occ_id}/skip", "authenticated_principal"),
    RouteAuthPolicy("POST", "/api/v1/recurring-bills/occurrences/{occ_id}/reconcile", "authenticated_principal"),
    RouteAuthPolicy("GET", "/api/v1/recurring-bills/{bill_id}/occurrences", "authenticated_principal"),
    RouteAuthPolicy("POST", "/api/v1/recurring-bills/{bill_id}/occurrences/generate", "authenticated_principal"),
    RouteAuthPolicy("POST", "/api/v1/recurring-bills/{bill_id}/match", "authenticated_principal"),
    RouteAuthPolicy("GET", "/api/v1/recurring-bills/{bill_id}", "authenticated_principal"),
    RouteAuthPolicy("PATCH", "/api/v1/recurring-bills/{bill_id}", "authenticated_principal"),
    RouteAuthPolicy("DELETE", "/api/v1/recurring-bills/{bill_id}", "authenticated_principal"),
    RouteAuthPolicy("GET", "/api/v1/dashboard/cards", "authenticated_principal"),
    RouteAuthPolicy("GET", "/api/v1/dashboard/years", "authenticated_principal"),
    RouteAuthPolicy("GET", "/api/v1/dashboard/summary", "authenticated_principal"),
    RouteAuthPolicy("GET", "/api/v1/dashboard/overview", "authenticated_principal"),
    RouteAuthPolicy("GET", "/api/v1/dashboard/trends", "authenticated_principal"),
    RouteAuthPolicy("GET", "/api/v1/dashboard/savings-breakdown", "authenticated_principal"),
    RouteAuthPolicy("GET", "/api/v1/dashboard/retailer-composition", "authenticated_principal"),
    RouteAuthPolicy("GET", "/api/v1/sources", "authenticated_principal"),
    RouteAuthPolicy("GET", "/api/v1/sources/status", "authenticated_principal"),
    RouteAuthPolicy("GET", "/api/v1/sources/{source_id}/status", "authenticated_principal"),
    RouteAuthPolicy("GET", "/api/v1/sources/{source_id}/auth", "authenticated_principal"),
    RouteAuthPolicy("GET", "/api/v1/connectors", "authenticated_principal"),
    RouteAuthPolicy("POST", "/api/v1/connectors/reload", "admin_only"),
    RouteAuthPolicy("POST", "/api/v1/connectors/rescan", "admin_only"),
    RouteAuthPolicy("POST", "/api/v1/connectors/{source_id}/install", "admin_only"),
    RouteAuthPolicy("POST", "/api/v1/connectors/{source_id}/enable", "admin_only"),
    RouteAuthPolicy("POST", "/api/v1/connectors/{source_id}/disable", "admin_only"),
    RouteAuthPolicy("POST", "/api/v1/connectors/{source_id}/uninstall", "admin_only"),
    RouteAuthPolicy("GET", "/api/v1/connectors/{source_id}/config", "admin_only"),
    RouteAuthPolicy("POST", "/api/v1/connectors/{source_id}/config", "admin_only"),
    RouteAuthPolicy("GET", "/api/v1/plugin-management", "admin_only"),
    RouteAuthPolicy("POST", "/api/v1/plugin-management/rescan", "admin_only"),
    RouteAuthPolicy("POST", "/api/v1/connectors/cascade/start", "authenticated_principal"),
    RouteAuthPolicy("POST", "/api/v1/connectors/cascade/retry", "authenticated_principal"),
    RouteAuthPolicy("GET", "/api/v1/connectors/cascade/status", "authenticated_principal"),
    RouteAuthPolicy("POST", "/api/v1/connectors/cascade/cancel", "authenticated_principal"),
    RouteAuthPolicy("POST", "/api/v1/connectors/{source_id}/bootstrap/start", "authenticated_principal"),
    RouteAuthPolicy("GET", "/api/v1/connectors/{source_id}/bootstrap/status", "authenticated_principal"),
    RouteAuthPolicy("POST", "/api/v1/connectors/{source_id}/bootstrap/cancel", "authenticated_principal"),
    RouteAuthPolicy("POST", "/api/v1/connectors/{source_id}/sync", "authenticated_principal"),
    RouteAuthPolicy("POST", "/api/v1/sources/{source_id}/sync", "authenticated_principal"),
    RouteAuthPolicy("GET", "/api/v1/connectors/{source_id}/sync/status", "authenticated_principal"),
    RouteAuthPolicy("GET", "/api/v1/sources/{source_id}/sync-status", "authenticated_principal"),
    RouteAuthPolicy("PATCH", "/api/v1/sources/{source_id}/sharing", "authenticated_principal"),
    RouteAuthPolicy("PATCH", "/api/v1/transactions/{transaction_id}/sharing", "authenticated_principal"),
    RouteAuthPolicy("PATCH", "/api/v1/transactions/{transaction_id}/items/{item_id}/sharing", "authenticated_principal"),
    RouteAuthPolicy("POST", "/api/v1/query/run", "authenticated_principal"),
    RouteAuthPolicy("POST", "/api/v1/query/dsl", "authenticated_principal"),
    RouteAuthPolicy("GET", "/api/v1/analytics/heatmap/weekday", "authenticated_principal"),
    RouteAuthPolicy("GET", "/api/v1/analytics/heatmap/hour", "authenticated_principal"),
    RouteAuthPolicy("GET", "/api/v1/analytics/heatmap/matrix", "authenticated_principal"),
    RouteAuthPolicy("GET", "/api/v1/analytics/deposits", "authenticated_principal"),
    RouteAuthPolicy("GET", "/api/v1/analytics/price-index", "authenticated_principal"),
    RouteAuthPolicy("POST", "/api/v1/tools/exec", "admin_only"),
    RouteAuthPolicy("POST", "/api/v1/analytics/basket-compare", "authenticated_principal"),
    RouteAuthPolicy("GET", "/api/v1/analytics/budget-rules", "authenticated_principal"),
    RouteAuthPolicy("POST", "/api/v1/analytics/budget-rules", "authenticated_principal"),
    RouteAuthPolicy("GET", "/api/v1/analytics/budget", "authenticated_principal"),
    RouteAuthPolicy("GET", "/api/v1/budget/months/{year}/{month}", "authenticated_principal"),
    RouteAuthPolicy("PUT", "/api/v1/budget/months/{year}/{month}", "authenticated_principal"),
    RouteAuthPolicy("GET", "/api/v1/budget/months/{year}/{month}/summary", "authenticated_principal"),
    RouteAuthPolicy("GET", "/api/v1/cashflow-entries", "authenticated_principal"),
    RouteAuthPolicy("POST", "/api/v1/cashflow-entries", "authenticated_principal"),
    RouteAuthPolicy("PATCH", "/api/v1/cashflow-entries/{entry_id}", "authenticated_principal"),
    RouteAuthPolicy("DELETE", "/api/v1/cashflow-entries/{entry_id}", "authenticated_principal"),
    RouteAuthPolicy("GET", "/api/v1/groceries/summary", "authenticated_principal"),
    RouteAuthPolicy("GET", "/api/v1/merchants/summary", "authenticated_principal"),
    RouteAuthPolicy("GET", "/api/v1/reports/templates", "authenticated_principal"),
    RouteAuthPolicy("GET", "/api/v1/goals/summary", "authenticated_principal"),
    RouteAuthPolicy("GET", "/api/v1/goals", "authenticated_principal"),
    RouteAuthPolicy("POST", "/api/v1/goals", "authenticated_principal"),
    RouteAuthPolicy("PATCH", "/api/v1/goals/{goal_id}", "authenticated_principal"),
    RouteAuthPolicy("DELETE", "/api/v1/goals/{goal_id}", "authenticated_principal"),
    RouteAuthPolicy("GET", "/api/v1/notifications", "authenticated_principal"),
    RouteAuthPolicy("PATCH", "/api/v1/notifications/{notification_id}", "authenticated_principal"),
    RouteAuthPolicy("POST", "/api/v1/notifications/mark-all-read", "authenticated_principal"),
    RouteAuthPolicy("GET", "/api/v1/analytics/patterns", "authenticated_principal"),
    RouteAuthPolicy("GET", "/api/v1/query/saved", "authenticated_principal"),
    RouteAuthPolicy("POST", "/api/v1/query/saved", "authenticated_principal"),
    RouteAuthPolicy("GET", "/api/v1/query/saved/{query_id}", "authenticated_principal"),
    RouteAuthPolicy("DELETE", "/api/v1/query/saved/{query_id}", "authenticated_principal"),
    RouteAuthPolicy("GET", "/api/v1/settings/ai", "admin_only"),
    RouteAuthPolicy("POST", "/api/v1/settings/ai", "admin_only"),
    RouteAuthPolicy("POST", "/api/v1/settings/ai/chat", "admin_only"),
    RouteAuthPolicy("POST", "/api/v1/settings/ai/categorization", "admin_only"),
    RouteAuthPolicy("POST", "/api/v1/settings/ai/disconnect", "admin_only"),
    RouteAuthPolicy("POST", "/api/v1/settings/ai/oauth/start", "admin_only"),
    RouteAuthPolicy("GET", "/api/v1/settings/ai/oauth/status", "admin_only"),
    RouteAuthPolicy("GET", "/api/v1/settings/ocr", "admin_only"),
    RouteAuthPolicy("POST", "/api/v1/settings/ocr", "admin_only"),
    RouteAuthPolicy("GET", "/api/v1/settings/ai/agent-config", "authenticated_user_session"),
    RouteAuthPolicy("POST", "/api/stream", "authenticated_user_session"),
    RouteAuthPolicy("GET", "/api/v1/products", "authenticated_principal"),
    RouteAuthPolicy("GET", "/api/v1/products/categories", "authenticated_principal"),
    RouteAuthPolicy("POST", "/api/v1/products", "authenticated_principal"),
    RouteAuthPolicy("POST", "/api/v1/products/seed", "authenticated_principal"),
    RouteAuthPolicy("POST", "/api/v1/products/cluster", "authenticated_principal"),
    RouteAuthPolicy("GET", "/api/v1/products/cluster/{job_id}", "authenticated_principal"),
    RouteAuthPolicy("GET", "/api/v1/products/{product_id}", "authenticated_principal"),
    RouteAuthPolicy("POST", "/api/v1/products/{product_id}/merge", "authenticated_principal"),
    RouteAuthPolicy("GET", "/api/v1/products/{product_id}/price-series", "authenticated_principal"),
    RouteAuthPolicy("GET", "/api/v1/products/{product_id}/purchases", "authenticated_principal"),
    RouteAuthPolicy("POST", "/api/v1/products/match", "authenticated_principal"),
    RouteAuthPolicy("GET", "/api/v1/compare/groups", "authenticated_principal"),
    RouteAuthPolicy("POST", "/api/v1/compare/groups", "authenticated_principal"),
    RouteAuthPolicy("GET", "/api/v1/compare/groups/{group_id}/series", "authenticated_principal"),
    RouteAuthPolicy("POST", "/api/v1/compare/groups/{group_id}/members", "authenticated_principal"),
    RouteAuthPolicy("POST", "/api/v1/quality/recategorize", "authenticated_principal"),
    RouteAuthPolicy("GET", "/api/v1/quality/recategorize/status", "authenticated_principal"),
    RouteAuthPolicy("GET", "/api/v1/quality/unmatched-items", "authenticated_principal"),
    RouteAuthPolicy("GET", "/api/v1/quality/low-confidence-ocr", "authenticated_principal"),
    RouteAuthPolicy("GET", "/api/v1/reliability/slo", "admin_only"),
    RouteAuthPolicy("GET", "/api/v1/review-queue/{document_id}", "authenticated_principal"),
    RouteAuthPolicy("POST", "/api/v1/review-queue/{document_id}/approve", "authenticated_principal"),
    RouteAuthPolicy("POST", "/api/v1/review-queue/{document_id}/reject", "authenticated_principal"),
    RouteAuthPolicy("PATCH", "/api/v1/review-queue/{document_id}/transaction", "authenticated_principal"),
    RouteAuthPolicy("PATCH", "/api/v1/review-queue/{document_id}/items/{item_id}", "authenticated_principal"),
    RouteAuthPolicy("WEBSOCKET", "/api/v1/connectors/vnc/ws", "authenticated_user_session"),
)

HTTP_ROUTE_AUTH_BY_KEY: dict[tuple[str, str], RouteAuthPolicy] = {
    (policy.method, policy.path): policy for policy in HTTP_ROUTE_AUTH_MATRIX
}

MINIMAL_PUBLIC_ROUTE_KEYS = frozenset(
    {
        ("GET", "/api/v1/health"),
        ("GET", "/api/v1/ready"),
        ("GET", "/api/v1/auth/setup-required"),
        ("POST", "/api/v1/auth/setup"),
        ("POST", "/api/v1/auth/login"),
    }
)


@dataclass(frozen=True, slots=True)
class RouteAuthVerificationReport:
    duplicate_entries: tuple[tuple[str, str], ...]
    missing_routes: tuple[tuple[str, str], ...]
    extra_routes: tuple[tuple[str, str], ...]
    unexpected_public_routes: tuple[tuple[str, str], ...]
    missing_public_routes: tuple[tuple[str, str], ...]

    @property
    def ok(self) -> bool:
        return not (
            self.duplicate_entries
            or self.missing_routes
            or self.extra_routes
            or self.unexpected_public_routes
            or self.missing_public_routes
        )

    def format_failure(self) -> str:
        message_lines = [
            "HTTP route auth policy verification failed.",
            "Every /api route must have exactly one RouteAuthPolicy entry in src/lidltool/api/route_auth.py.",
        ]
        if self.duplicate_entries:
            message_lines.append(
                "Duplicate matrix entries: "
                + ", ".join(f"{method} {path}" for method, path in self.duplicate_entries)
            )
        if self.missing_routes:
            message_lines.append(
                "Unclassified registered routes: "
                + ", ".join(f"{method} {path}" for method, path in self.missing_routes)
            )
            message_lines.append(
                "Fix: add RouteAuthPolicy(...) entries for the new route(s) in src/lidltool/api/route_auth.py."
            )
        if self.extra_routes:
            message_lines.append(
                "Stale matrix entries with no matching registered route: "
                + ", ".join(f"{method} {path}" for method, path in self.extra_routes)
            )
            message_lines.append(
                "Fix: remove or rename the stale RouteAuthPolicy entry in src/lidltool/api/route_auth.py."
            )
        if self.unexpected_public_routes or self.missing_public_routes:
            message_lines.append(
                "Public route set drifted from the hardened allowlist in MINIMAL_PUBLIC_ROUTE_KEYS."
            )
            if self.unexpected_public_routes:
                message_lines.append(
                    "Unexpected public routes: "
                    + ", ".join(
                        f"{method} {path}" for method, path in self.unexpected_public_routes
                    )
                )
            if self.missing_public_routes:
                message_lines.append(
                    "Expected public routes missing from the matrix: "
                    + ", ".join(f"{method} {path}" for method, path in self.missing_public_routes)
                )
            message_lines.append(
                "Fix: update the RouteAuthPolicy classification or explicitly review MINIMAL_PUBLIC_ROUTE_KEYS."
            )
        return "\n".join(message_lines)


def registered_api_route_keys(app: FastAPI) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    for route in app.routes:
        if isinstance(route, APIRoute):
            for method in sorted(route.methods or ()):
                if method in {"HEAD", "OPTIONS"}:
                    continue
                if route.path.startswith("/api/"):
                    keys.add((method.upper(), route.path))
        elif isinstance(route, APIWebSocketRoute) and route.path.startswith("/api/"):
            keys.add(("WEBSOCKET", route.path))
    return keys


def verify_route_auth_policy(
    registered_routes: Iterable[tuple[str, str]],
) -> RouteAuthVerificationReport:
    matrix_keys = [(policy.method, policy.path) for policy in HTTP_ROUTE_AUTH_MATRIX]
    key_counts = Counter(matrix_keys)
    duplicate_entries = tuple(sorted(key for key, count in key_counts.items() if count > 1))
    registered_set = set(registered_routes)
    classified_set = set(matrix_keys)
    public_routes = {
        (policy.method, policy.path)
        for policy in HTTP_ROUTE_AUTH_MATRIX
        if policy.category == "public"
    }
    return RouteAuthVerificationReport(
        duplicate_entries=duplicate_entries,
        missing_routes=tuple(sorted(registered_set - classified_set)),
        extra_routes=tuple(sorted(classified_set - registered_set)),
        unexpected_public_routes=tuple(sorted(public_routes - MINIMAL_PUBLIC_ROUTE_KEYS)),
        missing_public_routes=tuple(sorted(MINIMAL_PUBLIC_ROUTE_KEYS - public_routes)),
    )


def assert_route_auth_policy(app: FastAPI) -> None:
    report = verify_route_auth_policy(registered_api_route_keys(app))
    if not report.ok:
        raise RuntimeError(report.format_failure())
