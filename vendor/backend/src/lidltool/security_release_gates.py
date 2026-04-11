from __future__ import annotations

import re
from pathlib import Path

from lidltool.deployment_policy import HttpExposureMode

EXPECTED_HTTP_EXPOSURE_MODES = (
    HttpExposureMode.LOCALHOST.value,
    HttpExposureMode.CONTAINER_LOCALHOST.value,
    HttpExposureMode.PRIVATE_NETWORK.value,
    HttpExposureMode.REVERSE_PROXY_TLS.value,
)


def _read(repo_root: Path, relative_path: str) -> str:
    return (repo_root / relative_path).read_text(encoding="utf-8")


def _append_missing(
    errors: list[str],
    *,
    relative_path: str,
    content: str,
    required_fragments: tuple[str, ...],
) -> None:
    for fragment in required_fragments:
        if fragment not in content:
            errors.append(f"{relative_path}: missing required fragment {fragment!r}")


def _append_forbidden(
    errors: list[str],
    *,
    relative_path: str,
    content: str,
    forbidden_fragments: tuple[str, ...],
) -> None:
    for fragment in forbidden_fragments:
        if fragment in content:
            errors.append(f"{relative_path}: forbidden fragment present {fragment!r}")


def assert_security_docs_and_defaults(repo_root: Path) -> None:
    errors: list[str] = []
    compose = _read(repo_root, "docker-compose.yml")
    env_example = _read(repo_root, ".env.example")
    readme = _read(repo_root, "README.md")
    deploy = _read(repo_root, "DEPLOY.md")

    if '"127.0.0.1:8000:8000"' not in compose:
        errors.append("docker-compose.yml: default port publish must stay loopback-only")
    if re.search(r'^\s*-\s*["\']?8000:8000["\']?\s*$', compose, flags=re.MULTILINE):
        errors.append("docker-compose.yml: must not publish 8000:8000 on all interfaces by default")

    _append_missing(
        errors,
        relative_path=".env.example",
        content=env_example.lower(),
        required_fragments=(
            "lidltool_http_exposure_mode=localhost",
            "container_localhost",
            "private_network",
            "reverse_proxy_tls",
            "publishing a port is not an auth boundary",
        ),
    )
    _append_forbidden(
        errors,
        relative_path=".env.example",
        content=env_example.lower(),
        forbidden_fragments=("warn_only", "?db=", "?config="),
    )

    for relative_path, content in (
        ("README.md", readme),
        ("DEPLOY.md", deploy),
    ):
        lowered = content.lower()
        _append_missing(
            errors,
            relative_path=relative_path,
            content=lowered,
            required_fragments=(
                "not intended to be exposed directly to the public internet",
                "localhost-only",
                "docker-local",
                "private-network/vpn",
                "reverse proxy with tls",
                "publishing a port is not an auth boundary",
            ),
        )
        _append_missing(
            errors,
            relative_path=relative_path,
            content=content,
            required_fragments=(
                "LIDLTOOL_HTTP_EXPOSURE_MODE",
                "container_localhost",
                "private_network",
                "reverse_proxy_tls",
            ),
        )
        _append_forbidden(
            errors,
            relative_path=relative_path,
            content=lowered,
            forbidden_fragments=("warn_only", "?db=", "?config="),
        )

    if tuple(mode.value for mode in HttpExposureMode) != EXPECTED_HTTP_EXPOSURE_MODES:
        errors.append(
            "src/lidltool/deployment_policy.py: supported exposure modes changed; review release docs and CI gates intentionally"
        )

    if errors:
        raise RuntimeError("\n".join(errors))


def assert_release_security_checklist(repo_root: Path) -> None:
    errors: list[str] = []
    checklist = _read(repo_root, "docs/security/security-hardening-checklist.md").lower()
    threat_model = _read(repo_root, "docs/security/threat-model.md").lower()

    _append_missing(
        errors,
        relative_path="docs/security/security-hardening-checklist.md",
        content=checklist,
        required_fragments=(
            "## sprint 5 regression gates",
            "security-regressions",
            "default deployment is localhost-only",
            "supported exposure modes are unchanged unless intentionally reviewed",
            "privileged routes require auth",
            "public route set remains minimal",
            "dangerous debug/test features are disabled by default",
            "docs match the implementation",
        ),
    )

    _append_missing(
        errors,
        relative_path="docs/security/threat-model.md",
        content=threat_model,
        required_fragments=(
            "## enforced protections",
            "## operator-controlled risks",
            "## future backlog",
            "manual key rotation",
            "re-encryption",
            "nat/firewall/public topology",
            "reverse-proxy and network boundary setup",
        ),
    )

    if errors:
        raise RuntimeError("\n".join(errors))


def run_security_release_gates(repo_root: Path) -> None:
    assert_security_docs_and_defaults(repo_root)
    assert_release_security_checklist(repo_root)
