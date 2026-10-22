"""Price age for one offer, from offers.last_price_changed_at.

TODO: category-specific stale windows. The threshold is STALE_PRICE_DAYS.
"""

from __future__ import annotations

from backend.app.db.connection import read_connection
from backend.app.freshness import describe_freshness


def check_store_freshness(offer_id: str = "", **_) -> dict:
    # TODO: per-category stale windows instead of one global threshold.
    offer_id = str(offer_id or "").strip()
    if not offer_id:
        return {"ok": False, "error": "شناسهٔ پیشنهاد لازم است."}
    with read_connection() as conn:
        row = conn.execute(
            """
            SELECT offer_id, product_id, shop_id, seller_title, price_toman, last_price_changed_at
            FROM offers
            WHERE offer_id = ?
            """,
            (offer_id,),
        ).fetchone()
    if row is None:
        return {"ok": False, "error": "پیشنهاد پیدا نشد."}
    fresh = describe_freshness(row["last_price_changed_at"])
    return {
        "ok": True,
        "offer_id": row["offer_id"],
        "product_id": row["product_id"],
        "shop_id": row["shop_id"],
        "seller_title": row["seller_title"],
        "price_toman": row["price_toman"],
        **fresh,
        "label_fa": fresh["freshness_label_fa"],
    }
