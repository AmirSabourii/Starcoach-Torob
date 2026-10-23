"""In-store shopping helpers (DB only, $0): fair price range, other shops in the same mall, alternatives right here,
«چی بپرسم؟» checklist + authenticity hints (static), mall facts (mall_facts.json, cited), and photo → product (vision, spend-capped)."""
import json, math, os, re, statistics, time, threading
from fastapi import APIRouter, HTTPException, Request
import playground_drill as D
import playground_mallguide as MG

HERE = os.path.dirname(os.path.abspath(__file__))
router = APIRouter()
_H = {'auth': None, 'add_spend': None, 'can_spend': None, 'client_fn': None, 'hydrate_fn': None, 'session_fn': None}
def init(auth=None, add_spend=None, can_spend=None, client_fn=None, hydrate_fn=None, session_fn=None):
    _H.update(auth=auth, add_spend=add_spend, can_spend=can_spend, client_fn=client_fn, hydrate_fn=hydrate_fn, session_fn=session_fn)
def _auth(req):
    if _H['auth']: _H['auth'](req)
q = D.q
_FA = str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹')
def fa(x): return str(x).translate(_FA)

def _clean(t):
    t = re.sub(r'موجود(ی)?', 'دارد', str(t or ''))
    t = re.sub(r'[0-9۰-۹]+(?:[.٫][0-9۰-۹]+)?\s*کیلومتر', 'کمی', t)
    return t.replace('·', '،').strip()

def money_short(v):
    """۱٫۲ میلیون / ۸۵۰ هزار"""
    if v is None: return 'نامشخص'
    if v >= 1_000_000:
        m = round(v / 1_000_000, 1)
        s = (f'{m:.1f}'.rstrip('0').rstrip('.')).replace('.', '٫')
        return fa(s) + ' میلیون'
    return fa(int(round(v / 1000.0))) + ' هزار'

def _pct(xs, p):
    xs = sorted(xs); k = (len(xs) - 1) * p; f = math.floor(k); c = math.ceil(k)
    return xs[int(k)] if f == c else xs[f] + (xs[c] - xs[f]) * (k - f)

# ------------------------------------------------------------------ 1) fair price
def fair_price(pid):
    po = D.product_offers(pid)
    if not po: return None
    per_shop = {}
    for o in po['offers']:
        if not o['price_toman'] or o['suspicious']: continue
        cur = per_shop.get(o['shop_id'])
        if cur is None or (cur['stale'] and not o['stale']) or (cur['stale'] == o['stale'] and o['price_toman'] < cur['price_toman']):
            per_shop[o['shop_id']] = o
    fresh = [o for o in per_shop.values() if not o['stale']]
    use = fresh if len(fresh) >= 3 else list(per_shop.values())
    prices = [o['price_toman'] for o in use]
    out = {'product_id': pid, 'n_sellers': len(prices), 'stale_included': len(use) != len(fresh), 'ok': False}
    if len(prices) < 3:
        return out
    q1, q3 = _pct(prices, .25), _pct(prices, .75); iqr = q3 - q1
    kept = [p for p in prices if q1 - 1.5 * iqr <= p <= q3 + 1.5 * iqr] if iqr > 0 else prices
    if len(kept) < 3: kept = prices
    p25, p75 = _pct(kept, .25), _pct(kept, .75)
    gouge = p75 + 0.5 * (p75 - p25)
    gouge = math.ceil(gouge / 100_000) * 100_000 if gouge >= 1_000_000 else math.ceil(gouge / 10_000) * 10_000
    lo_l, hi_l = money_short(p25), money_short(p75)
    unit_same = lo_l.split()[-1] == hi_l.split()[-1]
    label = f"قیمت منصفانه حدود {hi_l}" if lo_l == hi_l else f"قیمت منصفانه {lo_l.rsplit(' ', 1)[0] if unit_same else lo_l} تا {hi_l}"
    out.update(ok=True, lo=min(kept), hi=max(kept), p25=int(p25), p75=int(p75), gouge=int(gouge), median=int(_pct(kept, .5)),
               n_used=len(kept), n_outliers=len(prices) - len(kept), label=label,
               gouge_label=f"بیشتر از {money_short(gouge).replace(' میلیون', '') if gouge >= 1_000_000 and p75 >= 1_000_000 else money_short(gouge)} گرونه",
               lo_label=money_short(min(kept)), hi_label=money_short(max(kept)))
    return out

# ------------------------------------------------------------------ 5/6) «چی بپرسم؟» + authenticity (static)
GROUPS = [
    ('phone', ('گوشی موبایل', 'گوشی شیائومی', 'گوشی سامسونگ', 'گوشی اپل', 'موبایل'), ['گارانتی چند ماهه و مال کدوم شرکته؟', 'رجیستری شده؟ کد فعال‌سازی رو نشون بده', 'پلمپه یا کارکرده/اوپن‌باکس؟', 'نسخهٔ کدوم کشوره و شارژر توی جعبه هست؟']),
    ('laptop', ('لپ تاپ', 'نوت بوک'), ['پردازنده، رم و حافظه دقیقاً همینه؟', 'گارانتی چیه و تعمیرش کجاست؟', 'نو و پلمپه یا استوک؟', 'باتری و آداپتور اصلیه؟']),
    ('headphone', ('هدفون', 'هندزفری', 'هدست', 'ایرپاد'), ['اصلیه یا های‌کپی؟', 'گارانتی تعویض داره؟', 'قبل از خرید وصلش کنم و تست کنم؟', 'کیس شارژ و کابلش توی جعبه هست؟']),
    ('charger', ('شارژر', 'پاوربانک', 'آداپتور'), ['توانش چند واته و با گوشی من فست‌شارژ می‌کنه؟', 'اصلیه یا طرح اصلی؟', 'گارانتی تعویض داره؟', 'کابلش همراهشه؟']),
    ('cable', ('کابل',), ['چه نوع سری داره و چند متره؟', 'از فست‌شارژ و انتقال داده پشتیبانی می‌کنه؟', 'گارانتی تعویض داره؟']),
    ('watch', ('ساعت',), ['اصلیه؟ کارت گارانتی و جعبه داره؟', 'گارانتی چند ساله و نمایندگیش کجاست؟', 'باتری یا موتورش کجای کاره؟', 'بند رو می‌شه کوتاه کرد؟']),
    ('perfume', ('عطر', 'ادکلن', 'ادو پرفیوم', 'ادو تویلت'), ['اورجینال و پلمپه یا تستر؟', 'کد بچ روی جعبه با شیشه یکیه؟', 'می‌شه اول تست کنم؟', 'حجمش دقیقاً چند میله؟']),
    ('sofa', ('مبل',), ['جنس اسکلت و پارچه چیه؟', 'ابعاد دقیقش چقدره و از در خونه رد می‌شه؟', 'ارسال و نصب رایگانه؟', 'ضمانت اسکلت و فوم چند ساله؟']),
    ('kitchen', ('یخچال', 'ماشین ظرفشویی', 'اجاق', 'گاز', 'مایکروفر', 'سرخ کن', 'چای ساز', 'قهوه ساز', 'آشپزخانه', 'ماشین لباسشویی', 'جاروبرقی'), ['گارانتی چند ساله و کدوم شرکته؟', 'برچسب انرژیش چیه؟', 'ارسال و نصب رایگانه؟', 'نو و پلمپه یا نمایشگاهی؟']),
    ('cctv', ('دوربین مدار بسته', 'دی وی آر', 'ان وی آر', 'دزدگیر'), ['دید در شب و رزولوشن واقعیش چقدره؟', 'روی گوشی تصویر می‌ده؟', 'نصب و کابل‌کشی با خودتونه؟', 'گارانتی چند ماهه؟']),
]
GENERIC = ['گارانتی داره؟ چند ماه و کدوم شرکت؟', 'نو و پلمپه؟', 'اگه مشکل داشت، تعویض می‌کنید؟']
AUTH = [
    (('اپل', 'apple', 'ایرپاد', 'airpods', 'آیفون', 'iphone'), ['شمارهٔ سریال رو روی سایت اپل چک کن', 'با آیفون جفت کن؛ پنجرهٔ اتصال اصلی باید بیاد', 'جعبه و چاپش باید تمیز و بدون غلط باشه', 'قیمت خیلی پایین‌تر از بازه یعنی احتمال کپی']),
    (('سامسونگ', 'samsung', 'گلکسی'), ['سریال و IMEI جعبه با خود دستگاه یکی باشه', 'کد فعال‌سازی و رجیستری رو چک کن', 'شارژر و کابل اصلی آرم و چاپ دقیق دارن']),
    (('عطر', 'ادکلن', 'پرفیوم', 'تویلت'), ['کد بچ کف شیشه و روی جعبه یکی باشه', 'سلفون جعبه صاف و بدون چسب اضافه باشه', 'درِ شیشه سفت و بدون لق باشه', 'قیمت خیلی پایین‌تر از بازه یعنی احتمال تقلبی']),
    (('ساعت',), ['کارت گارانتی با سریال پشت ساعت یکی باشه', 'حکاکی‌ها تمیز و دقیق باشه', 'از نمایندگی رسمی بپرس']),
]
def _group(cat, title):
    t = (cat or '') + ' ' + (title or '')
    for key, kws, qs in GROUPS:
        if any(k in (cat or '') for k in kws): return key, qs
    for key, kws, qs in GROUPS:
        if any(k in t for k in kws): return key, qs
    return 'generic', GENERIC

def _auth_hints(brand, cat, title):
    t = ' '.join([brand or '', cat or '', title or '']).lower()
    for kws, hints in AUTH:
        if any(k.lower() in t for k in kws):
            if kws[0] == 'ساعت' and 'ساعت هوشمند' in t and 'اپل' not in t: return []
            return hints
    return []

def before_buy(pid):
    head = D.product_head(pid)
    if not head: return None
    g, qs = _group(head['category'], head['title'])
    return {'product_id': pid, 'fair': fair_price(pid), 'group': g, 'questions': qs[:4], 'auth': _auth_hints(head['brand'], head['category'], head['title']),
            'auth_note': 'این فقط راهنماست، نه تشخیص قطعی', 'llm_calls': 0}

# ------------------------------------------------------------------ mall keys for all shops (cached)
_MK = None; _MK_LOCK = threading.Lock()
def _mall_index():
    global _MK
    with _MK_LOCK:
        if _MK is None:
            idx = {}
            for sid, addr in q('SELECT shop_id, address FROM shops WHERE address IS NOT NULL'):
                try:
                    p = MG.parse(addr)
                except Exception:
                    continue
                if p.get('in_mall') and p.get('mall'):
                    idx[sid] = {'key': MG.mall_key(p['mall']), 'mall': p['mall'], 'floor': p.get('floor'), 'unit': p.get('unit')}
            _MK = idx
    return _MK

def _unit_num(u):
    m = re.search(r'\d+', (u or {}).get('label', '').translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹', '0123456789')))
    return int(m.group(0)) if m else 10 ** 6

def _where(info):
    f = (info.get('floor') or {}).get('label') or 'طبقهٔ نامشخص'
    u = (info.get('unit') or {}).get('label') or 'واحد نامشخص'
    return f'{f}، {u}'

# ------------------------------------------------------------------ 2) other shops in the same mall with this product
def mall_mates(sid, pid):
    idx = _mall_index(); me = idx.get(sid)
    if not me: return {'shop_id': sid, 'in_mall': False, 'stops': [], 'n_other': 0}
    po = D.product_offers(pid) if pid else None
    best = {}
    for o in (po or {}).get('offers', []):
        if o['shop_id'] in idx and idx[o['shop_id']]['key'] == me['key']:
            cur = best.get(o['shop_id'])
            if cur is None or ((o['price_toman'] or 1e18) < (cur['price_toman'] or 1e18)): best[o['shop_id']] = o
    stops = []
    for s_, o in best.items():
        info = idx[s_]; lvl = (info.get('floor') or {}).get('level')
        stops.append({'shop_id': s_, 'name': o['shop_name'], 'where': _where(info), 'floor_level': lvl, 'is_current': s_ == sid,
                      'price_toman': o['price_toman'] if not o.get('suspicious') else None,
                      'price_label': D.fa_money(o['price_toman']) if o.get('price_toman') and not o.get('suspicious') else 'نامشخص',
                      '_k': (2 if lvl is None else (1 if lvl < 0 else 0), abs(lvl) if lvl is not None else 0, _unit_num(info.get('unit')))})
    stops.sort(key=lambda x: x.pop('_k'))
    n = len(stops) - (1 if sid in best else 0)
    return {'shop_id': sid, 'in_mall': True, 'mall': me['mall'], 'mall_key': me['key'], 'stops': stops, 'n_other': n,
            'label': f'{fa(n)} مغازهٔ دیگه توی همین پاساژ' if n > 0 else None, 'facts': mall_facts_for(me['mall']), 'llm_calls': 0}

# ------------------------------------------------------------------ 3) alternatives right here (same shop -> same mall -> nearby)
def alts_here(sid, pid, k=8):
    head = D.product_head(pid)
    if not head: return None
    fp = fair_price(pid); ref = (fp or {}).get('median') or (D.product_offers(pid) or {}).get('median_price') or (D.product_offers(pid) or {}).get('min_price')
    cat = head['category']
    lo, hi = (ref * 0.6, ref * 1.5) if ref else (0, 1e18)
    idx = _mall_index(); me = idx.get(sid)
    srow = q('SELECT lat, lon FROM shops WHERE shop_id=?', (sid,)); slat, slon = (srow[0] if srow else (None, None))
    rows = q('''SELECT o.product_id, p.persian_title, p.image_urls, o.shop_id, s.name, o.price_toman, s.lat, s.lon
                FROM offers o JOIN products p USING(product_id) JOIN shops s USING(shop_id)
                WHERE p.category_name=? AND o.product_id<>? AND o.price_toman BETWEEN ? AND ? LIMIT 4000''', (cat, pid, lo, hi))
    same, mall, near = [], [], []
    seen = set()
    def item(r, where):
        return {'product_id': r[0], 'title': r[1], 'image': D._img(r[2]), 'shop_id': r[3], 'shop_name': r[4], 'price_toman': int(r[5]),
                'price_label': D.fa_money(r[5]), 'where': where}
    tn = D.norm(head['title']) if hasattr(D, 'norm') else head['title']
    rows = [r for r in rows if (D.norm(r[1]) if hasattr(D, 'norm') else r[1]) != tn]      # a different listing of the very same item is not an alternative
    rows = sorted(rows, key=lambda r: abs((r[5] or 0) - (ref or 0)))
    for r in rows:
        if r[0] in seen: continue
        if r[3] == sid:
            same.append(item(r, 'همین مغازه')); seen.add(r[0])
        elif me and r[3] in idx and idx[r[3]]['key'] == me['key']:
            mall.append(item(r, 'مغازهٔ کناری')); seen.add(r[0])
    if slat is not None:
        cand = []
        for r in rows:
            if r[0] in seen or r[6] is None or r[3] == sid: continue
            d = (r[6] - slat) ** 2 + ((r[7] - slon) * 0.81) ** 2
            if d < 0.0045 ** 2 * 4:            # roughly a short walk (used for ordering/filter only; never shown)
                cand.append((d, r))
        for d, r in sorted(cand, key=lambda x: x[0]):
            if r[0] in seen: continue
            near.append(item(r, 'همین نزدیکی')); seen.add(r[0])
            if len(near) >= k: break
    return {'shop_id': sid, 'product_id': pid, 'same_shop': same[:k], 'neighbours': (mall + near)[:k], 'llm_calls': 0}

# ------------------------------------------------------------------ 9) mall facts (supplementary, cited)
_MF = {'mt': None, 'd': {}}
_STRICT = {'kian', 'yegane', 'naderi', 'etehadiyeh'}
def _nk(s):
    s = (s or '').replace('\u200c', '').replace(' ', '')
    s = re.sub(r'[ءئأإؤ]', '', s).replace('ي', 'ی').replace('ك', 'ک').translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹', '0123456789'))
    return s
def _facts_file():
    p = os.path.join(HERE, 'mall_facts.json')
    try:
        mt = os.path.getmtime(p)
    except OSError:
        return {}
    if _MF['mt'] != mt:
        try: _MF['d'] = json.load(open(p)); _MF['mt'] = mt
        except Exception: return {}
    return _MF['d']

_FLAB = [('parking', 'پارکینگ'), ('entrances', 'ورودی'), ('metro', 'مترو'), ('tips', 'نکته')]
def mall_facts_for(mall_name):
    d = _facts_file()
    if not d or not mall_name: return None
    mn = _nk(mall_name)
    for key, v in d.items():
        names = [v.get('name') or ''] + list(v.get('aliases') or [])
        hit = False
        for a in names:
            a2 = _nk(a)
            if not a2: continue
            if key in _STRICT:
                bare = _nk(re.sub(r'^(پاساژ|مجتمع|بازار)\s*', '', a))
                if mn in (_nk('پاساژ' + bare), _nk('پاساژ' + bare + '2')) or mn == _nk(a) and a.startswith('پاساژ'): hit = True
            elif a2 in mn or mn.endswith(a2): hit = True
            if hit: break
        if not hit: continue
        rows = []
        for f, lab in _FLAB:
            for it in (v.get(f) or [])[:2]:
                if isinstance(it, dict) and it.get('text') and it.get('source_url'):
                    rows.append({'kind': f, 'label': lab, 'text': _clean(it['text']), 'source_url': it['source_url'], 'host': re.sub(r'^https?://(www\.)?([^/]+).*', r'\2', it['source_url'])})
        hn = v.get('hours_note')
        if isinstance(hn, dict) and hn.get('text') and hn.get('source_url'):
            t = _clean(hn['text']); t = t if t.startswith('معمولاً') else 'معمولاً ' + t[0:1].replace('ب', 'ب') + t[1:]
            rows.append({'kind': 'hours', 'label': 'ساعت کاری', 'text': t, 'source_url': hn['source_url'], 'host': re.sub(r'^https?://(www\.)?([^/]+).*', r'\2', hn['source_url'])})
        return {'mall_key': key, 'name': v.get('name'), 'rows': rows} if rows else None
    return None

# ------------------------------------------------------------------ 7) photo → product
_TOK = re.compile(r'[A-Za-z0-9]+|[\u0600-\u06FF]{2,}')
def match_text(text, k=3):
    """brand/model string -> DB products via FTS (no model): OR query, then token coverage on the title; accessories last.
    confident = one main product covers clearly more of the label than the next one"""
    stop = {'by', 'the', 'and', 'for', 'with', 'model', 'mod', 'new', 'مدل', 'برند', 'رنگ'}
    toks = [t.lower() for t in _TOK.findall(text or '') if len(t) >= 2 and t.lower() not in stop][:8]
    if not toks: return {'status': 'not_found', 'candidates': []}
    expr = ' OR '.join('"%s"' % t.replace('"', '') for t in toks)
    try:
        res = q('SELECT product_id, bm25(products_fts) FROM products_fts WHERE products_fts MATCH ? ORDER BY bm25(products_fts) LIMIT 60', (expr,))
    except Exception:
        res = []
    if not res: return {'status': 'not_found', 'candidates': [], 'query': ' '.join(toks)}
    pids = [r[0] for r in res]
    info = {pid: (t or '', (b_ or '') + ' ' + (m_ or '')) for pid, t, b_, m_ in q('SELECT product_id, persian_title, brand_name, model FROM products WHERE product_id IN (%s)' % ','.join('?' * len(pids)), pids)}
    have = {r[0]: r[1] for r in q('SELECT product_id, COUNT(*) FROM offers WHERE product_id IN (%s) GROUP BY product_id' % ','.join('?' * len(pids)), pids)}
    acc = ('قاب', 'گلس', 'فلت', 'محافظ', 'کاور', 'شاسی', 'باتری', 'تاچ', 'برد', 'درب', 'کابل', 'بند', 'کیف', 'هولدر', 'پایه', 'ال', 'شیشه', 'بازر', 'اسپیکر', 'battery', 'flat', 'lcd', 'glass', 'case', 'cover', 'باطری')
    def is_acc(pid):
        w = info.get(pid, ('', ''))[0].lower().split()[:2]
        return any(x in acc for x in w) and not any(a_ in (text or '') for a_ in acc)
    def cov(pid):
        t = (info.get(pid, ('', ''))[0] + ' ' + info.get(pid, ('', ''))[1]).lower()
        return sum(1 for x in toks if x in t)
    bm = dict(res)
    knock = ('کپی', 'مستر کوالیتی', 'طرح اصلی', 'های کپی', 'master', 'copy', 'replica')
    is_knock = lambda p_: any(k in info.get(p_, ('', ''))[0].lower() for k in knock)
    ranked = sorted(pids, key=lambda p_: (1 if is_acc(p_) else 0, 1 if is_knock(p_) else 0, -cov(p_) // 2, -min(have.get(p_, 0), 30), -cov(p_), bm[p_]))
    digit_toks = [x for x in toks if re.search(r'\d', x)]      # model numbers must match exactly
    def has_digits(p_):
        t = (info.get(p_, ('', ''))[0] + ' ' + info.get(p_, ('', ''))[1]).lower()
        return all(x in t for x in digit_toks)
    main = [p_ for p_ in ranked if not is_acc(p_) and has_digits(p_) and cov(p_) >= max(1, math.ceil(len(toks) * 0.66))]
    if not main: return {'status': 'not_found', 'candidates': [], 'query': ' '.join(toks)}
    h0, h1 = have.get(main[0], 0), (have.get(main[1], 0) if len(main) > 1 else 0)
    conf = bool(digit_toks) and not is_knock(main[0]) and h0 >= 3 and (len(main) == 1 or h0 >= 2 * max(1, h1))
    cands = []
    for pid in (main[:1] if conf else main[:k]):
        h = D.product_head(pid); fp = fair_price(pid)
        cands.append({'product_id': pid, 'title': h['title'], 'image': h['image'], 'fair_label': fp.get('label') if fp and fp.get('ok') else None})
    return {'status': 'match' if conf else 'unsure', 'candidates': cands, 'query': ' '.join(toks)}

_VPROMPT = ('You read a photo of a product label/box taken in a Tehran shop. Reply ONLY JSON: {"brand": "...", "model": "...", "product_type": "..."} '
            'using the exact text printed on the label (Latin as printed). Empty strings if unreadable. No other text.')
def identify(image_data_url, text=''):
    if not _H['can_spend'] or not _H['can_spend'](0.006):
        return {'status': 'spend_cap', 'candidates': [], 'llm_calls': 0}
    cl = _H['client_fn']()
    t0 = time.time()
    r = cl.chat.completions.create(model='gpt-6-luna', max_completion_tokens=200, response_format={'type': 'json_object'},
                                   messages=[{'role': 'system', 'content': _VPROMPT},
                                             {'role': 'user', 'content': [{'type': 'text', 'text': (text or 'این چیه؟')[:200]}, {'type': 'image_url', 'image_url': {'url': image_data_url}}]}])
    try:
        cost = float(((r.model_dump() or {}).get('usage') or {}).get('cost') or 0)
    except Exception:
        cost = 0.0
    if not cost and getattr(r, 'usage', None) is not None:      # gateway omitted cost: conservative estimate so the cap still counts it
        cost = (r.usage.prompt_tokens * 2.0 + r.usage.completion_tokens * 10) / 1e6
    if _H['add_spend']: _H['add_spend'](cost)
    try: j = json.loads(r.choices[0].message.content or '{}')
    except Exception: j = {}
    qtxt = ' '.join(x for x in (j.get('brand'), j.get('model')) if x)
    out = match_text(qtxt) if qtxt else {'status': 'not_found', 'candidates': []}
    out.update(read={'brand': j.get('brand') or None, 'model': j.get('model') or None}, llm_calls=1, cost_usd=round(cost, 6), latency_s=round(time.time() - t0, 1))
    return out

def chat_reply(res):
    """identify/match result -> chat message (R shape): DB cards + fair band; unsure/none -> ask, never guess"""
    st, cands = res.get('status'), res.get('candidates') or []
    pids = [c['product_id'] for c in cands]
    blocks = []
    if pids and _H['hydrate_fn']:
        try: blocks = _H['hydrate_fn'](pids)
        except Exception: blocks = []
    if not blocks and pids:
        blocks = [{'type': 'product_cards', 'items': [{'product_id': p_, 'title': c['title'], 'image': c['image']} for p_, c in zip(pids, cands)]}]
    if st == 'match' and cands:
        c = cands[0]
        text = (c['fair_label'] + '.') if c.get('fair_label') else 'این مدل رو پیدا کردم.'
        return {'ok': True, 'text': text, 'blocks': blocks, 'instore': {'kind': 'photo', 'status': 'match', 'product_id': c['product_id']}, 'suggestions': []}
    if st == 'unsure' and cands:
        return {'ok': True, 'text': 'مطمئن نیستم کدوم مدله؛ اگه یکی از اینهاست بازش کن، وگرنه مدلش رو بنویس یا یه عکس واضح‌تر از برچسب بفرست.', 'blocks': blocks,
                'instore': {'kind': 'photo', 'status': 'unsure'}, 'suggestions': []}
    if st == 'spend_cap':
        return {'ok': True, 'text': 'الان نمی‌تونم عکس رو بخونم؛ مدلش رو بنویس تا پیداش کنم.', 'blocks': [], 'instore': {'kind': 'photo', 'status': 'spend_cap'}, 'suggestions': []}
    return {'ok': True, 'text': 'این مدل رو توی ترب پیدا نکردم؛ مدلش رو بنویس یا یه عکس واضح‌تر از برچسب بفرست.', 'blocks': [], 'instore': {'kind': 'photo', 'status': 'not_found'}, 'suggestions': []}

# ------------------------------------------------------------------ «پیش از خرید» advice: ONE model call with the shopper/product/shop context
_ASYS = """You help a shopper who is standing in a physical shop in Tehran, about to buy one product. You get JSON context: product facts from the price-comparison database, a fair-price band computed from real offers, optional shop facts from the database, optional prices the shopper noted from sellers today, and a short summary of what the shopper said in the conversation.
Write in casual, friendly Persian (محاوره‌ای), short lines.
Return ONLY one JSON object: {"questions": [3 to 5 short questions the shopper should ask THIS seller about THIS product], "tips": [2 to 4 short «حواست باشه» tips]}.
Rules:
- Personalise to the product, its category/brand and the shopper's need (e.g. their phone model for a charger: compatibility, fast-charge standard, wattage).
- Tips are general guidance about this kind of product (how to check it, what to compare, typical tricks to watch for). Include an authenticity check when the brand/category is commonly counterfeited, phrased as a general tip («معمولاً…»، «چک کن…»), never as a verdict.
- Never claim anything about this specific shop or seller (never imply it sells fakes or overcharges). No shop names in tips.
- Never invent prices, stock, shop names or specs not in the context. You may refer to the fair band only with the given label text. If shopper notes are above the band's upper limit, one tip may say to compare/negotiate, without new numbers.
- Never use the word «موجود» or «ناموجود». No distances in kilometres. No phone numbers or links. No disclaimers, no emojis, no markdown.
- Each item max ~14 words."""
_ACACHE = {}
_BANNED = re.compile(r'موجود|ناموجود|https?://|tel:|\d{7,}')
def _sanitize_list(xs, lo, hi):
    out = []
    for x in xs if isinstance(xs, list) else []:
        if not isinstance(x, str): continue
        t = _clean(re.sub(r'\s+', ' ', x)).strip(' -•*')
        t = re.sub(r'[0-9۰-۹]+(?:[.٫][0-9۰-۹]+)?\s*(?:کیلومتر|km)', '', t)
        if not t or _BANNED.search(t) or len(t) > 140: continue
        out.append(t)
    return out[:hi] if len(out) >= lo else None

def _shop_ctx(sid):
    if not sid: return None
    r = q('SELECT name, address, category_names FROM shops WHERE shop_id=?', (sid,))
    if not r: return None
    name, addr, cats = r[0]
    info = _mall_index().get(sid) or {}
    hrs = None
    try:
        import playground_mall as MALL
        st = MALL.status(sid) or {}
        hrs = st.get('badge') or 'نامشخص'
    except Exception:
        pass
    return {'name': name, 'mall': info.get('mall'), 'where': _where(info) if info else None, 'categories': (cats or '')[:120] or None, 'hours_today': hrs}

def advice(pid, shop_id=None, notes=None, need=None, sid=None):
    head = D.product_head(pid)
    if not head: return None
    notes = [n for n in (notes or []) if isinstance(n, dict) and isinstance(n.get('price'), (int, float))][:6]
    conv = ''
    if sid and _H['session_fn']:
        try: conv = _H['session_fn'](sid) or ''
        except Exception: conv = ''
    need = (need or '').strip()[:200]
    key = (pid, shop_id or '', json.dumps(notes, sort_keys=True, ensure_ascii=False), need, conv[-300:])
    if key in _ACACHE: return dict(_ACACHE[key], cached=True)
    g, qs = _group(head['category'], head['title'])
    fb = {'questions': qs[:4], 'tips': _auth_hints(head['brand'], head['category'], head['title'])[:3] or ['قبل از پرداخت، جعبه و پلمپ رو جلوی خودت باز و تست کن', 'برگهٔ گارانتی و فاکتور رو بگیر'], 'source': 'fallback', 'llm_calls': 0, 'cost_usd': 0.0}
    if not _H['can_spend'] or not _H['can_spend'](0.004) or not _H['client_fn']:
        return fb
    fp = fair_price(pid)
    ctx = {'product': {'title': head['title'], 'brand': head['brand'], 'category': head['category'], 'model': head.get('model')},
           'fair_price': {'label': fp.get('label'), 'upper_limit_label': fp.get('gouge_label'), 'n_sellers': fp.get('n_sellers')} if fp and fp.get('ok') else {'note': 'not enough prices', 'n_sellers': (fp or {}).get('n_sellers')},
           'shop': _shop_ctx(shop_id), 'shopper_notes_today': [{'shop': n.get('name'), 'price_toman': int(n['price'])} for n in notes] or None,
           'shopper_said': (need + ' ' + conv).strip()[-600:] or None}
    t0 = time.time()
    try:
        r = _H['client_fn']().chat.completions.create(model='gpt-6-luna', max_completion_tokens=450, reasoning_effort='none', response_format={'type': 'json_object'},
                                                      messages=[{'role': 'system', 'content': _ASYS}, {'role': 'user', 'content': json.dumps(ctx, ensure_ascii=False)}], timeout=15)
    except Exception as e:
        print('advice call failed:', type(e).__name__, str(e)[:160], flush=True)
        return fb
    try: cost = float(((r.model_dump() or {}).get('usage') or {}).get('cost') or 0)
    except Exception: cost = 0.0
    if not cost and getattr(r, 'usage', None) is not None:
        cost = (r.usage.prompt_tokens * 2.0 + r.usage.completion_tokens * 10) / 1e6
    if _H['add_spend']: _H['add_spend'](cost)
    try: j = json.loads(r.choices[0].message.content or '{}')
    except Exception: j = {}
    qs2, tips2 = _sanitize_list(j.get('questions'), 3, 5), _sanitize_list(j.get('tips'), 2, 4)
    if not qs2 or not tips2:
        return dict(fb, llm_calls=1, cost_usd=round(cost, 6))
    out = {'questions': qs2, 'tips': tips2, 'source': 'ai', 'llm_calls': 1, 'cost_usd': round(cost, 6), 'latency_s': round(time.time() - t0, 1)}
    _ACACHE[key] = out
    return out

@router.post('/api/product/{pid}/advice')
async def api_advice(pid: str, req: Request):
    _auth(req); b = await req.json()
    import asyncio
    r = await asyncio.get_running_loop().run_in_executor(None, lambda: advice(pid[:64], (b.get('shop_id') or '')[:64] or None, b.get('notes'), b.get('need'), (b.get('sid') or '')[:64] or None))
    if not r: raise HTTPException(404, 'product not found')
    return r

# ------------------------------------------------------------------ routes
@router.get('/api/product/{pid}/before_buy')
def api_before_buy(pid: str, req: Request):
    _auth(req); r = before_buy(pid[:64])
    if not r: raise HTTPException(404, 'product not found')
    return r

@router.get('/api/shop/{sid}/mallmates')
def api_mallmates(sid: str, req: Request, pid: str = ''):
    _auth(req); return mall_mates(sid[:64], pid[:64] or None)

@router.get('/api/shop/{sid}/alts_here')
def api_alts_here(sid: str, req: Request, pid: str = ''):
    _auth(req); r = alts_here(sid[:64], pid[:64])
    if not r: raise HTTPException(404, 'product not found')
    return r

@router.get('/api/instore/match')
def api_match(req: Request, q_: str = ''):
    _auth(req); return match_text((req.query_params.get('q') or q_)[:120])

@router.post('/api/instore/identify')
async def api_identify(req: Request):
    _auth(req); b = await req.json()
    img = str(b.get('image') or '')
    if not img.startswith('data:image/') or len(img) > 6_000_000: raise HTTPException(400, 'image data url required')
    import asyncio
    def run():
        try:
            res = identify(img, str(b.get('text') or ''))
        except Exception as e:
            print('instore identify failed:', type(e).__name__, str(e)[:200], flush=True)
            res = {'status': 'not_found', 'candidates': [], 'error': type(e).__name__}
        out = chat_reply(res)
        out['metrics'] = {'llm_calls': res.get('llm_calls', 0), 'cost_usd': res.get('cost_usd', 0.0)}
        out['read'] = res.get('read')
        return out
    return await asyncio.get_running_loop().run_in_executor(None, run)

@router.get('/api/instore/match_chat')
def api_match_chat(req: Request):
    """offline: the same chat reply from a typed brand/model ($0)"""
    _auth(req); return chat_reply(match_text((req.query_params.get('q') or '')[:120]))
