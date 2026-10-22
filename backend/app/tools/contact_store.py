"""Return a shop's contact fields for a human to review.

IMPORTANT: phone numbers in this dataset are FAKE.
This step is simulated and human-in-the-loop. It must never place a call,
send an SMS, or talk to a messaging provider.

TODO: a review queue where a person confirms the next step. Do not wire a dialer.
"""

from __future__ import annotations

import json

from backend.app.cleaning import parse_json_value
from backend.app.db.connection import read_connection

DISCLAIMER_FA = (
    "شماره‌های تماس این مجموعه داده ساختگی (FAKE) هستند. "
    "این گام شبیه‌سازی‌شده و نیازمند تأیید انسان است و هیچ تماس یا پیام واقعی ارسال نمی‌شود."
)


def contact_store(shop_id: str = "", **_) -> dict:
    # TODO: human-in-the-loop outbox. Never add a dialer or SMS provider.
    shop_id = str(shop_id or "").strip()
    if not shop_id:
        return {"ok": False, "error": "شناسهٔ فروشگاه لازم است.", "simulated": True, "disclaimer_fa": DISCLAIMER_FA}
    with read_connection() as conn:
        shop = conn.execute("SELECT * FROM shops WHERE shop_id = ?", (shop_id,)).fetchone()
        if shop is None:
            return {
                "ok": False,
                "error": "فروشگاه پیدا نشد.",
                "simulated": True,
                "disclaimer_fa": DISCLAIMER_FA,
            }
        contacts = conn.execute(
            "SELECT channel, display_number FROM shop_contacts WHERE shop_id = ?",
            (shop_id,),
        ).fetchall()
        payments = conn.execute(
            "SELECT provider_name, channel FROM shop_payment_options WHERE shop_id = ?",
            (shop_id,),
        ).fetchall()
    return {
        "ok": True,
        "simulated": True,
        "human_in_the_loop": True,
        "disclaimer_fa": DISCLAIMER_FA,
        "shop_id": shop["shop_id"],
        "name": shop["name"],
        "address": shop["address"],
        "location_label": shop["location_label"],
        "lat": shop["lat"],
        "lon": shop["lon"],
        "instagram": shop["instagram"],
        "website_url": shop["website_url"],
        "contacts": [
            {"channel": row["channel"], "display_number": row["display_number"]}
            for row in contacts
        ],
        "weekly_hours": parse_json_value(shop["weekly_hours_json"]),
        "payment_options": [
            {"provider_name": row["provider_name"], "channel": row["channel"]}
            for row in payments
        ],
        "contacts_raw": _loads(shop["contacts_json"]),
    }


def _loads(raw: str | None):
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None
