"""In-person stores for a product, ordered by distance then price.

TODO: push haversine into Postgres earthdistance / geography, and add a weighted
rank over price, distance, freshness, and BNPL channel.
"""

from __future__ import annotations

from collections import defaultdict

from backend.app.db.connection import read_connection
from backend.app.freshness import describe_freshness
from backend.app.geo import haversine_km
from backend.app.textnorm import parse_user_int

_OFFER_SQL = """
    SELECT
        o.offer_id, o.product_id, o.shop_id, o.seller_title, o.description,
        o.price_toman, o.last_price_changed_at, o.warranty_provider,
        o.warranty_period_months, o.warranty_description,
        s.name, s.address, s.location_label, s.lat, s.lon, s.instagram,
        s.website_url, s.supports_fast_delivery
    FROM offers o
    JOIN shops s ON s.shop_id = o.shop_id
    WHERE o.product_id = ?
"""


def find_stores_for_product(
    product_id: str = "",
    user_lat=None,
    user_lon=None,
    max_distance_km=None,
    limit=None,
    **_,
) -> dict:
    # TODO: category-aware default radius instead of "no cap unless asked".
    return _stores_for_product(
        product_id=product_id,
        user_lat=user_lat,
        user_lon=user_lon,
        max_distance_km=max_distance_km,
        shop_ids=None,
        limit=_clamp_limit(limit, default=40, maximum=100),
    )


def compare_stores(
    shop_ids=None,
    product_id: str = "",
    user_lat=None,
    user_lon=None,
    **_,
) -> dict:
    # TODO: weighted ranking (price, distance, freshness, installment channel).
    from backend.app.tools.common import coerce_id_list

    ids = coerce_id_list(shop_ids, limit=8)
    if len(ids) < 2:
        return {"ok": False, "error": "حداقل دو فروشگاه لازم است.", "stores": []}
    result = _stores_for_product(
        product_id=product_id,
        user_lat=user_lat,
        user_lon=user_lon,
        max_distance_km=None,
        shop_ids=ids,
        limit=len(ids),
    )
    if not result.get("ok"):
        return result
    found = {store["shop_id"] for store in result["stores"]}
    result["missing_shop_ids"] = [shop_id for shop_id in ids if shop_id not in found]
    return result


def _stores_for_product(*, product_id, user_lat, user_lon, max_distance_km, shop_ids, limit: int) -> dict:
    product_id = str(product_id or "").strip()
    if not product_id:
        return {"ok": False, "error": "شناسهٔ محصول لازم است.", "stores": []}
    lat, lon, coord_error = _coords(user_lat, user_lon)
    if coord_error:
        return {"ok": False, "error": coord_error, "stores": []}
    distance_cap, distance_error = _distance(max_distance_km)
    if distance_error:
        return {"ok": False, "error": distance_error, "stores": []}

    with read_connection() as conn:
        title_row = conn.execute(
            "SELECT persian_title FROM products WHERE product_id = ?",
            (product_id,),
        ).fetchone()
        if title_row is None:
            return {"ok": False, "error": "محصول پیدا نشد.", "stores": []}
        sql = _OFFER_SQL
        params: list = [product_id]
        if shop_ids:
            marks = ",".join("?" * len(shop_ids))
            sql += f" AND o.shop_id IN ({marks})"
            params.extend(shop_ids)
        rows = conn.execute(sql, params).fetchall()
        shop_id_list = list({row["shop_id"] for row in rows})
        payments = _payments(conn, shop_id_list)

    grouped: dict[str, dict] = {}
    for row in rows:
        shop = grouped.get(row["shop_id"])
        if shop is None:
            distance = haversine_km(lat, lon, row["lat"], row["lon"]) if lat is not None else None
            flag = row["supports_fast_delivery"]
            shop = {
                "shop_id": row["shop_id"],
                "name": row["name"],
                "address": row["address"],
                "location_label": row["location_label"],
                "lat": row["lat"],
                "lon": row["lon"],
                "distance_km": distance,
                "supports_fast_delivery": None if flag is None else bool(flag),
                "instagram": row["instagram"],
                "website_url": row["website_url"],
                "payment_options": payments.get(row["shop_id"], []),
                "offers": [],
            }
            grouped[row["shop_id"]] = shop
        shop["offers"].append(_offer(row))

    stores = list(grouped.values())
    if distance_cap is not None:
        stores = [
            store
            for store in stores
            if store["distance_km"] is not None and store["distance_km"] <= distance_cap
        ]
    for store in stores:
        store["offers"].sort(key=lambda offer: (offer["price_toman"] is None, offer["price_toman"] or 0))
        priced = [offer for offer in store["offers"] if offer["price_toman"] is not None]
        if priced:
            cheapest = priced[0]
            store["best_price_toman"] = cheapest["price_toman"]
            store["cheapest_is_stale"] = cheapest["is_stale"]
        else:
            store["best_price_toman"] = None
            store["cheapest_is_stale"] = True
    stores.sort(
        key=lambda store: (
            store["distance_km"] is None,
            store["distance_km"] if store["distance_km"] is not None else 1e9,
            store["best_price_toman"] is None,
            store["best_price_toman"] if store["best_price_toman"] is not None else 1e18,
        )
    )
    truncated = len(stores) > limit
    stores = stores[:limit]
    return {
        "ok": True,
        "product_id": product_id,
        "product_title": title_row["persian_title"],
        "user_lat": lat,
        "user_lon": lon,
        "max_distance_km": distance_cap,
        "count": len(stores),
        "truncated": truncated,
        "stores": stores,
        "message_fa": None if stores else "فروشگاه حضوری در این محدوده پیدا نشد.",
    }


def _offer(row) -> dict:
    fresh = describe_freshness(row["last_price_changed_at"])
    warranty = None
    if row["warranty_provider"] or row["warranty_period_months"] or row["warranty_description"]:
        warranty = {
            "provider": row["warranty_provider"],
            "period_months": row["warranty_period_months"],
            "description": row["warranty_description"],
        }
    return {
        "offer_id": row["offer_id"],
        "seller_title": row["seller_title"],
        "description": row["description"],
        "price_toman": row["price_toman"],
        "warranty": warranty,
        **fresh,
    }


def _payments(conn, shop_ids: list[str]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for start in range(0, len(shop_ids), 400):
        chunk = shop_ids[start : start + 400]
        marks = ",".join("?" * len(chunk))
        rows = conn.execute(
            f"""
            SELECT shop_id, provider_name, channel
            FROM shop_payment_options
            WHERE shop_id IN ({marks})
            """,
            chunk,
        ).fetchall()
        for row in rows:
            grouped[row["shop_id"]].append(
                {"provider_name": row["provider_name"], "channel": row["channel"]}
            )
    return grouped


def _coords(lat, lon):
    if lat is None and lon is None:
        return None, None, None
    if lat is None or lon is None:
        return None, None, "lat و lon باید با هم باشند."
    try:
        lat_f = float(lat)
        lon_f = float(lon)
    except (TypeError, ValueError):
        return None, None, "مختصات نامعتبر است."
    if not (-90 <= lat_f <= 90 and -180 <= lon_f <= 180):
        return None, None, "مختصات خارج از محدوده است."
    return lat_f, lon_f, None


def _distance(value):
    if value is None or value == "":
        return None, None
    if isinstance(value, bool):
        return None, "max_distance_km نامعتبر است."
    if isinstance(value, (int, float)):
        number_f = float(value)
    else:
        parsed = parse_user_int(value)
        if parsed is None:
            return None, "max_distance_km نامعتبر است."
        number_f = float(parsed)
    if number_f <= 0 or number_f > 200:
        return None, "max_distance_km نامعتبر است."
    return number_f, None


def _clamp_limit(value, *, default: int, maximum: int) -> int:
    if value is None or value == "":
        return default
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return min(maximum, max(1, number))
