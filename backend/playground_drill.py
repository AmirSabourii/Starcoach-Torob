"""Drill-down data for the Playground (offers / shop / related products / next-prompt templates).
Pure SQLite + the stored product embeddings (product_emb.f16.npy). NO LLM and NO embedding-API calls: this module
imports no HTTP/LLM client. Every price/date/field comes straight from torob.sqlite."""
import json, os, re, sqlite3, statistics, threading
from datetime import datetime, timezone, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(HERE, 'torob.sqlite')
STALE_DAYS = 30          # same as V3+ (agent_v3plus: B.STALE_DAYS = 30)
SUSPICIOUS_RATIO = 0.4   # same as V3+ (price < 40% of the product's median offer price)
MIN_PRICED_FOR_MEDIAN = 3
TEHRAN = timezone(timedelta(hours=3, minutes=30))
UNKNOWN = 'نامشخص'
OFFER_NOTE = 'پیشنهاد ثبت‌شده؛ موجودی تضمین نیست'
PHONE_NOTE = 'شمارهٔ نمایشی دیتاست، واقعی نیست'
DAYS_FA = [('sat', 'شنبه'), ('sun', 'یکشنبه'), ('mon', 'دوشنبه'), ('tue', 'سه‌شنبه'), ('wed', 'چهارشنبه'), ('thu', 'پنجشنبه'), ('fri', 'جمعه')]

_lock = threading.Lock()
_con = sqlite3.connect(f'file:{DB}?mode=ro', uri=True, check_same_thread=False)
_con.execute('PRAGMA query_only=ON')

def q(sql, args=()):
    with _lock:
        return _con.execute(sql, args).fetchall()

_FA = str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹')
_MONTHS = ['فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد', 'شهریور', 'مهر', 'آبان', 'آذر', 'دی', 'بهمن', 'اسفند']
def jalali(ts):
    try:
        gy, gm, gd = (int(x) for x in str(ts)[:10].split('-'))
    except Exception:
        return None
    g = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2 = gy + 1 if gm > 2 else gy
    d = 355666 + 365 * gy + (gy2 + 3) // 4 - (gy2 + 99) // 100 + (gy2 + 399) // 400 + gd + g[gm - 1]
    jy = -1595 + 33 * (d // 12053); d %= 12053
    jy += 4 * (d // 1461); d %= 1461
    if d > 365:
        jy += (d - 1) // 365; d = (d - 1) % 365
    jm, jd = (1 + d // 31, 1 + d % 31) if d < 186 else (7 + (d - 186) // 30, 1 + (d - 186) % 30)
    return f'{str(jd).translate(_FA)} {_MONTHS[jm - 1]} {str(jy).translate(_FA)}'

def days_ago(ts, now=None):
    if not ts:
        return None
    try:
        t = datetime.fromisoformat(str(ts).replace('Z', '+00:00'))
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        return int(((now or datetime.now(timezone.utc)) - t).total_seconds() // 86400)
    except Exception:
        return None

def _img(js):
    try:
        v = json.loads(js) if js else None
        return v[0] if v else None
    except Exception:
        return None

def _median_of(pid):
    ps = [r[0] for r in q('SELECT price_toman FROM offers WHERE product_id=? AND price_toman IS NOT NULL', (pid,))]
    return (statistics.median(ps) if len(ps) >= MIN_PRICED_FOR_MEDIAN else None), len(ps)

def _label_offer(price, ts, med):
    age = days_ago(ts)
    stale = age is not None and age > STALE_DAYS
    sus = bool(med and price and price < SUSPICIOUS_RATIO * med)
    labels = (['قدیمی'] if stale else []) + (['مشکوک'] if sus else [])
    return age, stale, sus, labels

def fmt_warranty(w):
    if not w:
        return UNKNOWN
    try:
        d = json.loads(w)
    except Exception:
        return str(w)[:80]
    if not isinstance(d, dict):
        return str(w)[:80]
    parts = []
    if d.get('period_months'):
        parts.append(f"{str(d['period_months']).translate(_FA)} ماه")
    if d.get('provider'):
        parts.append(str(d['provider']))
    if d.get('description'):
        parts.append(str(d['description'])[:60])
    return ' '.join(parts) or UNKNOWN

def _sort_key(o):
    # 1) priced, fresh, not suspicious (cheapest first)  2) priced stale  3) suspicious  4) no valid price
    grp = 3 if o['price_toman'] is None else (2 if o['suspicious'] else (1 if o['stale'] else 0))
    return (grp, o['price_toman'] or 0, o['age_days'] if o['age_days'] is not None else 10 ** 6)

def product_head(pid):
    r = q('SELECT product_id,persian_title,brand_name,category_name,model,image_urls FROM products WHERE product_id=?', (pid,))
    if not r:
        return None
    r = r[0]
    return {'product_id': r[0], 'title': r[1] or UNKNOWN, 'brand': r[2] or UNKNOWN, 'category': r[3] or UNKNOWN, 'model': r[4] or None, 'image': _img(r[5])}

def product_offers(pid):
    head = product_head(pid)
    if not head:
        return None
    med, n_priced = _median_of(pid)
    rows = q('''SELECT o.offer_id,o.shop_id,o.price_toman,o.price_status,o.price_toman_raw,o.last_price_changed_at,o.seller_title,o.warranty,
                       s.name,s.location_label,s.address,s.lat,s.lon
                FROM offers o LEFT JOIN shops s ON s.shop_id=o.shop_id WHERE o.product_id=?''', (pid,))
    offers = []
    for (oid, sid, price, pst, raw, ts, stitle, warr, sname, slabel, saddr, slat, slon) in rows:
        age, stale, sus, labels = _label_offer(price, ts, med)
        offers.append({'offer_id': oid, 'shop_id': sid, 'shop_name': sname or UNKNOWN, 'shop_area': slabel or UNKNOWN,
                       'shop_has_address': bool(saddr), 'shop_has_location': slat is not None,
                       'shop_lat': slat if slat is not None else None, 'shop_lon': slon if slon is not None else None,
                       'price_toman': int(price) if price else None,
                       'price_note': None if price else ({'missing': 'قیمت ثبت نشده', 'too_low': 'قیمت نامعتبر (خیلی کم)', 'too_high': 'قیمت نامعتبر (خیلی زیاد)'}.get(pst) or UNKNOWN),
                       'date': (ts or '')[:10] or None, 'date_fa': jalali(ts) if ts else UNKNOWN, 'age_days': age,
                       'stale': stale, 'suspicious': sus, 'labels': labels,
                       'seller_title': stitle or None, 'warranty': fmt_warranty(warr)})
    offers.sort(key=_sort_key)
    fresh = [o for o in offers if o['price_toman'] and not o['stale'] and not o['suspicious']]
    priced = [o for o in offers if o['price_toman']]
    return dict(head, median_price=int(med) if med else None, n_priced=n_priced, n_offers=len(offers),
                n_shops=len({o['shop_id'] for o in offers}), n_stale=sum(o['stale'] for o in offers), n_suspicious=sum(o['suspicious'] for o in offers),
                min_price=min((o['price_toman'] for o in priced), default=None),
                min_fresh_price=fresh[0]['price_toman'] if fresh else None,
                rules={'stale_days': STALE_DAYS, 'suspicious_ratio': SUSPICIOUS_RATIO, 'median_needs_priced_offers': MIN_PRICED_FOR_MEDIAN,
                       'age_reference': 'امروز (' + datetime.now(TEHRAN).strftime('%Y-%m-%d') + ')'},
                note=OFFER_NOTE, offers=offers, llm_calls=0)

def _hours(sid, weekly_json):
    """per-day hours from shop_hours (several shifts per day possible; 00:00–00:00 shift rows are empty placeholders)"""
    rows = {}
    for d, st, a, b in q('SELECT day,status,start_time,end_time FROM shop_hours WHERE shop_id=?', (sid,)):
        rows.setdefault(d, []).append((st, a, b))
    if not rows:
        return None
    today = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'][datetime.now(TEHRAN).weekday()]
    out = []
    for d, fa in DAYS_FA:
        lst = rows.get(d) or []
        shifts = sorted({(a[:5], b[:5]) for st, a, b in lst if st == 'declared' and a and b and not (a[:5] == '00:00' and b[:5] == '00:00')})
        if shifts:
            txt = '، '.join(f'{a} تا {b}' for a, b in shifts).translate(_FA)
        elif lst and all(st == 'closed' for st, _, _ in lst):
            txt = 'تعطیل'
        else:
            txt = UNKNOWN
        out.append({'day': fa, 'hours': txt, 'today': d == today})
    return out

def shop(sid, n_offers=8):
    r = q('''SELECT shop_id,name,address,category_names,phone,instagram,lat,lon,location_label,supports_fast_delivery,website_url,weekly_hours
             FROM shops WHERE shop_id=?''', (sid,))
    if not r:
        return None
    (sid, name, addr, cats, phone, insta, lat, lon, label, fast, web, weekly) = r[0]
    try:
        cats = json.loads(cats) if cats else []
    except Exception:
        cats = []
    pay = [{'provider': p or UNKNOWN, 'channel': {'in_person': 'حضوری', 'online': 'آنلاین'}.get(c, c or UNKNOWN),
            'min_toman': int(a) if a else None, 'max_toman': int(b) if b else None}
           for p, c, a, b in q('SELECT provider_name,channel,min_price_toman,max_price_toman FROM shop_payment_options WHERE shop_id=?', (sid,))]
    cnt = q('SELECT COUNT(*),COUNT(DISTINCT product_id),MAX(last_price_changed_at) FROM offers WHERE shop_id=?', (sid,))[0]
    rows = q('''SELECT o.offer_id,o.product_id,p.persian_title,o.price_toman,o.last_price_changed_at FROM offers o JOIN products p USING(product_id)
                WHERE o.shop_id=? AND o.price_toman IS NOT NULL ORDER BY o.last_price_changed_at DESC LIMIT ?''', (sid, n_offers))
    others = []
    for oid, pid, title, price, ts in rows:
        med, _ = _median_of(pid)
        age, stale, sus, labels = _label_offer(price, ts, med)
        others.append({'offer_id': oid, 'product_id': pid, 'title': title, 'price_toman': int(price), 'date_fa': jalali(ts) if ts else UNKNOWN,
                       'age_days': age, 'labels': labels})
    return {'shop_id': sid, 'name': name or UNKNOWN, 'address': addr or UNKNOWN, 'area': label or UNKNOWN,
            'city': 'تهران' if lat is not None and 35.4 < lat < 36.0 and 51.0 < lon < 51.8 else UNKNOWN,
            'lat': lat, 'lon': lon,
            'map_url': f'https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=17/{lat}/{lon}' if lat is not None and lon is not None else None,
            'hours': _hours(sid, weekly), 'hours_note': 'ساعت ثبت‌شده؛ تعطیلی‌ها لحاظ نشده',
            'categories': cats[:12], 'n_categories': len(cats), 'payment_options': pay,
            'fast_delivery': None if fast is None else bool(fast), 'website': web or None, 'instagram': insta or None,
            'phone_display': phone or None, 'phone_note': PHONE_NOTE if phone else None,
            'n_offers': cnt[0], 'n_products': cnt[1], 'last_price_change_fa': jalali(cnt[2]) if cnt[2] else UNKNOWN,
            'recent_offers': others, 'llm_calls': 0}

# ------------------------------------------------------------------ related products (stored embeddings + same category / model)
_E = {'M': None, 'idx': None}
def _emb():
    if _E['M'] is None:
        import numpy as np
        try:
            import recall as R          # reuse the matrix already loaded by the agents' retrieval (same file, no API)
            M, ids = R._load_emb()
        except Exception:
            M = np.load(os.path.join(HERE, 'product_emb.f16.npy')).astype('float32')
            ids = json.load(open(os.path.join(HERE, 'product_emb_ids.json')))
        _E['M'], _E['idx'] = M, {p: i for i, p in enumerate(ids)}
    return _E['M'], _E['idx']

def price_summary(pid):
    """lowest fresh (≤30 days, not suspicious) price; else the lowest price, labelled"""
    med, _ = _median_of(pid)
    best = None
    for oid, price, ts in q('SELECT offer_id,price_toman,last_price_changed_at FROM offers WHERE product_id=? AND price_toman IS NOT NULL', (pid,)):
        age, stale, sus, labels = _label_offer(price, ts, med)
        cand = {'offer_id': oid, 'price_toman': int(price), 'date_fa': jalali(ts) if ts else UNKNOWN, 'age_days': age, 'labels': labels,
                'fresh': not stale and not sus}
        k = (0 if cand['fresh'] else (1 if not sus else 2), price)
        if best is None or k < best[0]:
            best = (k, cand)
    n = q('SELECT COUNT(*),COUNT(DISTINCT shop_id) FROM offers WHERE product_id=?', (pid,))[0]
    return (best[1] if best else None), n[0], n[1]

def related(seed_ids, exclude=(), k=8):
    import numpy as np
    seeds = [s for s in dict.fromkeys(seed_ids) if s]
    if not seeds:
        return []
    M, idx = _emb()
    excl = set(seeds) | set(exclude)
    heads = [h for h in (product_head(s) for s in seeds[:6]) if h]
    if not heads:
        return []
    cats = list(dict.fromkeys(h['category'] for h in heads if h['category'] != UNKNOWN))
    models = list(dict.fromkeys(h['model'] for h in heads if h['model']))
    cand = set()
    for c in cats[:3]:
        cand |= {r[0] for r in q('''SELECT p.product_id FROM products p JOIN product_stats s USING(product_id)
                                     WHERE p.category_name=? AND s.n_priced>0''', (c,))}
    fam = set()
    for m in models[:3]:
        fam |= {r[0] for r in q('SELECT product_id FROM products WHERE model=? ', (m,))}
    cand |= fam
    cand -= excl
    cand = [c for c in cand if c in idx]
    sidx = [idx[s] for s in seeds if s in idx]
    if not cand or not sidx:
        return []
    S = M[sidx].mean(axis=0)
    S /= (np.linalg.norm(S) or 1.0)
    sims = M[[idx[c] for c in cand]] @ S
    scored = sorted(zip(cand, sims.tolist()), key=lambda x: -(x[1] + (0.05 if x[0] in fam else 0)))
    out, seen_titles = [], {h['title'] for h in heads}
    for pid, sim in scored:
        if len(out) >= k:
            break
        h = product_head(pid)
        if not h or h['title'] in seen_titles:
            continue
        best, n_off, n_shops = price_summary(pid)
        if not best:
            continue
        seen_titles.add(h['title'])
        out.append(dict(h, similarity=round(sim, 3), same_model=pid in fam, price=best, n_offers=n_off, n_shops=n_shops,
                        why='هم‌خانوادهٔ همین مدل' if pid in fam else 'از همین دسته و شبیه'))
    return out

# ------------------------------------------------------------------ next-prompt templates (fallback; grounded in the turn + memory)
_BAD = re.compile(r'زنگ|تماس|بخر|خرید کن|سفارش|رزرو|پرداخت')
def _short(t, n=28):
    t = re.sub(r'\s+', ' ', (t or '').split('|')[0]).strip()
    for p in ('گوشی موبایل ', 'کنسول بازی ', 'لپ تاپ '):
        if t.startswith(p):
            t = t[len(p):]
    return t if len(t) <= n else t[:n].rsplit(' ', 1)[0]

def fa_money(n):
    if not n:
        return None
    if n >= 1_000_000:
        v = n / 1_000_000
        s = (f'{v:.1f}'.rstrip('0').rstrip('.') if v < 10 else str(int(round(v))))
        return s.translate(_FA).replace('.', '٫') + ' میلیون'
    return f'{int(n):,}'.replace(',', '٬').translate(_FA) + ' تومان'

def template_suggestions(products, shops, mem):
    s = []
    if products:
        s.append(f'ارزون‌تر از {_short(products[0].get("title") or products[0].get("name"))} هم هست؟')
        if len(products) >= 2:
            s.append(f'{_short(products[0].get("title") or products[0].get("name"), 20)} یا {_short(products[1].get("title") or products[1].get("name"), 20)}؟ کدوم بهتره')
    area = (mem or {}).get('area')
    if products:
        s.append(f'نزدیک {area} کی داره؟' if area else 'کدوم فروشنده‌ها آدرس حضوری دارن؟')
    if shops:
        s.append(f'ساعت کاری {_short(shops[0]["name"], 22)}؟')
    if not products and not shops:
        b = (mem or {}).get('budget_toman')
        s += ['ارزان‌ترین پلی استیشن ۵', f'یه گوشی خوب تا {fa_money(b) or "۲۰ میلیون"}', 'فروشگاه‌های لپ‌تاپ نزدیک ونک']
    out = []
    for x in s:
        if x and not _BAD.search(x) and x not in out:
            out.append(x)
    return out
