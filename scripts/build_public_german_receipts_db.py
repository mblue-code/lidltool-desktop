#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = REPO_ROOT / ".tmp" / "public_german_receipts_db"
DEFAULT_DB_PATH = DEFAULT_OUTPUT_DIR / "public_german_receipts.sqlite"
DEFAULT_FILES_DIR = DEFAULT_OUTPUT_DIR / "files"
USER_AGENT = "outlays-desktop-public-german-receipts/1.0"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
GITHUB_API = "https://api.github.com"
FILE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".pdf"}
COMMONS_RATE_LIMIT_DELAY_S = 0.35
COMMONS_RETRY_STATUS_CODES = {429, 500, 502, 503, 504}


SCHEMA_SQL = """
create table if not exists source (
  source_id integer primary key autoincrement,
  source_key text not null unique,
  kind text not null,
  label text not null,
  homepage_url text not null,
  license_hint text,
  notes text,
  created_at text not null
);

create table if not exists asset (
  asset_id integer primary key autoincrement,
  source_id integer not null,
  external_id text not null unique,
  title text not null,
  source_page_url text,
  download_url text not null,
  source_path text,
  category_label text,
  receipt_type text,
  mime_type text,
  size_bytes integer,
  width integer,
  height integer,
  license_name text,
  license_url text,
  attribution text,
  local_relpath text,
  sha256 text,
  duplicate_of_asset_id integer,
  status text not null,
  metadata_json text,
  downloaded_at text,
  created_at text not null
);
"""


COMMONS_FOCUSED_CATEGORIES = [
    "Category:ALDI_receipts_in_Germany",
    "Category:Lidl_receipts_in_Germany",
    "Category:REWE_receipts",
    "Category:Rossmann_receipts_in_Germany",
    "Category:EDEKA_receipts",
    "Category:Bottle_reverse_vending_machines_receipts_in_Germany",
]
COMMONS_EXTRA_FILE_TITLES = [
    "File:Real_receipt,_Oude_Pekela_(2019)_01.jpg",
    "File:Real_receipt,_Oude_Pekela_(2019)_02.jpg",
    "File:Kassenzettel_Fressnapf_mit_ausgewiesener_MwSt-Senkung_und_TSE_Transaktionsnummer_12_2020.png",
    "File:Ikea-Quittung-2009.jpg",
    "File:KiK-Quittung-2009.jpg",
    "File:Schlecker-Quittung-2009.jpg",
    "File:Schlecker-Quittung-2011.jpg",
    "File:MediaMarkt-Quittung-2011.jpg",
    "File:Obi-Quittung-2009.jpg",
]
GITHUB_REPOS: list[dict[str, Any]] = [
    {
        "owner": "knipknap",
        "repo": "receiptparser",
        "source_key": "github:knipknap/receiptparser",
        "label": "knipknap/receiptparser",
        "notes": "German supermarket receipt sample set and OCR text fixtures.",
        "default_branch": "master",
        "asset_paths": [
            "tests/data/germany/img/IMG0001.jpg",
            "tests/data/germany/img/IMG0003.jpg",
            "tests/data/germany/img/IMG0004.jpg",
            "tests/data/germany/img/IMG0006.jpg",
            "tests/data/germany/img/IMG0007.jpg",
            "tests/data/germany/img/IMG0008.jpg",
        ],
    },
    {
        "owner": "ReceiptManager",
        "repo": "receipt-parser-legacy",
        "source_key": "github:ReceiptManager/receipt-parser-legacy",
        "label": "ReceiptManager/receipt-parser-legacy",
        "notes": "Legacy German supermarket receipt parser. Some overlap with receiptparser.",
        "default_branch": "master",
        "asset_paths": [
            "data/img/IMG0001.jpg",
            "data/img/IMG0001.pdf",
            "data/img/IMG0003.jpg",
            "data/img/IMG0004.jpg",
            "data/img/IMG0006.jpg",
            "data/img/IMG0007.jpg",
            "data/img/IMG0008.jpg",
        ],
    },
    {
        "owner": "oraies",
        "repo": "eBonsParser",
        "source_key": "github:oraies/eBonsParser",
        "label": "oraies/eBonsParser",
        "notes": "German REWE eBon PDF examples.",
        "default_branch": "main",
        "asset_paths": [
            "examples/rewe/rewe_bar.pdf",
            "examples/rewe/rewe_card.pdf",
            "examples/thalia/thalia_card.pdf",
        ],
    },
    {
        "owner": "webD97",
        "repo": "rewe-ebon-parser",
        "source_key": "github:webD97/rewe-ebon-parser",
        "label": "webD97/rewe-ebon-parser",
        "notes": "German REWE eBon PDF examples.",
        "default_branch": "master",
        "asset_paths": [
            "examples/eBons/1.pdf",
            "examples/eBons/2.pdf",
            "examples/eBons/3.pdf",
            "examples/eBons/4.pdf",
            "examples/eBons/5.pdf",
        ],
    },
    {
        "owner": "e-kotov",
        "repo": "rewe-ebon-parser",
        "source_key": "github:e-kotov/rewe-ebon-parser",
        "label": "e-kotov/rewe-ebon-parser",
        "notes": "Fork with German REWE eBon examples and anonymized text exports.",
        "default_branch": "main",
        "asset_paths": [
            "examples/eBons/1.pdf",
            "examples/eBons/2.pdf",
            "examples/eBons/3.pdf",
            "examples/eBons/4.pdf",
            "examples/eBons/5.pdf",
        ],
    },
]


@dataclass(slots=True)
class CatalogConfig:
    db_path: Path
    files_dir: Path
    commons_categories: tuple[str, ...] = tuple(COMMONS_FOCUSED_CATEGORIES)
    commons_extra_file_titles: tuple[str, ...] = tuple(COMMONS_EXTRA_FILE_TITLES)
    download_commons_assets: bool = False


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _slugify(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9._-]+", "_", value.strip())
    return normalized.strip("_") or "asset"


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _request_with_retry(url: str, *, timeout: int, is_commons: bool) -> bytes:
    last_error: Exception | None = None
    for attempt in range(6):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = response.read()
            if is_commons:
                time.sleep(COMMONS_RATE_LIMIT_DELAY_S)
            return payload
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code not in COMMONS_RETRY_STATUS_CODES or attempt == 5:
                raise
            time.sleep((2**attempt) * 0.75)
        except urllib.error.URLError as exc:
            last_error = exc
            if attempt == 5:
                raise
            time.sleep((2**attempt) * 0.5)
    if last_error is not None:
        raise last_error
    raise RuntimeError(f"request failed without error for {url}")


def _http_get_json(url: str) -> dict[str, Any]:
    payload = _request_with_retry(url, timeout=60, is_commons="commons.wikimedia.org" in url)
    return json.loads(payload.decode("utf-8"))


def _http_get_bytes(url: str) -> bytes:
    return _request_with_retry(url, timeout=120, is_commons="wikimedia.org" in url)


def _ensure_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    conn.commit()


def _upsert_source(
    conn: sqlite3.Connection,
    *,
    source_key: str,
    kind: str,
    label: str,
    homepage_url: str,
    license_hint: str | None,
    notes: str | None,
) -> int:
    conn.execute(
        """
        insert into source (source_key, kind, label, homepage_url, license_hint, notes, created_at)
        values (?, ?, ?, ?, ?, ?, ?)
        on conflict(source_key) do update set
          kind=excluded.kind,
          label=excluded.label,
          homepage_url=excluded.homepage_url,
          license_hint=excluded.license_hint,
          notes=excluded.notes
        """,
        (source_key, kind, label, homepage_url, license_hint, notes, _utc_now()),
    )
    row = conn.execute("select source_id from source where source_key = ?", (source_key,)).fetchone()
    if row is None:
        raise RuntimeError(f"failed to upsert source {source_key}")
    return int(row[0])


def _asset_exists(conn: sqlite3.Connection, external_id: str) -> bool:
    row = conn.execute("select 1 from asset where external_id = ?", (external_id,)).fetchone()
    return row is not None


def _find_duplicate_asset_id(conn: sqlite3.Connection, sha256: str) -> int | None:
    row = conn.execute(
        "select asset_id from asset where sha256 = ? order by asset_id asc limit 1",
        (sha256,),
    ).fetchone()
    return int(row[0]) if row is not None else None


def _insert_asset(
    conn: sqlite3.Connection,
    *,
    source_id: int,
    external_id: str,
    title: str,
    source_page_url: str | None,
    download_url: str,
    source_path: str | None,
    category_label: str | None,
    receipt_type: str,
    mime_type: str | None,
    size_bytes: int | None,
    width: int | None,
    height: int | None,
    license_name: str | None,
    license_url: str | None,
    attribution: str | None,
    local_relpath: str | None,
    sha256: str | None,
    duplicate_of_asset_id: int | None,
    status: str,
    metadata: dict[str, Any],
) -> None:
    conn.execute(
        """
        insert into asset (
          source_id, external_id, title, source_page_url, download_url, source_path,
          category_label, receipt_type, mime_type, size_bytes, width, height,
          license_name, license_url, attribution, local_relpath, sha256,
          duplicate_of_asset_id, status, metadata_json, downloaded_at, created_at
        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            source_id,
            external_id,
            title,
            source_page_url,
            download_url,
            source_path,
            category_label,
            receipt_type,
            mime_type,
            size_bytes,
            width,
            height,
            license_name,
            license_url,
            attribution,
            local_relpath,
            sha256,
            duplicate_of_asset_id,
            status,
            json.dumps(metadata, ensure_ascii=False),
            _utc_now() if status == "downloaded" else None,
            _utc_now(),
        ),
    )


def _download_asset(
    *,
    conn: sqlite3.Connection,
    files_dir: Path,
    source_key: str,
    title: str,
    download_url: str,
) -> tuple[str, str, int | None]:
    payload = _http_get_bytes(download_url)
    sha256 = _sha256_bytes(payload)
    suffix = Path(urllib.parse.urlparse(download_url).path).suffix or ".bin"
    target_dir = files_dir / _slugify(source_key)
    target_dir.mkdir(parents=True, exist_ok=True)
    file_name = f"{_slugify(title)}{suffix}"
    target_path = target_dir / file_name
    if target_path.exists() and target_path.read_bytes() == payload:
        return str(target_path.relative_to(files_dir.parent)), sha256, _find_duplicate_asset_id(conn, sha256)
    target_path.write_bytes(payload)
    duplicate_of = _find_duplicate_asset_id(conn, sha256)
    return str(target_path.relative_to(files_dir.parent)), sha256, duplicate_of


def _commons_api(params: dict[str, str]) -> dict[str, Any]:
    query = dict(params)
    query["format"] = "json"
    query["formatversion"] = "2"
    query["origin"] = "*"
    url = f"{COMMONS_API}?{urllib.parse.urlencode(query)}"
    return _http_get_json(url)


def _walk_commons_category(root_category: str) -> list[dict[str, Any]]:
    seen_categories: set[str] = set()
    queue = [root_category]
    files: list[dict[str, Any]] = []
    while queue:
        category = queue.pop(0)
        if category in seen_categories:
            continue
        seen_categories.add(category)
        category_label = category.removeprefix("Category:")
        cmcontinue: str | None = None
        while True:
            params = {
                "action": "query",
                "list": "categorymembers",
                "cmtitle": category,
                "cmlimit": "500",
            }
            if cmcontinue:
                params["cmcontinue"] = cmcontinue
            payload = _commons_api(params)
            members = payload.get("query", {}).get("categorymembers", [])
            for member in members:
                title = str(member.get("title") or "")
                ns = int(member.get("ns") or -1)
                if ns == 6 and title.startswith("File:"):
                    files.append({"title": title, "category_label": category_label})
                elif ns == 14 and title.startswith("Category:"):
                    queue.append(title)
            cmcontinue = payload.get("continue", {}).get("cmcontinue")
            if not cmcontinue:
                break
    unique: dict[str, dict[str, Any]] = {}
    for item in files:
        unique.setdefault(item["title"], item)
    return list(unique.values())


def _collect_commons_targets(
    categories: tuple[str, ...],
    extra_file_titles: tuple[str, ...],
) -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    for category in categories:
        for item in _walk_commons_category(category):
            entry = dict(item)
            entry.setdefault("source_labels", [])
            label = str(entry.get("category_label") or "")
            if label and label not in entry["source_labels"]:
                entry["source_labels"].append(label)
            current = unique.get(entry["title"])
            if current is None:
                unique[entry["title"]] = entry
                continue
            for source_label in entry["source_labels"]:
                if source_label not in current["source_labels"]:
                    current["source_labels"].append(source_label)
    for file_title in extra_file_titles:
        entry = unique.setdefault(
            file_title,
            {
                "title": file_title,
                "category_label": "Receipts of Germany (root extras)",
                "source_labels": ["Receipts of Germany (root extras)"],
            },
        )
        if "Receipts of Germany (root extras)" not in entry["source_labels"]:
            entry["source_labels"].append("Receipts of Germany (root extras)")
    return sorted(unique.values(), key=lambda item: str(item["title"]).lower())


def _commons_file_metadata(file_title: str) -> dict[str, Any]:
    payload = _commons_api(
        {
            "action": "query",
            "titles": file_title,
            "prop": "imageinfo",
            "iiprop": "url|mime|size|extmetadata",
        }
    )
    pages = payload.get("query", {}).get("pages", [])
    if not pages:
        raise RuntimeError(f"commons metadata missing for {file_title}")
    page = pages[0]
    info = (page.get("imageinfo") or [{}])[0]
    ext = info.get("extmetadata") or {}
    def _ext(key: str) -> str | None:
        raw = ext.get(key) or {}
        value = raw.get("value")
        return str(value) if value not in (None, "") else None
    return {
        "title": file_title,
        "source_page_url": page.get("canonicalurl") or f"https://commons.wikimedia.org/wiki/{urllib.parse.quote(file_title.replace(' ', '_'))}",
        "download_url": info.get("url"),
        "mime_type": info.get("mime"),
        "size_bytes": info.get("size"),
        "width": info.get("width"),
        "height": info.get("height"),
        "license_name": _ext("LicenseShortName"),
        "license_url": _ext("LicenseUrl"),
        "attribution": _ext("Attribution"),
        "artist": _ext("Artist"),
    }


def _collect_commons(conn: sqlite3.Connection, cfg: CatalogConfig) -> None:
    source_id = _upsert_source(
        conn,
        source_key="commons:german_receipts_curated",
        kind="wikimedia_commons",
        label="Wikimedia Commons German receipts (curated)",
        homepage_url="https://commons.wikimedia.org/wiki/Category:Receipts_of_Germany",
        license_hint="Per-file Wikimedia Commons licensing",
        notes="Focused crawl of German receipt and bottle-return categories plus selected root-only extras.",
    )
    files = _collect_commons_targets(cfg.commons_categories, cfg.commons_extra_file_titles)
    for item in files:
        file_title = str(item["title"])
        external_id = f"commons:{file_title}"
        if _asset_exists(conn, external_id):
            continue
        try:
            meta = _commons_file_metadata(file_title)
            download_url = str(meta.get("download_url") or "")
            if not download_url:
                raise RuntimeError("missing download url")
            local_relpath: str | None = None
            sha256: str | None = None
            duplicate_of: int | None = None
            status = "indexed"
            if cfg.download_commons_assets:
                local_relpath, sha256, duplicate_of = _download_asset(
                    conn=conn,
                    files_dir=cfg.files_dir,
                    source_key="commons_receipts_of_germany",
                    title=file_title.removeprefix("File:"),
                    download_url=download_url,
                )
                status = "downloaded"
            _insert_asset(
                conn,
                source_id=source_id,
                external_id=external_id,
                title=file_title.removeprefix("File:"),
                source_page_url=str(meta.get("source_page_url") or ""),
                download_url=download_url,
                source_path=None,
                category_label=str(item.get("category_label") or ""),
                receipt_type=_guess_receipt_type(file_title),
                mime_type=str(meta.get("mime_type") or "") or None,
                size_bytes=int(meta["size_bytes"]) if meta.get("size_bytes") is not None else None,
                width=int(meta["width"]) if meta.get("width") is not None else None,
                height=int(meta["height"]) if meta.get("height") is not None else None,
                license_name=str(meta.get("license_name") or "") or None,
                license_url=str(meta.get("license_url") or "") or None,
                attribution=str(meta.get("attribution") or meta.get("artist") or "") or None,
                local_relpath=local_relpath,
                sha256=sha256,
                duplicate_of_asset_id=duplicate_of,
                status=status,
                metadata=meta
                | {
                    "category_label": item.get("category_label"),
                    "source_labels": item.get("source_labels") or [],
                },
            )
            conn.commit()
        except Exception as exc:  # noqa: BLE001
            _insert_asset(
                conn,
                source_id=source_id,
                external_id=external_id,
                title=file_title.removeprefix("File:"),
                source_page_url=None,
                download_url="",
                source_path=None,
                category_label=str(item.get("category_label") or ""),
                receipt_type=_guess_receipt_type(file_title),
                mime_type=None,
                size_bytes=None,
                width=None,
                height=None,
                license_name=None,
                license_url=None,
                attribution=None,
                local_relpath=None,
                sha256=None,
                duplicate_of_asset_id=None,
                status="error",
                metadata={
                    "error": str(exc),
                    "category_label": item.get("category_label"),
                    "source_labels": item.get("source_labels") or [],
                },
            )
            conn.commit()


def _github_repo_tree(owner: str, repo: str) -> tuple[str, list[dict[str, Any]]]:
    repo_payload = _http_get_json(f"{GITHUB_API}/repos/{owner}/{repo}")
    default_branch = str(repo_payload.get("default_branch") or "main")
    tree_payload = _http_get_json(
        f"{GITHUB_API}/repos/{owner}/{repo}/git/trees/{default_branch}?recursive=1"
    )
    return default_branch, tree_payload.get("tree", []) or []


def _looks_like_german_receipt_asset(repo: str, path: str) -> bool:
    lower = path.lower()
    suffix = Path(lower).suffix
    if suffix not in FILE_EXTENSIONS:
        return False
    if repo == "receiptparser":
        return "tests/data/germany/" in lower
    if repo == "receipt-parser-legacy":
        return "data/img/" in lower and re.search(r"img0+\d+\.(jpg|pdf)$", lower) is not None
    if repo in {"eBonsParser", "rewe-ebon-parser"}:
        return lower.startswith("examples/") or "/examples/" in lower
    return False


def _guess_receipt_type(path: str) -> str:
    suffix = Path(path).suffix.lower()
    if suffix == ".pdf":
        if "ebon" in path.lower() or "rewe" in path.lower():
            return "ebon_pdf"
        return "pdf"
    lower = path.lower()
    if "leergut" in lower or "bottle_reverse" in lower or "reverse_vending" in lower:
        return "bottle_return"
    return "photo"


def _collect_github(conn: sqlite3.Connection, cfg: CatalogConfig) -> None:
    for repo_cfg in GITHUB_REPOS:
        owner = repo_cfg["owner"]
        repo = repo_cfg["repo"]
        homepage = f"https://github.com/{owner}/{repo}"
        source_id = _upsert_source(
            conn,
            source_key=repo_cfg["source_key"],
            kind="github",
            label=repo_cfg["label"],
            homepage_url=homepage,
            license_hint="See upstream repository license",
            notes=repo_cfg.get("notes"),
        )
        default_branch = str(repo_cfg.get("default_branch") or "main")
        asset_paths = repo_cfg.get("asset_paths")
        nodes: list[dict[str, Any]]
        if isinstance(asset_paths, list) and asset_paths:
            nodes = [{"path": path} for path in asset_paths]
        else:
            try:
                default_branch, tree = _github_repo_tree(owner, repo)
            except Exception as exc:  # noqa: BLE001
                print(f"[warn] failed to enumerate {homepage}: {exc}", file=sys.stderr)
                continue
            nodes = [node for node in tree if str(node.get("type")) == "blob"]
        for node in nodes:
            path = str(node.get("path") or "")
            if not _looks_like_german_receipt_asset(repo, path):
                continue
            external_id = f"github:{owner}/{repo}:{path}"
            if _asset_exists(conn, external_id):
                continue
            raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{default_branch}/{path}"
            title = Path(path).name
            try:
                local_relpath, sha256, duplicate_of = _download_asset(
                    conn=conn,
                    files_dir=cfg.files_dir,
                    source_key=f"github_{owner}_{repo}",
                    title=title,
                    download_url=raw_url,
                )
                _insert_asset(
                    conn,
                    source_id=source_id,
                    external_id=external_id,
                    title=title,
                    source_page_url=f"{homepage}/blob/{default_branch}/{path}",
                    download_url=raw_url,
                    source_path=path,
                    category_label=None,
                    receipt_type=_guess_receipt_type(path),
                    mime_type=None,
                    size_bytes=int(node["size"]) if node.get("size") is not None else None,
                    width=None,
                    height=None,
                    license_name=None,
                    license_url=None,
                    attribution=None,
                    local_relpath=local_relpath,
                    sha256=sha256,
                    duplicate_of_asset_id=duplicate_of,
                    status="downloaded",
                    metadata={
                        "owner": owner,
                        "repo": repo,
                        "default_branch": default_branch,
                        "path": path,
                    },
                )
                conn.commit()
            except Exception as exc:  # noqa: BLE001
                _insert_asset(
                    conn,
                    source_id=source_id,
                    external_id=external_id,
                    title=title,
                    source_page_url=f"{homepage}/blob/{default_branch}/{path}",
                    download_url=raw_url,
                    source_path=path,
                    category_label=None,
                    receipt_type=_guess_receipt_type(path),
                    mime_type=None,
                    size_bytes=int(node["size"]) if node.get("size") is not None else None,
                    width=None,
                    height=None,
                    license_name=None,
                    license_url=None,
                    attribution=None,
                    local_relpath=None,
                    sha256=None,
                    duplicate_of_asset_id=None,
                    status="error",
                    metadata={
                        "owner": owner,
                        "repo": repo,
                        "default_branch": default_branch,
                        "path": path,
                        "error": str(exc),
                    },
                )
                conn.commit()


def _write_summary(conn: sqlite3.Connection, cfg: CatalogConfig) -> None:
    rows = conn.execute(
        """
        select
          s.source_key,
          s.label,
          count(*) as asset_count,
          sum(case when a.status = 'downloaded' then 1 else 0 end) as downloaded_count,
          sum(case when a.status = 'indexed' then 1 else 0 end) as indexed_count,
          sum(case when a.duplicate_of_asset_id is not null then 1 else 0 end) as duplicate_count
        from asset a
        join source s on s.source_id = a.source_id
        group by s.source_key, s.label
        order by (downloaded_count + indexed_count) desc, asset_count desc
        """
    ).fetchall()
    totals = conn.execute(
        """
        select
          count(*) as total_assets,
          sum(case when status = 'downloaded' then 1 else 0 end) as downloaded_assets,
          sum(case when status = 'indexed' then 1 else 0 end) as indexed_assets,
          sum(case when duplicate_of_asset_id is not null then 1 else 0 end) as duplicate_assets
        from asset
        """
    ).fetchone()
    summary = {
        "generated_at": _utc_now(),
        "output_dir": str(cfg.db_path.parent),
        "db_path": str(cfg.db_path),
        "totals": {
            "assets": int(totals[0] or 0),
            "downloaded": int(totals[1] or 0),
            "indexed": int(totals[2] or 0),
            "duplicates": int(totals[3] or 0),
        },
        "sources": [
            {
                "source_key": row[0],
                "label": row[1],
                "asset_count": int(row[2] or 0),
                "downloaded_count": int(row[3] or 0),
                "indexed_count": int(row[4] or 0),
                "duplicate_count": int(row[5] or 0),
            }
            for row in rows
        ],
    }
    (cfg.db_path.parent / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


def build_catalog(cfg: CatalogConfig) -> None:
    cfg.db_path.parent.mkdir(parents=True, exist_ok=True)
    cfg.files_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(cfg.db_path)
    try:
        _ensure_db(conn)
        _collect_github(conn, cfg)
        _collect_commons(conn, cfg)
        _write_summary(conn, cfg)
        conn.commit()
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a public German receipts SQLite catalog.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--files-dir", type=Path, default=DEFAULT_FILES_DIR)
    parser.add_argument(
        "--commons-categories",
        nargs="*",
        default=COMMONS_FOCUSED_CATEGORIES,
        help="Focused Wikimedia Commons categories to crawl.",
    )
    parser.add_argument(
        "--download-commons-assets",
        action="store_true",
        help="Download Wikimedia Commons originals locally. Default is metadata-only indexing to avoid rate limits.",
    )
    args = parser.parse_args()
    cfg = CatalogConfig(
        db_path=args.db,
        files_dir=args.files_dir,
        commons_categories=tuple(args.commons_categories),
        download_commons_assets=bool(args.download_commons_assets),
    )
    build_catalog(cfg)
    print(f"Catalog written to: {cfg.db_path}")
    print(f"Files stored under: {cfg.files_dir}")
    summary_path = cfg.db_path.parent / "summary.json"
    if summary_path.exists():
        print(summary_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
