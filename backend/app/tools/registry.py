"""Tool schemas and dispatch. Every tool is read-only."""

from __future__ import annotations

import logging

from backend.app.db.connection import DatabaseNotReady
from backend.app.tools.check_freshness import check_store_freshness
from backend.app.tools.compare_products import compare_products
from backend.app.tools.contact_store import contact_store
from backend.app.tools.search_products import search_products
from backend.app.tools.stores import compare_stores, find_stores_for_product

logger = logging.getLogger("starcoach.tools")

TOOLS = {
    "search_products": search_products,
    "compare_products": compare_products,
    "find_stores_for_product": find_stores_for_product,
    "compare_stores": compare_stores,
    "check_store_freshness": check_store_freshness,
    "contact_store": contact_store,
}

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "search_products",
            "description": "جست‌وجوی محصول در دادهٔ ترب با عنوان فارسی، برند، مدل و دسته. قیمت و فروشگاه را از این ابزار نساز؛ فقط نتیجه را بگو.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "عبارت جست‌وجو، ترجیحاً نام کالا و برند"},
                    "brand": {"type": "string", "description": "فیلتر برند"},
                    "category": {"type": "string", "description": "فیلتر دسته"},
                    "min_price": {"type": "integer", "description": "کف قیمت تومان"},
                    "max_price": {"type": "integer", "description": "سقف قیمت تومان"},
                    "limit": {"type": "integer", "description": "حداکثر تعداد، تا ۵۰"},
                    "filters": {
                        "type": "object",
                        "description": "همان فیلترها اگر یکجا فرستاده شوند",
                        "properties": {
                            "brand": {"type": "string"},
                            "category": {"type": "string"},
                            "min_price": {"type": "integer"},
                            "max_price": {"type": "integer"},
                            "limit": {"type": "integer"},
                        },
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compare_products",
            "description": "مقایسهٔ مشخصات و بازهٔ قیمت چند محصول با شناسه‌هایی که search_products داده است.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "دو تا چهار product_id",
                    }
                },
                "required": ["product_ids"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_stores_for_product",
            "description": "فروشگاه‌های حضوری که این محصول را دارند، با فاصله از کاربر و وضعیت کهنه‌بودن قیمت.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "string"},
                    "user_lat": {"type": "number"},
                    "user_lon": {"type": "number"},
                    "max_distance_km": {"type": "number"},
                    "limit": {"type": "integer"},
                },
                "required": ["product_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compare_stores",
            "description": "مقایسهٔ پیشنهادهای یک محصول بین چند فروشگاه: قیمت، فاصله، تازگی و شیوهٔ پرداخت.",
            "parameters": {
                "type": "object",
                "properties": {
                    "shop_ids": {"type": "array", "items": {"type": "string"}},
                    "product_id": {"type": "string"},
                    "user_lat": {"type": "number"},
                    "user_lon": {"type": "number"},
                },
                "required": ["shop_ids", "product_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_store_freshness",
            "description": "تازگی قیمت یک پیشنهاد از روی last_price_changed_at.",
            "parameters": {
                "type": "object",
                "properties": {"offer_id": {"type": "string"}},
                "required": ["offer_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "contact_store",
            "description": "اطلاعات تماس فروشگاه را برمی‌گرداند. شماره‌ها ساختگی هستند و این ابزار تماس یا پیام واقعی نمی‌فرستد.",
            "parameters": {
                "type": "object",
                "properties": {"shop_id": {"type": "string"}},
                "required": ["shop_id"],
            },
        },
    },
]


def execute_tool(name: str, arguments: dict | None) -> dict:
    fn = TOOLS.get(name)
    if fn is None:
        return {"ok": False, "error": "ابزار ناشناخته است."}
    try:
        result = fn(**(arguments or {}))
    except DatabaseNotReady:
        raise
    except TypeError:
        logger.exception("bad arguments for %s", name)
        return {"ok": False, "error": "ورودی ابزار نامعتبر است."}
    except Exception:
        logger.exception("tool %s failed", name)
        return {"ok": False, "error": "اجرای ابزار ناموفق بود."}
    if not isinstance(result, dict):
        return {"ok": False, "error": "پاسخ ابزار نامعتبر است."}
    return result
