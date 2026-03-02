from __future__ import annotations

import re
from typing import Any

METRIC_MAP = {
    "net": "net_total",
    "gross": "gross_total",
    "discount": "discount_total",
    "count": "purchase_count",
    "avg_price": "avg_unit_price",
}

DIMENSION_MAP = {
    "month": "month",
    "date": "date",
    "source_kind": "source_kind",
    "source": "source_kind",
    "category": "category",
    "product": "product",
}


def parse_dsl_to_query(dsl: str) -> dict[str, Any]:
    lines = [line.strip() for line in dsl.splitlines() if line.strip()]
    if not lines:
        raise ValueError("DSL query cannot be empty")

    header = lines[0]
    header_match = re.fullmatch(r"SPEND\s+(\w+)\s+BY\s+(.+)", header, flags=re.IGNORECASE)
    if header_match is None:
        raise ValueError("DSL header must be: SPEND <metric> BY <dim1, dim2>")
    metric_key = header_match.group(1).lower()
    metric = METRIC_MAP.get(metric_key)
    if metric is None:
        raise ValueError("unsupported metric in DSL")

    dims_raw = [part.strip().lower() for part in header_match.group(2).split(",") if part.strip()]
    dimensions = []
    for dim_raw in dims_raw:
        mapped = DIMENSION_MAP.get(dim_raw)
        if mapped is None:
            raise ValueError(f"unsupported dimension in DSL: {dim_raw}")
        dimensions.append(mapped)

    filters: dict[str, Any] = {}
    limit: int | None = None
    sort_dir = "desc"
    sort_by = metric

    joined = " ".join(lines[1:])
    where_match = re.search(r"WHERE\s+(.+?)(?:\s+LIMIT\s+\d+)?$", joined, flags=re.IGNORECASE)
    if where_match:
        where_expr = where_match.group(1)

        between_match = re.search(
            r"date\s+BETWEEN\s+(\d{4}-\d{2}-\d{2})\.\.(\d{4}-\d{2}-\d{2})",
            where_expr,
            flags=re.IGNORECASE,
        )
        if between_match:
            filters["date_from"] = between_match.group(1)
            filters["date_to"] = between_match.group(2)

        category_match = re.search(r'category\s*=\s*"([^"]+)"', where_expr, flags=re.IGNORECASE)
        if category_match:
            filters["categories"] = [category_match.group(1)]

        source_match = re.search(r"source(?:_kind)?\s*=\s*([a-zA-Z0-9_]+)", where_expr, flags=re.IGNORECASE)
        if source_match:
            filters["source_kinds"] = [source_match.group(1)]

    limit_match = re.search(r"\bLIMIT\s+(\d+)\b", joined, flags=re.IGNORECASE)
    if limit_match:
        limit = int(limit_match.group(1))

    return {
        "metrics": [metric],
        "dimensions": dimensions,
        "filters": filters,
        "sort_by": sort_by,
        "sort_dir": sort_dir,
        "limit": limit,
    }
