-- Starcoach Torob MVP (SQLite).
-- Source fields are only the columns documented for shops.csv, products.csv,
-- and offers.csv. *_norm, primary_image_url, parsed warranty columns, and the
-- side tables are derived from those fields.
--
-- Later Postgres shape (not created by this file):
--   pg_trgm GIN indexes on products.persian_title_norm, brand_name_norm, model_norm
--   a pgvector column over persian_title + brand + category + key specs
--   shops.geog geography(Point, 4326) with a GiST index
--   btree indexes matching indexes.sql

PRAGMA foreign_keys = ON;

CREATE TABLE shops (
    shop_id TEXT PRIMARY KEY,
    name TEXT,
    address TEXT,
    location_label TEXT,
    lat REAL,
    lon REAL,
    instagram TEXT,
    website_url TEXT,
    supports_fast_delivery INTEGER,
    category_names_json TEXT,
    contacts_json TEXT,
    payment_options_json TEXT,
    weekly_hours_json TEXT
);

CREATE TABLE shop_categories (
    shop_id TEXT NOT NULL REFERENCES shops(shop_id),
    category_name TEXT NOT NULL,
    PRIMARY KEY (shop_id, category_name)
);

CREATE TABLE shop_contacts (
    shop_id TEXT NOT NULL REFERENCES shops(shop_id),
    channel TEXT,
    display_number TEXT
);

CREATE TABLE shop_payment_options (
    shop_id TEXT NOT NULL REFERENCES shops(shop_id),
    provider_name TEXT,
    channel TEXT,
    min_price_toman INTEGER,
    max_price_toman INTEGER,
    category_names_json TEXT
);

CREATE TABLE products (
    product_id TEXT PRIMARY KEY,
    persian_title TEXT,
    persian_title_norm TEXT,
    brand_name TEXT,
    brand_name_norm TEXT,
    model TEXT,
    model_norm TEXT,
    category_name TEXT,
    category_name_norm TEXT,
    image_urls_json TEXT,
    primary_image_url TEXT,
    specs_json TEXT
);

CREATE TABLE offers (
    offer_id TEXT PRIMARY KEY,
    product_id TEXT NOT NULL REFERENCES products(product_id),
    shop_id TEXT NOT NULL REFERENCES shops(shop_id),
    seller_title TEXT,
    description TEXT,
    price_toman INTEGER,
    last_price_changed_at TEXT,
    warranty_json TEXT,
    warranty_provider TEXT,
    warranty_period_months INTEGER,
    warranty_description TEXT
);

CREATE TABLE product_price_stats (
    product_id TEXT PRIMARY KEY REFERENCES products(product_id),
    min_price INTEGER,
    max_price INTEGER,
    offer_count INTEGER NOT NULL,
    shop_count INTEGER NOT NULL
);

CREATE TABLE meta (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE VIRTUAL TABLE products_fts USING fts5(
    product_id UNINDEXED,
    persian_title_norm,
    brand_name_norm,
    model_norm,
    category_name_norm,
    tokenize = "unicode61 remove_diacritics 0"
);

CREATE VIRTUAL TABLE products_trgm USING fts5(
    product_id UNINDEXED,
    persian_title_norm,
    brand_name_norm,
    model_norm,
    category_name_norm,
    tokenize = "trigram case_sensitive 0"
);
