"""Hybrid Persian product search: FTS5 unicode61, then trigram.

TODO: blend this rank with a pgvector cosine score once embeddings exist.
The SQL filters (brand, category, price) stay in the database either way.
"""

from __future__ import annotations

import sqlite3

from backend.app.db.connection import read_connection
from backend.app.textnorm import normalize_fa, tokenize
from backend.app.tools.common import (
    coerce_filters,
    filter_clauses,
    product_card,
    product_detail,
    public_filters,
)

_FTS_TABLES = {"products_fts", "products_trgm"}

_SELECT = """
    p.product_id, p.persian_title, p.brand_name, p.model, p.category_name,
    p.primary_image_url, p.image_urls_json, p.specs_json,
    s.min_price AS min_price, s.max_price AS max_price,
    s.offer_count AS offer_count, s.shop_count AS shop_count
"""


def search_products(query: str = "", filters: dict | None = None, **extra) -> dict:
    parsed = coerce_filters(filters, **extra)
    tokens = tokenize(query)
    limit = parsed["limit"]
    with read_connection() as conn:
        if not tokens:
            if not any(parsed[key] is not None for key in ("brand", "category", "min_price", "max_price")):
                return _payload(query, parsed, "empty", [], "عبارت جست‌وجو خالی است.")
            products = _browse(conn, parsed, limit)
            return _payload(
                query,
                parsed,
                "browse",
                products,
                None if products else "محصولی با این فیلتر پیدا نشد.",
            )

        products: list[dict] = []
        seen: set[str] = set()
        mode = "fts"
        and_query = " AND ".join(f'"{token}"*' for token in tokens)
        products = _run_fts(conn, "products_fts", and_query, parsed, limit, seen, products)
        if len(products) < min(3, limit) and len(tokens) > 1:
            or_query = " OR ".join(f'"{token}"*' for token in tokens)
            before = len(products)
            products = _run_fts(conn, "products_fts", or_query, parsed, limit, seen, products)
            if len(products) > before:
                mode = "fts_or"
        if len(products) < min(3, limit):
            long_tokens = [token for token in tokens if len(token) >= 3]
            if long_tokens:
                trigram_query = " OR ".join(f'"{token}"' for token in long_tokens)
                before = len(products)
                products = _run_fts(conn, "products_trgm", trigram_query, parsed, limit, seen, products)
                if len(products) > before:
                    mode = "mixed" if before else "trigram"
        products = _prefer_leading_token(products, tokens)
        return _payload(query, parsed, mode, products, None if products else "محصولی پیدا نشد.")


def get_product(product_id: str) -> dict | None:
    with read_connection() as conn:
        row = conn.execute(
            f"""
            SELECT {_SELECT}
            FROM products p
            LEFT JOIN product_price_stats s ON s.product_id = p.product_id
            WHERE p.product_id = ?
            """,
            (product_id,),
        ).fetchone()
    if row is None:
        return None
    return product_detail(row)


def _prefer_leading_token(products: list[dict], tokens: list[str]) -> list[dict]:
    """Keep BM25 order, but prefer titles that lead with the query.

    TODO: replace this nudge with a hybrid pgvector score.
    """
    if not tokens:
        return products
    head = tokens[0]
    phrase = " ".join(tokens)

    def rank(item: dict) -> tuple[int, int]:
        title = normalize_fa(item.get("persian_title")) or ""
        return (0 if title.startswith(head) else 1, 0 if phrase in title else 1)

    return sorted(products, key=rank)


def _payload(query: str, filters: dict, mode: str, products: list[dict], message: str | None) -> dict:
    return {
        "ok": True,
        "query": query,
        "query_normalized": " ".join(tokenize(query)),
        "filters": public_filters(filters),
        "search_mode": mode,
        "count": len(products),
        "products": products,
        "message_fa": message,
    }


def _run_fts(conn, table: str, match: str, filters: dict, limit: int, seen: set[str], products: list[dict]) -> list[dict]:
    if table not in _FTS_TABLES or len(products) >= limit:
        return products
    where = [f"{table} MATCH ?"]
    params: list = [match]
    extra_where, extra_params = filter_clauses(filters)
    where.extend(extra_where)
    params.extend(extra_params)
    params.append(limit + len(seen))
    sql = f"""
        SELECT {_SELECT}, bm25({table}) AS rank
        FROM {table}
        JOIN products p ON p.product_id = {table}.product_id
        LEFT JOIN product_price_stats s ON s.product_id = p.product_id
        WHERE {" AND ".join(where)}
        ORDER BY rank
        LIMIT ?
    """
    try:
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.OperationalError:
        return products
    for row in rows:
        if row["product_id"] in seen:
            continue
        seen.add(row["product_id"])
        products.append(product_card(row))
        if len(products) >= limit:
            break
    return products


def _browse(conn, filters: dict, limit: int) -> list[dict]:
    where, params = filter_clauses(filters)
    sql = f"""
        SELECT {_SELECT}
        FROM products p
        LEFT JOIN product_price_stats s ON s.product_id = p.product_id
        {"WHERE " + " AND ".join(where) if where else ""}
        ORDER BY COALESCE(s.shop_count, 0) DESC, COALESCE(s.offer_count, 0) DESC
        LIMIT ?
    """
    params.append(limit)
    return [product_card(row) for row in conn.execute(sql, params).fetchall()]
