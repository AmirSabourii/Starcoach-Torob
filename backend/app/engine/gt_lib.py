"""Ground-truth helpers over torob.sqlite (pure SQL + python, no LLM)."""
import json, math, re, sqlite3, statistics, os
from datetime import datetime, timezone

def _repo_root():
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def db_path():
    """SQLite file. DATABASE_PATH overrides; default is <repo>/data/torob.sqlite (never committed)."""
    return os.environ.get('DATABASE_PATH') or os.path.join(_repo_root(), 'data', 'torob.sqlite')


# Kept for callers that read the constant. Evaluated at import; connect() re-reads the env.
DB = db_path()
REF_DATE = datetime(2026, 10, 22, tzinfo=timezone.utc)   # eval "today"
BNPL = ['اسنپ\u200cپی', 'ترب\u200cپی', 'دیجی پی', 'تارا', 'ازکی\u200cوام']


def haversine(lat1, lon1, lat2, lon2):
    if None in (lat1, lon1, lat2, lon2):
        return None
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


class DatabaseNotReady(FileNotFoundError):
    """Raised when a tool asks for the SQLite file before scripts/build_db.py has created it."""


def connect(path=None):
    path = path or db_path()
    if not os.path.exists(path):
        raise DatabaseNotReady(path)
    con = sqlite3.connect(path, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.create_function('dist_km', 4, haversine, deterministic=True)
    con.create_function('regexp', 2, lambda p, s: s is not None and re.search(p, s) is not None, deterministic=True)
    return con


class _LazyConn:
    """Same connection object the tools use, opened on first query so import/boot works before the DB exists."""

    def __init__(self):
        self._c = None
        self._path = None

    def open(self):
        path = db_path()
        if self._c is None or self._path != path:
            if self._c is not None:
                try:
                    self._c.close()
                except Exception:
                    pass
            self._c = connect(path)
            self._path = path
        return self._c

    def reset(self):
        if self._c is not None:
            try:
                self._c.close()
            except Exception:
                pass
        self._c = None
        self._path = None

    def __getattr__(self, name):
        return getattr(self.open(), name)


con = _LazyConn()


def days_old(iso):
    if not iso:
        return None
    return round((REF_DATE - datetime.fromisoformat(iso)).total_seconds() / 86400, 1)


def product(pid):
    r = con.execute('SELECT product_id, persian_title, brand_name, category_name FROM products WHERE product_id=?', (pid,)).fetchone()
    return dict(r)


def shop_offers(pid, valid_only=True):
    """One row per shop: the shop's cheapest valid offer for this product."""
    sql = '''SELECT o.shop_id, s.name shop_name, s.address, s.location_label, s.lat, s.lon, s.phone,
                    MIN(o.price_toman) price_toman, o.offer_id, o.last_price_changed_at, o.warranty_provider,
                    o.warranty_months, COUNT(*) n_offers_in_shop
             FROM offers o JOIN shops s USING(shop_id)
             WHERE o.product_id=? %s GROUP BY o.shop_id ORDER BY price_toman, o.shop_id''' % (
        'AND o.price_toman IS NOT NULL' if valid_only else '')
    return [dict(r) for r in con.execute(sql, (pid,))]


def price_summary(pid):
    so = shop_offers(pid)
    prices = [r['price_toman'] for r in so]
    allo = con.execute('SELECT COUNT(*), COUNT(DISTINCT shop_id), SUM(price_toman IS NULL), MAX(last_price_changed_at) FROM offers WHERE product_id=?', (pid,)).fetchone()
    out = dict(product(pid))
    out.update(n_offers=allo[0], n_shops=allo[1], n_offers_null_price=allo[2], n_shops_with_valid_price=len(so),
               latest_price_change=allo[3])
    if prices:
        med = statistics.median(prices)
        out.update(min_price=prices[0], median_price=med, max_price=prices[-1])
        out['suspicious_low_offers'] = [compact(r) for r in so if r['price_toman'] < 0.4 * med]
        out['suspicious_high_offers'] = [compact(r) for r in so if r['price_toman'] > 2.5 * med]
    return out


def compact(r, keys=('shop_id', 'shop_name', 'price_toman', 'last_price_changed_at')):
    d = {k: r[k] for k in keys if k in r}
    if 'distance_km' in r:
        d['distance_km'] = r['distance_km']
    return d


def cheapest(pid, k=3, plausible=True):
    so = shop_offers(pid)
    res = {'product': product(pid), 'cheapest': compact(so[0]) if so else None,
           'top_cheapest': [compact(r) for r in so[:k]], 'n_shops_with_valid_price': len(so)}
    if so:
        med = statistics.median([r['price_toman'] for r in so])
        pl = [r for r in so if r['price_toman'] >= 0.4 * med]
        res['median_shop_price'] = med
        res['max_price'] = so[-1]['price_toman']
        res['cheapest'].update(last_price_changed_at=so[0]['last_price_changed_at'], address=so[0]['address'])
        if plausible and pl and pl[0]['shop_id'] != so[0]['shop_id']:
            res['cheapest_plausible_excluding_outliers'] = compact(pl[0])
    return res


def nearest(pids, lat, lon, k=5, extra_where='', args=()):
    if isinstance(pids, str):
        pids = [pids]
    ph = ','.join('?' * len(pids))
    sql = f'''SELECT o.shop_id, s.name shop_name, s.address, s.location_label, MIN(o.price_toman) price_toman,
                     dist_km(?, ?, s.lat, s.lon) distance_km, o.product_id
              FROM offers o JOIN shops s USING(shop_id)
              WHERE o.product_id IN ({ph}) AND o.price_toman IS NOT NULL {extra_where}
              GROUP BY o.shop_id ORDER BY distance_km, price_toman'''
    rows = [dict(r) for r in con.execute(sql, (lat, lon, *pids, *args))]
    for r in rows:
        r['distance_km'] = round(r['distance_km'], 3)
    top = rows[:k]
    # tie tolerance: any shop within +0.05 km of the k-th is also acceptable
    cutoff = top[-1]['distance_km'] + 0.05 if top else 0
    acceptable = [r['shop_id'] for r in rows if r['distance_km'] <= cutoff]
    return {'nearest_shops': [compact(r, ('shop_id', 'shop_name', 'address', 'location_label', 'price_toman')) | {'distance_km': r['distance_km']} for r in top],
            'acceptable_shop_ids_for_top_k': acceptable, 'n_candidate_shops': len(rows)}


SPEC_FIELDS = {
    'chip': r'^(تراشه|مدل تراشه)$', 'ram': r'^(ظرفیت رم|رم اجرایی|رم)$', 'storage': r'^حافظه داخلی$',
    'display_size': r'^(اندازه نمایشگر|ابعاد نمایشگر|اندازه صفحه نمایش)$',
    'refresh_rate': r'(نرخ نوسازی)', 'main_camera': r'^(دوربین اصلی|دوربین اصلی - واید/استاندارد)$',
    'battery': r'^(گنجایش باتری|ظرفیت باتری)$', 'charging': r'^سرعت شارژ$', 'ip_rating': r'(گواهی پایداری|مقاومت دربرابر)',
    'weight': r'^وزن$', '5g': r'^(پشتیبانی از 5G|فناوری\u200c ارتباطی)$',
}


def specs(pid, fields=None):
    rows = con.execute('SELECT key, value FROM product_specs WHERE product_id=?', (pid,)).fetchall()
    out = {}
    for f, pat in SPEC_FIELDS.items():
        if fields and f not in fields:
            continue
        for k, v in rows:
            if k and re.search(pat, k):
                out.setdefault(f, f'{k}: {v}')
                break
    return out


def shop(sid):
    r = dict(con.execute('SELECT shop_id,name,address,location_label,lat,lon,phone,phone_latin,instagram,website_url,'
                         'supports_fast_delivery,weekly_hours,payment_options FROM shops WHERE shop_id=?', (sid,)).fetchone())
    r['weekly_hours'] = json.loads(r['weekly_hours']) if r['weekly_hours'] else {}
    r['payment_options'] = [{'provider_name': p['provider_name'], 'channel': p['channel']} for p in json.loads(r['payment_options'] or '[]')]
    return r


def search(where, args=(), order='s.min_price', limit=None):
    sql = f'''SELECT p.product_id, p.persian_title, p.brand_name, s.min_price, s.n_shops
              FROM products p JOIN product_stats s USING(product_id) WHERE {where} ORDER BY {order}'''
    rows = [dict(r) for r in con.execute(sql, args)]
    return rows if limit is None else rows[:limit]
