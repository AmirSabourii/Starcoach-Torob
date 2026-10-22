"""Load the three Torob CSVs into a fresh SQLite file.

Re-running replaces the database atomically. The previous file is left in place
until the new build commits and passes quick_check.
"""

from __future__ import annotations

import csv
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from backend.app.cleaning import (
    EXPECTED_COLUMNS,
    assert_columns,
    clean_bool,
    clean_float,
    clean_price_field,
    clean_text,
    iter_categories,
    iter_contacts,
    iter_payments,
    json_text,
    parse_json_value,
    parse_warranty,
    primary_image,
)
from backend.app.textnorm import normalize_fa

PACKAGE_DIR = Path(__file__).resolve().parent
SCHEMA_SQL = (PACKAGE_DIR / "db" / "schema.sql").read_text(encoding="utf-8")
INDEX_SQL = (PACKAGE_DIR / "db" / "indexes.sql").read_text(encoding="utf-8")
BATCH = 4000

csv.field_size_limit(50 * 1024 * 1024)


def _open_reader(path: Path):
    handle = path.open("r", encoding="utf-8-sig", newline="")
    reader = csv.DictReader(handle)
    assert_columns(reader.fieldnames, EXPECTED_COLUMNS[path.name], path.name)
    return handle, reader


def _executemany(conn: sqlite3.Connection, sql: str, rows: list[tuple]) -> None:
    if rows:
        conn.executemany(sql, rows)


def build_database(csv_dir: Path, db_path: Path, *, source_url: str) -> dict:
    csv_dir = Path(csv_dir)
    db_path = Path(db_path)
    for name in ("shops.csv", "products.csv", "offers.csv"):
        if not (csv_dir / name).exists():
            raise FileNotFoundError(csv_dir / name)

    db_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = db_path.with_suffix(db_path.suffix + ".building")
    temporary.unlink(missing_ok=True)

    conn = sqlite3.connect(temporary)
    try:
        conn.execute("PRAGMA journal_mode = OFF")
        conn.execute("PRAGMA synchronous = OFF")
        conn.execute("PRAGMA temp_store = MEMORY")
        conn.execute("PRAGMA cache_size = -262144")
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(SCHEMA_SQL)
        shops = _load_shops(conn, csv_dir / "shops.csv")
        products = _load_products(conn, csv_dir / "products.csv")
        offers = _load_offers(conn, csv_dir / "offers.csv")
        conn.executescript(INDEX_SQL)
        conn.execute(
            """
            INSERT INTO product_price_stats (product_id, min_price, max_price, offer_count, shop_count)
            SELECT product_id,
                   MIN(price_toman),
                   MAX(price_toman),
                   COUNT(*),
                   COUNT(DISTINCT shop_id)
            FROM offers
            GROUP BY product_id
            """
        )
        summary = {
            "shops": shops["shops"],
            "products": products["products"],
            "offers": offers["offers"],
            "shop_categories": shops["shop_categories"],
            "payment_options": shops["payment_options"],
            "dirty_prices_nulled": offers["dirty_prices_nulled"],
            "null_prices": offers["null_prices"],
            "duplicate_rows_skipped": shops["duplicates"] + products["duplicates"] + offers["duplicates"],
            "source_url": source_url,
            "built_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "schema_version": "1",
            "fts": "sqlite-fts5-unicode61+trigram",
        }
        conn.executemany(
            "INSERT INTO meta (key, value) VALUES (?, ?)",
            [(key, str(value)) for key, value in summary.items()],
        )
        conn.commit()
        check = conn.execute("PRAGMA quick_check").fetchone()[0]
        if check != "ok":
            raise RuntimeError(f"sqlite quick_check failed: {check}")
        conn.execute("PRAGMA journal_mode = DELETE")
        conn.commit()
    except Exception:
        conn.close()
        temporary.unlink(missing_ok=True)
        raise
    else:
        conn.close()

    for sidecar_name in (f"{db_path.name}-wal", f"{db_path.name}-shm"):
        sidecar = db_path.parent / sidecar_name
        sidecar.unlink(missing_ok=True)
    temporary.replace(db_path)
    summary["database_path"] = str(db_path)
    return summary


def _load_shops(conn: sqlite3.Connection, path: Path) -> dict:
    shop_sql = """
        INSERT INTO shops (
            shop_id, name, address, location_label, lat, lon, instagram, website_url,
            supports_fast_delivery, category_names_json, contacts_json,
            payment_options_json, weekly_hours_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    shops: list[tuple] = []
    categories: list[tuple] = []
    contacts: list[tuple] = []
    payments: list[tuple] = []
    seen: set[str] = set()
    duplicates = 0
    handle, reader = _open_reader(path)
    try:
        for row in reader:
            shop_id = clean_text(row.get("shop_id"))
            if not shop_id or shop_id in seen:
                duplicates += 1
                continue
            seen.add(shop_id)
            category_value = parse_json_value(row.get("category_names"))
            contact_value = parse_json_value(row.get("contacts"))
            payment_value = parse_json_value(row.get("payment_options"))
            shops.append(
                (
                    shop_id,
                    clean_text(row.get("name")),
                    clean_text(row.get("address")),
                    clean_text(row.get("location_label")),
                    clean_float(row.get("lat")),
                    clean_float(row.get("lon")),
                    clean_text(row.get("instagram")),
                    clean_text(row.get("website_url")),
                    clean_bool(row.get("supports_fast_delivery")),
                    json_text(row.get("category_names")),
                    json_text(row.get("contacts")),
                    json_text(row.get("payment_options")),
                    json_text(row.get("weekly_hours")),
                )
            )
            categories.extend((shop_id, name) for name in iter_categories(category_value))
            contacts.extend((shop_id, channel, number) for channel, number in iter_contacts(contact_value))
            payments.extend((shop_id, *item) for item in iter_payments(payment_value))
    finally:
        handle.close()

    _executemany(conn, shop_sql, shops)
    _executemany(
        conn,
        "INSERT OR IGNORE INTO shop_categories (shop_id, category_name) VALUES (?, ?)",
        categories,
    )
    _executemany(
        conn,
        "INSERT INTO shop_contacts (shop_id, channel, display_number) VALUES (?, ?, ?)",
        contacts,
    )
    _executemany(
        conn,
        """
        INSERT INTO shop_payment_options (
            shop_id, provider_name, channel, min_price_toman, max_price_toman, category_names_json
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        payments,
    )
    print(f"shops: {len(shops)}", flush=True)
    return {
        "shops": len(shops),
        "shop_categories": len(categories),
        "payment_options": len(payments),
        "duplicates": duplicates,
    }


def _load_products(conn: sqlite3.Connection, path: Path) -> dict:
    product_sql = """
        INSERT INTO products (
            product_id, persian_title, persian_title_norm, brand_name, brand_name_norm,
            model, model_norm, category_name, category_name_norm, image_urls_json,
            primary_image_url, specs_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    fts_sql = """
        INSERT INTO products_fts (
            product_id, persian_title_norm, brand_name_norm, model_norm, category_name_norm
        ) VALUES (?, ?, ?, ?, ?)
    """
    trgm_sql = """
        INSERT INTO products_trgm (
            product_id, persian_title_norm, brand_name_norm, model_norm, category_name_norm
        ) VALUES (?, ?, ?, ?, ?)
    """
    products: list[tuple] = []
    fts_rows: list[tuple] = []
    seen: set[str] = set()
    duplicates = 0
    handle, reader = _open_reader(path)
    try:
        for index, row in enumerate(reader, start=1):
            product_id = clean_text(row.get("product_id"))
            if not product_id or product_id in seen:
                duplicates += 1
                continue
            seen.add(product_id)
            title_norm = normalize_fa(row.get("persian_title")) or ""
            brand_norm = normalize_fa(row.get("brand_name")) or ""
            model_norm = normalize_fa(row.get("model")) or ""
            category_norm = normalize_fa(row.get("category_name")) or ""
            images = parse_json_value(row.get("image_urls"))
            products.append(
                (
                    product_id,
                    clean_text(row.get("persian_title")),
                    title_norm or None,
                    clean_text(row.get("brand_name")),
                    brand_norm or None,
                    clean_text(row.get("model")),
                    model_norm or None,
                    clean_text(row.get("category_name")),
                    category_norm or None,
                    json_text(row.get("image_urls")),
                    primary_image(images),
                    json_text(row.get("specs")),
                )
            )
            fts_rows.append((product_id, title_norm, brand_norm, model_norm, category_norm))
            if len(products) >= BATCH:
                _flush_products(conn, product_sql, fts_sql, trgm_sql, products, fts_rows)
                products = []
                fts_rows = []
            if index % 50000 == 0:
                print(f"products read: {index}", flush=True)
    finally:
        handle.close()
    _flush_products(conn, product_sql, fts_sql, trgm_sql, products, fts_rows)
    print(f"products: {len(seen)}", flush=True)
    return {"products": len(seen), "duplicates": duplicates}


def _flush_products(conn, product_sql, fts_sql, trgm_sql, products, fts_rows) -> None:
    _executemany(conn, product_sql, products)
    _executemany(conn, fts_sql, fts_rows)
    _executemany(conn, trgm_sql, fts_rows)


def _load_offers(conn: sqlite3.Connection, path: Path) -> dict:
    offer_sql = """
        INSERT INTO offers (
            offer_id, product_id, shop_id, seller_title, description, price_toman,
            last_price_changed_at, warranty_json, warranty_provider,
            warranty_period_months, warranty_description
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    batch: list[tuple] = []
    seen: set[str] = set()
    duplicates = 0
    dirty = 0
    null_prices = 0
    handle, reader = _open_reader(path)
    try:
        for index, row in enumerate(reader, start=1):
            offer_id = clean_text(row.get("offer_id"))
            product_id = clean_text(row.get("product_id"))
            shop_id = clean_text(row.get("shop_id"))
            if not offer_id or not product_id or not shop_id or offer_id in seen:
                duplicates += 1
                continue
            seen.add(offer_id)
            price, was_dirty = clean_price_field(row.get("price_toman"))
            if was_dirty:
                dirty += 1
            elif price is None:
                null_prices += 1
            warranty = parse_json_value(row.get("warranty"))
            provider, months, description = parse_warranty(warranty)
            batch.append(
                (
                    offer_id,
                    product_id,
                    shop_id,
                    clean_text(row.get("seller_title")),
                    clean_text(row.get("description")),
                    price,
                    clean_text(row.get("last_price_changed_at")),
                    json_text(row.get("warranty")),
                    provider,
                    months,
                    description,
                )
            )
            if len(batch) >= BATCH:
                _executemany(conn, offer_sql, batch)
                batch = []
            if index % 50000 == 0:
                print(f"offers read: {index}", flush=True)
    finally:
        handle.close()
    _executemany(conn, offer_sql, batch)
    print(f"offers: {len(seen)} dirty_prices_nulled: {dirty}", flush=True)
    return {
        "offers": len(seen),
        "duplicates": duplicates,
        "dirty_prices_nulled": dirty,
        "null_prices": null_prices,
    }
