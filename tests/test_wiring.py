"""Wiring checks for the validated engine. No live model calls."""

from __future__ import annotations

import csv
import json
import os
import sqlite3
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

TMP = Path(os.environ.get("STARCOACH_TEST_TMP") or (Path("/tmp") / "starcoach-wiring"))
TMP.mkdir(parents=True, exist_ok=True)
os.environ["DATABASE_PATH"] = str(TMP / "torob.sqlite")
os.environ["DATA_DIR"] = str(TMP)
os.environ["BOXAPI_API_KEY"] = ""
os.environ["BOXAPI_BASE_URL"] = "https://ai.boxapi.ir/ai/v1"
os.environ["BOXAPI_MODEL"] = "gpt-6-luna"
os.environ.pop("TOROB_RECALL", None)

from fastapi.testclient import TestClient  # noqa: E402

from backend.app.config import get_settings  # noqa: E402
from backend.app.engine.build_eval_db import build, norm  # noqa: E402
from backend.app.main import create_app  # noqa: E402

import tools  # noqa: E402
from gt_lib import con  # noqa: E402


def _shop(sid, name, label, lat, lon, pay):
    hours = {
        "sat": {"shifts": [{"start_time": "10:00:00", "end_time": "19:00:00"}], "status": "declared"},
        "fri": {"shifts": [{"start_time": "00:00:00", "end_time": "00:00:00"}], "status": "closed"},
    }
    return {
        "shop_id": sid,
        "name": name,
        "address": f"تهران {label} خیابان نمونه",
        "category_names": json.dumps(["گوشی موبایل"], ensure_ascii=False),
        "contacts": json.dumps([{"channel": "phone", "display_number": "09120000000"}], ensure_ascii=False),
        "instagram": "demo_shop",
        "lat": lat,
        "lon": lon,
        "location_label": label,
        "payment_options": json.dumps(pay, ensure_ascii=False),
        "supports_fast_delivery": "true",
        "website_url": "https://example.invalid/shop",
        "weekly_hours": json.dumps(hours, ensure_ascii=False),
    }


def _product(pid, title, brand, model, category, specs=None):
    return {
        "product_id": pid,
        "persian_title": title,
        "brand_name": brand,
        "category_name": category,
        "model": model,
        "image_urls": json.dumps(["https://example.invalid/p.jpg"]),
        "specs": json.dumps(specs or [{"key": "رنگ", "section": "کلی", "value": "مشکی"}], ensure_ascii=False),
    }


def _offer(oid, pid, sid, price, when, desc=""):
    return {
        "offer_id": oid,
        "product_id": pid,
        "shop_id": sid,
        "price_toman": price,
        "seller_title": "seller",
        "description": desc,
        "warranty": json.dumps({"provider": "شرکتی", "period_months": 18, "description": ""}, ensure_ascii=False),
        "last_price_changed_at": when,
    }


class WiringTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        csv_dir = TMP / "csv"
        csv_dir.mkdir(parents=True, exist_ok=True)
        shops = [
            _shop("shop_near", "فروشگاه نزدیک", "فردوسی", 35.69305, 51.42020, [
                {"provider_name": "اسنپ‌پی", "channel": "in_person", "min_price_toman": None, "max_price_toman": None, "category_names": []},
            ]),
            _shop("shop_far", "فروشگاه دور", "تجریش", 35.80607, 51.43001, []),
        ]
        products = [
            _product("product_phone", "گوشی سامسونگ گلکسی", "سامسونگ", "گلکسی", "گوشی موبایل", [
                {"key": "حافظه داخلی", "section": "حافظه", "value": "256 گیگابایت"},
                {"key": "اندازه نمایشگر", "section": "صفحه", "value": "6.7 اینچ"},
            ]),
            _product("product_case", "قاب گوشی سامسونگ", "سامسونگ", "قاب", "قاب و کاور گوشی"),
            _product("product_knock", "گوشی طرح سامسونگ", "طرح", "کپی", "گوشی موبایل"),
            _product("product_cable", "كابل شارژ سامسونگ", "سامسونگ", "کابل", "کابل شارژ"),
        ]
        offers = [
            _offer("o_near", "product_phone", "shop_near", "15000000", "2026-10-20T12:00:00+00:00"),
            _offer("o_far", "product_phone", "shop_far", "14000000", "2020-01-01T00:00:00+00:00"),
            _offer("o_low", "product_phone", "shop_near", "10", "2026-10-01T00:00:00+00:00"),
            _offer("o_high", "product_phone", "shop_far", "1000000000000", "2026-10-01T00:00:00+00:00"),
            _offer("o_null", "product_phone", "shop_near", "null", "2026-10-01T00:00:00+00:00"),
            _offer("o_case", "product_case", "shop_near", "250000", "2026-10-18T00:00:00+00:00"),
            _offer("o_knock", "product_knock", "shop_far", "9000000", "2026-10-18T00:00:00+00:00"),
            _offer("o_cable", "product_cable", "shop_near", "180000", "2026-10-19T00:00:00+00:00"),
        ]
        _write(csv_dir / "shops.csv", shops)
        _write(csv_dir / "products.csv", products)
        _write(csv_dir / "offers.csv", offers)
        cls.db = TMP / "torob.sqlite"
        cls.csv_dir = csv_dir
        build(str(csv_dir), str(cls.db))
        build(str(csv_dir), str(cls.db))
        get_settings.cache_clear()
        con.reset()
        cls.client = TestClient(create_app())

    def setUp(self):
        os.environ["DATABASE_PATH"] = str(self.db)
        os.environ["DATA_DIR"] = str(TMP)
        os.environ["BOXAPI_API_KEY"] = ""
        get_settings.cache_clear()
        con.reset()

    def test_norm_and_price_status(self):
        self.assertEqual(norm("كالاي ۱۲"), "کالای 12")
        self.assertEqual(norm("نیم\u200cفاصله"), "نیم فاصله")
        db = sqlite3.connect(self.db)
        counts = dict(db.execute("SELECT price_status, COUNT(*) FROM offers GROUP BY 1"))
        self.assertEqual(counts["ok"], 5)
        self.assertEqual(counts["too_low"], 1)
        self.assertEqual(counts["too_high"], 1)
        self.assertEqual(counts["missing"], 1)
        self.assertIsNone(db.execute("SELECT price_toman FROM offers WHERE offer_id='o_low'").fetchone()[0])
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for name in ("product_specs", "shop_hours", "shop_payment_options", "shop_categories", "products_fts", "product_stats"):
            self.assertIn(name, tables)
        self.assertFalse((TMP / "torob.sqlite.tmp").exists())

    def test_tools_search_stores_browse_contact(self):
        self.assertTrue(tools.USE_RECALL_LAYER)
        found = tools.search_products_lexical("گوشی سامسونگ", limit=5)
        self.assertEqual(found["results"][0]["product_id"], "product_phone")
        cable = tools.search_products_lexical("کابل شارژ", limit=5)
        self.assertTrue(any(r["product_id"] == "product_cable" for r in cable["results"]))
        stores = tools.find_stores_for_product("product_phone", user_lat=35.69305, user_lon=51.42020, sort_by="distance")
        self.assertEqual(stores["shops"][0]["shop_id"], "shop_near")
        self.assertLess(stores["shops"][0]["distance_km"], stores["shops"][1]["distance_km"])
        by_id = {s["shop_id"]: s for s in stores["shops"]}
        self.assertFalse(by_id["shop_near"]["stale_price"])
        self.assertTrue(by_id["shop_far"]["stale_price"])
        self.assertIn("price_updated", by_id["shop_near"])
        contact = tools.contact_store(shop_id="shop_near")
        self.assertIn("FAKE", contact["shops"][0]["phone_warning"])
        browse = tools.browse_catalog(category="گوشی", exclude_basic_phones=True, limit=8)
        ids = {item["product_id"] for item in browse["items"]}
        self.assertIn("product_phone", ids)
        self.assertNotIn("product_knock", ids)
        self.assertNotIn("product_case", ids)
        self.assertTrue(browse["brands"])
        area = tools.search_stores(address_contains="فردوسی", user_lat=35.69305, user_lon=51.42020)
        self.assertGreaterEqual(area["n_matches"], 1)
        inst = tools.search_stores(installment_any=True)
        self.assertGreaterEqual(inst["shops_per_provider"]["اسنپ‌پی"], 1)
        compared = tools.compare_products(["product_phone", "product_case"])
        self.assertEqual(len(compared["products"]), 2)
        self.assertIn("storage", compared["products"][0]["specs"])

    def test_http_and_static_without_model(self):
        health = self.client.get("/health")
        self.assertEqual(health.status_code, 200)
        body = health.json()
        self.assertTrue(body["db_ready"])
        self.assertFalse(body["llm_configured"])
        self.assertEqual(body["model"], "gpt-6-luna")
        self.assertEqual(body["stale_price_days"], 90)
        self.assertEqual(body["products"], 4)
        search = self.client.get("/api/products/search", params={"q": "کابل"})
        self.assertEqual(search.status_code, 200)
        payload = search.json()
        self.assertEqual(payload["retrieval"], "lexical")
        self.assertTrue(any(r["product_id"] == "product_cable" for r in payload["results"]))
        self.assertIn("latest_price_change", payload["results"][0])
        stores = self.client.get("/api/products/product_phone/stores", params={"lat": 35.69305, "lon": 51.4202, "sort_by": "distance"})
        self.assertEqual(stores.status_code, 200)
        self.assertEqual(stores.json()["shops"][0]["shop_id"], "shop_near")
        browse = self.client.get("/api/browse", params={"category": "گوشی"})
        self.assertEqual(browse.status_code, 200)
        chat = self.client.post("/chat", json={"message": "قیمت گوشی سامسونگ", "lat": 35.69, "lon": 51.42})
        self.assertEqual(chat.status_code, 503)
        self.assertNotIn("product_phone", chat.text)
        missing = os.environ["DATABASE_PATH"]
        os.environ["DATABASE_PATH"] = str(TMP / "absent.sqlite")
        get_settings.cache_clear()
        bare = self.client.get("/health")
        os.environ["DATABASE_PATH"] = missing
        get_settings.cache_clear()
        self.assertEqual(bare.status_code, 200)
        self.assertFalse(bare.json()["db_ready"])
        for path in ("/", "/app.js", "/app.css", "/screens/01-home.html", "/assets/logo.png", "/fonts/Vazirmatn-var.woff2"):
            res = self.client.get(path)
            self.assertEqual(res.status_code, 200, path)
        js = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
        self.assertIn('fetch("/chat"', js)
        self.assertNotIn("tel:", js)
        html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("tel:", html)

    def test_model_config_and_boot_and_gitignore(self):
        agent_src = (ROOT / "backend" / "app" / "engine" / "agent.py").read_text(encoding="utf-8")
        recall_src = (ROOT / "backend" / "app" / "engine" / "recall.py").read_text(encoding="utf-8")
        self.assertIn("max_completion_tokens=MAX_COMPLETION_TOKENS", agent_src)
        self.assertIn("reasoning_effort='none'", agent_src)
        self.assertNotIn("max_tokens=", agent_src)
        self.assertIn("max_completion_tokens=max_tokens", recall_src)
        self.assertIn("reasoning_effort='none'", recall_src)
        self.assertIn("text-embedding-3-small", recall_src)
        ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        for token in ("*.npy", "llm_cache.json", "emb_cache/", "*.sqlite", "data/"):
            self.assertIn(token, ignore)
        env = os.environ.copy()
        env["DATABASE_PATH"] = str(TMP / "missing-boot.sqlite")
        env["BOXAPI_API_KEY"] = ""
        proc = subprocess.run(
            [sys.executable, "-c", "import backend.app.main; print(backend.app.main.app.title)"],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("Starcoach Torob", proc.stdout)


def _write(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    unittest.main()
