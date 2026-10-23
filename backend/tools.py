"""Read-only, DB-grounded tools for the Torob in-person shopping assistant.
Every tool returns compact JSON-serialisable dicts built only from torob.sqlite rows."""
import json, math, os, re, statistics
from datetime import datetime, timezone
from build_eval_db import norm
from gt_lib import connect, haversine

REF_DATE = datetime(2026, 10, 22, tzinfo=timezone.utc)
STALE_DAYS = 90
con = connect()

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



# ------------------------------------------------------------------ soft attributes (colour / RAM / storage)
# Colour is almost never in titles, RAM/storage only sometimes: they must RANK results, never zero them out.
COLOR_WORDS = ['مشکی', 'سیاه', 'سفید', 'آبی', 'ابی', 'سرمه ای', 'سرمه‌ای', 'قرمز', 'سبز', 'طلایی', 'نقره ای', 'نقره‌ای', 'نقره', 'خاکستری',
               'طوسی', 'صورتی', 'بنفش', 'زرد', 'نارنجی', 'کرم', 'بژ', 'رزگلد', 'رز گلد', 'یاسی', 'گرافیتی', 'black', 'white', 'blue', 'navy',
               'red', 'green', 'gold', 'silver', 'gray', 'grey', 'pink', 'purple', 'yellow', 'orange', 'midnight', 'graphite']
_COLOR_RX = re.compile(r'(^|[\s,،/|(])(?:رنگ\s+)?(' + '|'.join(sorted({re.escape(norm(c)) for c in COLOR_WORDS}, key=len, reverse=True)) + r')(?=$|[\s,،/|)])')


def split_soft_attrs(text):
    """-> (text without colour words, [colour words]). 'رنگ' alone is dropped too."""
    t = norm(text or '')
    found = [m.group(2) for m in _COLOR_RX.finditer(t)]
    t = _COLOR_RX.sub(r'\1', t)
    t = re.sub(r'(^|\s)(رنگ|یا|ترجیحا)(?=\s|$)', ' ', t)
    return re.sub(r'\s+', ' ', t).strip(), found


def _first(pats, t):
    for p in pats:
        m = re.search(p, t)
        if m:
            return m
    return None


def title_specs(tn):
    """best-effort RAM / storage (GB) parsed from normalised text (title or shopper wording); None when not stated."""
    tn = norm(tn or '').replace('گیگابایت', 'گیگ')
    ram = None
    for p in (r'(\d+(?:\.\d+)?)\s*(?:گیگ|gb)\s*(?:رم|ram)\b', r'رمش?\s*(\d+(?:\.\d+)?)', r'\bram\s*(\d+)', r'(\d+(?:\.\d+)?)\s*(?:رم|ram)\b'):
        for m in re.finditer(p, tn):
            if float(m.group(1)) <= 64:          # plausible RAM only
                ram = float(m.group(1)); break
        if ram is not None:
            break
    m = _first([r'حافظه\s*(?:داخلی\s*)?(\d+)\s*(ترابایت|tb)?', r'(\d+)\s*(ترابایت|tb)?\s*(?:گیگ|gb)?\s*(?:ssd|hdd)', r'ظرفیت\s*(\d+)\s*(ترابایت|tb)?',
                r'(\d+)\s*(ترابایت|tb)', r'(\d+)\s*(?:گیگ|gb)?\s*()(?:حافظه)'], tn)
    sto = float(m.group(1)) * (1024 if m.group(2) else 1) if m else None
    if re.search(r'(لپ ?تاپ|نوت ?بوک|laptop)', tn) and ram is None and sto is not None and sto <= 32:   # laptops: «حافظه 8 گیگ» = RAM
        ram = sto
        m = re.search(r'(\d+)\s*(ترابایت|tb)?\s*(?:گیگ|gb)?\s*(?:ssd|hdd)', tn)
        sto = float(m.group(1)) * (1024 if m.group(2) else 1) if m else None
    if sto is None:
        for m in re.finditer(r'(\d+)\s*(?:گیگ|gb)\b', tn):
            v = float(m.group(1))
            if v >= 32 and v != ram:
                sto = v; break
    if ram is not None and ram == sto:
        ram = None
    return ram, sto


PREF_FILLER = set('با و باشه بهتره یا حداقل ترجیحا مناسب برای خوب بالا زیاد کم نرخ تازه سازی نوسازی کار کاربری برنامه نویسی '
                  'درس دانشگاه ورزش مامان بچه حرفه ای حرفه‌ای عالی قوی'.split())


def parse_prefer(text):
    """free-text preference -> {'colors': [...], 'min_ram_gb': n, 'min_storage_gb': n, 'terms': [...]}"""
    rest, colors = split_soft_attrs(text)
    out = {'colors': colors}
    ram, sto = title_specs(rest)
    if ram:
        out['min_ram_gb'] = ram
    if sto:
        out['min_storage_gb'] = sto
    rest = re.sub(r'\d+(\.\d+)?|رمش|رم|ram|حافظه|ظرفیت|داخلی|گیگابایت|گیگ|gb|ترابایت|tb|ssd|hdd', ' ', rest)
    rest = re.sub(r'[،,;:!?؟()«»"]', ' ', rest)
    out['terms'] = [t for t in rest.split() if len(t) > 1 and t not in PREF_FILLER]
    return out


def pref_score(tn, pref):
    """(n preference parts met, n parts unknown/not stated in title)"""
    met = unk = 0
    if pref.get('colors'):
        if any(c in tn for c in pref['colors']):
            met += 1
        else:
            unk += 1
    ram, sto = title_specs(tn)
    for want, have in ((pref.get('min_ram_gb'), ram), (pref.get('min_storage_gb'), sto)):
        if want:
            if have is None:
                unk += 1
            elif have >= want:
                met += 1
    for t in pref.get('terms', []):
        met += any(a in tn for a in SYN.get(t, [t]))
    return met, unk


# ------------------------------------------------------------------ Tehran areas
# coarse regions (by coordinates) + approximate centres of well-known neighbourhoods; anything else = address/label text match
REGIONS = {'غرب': lambda la, lo: lo < 51.36, 'شرق': lambda la, lo: lo > 51.46, 'شمال': lambda la, lo: la > 35.76,
           'جنوب': lambda la, lo: la < 35.67, 'مرکز': lambda la, lo: 35.67 <= la <= 35.73 and 51.38 <= lo <= 51.45}
REGION_CENTRE = {'غرب': (35.735, 51.31), 'شرق': (35.725, 51.50), 'شمال': (35.79, 51.42), 'جنوب': (35.64, 51.42), 'مرکز': (35.695, 51.415)}
PLACES = {'تجریش': (35.804, 51.434), 'ونک': (35.757, 51.410), 'صادقیه': (35.718, 51.336), 'جنت اباد': (35.752, 51.303),
          'پونک': (35.761, 51.333), 'سعادت اباد': (35.780, 51.375), 'شهرک غرب': (35.758, 51.370), 'ستارخان': (35.712, 51.355),
          'ازادی': (35.700, 51.338), 'انقلاب': (35.701, 51.391), 'بهارستان': (35.692, 51.432), 'هفت تیر': (35.716, 51.426), 'تهرانپارس': (35.734, 51.540),
          'تهران پارس': (35.734, 51.540), 'نارمک': (35.742, 51.500), 'پیروزی': (35.692, 51.470), 'نازی اباد': (35.643, 51.402),
          'اکباتان': (35.708, 51.307), 'میرداماد': (35.760, 51.430), 'پاسداران': (35.770, 51.470), 'الهیه': (35.788, 51.425),
          'شهر ری': (35.590, 51.435), 'باغ فیض': (35.740, 51.316)}
PLACE_RADIUS_KM = 2.5


def resolve_area(text):
    """-> dict(kind=region|place|text, label, centre, test(addr,label,lat,lon)->bool)"""
    k = _addr_key(text).replace('آ', 'ا')
    plain = norm(text or '').replace('آ', 'ا')
    regs = [r for r in REGIONS if r in plain]
    rest = plain
    for w in ('تهران', 'محدوده', 'منطقه', 'سمت', 'شهر', 'نزدیک', 'حوالی', 'دور و بر', 'همین', 'های', 'ی'):
        rest = rest.replace(w, '')
    if regs and (len(_addr_key(rest))
                 <= sum(len(r) for r in regs) + 2):
        c = tuple(sum(REGION_CENTRE[r][i] for r in regs) / len(regs) for i in (0, 1))
        return {'kind': 'region', 'label': ' '.join(regs) + ' تهران', 'centre': c,
                'test': lambda a, l, la, lo: la is not None and all(REGIONS[r](la, lo) for r in regs)}
    for name, c in PLACES.items():
        left = plain.replace(name.replace('آ', 'ا'), '')
        for w in ('تهران', 'محدوده', 'منطقه', 'سمت', 'نزدیک', 'حوالی', 'اطراف', 'دور و بر', 'همین', 'خیابان', 'میدان', 'محله', 'بازار', 'شهرک'):
            left = left.replace(w, '')
        if _addr_key(name) and _addr_key(name) in k and len(_addr_key(left)) <= 3:   # only a bare place name; «مجتمع ... فردوسی» stays literal
            nk = _addr_key(name)
            return {'kind': 'place', 'label': name, 'centre': c,
                    'test': lambda a, l, la, lo, nk=nk, c=c: (la is not None and haversine(c[0], c[1], la, lo) <= PLACE_RADIUS_KM)
                    or nk in _addr_key(a).replace('ا', 'ا') or nk in _addr_key(l)}
    return {'kind': 'text', 'label': text, 'centre': None,
            'test': lambda a, l, la, lo: k in _addr_key(a).replace('آ', 'ا') or k in _addr_key(l).replace('آ', 'ا')}


_SHOP_GEO = None


def _shop_geo(sid):
    global _SHOP_GEO
    if _SHOP_GEO is None:
        _SHOP_GEO = {r[0]: (r[1] or '', r[2] or '', r[3], r[4]) for r in con.execute('SELECT shop_id, address, location_label, lat, lon FROM shops')}
    return _SHOP_GEO.get(sid, ('', '', None, None))


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
    cat_allowed = resolved_category_names(category) if category else None
    scored = []
    for pid, bm in cands.items():
        p = con.execute('SELECT p.persian_title, p.title_norm, p.brand_name, p.category_name, s.n_shops, s.n_priced FROM products p JOIN product_stats s USING(product_id) WHERE product_id=?', (pid,)).fetchone()
        title, tn, br, cat, n_shops, n_priced = p
        tn = tn or ''
        if brand and norm(brand) not in norm(br or '') and not any(a in tn for a in SYN.get(norm(brand), [norm(brand)])):
            continue
        if cat_allowed and cat not in cat_allowed:
            continue   # category filter = resolved category names, not any category containing the word
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
    # colour is a SOFT attribute (almost never in titles): search without it, then rank colour hits first
    q2, colors = split_soft_attrs(query)
    q2 = q2 or query
    if USE_RECALL_LAYER:
        from recall import search_products_hybrid
        out = search_products_hybrid(q2, brand=brand, category=category, min_price=min_price, max_price=max_price, limit=limit)
    else:
        out = search_products_lexical(q2, brand=brand, category=category, min_price=min_price, max_price=max_price, limit=limit)
    if (min_price is not None or max_price is not None) and not out.get('results'):
        alt = search_products(query, brand=brand, category=category, limit=limit)   # same search without the price band
        if alt.get('results'):
            for r in alt['results']:
                r['outside_requested_price_range'] = True
            alt['price_note'] = (f'the item EXISTS in the catalogue but has NO offer within the requested price range '
                                 f'({min_price or 0:,.0f}-{max_price or 0:,.0f}); these are its real prices. Say it exists but is outside the budget, '
                                 f'give the real cheapest price, and optionally suggest in-budget alternatives via browse_catalog. Never say the item is not in the data.')
            alt['filters_requested'] = {k: v for k, v in dict(min_price=min_price, max_price=max_price).items() if v is not None}
            return alt
    if colors:
        out['results'].sort(key=lambda r: not any(c in norm(r.get('title') or '') for c in colors))
        out['soft_attributes_not_filtered'] = colors
        out['soft_attribute_note'] = ('colour is NOT a filter: titles rarely record colour. Present these real matches; say the colour is '
                                      'not recorded in the data and must be confirmed with the shop. Never answer "nothing found" because of colour.')
    return out


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
                            address_contains=None, require_warranty=False, payment_provider=None, area=None):
    pids = product_id if isinstance(product_id, list) else [product_id]
    ar = None
    if area or address_contains:
        ar = resolve_area(area or address_contains)
        if ar['kind'] == 'text' and not area:
            ar = None                      # plain address text (mall / street): keep the literal address filter below
        else:
            address_contains = None
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
    area_note = None
    if ar:
        rows = [r for r in rows if ar['test'](*_shop_geo(r['shop_id']))]
        if ar['centre'] and not has_loc:
            for r in rows:
                g = _shop_geo(r['shop_id'])
                r['distance_from_area_centre_km'] = round(haversine(ar['centre'][0], ar['centre'][1], g[2], g[3]), 2)
            if sort_by == 'distance':
                rows.sort(key=lambda r: (r['distance_from_area_centre_km'], r['price_toman']))
        area_note = f"area filter «{ar['label']}» ({ar['kind']}): {len(rows)} of {n_all} shops"
    if require_warranty:
        rows = [r for r in rows if 'warranty' in r]
    if payment_provider:
        pk = _addr_key(payment_provider)
        rows = [r for r in rows if any(pk in _addr_key(p) for p in r.get('payment_options', []))]
    note = None
    if sort_by == 'distance' and has_loc:
        rows.sort(key=lambda r: (r['distance_km'], r['price_toman']))
    elif not (ar and ar['centre'] and sort_by == 'distance'):
        if sort_by == 'distance':
            note = 'no user location given – sorted by price'
        rows.sort(key=lambda r: r['price_toman'])
    fresh = [r for r in rows if not r['stale_price'] and 'suspicious_price' not in r]
    out = {'products': titles, 'n_shops_carrying_with_valid_price': n_all, 'n_shops_after_filters': len(rows),
           **({'unknown_product_ids_ignored': [p for p in pids if p not in titles]} if len(titles) < len(pids) else {}),
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
    if area_note:
        out['area_note'] = area_note
        if not rows and n_all:
            out['note'] = f'NO SHOPS IN «{ar["label"]}» carry it; {n_all} shops elsewhere do - offer the nearest/cheapest of those instead of saying it is unavailable'
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
                  user_lat=None, user_lon=None, limit=10, installment_any=False, _cap=20, area=None):
    if installment_any and not payment_provider:
        return _stores_installment(area or address_contains, in_person_only, sells_category, user_lat, user_lon, limit)
    ar = resolve_area(area or address_contains) if (area or address_contains) else None
    if ar and ar['kind'] == 'text' and not area:
        ar = None
    if ar:
        address_contains = None
    ref = (user_lat, user_lon) if user_lat is not None and user_lon is not None else (ar['centre'] if ar and ar['centre'] else None)
    sql, args = 'SELECT s.shop_id, s.name, s.address, s.location_label, s.lat, s.lon FROM shops s WHERE 1=1', []
    if sells_category:
        sc_names = resolved_category_names(sells_category)
        sc_sql = ('p.category_name IN (%s)' % ','.join('?' * len(sc_names))) if sc_names else 'p.category_name LIKE ?'
        sc_args = sorted(sc_names) if sc_names else [f'%{sells_category}%']
        sql += f''' AND s.shop_id IN (SELECT o.shop_id FROM offers o JOIN products p USING(product_id)
                   WHERE {sc_sql} AND o.price_toman IS NOT NULL)'''
        args += sc_args
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
        if ar and not ar['test'](addr or '', label or '', lat, lon):
            continue
        pay = con.execute('SELECT provider_name, channel FROM shop_payment_options WHERE shop_id=?', (sid,)).fetchall()
        if pk:
            pay_m = [p for p in pay if pk in _addr_key(p[0]) and (not in_person_only or p[1] == 'in_person')]
            if not pay_m:
                continue
        r = {'shop_id': sid, 'shop_name': nm, 'address': (addr or '')[:110], 'area': label}
        if sells_category:
            r['n_priced_products_in_category'] = con.execute(f'''SELECT COUNT(DISTINCT o.product_id) FROM offers o JOIN products p USING(product_id)
                WHERE o.shop_id=? AND {sc_sql} AND o.price_toman IS NOT NULL''', [sid] + sc_args).fetchone()[0]
        if pay:
            r['payment_options'] = [f'{a}:{b}' for a, b in pay]
        if ref:
            r['distance_km' if ref == (user_lat, user_lon) else 'distance_from_area_centre_km'] = round(haversine(ref[0], ref[1], lat, lon), 2)
        out.append(r)
    if ref:
        out.sort(key=lambda r: r.get('distance_km', r.get('distance_from_area_centre_km')))
    res = {'n_matches': len(out), 'shops': out[:max(1, min(int(limit or 10), _cap))]}
    if ar:
        res['area_note'] = f"area «{ar['label']}» resolved as {ar['kind']}" + (' (by shop coordinates)' if ar['kind'] != 'text' else ' (address text)')
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


# qualifiers that turn a generic category word into a DIFFERENT product class / an accessory class
# ('مانیتور' vs 'مانیتور آیفون تصویری' / 'مانیتور خودرو' / 'پایه نگهدارنده مانیتور'). Such categories are only merged
# into a generic request when the shopper's own words contain the qualifier.
OTHER_CLASS_QUALIFIERS = ['خودرو', 'موتور سیکلت', 'آیفون تصویری', 'کنترل کودک', 'اسباب بازی', 'پایه', 'نگهدارنده',
                          'قاب', 'کاور', 'کیف', 'محافظ', 'گلس', 'لوازم جانبی', 'قطعات', 'قطعه', 'صنعتی', 'ویدیو وال', 'آینه', 'میز',
                          'شارژر', 'کابل', 'باتری', 'برچسب', 'استیکر', 'سایر', 'تعمیر', 'فروشگاهی', 'آنتن', 'پنل پخش']
CAT_EXACT_DOMINANT = 1.0   # an exact-name category at least as large as every remaining sibling is used alone


def _sq(s):
    return re.sub(r'\s+', ' ', norm(s or '')).strip()


def _other_class(cat_name, user_text):
    n = ' %s ' % re.sub(r'[،,()\-]', ' ', _sq(cat_name))
    u = ' %s ' % user_text
    return any(f' {q} ' in n and f' {q} ' not in u for q in OTHER_CLASS_QUALIFIERS)   # whole-word match


def _resolve_categories(category, _depth=0):
    """map the shopper's category words to category_name values.
    Preference order: (a) EXACT category name (used alone when it is a substantial category),
    (b) categories whose name STARTS with the term (head word), (c) any category containing it;
    categories that are a different product class / accessory class (OTHER_CLASS_QUALIFIERS) are dropped unless the
    shopper asked for that qualifier. Multi-word phrases with no category ('مانیتور گیمینگ') fall back to their head words
    before guessing from text hits."""
    c = _sq(category)
    c2 = _sq(CAT_SYN.get(c, c))
    if not c2:
        return []
    rows = [tuple(r) for r in con.execute('SELECT category_name, COUNT(*) FROM products WHERE category_name LIKE ? GROUP BY 1 ORDER BY 2 DESC', (f'%{c2}%',)).fetchall()]
    rows += [tuple(r) for r in con.execute('SELECT category_name, COUNT(*) FROM products WHERE category_name LIKE ? GROUP BY 1 ORDER BY 2 DESC',
                                           (f'%{c2.replace(" ", "%")}%',)).fetchall() if r[0] not in {x[0] for x in rows}] if ' ' in c2 else []
    wants_acc = any(a in c for a in ('قاب', 'کاور', 'شارژر', 'لوازم', 'کابل'))
    user_text = f'{c} {c2}'
    exact = [(n, k) for n, k in rows if _sq(n) == c2]
    starts = [(n, k) for n, k in rows if _sq(n).startswith(c2)]
    if starts:          # 'تلویزیون' -> the TV category itself, not 'پایه تلویزیون' / 'میز تلویزیون'
        rows = starts
    rows = [(n, k) for n, k in rows if wants_acc or not _cat_acc(n, c2.split()[0])]
    clean = [(n, k) for n, k in rows if not _other_class(n, user_text)]
    if clean or exact:
        rows = clean or exact
    if exact:
        biggest = max([k for n, k in rows if n != exact[0][0]] or [0])
        if exact[0][1] >= CAT_EXACT_DOMINANT * biggest:
            return exact                    # 'مانیتور' -> only the computer-monitor category
        rows = exact + [r for r in rows if r[0] != exact[0][0]]   # tiny exact category ('یخچال', 6) + its real siblings
    if rows:
        return rows
    words = c.split()
    if len(words) > 1 and _depth == 0:   # 'مانیتور گیمینگ' / 'مانیتور 27 اینچ' -> head words
        for k in range(len(words) - 1, 0, -1):
            sub = _resolve_categories(' '.join(words[:k]), _depth=1)
            if sub and not any(len(s) > 2 for s in sub):
                return sub
    if c:   # fall back to categories of the best text matches
        hits = search_products_lexical(c, limit=15, _max_limit=15)['results']
        cats = {}
        for h in hits:
            if not any(f.startswith(('ACCESSORY', 'KNOCKOFF')) for f in h.get('flags') or []) and not _other_class(h['category'], user_text):
                cats[h['category']] = cats.get(h['category'], 0) + 1
        rows = [(n, con.execute('SELECT COUNT(*) FROM products WHERE category_name=?', (n,)).fetchone()[0])
                for n, _ in sorted(cats.items(), key=lambda x: -x[1])[:3]]
        rows = [(n, k, 'GUESSED') for n, k in rows]
    return rows


_CAT_CACHE = {}
def resolved_category_names(category):
    """set of confidently-resolved category_name values for a category filter (None = no confident match)"""
    key = _sq(category)
    if key not in _CAT_CACHE:
        rows = _resolve_categories(category) if key else []
        _CAT_CACHE[key] = None if (not rows or any(len(r) > 2 for r in rows)) else {r[0] for r in rows[:6]}
    return _CAT_CACHE[key]


def _title_terms(text):
    """alias-aware hard title terms: each term = list of alternatives (any must appear)"""
    try:
        from recall import PHRASES
    except Exception:
        PHRASES = []
    t = norm(text or '')
    for pat, rep in PHRASES:
        t = re.sub(pat, rep, t)
    return [SYN.get(w, [w]) + ([w.replace('ps', 'پلی استیشن ')] if w.startswith('ps') else []) for w in t.split()]


def browse_catalog(category=None, brand=None, min_price=None, max_price=None, sort_by='popularity', limit=8, include_used=False,
                   title_contains=None, exclude_basic_phones=False, exclude_brand=None, prefer=None):
    """title_contains = hard, alias-aware, auto-relaxed if it matches nothing; colour words in it are moved to `prefer`.
    prefer = SOFT preferences (colour, «رم 16», «حافظه 256», extra words): rank matching items first, never filter."""
    soft = []
    if title_contains:
        title_contains, cols = split_soft_attrs(title_contains)
        pt = parse_prefer(title_contains)
        if pt.get('min_ram_gb') or pt.get('min_storage_gb'):   # specs are soft too
            soft.append(title_contains); title_contains = ' '.join(pt['terms'])
        soft += cols
    if prefer:
        soft.append(prefer)
    if category:   # 'مانیتور گیمینگ' resolved via its head word 'مانیتور': the extra words become soft preferences
        cw = _sq(category).split()
        if (len(cw) > 1 and _sq(CAT_SYN.get(_sq(category), category)) == _sq(category)
                and not con.execute('SELECT 1 FROM products WHERE category_name LIKE ? LIMIT 1', (f'%{_sq(category)}%',)).fetchone()):
            head = next((k for k in range(len(cw) - 1, 0, -1) if _resolve_categories(' '.join(cw[:k]), _depth=1)
                         and _resolve_categories(' '.join(cw[:k]), _depth=1) == _resolve_categories(category)), None)
            if head and not any(_sq(n) == _sq(category) for n, *_ in _resolve_categories(category)):
                soft.append(' '.join(cw[head:]))
    pref = parse_prefer(' '.join(soft)) if soft else None
    res = _browse(category, brand, min_price, max_price, sort_by, limit, include_used, title_contains, exclude_basic_phones, exclude_brand, pref)
    if title_contains and not res.get('n_items') and not res.get('error'):
        res2 = _browse(category, brand, min_price, max_price, sort_by, limit, include_used, None, exclude_basic_phones, exclude_brand, pref)
        if res2.get('n_items'):
            res2['title_filter_relaxed'] = (f'no item title contains «{title_contains}», so that filter was dropped; these are the other '
                                            f'items matching the remaining filters - say the attribute is not recorded and must be checked in-store')
            res = res2
    if pref and (pref.get('min_ram_gb') or pref.get('min_storage_gb')) and res.get('n_items') and not res.get('n_items_matching_preference') and max_price:
        sp = {k: v for k, v in pref.items() if k in ('min_ram_gb', 'min_storage_gb')}
        up = _browse(category, brand, max_price, None, 'price', 12, include_used, title_contains, exclude_basic_phones, exclude_brand, sp)
        meet = [i for i in up.get('items', []) if i.get('matches_preference') and not i.get('flags')][:3]
        if meet:
            res['cheapest_meeting_spec_above_budget'] = meet
            res['spec_note'] = 'no item within budget states the requested RAM/storage; these are the cheapest that do (ABOVE budget) - mention them, labelled'
    if max_price and res.get('n_items', 0) < 3 and not res.get('error'):
        up = _browse(category, brand, max_price, None, 'price', 3, include_used, title_contains, exclude_basic_phones, exclude_brand, pref)
        above = [i for i in up.get('items', []) if i['cheapest_plausible_price'] > float(max_price)][:3]
        if above:
            res['just_above_budget'] = above
            res['just_above_budget_note'] = 'few/no items within budget: you may mention these cheapest ones ABOVE the budget, clearly labelled'
    return res


def _browse(category, brand, min_price, max_price, sort_by, limit, include_used, title_contains, exclude_basic_phones, exclude_brand, pref):
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
        basic = bool(re.search(r'(نوکیا|nokia)\s*\d{3,4}\b', tn)) or 'گوشی' in tn and ('مگابایت' in tn or 'دکمه' in tn or bool(re.search(r'نوکیا[^|]{0,25}\b[1-3]\d\d\b', tn))
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
        if title_contains and not all(any(a in tn for a in alts) for alts in _title_terms(title_contains)):
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
        if re.search(r'(مینی|mini)\s*(ps\d|پلی ?استیشن|xbox|ایکس ?باکس)|(ps\d|xbox)\s*(pro\d|mini|مینی)', tn):
            clone = True   # miniature knock-off consoles
        if pref:
            it_pref = pref_score(tn, pref)
        fl = (['USED_OR_STOCK'] if used else []) + (['BASIC_FEATURE_PHONE (not a smartphone)'] if basic else []) + \
             (['SUSPICIOUS: clone naming (flagship model name on another brand)'] if clone else [])
        if fl:
            it['flags'] = fl
        if pref:
            it['_pm'] = it_pref[0]
            if it_pref[0]:
                it['matches_preference'] = True
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
    items.sort(key=lambda r: (any(f.startswith('SUSPICIOUS') for f in r.get('flags', [])), -r.get('_pm', 0), k0(r)))
    n_pref = sum(1 for i in items if i.get('_pm'))
    for i in items:
        i.pop('_pm', None)
    lim = max(1, min(int(limit or 8), 12))
    out = {'categories_matched': [{'category': n, 'n_products': k} for n, k in cats[:4]],
           'filters': {k: v for k, v in dict(brand=brand, min_price=min_price, max_price=max_price, sort_by=sort_by).items() if v},
           'n_items': len(items),
           'price_range_all_items': [min(i['cheapest_plausible_price'] for i in items), max(i['cheapest_plausible_price'] for i in items)] if items else None,
           'brands': [{'brand': b, **v} for b, v in sorted(facets.items(), key=lambda x: -x[1]['n_items'])[:15]],
           'items': items[:lim]}
    if pref:
        p = {k: v for k, v in pref.items() if v}
        out['soft_preferences'] = p
        out['n_items_matching_preference'] = n_pref
        out['preference_note'] = ('preferences only RANK items (matches first), they never remove items. '
                                  + ('Colour is almost never in titles: say it is not recorded and must be confirmed in-store. ' if p.get('colors') else '')
                                  + ('RAM/storage parsed from titles; items without the spec in the title are not excluded. ' if (p.get('min_ram_gb') or p.get('min_storage_gb')) else '')
                                  + ('NO item states this preference - say so plainly, then present the real items.' if not n_pref else ''))
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
