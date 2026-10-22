"""Parse the CSV fields that the dataset profile actually contains."""

from __future__ import annotations

import json
import re

from backend.app.textnorm import clean_text, normalize_digits

EXPECTED_COLUMNS: dict[str, list[str]] = {
    "shops.csv": [
        "address",
        "category_names",
        "contacts",
        "instagram",
        "lat",
        "location_label",
        "lon",
        "name",
        "payment_options",
        "shop_id",
        "supports_fast_delivery",
        "website_url",
        "weekly_hours",
    ],
    "products.csv": [
        "brand_name",
        "category_name",
        "image_urls",
        "model",
        "persian_title",
        "product_id",
        "specs",
    ],
    "offers.csv": [
        "description",
        "last_price_changed_at",
        "offer_id",
        "price_toman",
        "product_id",
        "seller_title",
        "shop_id",
        "warranty",
    ],
}

_NUMBER = re.compile(r"\d+(?:\.\d+)?")


def assert_columns(fieldnames: list[str] | None, expected: list[str], filename: str) -> None:
    got = list(fieldnames or [])
    if set(got) != set(expected) or len(got) != len(set(got)):
        missing = sorted(set(expected) - set(got))
        extra = sorted(set(got) - set(expected))
        raise ValueError(
            f"{filename} columns do not match the dataset profile. missing={missing} extra={extra}"
        )


def parse_json_value(raw: object):
    text = clean_text(raw) if not isinstance(raw, (dict, list)) else None
    if isinstance(raw, (dict, list)):
        return raw
    if text is None:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def json_text(raw: object) -> str | None:
    """Keep the original JSON text when it parses. Drop literal null."""
    if isinstance(raw, (dict, list)):
        return json.dumps(raw, ensure_ascii=False, separators=(",", ":"))
    text = clean_text(raw)
    if text is None:
        return None
    try:
        json.loads(text)
    except json.JSONDecodeError:
        return None
    return text


def clean_bool(value: object) -> int | None:
    text = clean_text(value)
    if text is None:
        return None
    token = text.casefold()
    if token in {"true", "1", "yes"}:
        return 1
    if token in {"false", "0", "no"}:
        return 0
    return None


def clean_float(value: object) -> float | None:
    text = clean_text(value)
    if text is None:
        return None
    try:
        return float(normalize_digits(text))
    except ValueError:
        return None


def clean_price_field(value: object) -> tuple[int | None, bool]:
    """Return (price_to_store, discarded_dirty_number).

    Nulls stay null and are not counted as dirty. Numbers below 1000 or above 1e11
    are stored as null and counted as dirty, matching the dataset profile.
    """
    if value is None or isinstance(value, bool):
        return None, False
    if isinstance(value, str):
        raw = clean_text(value)
        if raw is None:
            return None, False
        text = normalize_digits(raw).replace(",", "").replace("٬", "").replace(" ", "")
        if not _NUMBER.fullmatch(text):
            return None, True
        number = float(text)
    elif isinstance(value, (int, float)):
        number = float(value)
    else:
        return None, True
    if number < 1000 or number > 1e11:
        return None, True
    return int(number), False


def clean_optional_int(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        raw = clean_text(value)
        if raw is None:
            return None
        text = normalize_digits(raw)
        if not text.isdigit():
            return None
        return int(text)
    if isinstance(value, (int, float)):
        return int(value)
    return None


def primary_image(value: object) -> str | None:
    if not isinstance(value, list):
        return None
    for item in value:
        if isinstance(item, str) and item.startswith(("http://", "https://")):
            return item
    return None


def parse_image_urls(raw: object) -> list[str]:
    value = raw if isinstance(raw, list) else parse_json_value(raw)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.startswith(("http://", "https://"))]


def parse_specs(raw: object) -> list[dict]:
    value = raw if isinstance(raw, list) else parse_json_value(raw)
    if not isinstance(value, list):
        return []
    specs: list[dict] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        specs.append(
            {
                "key": item.get("key"),
                "section": item.get("section"),
                "value": item.get("value"),
            }
        )
    return specs


def iter_categories(value: object):
    if not isinstance(value, list):
        return
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            continue
        name = item.strip()
        if not name or name.lower() == "null" or name in seen:
            continue
        seen.add(name)
        yield name


def iter_contacts(value: object):
    if not isinstance(value, list):
        return
    for item in value:
        if not isinstance(item, dict):
            continue
        channel = clean_text(item.get("channel"))
        number = clean_text(item.get("display_number"))
        if channel is None and number is None:
            continue
        yield channel, number


def iter_payments(value: object):
    if not isinstance(value, list):
        return
    for item in value:
        if not isinstance(item, dict):
            continue
        provider = clean_text(item.get("provider_name"))
        channel = clean_text(item.get("channel"))
        min_price, _ = clean_price_field(item.get("min_price_toman"))
        max_price, _ = clean_price_field(item.get("max_price_toman"))
        categories = item.get("category_names")
        if not isinstance(categories, list):
            categories = []
        yield (
            provider,
            channel,
            min_price,
            max_price,
            json.dumps(categories, ensure_ascii=False, separators=(",", ":")),
        )


def parse_warranty(value: object) -> tuple[str | None, int | None, str | None]:
    if not isinstance(value, dict):
        return None, None, None
    provider = clean_text(value.get("provider")) if not isinstance(value.get("provider"), (int, float)) else None
    if isinstance(value.get("provider"), str):
        provider = clean_text(value.get("provider"))
    description = clean_text(value.get("description")) if isinstance(value.get("description"), str) else None
    period = value.get("period_months")
    months = clean_optional_int(period)
    return provider, months, description
