"""Shared shaping for product and store rows."""

from __future__ import annotations

import json

from backend.app.cleaning import parse_image_urls, parse_specs
from backend.app.textnorm import like_contains, normalize_fa, parse_user_int


def coerce_filters(filters: dict | str | None = None, **extra) -> dict:
    raw: dict = {}
    if isinstance(filters, str):
        try:
            parsed = json.loads(filters)
        except json.JSONDecodeError:
            parsed = None
        filters = parsed if isinstance(parsed, dict) else None
    if isinstance(filters, dict):
        raw.update(filters)
    for key, value in extra.items():
        raw.setdefault(key, value)

    try:
        limit = int(raw.get("limit", 20))
    except (TypeError, ValueError):
        limit = 20
    limit = min(50, max(1, limit))
    min_price = parse_user_int(raw.get("min_price"))
    max_price = parse_user_int(raw.get("max_price"))
    if min_price is not None and max_price is not None and min_price > max_price:
        min_price, max_price = max_price, min_price
    brand = normalize_fa(raw.get("brand")) if raw.get("brand") else None
    category = normalize_fa(raw.get("category")) if raw.get("category") else None
    return {
        "brand": brand,
        "category": category,
        "min_price": min_price,
        "max_price": max_price,
        "limit": limit,
    }


def public_filters(filters: dict) -> dict:
    return {
        "brand": filters["brand"],
        "category": filters["category"],
        "min_price": filters["min_price"],
        "max_price": filters["max_price"],
        "limit": filters["limit"],
    }


def filter_clauses(filters: dict) -> tuple[list[str], list]:
    clauses: list[str] = []
    params: list = []
    if filters["brand"]:
        clauses.append("p.brand_name_norm LIKE ? ESCAPE '\\'")
        params.append(like_contains(filters["brand"]))
    if filters["category"]:
        clauses.append("p.category_name_norm LIKE ? ESCAPE '\\'")
        params.append(like_contains(filters["category"]))
    if filters["min_price"] is not None:
        clauses.append("s.max_price >= ?")
        params.append(filters["min_price"])
    if filters["max_price"] is not None:
        clauses.append("s.min_price <= ?")
        params.append(filters["max_price"])
    return clauses, params


def product_card(row) -> dict:
    return {
        "product_id": row["product_id"],
        "persian_title": row["persian_title"],
        "brand_name": row["brand_name"],
        "model": row["model"],
        "category_name": row["category_name"],
        "primary_image_url": row["primary_image_url"],
        "min_price_toman": row["min_price"],
        "max_price_toman": row["max_price"],
        "offer_count": row["offer_count"] or 0,
        "shop_count": row["shop_count"] or 0,
    }


def product_detail(row) -> dict:
    card = {
        "product_id": row["product_id"],
        "persian_title": row["persian_title"],
        "brand_name": row["brand_name"],
        "model": row["model"],
        "category_name": row["category_name"],
        "primary_image_url": row["primary_image_url"],
        "min_price_toman": row["min_price"],
        "max_price_toman": row["max_price"],
        "offer_count": row["offer_count"] or 0,
        "shop_count": row["shop_count"] or 0,
        "image_urls": parse_image_urls(row["image_urls_json"]),
        "specs": parse_specs(row["specs_json"]),
    }
    return card


def coerce_id_list(value: object, *, limit: int) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        items = [part.strip() for part in value.split(",")]
    elif isinstance(value, (list, tuple)):
        items = value
    else:
        return []
    ids: list[str] = []
    for item in items:
        if not isinstance(item, str):
            continue
        text = item.strip()
        if text and text not in ids:
            ids.append(text)
        if len(ids) >= limit:
            break
    return ids
