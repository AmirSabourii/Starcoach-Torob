"""Fixture checks for the loader and the two required tool paths."""

from __future__ import annotations

import csv
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from backend.app.cleaning import EXPECTED_COLUMNS, assert_columns, clean_price_field  # noqa: E402
from backend.app.config import get_settings  # noqa: E402
from backend.app.geo import haversine_km  # noqa: E402
from backend.app.ingest import build_database  # noqa: E402
from backend.app.main import create_app  # noqa: E402
from backend.app.tools.check_freshness import check_store_freshness  # noqa: E402
from backend.app.tools.compare_products import compare_products  # noqa: E402
from backend.app.tools.contact_store import contact_store  # noqa: E402
from backend.app.tools.search_products import search_products  # noqa: E402
from backend.app.tools.stores import find_stores_for_product  # noqa: E402

ENV_KEYS = (
    "DATABASE_PATH",
    "BOXAPI_API_KEY",
    "BOXAPI_BASE_URL",
    "BOXAPI_MODEL",
    "STALE_PRICE_DAYS",
    "CORS_ORIGINS",
)


class SkeletonTest(unittest.TestCase):
    def setUp(self) -> None:
        self._saved = {key: os.environ.get(key) for key in ENV_KEYS}
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        csv_dir = root / "csv"
        csv_dir.mkdir()
        self.db = root / "starcoach.db"
        fresh = (datetime.now(timezone.utc) - timedelta(days=2)).replace(microsecond=0).isoformat()
        stale = "2020-12-01T00:00:00+00:00"
        hours = {
            "sat": {"shifts": [{"start_time": "10:00:00", "end_time": "19:00:00"}], "status": "declared"},
            "fri": {"shifts": [{"start_time": "00:00:00", "end_time": "00:00:00"}], "status": "closed"},
        }
        _write(
            csv_dir / "shops.csv",
            EXPECTED_COLUMNS["shops.csv"],
            [
                _shop("shop_near", "فروشگاه نزدیک", "فردوسی", 35.69305, 51.42020, "true", hours),
                _shop("shop_far", "فروشگاه دور", "تجریش", 35.90, 51.60, "null", hours),
            ],
        )
        _write(
            csv_dir / "products.csv",
            EXPECTED_COLUMNS["products.csv"],
            [
                _product(
                    "product_phone",
                    "گوشی سامسونگ گلکسی",
                    "سامسونگ",
                    "گلکسی",
                    "گوشی موبایل",
                    [{"key": "رنگ", "section": "کلی", "value": "مشکی"}],
                ),
                _product(
                    "product_phone2",
                    "گوشی سامسونگ ساده",
                    "سامسونگ",
                    "ساده",
                    "گوشی موبایل",
                    [{"key": "رنگ", "section": "کلی", "value": "سفید"}],
                ),
                _product(
                    "product_cable",
                    "کابل شارژ اچ\u200cپی",
                    "اچ\u200cپی",
                    None,
                    "کابل",
                    [{"key": "طول", "section": "کلی", "value": "۱ متر"}],
                ),
                _product("product_edge", "کالای مرزی قیمت", None, None, "متفرقه", []),
            ],
        )
        _write(
            csv_dir / "offers.csv",
            EXPECTED_COLUMNS["offers.csv"],
            [
                _offer("offer_dirty", "product_phone", "shop_near", "500", fresh, "نسخهٔ ارزان"),
                _offer("offer_fresh", "product_phone", "shop_near", "15000000", fresh, "نسخهٔ اصلی", months=12),
                _offer("offer_stale", "product_phone", "shop_far", "14000000", stale, "نسخهٔ دور"),
                _offer("offer_phone2", "product_phone2", "shop_near", "2500000", fresh, "ساده"),
                _offer("offer_cable_dirty", "product_cable", "shop_near", "100000000000000", fresh, "پرت"),
                _offer("offer_cable_ok", "product_cable", "shop_near", "90000", fresh, "کابل سالم"),
                _offer("offer_edge", "product_edge", "shop_near", "100000000000", fresh, "مرز"),
            ],
        )
        os.environ["DATABASE_PATH"] = str(self.db)
        os.environ["BOXAPI_API_KEY"] = ""
        os.environ["BOXAPI_BASE_URL"] = ""
        os.environ["BOXAPI_MODEL"] = ""
        os.environ["STALE_PRICE_DAYS"] = "30"
        get_settings.cache_clear()
        self.summary = build_database(csv_dir, self.db, source_url="fixture://test")
        get_settings.cache_clear()
        self.app = create_app()

    def tearDown(self) -> None:
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        get_settings.cache_clear()
        self.tmp.cleanup()

    def test_price_thresholds(self) -> None:
        self.assertEqual(clean_price_field("500"), (None, True))
        self.assertEqual(clean_price_field("1000"), (1000, False))
        self.assertEqual(clean_price_field("100000000000"), (100000000000, False))
        self.assertEqual(clean_price_field("100000000001"), (None, True))
        self.assertEqual(clean_price_field("null"), (None, False))
        self.assertEqual(clean_price_field(None), (None, False))

    def test_loader_nulls_dirty_prices_and_is_idempotent(self) -> None:
        self.assertEqual(self.summary["dirty_prices_nulled"], 2)
        self.assertEqual(self.summary["products"], 4)
        connection = sqlite3.connect(self.db)
        dirty = connection.execute("SELECT price_toman FROM offers WHERE offer_id = 'offer_dirty'").fetchone()[0]
        edge = connection.execute("SELECT price_toman FROM offers WHERE offer_id = 'offer_edge'").fetchone()[0]
        kept = connection.execute("SELECT price_toman FROM offers WHERE offer_id = 'offer_fresh'").fetchone()[0]
        connection.close()
        self.assertIsNone(dirty)
        self.assertEqual(edge, 100000000000)
        self.assertEqual(kept, 15000000)
        again = build_database(Path(self.tmp.name) / "csv", self.db, source_url="fixture://test")
        self.assertEqual(again["products"], 4)
        self.assertFalse(self.db.with_suffix(self.db.suffix + ".building").exists())
        found = search_products("سامسونگ")
        self.assertEqual(found["count"], 2)

    def test_search_normalizes_persian_and_filters_price(self) -> None:
        arabic = search_products("\u0643\u0627\u0628\u0644")
        self.assertEqual([item["product_id"] for item in arabic["products"]], ["product_cable"])
        zwnj = search_products("اچ\u200cپی")
        self.assertEqual(zwnj["products"][0]["product_id"], "product_cable")
        sentence = search_products("یک گوشی سامسونگ می\u200cخوام")
        self.assertEqual(sentence["count"], 2)
        cheap = search_products("سامسونگ", {"max_price": 3_000_000})
        self.assertEqual([item["product_id"] for item in cheap["products"]], ["product_phone2"])
        expensive = search_products("سامسونگ", {"min_price": 10_000_000})
        self.assertEqual([item["product_id"] for item in expensive["products"]], ["product_phone"])

    def test_find_stores_sorts_by_distance_and_marks_stale_prices(self) -> None:
        found = find_stores_for_product("product_phone", user_lat=35.69305, user_lon=51.42020)
        self.assertTrue(found["ok"])
        self.assertEqual(found["stores"][0]["shop_id"], "shop_near")
        self.assertLess(found["stores"][0]["distance_km"], 1)
        self.assertGreater(found["stores"][1]["distance_km"], 10)
        self.assertEqual(found["stores"][0]["best_price_toman"], 15000000)
        self.assertFalse(found["stores"][0]["cheapest_is_stale"])
        self.assertTrue(found["stores"][1]["cheapest_is_stale"])
        self.assertEqual(found["stores"][0]["payment_options"][0]["provider_name"], "ترب‌پی")
        near = find_stores_for_product(
            "product_phone",
            user_lat=35.69305,
            user_lon=51.42020,
            max_distance_km=5,
        )
        self.assertEqual([store["shop_id"] for store in near["stores"]], ["shop_near"])
        fresh = check_store_freshness("offer_fresh")
        stale = check_store_freshness("offer_stale")
        self.assertFalse(fresh["is_stale"])
        self.assertTrue(stale["is_stale"])

    def test_contact_is_simulated_and_compare_reads_specs(self) -> None:
        contact = contact_store("shop_near")
        self.assertTrue(contact["simulated"])
        self.assertTrue(contact["human_in_the_loop"])
        self.assertIn("FAKE", contact["disclaimer_fa"])
        self.assertIn("ساختگی", contact["disclaimer_fa"])
        self.assertEqual(contact["contacts"][0]["display_number"], "۰۹۱۲۰۰۰۰۰۰۰")
        compared = compare_products(["product_phone", "product_phone2"])
        self.assertTrue(compared["ok"])
        color = next(row for row in compared["rows"] if row["key"] == "رنگ")
        self.assertEqual(color["values"]["product_phone"], "مشکی")
        self.assertEqual(color["values"]["product_phone2"], "سفید")

    def test_http_search_stores_and_grounded_chat(self) -> None:
        with TestClient(self.app) as client:
            health = client.get("/health")
            self.assertEqual(health.status_code, 200)
            self.assertTrue(health.json()["db_ready"])
            self.assertFalse(health.json()["llm_configured"])
            search = client.get("/api/products/search", params={"q": "سامسونگ"})
            self.assertEqual(search.status_code, 200)
            self.assertEqual(search.json()["count"], 2)
            stores = client.get(
                "/api/products/product_phone/stores",
                params={"lat": 35.69305, "lon": 51.42020, "max_distance_km": 5},
            )
            self.assertEqual(stores.status_code, 200)
            self.assertEqual(stores.json()["stores"][0]["name"], "فروشگاه نزدیک")
            chat = client.post("/chat", json={"message": "سامسونگ", "lat": 35.69305, "lon": 51.42020})
            self.assertEqual(chat.status_code, 200)
            body = chat.json()
            self.assertEqual(body["mode"], "fallback")
            self.assertTrue(body["grounded"])
            titles = {item["persian_title"] for item in body["products"]}
            self.assertIn("گوشی سامسونگ گلکسی", titles)
            self.assertTrue(any(title and title in body["reply"] for title in titles))
            self.assertNotIn("آیفون خیالی", body["reply"])
            page = client.get("/")
            self.assertEqual(page.status_code, 200)
            self.assertIn("استارکوچ", page.text)
            self.assertIn('dir="rtl"', page.text)

    def test_missing_database_stays_explicit(self) -> None:
        os.environ["DATABASE_PATH"] = str(Path(self.tmp.name) / "missing.db")
        get_settings.cache_clear()
        with TestClient(self.app) as client:
            health = client.get("/health")
            self.assertEqual(health.status_code, 200)
            self.assertFalse(health.json()["db_ready"])
            search = client.get("/api/products/search", params={"q": "سامسونگ"})
            self.assertEqual(search.status_code, 503)
            self.assertIn("پایگاه داده", search.json()["detail"])

    def test_profile_columns_and_gitignore(self) -> None:
        with self.assertRaises(ValueError):
            assert_columns(["shop_id", "english_title"], EXPECTED_COLUMNS["shops.csv"], "shops.csv")
        schema = (ROOT / "backend/app/db/schema.sql").read_text(encoding="utf-8")
        self.assertNotIn("english_title", schema)
        self.assertNotIn("stock", schema)
        gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        for line in ("data/", "*.csv", "*.zip", "*.db", ".env"):
            self.assertIn(line, gitignore)
        self.assertGreater(haversine_km(0, 0, 0, 1), 110)
        self.assertLess(haversine_km(0, 0, 0, 1), 112)
        self.assertEqual(haversine_km(35.7, 51.4, 35.7, 51.4), 0)


def _write(path: Path, columns: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def _shop(shop_id, name, label, lat, lon, fast, hours) -> dict:
    return {
        "address": "خیابان نمونه",
        "category_names": json.dumps(["گوشی موبایل"], ensure_ascii=False),
        "contacts": json.dumps([{"channel": "phone", "display_number": "۰۹۱۲۰۰۰۰۰۰۰"}], ensure_ascii=False),
        "instagram": "null",
        "lat": lat,
        "location_label": label,
        "lon": lon,
        "name": name,
        "payment_options": json.dumps(
            [
                {
                    "provider_name": "ترب‌پی",
                    "channel": "in_person",
                    "min_price_toman": None,
                    "max_price_toman": None,
                    "category_names": [],
                }
            ],
            ensure_ascii=False,
        ),
        "shop_id": shop_id,
        "supports_fast_delivery": fast,
        "website_url": "null",
        "weekly_hours": json.dumps(hours, ensure_ascii=False),
    }


def _product(product_id, title, brand, model, category, specs) -> dict:
    return {
        "brand_name": brand if brand is not None else "null",
        "category_name": category,
        "image_urls": json.dumps(["https://image.torob.com/example.jpg"], ensure_ascii=False),
        "model": model if model is not None else "null",
        "persian_title": title,
        "product_id": product_id,
        "specs": json.dumps(specs, ensure_ascii=False),
    }


def _offer(offer_id, product_id, shop_id, price, changed_at, seller, months=None) -> dict:
    warranty = {"provider": "شرکتی", "period_months": months, "description": None}
    return {
        "description": "",
        "last_price_changed_at": changed_at,
        "offer_id": offer_id,
        "price_toman": price,
        "product_id": product_id,
        "seller_title": seller,
        "shop_id": shop_id,
        "warranty": json.dumps(warranty, ensure_ascii=False),
    }


if __name__ == "__main__":
    unittest.main()
