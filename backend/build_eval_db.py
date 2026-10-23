#!/usr/bin/env python3
"""Build a clean SQLite eval DB from the Torob CSVs. Idempotent: rebuilds into a temp file and atomically replaces.

Usage: python3 build_eval_db.py [--data DIR] [--out PATH]
"""
import argparse, csv, json, os, sqlite3, sys, time

csv.field_size_limit(sys.maxsize)
HERE = os.path.dirname(os.path.abspath(__file__))
PRICE_MIN, PRICE_MAX = 1000, 1e11

_TR = str.maketrans({'ي': 'ی', 'ى': 'ی', 'ك': 'ک', 'ة': 'ه', 'ۀ': 'ه', 'أ': 'ا', 'إ': 'ا', 'ٱ': 'ا',
                     '\u200c': ' ', '\u200f': ' ', '\u200e': ' ', '\u0640': '',
                     **{c: str(i) for i, c in enumerate('۰۱۲۳۴۵۶۷۸۹')},
                     **{c: str(i) for i, c in enumerate('٠١٢٣٤٥٦٧٨٩')}})


def norm(s):
    """Persian/Arabic char + digit normalization, ZWNJ->space, lowercase latin."""
    if s is None:
        return None
    return ' '.join(s.translate(_TR).lower().split())


def nv(v):
    return None if v in ('', 'null', None) else v


def jload(v):
    v = nv(v)
    if v is None:
        return None
    try:
        return json.loads(v)
    except Exception:
        return None


def rows(path):
    with open(path, newline='', encoding='utf-8') as f:
        yield from csv.DictReader(f)


SCHEMA = """
PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF;
CREATE TABLE shops(
  shop_id TEXT PRIMARY KEY, name TEXT, name_norm TEXT, address TEXT, address_norm TEXT,
  category_names TEXT, contacts TEXT, phone TEXT, phone_latin TEXT, instagram TEXT,
  lat REAL, lon REAL, location_label TEXT, payment_options TEXT, n_payment_options INTEGER,
  supports_fast_delivery INTEGER, website_url TEXT, weekly_hours TEXT);
CREATE TABLE shop_categories(shop_id TEXT, category_name TEXT);
CREATE TABLE shop_payment_options(shop_id TEXT, provider_name TEXT, channel TEXT,
  min_price_toman REAL, max_price_toman REAL, category_names TEXT);
CREATE TABLE shop_hours(shop_id TEXT, day TEXT, status TEXT, start_time TEXT, end_time TEXT);
CREATE TABLE products(
  product_id TEXT PRIMARY KEY, persian_title TEXT, title_norm TEXT, brand_name TEXT, category_name TEXT,
  model TEXT, image_urls TEXT, n_images INTEGER, specs TEXT, n_specs INTEGER);
CREATE TABLE product_specs(product_id TEXT, section TEXT, key TEXT, value TEXT);
CREATE TABLE offers(
  offer_id TEXT PRIMARY KEY, product_id TEXT, shop_id TEXT,
  price_toman REAL,            -- cleaned (NULL if missing or dirty)
  price_toman_raw REAL,        -- as in CSV
  price_status TEXT,           -- ok | missing | too_low | too_high
  seller_title TEXT, description TEXT, warranty TEXT,
  warranty_provider TEXT, warranty_months INTEGER, last_price_changed_at TEXT);
"""

INDEXES = """
CREATE INDEX ix_offers_product ON offers(product_id);
CREATE INDEX ix_offers_shop ON offers(shop_id);
CREATE INDEX ix_offers_price ON offers(price_toman);
CREATE INDEX ix_offers_prod_price ON offers(product_id, price_toman);
CREATE INDEX ix_products_brand ON products(brand_name);
CREATE INDEX ix_products_category ON products(category_name);
CREATE INDEX ix_shops_label ON shops(location_label);
CREATE INDEX ix_shops_latlon ON shops(lat, lon);
CREATE INDEX ix_shopcat_shop ON shop_categories(shop_id);
CREATE INDEX ix_shopcat_cat ON shop_categories(category_name);
CREATE INDEX ix_shoppay_shop ON shop_payment_options(shop_id);
CREATE INDEX ix_shophours_shop ON shop_hours(shop_id);
CREATE INDEX ix_specs_product ON product_specs(product_id);
CREATE TABLE product_stats AS
  SELECT o.product_id, COUNT(*) n_offers, COUNT(DISTINCT o.shop_id) n_shops,
         COUNT(o.price_toman) n_priced, MIN(o.price_toman) min_price, MAX(o.price_toman) max_price,
         MAX(o.last_price_changed_at) latest_price_change
  FROM offers o GROUP BY o.product_id;
CREATE UNIQUE INDEX ix_pstats ON product_stats(product_id);
CREATE INDEX ix_pstats_nshops ON product_stats(n_shops);
-- FTS over normalized text (title/brand/model/category). Query with normalized tokens too.
CREATE VIRTUAL TABLE products_fts USING fts5(
  product_id UNINDEXED, persian_title, brand_name, model, category_name,
  tokenize = 'unicode61 remove_diacritics 2');
INSERT INTO products_fts(product_id, persian_title, brand_name, model, category_name)
  SELECT product_id, title_norm, brand_norm, model_norm, cat_norm FROM _fts_src;
DROP TABLE _fts_src;
"""


def build(data, out):
    tmp = out + '.tmp'
    if os.path.exists(tmp):
        os.remove(tmp)
    con = sqlite3.connect(tmp)
    con.executescript(SCHEMA)
    con.execute('CREATE TABLE _fts_src(product_id, title_norm, brand_norm, model_norm, cat_norm)')
    t0 = time.time()

    # shops
    sh, sc, sp, shh = [], [], [], []
    for r in rows(os.path.join(data, 'shops.csv')):
        sid = r['shop_id']
        cats = jload(r['category_names']) or []
        for c in cats:
            sc.append((sid, c))
        contacts = jload(r['contacts']) or []
        phone = next((c.get('display_number') for c in contacts if c.get('channel') == 'phone'), None)
        pay = jload(r['payment_options']) or []
        for p in pay:
            sp.append((sid, p.get('provider_name'), p.get('channel'), p.get('min_price_toman'),
                       p.get('max_price_toman'), json.dumps(p.get('category_names') or [], ensure_ascii=False)))
        for day, d in (jload(r['weekly_hours']) or {}).items():
            for s in (d.get('shifts') or [{}]):
                shh.append((sid, day, d.get('status'), s.get('start_time'), s.get('end_time')))
        sfd = nv(r['supports_fast_delivery'])
        sh.append((sid, nv(r['name']), norm(nv(r['name'])), nv(r['address']), norm(nv(r['address'])),
                   nv(r['category_names']), nv(r['contacts']), phone, norm(phone),
                   nv(r['instagram']), float(r['lat']) if nv(r['lat']) else None,
                   float(r['lon']) if nv(r['lon']) else None, nv(r['location_label']),
                   nv(r['payment_options']), len(pay),
                   None if sfd is None else int(sfd.lower() == 'true'), nv(r['website_url']), nv(r['weekly_hours'])))
    con.executemany('INSERT INTO shops VALUES (%s)' % ','.join('?' * 18), sh)
    con.executemany('INSERT INTO shop_categories VALUES (?,?)', sc)
    con.executemany('INSERT INTO shop_payment_options VALUES (?,?,?,?,?,?)', sp)
    con.executemany('INSERT INTO shop_hours VALUES (?,?,?,?,?)', shh)

    # products
    batch, specs, fts = [], [], []
    def flush():
        con.executemany('INSERT INTO products VALUES (?,?,?,?,?,?,?,?,?,?)', batch)
        con.executemany('INSERT INTO product_specs VALUES (?,?,?,?)', specs)
        con.executemany('INSERT INTO _fts_src VALUES (?,?,?,?,?)', fts)
        batch.clear(); specs.clear(); fts.clear()
    for r in rows(os.path.join(data, 'products.csv')):
        pid = r['product_id']
        imgs = jload(r['image_urls']) or []
        sp_ = jload(r['specs']) or []
        for s in sp_:
            specs.append((pid, s.get('section'), s.get('key'), s.get('value')))
        t, b, m, c = nv(r['persian_title']), nv(r['brand_name']), nv(r['model']), nv(r['category_name'])
        batch.append((pid, t, norm(t), b, c, m, nv(r['image_urls']), len(imgs), nv(r['specs']), len(sp_)))
        fts.append((pid, norm(t) or '', norm(b) or '', norm(m) or '', norm(c) or ''))
        if len(batch) >= 20000:
            flush()
    flush()

    # offers
    stats = {'ok': 0, 'missing': 0, 'too_low': 0, 'too_high': 0}
    batch = []
    for r in rows(os.path.join(data, 'offers.csv')):
        raw = nv(r['price_toman'])
        raw = float(raw) if raw is not None else None
        if raw is None:
            st, clean = 'missing', None
        elif raw < PRICE_MIN:
            st, clean = 'too_low', None
        elif raw > PRICE_MAX:
            st, clean = 'too_high', None
        else:
            st, clean = 'ok', raw
        stats[st] += 1
        w = jload(r['warranty']) or {}
        batch.append((r['offer_id'], r['product_id'], r['shop_id'], clean, raw, st, nv(r['seller_title']),
                      nv(r['description']), nv(r['warranty']), w.get('provider'), w.get('period_months'),
                      nv(r['last_price_changed_at'])))
        if len(batch) >= 50000:
            con.executemany('INSERT INTO offers VALUES (?,?,?,?,?,?,?,?,?,?,?,?)', batch); batch.clear()
    con.executemany('INSERT INTO offers VALUES (?,?,?,?,?,?,?,?,?,?,?,?)', batch)
    con.commit()
    con.executescript(INDEXES)
    con.execute('CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT)')
    meta = {'built_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'), 'price_rule': 'NULL if <1000 or >1e11',
            'data_dir': data, **{f'price_{k}': v for k, v in stats.items()},
            'dataset_max_price_change': con.execute('SELECT MAX(last_price_changed_at) FROM offers').fetchone()[0]}
    con.executemany('INSERT INTO meta VALUES (?,?)', [(k, str(v)) for k, v in meta.items()])
    con.commit()
    con.execute('ANALYZE'); con.commit()
    con.close()
    os.replace(tmp, out)

    con = sqlite3.connect(out)
    print(f'Built {out} in {time.time()-t0:.0f}s')
    for t in ['shops', 'shop_categories', 'shop_payment_options', 'shop_hours', 'products', 'product_specs',
              'offers', 'product_stats', 'products_fts']:
        print(f'  {t:22s} {con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]:>10,}')
    print('  price status:', stats)
    print(f"  dirty prices nulled: {stats['too_low'] + stats['too_high']:,} "
          f"(too_low={stats['too_low']:,}, too_high={stats['too_high']:,}); originally missing: {stats['missing']:,}; "
          f"total NULL price_toman: {con.execute('SELECT COUNT(*) FROM offers WHERE price_toman IS NULL').fetchone()[0]:,}")
    print('  orphan offers (product):', con.execute('SELECT COUNT(*) FROM offers o LEFT JOIN products p USING(product_id) WHERE p.product_id IS NULL').fetchone()[0],
          ' (shop):', con.execute('SELECT COUNT(*) FROM offers o LEFT JOIN shops s USING(shop_id) WHERE s.shop_id IS NULL').fetchone()[0])


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--data', default=os.path.join(os.path.dirname(HERE), 'data'))
    ap.add_argument('--out', default=os.path.join(HERE, 'torob.sqlite'))
    a = ap.parse_args()
    build(a.data, a.out)
