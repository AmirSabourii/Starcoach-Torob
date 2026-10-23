"""Torob shopping assistant v3 — AI-first. One loop, 3 general tools (sql, text_search, geocode_area).
The model explores the DB like an analyst; the server only hydrates the ids it returns (the single grounding guard).
API: run_agent_v3(messages_or_question, session_mission=None, user_lat=None, user_lon=None)
     -> {text, blocks, mission, usage, tool_trace, hydration_log}"""
import json, math, os, re, sqlite3, statistics, time
from datetime import datetime, timezone, timedelta
from build_eval_db import norm
import tools as T          # existing tools: kept untouched; reused for normalisation, places, flags
import recall as R         # existing retrieval (aliases/fuzzy + FTS + embeddings)

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(HERE, 'torob.sqlite')
MODEL = 'gpt-6-luna'
MAX_STEPS = 8
LLM_TIMEOUT = 25
MAX_COMPLETION_TOKENS = 1000
SQL_TIMEOUT_S = 3.0
EMBED_TIMEOUT_S = 5.0      # embeddings call inside text_search: own client, no retries; on failure -> FTS/alias layers only
LLM_STEP_TIMEOUT_S = 12.0  # one exploring LLM call (normally 2-5s); a hung call leaves ~17s for the agent.py fallback
TURN_SOFT_S = 18.0         # past this, stop exploring: one forced final-answer step with what we have
TURN_FINAL_BY_S = 26.0     # the forced final step must finish by here
TURN_BUDGET_S = 29.5       # hard wall-clock cap for the whole turn, agent.py fallback included
STALE_DAYS = 60            # offer price older than this -> stale
SUSPICIOUS_RATIO = 0.5     # offer price < this x product median (>=3 priced offers) -> suspicious_low
TEHRAN = timezone(timedelta(hours=3, minutes=30))
COST = {'llm': 0.0, 'embed': 0.0}           # process-wide running totals (USD)

_client = None
def client():
    global _client
    if _client is None:
        from openai import OpenAI
        _client = OpenAI(api_key=os.environ['BOXAPI_API_KEY'], base_url='https://ai.boxapi.ir/ai/v1', timeout=LLM_TIMEOUT, max_retries=0)
    return _client

_eclient = None
def embed_client():
    global _eclient
    if _eclient is None:
        from openai import OpenAI
        _eclient = OpenAI(api_key=os.environ['BOXAPI_API_KEY'], base_url='https://ai.boxapi.ir/ai/v1', timeout=EMBED_TIMEOUT_S, max_retries=0)
    return _eclient


# ------------------------------------------------------------------ SQL functions
def _km(a, b, c, d):
    if None in (a, b, c, d):
        return None
    return T.haversine(a, b, c, d)

def _days_ago(ts):
    if not ts:
        return None
    try:
        t = datetime.fromisoformat(str(ts).replace('Z', '+00:00'))
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        return round((datetime.now(timezone.utc) - t).total_seconds() / 86400, 1)
    except Exception:
        return None

_FA_MONTHS = ['فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد', 'شهریور', 'مهر', 'آبان', 'آذر', 'دی', 'بهمن', 'اسفند']
def _fa_digits(x):
    return str(x).translate(str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹'))

def _jalali(ts):
    """ISO timestamp/date -> '۱۹ مهر ۱۴۰۵' (deterministic; the model must not convert calendars itself)"""
    try:
        gy, gm, gd = (int(x) for x in str(ts)[:10].split('-'))
    except Exception:
        return None
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2 = gy + 1 if gm > 2 else gy
    days = 355666 + 365 * gy + (gy2 + 3) // 4 - (gy2 + 99) // 100 + (gy2 + 399) // 400 + gd + g_d_m[gm - 1]
    jy = -1595 + 33 * (days // 12053); days %= 12053
    jy += 4 * (days // 1461); days %= 1461
    if days > 365:
        jy += (days - 1) // 365; days = (days - 1) % 365
    jm, jd = (1 + days // 31, 1 + days % 31) if days < 186 else (7 + (days - 186) // 30, 1 + (days - 186) % 30)
    return f'{_fa_digits(jd)} {_FA_MONTHS[jm - 1]} {_fa_digits(jy)}'

def _norm_fa(s):
    return norm(s) if s is not None else None

class _Median:
    def __init__(self): self.v = []
    def step(self, x):
        if x is not None: self.v.append(x)
    def inverse(self, x):
        if x is not None: self.v.remove(x)
    def value(self): return statistics.median(self.v) if self.v else None
    def finalize(self): return self.value()

def ro_connect():
    con = sqlite3.connect(f'file:{DB}?mode=ro', uri=True, timeout=SQL_TIMEOUT_S, check_same_thread=False)
    con.execute('PRAGMA query_only=ON')
    con.create_function('km', 4, _km, deterministic=True)
    con.create_function('norm_fa', 1, _norm_fa, deterministic=True)
    con.create_function('days_ago', 1, _days_ago)
    con.create_function('jalali', 1, _jalali, deterministic=True)
    con.create_window_function('median', 1, _Median)   # works as plain aggregate and as OVER(...) window
    return con

RO = ro_connect()
_WRITE_RX = re.compile(r'\b(insert|update|delete|drop|alter|create|replace|attach|detach|pragma|vacuum|reindex)\b', re.I)


def tool_sql(query):
    q = (query or '').strip().rstrip(';').strip()
    if not re.match(r'^(select|with)\b', q, re.I) or ';' in q or _WRITE_RX.search(re.sub(r"'[^']*'", "''", q)):
        return {'error': 'only a single read-only SELECT/WITH statement is allowed'}
    if not re.search(r'\blimit\s+\d+', q, re.I):
        q += '\nLIMIT 50'
    t0 = time.time()
    RO.set_progress_handler(lambda: 1 if time.time() - t0 > SQL_TIMEOUT_S else 0, 20000)
    try:
        cur = RO.execute(q)
        cols = [d[0] for d in cur.description or []]
        rows = cur.fetchmany(50)
    except Exception as e:
        msg = str(e)
        return {'error': ('query timed out (>3s): add selective WHERE/use text_search ids' if 'interrupt' in msg else msg)[:300]}
    finally:
        RO.set_progress_handler(None, 0)
    def cell(v):
        if isinstance(v, float):
            return round(v, 3) if abs(v) < 1000 else int(v)
        if isinstance(v, str) and len(v) > 110:
            return v[:110] + '…'
        return v
    res = {'columns': cols, 'row_count': len(rows), 'rows': [[cell(v) for v in r] for r in rows],
           'ms': int((time.time() - t0) * 1000)}
    oc = [i for i, c in enumerate(cols) if c.lower() in ('offer_id', 'oid')]
    if oc:   # server-side flags the model must mention when it quotes such an offer
        flags = {}
        for r in rows:
            v = r[oc[0]]
            if isinstance(v, str) and v.startswith('offer_'):
                f = _offer_flags(v)
                if f and (f.get('stale') or f.get('suspicious_low')):
                    flags[v] = f
        if flags:
            res['offer_flags'] = flags
    return res


# ------------------------------------------------------------------ text_search (the one retrieval layer)
SEARCH_LAYERS = {'alias': True, 'embed': True, 'llm_expand': False, 'grader': False}

def _pstats(pid):
    r = RO.execute('SELECT COUNT(*), COUNT(DISTINCT shop_id), MIN(price_toman), MAX(last_price_changed_at) FROM offers WHERE product_id=?', (pid,)).fetchone()
    ps = [x[0] for x in RO.execute('SELECT price_toman FROM offers WHERE product_id=? AND price_toman IS NOT NULL', (pid,))]
    d = {'offers': r[0], 'shops': r[1], 'min_price': int(r[2]) if r[2] else None,
         'median_price': int(statistics.median(ps)) if ps else None, 'last_change': (r[3] or '')[:10], 'last_change_fa': _jalali(r[3]) if r[3] else None}
    mo = RO.execute('SELECT offer_id,last_price_changed_at FROM offers WHERE product_id=? AND price_toman IS NOT NULL ORDER BY price_toman LIMIT 1', (pid,)).fetchone()
    if mo:   # the cheapest offer's OWN date (a product's last_change is the latest change of ANY offer)
        dd = _days_ago(mo[1])
        d.update({'min_price_offer_id': mo[0], 'min_price_date_fa': _jalali(mo[1]) if mo[1] else None, 'min_price_days_old': int(dd) if dd is not None else None})
        if dd is not None and dd > STALE_DAYS:
            d['min_price_stale'] = True
        if len(ps) >= 3 and d['min_price'] and d['min_price'] < SUSPICIOUS_RATIO * statistics.median(ps):
            d['min_price_suspicious_low'] = True
    return d

def _offer_flags(oid, _med={}):
    """deterministic freshness/suspicion flags for one offer"""
    r = RO.execute('SELECT product_id,price_toman,last_price_changed_at FROM offers WHERE offer_id=?', (oid,)).fetchone()
    if not r:
        return None
    out, dd = {}, _days_ago(r[2])
    if dd is not None:
        out['days_old'] = int(dd)
        if dd > STALE_DAYS:
            out['stale'] = True
    if r[0] not in _med:
        ps = [x[0] for x in RO.execute('SELECT price_toman FROM offers WHERE product_id=? AND price_toman IS NOT NULL', (r[0],))]
        _med[r[0]] = statistics.median(ps) if len(ps) >= 3 else None
    m = _med[r[0]]
    if m and r[1] and r[1] < SUSPICIOUS_RATIO * m:
        out['suspicious_low'] = True; out['product_median'] = int(m)
    return out

def tool_text_search(query, k=20):
    k = max(1, min(int(k or 20), 25))
    before = R.STATS['cost']
    layers, note = dict(SEARCH_LAYERS), None
    if layers.get('embed'):
        ck = 'emb::' + (query or '')
        try:
            if R._cache_get(ck) is None:   # pre-fill recall's cache with our own bounded call, so recall never uses agent.py's 600s client
                r = embed_client().embeddings.create(model='text-embedding-3-small', input=[query], dimensions=256)
                COST['embed'] += _usage_cost(r.usage)
                R._cache_put(ck, r.data[0].embedding)
        except Exception as e:
            layers['embed'] = False; note = 'semantic layer skipped (' + type(e).__name__ + '); lexical/alias results only'
    try:
        fused, _ = R.retrieve(query, layers=layers)
    except Exception as e:
        return {'error': str(e)[:200]}
    COST['embed'] += R.STATS['cost'] - before
    out, seen = [], set()
    for r in fused:
        if len(out) >= k:
            break
        key = norm(r.get('title') or '')
        if key in seen:
            continue
        seen.add(key)
        row = {'product_id': r['product_id'], 'title': r.get('title'), 'category': r.get('category'), 'brand': r.get('brand')}
        row.update(_pstats(r['product_id']))
        fl = [f.split(' ')[0] for f in r.get('flags', []) if f.startswith(('ACCESSORY', 'KNOCKOFF', 'USED'))]
        if fl:
            row['flags'] = fl
        out.append(row)
    res = {'query': query, 'count': len(out), 'results': out}
    if note:
        res['note'] = note
    return res


# ------------------------------------------------------------------ geocode_area
EXTRA_PLACES = {  # central Tehran landmarks (approx.) on top of the area table built last round (tools.PLACES / REGION_CENTRE)
    'فردوسی': (35.7012, 51.4196), 'میدان فردوسی': (35.7012, 51.4196), 'جمهوری': (35.6960, 51.4100), 'خیابان جمهوری': (35.6960, 51.4100),
    'حافظ': (35.6985, 51.4130), 'لاله زار': (35.6975, 51.4225), 'منوچهری': (35.6985, 51.4235), 'سعدی': (35.6980, 51.4260),
    'امام خمینی': (35.6862, 51.4210), 'میدان امام خمینی': (35.6862, 51.4210), 'توپخانه': (35.6862, 51.4210),
    'بازار': (35.6760, 51.4220), 'بازار بزرگ': (35.6760, 51.4220), 'ولیعصر': (35.7120, 51.4070), 'میدان ولیعصر': (35.7120, 51.4070),
    'میدان انقلاب': (35.7010, 51.3910), 'تجارت جهانی': (35.7025, 51.4220), 'پایتخت': (35.7230, 51.3930), 'چارسو': (35.6905, 51.4160),
    'امیر کبیر': (35.6880, 51.4280), 'شوش': (35.6600, 51.4300), 'کریمخان': (35.7140, 51.4150), 'ایرانمال': (35.7550, 51.1930),
    'بام لند': (35.7470, 51.2120), 'پالادیوم': (35.7970, 51.4350), 'کوروش': (35.7400, 51.3220), 'ستارخان': (35.712, 51.355),
}

def _geo_table():
    t = {}
    for k, v in T.PLACES.items(): t[k] = v
    for k, v in T.REGION_CENTRE.items(): t[k + ' تهران'] = v; t[k] = v
    for k, v in EXTRA_PLACES.items(): t[k] = v
    return {T._addr_key(k).replace('آ', 'ا'): (k, v) for k, v in t.items()}
GEO = _geo_table()
# same boundaries as tools.REGIONS (coarse Tehran regions), expressed as SQL on shops alias s
REGION_SQL = {'غرب': 's.lon < 51.36', 'شرق': 's.lon > 51.46', 'شمال': 's.lat > 35.76', 'جنوب': 's.lat < 35.67',
              'مرکز': 's.lat BETWEEN 35.67 AND 35.73 AND s.lon BETWEEN 51.38 AND 51.45'}
_REGION_PY = {'غرب': lambda la, lo: lo < 51.36, 'شرق': lambda la, lo: lo > 51.46, 'شمال': lambda la, lo: la > 35.76,
              'جنوب': lambda la, lo: la < 35.67, 'مرکز': lambda la, lo: 35.67 <= la <= 35.73 and 51.38 <= lo <= 51.45}

def tool_geocode_area(name):
    k = T._addr_key(name or '').replace('آ', 'ا')
    for w in ('میدان', 'خیابان', 'پاساژ', 'مجتمع', 'محله', 'منطقه', 'حوالی', 'نزدیک', 'تهران'):
        k2 = k.replace(T._addr_key(w), '')
        if k2 in GEO and k2:
            k = k2
            break
    if k in GEO:
        lab, (la, lo) = GEO[k]
        reg = REGION_SQL.get(lab.replace(' تهران', '').strip())
        if reg:   # coarse region of the city: a seller filter, not just a point
            return {'found': True, 'name': lab, 'lat': la, 'lon': lo, 'is_region': True, 'region_sql': reg,
                    'source': 'coarse city region; filter sellers with region_sql (shops alias s)'}
        return {'found': True, 'name': lab, 'lat': la, 'lon': lo, 'suggested_radius_km': 3, 'source': 'area table (approx. centre)'}
    # data-derived fallback: centroid of shops whose address mentions the place (e.g. a mall/passage name)
    nk = norm(name or '').replace('آ', 'ا').replace('ء', '')
    rows = RO.execute("SELECT lat, lon FROM shops WHERE lat IS NOT NULL AND replace(replace(address_norm,'آ','ا'),'ء','') LIKE ?", (f'%{nk}%',)).fetchall()
    if len(rows) >= 3:
        las, los = sorted(r[0] for r in rows), sorted(r[1] for r in rows)
        return {'found': True, 'name': name, 'lat': round(statistics.median(las), 5), 'lon': round(statistics.median(los), 5),
                'source': f'median location of {len(rows)} shops whose address mentions it', 'n_shops_with_this_in_address': len(rows)}
    return {'found': False, 'name': name, 'known_examples': [v[0] for v in list(GEO.values())[:25]]}


TOOLS = {'sql': lambda a: tool_sql(a.get('query')), 'text_search': lambda a: tool_text_search(a.get('query'), a.get('k', 20)),
         'geocode_area': lambda a: tool_geocode_area(a.get('name'))}
TOOL_SCHEMAS = [
    {'type': 'function', 'function': {'name': 'sql', 'description': 'Run ONE read-only SQLite SELECT/WITH on the Torob DB. Auto LIMIT 50. Extra functions: km(lat1,lon1,lat2,lon2), norm_fa(text), days_ago(ts), jalali(ts) -> Persian date, median(x) aggregate.',
                                      'parameters': {'type': 'object', 'properties': {'query': {'type': 'string'}}, 'required': ['query']}}},
    {'type': 'function', 'function': {'name': 'text_search', 'description': 'Fuzzy product finder (Persian/English, misspellings, aliases, semantic). Returns product_id, title, category, offers, shops, min/median price, last_change, flags. Call again with your own rewrites if results are off.',
                                      'parameters': {'type': 'object', 'properties': {'query': {'type': 'string'}, 'k': {'type': 'integer'}}, 'required': ['query']}}},
    {'type': 'function', 'function': {'name': 'geocode_area', 'description': 'Tehran place/neighbourhood/square/mall/region name -> approx lat/lon (+ region_sql for غرب/شرق/شمال/جنوب/مرکز, or suggested_radius_km). Use to FILTER sellers in SQL.',
                                      'parameters': {'type': 'object', 'properties': {'name': {'type': 'string'}}, 'required': ['name']}}},
]


# ------------------------------------------------------------------ system prompt (knowledge, not rules)
SCHEMA_CARD = """DB (SQLite, read-only). Prices in toman.
- products(product_id, persian_title, title_norm [normalised lowercase title — use for LIKE], brand_name, category_name, model, specs [json text], n_specs)
- product_stats(product_id, n_offers, n_shops, n_priced, min_price, max_price, latest_price_change)  1 row/product
- offers(offer_id, product_id, shop_id, price_toman [cleaned, NULL if missing/garbage], price_status, seller_title, warranty, warranty_months, last_price_changed_at [ISO])
- shops(shop_id, name, address, lat, lon, location_label, category_names [json], phone, payment_options [json], supports_fast_delivery, weekly_hours [json])
- shop_hours(shop_id, day [sat|sun|mon|tue|wed|thu|fri], status [declared|closed|unsupported], start_time 'HH:MM:SS', end_time)
- shop_payment_options(shop_id, provider_name [e.g. اسنپ‌پی, ترب‌پی, دیجی پی, تارا, ازکی‌وام], channel [in_person|unknown], min_price_toman, max_price_toman)
- shop_categories(shop_id, category_name)   product_specs(product_id, section, key, value)
Joins: offers.product_id=products.product_id, offers.shop_id=shops.shop_id. Indexed: offers(product_id), offers(shop_id), products(category_name), products(brand_name).
Full scans of products with LIKE on title_norm are OK (~0.3s); avoid functions over all offers without a WHERE on product_id/category.
Examples:
1) cheapest offers of given products near a point:
SELECT o.offer_id,o.product_id,o.shop_id,o.price_toman,substr(o.last_price_changed_at,1,10) d,s.name,round(km(35.7012,51.4196,s.lat,s.lon),2) km
FROM offers o JOIN shops s USING(shop_id) WHERE o.product_id IN ('product_a','product_b') AND o.price_toman IS NOT NULL ORDER BY km, o.price_toman LIMIT 15
2) compare two products: SELECT p.product_id,p.persian_title,COUNT(o.offer_id) n,MIN(o.price_toman) mn,median(o.price_toman) med,MAX(o.last_price_changed_at) last
FROM products p JOIN offers o USING(product_id) WHERE p.product_id IN (..) AND o.price_toman IS NOT NULL GROUP BY 1
   specs: SELECT product_id,key,value FROM product_specs WHERE product_id IN (..) AND key IN ('...')
3) shops open now (today={DAY}, time={HHMM}): SELECT s.shop_id,s.name,h.start_time,h.end_time FROM shops s JOIN shop_hours h USING(shop_id)
WHERE h.day='{DAY}' AND h.status='declared' AND h.start_time<='{HHMMSS}' AND h.end_time>'{HHMMSS}' AND s.shop_id IN (...)
4) installment shops selling a category: SELECT DISTINCT s.shop_id,s.name,p.provider_name,p.channel FROM shop_payment_options p JOIN shops s USING(shop_id)
JOIN shop_categories c USING(shop_id) WHERE c.category_name='گوشی موبایل' ORDER BY p.channel='in_person' DESC
5) browse a category in a budget: SELECT p.product_id,p.persian_title,st.n_shops,st.min_price FROM products p JOIN product_stats st USING(product_id)
WHERE p.category_name='مانیتور' AND st.min_price BETWEEN 8e6 AND 3e7 ORDER BY st.n_shops DESC LIMIT 20
6) a good X up to a budget, sellers inside an area (region_sql from geocode_area, or km(lat,lon,s.lat,s.lon)<=radius for a place):
SELECT p.brand_name,p.model,MIN(p.persian_title) t,COUNT(DISTINCT o.shop_id) area_shops,MIN(o.price_toman) mn,MAX(st.n_shops) city_shops
FROM offers o JOIN shops s USING(shop_id) JOIN products p USING(product_id) JOIN product_stats st USING(product_id)
WHERE p.category_name='لپ تاپ و نوت بوک' AND o.price_toman BETWEEN 3e7 AND 6e7 AND s.lon > 51.46 AND p.title_norm NOT LIKE '%استوک%'
GROUP BY 1,2 ORDER BY city_shops DESC LIMIT 25     -- one row per MODEL (storage variants merged); then fetch the in-area offers of the 3-5 models you pick
7) cheaper comparable alternatives to a product P (median price M, category C): SELECT p.product_id,p.persian_title,st.n_shops,st.min_price,
(SELECT median(o.price_toman) FROM offers o WHERE o.product_id=p.product_id AND o.price_toman IS NOT NULL) med FROM products p JOIN product_stats st USING(product_id)
WHERE p.category_name=C AND p.product_id<>P AND st.min_price BETWEEN 0.5*M AND 0.9*M AND st.n_shops>=5 AND p.title_norm NOT LIKE '%استوک%' ORDER BY st.n_shops DESC LIMIT 20
8) the cheapest offer PER product with ITS OWN offer_id/shop/date (SQLite: with a single MIN(), bare columns come from that same row):
SELECT o.product_id,MIN(o.price_toman) price,o.offer_id,o.shop_id,jalali(o.last_price_changed_at) fa FROM offers o WHERE o.product_id IN (..) AND o.price_toman IS NOT NULL GROUP BY o.product_id
   (never combine MIN(price), MIN(offer_id), MIN(date) in one SELECT: each MIN comes from a different row, so the id/date would not belong to that price)
Category names are Persian, e.g. 'گوشی موبایل','لپ تاپ و نوت بوک','مانیتور','هدفون، هدست و هندزفری','کنسول بازی','تبلت','ساعت هوشمند'. Discover others with SELECT category_name,COUNT(*) FROM products WHERE category_name LIKE '%..%' GROUP BY 1."""

DATA_TRUTHS = """Data truths (reason with them, mention them to the shopper when relevant):
- Prices are historical snapshots: always give the last price-change date; an offer does NOT mean it is in stock now — the shopper should confirm before going.
- Shop phone numbers are fake/test data: never present a phone as callable; say contact details in this demo data are not real. Most shop names are also synthetic.
- ~85% of shops sit around Ferdowsi/Baharestan/Jomhouri (central Tehran); other areas are thin, so a far-away area may have few or no shops — say so and offer the nearest real option.
- There is NO stock, colour or review data. Colour/condition requests are a soft note ("colour not recorded; confirm with the shop"), never a filter that empties the result.
- A price far below the product's median (e.g. <50%) is suspicious (data error, part, clone, or used): check the median yourself in SQL before calling something "cheapest".
- Mislabelled items exist: accessories (cases, glass, parts, chargers) and «طرح»/clone knock-offs often match a device name; check the title AND category really are the thing asked.
- Dates: never convert Gregorian↔Persian yourself (it goes wrong); write a Persian date only from jalali(ts) in SQL or a *_fa field, otherwise the date exactly as shown. A date belongs to one offer: quote the date of the same offer whose price you quote (a product's last_change is the latest change of ANY of its offers).
- Products have many near-duplicate listings (storage/variant in the title); group or pick the clearest ones.
- FRESHNESS RULE (always, not only when asked): tool results flag offers server-side — sql adds offer_flags {offer_id: {days_old, stale, suspicious_low, product_median}}; text_search rows carry min_price_date_fa, min_price_days_old, min_price_stale, min_price_suspicious_low. stale = last price change older than 60 days; suspicious_low = under half the product's median. For EVERY flagged offer/price you quote or show, say it in the Persian text right next to that price, e.g. «(قیمت ثبت‌شده در ۲۱ تیر ۱۴۰۵، بیش از سه ماه پیش؛ احتمالاً به‌روز نیست)» or «خیلی کمتر از میانهٔ قیمت (حدود ۳٫۵ میلیون) است؛ شاید خطا، کالای دیگر یا کارکرده باشد». Prefer a fresh offer when a similar one exists. Write these notes only in Persian — never the words stale/suspicious or field names."""

SYSTEM = """You are «دستیار خرید حضوری ترب», an in-person shopping assistant for Tehran stores, working like a careful data analyst with a database.
Now: {NOW} (Tehran). Today's day code: {DAY}.
{SCHEMA}

{TRUTHS}

Working method: understand the need → explore (text_search with several rewrites, e.g. آیفون/iPhone/اپل; SQL for prices, shops, distance, hours, installments) → verify the hits really are the product asked for → refine → answer. You have at most 8 tool steps; then answer with what you have. Prefer showing 3–5 real items over asking. Ask a clarifying question only if it truly changes the result, at most once in the whole conversation (check the history), and preferably after already showing real options. If nothing matches, say so plainly and SHOW the closest real alternative in the same answer (with its ids: other area, budget, similar product) instead of only offering to look. Short follow-ups («ارزون‌ترش», «این نه», «نزدیک‌تر») refer to what you showed last (the history lists the ids shown); if one reads two ways (cheaper offer of the same item vs. a cheaper similar product) cover both (see worked example b). A shop the user rejects goes into mission.excluded_shop_ids and stays out of later answers. If the user's location matters and is unknown, show central-Tehran options and ask for the area once.

Worked examples (patterns of good analysis — adapt them, they are not fixed rules):
(a) «لپ‌تاپ خوب تا ۶۰ میلیون شرق تهران» — "a good X up to BUDGET [in AREA]" asks for a CHOICE, not the first cheap hit. geocode_area the area → one SQL over the category (example 6): priced offers between ~half the budget and the budget, real devices only (no used/stock/clone/accessory titles), ranked by popularity (city_shops); when the shopper named an area, the area is a real seller filter: join shops and keep only sellers inside it (region_sql or km to the area point), so every seller you show is really in that area → pick 3–5 DIFFERENT strong models spread across the budget (not storage variants of one model, not only the cheapest) → show each with its best in-area offer_id and date (product_cards + sellers). If the area has fewer than 3 options, show all it has, say the area is thin, then add 1–2 strong options from the nearest well-stocked area clearly labelled with their area/distance. A colour wish is only a soft note.
(b) Turn 1 showed «هدفون سونی WH-1000XM5» (typical ~40M); turn 2 the shopper says «ارزون‌ترش؟». This reads two ways — answer BOTH in the same reply, never only the first: (1) the cheapest offer of that same item (say plainly if what you showed is already the cheapest); (2) 2–3 comparable CHEAPER ALTERNATIVE models (other models/brands of the same category and tier), found with one SQL (example 7) priced at roughly 50–90% of the current item's median, popular (n_shops), real devices (not basic/used/accessory) → fetch each one's cheapest offer_id and date. Text: «ارزان‌ترین همین مدل … ؛ اگر مدل ارزان‌تر هم‌رده هم قبول است: …». Put (1) in sellers and (2) in product_cards + sellers.

FINAL ANSWER = ONE valid JSON object only (no markdown fence, no text outside it; escape quotes/newlines inside strings):
{{"text": "<fluent, concise Persian for the shopper; may quote prices you saw in tool results>",
 "blocks": [ ... ],
 "mission": {{"goal":..,"budget_toman":..,"area":..,"area_latlon":[lat,lon]|null,"selected_product_id":..,"selected_shop_id":..,"excluded_shop_ids":[..],"notes":..}} }}
Block types (ids ONLY — the server fills titles/prices/addresses from the DB; never put prices or addresses in blocks):
- {{"type":"product_cards","items":[{{"product_id":"..","note":"<short Persian why>"}}]}}
- {{"type":"sellers","items":[{{"offer_id":"..","note":".."}}]}}   (an offer_id identifies product+shop+price)
- {{"type":"compare","product_ids":[..],"note":".."}}
- {{"type":"map","shop_ids":[..],"center":[lat,lon]|null}}
- {{"type":"plan","steps":[{{"shop_id":"..","note":".."}}]}}   (a visit route)
- {{"type":"verify","items":[{{"offer_id":"..","note":"<what to check: price/stock/colour>"}}]}}
- {{"type":"chips","options":["<short Persian follow-up suggestions>"]}}
Use only ids you actually saw in tool results. The text and chips must be entirely Persian (only product model names like "S25 FE" or "PS5" may be Latin; write every other word in Persian, e.g. «قیمت ثبت‌شده/تاریخی» not «snapshot»); never output English words or sentences, tool names, SQL, ids or internal reasoning in text. Keep text under ~120 words; the text must stand on its own (never empty) and mention the key prices/dates you saw. Update mission each turn (keep what still holds)."""


def system_prompt(mission=None, user_lat=None, user_lon=None):
    now = datetime.now(TEHRAN)
    day = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'][now.weekday()]
    hh = now.strftime('%H:%M:%S')
    sch = SCHEMA_CARD.replace('{DAY}', day).replace('{HHMMSS}', hh).replace('{HHMM}', hh[:5])
    s = SYSTEM.format(NOW=now.strftime('%Y-%m-%d %H:%M'), DAY=day, SCHEMA=sch, TRUTHS=DATA_TRUTHS)
    if user_lat is not None:
        s += f'\nShopper location (from device): lat={user_lat}, lon={user_lon}.'
    if mission:
        s += '\nCurrent mission (from earlier turns; you own it, update it): ' + json.dumps(mission, ensure_ascii=False)
    return s


# ------------------------------------------------------------------ hydration (deterministic grounding guard)
def _offer(oid):
    r = RO.execute('''SELECT o.offer_id,o.product_id,o.shop_id,o.price_toman,o.last_price_changed_at,o.warranty,p.persian_title,p.category_name,
                      s.name,s.address,s.lat,s.lon,s.phone FROM offers o JOIN products p USING(product_id) JOIN shops s USING(shop_id) WHERE o.offer_id=?''', (oid,)).fetchone()
    if not r:
        return None
    return {'offer_id': r[0], 'product_id': r[1], 'shop_id': r[2], 'price_toman': int(r[3]) if r[3] else None, 'last_price_change': (r[4] or '')[:10],
            'last_price_change_fa': _jalali(r[4]) if r[4] else None, 'days_since_change': _days_ago(r[4]), 'warranty': r[5], 'product_title': r[6], 'category': r[7], 'shop': _shop(r[2]),
            **_flag_fields(_offer_flags(r[0]) or {}, _jalali(r[4]) if r[4] else None)}

def _flag_fields(f, date_fa):
    """structured flags + a ready Persian note for the UI card (never English)"""
    d = {'stale': bool(f.get('stale')), 'suspicious_low': bool(f.get('suspicious_low'))}
    notes = []
    if d['stale']:
        notes.append(f'قیمت مربوط به {date_fa} است (حدود {_fa_digits(f["days_old"])} روز پیش) و ممکن است به‌روز نباشد')
    if d['suspicious_low']:
        notes.append(f'این قیمت کمتر از نصف میانهٔ قیمت این کالا (حدود {_fa_digits(format(f["product_median"], ",").replace(",", "٬"))} تومان) است؛ ممکن است خطا، کالای متفاوت یا کارکرده باشد')
    if notes:
        d['freshness_note_fa'] = '؛ '.join(notes)
    return d

def _hours_today(sid):
    day = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'][datetime.now(TEHRAN).weekday()]
    h = RO.execute('SELECT status,start_time,end_time FROM shop_hours WHERE shop_id=? AND day=?', (sid, day)).fetchone()
    if not h or h[0] == 'unsupported':
        return None
    return 'تعطیل' if h[0] == 'closed' else f'{h[1][:5]}–{h[2][:5]}'

def _shop(sid):
    r = RO.execute('SELECT shop_id,name,address,lat,lon,location_label FROM shops WHERE shop_id=?', (sid,)).fetchone()
    if not r:
        return None
    pay = [p[0] + (' (حضوری)' if p[1] == 'in_person' else '') for p in RO.execute('SELECT provider_name,channel FROM shop_payment_options WHERE shop_id=?', (sid,))]
    return {'shop_id': r[0], 'name': r[1], 'address': r[2], 'lat': r[3], 'lon': r[4], 'label': r[5], 'hours_today': _hours_today(sid),
            'installment': pay, 'phone_note': 'شماره‌های تماس در این داده آزمایشی‌اند'}

def _product(pid):
    r = RO.execute('SELECT product_id,persian_title,brand_name,category_name,image_urls FROM products WHERE product_id=?', (pid,)).fetchone()
    if not r:
        return None
    img = None
    try:
        img = (json.loads(r[4]) or [None])[0] if r[4] else None
    except Exception:
        pass
    d = {'product_id': r[0], 'title': r[1], 'brand': r[2], 'category': r[3], 'image': img}
    d.update(_pstats(pid))
    return d

def _ed1(a, b):
    if a == b: return True
    if abs(len(a) - len(b)) > 1: return False
    if len(a) == len(b): return sum(x != y for x, y in zip(a, b)) == 1
    if len(a) > len(b): a, b = b, a
    return any(b[:i] + b[i + 1:] == a for i in range(len(b)))

_ID_RX = re.compile(r'(?:product|shop|offer)_[0-9a-f]{16,32}')

def hydrate(blocks, seen_ids=None):
    log = {'kept': 0, 'dropped': [], 'repaired': []}
    out = []
    seen_ids = seen_ids or set()
    def take(kind, ident, fn):
        v = fn(ident) if isinstance(ident, str) else None
        if v is None and isinstance(ident, str):   # 1-char copy slip of a long id: accept only a UNIQUE id the tools really returned
            cands = [x for x in seen_ids if x.split('_')[0] == ident.split('_')[0] and _ed1(x, ident)]
            if len(cands) == 1 and (v := fn(cands[0])) is not None:
                log['repaired'].append({'kind': kind, 'id': ident, 'to': cands[0]})
        if v is None:
            log['dropped'].append({'kind': kind, 'id': ident})
        else:
            log['kept'] += 1
        return v
    for b in blocks if isinstance(blocks, list) else []:
        if not isinstance(b, dict):
            continue
        t = b.get('type')
        if t == 'product_cards':
            items = []
            for it in b.get('items', []):
                p = take('product', (it or {}).get('product_id'), _product)
                if p: items.append(dict(p, note=it.get('note')))
            if items: out.append({'type': t, 'items': items})
        elif t in ('sellers', 'verify'):
            items = []
            for it in b.get('items', []):
                it = it or {}
                if it.get('offer_id'):
                    o = take('offer', it['offer_id'], _offer)
                    if o: items.append(dict(o, note=it.get('note')))
                elif it.get('shop_id'):
                    s = take('shop', it['shop_id'], _shop)
                    if s: items.append({'shop': s, 'note': it.get('note')})
                else:
                    log['dropped'].append({'kind': t + '_item_without_id', 'id': None})
            if items: out.append({'type': t, 'items': items})
        elif t == 'compare':
            ps = [p for p in (take('product', x, _product) for x in b.get('product_ids', [])) if p]
            if len(ps) >= 2: out.append({'type': t, 'products': ps, 'note': b.get('note')})
        elif t == 'map':
            ss = [s for s in (take('shop', x, _shop) for x in b.get('shop_ids', [])) if s and s['lat'] is not None]
            if ss: out.append({'type': t, 'center': b.get('center'), 'pins': [{k: s[k] for k in ('shop_id', 'name', 'lat', 'lon', 'address')} for s in ss]})
        elif t == 'plan':
            steps = []
            for st in b.get('steps', []):
                st = st if isinstance(st, dict) else {'note': str(st)}
                if st.get('shop_id'):
                    s = take('shop', st['shop_id'], _shop)
                    if s: steps.append({'shop': s, 'note': st.get('note')})
                else:
                    steps.append({'note': st.get('note')})
            if steps: out.append({'type': t, 'steps': steps})
        elif t == 'chips':
            opts = [str(o) for o in b.get('options', []) if o][:6]
            if opts: out.append({'type': t, 'options': opts})
        else:
            log['dropped'].append({'kind': 'unknown_block_type', 'id': t})
    return out, log


# ------------------------------------------------------------------ helpers for history
def summarize_blocks(blocks):
    """compact, id-bearing summary of what was shown (fed back as assistant context next turn)"""
    lines = []
    for b in blocks:
        if b['type'] == 'product_cards':
            lines += [f"product {p['product_id']} «{p['title'][:60]}» min {p['min_price']}" for p in b['items']]
        elif b['type'] in ('sellers', 'verify'):
            for o in b['items']:
                if 'offer_id' in o:
                    lines.append(f"offer {o['offer_id']} product {o['product_id']} shop {o['shop_id']} «{(o['shop'] or {}).get('name')}» {o['price_toman']} ({o['last_price_change']})")
        elif b['type'] == 'map':
            lines.append('map shops ' + ','.join(p['shop_id'] for p in b['pins']))
        elif b['type'] == 'plan':
            lines += [f"plan shop {s['shop']['shop_id']}" for s in b['steps'] if s.get('shop')]
    return '\n'.join(lines[:20])

def _parse_final(s):
    s = (s or '').strip()
    s = re.sub(r'^```(?:json)?|```$', '', s.strip(), flags=re.M).strip()
    try:
        return json.loads(s)
    except Exception:
        m = re.search(r'\{.*\}', s, re.S)
        if m:
            try:
                obj = json.loads(m.group(0))
                prose = _clean_tail(s[:m.start()])
                if isinstance(obj, dict) and obj.get('type') and 'blocks' not in obj:   # a bare block
                    obj = {'blocks': [obj]}
                if isinstance(obj, dict) and not obj.get('text') and prose:
                    obj['text'] = prose; obj['_parse_repaired'] = True
                return obj
            except Exception:
                pass
    return _salvage(s)

def _clean_tail(t):
    t = re.sub(r'#[^#\n]{0,40}#\s*$', '', t.strip())          # stray '# JSON only #' style markers
    return re.sub(r'[\[\{,\s]+$', '', t).strip()

def _salvage(s):
    """model JSON slightly malformed (stray brace / prose before the blocks array): recover text, blocks, mission deterministically"""
    dec, out = json.JSONDecoder(), {'_parse_repaired': True}
    cut = len(s)
    for key, opener in (('blocks', '['), ('mission', '{')):
        m = re.search(r'"%s"\s*:\s*\%s' % (key, opener), s)
        if m:
            try:
                out[key] = dec.raw_decode(s, m.end() - 1)[0]; cut = min(cut, m.start())
            except Exception:
                pass
    if 'blocks' not in out:
        m = re.search(r'\[\s*\{\s*"type"', s)
        if m:
            try:
                out['blocks'] = dec.raw_decode(s, m.start())[0]; cut = min(cut, m.start())
            except Exception:
                pass
    t = s[:cut]
    t = re.sub(r'^\s*\{\s*"text"\s*:\s*"', '', t)
    t = re.sub(r'["}\],\s\[]*$', '', t)
    out['text'] = _clean_tail(t.replace('\\n', '\n').replace('\\"', '"'))
    if not out['text'] or len(out) == 2 and 'blocks' not in out:
        out['_parse_error'] = True
    return out

_NUM = re.compile(r'[\d۰-۹][\d۰-۹,٬\.]*')
def price_mentions_check(text, seen_numbers):
    """log-only check: numbers in the text that look like prices (>=100k toman, or '<n> میلیون') and were never seen in tool output"""
    t = norm(text or '').replace('٫', '.').replace('٬', ',')
    bad = []
    for m in re.finditer(r'(\d[\d,\.]*)\s*(میلیون|هزار)?', t):
        raw, unit = m.group(1).replace(',', ''), m.group(2)
        try:
            v = float(raw)
        except ValueError:
            continue
        if unit == 'میلیون': v *= 1e6
        elif unit == 'هزار': v *= 1e3
        if v < 1e5:
            continue
        if not any(abs(v - s) <= max(0.051 * s, 1) for s in seen_numbers):   # 'حدود ۴۵ میلیون' style rounding tolerated
            bad.append(m.group(0))
    return bad

def dates_check(text, blocks, tool_text):
    """log-only: Gregorian dates / Persian 'day month' dates in the text that appear neither in tool output nor in hydrated blocks"""
    t = norm(text or '')
    hay = norm(tool_text + ' ' + json.dumps(blocks, ensure_ascii=False))
    bad = [d for d in re.findall(r'20\d\d-\d\d-\d\d', t) if d not in hay]
    for m in re.finditer(r'(\d{1,2}) (%s)' % '|'.join(norm(x) for x in _FA_MONTHS), t):
        if m.group(0) not in hay and (m.group(0) + ' ') not in hay:
            bad.append(m.group(0))
    return bad

_LATIN_RUN = re.compile(r"[A-Za-z][A-Za-z'\-]*(?:\s+[A-Za-z][A-Za-z'\-]*){3,}")


# ------------------------------------------------------------------ main loop
def _usage_cost(u):
    return float(getattr(u, 'cost', 0) or (getattr(u, 'model_extra', None) or {}).get('cost', 0) or 0)

def _area_check(blocks, mission):
    """log + annotate: each hydrated seller gets km to the shopper's area; list sellers outside a named region / >radius"""
    mission = mission or {}
    ll = mission.get('area_latlon') if isinstance(mission.get('area_latlon'), list) and len(mission.get('area_latlon')) == 2 else None
    area = str(mission.get('area') or '')
    reg = next((r for r in _REGION_PY if r in area), None)
    out = []
    for b in blocks:
        if b['type'] not in ('sellers', 'verify'):
            continue
        for it in b['items']:
            sh = it.get('shop') or {}
            if sh.get('lat') is None:
                continue
            if ll:
                try: sh['km_from_area'] = round(T.haversine(float(ll[0]), float(ll[1]), sh['lat'], sh['lon']), 1)
                except Exception: pass
            inside = _REGION_PY[reg](sh['lat'], sh['lon']) if reg else (sh.get('km_from_area', 0) <= 5 if ll else True)
            if not inside:
                out.append({'shop_id': sh.get('shop_id'), 'km_from_area': sh.get('km_from_area'), 'note': it.get('note')})
    return out

def _fallback(hist, mission, user_lat, user_lon, usage, trace, final, t0):
    """v3 failed (timeout / no usable answer): answer this turn with the current agent.py instead of an error string"""
    import agent as OLD
    q = next((m['content'] for m in reversed(hist) if m.get('role') == 'user'), '')
    if len(hist) > 1 and isinstance(mission, dict) and mission.get('goal'):
        q = f"(ادامهٔ گفتگو دربارهٔ: {mission.get('goal')}) {q}"
    reason = final.get('_error') or ('parse_error' if final.get('_parse_error') else 'empty_text')
    import threading
    box = {}
    def _run():
        try:
            box['r'] = OLD.run_agent(q, user_lat=user_lat, user_lon=user_lon)
        except Exception as e:
            box['e'] = e
    th = threading.Thread(target=_run, daemon=True)
    th.start()
    th.join(max(0.5, TURN_BUDGET_S - (time.time() - t0)))   # the whole turn stays inside TURN_BUDGET_S
    if 'r' in box:
        r = box['r']
        text, c = r['final_answer'], float(r['usage'].get('cost', 0))
        usage['cost'] += c; COST['llm'] += c; usage['api_calls'] += r['usage'].get('api_calls', 0)
    else:
        text = 'متأسفم، پاسخ این سؤال بیش از حد طول کشید؛ لطفاً دوباره یا کمی دقیق‌تر بپرسید.'
        reason += f" | fallback failed: {str(box['e'])[:120]}" if 'e' in box else ' | fallback exceeded turn budget (still running in background; its cost is not counted here)'
    mission = mission or {}
    hlog = {'kept': 0, 'dropped': [], 'repaired': [], 'unverified_price_mentions': [], 'latin_runs_in_text': [], 'latin_words_not_in_data': [], 'unverified_dates': [],
            'parse_error': bool(final.get('_parse_error')), 'parse_repaired': False, 'llm_error': final.get('_error'),
            'raw_final': (final.get('_raw') or '')[:3000], 'sellers_outside_area': [], 'fallback': 'agent.run_agent: ' + reason}
    usage['cost_embed_this_process'] = round(COST['embed'], 5)
    return {'text': text, 'blocks': [], 'mission': mission, 'usage': usage, 'tool_trace': trace, 'hydration_log': hlog,
            'elapsed_s': round(time.time() - t0, 1), 'history_entry': {'role': 'assistant', 'content': json.dumps({'text': text, 'shown_ids': [], 'mission': mission}, ensure_ascii=False)}}

def run_agent_v3(messages_or_question, session_mission=None, user_lat=None, user_lon=None):
    hist = [{'role': 'user', 'content': messages_or_question}] if isinstance(messages_or_question, str) else list(messages_or_question)
    msgs = [{'role': 'system', 'content': system_prompt(session_mission, user_lat, user_lon)}] + hist
    usage = {'prompt_tokens': 0, 'completion_tokens': 0, 'cost': 0.0, 'api_calls': 0}
    trace, seen_nums, final = [], [], None
    t0 = time.time()
    for step in range(MAX_STEPS + 1):
        el = time.time() - t0
        if el >= TURN_FINAL_BY_S - 2:   # no time left even for a forced final answer -> fallback
            final = {'text': '', 'blocks': [], '_error': f'turn deadline ({el:.1f}s)'}
            break
        forced = step == MAX_STEPS or el >= TURN_SOFT_S
        kw = dict(model=MODEL, messages=msgs, max_completion_tokens=MAX_COMPLETION_TOKENS, reasoning_effort='none', tools=TOOL_SCHEMAS,
                  response_format={'type': 'json_object'})   # final content is forced to JSON; tool calls are unaffected
        if forced:
            kw['tool_choice'] = 'none'
            msgs.append({'role': 'system', 'content': ('Tool budget used up' if step == MAX_STEPS else 'Time budget used up') + ': give the final JSON answer now with what you have.'})
            kw['timeout'] = max(2.0, TURN_FINAL_BY_S - el)
        else:   # an exploring call may run until SOFT+4s, leaving room for the forced final step
            kw['timeout'] = max(2.0, min(LLM_STEP_TIMEOUT_S, TURN_SOFT_S + 4 - el))
        try:
            resp = client().chat.completions.create(**kw)
        except Exception as e:     # no retry loop: fail honestly
            final = {'text': '', 'blocks': [], '_error': str(e)[:200] + f' (step {step}, {time.time() - t0:.1f}s)'}
            break
        u = resp.usage
        usage['prompt_tokens'] += u.prompt_tokens; usage['completion_tokens'] += u.completion_tokens
        c = _usage_cost(u); usage['cost'] += c; COST['llm'] += c; usage['api_calls'] += 1
        m = resp.choices[0].message
        if not m.tool_calls:
            final = _parse_final(m.content); final['_raw'] = m.content or ''
            if forced and step < MAX_STEPS:
                final['_deadline_forced'] = round(el, 1)
            break
        if forced:   # tool calls despite tool_choice=none: no usable answer
            break
        msgs.append({'role': 'assistant', 'content': None, 'tool_calls': [
            {'id': tc.id, 'type': 'function', 'function': {'name': tc.function.name, 'arguments': tc.function.arguments}} for tc in m.tool_calls]})
        for tc in m.tool_calls:
            try:
                args = json.loads(tc.function.arguments or '{}')
            except Exception:
                args = {}
            fn = TOOLS.get(tc.function.name)
            ts = time.time()
            res = fn(args) if fn else {'error': 'unknown tool'}
            js = json.dumps(res, ensure_ascii=False, separators=(',', ':'))
            seen_nums += [float(x) for x in re.findall(r'(?<![\w.])\d{5,}(?:\.\d+)?', js)]
            trace.append({'step': step, 'tool': tc.function.name, 'args': args, 'ms': int((time.time() - ts) * 1000),
                          'rows': res.get('row_count', res.get('count')), 'error': res.get('error'), 'out_chars': len(js)})
            msgs.append({'role': 'tool', 'tool_call_id': tc.id, 'content': js[:9000]})
    final = final or {'text': '', 'blocks': [], '_error': 'no final answer'}
    if final.get('_error') or final.get('_parse_error') or not (final.get('text') or '').strip():
        return _fallback(hist, session_mission, user_lat, user_lon, usage, trace, final, t0)
    seen_ids = set(_ID_RX.findall(' '.join(str(m.get('content') or '') for m in msgs if m.get('role') in ('tool', 'assistant'))))
    blocks, hlog = hydrate(final.get('blocks') or [], seen_ids)
    for b in blocks:   # hydrated prices are data too
        for it in b.get('items', []) + b.get('products', []):
            for k in ('price_toman', 'min_price', 'median_price'):
                if isinstance(it, dict) and it.get(k): seen_nums.append(float(it[k]))
    text = final.get('text') or ''
    hlog['internal_tokens_scrubbed'] = re.findall(r'\b(?:suspicious_low|min_price_\w+|offer_flags|days_old|stale|suspicious)\b', text, re.I)
    for a, b in ((r'\bsuspicious_low\b|\bsuspicious\b', 'مشکوک'), (r'\bstale\b', 'قدیمی'), (r'\b(?:min_price_\w+|offer_flags|days_old)\b', '')):
        text = re.sub(a, b, text, flags=re.I)
    mission = final.get('mission') if isinstance(final.get('mission'), dict) else (session_mission or {})
    hlog['unverified_price_mentions'] = price_mentions_check(text, seen_nums)
    hlog['latin_runs_in_text'] = _LATIN_RUN.findall(text)
    hlog['unverified_dates'] = dates_check(text, blocks, ' '.join(str(m.get('content') or '') for m in msgs if m.get('role') == 'tool'))
    titles = ' '.join(json.dumps(b, ensure_ascii=False) for b in blocks).lower() + ' ' + ' '.join(str(m.get('content', '')) for m in msgs if m.get('role') == 'tool').lower()
    hlog['latin_words_not_in_data'] = sorted({w for w in re.findall(r'[A-Za-z][A-Za-z\-]{2,}', text) if w.lower() not in titles})
    hlog['parse_error'] = bool(final.get('_parse_error')); hlog['parse_repaired'] = bool(final.get('_parse_repaired')); hlog['llm_error'] = final.get('_error')
    hlog['raw_final'] = (final.get('_raw') or '')[:3000]
    hlog['sellers_outside_area'] = _area_check(blocks, mission)
    hlog['fallback'] = None
    fl = [it for b in blocks if b['type'] in ('sellers', 'verify') for it in b['items'] if it.get('stale') or it.get('suspicious_low')]
    hlog['flagged_offers_shown'] = len(fl)
    hlog['flagged_but_text_silent'] = bool(fl) and not re.search(r'قدیمی|به‌روز|بروز|به روز|ماه پیش|روز پیش|سال پیش|مشکوک|میانه|خطا', text)
    usage['cost_embed_this_process'] = round(COST['embed'], 5)
    return {'text': text, 'blocks': blocks, 'mission': mission, 'usage': usage, 'tool_trace': trace, 'hydration_log': hlog,
            'elapsed_s': round(time.time() - t0, 1), 'history_entry': {'role': 'assistant', 'content': json.dumps({'text': text, 'shown_ids': summarize_blocks(blocks).split('\n') if blocks else [], 'mission': mission}, ensure_ascii=False)}}
