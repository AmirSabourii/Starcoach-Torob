"""Run a grounded turn.

The model may choose tools. The sentence the user sees is built from tool
payloads, so a fluent hallucination cannot introduce a price or a shop.

TODO: a citation check that can safely surface model prose when every number
in it already appears in the tool JSON.
TODO: embeddings hybrid behind search_products once pgvector is available.
"""

from __future__ import annotations

import json
import logging

from backend.app.agent.llm import LLMClient, LLMError
from backend.app.format_fa import fa_int, fa_km
from backend.app.textnorm import tokenize
from backend.app.tools.registry import TOOL_SCHEMAS, execute_tool
from backend.app.tools.search_products import search_products
from backend.app.tools.stores import find_stores_for_product

logger = logging.getLogger("starcoach.agent")

SYSTEM_PROMPT = """تو دستیار خرید حضوری «استارکوچ» هستی.
فقط داده‌ای را بگو که ابزارها از ترب برمی‌گردانند.
هرگز محصول، قیمت، فروشگاه، آدرس یا موجودی نساز.
اگر سؤال دربارهٔ کالا، قیمت، مقایسه، فروشگاه حضوری، تازگی قیمت یا تماس است، ابزار مناسب را صدا بزن.
اگر ابزار خالی بود، بگو پیدا نشد.
شمارهٔ فروشگاه‌ها ساختگی (FAKE) است. contact_store تماس یا پیام واقعی نمی‌فرستد؛ به کاربر هشدار بده.
مختصات داخل پیام کاربر را برای find_stores_for_product و compare_stores به کار ببر.
پاسخ را کوتاه و فارسی نگه دار و شناسه نساز.
"""

_CARD_KEYS = (
    "product_id",
    "persian_title",
    "brand_name",
    "model",
    "category_name",
    "primary_image_url",
    "min_price_toman",
    "max_price_toman",
    "offer_count",
    "shop_count",
)


def run_turn(message: str, history: list[dict] | None, lat: float | None, lon: float | None) -> dict:
    client = LLMClient()
    if not client.configured:
        return _fallback(message, lat, lon, mode="fallback")
    try:
        return _llm_turn(client, message, history or [], lat, lon)
    except LLMError as exc:
        logger.warning("llm failed: %s", exc)
        return _fallback(message, lat, lon, mode="llm_error")


def _llm_turn(client: LLMClient, message: str, history: list[dict], lat, lon) -> dict:
    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for turn in history[-8:]:
        role = turn.get("role")
        content = turn.get("content")
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": str(content)[:4000]})
    user_text = message.strip()
    if lat is not None and lon is not None:
        user_text += f"\n[user_lat={lat} user_lon={lon}]"
    messages.append({"role": "user", "content": user_text})

    calls: list[dict] = []
    for _ in range(4):
        data = client.complete(messages, TOOL_SCHEMAS, "auto")
        assistant = data["choices"][0].get("message") or {}
        tool_calls = assistant.get("tool_calls") or []
        if not tool_calls:
            break
        messages.append(
            {
                "role": "assistant",
                "content": assistant.get("content"),
                "tool_calls": tool_calls,
            }
        )
        for index, call in enumerate(tool_calls, start=1):
            function = call.get("function") or {}
            name = function.get("name") or ""
            arguments = _parse_args(function.get("arguments"))
            if lat is not None and name in {"find_stores_for_product", "compare_stores"}:
                arguments["user_lat"] = lat
                arguments["user_lon"] = lon
            result = execute_tool(name, arguments)
            calls.append({"name": name, "arguments": arguments, "result": result})
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.get("id") or f"call_{len(calls)}_{index}",
                    "content": json.dumps(_shrink(result), ensure_ascii=False),
                }
            )
    products, stores = _extract_cards(calls)
    return {
        "reply": _compose(calls),
        "mode": "llm",
        "grounded": True,
        "tool_calls": _public_calls(calls),
        "products": products,
        "stores": stores,
    }


def _fallback(message: str, lat, lon, *, mode: str) -> dict:
    note = _fallback_note(mode)
    if not tokenize(message):
        return {
            "reply": note + "\n" + _compose([]),
            "mode": mode,
            "grounded": True,
            "tool_calls": [],
            "products": [],
            "stores": [],
        }
    calls = []
    search = search_products(message, limit=8)
    calls.append({"name": "search_products", "arguments": {"query": message, "limit": 8}, "result": search})
    products = search.get("products") or []
    if len(products) == 1 and lat is not None and lon is not None:
        stores = find_stores_for_product(products[0]["product_id"], user_lat=lat, user_lon=lon, max_distance_km=10)
        calls.append(
            {
                "name": "find_stores_for_product",
                "arguments": {"product_id": products[0]["product_id"], "user_lat": lat, "user_lon": lon},
                "result": stores,
            }
        )
    cards, store_cards = _extract_cards(calls)
    return {
        "reply": note + "\n" + _compose(calls),
        "mode": mode,
        "grounded": True,
        "tool_calls": _public_calls(calls),
        "products": cards,
        "stores": store_cards,
    }


def _fallback_note(mode: str) -> str:
    if mode == "llm_error":
        return "ارتباط با مدل زبانی برقرار نشد. نتیجهٔ زیر فقط از جست‌وجوی داده است."
    return "اتصال مدل زبانی تنظیم نشده است. این متن فقط از نتیجهٔ ابزار روی دادهٔ ترب ساخته شده."


def _compose(calls: list[dict]) -> str:
    if not calls:
        return (
            "سلام. نام کالا را بگویید تا در دادهٔ ترب بگردم، فروشگاه حضوری را با فاصله نشان بدهم "
            "و قیمت‌ها را مقایسه کنم. شمارهٔ فروشگاه‌ها ساختگی است و تماسی گرفته نمی‌شود."
        )
    parts: list[str] = []
    for call in calls:
        result = call.get("result") or {}
        name = call.get("name")
        if result.get("ok") is False:
            parts.append(result.get("error") or "ابزار به خطا خورد.")
            continue
        if name == "search_products":
            products = result.get("products") or []
            if not products:
                parts.append(result.get("message_fa") or "محصولی پیدا نشد.")
            else:
                top = products[0]
                title = top.get("persian_title") or "بدون عنوان"
                parts.append(f"{fa_int(len(products))} محصول پیدا شد. اولین مورد: {title} ({_price_phrase(top)}).")
        elif name in {"find_stores_for_product", "compare_stores"}:
            parts.append(_store_sentence(result))
        elif name == "compare_products":
            count = len(result.get("products") or [])
            parts.append(f"مقایسهٔ {fa_int(count)} محصول از روی مشخصات و بازهٔ قیمت دادهٔ ترب آماده است.")
        elif name == "check_store_freshness":
            parts.append(result.get("freshness_label_fa") or result.get("label_fa") or "وضعیت قیمت مشخص نشد.")
        elif name == "contact_store":
            parts.append(result.get("disclaimer_fa") or "شماره‌ها ساختگی است.")
            shop_name = result.get("name") or "فروشگاه"
            parts.append(f"اطلاعات تماس {shop_name} فقط برای بررسی انسانی نمایش داده شد.")
        else:
            parts.append("ابزار ناشناخته اجرا شد و نتیجه‌اش در کارت‌ها نیامده است.")
    return "\n".join(parts)


def _store_sentence(result: dict) -> str:
    stores = result.get("stores") or []
    if not stores:
        return result.get("message_fa") or "فروشگاه حضوری پیدا نشد."
    near = stores[0]
    sentence = f"{fa_int(len(stores))} فروشگاه حضوری پیدا شد. نزدیک‌ترین: {near.get('name') or 'فروشگاه'}"
    distance = near.get("distance_km")
    if isinstance(distance, (int, float)):
        sentence += f" در {fa_km(distance)}"
    if near.get("best_price_toman") is not None:
        sentence += f"، {fa_int(near['best_price_toman'])} تومان"
    sentence += "."
    if near.get("cheapest_is_stale"):
        sentence += " قیمت این فروشگاه کهنه است."
    return sentence


def _price_phrase(product: dict) -> str:
    low = product.get("min_price_toman")
    high = product.get("max_price_toman")
    if low is None and high is None:
        return "قیمت نامشخص"
    if low is None or high is None or low == high:
        return fa_int(low if low is not None else high) + " تومان"
    return f"از {fa_int(low)} تا {fa_int(high)} تومان"


def _extract_cards(calls: list[dict]) -> tuple[list[dict], list[dict]]:
    products: list[dict] = []
    stores: list[dict] = []
    seen_products: set[str] = set()
    seen_stores: set[tuple] = set()
    for call in calls:
        result = call.get("result") or {}
        for product in result.get("products") or []:
            product_id = product.get("product_id")
            if not product_id or product_id in seen_products:
                continue
            seen_products.add(product_id)
            products.append({key: product.get(key) for key in _CARD_KEYS})
        for store in result.get("stores") or []:
            key = (result.get("product_id"), store.get("shop_id"))
            if key in seen_stores:
                continue
            seen_stores.add(key)
            item = dict(store)
            item["product_id"] = result.get("product_id")
            item["product_title"] = result.get("product_title")
            stores.append(item)
    return products[:12], stores[:12]


def _public_calls(calls: list[dict]) -> list[dict]:
    return [
        {"name": call["name"], "arguments": call["arguments"], "result": _shrink(call["result"])}
        for call in calls
    ]


def _shrink(result: dict) -> dict:
    data = dict(result)
    products = data.get("products")
    if isinstance(products, list):
        slim = []
        for product in products[:8]:
            item = dict(product)
            specs = item.get("specs")
            if isinstance(specs, list):
                item["specs"] = specs[:20]
            slim.append(item)
        data["products"] = slim
        if len(products) > 8:
            data["truncated_for_model"] = True
    stores = data.get("stores")
    if isinstance(stores, list) and len(stores) > 6:
        data["stores"] = stores[:6]
        data["truncated_for_model"] = True
    rows = data.get("rows")
    if isinstance(rows, list) and len(rows) > 30:
        data["rows"] = rows[:30]
        data["truncated_for_model"] = True
    return data


def _parse_args(raw) -> dict:
    if raw is None or raw == "":
        return {}
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}
