"""Spec and price comparison across a handful of products.

TODO: align synonymous spec keys (رنگ / Color), score which fields differ,
and attach embedding similarity when pgvector is available.
"""

from __future__ import annotations

from backend.app.db.connection import read_connection
from backend.app.tools.common import coerce_id_list, product_detail

_SELECT = """
    p.product_id, p.persian_title, p.brand_name, p.model, p.category_name,
    p.primary_image_url, p.image_urls_json, p.specs_json,
    s.min_price AS min_price, s.max_price AS max_price,
    s.offer_count AS offer_count, s.shop_count AS shop_count
    FROM products p
    LEFT JOIN product_price_stats s ON s.product_id = p.product_id
"""


def compare_products(product_ids=None, **_) -> dict:
    # TODO: synonym alignment, diff scoring, embeddings.
    ids = coerce_id_list(product_ids, limit=4)
    if len(ids) < 2:
        return {"ok": False, "error": "حداقل دو شناسهٔ محصول لازم است.", "products": [], "rows": []}
    marks = ",".join("?" * len(ids))
    with read_connection() as conn:
        rows = conn.execute(
            f"SELECT {_SELECT} WHERE p.product_id IN ({marks})",
            ids,
        ).fetchall()
    by_id = {row["product_id"]: product_detail(row) for row in rows}
    products = [by_id[product_id] for product_id in ids if product_id in by_id]
    missing = [product_id for product_id in ids if product_id not in by_id]
    if len(products) < 2:
        return {
            "ok": False,
            "error": "برای مقایسه دست‌کم دو محصول موجود لازم است.",
            "products": products,
            "rows": [],
            "missing_ids": missing,
        }

    order: list[tuple[str, str]] = []
    values: dict[tuple[str, str], dict] = {}
    for product in products:
        for spec in product["specs"]:
            key = (spec.get("section") or "", spec.get("key") or "")
            if key not in values:
                values[key] = {}
                order.append(key)
            values[key].setdefault(product["product_id"], spec.get("value"))
    table = [
        {"section": section, "key": key, "values": values[(section, key)]}
        for section, key in order
    ]
    return {
        "ok": True,
        "products": products,
        "rows": table,
        "missing_ids": missing,
        "message_fa": None,
    }
