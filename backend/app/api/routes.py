"""HTTP API. Card views call these routes directly; /chat goes through the agent."""

from __future__ import annotations

import logging
import sqlite3
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.app.agent.orchestrator import run_turn
from backend.app.config import get_settings
from backend.app.db.connection import DatabaseNotReady, database_ready, read_connection
from backend.app.tools.check_freshness import check_store_freshness
from backend.app.tools.compare_products import compare_products
from backend.app.tools.contact_store import contact_store
from backend.app.tools.search_products import get_product, search_products
from backend.app.tools.stores import compare_stores, find_stores_for_product

logger = logging.getLogger("starcoach.api")
router = APIRouter()


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=4000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    lat: float | None = None
    lon: float | None = None
    history: list[ChatTurn] = Field(default_factory=list, max_length=12)


def health_payload() -> dict:
    if not database_ready():
        return {
            "status": "ok",
            "db_ready": False,
            "products": 0,
            "offers": 0,
            "shops": 0,
            "built_at": None,
            "llm_configured": get_settings().llm_configured,
        }
    with read_connection() as conn:
        meta = {row["key"]: row["value"] for row in conn.execute("SELECT key, value FROM meta")}
    return {
        "status": "ok",
        "db_ready": True,
        "products": int(meta.get("products") or 0),
        "offers": int(meta.get("offers") or 0),
        "shops": int(meta.get("shops") or 0),
        "built_at": meta.get("built_at"),
        "fts": meta.get("fts"),
        "stale_price_days": get_settings().stale_price_days,
        "llm_configured": get_settings().llm_configured,
    }


@router.get("/health")
@router.get("/api/health")
def health() -> dict:
    return health_payload()


@router.get("/api/meta")
def meta() -> dict:
    return health_payload()


@router.get("/api/products/search")
def search_route(
    q: str = Query("", max_length=200),
    brand: str | None = Query(None, max_length=80),
    category: str | None = Query(None, max_length=80),
    min_price: str | None = Query(None, max_length=20),
    max_price: str | None = Query(None, max_length=20),
    limit: int = Query(20, ge=1, le=50),
) -> dict:
    try:
        return search_products(
            q,
            {
                "brand": brand,
                "category": category,
                "min_price": min_price,
                "max_price": max_price,
                "limit": limit,
            },
        )
    except sqlite3.Error:
        logger.exception("search failed")
        raise HTTPException(status_code=500, detail="جست‌وجو انجام نشد.") from None


@router.get("/api/products/{product_id}")
def product_route(product_id: str) -> dict:
    try:
        product = get_product(product_id)
    except sqlite3.Error:
        logger.exception("product read failed")
        raise HTTPException(status_code=500, detail="خواندن محصول انجام نشد.") from None
    if product is None:
        raise HTTPException(status_code=404, detail="محصول پیدا نشد.")
    return {"ok": True, "product": product}


@router.get("/api/products/{product_id}/stores")
def stores_route(
    product_id: str,
    lat: float | None = None,
    lon: float | None = None,
    max_distance_km: float | None = Query(None, gt=0, le=200),
    limit: int = Query(40, ge=1, le=100),
) -> dict:
    lat, lon = _coords_or_400(lat, lon)
    try:
        result = find_stores_for_product(
            product_id,
            user_lat=lat,
            user_lon=lon,
            max_distance_km=max_distance_km,
            limit=limit,
        )
    except sqlite3.Error:
        logger.exception("store lookup failed")
        raise HTTPException(status_code=500, detail="فروشگاه‌ها خوانده نشدند.") from None
    return _ok(result)


@router.get("/api/compare/products")
def compare_products_route(ids: str = Query("", max_length=500)) -> dict:
    try:
        result = compare_products(ids)
    except sqlite3.Error:
        logger.exception("compare products failed")
        raise HTTPException(status_code=500, detail="مقایسه انجام نشد.") from None
    return _ok(result)


@router.get("/api/compare/stores")
def compare_stores_route(
    product_id: str = Query(..., max_length=80),
    shop_ids: str = Query("", max_length=800),
    lat: float | None = None,
    lon: float | None = None,
) -> dict:
    lat, lon = _coords_or_400(lat, lon)
    try:
        result = compare_stores(shop_ids, product_id, user_lat=lat, user_lon=lon)
    except sqlite3.Error:
        logger.exception("compare stores failed")
        raise HTTPException(status_code=500, detail="مقایسهٔ فروشگاه انجام نشد.") from None
    return _ok(result)


@router.get("/api/offers/{offer_id}/freshness")
def freshness_route(offer_id: str) -> dict:
    try:
        result = check_store_freshness(offer_id)
    except sqlite3.Error:
        logger.exception("freshness failed")
        raise HTTPException(status_code=500, detail="تازگی قیمت خوانده نشد.") from None
    return _ok(result)


@router.get("/api/shops/{shop_id}/contact")
def contact_route(shop_id: str) -> dict:
    try:
        result = contact_store(shop_id)
    except sqlite3.Error:
        logger.exception("contact failed")
        raise HTTPException(status_code=500, detail="اطلاعات تماس خوانده نشد.") from None
    return _ok(result)


@router.post("/chat")
@router.post("/api/chat")
def chat_route(body: ChatRequest) -> dict:
    lat, lon = _coords_or_400(body.lat, body.lon)
    return run_turn(body.message, [turn.model_dump() for turn in body.history], lat, lon)


def _ok(result: dict) -> dict:
    if result.get("ok"):
        return result
    error = result.get("error") or "درخواست انجام نشد."
    status = 404 if "پیدا نشد" in error else 400
    raise HTTPException(status_code=status, detail=error)


def _coords_or_400(lat: float | None, lon: float | None) -> tuple[float | None, float | None]:
    if lat is None and lon is None:
        return None, None
    if lat is None or lon is None:
        raise HTTPException(status_code=400, detail="lat و lon باید با هم ارسال شوند.")
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise HTTPException(status_code=400, detail="مختصات نامعتبر است.")
    return lat, lon
