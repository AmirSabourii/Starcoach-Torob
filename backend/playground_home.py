"""Data for the real home page (/app): category tiles, category listings, «کم‌قیمت‌ترین پیشنهادهای امروز», Tehran areas, map shops.
Pure SQLite (read-only torob.sqlite) — NO LLM, no HTTP. Every price/count comes from the DB.
Price rules are the same as playground_drill (stale > 30 days, suspicious < 40% of the product's median, median needs ≥3 priced offers)."""
import json, math, statistics, threading
import playground_drill as D
import tools as T

UNKNOWN = D.UNKNOWN

# ---------------------------------------------------------------- tile -> exact DB category_name values (curated, all verified to exist)
TILES = [
    ('digital', 'کالای دیجیتال', ['گوشی موبایل', 'لپ تاپ و نوت بوک', 'تبلت', 'تلویزیون', 'دوربین عکاسی و فیلمبرداری', 'هدفون، هدست و هندزفری',
                                  'ساعت و مچ بند هوشمند', 'اسپیکر و سیستم صوتی', 'پاوربانک و شارژر همراه', 'شارژر گوشی', 'کیف و کاور گوشی',
                                  'محافظ صفحه نمایش گوشی', 'کنسول بازی  PS5', 'کنسول بازی  PS4', 'کنسول بازی Xbox', 'کنسول بازی نینتندو', 'لوازم جانبی کنسول',
                                  'مانیتور', 'ماوس', 'کیبورد', 'ست ماوس و کیبورد', 'هارد دیسک اینترنال', 'فلش مموری', 'مودم LTE/3G/4G/5G']),
    ('home', 'خانه و آشپزخانه', ['یخچال فریزر ساید بای ساید', 'یخچال فریزر بالاپایین', 'یخچال فریزر دوقلو', 'ماشین لباسشویی', 'ماشین ظرفشویی',
                                 'اجاق گاز', 'هود آشپزخانه', 'مایکروویو', 'هواپز و سرخ کن', 'چای ساز', 'قهوه و اسپرسو ساز', 'مخلوط کن برقی',
                                 'پلوپز و مولتی کوکر', 'کتری برقی', 'آبمیوه گیری', 'جارو برقی', 'جارو شارژی', 'جارو رباتیک', 'قابلمه تکی',
                                 'سرویس قابلمه', 'ظروف نگهداری و حمل غذا', 'سایر ظروف سرو و پذیرایی', 'کتری و قوری', 'شیرآلات آشپزخانه', 'سینک ظرفشویی',
                                 'لوستر و چراغ تزئینی', 'فرش ماشینی', 'میز جلو مبلی و عسلی', 'مبل تخت‌خواب شو', 'بخاری برقی', 'کولر گازی']),
    ('fashion', 'مد و پوشاک', ['پیراهن مردانه', 'تیشرت و پولوشرت', 'شلوار رسمی و راحتی مردانه', 'سویشرت و هودی مردانه', 'هودی و سویشرت',
                               'سویشرت و هودی زنانه', 'بلوز و پیراهن زنانه', 'نیم تنه و کراپ زنانه', 'شلوار و لگ', 'مانتو و شلوار زنانه',
                               'مانتو، پانچ و رویه', 'کتانی و کفش اسپرت', 'سایر کفش زنانه', 'کفش مجلسی و رسمی مردانه', 'کفش کالج مردانه',
                               'کفش کالج زنانه', 'کیف و کوله', 'عینک آفتابی', 'ساعت مچی عقربه\u200c ای و دیجیتالی']),
    ('sport', 'ورزش و سفر', ['دوچرخه ثابت و الپتیکال', 'تردمیل', 'دمبل، وزنه و هالتر', 'کش ورزشی', 'طناب ورزشی', 'کیف و کوله ورزشی',
                             'شلوار و لگ ورزشی زنانه', 'سایر لباس ورزشی', 'دوربین ورزشی', 'چمدان و ساک', 'کاور کیف و چمدان', 'ساج و اجاق سفری',
                             'چاقوی سفری', 'کلمن و ظروف سفر', 'سایر لوازم سفر و کمپینگ', 'چادر مسافرتی', 'لباس کوهنوردی', 'کیف و کوله کوهنوردی',
                             'کفش کوهنوردی', 'یخچال مسافرتی']),
    ('beauty', 'زیبایی و سلامت', ['عطر و ادکلن', 'ماسک پوستی', 'ضد آفتاب', 'کرم پودر', 'سایر کرم پوستی', 'رنگ مو', 'شامپو و نرم کننده',
                                  'سشوار و برس حرارتی', 'ماشین اصلاح و ریش\u200c تراش', 'برس و ابزار آرایشی', 'سایر آرایش و مراقبت لب',
                                  'فشارسنج پزشکی', 'ماساژور و لوازم ماساژ', 'اکسیژن ساز و نبولایزر', 'کوکتل و مواد ویتامینه']),
    ('kids', 'اسباب‌بازی و کودک', ['فکری، پازل و لگو', 'ماشین اسباب بازی', 'ربات اسباب بازی', 'دوربین اسباب بازی', 'قطعات و لوازم جانبی اسباب بازی',
                                    'سایر اسباب‌بازی و سرگرمی', 'سایر اسباب بازی موزیکال', 'لوازم خانگی اسباب بازی', 'اسباب بازی حمام',
                                    'اسباب بازی حباب ساز', 'هواپیما و هلی کوپتر اسباب بازی', 'کامیون و تریلی اسباب بازی', 'قطار اسباب بازی',
                                    'سایر عروسک', 'عروسک لبوبو', 'عروسک السا', 'عروسک حیوانات', 'عروسک باربی', 'عروسک موزیکال',
                                    'دوربین و مانیتور کنترل کودک', 'ست اتاق خواب کودک', 'سرویس خواب کودک و نوزاد', 'ظروف کودک و نوزاد',
                                    'تخت خواب کودک و نوزاد', 'کتانی و کفش اسپرت بچگانه', 'ست نوزادی']),
    ('books', 'کتاب و لوازم تحریر', ['کتاب چاپی', 'کتاب صوتی و الکترونیکی', 'کتاب‌خوان و کاغذ دیجیتال', 'خودکار', 'مداد نوکی و اتود', 'جامدادی',
                                     'مداد', 'مداد رنگی', 'مداد پاک کن', 'مداد و قلم طراحی', 'دفتر مشق', 'دفتر و کاغذ کلاسور', 'سایر دفتر و کاغذ',
                                     'دفتر و کاغذ یادداشت', 'ست تحریر اداری', 'ست لوازم تحریر', 'ماژیک وایت برد', 'ماژیک', 'ماژیک هایلایتر',
                                     'قلم مو هنری', 'سایر رنگ هنری', 'کاغذ چاپ و کپی']),
    ('tools', 'ابزار و ساختمان', ['سیم و کابل برق ساختمان', 'کلید و پریز', 'کلید و فیوز مینیاتوری', 'سیم سیار و چندراهی برق', 'تابلو و جعبه برق',
                                  'لامپ LED و کم مصرف', 'دریل و پیچ گوشتی برقی و شارژی', 'فرز و مینی فرز', 'پیچ گوشتی', 'سری پیچ گوشتی',
                                  'بکس و آچار بکس', 'آچار تخت و رینگی', 'آچار فرانسه', 'جعبه ابزار', 'مولتی متر', 'سیم لخت\u200cکن و پرس کابل',
                                  'سایر ابزار دستی و تجهیزات کارگاهی', 'شیرآلات آشپزخانه' if False else 'ست کامل شیرآلات']),
]
TILE = {k: {'key': k, 'label': lab, 'categories': cats} for k, lab, cats in TILES}

_lock = threading.Lock()
_CACHE = {}

def _img_ok(u):
    return bool(u) and u.startswith('http')

def _tile_products(key):
    """all products of a tile with their DB price summary (computed once, cached; the DB is static)"""
    with _lock:
        if key in _CACHE:
            return _CACHE[key]
    cats = TILE[key]['categories']
    ph = ','.join('?' * len(cats))
    heads = D.q(f'''SELECT p.product_id,p.persian_title,p.brand_name,p.category_name,p.image_urls,s.n_offers,s.n_shops,s.n_priced
                    FROM products p JOIN product_stats s USING(product_id) WHERE p.category_name IN ({ph})''', cats)
    offers = {}
    for pid, price, ts in D.q(f'''SELECT o.product_id,o.price_toman,o.last_price_changed_at FROM offers o JOIN products p USING(product_id)
                                 WHERE p.category_name IN ({ph}) AND o.price_toman IS NOT NULL''', cats):
        offers.setdefault(pid, []).append((price, ts))
    out = []
    for pid, title, brand, cat, imgs, n_off, n_shops, n_priced in heads:
        ps = offers.get(pid, [])
        med = statistics.median([p for p, _ in ps]) if len(ps) >= D.MIN_PRICED_FOR_MEDIAN else None
        fresh, anyp = None, None
        for price, ts in ps:
            age, stale, sus, labels = D._label_offer(price, ts, med)
            if not stale and not sus and (fresh is None or price < fresh[0]):
                fresh = (price, age)
            if not sus and (anyp is None or price < anyp[0]):
                anyp = (price, age, labels)
        img = D._img(imgs)
        if fresh:
            price = {'price_toman': int(fresh[0]), 'fresh': True, 'labels': [], 'age_days': fresh[1]}
        elif anyp:
            price = {'price_toman': int(anyp[0]), 'fresh': False, 'labels': anyp[2], 'age_days': anyp[1]}
        else:
            price = {'price_toman': None, 'fresh': False, 'labels': [], 'age_days': None}
        out.append({'product_id': pid, 'title': title or UNKNOWN, 'brand': brand or UNKNOWN, 'category': cat, 'image': img if _img_ok(img) else None,
                    'price': price, 'median_price': int(med) if med else None, 'n_offers': n_off or 0, 'n_shops': n_shops or 0, 'n_priced': n_priced or 0})
    # popularity order: more shops first, products with a picture and a fresh price first
    out.sort(key=lambda r: (r['image'] is None, not r['price']['fresh'], r['price']['price_toman'] is None, -r['n_shops'], -r['n_offers']))
    with _lock:
        _CACHE[key] = out
    return out

def tiles():
    res = []
    for k, lab, cats in TILES:
        ps = _tile_products(k)
        per = {}
        for p in ps:
            per[p['category']] = per.get(p['category'], 0) + 1
        res.append({'key': k, 'label': lab, 'n_products': len(ps), 'n_priced': sum(1 for p in ps if p['price']['price_toman']),
                    'n_fresh': sum(1 for p in ps if p['price']['fresh']), 'n_with_image': sum(1 for p in ps if p['image']),
                    'categories': [{'name': c, 'n_products': per.get(c, 0)} for c in cats if per.get(c)]})
    return {'tiles': res, 'llm_calls': 0}

def category(key, sub=None, offset=0, limit=20):
    if key not in TILE:
        return None
    ps = _tile_products(key)
    per = {}
    for p in ps:
        per[p['category']] = per.get(p['category'], 0) + 1
    if sub:
        ps = [p for p in ps if p['category'] == sub]
    return {'key': key, 'label': TILE[key]['label'], 'sub': sub or None, 'total': len(ps), 'offset': offset,
            'subs': [{'name': c, 'n_products': per[c]} for c in TILE[key]['categories'] if per.get(c)],
            'items': ps[offset:offset + limit], 'rules': _RULES, 'llm_calls': 0}

# ---------------------------------------------------------------- «کم‌قیمت‌ترین پیشنهادهای امروز»
DEAL_TILES = ('digital', 'home', 'fashion', 'sport', 'beauty', 'kids', 'books')   # consumer tiles; «ابزار و ساختمان» is left out (per-metre vs roll prices skew medians)
DEAL_RULE = ('محصولات کاشی‌های مصرفی (همه به‌جز ابزار و ساختمان) که عکس دارند و دست‌کم ۵ فروشنده و ۳ پیشنهاد قیمت‌دار دارند؛ '
             'قیمت = ارزان‌ترین پیشنهاد به‌روز (حداکثر ۳۰ روز) و غیرمشکوک (دست‌کم ۴۰٪ میانه). '
             'رتبه = بیشترین فاصلهٔ این قیمت تا میانهٔ قیمت همان محصول (بین ۱۰٪ و ۴۵٪)، حداکثر ۱ محصول از هر زیردسته و ۲ محصول از هر کاشی؛ ترتیب کاشی‌ها یک‌درمیان.')
_RULES = {'stale_days': D.STALE_DAYS, 'suspicious_ratio': D.SUSPICIOUS_RATIO, 'median_needs_priced_offers': D.MIN_PRICED_FOR_MEDIAN}

def deals(limit=10):
    with _lock:
        cached = _CACHE.get('_deals')
    if cached is None:
        cand = []
        for k in DEAL_TILES:
            for p in _tile_products(k):
                pr = p['price']
                if not (p['image'] and pr['fresh'] and p['median_price'] and p['n_priced'] >= 3 and p['n_shops'] >= 5):
                    continue
                disc = 1 - pr['price_toman'] / p['median_price']
                if 0.10 <= disc <= 0.45:
                    cand.append((disc, k, p))
        cand.sort(key=lambda x: -x[0])
        per_cat, per_tile, out = {}, {}, []
        for disc, k, p in cand:
            if per_cat.get(p['category'], 0) >= 1 or per_tile.get(k, 0) >= 2:
                continue
            per_cat[p['category']] = per_cat.get(p['category'], 0) + 1
            per_tile[k] = per_tile.get(k, 0) + 1
            out.append(dict(p, tile=k, discount_pct=int(round(disc * 100))))
        # interleave tiles (round-robin, best discount first inside each tile) so the first cards are varied
        by = {}
        for d in out: by.setdefault(d['tile'], []).append(d)
        cached = []
        while any(by.values()):
            for k in DEAL_TILES:
                if by.get(k): cached.append(by[k].pop(0))
        with _lock:
            _CACHE['_deals'] = cached
    return {'items': cached[:limit], 'total': len(cached), 'rule': DEAL_RULE, 'rules': _RULES, 'llm_calls': 0}

# ---------------------------------------------------------------- Tehran areas (the same gazetteer the agents use: tools.PLACES)
_PRETTY = {'جنت اباد': 'جنت‌آباد', 'سعادت اباد': 'سعادت‌آباد', 'ازادی': 'آزادی', 'نازی اباد': 'نازی‌آباد', 'تهرانپارس': 'تهرانپارس'}
def areas():
    seen, out = set(), []
    for k, (la, lo) in T.PLACES.items():
        if k == 'تهران پارس' or (la, lo) in seen:
            continue
        seen.add((la, lo))
        out.append({'key': k, 'label': _PRETTY.get(k, k), 'lat': la, 'lon': lo})
    out.sort(key=lambda a: (a['key'] != 'ونک', a['label']))
    return {'areas': out, 'default': 'ونک', 'llm_calls': 0}

def area_point(key):
    c = T.PLACES.get((key or '').replace('آ', 'ا').replace('\u200c', ' '))
    return c

def _hav(a, b, c, d):
    r = math.radians
    x = math.sin(r(c - a) / 2) ** 2 + math.cos(r(a)) * math.cos(r(c)) * math.sin(r(d - b) / 2) ** 2
    return 12742 * math.asin(math.sqrt(x))

def map_shops(area='ونک', tile=None, q=None, limit=80):
    c = area_point(area) or T.PLACES['ونک']
    filt, args = '', []
    flabel = None
    if tile in TILE:
        cats = TILE[tile]['categories']
        filt = f' AND shop_id IN (SELECT DISTINCT o.shop_id FROM offers o JOIN products p USING(product_id) WHERE p.category_name IN ({",".join("?" * len(cats))}))'
        args = list(cats); flabel = TILE[tile]['label']
    elif q and q.strip():
        terms = [t for t in T.norm(q).split() if len(t) > 1][:4]
        if terms:
            fts = ' '.join('"' + t.replace('"', '') + '"*' for t in terms)
            filt = ' AND shop_id IN (SELECT DISTINCT o.shop_id FROM offers o WHERE o.product_id IN (SELECT product_id FROM products_fts WHERE products_fts MATCH ? LIMIT 4000))'
            args = [fts]; flabel = q.strip()[:40]
    box = 0.06
    if not filt:     # «همه»: only shops that have at least one offer in the data
        filt = ' AND shop_id IN (SELECT DISTINCT shop_id FROM offers)'
    rows = D.q(f'''SELECT shop_id,name,location_label,address,lat,lon FROM shops WHERE lat BETWEEN ? AND ? AND lon BETWEEN ? AND ?{filt}''',
               [c[0] - box, c[0] + box, c[1] - box, c[1] + box] + args)
    shops = sorted(({'shop_id': r[0], 'name': r[1] or UNKNOWN, 'area': r[2] or UNKNOWN, 'address': r[3] or UNKNOWN, 'lat': r[4], 'lon': r[5],
                     '_d': _hav(c[0], c[1], r[4], r[5])} for r in rows if r[4] is not None), key=lambda s: s['_d'])
    out = []
    for s in shops[:limit]:
        d = s.pop('_d')
        s['nearby'] = 'همین نزدیکی' if d <= 1.5 else 'کمی دورتر'      # approximate words only, never a number
        out.append(s)
    return {'area': area, 'centre': list(c), 'filter': flabel, 'n_total_in_view': len(shops), 'shops': out, 'llm_calls': 0}


# ================================================================ /app product + shop screens (pure SQLite, no LLM)
from datetime import datetime as _dt
import re as _re

# installments: shop_payment_options rows whose provider is a BNPL / installment service (the only payment rows in this DB)
INSTALLMENT_PROVIDERS = ('ترب\u200cپی', 'اسنپ\u200cپی', 'دیجی پی', 'تارا', 'ازکی\u200cوام')
_NO_WARRANTY = ('بدون گارانتی', 'تست و تحویل در حضور مشتری')
_BZ = {'hubs': None}

def _hubs():
    if _BZ['hubs'] is None:
        try:
            import playground_bazaar as BZ
            hs = []
            for g in BZ.data()['groups']:
                for h in g['hubs']:
                    hs.append((h['hub_name'], h['center']['lat'], h['center']['lon'], float(h.get('radius_km') or 0.6)))
            _BZ['hubs'] = hs
        except Exception:
            _BZ['hubs'] = []
    return _BZ['hubs']

def place_label(lat, lon, location_label):
    """«بازار X» only when the shop sits inside a trade hub computed in bazaars.json; else the shop's own location_label"""
    if lat is not None and lon is not None:
        best = None
        for name, la, lo, rad in _hubs():
            d = _hav(lat, lon, la, lo)
            if d <= max(rad, 0.35) and (best is None or d < best[0]):
                best = (d, name)
        if best:
            return 'بازار ' + best[1], True
    return (location_label or D.UNKNOWN), False

def _installments(sid):
    rows = D.q('SELECT DISTINCT provider_name FROM shop_payment_options WHERE shop_id=?', (sid,))
    return [r[0] for r in rows if r[0] in INSTALLMENT_PROVIDERS]

def _warranty(js, months):
    try:
        d = json.loads(js) if js else None
    except Exception:
        d = None
    prov = (d or {}).get('provider') if isinstance(d, dict) else None
    m = months or ((d or {}).get('period_months') if isinstance(d, dict) else None)
    if m:
        return {'has': True, 'months': int(m), 'label': f'گارانتی {str(int(m)).translate(D._FA)} ماهه', 'provider': prov}
    if prov and prov not in _NO_WARRANTY:
        return {'has': True, 'months': None, 'label': 'گارانتی ' + prov[:24], 'provider': prov}
    return {'has': False, 'months': None, 'label': None, 'provider': prov}

def coarse_distance(km):
    if km is None:
        return None
    return 'همین نزدیکی' if km < 1.5 else ('نزدیک' if km < 5 else ('کمی دورتر' if km < 12 else 'دور'))

def _main_categories(sid, k=4):
    rows = D.q('''SELECT p.category_name, COUNT(DISTINCT o.product_id) n FROM offers o JOIN products p USING(product_id)
                  WHERE o.shop_id=? AND p.category_name IS NOT NULL GROUP BY 1 ORDER BY n DESC LIMIT ?''', (sid, k))
    return [{'name': r[0], 'n_products': r[1]} for r in rows]

def _updated_fa(age):
    if age is None:
        return D.UNKNOWN
    return 'به‌روزرسانی امروز' if age <= 0 else f'به‌روزرسانی {str(age).translate(D._FA)} روز پیش'

HIGH_RATIO = 3.0   # /app display only: a price > 3x the product median (e.g. an extra zero) is shown as «قیمت مشکوک» and left out of ranges

def _flag_high(offers, med):
    for o in offers:
        if med and o['price_toman'] and o['price_toman'] > HIGH_RATIO * med and not o['suspicious']:
            o['suspicious'] = True; o['suspicious_high'] = True; o['labels'] = o['labels'] + ['مشکوک']

def card_info(pids):
    """chat product cards: price range (fresh, non-suspicious first), seller count, the top 1–2 areas"""
    out = {}
    for pid in pids[:12]:
        po = D.product_offers(pid)
        if not po:
            continue
        _flag_high(po['offers'], po['median_price'])
        good = [o for o in po['offers'] if o['price_toman'] and not o['stale'] and not o['suspicious']]
        pool = good or [o for o in po['offers'] if o['price_toman'] and not o['suspicious']]
        prices = sorted(o['price_toman'] for o in pool)
        areas = {}
        for o in po['offers']:
            if o['shop_area'] and o['shop_area'] != D.UNKNOWN:
                areas[o['shop_area']] = areas.get(o['shop_area'], 0) + 1
        top = [a for a, _ in sorted(areas.items(), key=lambda x: -x[1])[:2]]
        out[pid] = {'product_id': pid, 'title': po['title'], 'model': po['model'], 'image': po['image'],
                    'min_price': prices[0] if prices else None, 'max_price': prices[-1] if prices else None,
                    'prices_fresh': bool(good), 'n_shops': po['n_shops'], 'areas': top, 'area_label': ' و '.join(top) if top else D.UNKNOWN}
    return {'cards': out, 'llm_calls': 0}

def sellers(pid, area=None):
    po = D.product_offers(pid)
    if not po:
        return None
    c = area_point(area) if area else None
    _flag_high(po['offers'], po['median_price'])
    po['offers'].sort(key=D._sort_key)
    ids = list({o['shop_id'] for o in po['offers'] if o['shop_id']})
    meta = {}
    if ids:
        ph = ','.join('?' * len(ids))
        for sid, fast, lat, lon, label in D.q(f'SELECT shop_id,supports_fast_delivery,lat,lon,location_label FROM shops WHERE shop_id IN ({ph})', ids):
            meta[sid] = (fast, lat, lon, label)
    wrows = {r[0]: (r[1], r[2]) for r in D.q('SELECT offer_id,warranty,warranty_months FROM offers WHERE product_id=?', (pid,))}
    rows, places, seen = [], set(), set()
    for o in po['offers']:          # one card per shop: its best offer (offers are already sorted fresh-cheapest first)
        if o['shop_id'] in seen:
            continue
        seen.add(o['shop_id'])
        fast, lat, lon, label = meta.get(o['shop_id'], (None, None, None, None))
        place, is_hub = place_label(lat, lon, label)
        w = _warranty(*wrows.get(o['offer_id'], (None, None)))
        km = _hav(c[0], c[1], lat, lon) if c and lat is not None else None
        inst = _installments(o['shop_id'])
        rows.append(dict(o, place=place, place_is_bazaar=is_hub, fast_delivery=None if fast is None else bool(fast),
                         installment=bool(inst), installment_providers=inst, warranty_info=w,
                         distance_label=coarse_distance(km), _km=km, updated_fa=_updated_fa(o['age_days']),
                         main_category=(_main_categories(o['shop_id'], 1) or [{'name': None}])[0]['name']))
        if lat is not None:
            places.add(place)
    good = [r for r in rows if r['price_toman'] and not r['stale'] and not r['suspicious']]
    if good:
        good[0]['cheapest'] = True
    pts = [(r['shop_lat'], r['shop_lon']) for r in rows if r['shop_lat'] is not None]
    spread = None
    if pts:
        cla, clo = sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
        spread = max(_hav(cla, clo, a, b) for a, b in pts)
    for i, r in enumerate(sorted([r for r in rows if r['_km'] is not None], key=lambda r: r['_km'])):
        r['near_rank'] = i
    import playground_mall as _M
    _st = _M.statuses([r['shop_id'] for r in rows if r.get('shop_id')])
    for r in rows:
        r.pop('_km', None)
        st = _st.get(r.get('shop_id')) or {}
        r['open_state'], r['open_badge'] = st.get('state'), st.get('badge')     # «الان بازه» / «الان بسته» / «امروز تعطیل» / None (unknown)
    pool = [r['price_toman'] for r in (good or [r for r in rows if r['price_toman'] and not r['suspicious']])]
    all_bz = bool(places) and all(r['place_is_bazaar'] for r in rows if r['shop_lat'] is not None)
    return {'product_id': pid, 'title': po['title'], 'model': po['model'], 'image': po['image'], 'n_shops': po['n_shops'],
            'min_price': min(pool) if pool else None, 'max_price': max(pool) if pool else None,
            'sellers': rows, 'counts': {'fast': sum(1 for r in rows if r['fast_delivery']), 'installment': sum(1 for r in rows if r['installment']),
                                        'warranty': sum(1 for r in rows if r['warranty_info']['has'])},
            'places': {'n': len(places), 'kind': 'بازار' if all_bz else 'محدوده', 'together': spread is not None and spread < 2.5},
            'area': area, 'note': D.OFFER_NOTE, 'llm_calls': 0}

_DAY_KEYS = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']
def open_now(sid, now=None):
    now = now or _dt.now(D.TEHRAN)
    rows = D.q('SELECT day,status,start_time,end_time FROM shop_hours WHERE shop_id=?', (sid,))
    if not rows:
        return {'known': False, 'open': None, 'label': 'ساعت کاری نامشخص'}
    day = _DAY_KEYS[now.weekday()]
    hm = now.strftime('%H:%M')
    shifts = sorted((a[:5], b[:5]) for d, st, a, b in rows if d == day and st == 'declared' and a and b and not (a[:5] == '00:00' and b[:5] == '00:00'))
    for a, b in shifts:
        end = '24:00' if b == '00:00' else b
        if a <= hm < end:
            return {'known': True, 'open': True, 'until': b, 'label': f'باز است تا {b.translate(D._FA)}'}
    nxt = next(((a, b) for a, b in shifts if a > hm), None)
    return {'known': True, 'open': False, 'opens_at': nxt[0] if nxt else None,
            'label': 'بسته است' + (f' · باز می‌شود {nxt[0].translate(D._FA)}' if nxt else '')}

def shop_plus(sid, pid=None):
    s = D.shop(sid)
    if not s:
        return None
    r = D.q('SELECT lat,lon,location_label FROM shops WHERE shop_id=?', (sid,))[0]
    place, is_hub = place_label(r[0], r[1], r[2])
    cats = _main_categories(sid, 4)
    offer = None
    if pid:
        po = D.product_offers(pid)
        if po:
            mine = [o for o in po['offers'] if o['shop_id'] == sid]
            if mine:
                o = mine[0]
                w = D.q('SELECT warranty,warranty_months FROM offers WHERE offer_id=?', (o['offer_id'],))
                offer = dict(o, product_id=pid, title=po['title'], model=po['model'], image=po['image'],
                             warranty_info=_warranty(*(w[0] if w else (None, None))), updated_fa=_updated_fa(o['age_days']))
    inst = _installments(sid)
    lat, lon = s['lat'], s['lon']
    import playground_mall as _M
    st = _M.status(sid)
    return dict(s, place=place, place_is_bazaar=is_hub, open_now=open_now(sid), open_state=st['state'], open_badge=st['badge'],
                location=_M.place_info(sid), routes=_M.route_links(lat, lon), main_categories=cats,
                installment=bool(inst), installment_providers=inst, offer=offer,
                directions_url=(f'https://www.google.com/maps/dir/?api=1&destination={lat},{lon}' if lat is not None else None),
                osm_url=s['map_url'])

def shop_facts(sid):
    """compact server facts for a shop question sent from the shop sheet (consumed by the V3+ agent via session mission)"""
    s = shop_plus(sid)
    if not s:
        return None
    return {'shop_id': sid, 'name': s['name'], 'area': s['place'], 'address': s['address'],
            'open_now': s['open_now']['label'], 'weekly_hours': [f"{h['day']}: {h['hours']}" for h in (s['hours'] or [])],
            'payment_options': [p['provider'] for p in s['payment_options']] or 'ثبت نشده',
            'installment': ('بله: ' + '، '.join(s['installment_providers'])) if s['installment'] else 'در داده ثبت نشده',
            'fast_delivery': {True: 'دارد', False: 'ندارد', None: 'نامشخص'}[s['fast_delivery']],
            'main_categories': [c['name'] for c in s['main_categories']], 'n_products': s['n_products'],
            'not_in_data': 'parking, stock/availability, discounts beyond listed prices, staff, phone call results',
            'note': 'The shopper is asking about THIS shop from its page. Answer only from these facts (or tools on this shop_id). If the data has nothing (e.g. parking), say plainly it is not recorded; never guess.'}
