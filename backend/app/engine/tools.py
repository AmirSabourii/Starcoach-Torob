"""Read-only, DB-grounded tools for the Torob in-person shopping assistant.
Every tool returns compact JSON-serialisable dicts built only from torob.sqlite rows."""
import json, math, os, re, statistics
from datetime import datetime, timezone
from build_eval_db import norm
from gt_lib import connect, haversine, con

REF_DATE = datetime(2026, 10, 22, tzinfo=timezone.utc)
STALE_DAYS = 90

STOP = set('قیمت چند چنده چقدر چقدره کجا کجاست میخوام می خوام میخواهم بخرم خرید با و از رو را برای به در که یه یک چی چیه هست داره دارید دارن الان مدل لطفا میشه بده بگو تا زیر کمتر بیشتر ارزون ارزان ترین ارزونترین درمیاد تومن تومان معمولی the price of for'.split())
SYN = {  # query token -> alternatives (all normalised)
    'آیفون': ['آیفون', 'iphone'], 'iphone': ['آیفون', 'iphone'], 'ایفون': ['آیفون', 'iphone'],
    'ایرپاد': ['ایرپاد', 'airpods'], 'airpods': ['ایرپاد', 'airpods'], 'airpod': ['ایرپاد', 'airpods'],
    'پلی': ['ps5', 'پلی'], 'ps5': ['ps5'], 'اسلیم': ['slim', 'اسلیم'], 'slim': ['slim', 'اسلیم'],
    'دیجیتال': ['digital', 'دیجیتال'], 'digital': ['digital', 'دیجیتال'], 'پرو': ['pro', 'پرو'], 'pro': ['pro', 'پرو'],
    'مکس': ['max', 'مکس'], 'max': ['max', 'مکس'], 'اولترا': ['ultra', 'اولترا'], 'ultra': ['ultra', 'اولترا'],
    'ردمی': ['redmi', 'ردمی'], 'redmi': ['redmi', 'ردمی'], 'نوت': ['note', 'نوت'], 'note': ['note', 'نوت'],
    'پوکو': ['poco', 'پوکو'], 'poco': ['poco', 'پوکو'], 'گلکسی': ['galaxy', 'گلکسی', 'سامسونگ'], 'galaxy': ['galaxy', 'گلکسی', 'سامسونگ'],
    'samsung': ['سامسونگ', 'samsung'], 'سامسونگ': ['سامسونگ', 'samsung'], 'xiaomi': ['شیائومی', 'xiaomi'], 'شیائومی': ['شیائومی', 'xiaomi'],
    'apple': ['اپل', 'apple'], 'اپل': ['اپل', 'apple'], 'jbl': ['jbl', 'جی'], 'انکر': ['انکر', 'anker'], 'anker': ['انکر', 'anker'],
    'ایکس': ['xbox', 'ایکس'], 'xbox': ['xbox', 'ایکس'], 'ایکسباکس': ['xbox'], 'واچ': ['watch', 'واچ'], 'watch': ['watch', 'واچ'],
    'سری': ['series', 'سری'], 'series': ['series', 'سری'], 'نات': ['not', 'نات'], 'اکتیو': ['active', 'اکتیو'],
    'لپتاپ': ['لپ'], 'گیگ': ['گیگ'], 'هارمن': ['هارمن', 'harman'], 'لیبرتی': ['liberty', 'لیبرتی'],
}
ACCESSORY_WORDS = ['قاب', 'کاور', 'گلس', 'محافظ', 'باتری', 'تاچ', 'ال سی دی', 'lcd', 'فلت', 'ویبره', 'برد', 'هولدر', 'کیف',
                   'برچسب', 'اسکرین', 'لنز دوربین', 'دوربین پشت', 'پک کامل', 'شارژر', 'کابل', 'بند', 'استیکر', 'درب پشت', 'فریم',
                   'اسپیکر مکالمه', 'رینگ', 'ring', 'گوش چپ', 'گوش راست', 'سمت چپ', 'سمت راست', 'case', 'cover', 'glass', 'battery',
                   'back camera', 'دسته بازی', 'سوکت', 'فیلم', 'آنتن', 'دکمه', 'مادربرد', 'سیم کارت خور', 'خشاب', 'شیشه', 'پایه', 'لوازم', 'شاسی', 'دوربین اصلی', 'دوربین سلفی']
def _cat_acc(cat, first):
    # category-based accessory flag, except when the category head names the item itself
    # e.g. 'دزدگیر اماکن و لوازم جانبی' for a title starting with 'دزدگیر' is the device
    cat = norm(cat or '')
    if not any(c in cat for c in ACCESSORY_CATS):
        return False
    head = cat.split(' و ')[0]
    if any(c in head for c in ACCESSORY_CATS):
        return True
    t0 = (first or '').split()[:1]
    return not (t0 and t0[0] in head.split() and not any(t0[0].startswith(w) for w in ACCESSORY_WORDS))


PHONE_HINT = ['گوشی', 'موبایل', 'iphone', 'آیفون', 'گلکسی', 'galaxy', 'redmi', 'ردمی', 'poco', 'پوکو']
VARIANT_WORDS = {'max': ['max', 'مکس'], 'ultra': ['ultra', 'اولترا'], 'plus': ['plus', 'پلاس'], 'pro': ['pro', 'پرو'], 'lite': ['lite', 'لایت'], 'mini': ['mini', 'مینی']}
ACCESSORY_CATS = ['کیف و کاور', 'محافظ صفحه', 'تاچ و ال سی دی', 'باتری گوشی', 'قطعات', 'لوازم جانبی', 'شارژر', 'کابل و تبدیل', 'کاور و لوازم', 'دوربین گوشی', 'شاسی', 'درب گوشی', 'قطعه']
DEVICE_HINT = ['گوشی', 'موبایل', 'تلفن', 'iphone', 'آیفون', 'phone']


def _days_old(iso):
    if not iso:
        return None
    return round((REF_DATE - datetime.fromisoformat(iso)).total_seconds() / 86400)


def _addr_key(s):
    s = norm(s or '').replace('ء', '').replace('ئ', 'ی')
    return re.sub(r'\s+', '', s)


def _tokens(q):
    q = norm(q or '')
    q = re.sub(r'(\d+)\s*(گیگابایت|گیگ|gb|tb|ترابایت)', r'\1', q)
    q = re.sub(r'(\d)([a-z\u0600-\u06ff])', r'\1 \2', q)          # 42mm -> 42 mm
    toks = [t for t in re.findall(r'[\w\-./]+', q) if t not in STOP and len(t) > 0]
    return toks


WEAK = {'mm', 'میلی', 'میلیمتر', 'میلیمتری', 'متری', 'اینچ', 'inch', 'سایز', 'رنگ', 'اصل', 'اصلی', 'اورجینال', 'نسخه', 'گیگابایت'}


def _fts_group(tok):
    alts = SYN.get(tok, [tok])
    parts = []
    for a in alts:
        a = a.replace('"', '')
        parts.append(f'"{a}"*' if not (a.isdigit() or len(a) <= 2) else f'"{a}"')
    return '(' + ' OR '.join(parts) + ')' if len(parts) > 1 else parts[0]


def _word_hit(tok, text_words, text):
    for a in SYN.get(tok, [tok]):
        if a.isdigit() or len(a) <= 2:
            if a in text_words:
                return True
        elif any(w.startswith(a) for w in text_words) or (len(a) > 3 and a in text):
            return True
    return False


def _shop_prices(pid):
    return [r[0] for r in con.execute('SELECT MIN(price_toman) FROM offers WHERE product_id=? AND price_toman IS NOT NULL GROUP BY shop_id', (pid,))]


def _price_info(pid):
    ps = sorted(_shop_prices(pid))
    if not ps:
        return {'min_price': None, 'max_price': None, 'median_price': None, 'n_shops_priced': 0}
    med = statistics.median(ps)
    plausible = [p for p in ps if 0.4 * med <= p <= 2.5 * med]
    out = {'min_price': int(ps[0]), 'median_price': int(med), 'max_price': int(ps[-1]), 'n_shops_priced': len(ps)}
    if plausible and (plausible[0] != ps[0] or plausible[-1] != ps[-1]):
        out['plausible_range'] = [int(plausible[0]), int(plausible[-1])]
        out['outlier_warning'] = 'some shop prices are far from the median (possible data error / different item)'
    return out


# ------------------------------------------------------------------ tool 1
def search_products_lexical(query, brand=None, category=None, min_price=None, max_price=None, limit=10, _max_limit=15):
    limit = max(1, min(int(limit or 10), _max_limit))
    toks = _tokens(query)
    if brand:
        toks = [t for t in toks if t not in [norm(brand)] + SYN.get(norm(brand), [])]
    groups = [_fts_group(t) for t in toks]
    if brand:
        b = norm(brand)
        groups.append('{brand_name persian_title} : ' + _fts_group(b))
    if category:
        for t in _tokens(category):
            groups.append('{category_name persian_title} : ' + _fts_group(t))
    if not groups:
        return {'query': query, 'n_results': 0, 'results': [], 'note': 'empty query'}
    price_sql, args = '', []
    if min_price is not None or max_price is not None:
        price_sql = ' AND EXISTS (SELECT 1 FROM offers o WHERE o.product_id=f.product_id AND o.price_toman BETWEEN ? AND ?)'
        args = [float(min_price or 0), float(max_price or 1e12)]
    cands = {}
    for mode in ('AND', 'OR'):
        expr = f' {mode} '.join(groups)
        try:
            rows = con.execute(f'''SELECT f.product_id, bm25(products_fts) r FROM products_fts f
                                   WHERE products_fts MATCH ? {price_sql} ORDER BY r LIMIT 1500''', [expr] + args).fetchall()
        except Exception as e:
            rows = []
        for pid, r in rows:
            cands.setdefault(pid, r)
        if mode == 'AND' and len(cands) >= limit:
            break
    qn = norm(query or '')
    wants_accessory = any(w in qn for w in ACCESSORY_WORDS)
    wants_knockoff = 'طرح' in qn or 'کپی' in qn
    wants_device = any(w in qn for w in DEVICE_HINT) or not wants_accessory
    wants_phone = any(w in qn for w in PHONE_HINT) and not wants_accessory and not category
    q_variants = {v for v, alts in VARIANT_WORDS.items() if any(re.search(rf'(^|[^\w]){a}($|[^\w])', qn) for a in alts)}
    missing_by_tok = {t: 0 for t in toks}
    scored = []
    for pid, bm in cands.items():
        p = con.execute('SELECT p.persian_title, p.title_norm, p.brand_name, p.category_name, s.n_shops, s.n_priced FROM products p JOIN product_stats s USING(product_id) WHERE product_id=?', (pid,)).fetchone()
        title, tn, br, cat, n_shops, n_priced = p
        tn = tn or ''
        if brand and norm(brand) not in norm(br or '') and not any(a in tn for a in SYN.get(norm(brand), [norm(brand)])):
            continue
        text = f'{tn} {norm(br or "")} {norm(cat or "")}'
        words = re.findall(r'[\w\-./]+', text)
        hits = [_word_hit(t, words, text) for t in toks]
        strong = [h for t, h in zip(toks, hits) if t not in WEAK] or hits
        cov = sum(strong) / max(1, len(strong))
        for t, h in zip(toks, hits):
            if h:
                missing_by_tok[t] += 1
        first = ' '.join(tn.split()[:3])
        is_acc = any(first.startswith(w) or f' {w} ' in f' {first} ' for w in ACCESSORY_WORDS) or _cat_acc(cat, first)
        is_knock = 'طرح' in tn.split()[:4] or 'طرح' in first
        if any(w in tn for w in ('گوش چپ', 'گوش راست', 'سمت چپ', 'سمت راست', 'تک گوش', 'left', 'right')) and not wants_accessory:
            is_acc = True   # single earbud / spare part
        is_used = 'استوک' in tn or 'کارکرده' in tn
        score = cov * 10 + math.log1p(n_shops) * 0.6 - 0.02 * bm
        if is_acc and not wants_accessory and wants_device:
            score -= 6
        if is_knock and not wants_knockoff:
            score -= 8
        if wants_phone:
            score += 4 if cat == 'گوشی موبایل' else -3
        t_words = set(words)
        for v, alts in VARIANT_WORDS.items():
            if v not in q_variants and any(a in t_words for a in alts):
                score -= 2.5   # title has an extra variant word (e.g. Max) the user did not ask for
        if not n_priced:
            score -= 2
        scored.append((score, pid, title, br, cat, n_shops, is_acc, is_knock, is_used, cov))
    scored.sort(key=lambda x: -x[0])
    results, seen_titles = [], {}
    for score, pid, title, br, cat, n_shops, is_acc, is_knock, is_used, cov in scored:
        key = norm(title or '')
        if key in seen_titles:
            seen_titles[key].setdefault('same_title_other_product_ids', []).append(pid)
            continue
        if len(results) >= limit:
            continue
        r = {'product_id': pid, 'title': title, 'brand': br, 'category': cat, 'n_shops': n_shops}
        r.update(_price_info(pid))
        flags = []
        if is_acc and not wants_accessory:
            flags.append('ACCESSORY_OR_PART (not the device itself)')
        if is_knock:
            flags.append('KNOCKOFF_طرح (imitation, not genuine brand)')
        if is_used:
            flags.append('USED_OR_STOCK (استوک/کارکرده)')
        if cov < 1:
            flags.append(f'PARTIAL_MATCH ({cov:.0%} of query terms)')
        if flags:
            r['flags'] = flags
        results.append(r)
        seen_titles[key] = r
    for r in results:
        if 'same_title_other_product_ids' in r:
            r['note'] = 'other catalogue entries share this exact title; consider them the same item (pass all ids to store tools)'
    out = {'query': query, 'filters': {k: v for k, v in dict(brand=brand, category=category, min_price=min_price, max_price=max_price).items() if v is not None},
           'n_candidates': len(scored), 'n_results': len(results), 'results': results}
    never = [t for t, n in missing_by_tok.items() if n == 0]
    if never:
        out['terms_not_found_in_any_product'] = never
    if not results:
        out['note'] = 'NO MATCHING PRODUCTS IN DATASET'
    elif all('flags' in r and any(f.startswith('PARTIAL_MATCH') for f in r['flags']) for r in results):
        out['note'] = 'NO EXACT MATCH – results are only partial matches; the exact requested item may not exist in the dataset'
    return out


def describe_product(pid, query=''):
    """Result row (same shape as search results) for a product surfaced by a non-lexical retriever."""
    p = con.execute('SELECT p.persian_title, p.title_norm, p.brand_name, p.category_name, s.n_shops FROM products p JOIN product_stats s USING(product_id) WHERE product_id=?', (pid,)).fetchone()
    if not p:
        return None
    title, tn, br, cat, n_shops = p
    tn, qn = tn or '', norm(query or '')
    first = ' '.join(tn.split()[:3])
    wants_acc = any(w in qn for w in ACCESSORY_WORDS)
    is_acc = (any(first.startswith(w) or f' {w} ' in f' {first} ' for w in ACCESSORY_WORDS) or _cat_acc(cat, first)
              or any(w in tn for w in ('گوش چپ', 'گوش راست', 'سمت چپ', 'سمت راست'))) and not wants_acc
    r = {'product_id': pid, 'title': title, 'brand': br, 'category': cat, 'n_shops': n_shops}
    r.update(_price_info(pid))
    flags = []
    if is_acc:
        flags.append('ACCESSORY_OR_PART (not the device itself)')
    if 'طرح' in first and 'طرح' not in qn:
        flags.append('KNOCKOFF_طرح (imitation, not genuine brand)')
    if 'استوک' in tn or 'کارکرده' in tn:
        flags.append('USED_OR_STOCK (استوک/کارکرده)')
    if flags:
        r['flags'] = flags
    return r


USE_RECALL_LAYER = os.environ.get('TOROB_RECALL', '1') == '1'   # default ON; TOROB_RECALL=0 for the pure-lexical baseline


def search_products(query, brand=None, category=None, min_price=None, max_price=None, limit=10):
    if USE_RECALL_LAYER:
        from recall import search_products_hybrid
        return search_products_hybrid(query, brand=brand, category=category, min_price=min_price, max_price=max_price, limit=limit)
    return search_products_lexical(query, brand=brand, category=category, min_price=min_price, max_price=max_price, limit=limit)


# ------------------------------------------------------------------ tool 2
SPEC_KEYS = {
    'chip': r'^(تراشه|مدل تراشه|پردازنده)$', 'ram': r'^(ظرفیت رم|رم اجرایی|رم|حافظه رم)$', 'storage': r'^(حافظه داخلی|ظرفیت حافظه)',
    'display': r'^(اندازه نمایشگر|ابعاد نمایشگر|اندازه صفحه نمایش)$', 'refresh_rate': r'نرخ نوسازی',
    'main_camera': r'^(دوربین اصلی|دوربین اصلی - واید/استاندارد|ترکیب دوربین|پیکربندی دوربین پشت)$', 'telephoto': r'^دوربین تله',
    'selfie': r'^(دوربین سلفی|دوربین سلفی اصلی)$', 'battery': r'^(گنجایش باتری|ظرفیت باتری)', 'charging': r'^سرعت شارژ$',
    'water_resistance': r'(گواهی پایداری|مقاومت دربرابر)', 'network': r'^(پشتیبانی از 5G|فناوری\u200c ارتباطی)$', 'weight': r'^وزن$',
    'os': r'^(سیستم عامل|نوع سیستم\u200cعامل)$', 'resolution': r'^(کیفیت صفحه نمایش|رزولوشن|کیفیت تصویر)$', 'panel': r'^(نوع صفحه نمایش|نوع نمایشگر|نوع پنل)$',
}


def compare_products(product_ids):
    if isinstance(product_ids, str):
        product_ids = [product_ids]
    out = []
    for pid in product_ids[:4]:
        p = con.execute('SELECT persian_title, brand_name, category_name FROM products WHERE product_id=?', (pid,)).fetchone()
        if not p:
            out.append({'product_id': pid, 'error': 'NOT_FOUND'})
            continue
        specs = con.execute('SELECT key, value FROM product_specs WHERE product_id=?', (pid,)).fetchall()
        sel = {}
        for f, pat in SPEC_KEYS.items():
            for k, v in specs:
                if k and re.search(pat, k):
                    sel[f] = (v or '').strip(' ,')[:120]
                    break
        if not sel and specs:
            sel = {k: (v or '')[:80] for k, v in specs[:12]}
        r = {'product_id': pid, 'title': p[0], 'brand': p[1], 'category': p[2], 'specs': sel or 'NO_SPECS_IN_DATASET'}
        r.update(_price_info(pid))
        out.append(r)
    return {'products': out}


# ------------------------------------------------------------------ store helpers
def _shop_pay(sid):
    return [f'{a}:{b}' for a, b in con.execute('SELECT provider_name, channel FROM shop_payment_options WHERE shop_id=?', (sid,))]


def _store_rows(pids, user_lat=None, user_lon=None, shop_ids=None):
    ph = ','.join('?' * len(pids))
    extra, args = '', list(pids)
    if shop_ids:
        extra = f" AND o.shop_id IN ({','.join('?' * len(shop_ids))})"
        args += list(shop_ids)
    rows = con.execute(f'''SELECT o.shop_id, s.name, s.address, s.location_label, s.lat, s.lon, o.offer_id, o.price_toman,
               o.last_price_changed_at, o.warranty_provider, o.warranty_months, o.description, o.product_id
               FROM offers o JOIN shops s USING(shop_id) WHERE o.product_id IN ({ph}) AND o.price_toman IS NOT NULL {extra}
               ORDER BY o.price_toman''', args).fetchall()
    best = {}
    for r in rows:
        if r[0] not in best:
            best[r[0]] = r
    prices = [r[7] for r in best.values()]
    med = statistics.median(prices) if prices else None
    out = []
    for sid, name, addr, label, lat, lon, oid, price, ts, wp, wm, desc, pid in best.values():
        d = _days_old(ts)
        r = {'shop_id': sid, 'shop_name': name, 'address': (addr or '')[:110], 'area': label, 'price_toman': int(price),
             'offer_id': oid, 'price_updated': (ts or '')[:10], 'days_since_update': d, 'stale_price': d is None or d > STALE_DAYS}
        if user_lat is not None and user_lon is not None:
            r['distance_km'] = round(haversine(user_lat, user_lon, lat, lon), 2)
        if med and (price < 0.4 * med or price > 2.5 * med):
            r['suspicious_price'] = 'far from median of other shops – maybe error/different item'
        if wp and wp != 'بدون گارانتی':
            r['warranty'] = f'{wp}' + (f' {wm} ماه' if wm else '')
        pay = _shop_pay(sid)
        if pay:
            r['payment_options'] = pay
        if desc and re.search('اقساط|قسط', desc):
            r['installment_mentioned_in_offer'] = True
        if len(pids) > 1:
            r['product_id'] = pid
        out.append(r)
    return out, med


# ------------------------------------------------------------------ tool 3
def find_stores_for_product(product_id, user_lat=None, user_lon=None, max_distance_km=None, limit=10, sort_by='distance',
                            address_contains=None, require_warranty=False, payment_provider=None):
    pids = product_id if isinstance(product_id, list) else [product_id]
    titles = {r[0]: r[1] for r in con.execute(f"SELECT product_id, persian_title FROM products WHERE product_id IN ({','.join('?'*len(pids))})", pids)}
    if not titles:
        return {'error': 'PRODUCT_NOT_FOUND', 'shops': []}
    rows, med = _store_rows(list(titles), user_lat, user_lon)
    n_all = len(rows)
    has_loc = user_lat is not None and user_lon is not None
    if max_distance_km is not None and has_loc:
        rows = [r for r in rows if r['distance_km'] <= float(max_distance_km)]
    if address_contains:
        k = _addr_key(address_contains)
        rows = [r for r in rows if k in _addr_key(con.execute('SELECT address FROM shops WHERE shop_id=?', (r['shop_id'],)).fetchone()[0])]
    if require_warranty:
        rows = [r for r in rows if 'warranty' in r]
    if payment_provider:
        pk = _addr_key(payment_provider)
        rows = [r for r in rows if any(pk in _addr_key(p) for p in r.get('payment_options', []))]
    note = None
    if sort_by == 'distance' and has_loc:
        rows.sort(key=lambda r: (r['distance_km'], r['price_toman']))
    else:
        if sort_by == 'distance':
            note = 'no user location given – sorted by price'
        rows.sort(key=lambda r: r['price_toman'])
    fresh = [r for r in rows if not r['stale_price'] and 'suspicious_price' not in r]
    out = {'products': titles, 'n_shops_carrying_with_valid_price': n_all, 'n_shops_after_filters': len(rows),
           'median_price': int(med) if med else None, 'shops': rows[:max(1, min(int(limit or 10), 15))]}
    if rows:
        ch = min(rows, key=lambda r: r['price_toman'])
        out['cheapest_after_filters'] = {k: ch[k] for k in ('shop_id', 'shop_name', 'price_toman', 'price_updated', 'stale_price') if k in ch}
        if fresh:
            cf = min(fresh, key=lambda r: r['price_toman'])
            if cf['shop_id'] != ch['shop_id']:
                out['cheapest_fresh_plausible_alternative'] = {k: cf[k] for k in ('shop_id', 'shop_name', 'price_toman', 'price_updated', 'distance_km') if k in cf}
        nw = max(rows, key=lambda r: r['price_updated'])
        out['most_recently_updated'] = {k: nw[k] for k in ('shop_id', 'shop_name', 'price_toman', 'price_updated')}
    else:
        out['note'] = 'NO SHOPS MATCH THESE FILTERS'
    if note:
        out['sort_note'] = note
    return out


# ------------------------------------------------------------------ tool 4
def compare_stores(shop_ids, product_id, user_lat=None, user_lon=None):
    if isinstance(shop_ids, str):
        shop_ids = [shop_ids]
    pids = product_id if isinstance(product_id, list) else [product_id]
    rows, med = _store_rows(pids, user_lat, user_lon, shop_ids=shop_ids)
    rows.sort(key=lambda r: r['price_toman'])
    missing = [s for s in shop_ids if s not in {r['shop_id'] for r in rows}]
    return {'product_ids': pids, 'stores': rows, 'shops_without_valid_offer': missing}


# ------------------------------------------------------------------ tool 5
def check_store_freshness(offer_id=None, product_id=None, shop_id=None):
    if offer_id:
        rows = con.execute('SELECT o.offer_id, o.shop_id, s.name, o.price_toman, o.last_price_changed_at FROM offers o JOIN shops s USING(shop_id) WHERE offer_id=?', (offer_id,)).fetchall()
    elif product_id and shop_id:
        rows = con.execute('SELECT o.offer_id, o.shop_id, s.name, o.price_toman, o.last_price_changed_at FROM offers o JOIN shops s USING(shop_id) WHERE product_id=? AND shop_id=?', (product_id, shop_id)).fetchall()
    elif product_id:
        rows = con.execute('SELECT o.offer_id, o.shop_id, s.name, o.price_toman, o.last_price_changed_at FROM offers o JOIN shops s USING(shop_id) WHERE product_id=? ORDER BY o.last_price_changed_at DESC', (product_id,)).fetchall()
    else:
        return {'error': 'give offer_id, or product_id (+ optional shop_id)'}
    if not rows:
        return {'offers': [], 'note': 'NO OFFERS FOUND'}
    offers = []
    for oid, sid, name, price, ts in rows:
        d = _days_old(ts)
        offers.append({'offer_id': oid, 'shop_id': sid, 'shop_name': name, 'price_toman': int(price) if price else None,
                       'price_updated': (ts or '')[:10], 'days_since_update': d, 'stale': d is None or d > STALE_DAYS})
    out = {'reference_date': '2026-10-22', 'stale_threshold_days': STALE_DAYS, 'n_offers': len(offers)}
    if len(offers) > 1:
        out['n_updated_last_30_days'] = sum(1 for o in offers if o['days_since_update'] is not None and o['days_since_update'] <= 30)
        out['n_stale'] = sum(o['stale'] for o in offers)
        out['newest'] = offers[0]['price_updated']
        out['oldest'] = offers[-1]['price_updated']
    out['offers'] = offers[:30]
    return out


# ------------------------------------------------------------------ tool 6
DAYS = {'sat': 'شنبه', 'sun': 'یکشنبه', 'mon': 'دوشنبه', 'tue': 'سه‌شنبه', 'wed': 'چهارشنبه', 'thu': 'پنجشنبه', 'fri': 'جمعه'}


def _find_shop(shop_id=None, shop_name=None):
    if shop_id:
        r = con.execute('SELECT shop_id FROM shops WHERE shop_id=?', (shop_id,)).fetchone()
        return [r[0]] if r else []
    if shop_name:
        k = _addr_key(shop_name)
        return [r[0] for r in con.execute('SELECT shop_id, name FROM shops') if k and k in _addr_key(r[1])][:5]
    return []


def contact_store(shop_id=None, shop_name=None):
    ids = _find_shop(shop_id, shop_name)
    if not ids:
        return {'shops': [], 'note': 'SHOP NOT FOUND IN DATASET'}
    out = []
    for sid in ids:
        r = con.execute('SELECT name, address, location_label, phone, website_url, instagram, weekly_hours, supports_fast_delivery FROM shops WHERE shop_id=?', (sid,)).fetchone()
        wh = json.loads(r[6]) if r[6] else {}
        hours = {}
        for k, fa in DAYS.items():
            d = wh.get(k)
            if not d:
                continue
            if d.get('status') == 'closed':
                hours[fa] = 'تعطیل'
            else:
                hours[fa] = ', '.join(f"{s.get('start_time','')[:5]}-{s.get('end_time','')[:5]}" for s in d.get('shifts', []))
        out.append({'shop_id': sid, 'name': r[0], 'address': r[1], 'area': r[2],
                    'phone': r[3], 'phone_warning': 'FAKE/SIMULATED number in this demo dataset – not a real contact; user must verify independently',
                    'website': r[4], 'instagram': r[5], 'weekly_hours': hours or 'NOT_RECORDED',
                    'payment_options': _shop_pay(sid) or 'NONE_RECORDED', 'fast_delivery': r[7]})
    return {'shops': out}


# ------------------------------------------------------------------ tool 7 (helper)
def search_stores(name=None, address_contains=None, payment_provider=None, in_person_only=False, sells_category=None,
                  user_lat=None, user_lon=None, limit=10, installment_any=False, _cap=20):
    if installment_any and not payment_provider:
        return _stores_installment(address_contains, in_person_only, sells_category, user_lat, user_lon, limit)
    sql, args = 'SELECT s.shop_id, s.name, s.address, s.location_label, s.lat, s.lon FROM shops s WHERE 1=1', []
    if sells_category:
        sql += ''' AND s.shop_id IN (SELECT o.shop_id FROM offers o JOIN products p USING(product_id)
                   WHERE p.category_name LIKE ? AND o.price_toman IS NOT NULL)'''
        args.append(f'%{sells_category}%')
    if payment_provider or in_person_only:
        sql += ' AND s.shop_id IN (SELECT shop_id FROM shop_payment_options WHERE 1=1'
        if in_person_only:
            sql += " AND channel='in_person'"
        sql += ')'
    rows = con.execute(sql, args).fetchall()
    out = []
    nk = _addr_key(name) if name else None
    ak = _addr_key(address_contains) if address_contains else None
    pk = _addr_key(payment_provider) if payment_provider else None
    for sid, nm, addr, label, lat, lon in rows:
        if nk and nk not in _addr_key(nm):
            continue
        if ak and ak not in _addr_key(addr) and ak not in _addr_key(label or ''):
            continue
        pay = con.execute('SELECT provider_name, channel FROM shop_payment_options WHERE shop_id=?', (sid,)).fetchall()
        if pk:
            pay_m = [p for p in pay if pk in _addr_key(p[0]) and (not in_person_only or p[1] == 'in_person')]
            if not pay_m:
                continue
        r = {'shop_id': sid, 'shop_name': nm, 'address': (addr or '')[:110], 'area': label}
        if sells_category:
            r['n_priced_products_in_category'] = con.execute('''SELECT COUNT(DISTINCT o.product_id) FROM offers o JOIN products p USING(product_id)
                WHERE o.shop_id=? AND p.category_name LIKE ? AND o.price_toman IS NOT NULL''', (sid, f'%{sells_category}%')).fetchone()[0]
        if pay:
            r['payment_options'] = [f'{a}:{b}' for a, b in pay]
        if user_lat is not None and user_lon is not None:
            r['distance_km'] = round(haversine(user_lat, user_lon, lat, lon), 2)
        out.append(r)
    if user_lat is not None and user_lon is not None:
        out.sort(key=lambda r: r['distance_km'])
    res = {'n_matches': len(out), 'shops': out[:max(1, min(int(limit or 10), _cap))]}
    if sells_category:
        res['note'] = f'these shops have at least one priced offer in category "{sells_category}" in the dataset (ground truth from offers, not self-declared categories)'
    if not out:
        res['note'] = 'NO SHOPS MATCH'
    return res


# ---------------------------------------------------------------- discovery / browsing
CAT_SYN = {'لپتاپ': 'لپ تاپ و نوت بوک', 'لپ تاپ': 'لپ تاپ و نوت بوک', 'نوت بوک': 'لپ تاپ و نوت بوک', 'laptop': 'لپ تاپ و نوت بوک',
           'هندزفری': 'هدفون، هدست و هندزفری', 'هدفون': 'هدفون، هدست و هندزفری', 'هدست': 'هدفون، هدست و هندزفری', 'ایرپاد': 'هدفون، هدست و هندزفری',
           'هندزفری بلوتوثی': 'هدفون، هدست و هندزفری', 'ساعت هوشمند': 'ساعت و مچ بند هوشمند', 'مچ بند': 'ساعت و مچ بند هوشمند',
           'گوشی': 'گوشی موبایل', 'موبایل': 'گوشی موبایل', 'تلفن همراه': 'گوشی موبایل', 'کنسول': 'کنسول بازی', 'پلی استیشن': 'کنسول بازی',
           'اسپیکر': 'اسپیکر و سیستم صوتی', 'اسپیکر بلوتوثی': 'اسپیکر و سیستم صوتی', 'بلندگو': 'اسپیکر و سیستم صوتی', 'تلویزیون': 'تلویزیون',
           'بازی': 'دیسک بازی', 'گیم': 'دیسک بازی', 'دسته بازی': 'دسته بازی (گیم پد)', 'گیم پد': 'دسته بازی (گیم پد)'}
USED_WORDS = ('استوک', 'کارکرده', 'اوپن باکس', 'open box', 'دست دوم')


def _resolve_categories(category):
    c = norm(category or '')
    c2 = CAT_SYN.get(c, c)
    rows = con.execute('SELECT category_name, COUNT(*) FROM products WHERE category_name LIKE ? GROUP BY 1 ORDER BY 2 DESC', (f'%{c2}%',)).fetchall()
    starts = [(n, k) for n, k in rows if norm(n).startswith(c2)]
    if starts:          # 'تلویزیون' -> the TV category itself, not 'پایه تلویزیون' / 'میز تلویزیون'
        rows = starts
    wants_acc = any(a in c for a in ('قاب', 'کاور', 'شارژر', 'لوازم', 'کابل'))
    rows = [(n, k) for n, k in rows if wants_acc or not _cat_acc(n, c2.split()[0] if c2 else '')]
    if not rows and c:   # fall back to categories of the best text matches
        hits = search_products_lexical(c, limit=15, _max_limit=15)['results']
        cats = {}
        for h in hits:
            if not any(f.startswith(('ACCESSORY', 'KNOCKOFF')) for f in h.get('flags') or []):
                cats[h['category']] = cats.get(h['category'], 0) + 1
        rows = [(n, con.execute('SELECT COUNT(*) FROM products WHERE category_name=?', (n,)).fetchone()[0])
                for n, _ in sorted(cats.items(), key=lambda x: -x[1])[:3]]
        rows = [(n, k, 'GUESSED') for n, k in rows]
    return rows


def browse_catalog(category=None, brand=None, min_price=None, max_price=None, sort_by='popularity', limit=8, include_used=False,
                   title_contains=None, exclude_basic_phones=False, exclude_brand=None):
    """Browse a whole category (optional brand / price band): brand facets + a short list of genuine items sorted by
    price or popularity. Knock-offs, accessories and (by default) used/stock items excluded.
    Price = plausible cheapest shop price (outliers <0.4x / >2.5x median dropped)."""
    cats = _resolve_categories(category) if category else []
    if category and not cats:
        return {'category_query': category, 'categories_matched': [], 'n_items': 0, 'items': [],
                'note': 'NO CATEGORY MATCHES - nothing in the catalogue for this category'}
    guessed = any(len(c) > 2 for c in cats)
    cats = [c[:2] for c in cats]
    cat_names = [n for n, _ in cats[:4]]
    if not cat_names and not brand:
        return {'error': 'give a category and/or brand'}
    sql = ("SELECT p.product_id, p.persian_title, p.brand_name, p.category_name, o.shop_id, o.price_toman "
           "FROM products p JOIN product_stats s USING(product_id) JOIN offers o USING(product_id) "
           "WHERE s.n_priced > 0 AND o.price_toman IS NOT NULL")
    args = []
    if cat_names:
        sql += ' AND p.category_name IN (%s)' % ','.join('?' * len(cat_names))
        args += cat_names
    per = {}
    for pid, t, b, c, sid, pr in con.execute(sql, args):
        d = per.setdefault(pid, {'title': t, 'brand': b, 'category': c, 'shop_price': {}})
        d['shop_price'][sid] = min(pr, d['shop_price'].get(sid, 1e18))
    bal = None
    if brand:
        bq = norm(brand)
        try:
            import recall as _r
            bal = next((g for g in _r.BRAND_ALIASES if bq in g), [bq])
        except Exception:
            bal = [bq]
    items = []
    for pid, d in per.items():
        tn = norm(d['title'])
        first = ' '.join(tn.split()[:3])
        if 'طرح' in tn.split() or 'های کپی' in tn or 'replica' in tn:
            continue
        if any(first.startswith(w) or f' {w} ' in f' {first} ' for w in ACCESSORY_WORDS) or _cat_acc(d['category'], first):
            continue
        basic = 'گوشی' in tn and ('مگابایت' in tn or 'دکمه' in tn or bool(re.search(r'نوکیا[^|]{0,25}\b[1-3]\d\d\b', tn))
                                  or not re.search(r'(\bرم\b|\bram\b|گیگابایت|\bgb\b|iphone|آیفون|ایفون|galaxy|گلکسی)', tn))   # feature phone
        if exclude_brand:
            xb = norm(exclude_brand)
            try:
                import recall as _r
                xal = next((g for g in _r.BRAND_ALIASES if xb in g), [xb])
            except Exception:
                xal = [xb]
            if any(a in f"{norm(d['brand'] or '')} {tn}" for a in xal if len(a) > 2):
                continue
        flagship = re.search(r'(\bs2\d|iphone|آیفون|ایفون|\bi1\d ?pro|\b1\d ?pro ?max|\b1\d ?air|\b1\d ?mini|pro max mini|\ba\d\d ?mini|ایرپاد|airpods)', tn)
        clone = bool(flagship) and not any(b in tn for b in ('سامسونگ', 'samsung', 'اپل', 'apple', 'گلکسی', 'galaxy', 'آیفون', 'ایفون', 'iphone'))
        if basic and exclude_basic_phones:
            continue
        if title_contains and not all(w in tn for w in norm(title_contains).split()):
            continue
        used = any(w in tn for w in USED_WORDS)
        if used and not include_used:
            continue
        if bal and not any(a in tn for a in bal if len(a) > 1):   # brand must appear in the title (brand_name is sometimes mislabeled on clones)
            continue
        ps = sorted(d['shop_price'].values())
        med = statistics.median(ps)
        pl = [p for p in ps if 0.4 * med <= p <= 2.5 * med]
        lo = pl[0]
        it = {'product_id': pid, 'title': d['title'], 'brand': d['brand'], 'category': d['category'], 'n_shops_priced': len(ps),
              'cheapest_plausible_price': lo, 'median_price': med}
        fl = (['USED_OR_STOCK'] if used else []) + (['BASIC_FEATURE_PHONE (not a smartphone)'] if basic else []) + \
             (['SUSPICIOUS: clone naming (flagship model name on another brand)'] if clone else [])
        if fl:
            it['flags'] = fl
        items.append(it)
    groups = {}   # same brand + model code (e.g. 'سامسونگ'+'s25'): a listing far below its siblings is likely a mislabeled clone
    for it in items:
        for k in set(re.findall(r'[a-z]+\d+[a-z]*|\d+[a-z]+', norm(it['title']))):
            groups.setdefault((it['brand'], k), []).append(it)
    for (b, k), g in groups.items():
        if b and len(g) >= 3:
            m = statistics.median(x['median_price'] for x in g)
            for x in g:
                if x['cheapest_plausible_price'] < 0.35 * m and 'SUSPICIOUS' not in json.dumps(x.get('flags', [])):
                    x.setdefault('flags', []).append(f'SUSPICIOUS: far cheaper than other {b} {k} listings (median {int(m)}) - possibly a clone/mislabeled')
    items = [x for x in items if not any(f.startswith('SUSPICIOUS') for f in x.get('flags', []))] + \
            [x for x in items if any(f.startswith('SUSPICIOUS') for f in x.get('flags', []))]
    items = [x for x in items if not ((min_price and x['cheapest_plausible_price'] < float(min_price)) or (max_price and x['cheapest_plausible_price'] > float(max_price)))]
    facets = {}
    for it in items:
        f = facets.setdefault(it['brand'] or 'نامشخص', {'n_items': 0, 'min_price': 1e18, 'max_price': 0})
        f['n_items'] += 1
        f['min_price'] = min(f['min_price'], it['cheapest_plausible_price'])
        f['max_price'] = max(f['max_price'], it['cheapest_plausible_price'])
    keys = {'price': lambda r: r['cheapest_plausible_price'], 'price_desc': lambda r: -r['cheapest_plausible_price']}
    k0 = keys.get(sort_by, lambda r: (-r['n_shops_priced'], r['cheapest_plausible_price']))
    items.sort(key=lambda r: (any(f.startswith('SUSPICIOUS') for f in r.get('flags', [])), k0(r)))
    lim = max(1, min(int(limit or 8), 12))
    out = {'categories_matched': [{'category': n, 'n_products': k} for n, k in cats[:4]],
           'filters': {k: v for k, v in dict(brand=brand, min_price=min_price, max_price=max_price, sort_by=sort_by).items() if v},
           'n_items': len(items),
           'price_range_all_items': [min(i['cheapest_plausible_price'] for i in items), max(i['cheapest_plausible_price'] for i in items)] if items else None,
           'brands': [{'brand': b, **v} for b, v in sorted(facets.items(), key=lambda x: -x[1]['n_items'])[:15]],
           'items': items[:lim]}
    if guessed:
        out['category_warning'] = 'LOW CONFIDENCE: no category with this name; categories were guessed from text matches - ask the shopper what kind of item they mean'
    out['note'] = (f'showing {min(lim, len(items))} of {len(items)} genuine items; suggest a few, do not dump the list'
                   if items else 'NO ITEMS match these filters')
    return out


BNPL = ('اسنپ‌پی', 'ترب‌پی', 'دیجی پی', 'تارا', 'ازکی‌وام')


def _stores_installment(address_contains, in_person_only, sells_category, user_lat, user_lon, limit):
    # shops offering ANY BNPL/installment provider, with per-provider counts; shops with most in-person providers first
    res = [search_stores(address_contains=address_contains, payment_provider=p, in_person_only=in_person_only,
                         sells_category=sells_category, user_lat=user_lat, user_lon=user_lon, limit=10000, _cap=10000) for p in BNPL]
    counts = {p: r['n_matches'] for p, r in zip(BNPL, res)}
    shops = {}
    for r in res:
        for sh in r['shops']:
            shops[sh['shop_id']] = sh

    def rank(sh):
        po = sh.get('payment_options', [])
        return (sh.get('distance_km', 0), -sum(1 for x in po if x.endswith(':in_person') and x.split(':')[0] in BNPL), -len(po))
    lst = sorted(shops.values(), key=rank)
    return {'n_shops_with_installment': len(lst), 'shops_per_provider': counts,
            'note': 'channel in_person = confirmed at the physical shop; unknown = may be online only. Give a few examples, not the whole list.',
            'shops': lst[:max(1, min(int(limit or 8), 12))]}


TOOLS = {f.__name__: f for f in (search_products, compare_products, find_stores_for_product, compare_stores,
                                  check_store_freshness, contact_store, search_stores, browse_catalog)}
