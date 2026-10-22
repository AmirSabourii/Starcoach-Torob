"""HTTP API over the validated tools. /chat calls the agent; card routes call the tools directly."""

from __future__ import annotations

import json
import logging
import os
import sqlite3

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

import backend.app.engine  # noqa: F401  puts the engine on sys.path
import agent
import tools
from gt_lib import DatabaseNotReady, connect, days_old, db_path

from backend.app.config import get_settings

logger = logging.getLogger("starcoach.api")
router = APIRouter()


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    lat: float | None = None
    lon: float | None = None
    history: list[dict] = Field(default_factory=list)


def _apply_llm_env() -> None:
    settings = get_settings()
    if settings.boxapi_api_key.strip():
        os.environ["BOXAPI_API_KEY"] = settings.boxapi_api_key.strip()
    if settings.boxapi_base_url.strip():
        os.environ["BOXAPI_BASE_URL"] = settings.boxapi_base_url.strip()
    if settings.boxapi_model.strip():
        os.environ["BOXAPI_MODEL"] = settings.boxapi_model.strip()
    if settings.database_path.strip():
        os.environ["DATABASE_PATH"] = settings.database_path.strip()
    if settings.data_dir.strip():
        os.environ["DATA_DIR"] = settings.data_dir.strip()


def _require_db() -> None:
    if not os.path.exists(db_path()):
        raise DatabaseNotReady(db_path())


def health_payload() -> dict:
    settings = get_settings()
    payload = {
        "status": "ok",
        "db_ready": False,
        "products": 0,
        "offers": 0,
        "shops": 0,
        "built_at": None,
        "llm_configured": settings.llm_configured,
        "model": settings.boxapi_model or agent.MODEL,
        "base_url": settings.boxapi_base_url or agent.DEFAULT_BASE_URL,
        "recall_default_on": True,
        "stale_price_days": tools.STALE_DAYS,
        "embeddings_model": "text-embedding-3-small",
    }
    path = db_path()
    if not os.path.exists(path):
        return payload
    try:
        con = connect(path)
        for table in ("products", "offers", "shops"):
            payload[table] = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        meta = {row[0]: row[1] for row in con.execute("SELECT key, value FROM meta")}
        payload["built_at"] = meta.get("built_at")
        payload["db_ready"] = True
    except sqlite3.Error:
        logger.exception("health read failed")
        payload["db_ready"] = False
    return payload


def _present_products(payload: dict) -> dict:
    """Attach image and last price-change for the UI. Does not change the tool functions."""
    rows = list(payload.get("results") or []) + list(payload.get("items") or [])
    if isinstance(payload.get("products"), list):
        rows += payload["products"]
    ids = [row.get("product_id") for row in rows if row.get("product_id")]
    if not ids:
        return payload
    marks = ",".join("?" * len(ids))
    images = {}
    for pid, raw in tools.con.execute(
        f"SELECT product_id, image_urls FROM products WHERE product_id IN ({marks})", ids
    ):
        try:
            urls = json.loads(raw) if raw else []
        except json.JSONDecodeError:
            urls = []
        images[pid] = urls[0] if urls else None
    latest = {
        pid: ts
        for pid, ts in tools.con.execute(
            f"SELECT product_id, latest_price_change FROM product_stats WHERE product_id IN ({marks})", ids
        )
    }
    for row in rows:
        pid = row.get("product_id")
        if not pid:
            continue
        row["image"] = images.get(pid)
        ts = latest.get(pid)
        row["latest_price_change"] = (ts or "")[:10] or None
        days = days_old(ts) if ts else None
        row["days_since_update"] = days
        if "stale_price" not in row:
            row["stale_price"] = days is None or days > tools.STALE_DAYS
    return payload


@router.get("/health")
@router.get("/api/health")
def health() -> dict:
    _apply_llm_env()
    return health_payload()


@router.get("/api/products/search")
def search_route(
    q: str = Query("", max_length=200),
    brand: str | None = Query(None, max_length=80),
    category: str | None = Query(None, max_length=80),
    min_price: float | None = None,
    max_price: float | None = None,
    limit: int = Query(10, ge=1, le=15),
) -> dict:
    _require_db()
    _apply_llm_env()
    # Recall stays on for the agent. Direct catalogue search uses the lexical
    # tool when no key is configured, because the match-grader otherwise
    # fail-closes to an empty list.
    if get_settings().llm_configured:
        payload = tools.search_products(q, brand=brand, category=category, min_price=min_price, max_price=max_price, limit=limit)
        payload["retrieval"] = "hybrid"
    else:
        payload = tools.search_products_lexical(q, brand=brand, category=category, min_price=min_price, max_price=max_price, limit=limit)
        payload["retrieval"] = "lexical"
    return _present_products(payload)


@router.get("/api/products/{product_id}")
def product_route(product_id: str) -> dict:
    _require_db()
    row = tools.con.execute(
        """SELECT p.product_id, p.persian_title, p.brand_name, p.category_name, p.model, p.image_urls,
                  s.min_price, s.max_price, s.n_shops, s.n_priced, s.latest_price_change
           FROM products p LEFT JOIN product_stats s USING(product_id) WHERE p.product_id=?""",
        (product_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="محصول پیدا نشد.")
    try:
        urls = json.loads(row["image_urls"]) if row["image_urls"] else []
    except json.JSONDecodeError:
        urls = []
    ts = row["latest_price_change"]
    days = days_old(ts) if ts else None
    return {
        "product_id": row["product_id"],
        "title": row["persian_title"],
        "brand": row["brand_name"],
        "category": row["category_name"],
        "model": row["model"],
        "image": urls[0] if urls else None,
        "min_price": row["min_price"],
        "max_price": row["max_price"],
        "n_shops": row["n_shops"],
        "n_shops_priced": row["n_priced"],
        "latest_price_change": (ts or "")[:10] or None,
        "days_since_update": days,
        "stale_price": days is None or (days > tools.STALE_DAYS),
    }


@router.get("/api/products/{product_id}/stores")
def stores_route(
    product_id: str,
    lat: float | None = None,
    lon: float | None = None,
    max_distance_km: float | None = Query(None, gt=0, le=200),
    limit: int = Query(10, ge=1, le=15),
    sort_by: str = Query("distance", pattern="^(distance|price)$"),
    address_contains: str | None = Query(None, max_length=80),
    payment_provider: str | None = Query(None, max_length=40),
) -> dict:
    _require_db()
    _coords(lat, lon)
    return tools.find_stores_for_product(
        product_id,
        user_lat=lat,
        user_lon=lon,
        max_distance_km=max_distance_km,
        limit=limit,
        sort_by=sort_by,
        address_contains=address_contains,
        payment_provider=payment_provider,
    )


@router.get("/api/compare/products")
def compare_products_route(ids: str = Query(..., max_length=500)) -> dict:
    _require_db()
    product_ids = [part.strip() for part in ids.split(",") if part.strip()]
    if len(product_ids) < 2:
        raise HTTPException(status_code=400, detail="حداقل دو محصول برای مقایسه لازم است.")
    return tools.compare_products(product_ids)


@router.get("/api/compare/stores")
def compare_stores_route(
    product_id: str = Query(..., max_length=80),
    shop_ids: str = Query(..., max_length=800),
    lat: float | None = None,
    lon: float | None = None,
) -> dict:
    _require_db()
    _coords(lat, lon)
    ids = [part.strip() for part in shop_ids.split(",") if part.strip()]
    return tools.compare_stores(ids, product_id, user_lat=lat, user_lon=lon)


@router.get("/api/shops/{shop_id}/contact")
def contact_route(shop_id: str) -> dict:
    _require_db()
    return tools.contact_store(shop_id=shop_id)


@router.get("/api/freshness")
def freshness_route(
    offer_id: str | None = None,
    product_id: str | None = None,
    shop_id: str | None = None,
) -> dict:
    _require_db()
    return tools.check_store_freshness(offer_id=offer_id, product_id=product_id, shop_id=shop_id)


@router.get("/api/stores/search")
def search_stores_route(
    name: str | None = Query(None, max_length=80),
    address_contains: str | None = Query(None, max_length=80),
    payment_provider: str | None = Query(None, max_length=40),
    in_person_only: bool = False,
    sells_category: str | None = Query(None, max_length=80),
    installment_any: bool = False,
    lat: float | None = None,
    lon: float | None = None,
    limit: int = Query(8, ge=1, le=12),
) -> dict:
    _require_db()
    _coords(lat, lon)
    return tools.search_stores(
        name=name,
        address_contains=address_contains,
        payment_provider=payment_provider,
        in_person_only=in_person_only,
        sells_category=sells_category,
        user_lat=lat,
        user_lon=lon,
        limit=limit,
        installment_any=installment_any,
    )


@router.get("/api/browse")
def browse_route(
    category: str | None = Query(None, max_length=80),
    brand: str | None = Query(None, max_length=80),
    min_price: float | None = None,
    max_price: float | None = None,
    sort_by: str = Query("popularity", pattern="^(popularity|price|price_desc)$"),
    limit: int = Query(8, ge=1, le=12),
    include_used: bool = False,
    title_contains: str | None = Query(None, max_length=80),
    exclude_basic_phones: bool = False,
    exclude_brand: str | None = Query(None, max_length=80),
) -> dict:
    _require_db()
    payload = tools.browse_catalog(
        category=category,
        brand=brand,
        min_price=min_price,
        max_price=max_price,
        sort_by=sort_by,
        limit=limit,
        include_used=include_used,
        title_contains=title_contains,
        exclude_basic_phones=exclude_basic_phones,
        exclude_brand=exclude_brand,
    )
    return _present_products(payload)


@router.post("/chat")
@router.post("/api/chat")
def chat_route(body: ChatRequest) -> dict:
    _apply_llm_env()
    _coords(body.lat, body.lon)
    settings = get_settings()
    if not settings.llm_configured:
        raise HTTPException(
            status_code=503,
            detail="کلید مدل تنظیم نشده است. BOXAPI_API_KEY را در محیط اجرا قرار دهید. هیچ محصولی ساخته نمی‌شود.",
        )
    _require_db()
    try:
        result = agent.run_agent(body.message, user_lat=body.lat, user_lon=body.lon)
    except Exception:
        logger.exception("agent failed")
        raise HTTPException(status_code=502, detail="مدل پاسخ نداد. دوباره تلاش کنید.") from None
    calls = []
    for call in result.get("tool_calls") or []:
        raw = call.get("result")
        parsed = raw
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                parsed = {"raw": raw}
        if isinstance(parsed, dict):
            parsed = _present_products(parsed)
        calls.append({"name": call.get("name"), "args": call.get("args"), "result": parsed})
    return {
        "ok": True,
        "answer": result.get("final_answer") or "",
        "tool_calls": calls,
        "usage": result.get("usage"),
        "llm_configured": True,
    }


def _coords(lat: float | None, lon: float | None) -> None:
    if lat is None and lon is None:
        return
    if lat is None or lon is None:
        raise HTTPException(status_code=400, detail="lat و lon باید با هم ارسال شوند.")
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise HTTPException(status_code=400, detail="مختصات نامعتبر است.")
