"""Torob shopping assistant V3+ (round 2) — same V3 architecture (one agent loop over the read-only DB; the server
hydrates ids), with judgements moved from the model to deterministic server code:

1. FACTS: every offer/product the model sees carries computed fields (age_days, stale >30 d, suspicious <40 % of the
   product's median — or of its model family's median when the product has <3 priced offers —, min/median price,
   cheapest up-to-date offer, distance_km). The model never writes prices, dates, ages, distances or «قدیمی/مشکوک»:
   it writes tokens [[offer:ID]] / [[product:ID]] and the server renders them from those fields.
2. find_products: one generic constraint search (need text → categories, price range, sort price|popularity,
   area = region box or place+radius, required terms in title/specs, exclude ids, cheaper_than a reference product),
   diverse by model family/brand, with thin-area fallback (nearest options outside the area, labelled) and the
   cheapest qualifying items always attached.
3. CLAIM CHECK + COVERAGE: after the final answer the server validates comparative/superlative/freshness/suspicion
   words and "nothing cheaper/fresher" claims against the facts, and checks budget/cheapest/cheaper answers against a
   direct SQL ground truth (same constraints, sort=price). Violations → ONE regeneration with the evidence; whatever
   still fails is stripped (claims) or appended deterministically (missed cheaper items).
4. PROVENANCE: product_knowledge returns facts with ids and a source tag (db_spec / other_listing / public_reference).
   Spec claims are written as [[spec:<fact_id>|…]] or [[spec:gen|…]]; the label is added by the renderer from the tag
   after a content check. Any Torob attribution written by the model itself is removed.

agent_v3.py is NOT modified (a separate instance of its code is loaded and reused: sql/text_search/geocode tools,
hydration, parsing, fallback). API: run_agent_v3plus(messages_or_question, session_mission=None, user_lat=None, user_lon=None)
"""
import importlib.util, json, os, re, statistics, threading, time, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location('agent_v3_plusbase', os.path.join(HERE, 'agent_v3.py'))
B = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(B)
T = B.T
norm = B.norm

B.STALE_DAYS = 30
B.SUSPICIOUS_RATIO = 0.4
MODEL = B.MODEL
MAX_STEPS = 2                      # speed, enforced in code: round 1 = tools (parallel), round 2 = answer; a 2nd tool round only if round 1 found nothing; hard max 3 LLM rounds
MAX_COMPLETION_TOKENS = 1200
LLM_STEP_TIMEOUT_S = 10.0
TURN_SOFT_S = 22.0
TURN_FINAL_BY_S = 34.0
TURN_BUDGET_S = 40.0
REGEN_IF_BEFORE_S = 27.0          # one regeneration only if the turn is younger than this
WIKI_TIMEOUT_S = 4.0
COST = B.COST
RO = B.RO
B.TURN_BUDGET_S = TURN_BUDGET_S    # used by v3's _fallback

KNOWLEDGE_LABEL = 'طبق مشخصات عمومی سازنده (نه داده‌های ترب)'
DB_LABEL = 'طبق مشخصات ثبت‌شده در ترب'
SIBLING_LABEL = 'طبق مشخصات آگهی دیگری از همین مدل در ترب'
HOURS_LABEL = 'ساعت ثبت‌شده؛ تعطیلی‌ها لحاظ نشده'
DRAFT_LABEL = 'فقط پیش‌نویس — تماس واقعی انجام نشد'

_P = open(os.path.join(HERE, 'v3plus_prompt.txt'), encoding='utf-8').read()
TRUTHS_PLUS = _P.split('=====TRUTHS=====')[1].split('=====SYSTEM=====')[0].strip()
SYSTEM_PLUS = _P.split('=====SYSTEM=====')[1].strip()
# v3 schema card without the browse/alternatives examples (5-7): find_products does those deterministically now
SCHEMA_PLUS = re.sub(r'\n5\) browse a category.*?(?=\n8\) )', '\n', B.SCHEMA_CARD, flags=re.S)

_RUN = threading.local()
def _run(k, default=None):
    return getattr(_RUN, k, default)


# ================================================================== 1. deterministic facts
def _fa(x):
    return B._fa_digits(x)

def fmt_toman(v):
    return _fa(format(int(v), ',').replace(',', '٬')) + ' تومان'

def fmt_km(k):
    return _fa(f'{k:.1f}'.replace('.', '٫')) if k < 10 else _fa(str(int(round(k))))

_FAM_STOP = set(norm(w) for w in '''گوشی موبایل هدفون هدست هندزفری بی سیم بیسیم بلوتوثی بلوتوث مدل برند لپ تاپ نوت بوک ساعت هوشمند تبلت اسپیکر
 دسته بازی کنسول با و ظرفیت حافظه رم گیگابایت ترابایت اینچ دو سیمکارت سیم‌کارت نسخه رنگ سری جدید اصلی اورجینال روگوشی رو دورگوشی تو گوش'''.split())

def family_key(title, brand):
    """model family: brand + first alphanumeric model code (a17, t13, wh-1000xm5, v15) or the model number (16)."""
    t = norm(title or '').split('|')[0]
    t = re.sub(r'\(.*?\)', ' ', t)
    toks = [w for w in re.split(r'[\s،,/]+', t) if w]
    code = next((w for w in toks if re.search(r'\d', w) and re.search(r'[a-z]', w) and not re.fullmatch(r'\d+(gb|g|tb|mah|w|hz|mm)', w)), None)
    if not code:
        code = next((w for w in toks if re.fullmatch(r'\d{1,4}', w)), None)
    lead = norm(brand or '') or next((w for w in toks if re.fullmatch(r'[a-z]+', w)), '') or next((w for w in toks if w not in _FAM_STOP), '')
    if code and re.search(r'[a-z]', code):
        m = re.match(r'[a-z\-]*\d+', code)          # generation suffixes belong to the family: t13x→t13, a30i→a30
        return 'm:' + (m.group(0) if m else code)     # brand-independent (brand names are inconsistent in the data)
    if not code:
        code = ' '.join([w for w in toks if w not in _FAM_STOP and w != lead][:2])
    return f'{lead}:{code}'

_PCACHE = {}
def product_facts(pid):
    """min/median price, cheapest non-suspicious offer, cheapest up-to-date offer, latest change (cached per turn)."""
    if pid in _PCACHE:
        return _PCACHE[pid]
    r = RO.execute('SELECT persian_title,brand_name,category_name FROM products WHERE product_id=?', (pid,)).fetchone()
    if not r:
        return None
    rows = RO.execute('SELECT offer_id,price_toman,last_price_changed_at,shop_id FROM offers WHERE product_id=? AND price_toman IS NOT NULL', (pid,)).fetchall()
    ps = [x[1] for x in rows]
    med = statistics.median(ps) if ps else None
    fam = family_key(r[0], r[1])
    ref_med = med if len(ps) >= 3 else _family_median(fam, r[2])
    def flags(o):
        age = B._days_ago(o[2])
        return {'offer_id': o[0], 'price': int(o[1]), 'date_fa': B._jalali(o[2]) if o[2] else None, 'date': (o[2] or '')[:10],
                'age_days': int(age) if age is not None else None, 'stale': age is not None and age > B.STALE_DAYS,
                'suspicious': bool(ref_med) and o[1] < B.SUSPICIOUS_RATIO * ref_med, 'shop_id': o[3]}
    offs = sorted((flags(o) for o in rows), key=lambda x: x['price'])
    ok = [o for o in offs if not o['suspicious']]
    fresh = [o for o in ok if not o['stale']]
    d = {'product_id': pid, 'title': r[0], 'brand': r[1], 'category': r[2], 'family': fam, 'n_priced': len(ps),
         'n_shops': len({o[3] for o in rows}), 'median_price': int(med) if med else None, 'reference_median': int(ref_med) if ref_med else None,
         'min_price_offer': ok[0] if ok else None, 'cheapest_fresh_offer': fresh[0] if fresh else None,
         'latest_change': max((o['date'] for o in offs), default=None), 'offers': offs}
    _PCACHE[pid] = d
    return d

_FMED = {}
def _family_median(fam, cat):
    k = (fam, cat)
    if k not in _FMED:
        rows = RO.execute('SELECT p.persian_title,p.brand_name,o.price_toman FROM products p JOIN offers o USING(product_id) WHERE p.category_name=? AND o.price_toman IS NOT NULL', (cat,)).fetchall()
        by = {}
        for t, b, pr in rows:
            by.setdefault(family_key(t, b), []).append(pr)
        for f, v in by.items():
            _FMED[(f, cat)] = statistics.median(v) if len(v) >= 3 else None
        _FMED.setdefault(k, None)
    return _FMED[k]

def offer_facts(oid):
    r = RO.execute('SELECT product_id,shop_id FROM offers WHERE offer_id=?', (oid,)).fetchone()
    if not r:
        return None
    pf = product_facts(r[0])
    o = next((x for x in pf['offers'] if x['offer_id'] == oid), None)
    if o is None:      # unpriced offer
        return {'offer_id': oid, 'product_id': r[0], 'shop_id': r[1], 'price': None}
    o = dict(o, product_id=r[0], product_median=pf['reference_median'])
    o['is_product_cheapest'] = bool(pf['min_price_offer']) and o['price'] <= pf['min_price_offer']['price'] and not o['suspicious']
    o['is_product_freshest'] = o['date'] == pf['latest_change']
    o['good_price'] = bool(pf['reference_median']) and not o['suspicious'] and o['price'] < 0.85 * pf['reference_median']
    pt = _run('point')
    if pt:
        s = RO.execute('SELECT lat,lon FROM shops WHERE shop_id=?', (r[1],)).fetchone()
        if s and s[0] is not None:
            o['km'] = round(T.haversine(pt[0], pt[1], s[0], s[1]), 2)
    return o

# text_search / product cards: add the computed fields (v3's _pstats keeps its own keys too)
_base_pstats = B._pstats
def _pstats(pid):
    d = _base_pstats(pid)
    pf = product_facts(pid)
    if pf:
        m, f = pf['min_price_offer'], pf['cheapest_fresh_offer']
        d['facts'] = {'cheapest_ok_offer': m and {k: m[k] for k in ('offer_id', 'price', 'date_fa', 'age_days', 'stale')},
                      'cheapest_fresh_offer': f and {k: f[k] for k in ('offer_id', 'price', 'date_fa', 'age_days')},
                      'family': pf['family']}
    return d
B._pstats = _pstats

# sql tool: every offer row gets its facts (not only flagged ones)
_base_sql = B.tool_sql
def tool_sql(query):
    res = _base_sql(query)
    if 'columns' in res:
        oc = [i for i, c in enumerate(res['columns']) if c.lower() in ('offer_id', 'oid')]
        if oc:
            facts = {}
            for row in res['rows'][:50]:
                v = row[oc[0]]
                if isinstance(v, str) and v.startswith('offer_'):
                    f = offer_facts(v)
                    if f and f.get('price') is not None:
                        facts[v] = {k: f[k] for k in ('age_days', 'stale', 'suspicious', 'is_product_cheapest') if k in f}
                        if 'km' in f: facts[v]['km'] = f['km']
            res.pop('offer_flags', None)
            res['offer_facts'] = facts
    return res


# ================================================================== 2. find_products (generic constraint search)
_USED = ('استوک', 'کارکرده', 'اوپن باکس', 'open box', 'دست دوم', 'refurbished', 'ریفربیش', 'stock', 'used')
_KNOCK = ('طرح', 'کپی', 'های کپی', 'غیر اصل', 'غیراصل', 'replica', 'master copy')

def _quality_ok(title, cat, include_used, acc_ok=False):
    tn = norm(title or '')
    head = ' '.join(tn.split()[:4])
    if not include_used and any(w in tn for w in _USED):
        return False
    if any(w in head for w in _KNOCK) or 'غیر اصل' in tn:
        return False
    first = ' '.join(tn.split()[:3])
    if acc_ok:      # the shopper asked for this accessory category itself (charger, case, cable…)
        return True
    if any(first.startswith(w) or f' {w} ' in f' {first} ' for w in T.ACCESSORY_WORDS) and not any(w in norm(cat or '') for w in ('هدفون', 'دسته بازی')):
        return False
    if T._cat_acc(cat, first):
        return False
    return True

_ALLCATS = None
_CAT_STOP = {'و', 'سایر', 'لوازم', 'انواع', 'محصولات', 'برای', 'از', 'با', 'در'}
_Q_STOP = {'یک', 'دو', 'سه', 'چهار', 'پنج', 'شش', 'هفت', 'هشت', 'نه', 'ده', 'نفره', 'تا', 'زیر', 'حدود', 'میلیون', 'هزار', 'تومان', 'تومن',
           'لوکس', 'مدرن', 'خوب', 'ارزان', 'ارزون', 'ارزانترین', 'بهترین', 'جدید', 'می\u200cخوام', 'میخوام', 'دنبال', 'هستم', 'یه', 'برام', 'الان', 'کجا'}
def _cat_toks(s):
    return [t for t in re.split(r'[\s\u200c،,؛()/\-]+', norm(s or '')) if t and t not in _CAT_STOP]

def _resolve_categories(given, need):
    """map guessed category names (e.g. «مبلمان», «مبل راحتی») to real DB categories, generically:
    token overlap with the real names (whole token > prefix), the category's head word must match the shopper's words
    (so «مبلمان اداری» / «کیف و کاور هدفون» never beat the plain head-word match), fewer extra qualifier words win,
    plus a smaller vote from text-search inference. Returns only the categories close to the best score."""
    global _ALLCATS
    if _ALLCATS is None:
        _ALLCATS = [(c, n) for (c, n) in RO.execute('SELECT category_name, COUNT(*) FROM products WHERE category_name IS NOT NULL GROUP BY category_name')]
    q = []
    for g in list(given) + ([need] if need else []):
        q += [t for t in _cat_toks(g) if len(t) >= 2 and t not in _Q_STOP and not re.fullmatch(r'[0-9۰-۹]+', t)]
    qs = set(q)
    nh = next((t for t in _cat_toks(need) if t not in _Q_STOP and len(t) >= 2), None) if need else None   # the shopper's head noun
    if not qs:
        return []
    def tm(ct):       # 1 whole-token match, 0.6 prefix match (مبل ~ مبلمان), else 0
        if ct in qs: return 1.0
        if len(ct) >= 3 and any(len(t) >= 3 and (ct.startswith(t) or t.startswith(ct)) for t in qs): return 0.6
        return 0.0
    score, hits = {}, {}
    for c, n in _ALLCATS:
        ct = _cat_toks(c)
        if not ct:
            continue
        m = [tm(t) for t in ct]
        hit = sum(m)
        if not hit:
            continue
        head = m[0]
        extra = sum(1 for x in m if x == 0)
        v = hit + (1.0 if head == 1.0 else (0.4 if head else -1.2)) - 0.35 * extra + (0.3 if not extra else 0) + min(n, 300) / 3000.0
        if nh and nh in ct:
            v += 0.5
        if v > 0:
            score[c] = v
            hits[c] = (hit, head)
    try:
        inf = _infer_categories(need) if need else []
    except Exception:
        inf = []
    lexical = bool(score)
    for i, c in enumerate(inf):     # text-search vote: a tie-breaker among name matches; the only signal when no name matches
        if c in score or not lexical:
            score[c] = score.get(c, 0) + (0.4 if lexical else 1.0) - 0.1 * i
    ranked = sorted(score.items(), key=lambda x: -x[1])
    if not ranked:
        return []
    best = ranked[0][1]
    bh = hits.get(ranked[0][0], (0, 0))[0]
    # close scores, plus sibling categories that match the same shopper words with the same head (مبل راحتی → چستر / ال too)
    return [c for c, v in ranked if v >= best * 0.75 or (bh >= 2 and hits.get(c, (0, 0))[1] == 1.0 and hits[c][0] >= bh)][:5]

def _infer_categories(need):
    r = B.tool_text_search(need, 20)
    w = {}
    for i, row in enumerate(r.get('results', [])):
        if row.get('flags') or not row.get('category'):
            continue
        w[row['category']] = w.get(row['category'], 0) + 1.0 / (i + 2)
    tot = sum(w.values()) or 1
    cats = [c for c, v in sorted(w.items(), key=lambda x: -x[1]) if v / tot >= 0.15][:3]
    return cats

def _area(near, region, radius_km):
    """generic area resolver: region name -> bounding box (+centroid); place -> centroid + radius; 'user' -> device point"""
    if near in ('user', 'من', 'کاربر') and _run('user_ll'):
        la, lo = _run('user_ll'); return {'name': 'موقعیت شما', 'lat': la, 'lon': lo, 'radius_km': radius_km or 3}
    if near in ('user', 'من', 'کاربر') and not region:
        pt = _run('point')     # no device location: the mission's point, else no area filter (saves a wasted retry round)
        return {'name': 'محدودهٔ شما', 'lat': pt[0], 'lon': pt[1], 'radius_km': radius_km or 3} if pt else None
    name = region or near
    if not name:
        return None
    g = B.tool_geocode_area(name)
    if not g.get('found'):
        return {'error': f'area not found: {name}', 'known_examples': g.get('known_examples', [])[:10]}
    a = {'name': g['name'], 'lat': g['lat'], 'lon': g['lon']}
    reg = next((k for k in B._REGION_PY if k == g['name'].replace(' تهران', '').strip()), None)
    if reg:
        a['region'] = reg
    else:
        a['radius_km'] = radius_km or g.get('suggested_radius_km') or 3
    return a

def _in_area(a, la, lo):
    if la is None:
        return False
    if a.get('region'):
        return B._REGION_PY[a['region']](la, lo)
    return T.haversine(a['lat'], a['lon'], la, lo) <= a['radius_km']

def _region_of(la, lo):
    for k, f in B._REGION_PY.items():
        if f(la, lo):
            return k + ' تهران'
    return 'سایر مناطق'

def _terms_ok(pids, required_terms, titles):
    """each required term (alternatives separated by |) must appear in the title or in a spec value"""
    if not required_terms:
        return set(pids)
    groups = [[norm(x).strip() for x in str(g).split('|') if norm(x).strip()] for g in required_terms]
    groups = [g for g in groups if g]
    def has(x, text):     # Latin alternatives match whole words only ('anc' must not match 'balance'); a negated mention ('بدون X') is not a match
        pat = (r'(?<![a-z0-9])' + re.escape(x) + r'(?![a-z0-9])') if re.search(r'[a-z]', x) else re.escape(x)
        for m_ in re.finditer(pat, text):
            if not re.search(r'(بدون|فاقد|without|no|non)\s+(قابلیت\s+|امکان\s+)?$', text[max(0, m_.start() - 22):m_.start()]):
                return True
        return False
    ok, need_spec = set(), []
    for pid in pids:
        t = titles[pid]
        miss = [g for g in groups if not any(has(x, t) for x in g)]
        if not miss:
            ok.add(pid)
        else:
            need_spec.append((pid, miss))
    for i in range(0, min(len(need_spec), 600), 300):
        chunk = need_spec[i:i + 300]
        q = 'SELECT product_id, key, value FROM product_specs WHERE product_id IN (%s)' % ','.join('?' * len(chunk))
        spec = {}
        for p, kk, v in RO.execute(q, [p for p, _ in chunk]):
            nv = norm(v or '').strip()
            if not nv:
                continue
            neg_ = bool(re.match(r'(ندارد|خیر|نه|no|none|not|فاقد|-)(\s|$|\.)', nv))   # a spec row saying "no X" is not X — and vetoes X
            spec.setdefault(p, []).append((norm(kk or '').strip(), nv, neg_))
        WRAP = {'قابلیت', 'دارای', 'امکان', 'سیستم', 'فناوری', 'تکنولوژی', 'پشتیبانی', 'از', 'feature', 'support', 'فعال', 'active'}
        def key_is(x, kk):   # the key IS the feature, not a different thing that contains it ('noise cancelling microphone')
            return has(x, kk) and all(w in WRAP or not re.search(r'\w', w) for w in re.sub(r'[()\[\]]', ' ', kk.replace(x, ' ')).split())
        def spec_has(x, rows):
            if any(neg_ and (key_is(x, kk) or has(x, kk)) for kk, nv, neg_ in rows):
                return False
            return any(not neg_ and (has(x, nv) or key_is(x, kk)) for kk, nv, neg_ in rows)
        for pid, miss in chunk:
            rows = spec.get(pid, [])
            if all(any(spec_has(x, rows) for x in g) for g in miss):
                ok.add(pid)
    return ok

def _offer_view(o, pt=None, shop=None):
    v = {k: o[k] for k in ('offer_id', 'price', 'date_fa', 'age_days', 'stale', 'suspicious')}
    if shop:
        v['shop_id'] = shop[0]
        if pt and shop[1] is not None:
            v['km'] = round(T.haversine(pt[0], pt[1], shop[1], shop[2]), 2)
    return v

def _find_products_core(a):
    t0 = time.time()
    need = (a.get('need') or '').strip()
    cats = [c for c in (a.get('categories') or []) if isinstance(c, str)]
    pmin = float(a['price_min']) if a.get('price_min') not in (None, '') else 0
    pmax = float(a['price_max']) if a.get('price_max') not in (None, '') else None
    sort = a.get('sort') if a.get('sort') in ('price', 'popularity') else 'popularity'
    k = max(3, min(int(a.get('k') or 6), 10))
    excl = set(a.get('exclude_product_ids') or [])
    include_used = bool(a.get('include_used'))
    out = {'query': {kk: v for kk, v in a.items() if v not in (None, '', [])}}
    ref = None
    prev = getattr(_RUN, 'constraints', None) or {}
    if a.get('cheaper_than_product_id'):
        # «cheaper» keeps the SAME need: inherit the defining constraints of the earlier search unless overridden
        inh = {}
        if not a.get('required_terms') and prev.get('required_terms'):
            a = dict(a, required_terms=prev['required_terms']); inh['required_terms'] = prev['required_terms']
        if not cats and prev.get('categories'):
            cats = list(prev['categories']); inh['categories'] = cats
        if inh:
            out['inherited_constraints'] = inh
    elif a.get('required_terms') or cats:
        _RUN.constraints_new = {'required_terms': a.get('required_terms') or [], 'categories': cats}
    if a.get('cheaper_than_product_id'):
        rf = product_facts(a['cheaper_than_product_id'])
        if not rf:
            return {'error': 'cheaper_than_product_id not found'}
        base = rf['cheapest_fresh_offer'] or rf['min_price_offer']
        ref = {'product_id': rf['product_id'], 'title': rf['title'][:70], 'family': rf['family'], 'reference_price': base['price'] if base else rf['median_price']}
        excl.add(rf['product_id'])
        cats = cats or [rf['category']]
        if ref['reference_price']:
            pmax = min(pmax or 1e15, ref['reference_price'] - 1)
        # the same item: other listings of the same family that are cheaper (fresh or flagged), computed
        sib = RO.execute('SELECT product_id, persian_title, brand_name FROM products WHERE category_name=? AND (brand_name IS ? )', (rf['category'], rf['brand'])).fetchall()
        same = []
        for pid, t, b in sib:
            if family_key(t, b) == rf['family']:
                pf = product_facts(pid)
                for o in pf['offers']:
                    if ref['reference_price'] and o['price'] < ref['reference_price']:
                        same.append(dict(_offer_view(o), product_id=pid, title=t[:60]))
        same.sort(key=lambda x: x['price'])
        out['reference'] = ref
        out['same_item_cheaper_offers'] = same[:4]
        if not same:
            out['same_item_note'] = 'no cheaper offer of the same model family exists in the data'
    if not cats:
        if not need:
            return {'error': 'give need or categories'}
        cats = _resolve_categories([], need) or _infer_categories(need)   # name match over real categories first, text-search vote as tie-breaker
        if not cats:
            return {'error': 'could not infer a category; pass categories'}
    real = {c for (c,) in RO.execute('SELECT DISTINCT category_name FROM products WHERE category_name IN (%s)' % ','.join('?' * len(cats)), cats)}
    if len(real) < len(cats):   # model guessed category names that don't exist exactly -> resolve to real ones instead of failing
        fixed = _resolve_categories([c for c in cats if c not in real], need)
        cats = list(real) + [c for c in fixed if c not in real]
        real = set(cats)
        out['categories_resolved'] = cats
    if not real:
        return {'error': 'unknown categories', 'given': cats}
    cats = [c for c in cats if c in real]
    out['categories'] = cats
    area = _area(a.get('near'), a.get('region'), a.get('radius_km'))
    if area and area.get('error'):
        return area
    pt = (area['lat'], area['lon']) if area else _run('user_ll')
    if area:
        out['area'] = area
    q = '''SELECT o.offer_id,o.product_id,o.shop_id,o.price_toman,o.last_price_changed_at,s.lat,s.lon,p.persian_title,p.brand_name,p.category_name,o.seller_title
           FROM products p JOIN offers o USING(product_id) JOIN shops s USING(shop_id)
           WHERE p.category_name IN (%s) AND o.price_toman IS NOT NULL AND o.price_toman >= ?%s LIMIT 30000''' % (','.join('?' * len(cats)), ' AND o.price_toman <= ?' if pmax else '')
    rows = RO.execute(q, cats + [pmin] + ([pmax] if pmax else [])).fetchall()
    acc_cats = {c for c in cats if T._cat_acc(c, '')}     # requested categories that are accessory categories
    titles, meta, offers_by = {}, {}, {}
    for r in rows:
        if r[1] in excl:
            continue
        if r[10] and any(w in norm(r[10]) for w in _KNOCK + (() if include_used else _USED)):   # the seller's own listing says clone/used
            continue
        if r[1] not in titles:
            if not _quality_ok(r[7], r[9], include_used, acc_ok=r[9] in acc_cats):
                titles[r[1]] = None; continue
            titles[r[1]] = norm(r[7]); meta[r[1]] = (r[7], r[8], r[9])
        if titles[r[1]] is None:
            continue
        offers_by.setdefault(r[1], []).append(r)
    okp = _terms_ok(list(offers_by), a.get('required_terms'), titles)
    sims = {}
    if ref:
        okp = {p for p in okp if family_key(meta[p][0], meta[p][1]) != ref['family']}
        sims = _similarity(ref['product_id'], okp)
        if sims:   # "same need": keep products semantically close to the reference (relative cut, local vectors, no API call)
            top = max(sims.values())
            cut = 0.55 if a.get('required_terms') else max(0.55, min(0.6, top - 0.15))   # embedding sims are noisy across listings: loose floor
            okp = {p for p in okp if sims.get(p, 0) >= cut}
            out['similarity_cut'] = round(cut, 3)

    def pick(in_area_only):
        cands = []
        for pid in okp:
            pf = product_facts(pid)
            offs = []
            for r in offers_by[pid]:
                if in_area_only and area and not _in_area(area, r[5], r[6]):
                    continue
                o = next((x for x in pf['offers'] if x['offer_id'] == r[0]), None)
                if o and not o['suspicious']:
                    offs.append((o, (r[2], r[5], r[6])))
            if not offs:
                continue
            offs.sort(key=lambda x: x[0]['price'])
            best, shop = offs[0]
            fresh = next(((o, s) for o, s in offs if not o['stale']), None)
            row = {'product_id': pid, 'title': pf['title'][:75], 'brand': pf['brand'], 'category': pf['category'], 'family': pf['family'],
                   'n_shops_city': pf['n_shops'], 'median_price': pf['reference_median'], 'offer': _offer_view(best, pt, shop)}
            if best['stale'] and fresh:
                row['cheapest_fresh_offer'] = _offer_view(fresh[0], pt, fresh[1])
            if ref and ref['reference_price']:
                row['cheaper_than_reference_pct'] = round(100 * (1 - best['price'] / ref['reference_price']))
                if pid in sims: row['similarity_to_reference'] = round(sims[pid], 3)
            if area and not in_area_only:
                row['outside_area'] = not _in_area(area, shop[1], shop[2])
                row['shop_region'] = _region_of(shop[1], shop[2]) if shop[1] is not None else None
            cands.append(row)
        return cands

    def diverse(rows, key, n, exclude_fams=()):
        rows = sorted(rows, key=key)
        out_, fams, brands = [], set(exclude_fams), {}
        for r in rows:
            if r['family'] in fams or brands.get(r['brand'], 0) >= 2:
                continue
            out_.append(r); fams.add(r['family']); brands[r['brand']] = brands.get(r['brand'], 0) + 1
            if len(out_) >= n:
                break
        return out_
    by_price = lambda r: (r['offer']['price'], -r['n_shops_city'])
    by_pop = lambda r: (-r['n_shops_city'], r['offer']['price'])
    cands = pick(True)

    def tier(rows):
        # «a good X up to N»: a budget is a target, not a ceiling to undercut by 90% -> prefer items in the upper part of the budget
        if pmax and sort != 'price' and not ref and not a.get('cheaper_than_product_id'):
            up = [r for r in rows if r['offer']['price'] >= 0.35 * pmax]
            if len(up) >= 2:
                return up
        return rows
    if ref and sims:
        res = diverse(cands, by_pop, k)        # all passed the same-need cut; established (popular) substitutes first
    else:
        res = diverse(cands, by_price if sort == 'price' else by_pop, k)
    out['results'] = res
    # ground truth for "cheapest/cheaper/under budget": established items (>=3 sellers city-wide) so one-off oddities don't dominate
    # and only up-to-date prices count as "cheaper" (an old price is not evidence that it is cheaper today)
    est = [r for r in cands if r['n_shops_city'] >= 3] or cands
    gt = []
    for r in est:
        fo = r['offer'] if not r['offer']['stale'] else r.get('cheapest_fresh_offer')
        if fo:
            gt.append(dict(r, offer=fo))
    out['cheapest_qualifying'] = [{kk: r[kk] for kk in ('product_id', 'title', 'family', 'offer', 'n_shops_city')} for r in diverse(gt, by_price, 3)]
    out['n_qualifying_products'] = len(cands)
    if area and len({r['family'] for r in res}) < 3:
        wide = [r for r in pick(False) if r['outside_area']]
        for r in wide:
            r['_d'] = r['offer'].get('km', 99)
        near_first = sorted(wide, key=lambda r: (round(r['_d'] / 3), (by_price if sort == 'price' else by_pop)(r)))   # nearest first (3 km bands)
        outside = diverse(near_first, lambda r: 0, 3, exclude_fams={r['family'] for r in res})
        for r in outside:
            r.pop('_d', None)
        out['thin_area'] = True
        out['nearest_outside_area'] = outside
    if not res and not out.get('nearest_outside_area'):
        out['note'] = 'nothing matches all constraints; relax price/terms/area'
    out['ms'] = int((time.time() - t0) * 1000)
    rec = _run('fp')
    if rec is not None:
        rec.append({'args': a, 'categories': cats, 'area': area, 'ref': ref, 'cheapest_qualifying': out['cheapest_qualifying'],
                    'result_ids': [r['product_id'] for r in res], 'pmin': pmin, 'pmax': pmax})
    return out


def tool_find_products(a):
    """find_products + one automatic relax: if required_terms leave nothing, return the closest items of the same kind (flagged)"""
    out = _find_products_core(a)
    if isinstance(out, dict) and not out.get('error') and not out.get('results') and not out.get('nearest_outside_area') and a.get('required_terms'):
        keep = getattr(_RUN, 'constraints_new', None)
        r2 = _find_products_core(dict(a, required_terms=[]))
        if keep is not None: _RUN.constraints_new = keep      # remember the shopper's terms, not the relaxed call
        if isinstance(r2, dict) and r2.get('results'):
            r2['terms_relaxed'] = a.get('required_terms')
            r2['note'] = 'no item matches every required term; these are the closest items of the same kind: show them as cards and say in one short sentence how they differ'
            return r2
    return out

_EMB = {}
def _similarity(ref_pid, pids):
    try:
        import numpy as np
        if 'M' not in _EMB:
            M, ids = B.R._load_emb()
            if M is None:
                return {}
            _EMB['M'] = M / (np.linalg.norm(M, axis=1, keepdims=True) + 1e-8); _EMB['idx'] = {p: i for i, p in enumerate(ids)}
        M, idx = _EMB['M'], _EMB['idx']
        if ref_pid not in idx:
            return {}
        v = M[idx[ref_pid]]
        return {p: float(M[idx[p]] @ v) for p in pids if p in idx}
    except Exception:
        return {}


# ================================================================== 4. product_knowledge with provenance
_STOP = set('چند چنده چیه چی است هست داره دارد این اون آن را رو با به از که می میخوره چطوره ها های کدوم آیا ایا'.split())

def _q_terms(question, extra):
    t = norm(question or '')
    terms = set()
    for w in re.split(r'[\s،,؟?!.:;()]+', t):
        if len(w) >= 3 and w not in _STOP:
            terms.add(w)
            for suf in ('ش', 'اش', 'ها', 'های', 'ه'):
                if w.endswith(suf) and len(w) - len(suf) >= 3:
                    terms.add(w[:-len(suf)])
    for e in extra or []:
        e = norm(str(e))
        if len(e) >= 2:
            terms.add(e)
    return terms

def _db_specs(pid, terms, limit=10):
    rows = RO.execute('SELECT key,value FROM product_specs WHERE product_id=?', (pid,)).fetchall()
    return [(k, (v or '')[:160]) for k, v in rows if any(t in norm(f'{k} {v}') for t in terms)][:limit]

def _wiki(title_en, kws_en, max_chars=900):
    if not title_en:
        return None
    try:
        u = 'https://en.wikipedia.org/w/api.php?' + urllib.parse.urlencode({'action': 'query', 'prop': 'extracts', 'explaintext': 1, 'redirects': 1, 'format': 'json', 'titles': title_en})
        req = urllib.request.Request(u, headers={'User-Agent': 'TorobHackathonAssistant/0.1 (demo; no bulk)'})
        d = json.loads(urllib.request.urlopen(req, timeout=WIKI_TIMEOUT_S).read().decode())
        pg = next(iter(d['query']['pages'].values()))
        x = pg.get('extract') or ''
        kws = [k.lower() for k in (kws_en or []) if k] or ['specification']
        pick, n = [], 0
        for s in (s.strip() for s in re.split(r'(?<=[.!?])\s+|\n+', x)):
            if s and not s.startswith('=') and any(k in s.lower() for k in kws):
                pick.append(s[:300]); n += len(pick[-1])
                if n > max_chars or len(pick) >= 6:
                    break
        return {'source': 'en.wikipedia.org/wiki/' + pg.get('title', title_en).replace(' ', '_'), 'sentences': pick} if pick else None
    except Exception:
        return None

def tool_product_knowledge(a):
    pid = a.get('product_id')
    terms = _q_terms(a.get('question'), a.get('spec_keywords_fa'))
    facts, store = [], _run('facts')
    def add(src, text, origin):
        fid = f'f{len(store) + 1 if store is not None else len(facts) + 1}'
        f = {'fact_id': fid, 'source': src, 'text': text, 'origin': origin}
        facts.append(f)
        if store is not None:
            store[fid] = f
    if pid:
        r = RO.execute('SELECT persian_title,brand_name,model FROM products WHERE product_id=?', (pid,)).fetchone()
        if r:
            own = _db_specs(pid, terms)
            for kk, v in own:
                add('db_spec', f'{kk}: {v}', pid)
            if not own and r[2]:
                for (sib,) in RO.execute('SELECT product_id FROM products WHERE brand_name IS ? AND model=? AND product_id<>? AND n_specs>0 ORDER BY n_specs DESC LIMIT 5', (r[1], r[2], pid)):
                    sp = _db_specs(sib, terms)
                    if sp:
                        for kk, v in sp:
                            add('other_listing', f'{kk}: {v}', sib)
                        break
    w = _wiki(a.get('english_name'), a.get('keywords_en'))
    if w:
        for s in w['sentences']:
            add('public_reference', s, w['source'])
    log = _run('pk')
    if log is not None:
        log.append({'q': a.get('question'), 'n_db': sum(f['source'] != 'public_reference' for f in facts), 'n_public': sum(f['source'] == 'public_reference' for f in facts)})
    return {'facts': facts, 'how_to_cite': 'Write each spec claim as [[spec:<fact_id>|<Persian claim>]] using the fact it comes from, or [[spec:gen|<claim>]] '
                                         'for well-established manufacturer knowledge not in these facts. The server adds the source label; never write a source/Torob attribution yourself. '
                                         'If the db_spec facts do not literally answer the question, the Torob data does not answer it.'}


B.TOOLS = dict(B.TOOLS, sql=lambda a: tool_sql(a.get('query')), find_products=tool_find_products, product_knowledge=tool_product_knowledge)
_FP_SCHEMA = {'type': 'function', 'function': {
    'name': 'find_products',
    'description': ('Constraint search for "a good/cheap X (under budget) (in area)" and "cheaper than the shown item". Searches whole categories, '
                    'filters used/clone/accessory, returns DIVERSE models (one per model family, max 2 per brand) with computed facts: best offer '
                    '(price, date, age_days, stale, suspicious, km), cheapest_fresh_offer, city-wide seller count, median; plus cheapest_qualifying '
                    '(ground truth) and, for a thin area, nearest_outside_area options. With cheaper_than_product_id it also returns '
                    'same_item_cheaper_offers (other listings of the same model) and only DIFFERENT model families strictly cheaper than the reference.'),
    'parameters': {'type': 'object', 'properties': {
        'need': {'type': 'string', 'description': 'the need in Persian (used to infer categories when none given)'},
        'categories': {'type': 'array', 'items': {'type': 'string'}, 'description': 'exact category names if known'},
        'price_min': {'type': 'number'}, 'price_max': {'type': 'number'},
        'sort': {'type': 'string', 'enum': ['price', 'popularity']},
        'near': {'type': 'string', 'description': 'place name (square/street/mall/district) or "user" for the device location'},
        'region': {'type': 'string', 'description': 'غرب/شرق/شمال/جنوب/مرکز تهران'},
        'radius_km': {'type': 'number'},
        'required_terms': {'type': 'array', 'items': {'type': 'string'}, 'description': 'each item must match title or specs; alternatives separated by |, e.g. "16 گیگ|16gb"'},
        'exclude_product_ids': {'type': 'array', 'items': {'type': 'string'}},
        'cheaper_than_product_id': {'type': 'string'},
        'include_used': {'type': 'boolean'}, 'k': {'type': 'integer'}}}}}
_PK_SCHEMA = {'type': 'function', 'function': {
    'name': 'product_knowledge',
    'description': 'Spec/feature/compatibility facts with fact_id and source tag (db_spec | other_listing | public_reference). Never for prices, shops or stock.',
    'parameters': {'type': 'object', 'properties': {
        'product_id': {'type': 'string'}, 'product_name': {'type': 'string'}, 'question': {'type': 'string'},
        'spec_keywords_fa': {'type': 'array', 'items': {'type': 'string'}},
        'english_name': {'type': 'string', 'description': 'English Wikipedia article title of the product family'},
        'keywords_en': {'type': 'array', 'items': {'type': 'string'}}}, 'required': ['product_name', 'question']}}}
import playground_bazaar as _BZ      # «بورس» hubs computed from the DB (bazaars.json); no LLM
def tool_bazaar_hubs(a):
    r = _BZ.lookup(a.get('need') or '', a.get('category'))
    if not r:
        return {'found': False, 'groups_known': [g['group'] for g in _BZ.data()['groups']]}
    return dict(r, found=True, how_to_show='name the hub naturally; show 2-3 of these shops with a map block (shop_ids); never claim a hub that is not listed')
_BZ_SCHEMA = {'type': 'function', 'function': {'name': 'bazaar_hubs', 'description': 'Where in Tehran is the trade hub («بورس») for a kind of goods, computed from this DB: hub name, centre, share of offers and real shop ids there.',
              'parameters': {'type': 'object', 'properties': {'need': {'type': 'string', 'description': 'the goods in Persian, e.g. لوازم برقی'},
                                                             'category': {'type': 'string', 'description': 'optional exact category_name'}}, 'required': ['need']}}}
B.TOOLS['bazaar_hubs'] = tool_bazaar_hubs
_SP_SCHEMA = {'type': 'function', 'function': {'name': 'start_project', 'description': (
    'Route to the one-stop «خرید یکجا» planner. Call FIRST and ALONE when the request needs a list of several DIFFERENT kinds of items bought together '
    '(set up a kitchen / home office / gaming setup / baby room / new flat, CCTV for a shop, wiring a flat). Never for a single product or one kind of product.'),
    'parameters': {'type': 'object', 'properties': {'goal': {'type': 'string', 'description': "the user's need in Persian, with every detail they gave"}}, 'required': ['goal']}}}
TOOL_SCHEMAS = B.TOOL_SCHEMAS + [_FP_SCHEMA, _PK_SCHEMA, _BZ_SCHEMA, _SP_SCHEMA]
_TS_CACHE, _TS_LOCK = {}, threading.Lock()
_ts_base = B.TOOLS['text_search']
def _text_search_cached(a):        # same query within 15 min -> no second embedding call / search
    k = json.dumps([a.get('query'), a.get('k', 20)], ensure_ascii=False)
    with _TS_LOCK:
        hit = _TS_CACHE.get(k)
    if hit and time.time() - hit[0] < 900:
        return hit[1]
    r = _ts_base(a)
    with _TS_LOCK:
        if len(_TS_CACHE) > 300: _TS_CACHE.clear()
        _TS_CACHE[k] = (time.time(), r)
    return r
B.TOOLS['text_search'] = _text_search_cached

def _emit(kind, data):
    """progress events for /api/send_stream (no-op for /api/send)"""
    cb = getattr(_RUN, 'on_event', None)
    if cb:
        try: cb(kind, data)
        except Exception: pass


# ================================================================== prompt
def system_prompt(mission=None, user_lat=None, user_lon=None):
    now = B.datetime.now(B.TEHRAN)
    day = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'][now.weekday()]
    hh = now.strftime('%H:%M:%S')
    sch = SCHEMA_PLUS.replace('{DAY}', day).replace('{HHMMSS}', hh).replace('{HHMM}', hh[:5])
    s = SYSTEM_PLUS.replace('{NOW}', now.strftime('%Y-%m-%d %H:%M')).replace('{DAY}', day).replace('{SCHEMA}', sch).replace('{TRUTHS}', TRUTHS_PLUS)
    if user_lat is not None:
        s += f'\nShopper location (from device): lat={user_lat}, lon={user_lon} (find_products near="user").'
    try:
        s += '\n' + _BZ.summary_for_prompt()
    except Exception:
        pass
    if mission:
        s += '\nCurrent mission (from earlier turns; you own it, update it; keys starting with _ are server facts): ' + json.dumps(mission, ensure_ascii=False)
    return s


# ================================================================== hydration labels
def _flag_fields(f, date_fa):
    d = {'stale': bool(f.get('stale')), 'suspicious_low': bool(f.get('suspicious_low'))}
    notes = []
    if d['stale']:
        notes.append(f'قیمت قدیمی: آخرین تغییر {date_fa} (حدود {_fa(f["days_old"])} روز پیش)')
    if d['suspicious_low']:
        notes.append(f'قیمت مشکوک: کمتر از ۴۰٪ میانهٔ قیمت (حدود {fmt_toman(f["product_median"])})')
    if notes:
        d['freshness_note_fa'] = '؛ '.join(notes)
    return d
B._flag_fields = _flag_fields

def _offer_flags(oid, _m=None):
    """same facts as offer_facts (family median for thin products) so cards and text never disagree"""
    f = offer_facts(oid)
    if not f or f.get('price') is None:
        return None
    o = {'days_old': f['age_days']}
    if f['stale']: o['stale'] = True
    if f['suspicious']: o['suspicious_low'] = True; o['product_median'] = f['product_median']
    return o
B._offer_flags = _offer_flags

_base_shop = B._shop
def _shop(sid):
    s = _base_shop(sid)
    if s:
        s['phone_note'] = 'شماره‌های تماس در این داده آزمایشی‌اند؛ تماسی گرفته نشده'
    return s
B._shop = _shop


# ================================================================== 3. rendering + claim check + coverage
_TOK = re.compile(r'\[\[(offer|product):((?:offer|product)_[0-9a-f]{16,32})\]\]')
_SPEC = re.compile(r'\[\[spec:(f\d+|gen)\|([^\]]{1,300})\]\]')

def _resolve(kind, ident, seen):
    fn = offer_facts if kind == 'offer' else product_facts
    v = fn(ident)
    if v is None:
        c = [x for x in seen if x.startswith(kind + '_') and B._ed1(x, ident)]
        if len(c) == 1:
            v = fn(c[0])
    return v

def fmt_toman_text(v):
    """prose price, rounded the way people say it; the exact price stays on the cards.
    >=10M: whole millions («حدود ۱۶۳ میلیون تومان»); 1–10M: «۶ میلیون و ۷۰۰ هزار»; <1M: thousands."""
    v = int(v)
    if v >= 10_000_000:
        r = int(round(v / 1_000_000)) * 1_000_000
        txt = _fa(f'{r // 1_000_000:,}'.replace(',', '٬')) + ' میلیون تومان'
    elif v >= 1_000_000:
        r = int(round(v / 100_000)) * 100_000
        mm, hh = divmod(r, 1_000_000)
        txt = _fa(str(mm)) + ' میلیون' + (f' و {_fa(str(hh // 1000))} هزار' if hh else '') + ' تومان'
    elif v >= 1000:
        r = int(round(v / 10_000)) * 10_000 if v >= 100_000 else int(round(v / 1000)) * 1000
        txt = _fa(f'{r // 1000:,}'.replace(',', '٬')) + ' هزار تومان'
    else:
        return fmt_toman(v)
    return txt if r == v else 'حدود ' + txt

def natural_km(k):
    """distance in prose: coarse and natural, never decimals"""
    if k is None:
        return None
    if k < 0.8:
        return 'همین نزدیکی'
    if k < 1.5:
        return 'چند دقیقه راه'
    if k <= 3:
        return 'کمی دورتر'
    return f'حدود {_fa(str(int(round(k))))} کیلومتر فاصله'

def render_offer(o, km=True):
    if not o or o.get('price') is None:
        return 'قیمتش ثبت نشده'
    s = fmt_toman_text(o['price'])
    if km and o.get('km') is not None:
        s += f" ({natural_km(o['km'])})"
    return s

def render_product(p):
    m, f = p['min_price_offer'], p['cheapest_fresh_offer']
    if not m:
        return 'قیمتش ثبت نشده'
    s = 'از ' + render_offer(offer_facts(m['offer_id']), km=False)
    if m['stale'] and f and f['offer_id'] != m['offer_id']:
        s += ' (قیمت به‌روزش ' + render_offer(offer_facts(f['offer_id']), km=False) + ')'
    return s

_CLAIMS = {
    'stale': re.compile(r'قدیمی|به[‌ ]?روز نیست|به[‌ ]?روز نباشد'),
    'suspicious': re.compile(r'مشکوک'),
    'cheapest': re.compile(r'ارزان[‌ ]?ترین|ارزون[‌ ]?ترین|کمترین قیمت'),
    'freshest': re.compile(r'تازه[‌ ]?ترین|جدیدترین|به[‌ ]?روزترین'),
    'cheaper': re.compile(r'ارزان[‌ ]?تر(?!ین)|ارزون[‌ ]?تر(?!ین)|ارزان[‌ ]?تری|کم[‌ ]?هزینه[‌ ]?تر'),
}
_NEG = re.compile(r'پیدا نکردم|پیدا نشد|نیست|وجود ندارد|ندارد|نداریم|نبود|نیافتم|ثبت نشده')
_FRESHER = re.compile(r'تازه[‌ ]?تر(?!ین)|به[‌ ]?روزتر|جدیدتر(?!ین)')
_ATTRIB = re.compile(r'(طبق|بر ?اساس|مطابق|در)\s+(مشخصات|داده[‌ ]?های|اطلاعات)\s+(ثبت[‌ ]?شده\s+)?(در\s+)?ترب|در ترب ثبت شده|ترب (می[‌ ]?گوید|نوشته)')

def _sentences(text):
    return [s for s in re.split(r'(?<=[.!؟?\n])', text) if s.strip()]

def check_claims(text, seen, mission):
    """claims in the model's text vs computed facts. Returns list of violations (dicts)."""
    viol = []
    ref = (mission or {}).get('_shown_min_price')
    for sent in _sentences(text):
        toks = [(k, i) for k, i in _TOK.findall(sent)]
        free = _TOK.sub(' ', _SPEC.sub(' ', sent))
        offs = []
        for k, i in toks:
            v = _resolve(k, i, seen)
            if v is None:
                continue
            if k == 'offer':
                offs.append(v)
            else:
                m = v['min_price_offer']
                if m: offs.append(offer_facts(m['offer_id']))
        offs = [o for o in offs if o and o.get('price') is not None]
        s = sent.strip()[:140]
        for name in ('stale', 'suspicious'):
            if _CLAIMS[name].search(free):
                if not offs:
                    viol.append({'type': f'{name}_word_without_price_token', 'sentence': s})
                elif not any(o[name] for o in offs):
                    viol.append({'type': f'{name}_claim_false', 'sentence': s})
        neg = _NEG.search(free)
        if _CLAIMS['cheapest'].search(free) and offs and not neg:
            o0 = min(offs, key=lambda o: o['price'])
            fam = [o for o in _family_offers(product_facts(o0['product_id']), area=True) if not o['suspicious']]
            cheaper_fresh = [o for o in fam if not o['stale'] and o['price'] < o0['price']]
            cheaper_old = [o for o in fam if o['stale'] and o['price'] < o0['price']]
            if cheaper_fresh:
                c = min(cheaper_fresh, key=lambda o: o['price'])
                viol.append({'type': 'cheapest_claim_false', 'sentence': s, 'evidence': f"cheaper up-to-date offer of the same model{' in the area' if _run('point') else ''}: {c['offer_id']} ({c['title'][:50]}) {c['price']}"})
            elif cheaper_old and not any(o['stale'] for o in offs):
                c = min(cheaper_old, key=lambda o: o['price'])
                viol.append({'type': 'cheapest_claim_ignores_cheaper_old_price', 'sentence': s, 'evidence': f"a cheaper but OLD price exists: {c['offer_id']} ({c['title'][:50]}) {c['price']} — say «cheapest up-to-date» and mention it with its token"})
        if _CLAIMS['freshest'].search(free) and offs and not neg:
            if not any(o['is_product_freshest'] for o in offs):
                viol.append({'type': 'freshest_claim_false', 'sentence': s})
        if _CLAIMS['cheaper'].search(free) and offs and ref and not neg:
            bad = [o for o in offs if o['price'] >= ref]
            if len(bad) == len(offs):
                viol.append({'type': 'cheaper_claim_false', 'sentence': s, 'evidence': f'reference shown price {int(ref)}; these are not lower: ' + ', '.join(str(o['price']) for o in bad[:3])})
        if neg and (_FRESHER.search(free) or _CLAIMS['cheaper'].search(free)):
            # "nothing fresher/cheaper" — check the products this turn talks about (tokens in the sentence, else the mission's product)
            pids = {o['product_id'] for o in offs} or ({mission.get('selected_product_id')} if (mission or {}).get('selected_product_id') else set())
            for pid in pids:
                pf = product_facts(pid) if pid else None
                if not pf:
                    continue
                fam_offs = _family_offers(pf)
                shown_p = min((o['price'] for o in offs if o['product_id'] == pid), default=None)
                if _FRESHER.search(free) and any(not o['stale'] and not o['suspicious'] for o in fam_offs):
                    fr = min((o for o in fam_offs if not o['stale'] and not o['suspicious']), key=lambda o: o['price'])
                    if not offs or all(o['stale'] for o in offs):
                        viol.append({'type': 'nothing_fresher_claim_false', 'sentence': s, 'evidence': f"fresh offer exists: {fr['offer_id']} ({fr['title'][:50]}) {fr['price']} {fr['date']}"})
                if _CLAIMS['cheaper'].search(free) and shown_p:
                    ch = [o for o in fam_offs if o['price'] < shown_p and not o['suspicious']]
                    if ch:
                        c = min(ch, key=lambda o: o['price'])
                        viol.append({'type': 'nothing_cheaper_claim_false', 'sentence': s, 'evidence': f"cheaper offer of the same model exists: {c['offer_id']} {c['price']} {c['date']}{' (old)' if c['stale'] else ''}"})
        if _ATTRIB.search(free) and _run('pk'):
            viol.append({'type': 'self_written_torob_attribution', 'sentence': s})
    return viol

def _family_offers(pf, area=False):
    pt = _run('point') if area else None
    rows = RO.execute('SELECT product_id, persian_title, brand_name FROM products WHERE category_name=? AND brand_name IS ?', (pf['category'], pf['brand'])).fetchall()
    out = []
    for pid, t, b in rows:
        if family_key(t, b) == pf['family'] and _quality_ok(t, pf['category'], 'استوک' in norm(pf['title']) or 'کارکرده' in norm(pf['title'])):
            # same model AND same variant words (pro/max/...) as the product talked about
            if _variant(t) != _variant(pf['title']):
                continue
            for o in product_facts(pid)['offers']:
                if pt:
                    s_ = RO.execute('SELECT lat,lon FROM shops WHERE shop_id=?', (o['shop_id'],)).fetchone()
                    if not s_ or s_[0] is None or T.haversine(pt[0], pt[1], s_[0], s_[1]) > 3:
                        continue
                out.append(dict(o, title=t, product_id=pid))
    return out

def _variant(t):
    tn = norm(t)
    return tuple(sorted(k for k, ws in T.VARIANT_WORDS.items() if any(re.search(r'(^|\s)' + re.escape(norm(w)) + r'(\s|$)', tn) for w in ws)))

_INTENT = re.compile(r'ارزون|ارزان|کمترین|زیر\s*[\d۰-۹]|تا\s*[\d۰-۹]|حداکثر|بودجه|اقتصادی|بهترین|ارزونش|کم[‌ ]?قیمت')

def coverage_check(blocks, mission, user_text):
    """budget / cheapest / cheaper answers vs a direct ground truth with the same constraints (sort=price)."""
    fps = _run('fp') or []
    if not (_INTENT.search(norm(user_text or '')) or any((c['args'].get('sort') == 'price' or c['pmax']) for c in fps)):
        return []
    shown_p, shown_fam, prices = set(), set(), []
    for b in blocks:
        for it in b.get('items', []) + b.get('products', []):
            pid = it.get('product_id')
            if pid:
                shown_p.add(pid)
                pf = product_facts(pid)
                if pf: shown_fam.add(pf['family'])
            if it.get('price_toman') and not it.get('suspicious_low'):
                prices.append(it['price_toman'])
            elif it.get('min_price') and pid:
                m = product_facts(pid)['min_price_offer']
                if m: prices.append(m['price'])
    if not shown_p or not prices:
        return []
    if fps:
        gt = fps[-1]['cheapest_qualifying']
    else:
        return []          # no constraint record: nothing principled to compare against
    lo = min(prices)
    shown_cats = {product_facts(p)['category'] for p in shown_p if product_facts(p)}
    miss = [g for g in gt if g['product_id'] not in shown_p and g['family'] not in shown_fam and 0.3 * lo <= g['offer']['price'] < 0.9 * lo
            and (product_facts(g['product_id']) or {}).get('category') in shown_cats]
    return miss[:2]

_PRICE_ASK = re.compile(r'چند|قیمت|ارزون|ارزان|کمترین|کجا بخرم|کجا ارزون')
def same_model_check(blocks, user_text):
    """price questions: for every model family/variant shown, a clearly cheaper up-to-date offer of that same model
    (in the area when one is set) must not be silently left out."""
    if not _PRICE_ASK.search(norm(user_text or '')):
        return []
    shown = {}
    for b in blocks:
        for it in b.get('items', []):
            if it.get('offer_id') and it.get('price_toman') and not it.get('suspicious_low'):
                pf = product_facts(it['product_id'])
                key = (pf['family'], _variant(pf['title']))
                shown.setdefault(key, (pf, []))[1].append(it['price_toman'])
    miss = []
    for (fam, var), (pf, ps) in shown.items():
        fr = [o for o in _family_offers(pf, area=True) if not o['stale'] and not o['suspicious']]
        if fr:
            c = min(fr, key=lambda o: o['price'])
            if c['price'] < 0.9 * min(ps):
                miss.append({'product_id': c['product_id'], 'title': c['title'], 'family': fam, 'offer': {'offer_id': c['offer_id'], 'price': c['price']}, 'same_model': True})
    return miss[:2]

def _drop_whole_words(rx, sent):
    """remove claim matches together with the rest of any word they cut into (no «ش،» left from «ارزون‌ترش،»)"""
    spans = [m.span() for m in rx.finditer(sent) if m.end() > m.start()]
    stop = '،؛.!؟:()«»\u200c'
    for a, b in reversed(spans):
        a2, b2 = a, b      # extend only over a short attached suffix/prefix (ش، ها، تر); never eat a neighbouring noun
        while a2 > 0 and not sent[a2 - 1].isspace() and sent[a2 - 1] not in stop: a2 -= 1
        while b2 < len(sent) and not sent[b2].isspace() and sent[b2] not in stop: b2 += 1
        if a - a2 > 3: a2 = a
        if b2 - b > 3: b2 = b
        if b2 < len(sent) and sent[b2] == '\u200c' and b2 - b <= 0:   # «ارزون‌ترش»: claim ends at a ZWNJ -> also drop the short suffix after it
            e = b2 + 1
            while e < len(sent) and not sent[e].isspace() and sent[e] not in stop: e += 1
            if e - b2 <= 4: b2 = e
        sent = sent[:a2] + sent[b2:]
    return re.sub(r'[ \t]{2,}', ' ', sent)

def strip_claims(text, viol):
    """last resort after the one regeneration: remove the unsupported words/sentences"""
    bad = {v['sentence'] for v in viol}
    out = []
    for sent in _sentences(text):
        if sent.strip()[:140] in bad:
            if _TOK.search(sent):     # keep the facts, drop the claim words
                for rx in list(_CLAIMS.values()) + [_ATTRIB]:
                    sent = _drop_whole_words(rx, sent)
                sent = re.sub(r'^(\s*)[،؛,]\s*', r'\1', sent)
                out.append(sent)
            continue
        out.append(sent)
    return ''.join(out).strip()

def ident_pid(v, ident):
    return (v or {}).get('product_id') or (ident if str(ident).startswith('product_') else None)

_PRICE_RX = re.compile(r'(?:(?:حدود|حدوداً|تقریباً|از|با|فقط|قیمتش|قیمت)\s+)*([0-9۰-۹][0-9۰-۹٬,٫.]*)\s*(میلیون|هزار)?(?:\s*و\s*([0-9۰-۹][0-9۰-۹٬,]*)\s*هزار)?\s*تومان')
def _price_val(m):
    tr = str.maketrans('۰۱۲۳۴۵۶۷۸۹٫', '0123456789.')
    try:
        a = float(m.group(1).translate(tr).replace('٬', '').replace(',', ''))
    except ValueError:
        return None
    unit = {'میلیون': 1_000_000, 'هزار': 1_000}.get(m.group(2) or '', 1)
    v = a * unit
    if m.group(3):
        try: v += float(m.group(3).translate(tr).replace('٬', '').replace(',', '')) * 1000
        except ValueError: pass
    return v

def price_guard(text, cards, log):
    """Safety net after rendering: when cards are shown, every spoken price must equal a card's min or max (≤1%).
    Otherwise it is rewritten to «از <card min> تومان» for the card named in that sentence (or the only card)."""
    if not cards:
        return text
    allowed = [x for c in cards.values() for x in (c['min'], c.get('max')) if x]
    okp = [x for x in (getattr(_RUN, 'ok_prices', None) or []) if x]
    out = []
    for sent in re.split(r'(?<=[.!؟\n])', text):
        def rep(m):
            v = _price_val(m)
            if v is None or any(abs(v - a) <= 0.01 * a for a in allowed) or any(abs(v - a) <= 0.06 * a for a in okp):
                return m.group(0)
            low = norm(sent)
            named = [c for c in cards.values() if any(t in low for t in c['keys'])]
            c = named[0] if len(named) == 1 else (next(iter(cards.values())) if len(cards) == 1 else None)
            if c is None:
                log.setdefault('price_guard_unmapped', []).append(m.group(0)); return m.group(0)
            log.setdefault('price_guard_rewritten', []).append({'was': m.group(0), 'card_min': c['min']})
            keep = ' '.join(w for w in m.group(0)[:m.start(1) - m.start(0)].split() if w in ('قیمتش', 'قیمت', 'با', 'فقط'))
            return (keep + ' ' if keep else '') + 'از ' + fmt_toman(c['min'])
        out.append(_PRICE_RX.sub(rep, sent))
    return ''.join(out)

def card_prices(blocks):
    """{product_id: {min, max, keys}}: the SAME numbers the /app chat card shows (playground_home.card_info: fresh, non-suspicious
    offers first); falls back to the card's min_price."""
    items = [it for b in blocks if b.get('type') == 'product_cards' for it in (b.get('items') or []) if isinstance(it, dict) and it.get('product_id')]
    try:
        import playground_home as _HOME
        ci = _HOME.card_info([it['product_id'] for it in items])['cards']
    except Exception:
        ci = {}
    out = {}
    for it in items:
        c = ci.get(it['product_id']) or {}
        mn, mx = c.get('min_price') or it.get('min_price'), c.get('max_price')
        if not mn:
            continue
        keys = [w for w in re.findall(r'[a-z0-9]{2,}|[\u0600-\u06FF]{4,}', norm(it.get('title') or '')) if not w.isdigit()][:8]
        out[it['product_id']] = {'min': int(mn), 'max': int(mx) if mx else None, 'keys': keys}
    return out

def render_text(text, seen, log):
    def rep(m):
        v = _resolve(m.group(1), m.group(2), seen)
        if v is None:
            log['unknown_tokens'].append(m.group(2)); return ''
        cards = getattr(_RUN, 'cards', None) or {}
        pid = v.get('product_id') if m.group(1) == 'offer' else ident_pid(v, m.group(2))
        if pid in cards:          # the product is on a card: the text states the card's min price, nothing else
            log.setdefault('price_card_aligned', []).append({'token': m.group(2), 'card_min': cards[pid]['min'], 'offer_price': v.get('price') if m.group(1) == 'offer' else None})
            return 'از ' + fmt_toman(cards[pid]['min'])
        try:     # prices of products NOT on a card, rendered from DB tokens: the price guard leaves them alone
            okp = getattr(_RUN, 'ok_prices', None)
            if okp is not None:
                okp.append(v.get('price') if m.group(1) == 'offer' else (v.get('min_price_offer') or {}).get('price'))
        except Exception:
            pass
        return render_offer(v) if m.group(1) == 'offer' else render_product(v)
    facts = _run('facts') or {}
    def rep_spec(m):
        fid, claim = m.group(1), _ATTRIB.sub('', m.group(2)).strip(' ،,')
        f = facts.get(fid)
        src = f['source'] if f else 'gen'
        if src in ('db_spec', 'other_listing') and not _supports(claim, f['text']):
            log['spec_relabelled'].append({'claim': claim[:100], 'fact': f['text'][:100]}); src = 'gen'
        log['spec_sources'].append(src)      # provenance kept in the log only (owner: no labels in the text)
        return claim
    t = _ATTRIB.sub('', text) if _run('pk') else text   # the model can never attribute to Torob by itself (labels come only from fact tags)
    t = _SPEC.sub(rep_spec, t)
    t = re.sub(r'\(\s*\)|،\s*،', '', t)
    return _TOK.sub(rep, t)

_CSTOP = set(norm(w) for w in 'این آن است هست دارد دارای با به از که و یا را برای در هم یک شده می شود نیز همین مدل گوشی دستگاه آن را'.split())
def _supports(claim, fact):
    """a DB-tagged claim must be backed by the fact: every number/Latin token in it appears in the fact,
    and most of its content words do (closes the Persian-only false-claim gap)."""
    c, f = norm(claim), norm(fact)
    toks = re.findall(r'[a-z0-9]+', c)
    if any(t not in re.findall(r'[a-z0-9]+', f) for t in toks):
        return False
    words = [w for w in re.split(r'[\s،,.:؛]+', c) if len(w) >= 3 and w not in _CSTOP and not re.fullmatch(r'[a-z0-9]+', w)]
    if not words:
        return True
    hit = sum(1 for w in words if w in f or (len(w) > 4 and w[:-1] in f))
    return hit / len(words) >= 0.6


# ================================================================== main loop
_SEARCH_TOOLS = {'find_products', 'text_search', 'sql', 'bazaar_hubs', 'product_knowledge'}
def _need_second_tool_round(trace):
    """after round 1: allow one more (narrowed) tool round only if round 1 produced nothing usable"""
    r1 = [t for t in trace if t.get('step') == 0]
    if not r1:
        return False
    useful = [t for t in r1 if t['tool'] in _SEARCH_TOOLS and not t.get('error')
              and (t['rows'] > 0 if isinstance(t.get('rows'), int) else (t.get('n_pids') or t['tool'] in ('bazaar_hubs', 'product_knowledge', 'sql')))]
    return not useful

def _call(msgs, forced, el, log_usage, narrow=False):
    tools = TOOL_SCHEMAS if getattr(_RUN, 'allow_project', True) else [t for t in TOOL_SCHEMAS if t is not _SP_SCHEMA]
    if narrow:     # 2nd tool round: search tools only
        tools = [t for t in tools if t['function']['name'] in ('find_products', 'text_search', 'product_knowledge', 'sql', 'geocode_area')]
    kw = dict(model=MODEL, messages=msgs, max_completion_tokens=MAX_COMPLETION_TOKENS, reasoning_effort='none', tools=tools,
              response_format={'type': 'json_object'})
    if forced:
        kw['tool_choice'] = 'none'; kw['timeout'] = max(2.0, TURN_FINAL_BY_S - el)
    else:
        kw['timeout'] = max(2.0, min(LLM_STEP_TIMEOUT_S, TURN_SOFT_S + 4 - el))
    _ts = time.time()
    resp = B.client().chat.completions.create(**kw)
    u = resp.usage
    log_usage.setdefault('llm_steps', []).append({'ms': int((time.time() - _ts) * 1000), 'in': u.prompt_tokens, 'out': u.completion_tokens,
                                                  'tools': [tc.function.name for tc in (resp.choices[0].message.tool_calls or [])]})
    log_usage['prompt_tokens'] += u.prompt_tokens; log_usage['completion_tokens'] += u.completion_tokens
    c = B._usage_cost(u); log_usage['cost'] += c; COST['llm'] += c; log_usage['api_calls'] += 1
    return resp.choices[0].message

def run_agent_v3plus(messages_or_question, session_mission=None, user_lat=None, user_lon=None, allow_project=True, single_tool_round=False):
    _RUN.allow_project = allow_project
    _RUN.single_tool_round = single_tool_round   # late-night/urgent turns: no 2nd search round (server adds the open-shop step)
    hist = [{'role': 'user', 'content': messages_or_question}] if isinstance(messages_or_question, str) else list(messages_or_question)
    user_text = next((m['content'] for m in reversed(hist) if m.get('role') == 'user'), '')
    _PCACHE.clear()
    _RUN.fp, _RUN.pk, _RUN.facts = [], [], {}
    _RUN.constraints = (session_mission or {}).get('_constraints') or {}
    _RUN.constraints_new = None
    _RUN.user_ll = (user_lat, user_lon) if user_lat is not None else None
    ml = (session_mission or {}).get('area_latlon')
    _RUN.point = _RUN.user_ll or (tuple(ml) if isinstance(ml, list) and len(ml) == 2 and all(isinstance(x, (int, float)) for x in ml) else None)
    msgs = [{'role': 'system', 'content': system_prompt(session_mission, user_lat, user_lon)}] + hist
    usage = {'prompt_tokens': 0, 'completion_tokens': 0, 'cost': 0.0, 'api_calls': 0}
    trace, seen_nums, final, rescue = [], [], None, False
    t0 = time.time()
    try:
        for step in range(MAX_STEPS + 1):
            el = time.time() - t0
            if el >= TURN_FINAL_BY_S - 2:
                final = {'_error': f'turn deadline ({el:.1f}s)'}; break
            narrow = step == 1 and not getattr(_RUN, 'single_tool_round', False) and _need_second_tool_round(trace)
            forced = step >= MAX_STEPS or (step >= 1 and not narrow) or el >= TURN_SOFT_S or rescue
            if forced:
                msgs.append({'role': 'system', 'content': 'Now write the final JSON answer from these tool results (no more tools).'
                             if step < MAX_STEPS and not rescue else 'Budget used up: give the final JSON answer now with what you have.'})
            elif narrow:
                msgs.append({'role': 'system', 'content': 'Round 1 found nothing usable: one more search round (rewrite the query / widen the area or budget), then answer.'})
            _emit('status', {'stage': 'writing' if forced or step > 0 and trace else 'thinking', 'step': step})
            try:
                m = _call(msgs, forced, el, usage, narrow=narrow)
            except Exception as e:
                if not forced and trace and time.time() - t0 < TURN_FINAL_BY_S - 5:
                    rescue = True; usage['rescued_after_error'] = str(e)[:120]; continue
                final = {'_error': str(e)[:200] + f' (step {step})'}; break
            if not m.tool_calls:
                final = B._parse_final(m.content); final['_raw'] = m.content or ''; break
            if forced:
                break
            sp = next((tc for tc in m.tool_calls if tc.function.name == 'start_project'), None)
            if sp is not None:     # the agent decided this is a multi-item project -> the server's «خرید یکجا» planner takes over
                try:
                    goal = str(json.loads(sp.function.arguments or '{}').get('goal') or '').strip()[:400]
                except Exception:
                    goal = ''
                trace.append({'step': step, 'tool': 'start_project', 'args': {'goal': goal}, 'ms': 0})
                return {'project_intent': True, 'project_goal': goal or user_text, 'usage': usage, 'tool_trace': trace, 'engine': 'v3plus',
                        'elapsed_s': round(time.time() - t0, 1)}
            msgs.append({'role': 'assistant', 'content': None, 'tool_calls': [
                {'id': tc.id, 'type': 'function', 'function': {'name': tc.function.name, 'arguments': tc.function.arguments}} for tc in m.tool_calls]})
            _emit('status', {'stage': 'searching', 'tools': [tc.function.name for tc in m.tool_calls]})
            for tc in m.tool_calls:
                try:
                    args = json.loads(tc.function.arguments or '{}')
                except Exception:
                    args = {}
                fn = B.TOOLS.get(tc.function.name)
                ts = time.time()
                try:
                    res = fn(args) if fn else {'error': 'unknown tool'}
                except Exception as e:
                    res = {'error': f'{type(e).__name__}: {str(e)[:150]}'}
                js = json.dumps(res, ensure_ascii=False, separators=(',', ':'))
                seen_nums += [float(x) for x in re.findall(r'(?<![\w.])\d{5,}(?:\.\d+)?', js)]
                trace.append({'step': step, 'tool': tc.function.name, 'args': args, 'ms': int((time.time() - ts) * 1000),
                              'rows': res.get('row_count', res.get('count', len(res.get('results', [])) if isinstance(res.get('results'), list) else None)),
                              'error': res.get('error'), 'out_chars': len(js), 'n_pids': len(set(re.findall(r'product_[0-9a-f]{16,32}', js)))})
                msgs.append({'role': 'tool', 'tool_call_id': tc.id, 'content': js[:9000]})
                if tc.function.name in ('find_products', 'text_search') and not res.get('error'):    # progress only: raw tool results are never shown as cards
                    _emit('status', {'stage': 'searching', 'tool': tc.function.name, 'n_found': len(set(re.findall(r'product_[0-9a-f]{16,32}', js)))})
        final = final or {'_error': 'no final answer'}
        if final.get('_error') or final.get('_parse_error') or not (final.get('text') or '').strip():
            r = B._fallback(hist, session_mission, user_lat, user_lon, usage, trace, final, t0)
            r['engine'] = 'v3plus→agent.py fallback'
            return r
        seen = set(B._ID_RX.findall(' '.join(str(x.get('content') or '') for x in msgs if x.get('role') in ('tool', 'assistant'))))
        mission_in = session_mission or {}
        # ---- claim check + coverage (on the model's raw text, against computed facts) -> one regeneration
        log = {'unknown_tokens': [], 'spec_relabelled': [], 'spec_sources': [], 'regenerated': False}
        def evaluate(fin):
            bl, _ = B.hydrate(fin.get('blocks') or [], seen)
            return check_claims(fin.get('text') or '', seen, mission_in), coverage_check(bl, mission_in, user_text) + same_model_check(bl, user_text)
        _emit('status', {'stage': 'checking'})
        viol, miss = evaluate(final)
        log['violations_first'] = viol; log['coverage_missing_first'] = [m_['product_id'] for m_ in miss]
        # repair in code (strip unsupported claims, inject left-out cheaper items below); an LLM regeneration only if stripping would gut the answer
        log['repair'] = 'code'
        if viol and len(strip_claims(final.get('text') or '', viol).strip()) < 40 and time.time() - t0 < REGEN_IF_BEFORE_S:
            log['repair'] = 'llm_regen'
            fb = ['Server check of your answer (computed from the DB). Fix these and return the corrected final JSON (same format, tokens for prices). '
                  'The user never saw your draft: write the answer fresh for the user — do not acknowledge, apologise for or mention this check.']
            for v in viol:
                fb.append(f"- {v['type']}: «{v['sentence']}» {v.get('evidence', '')}")
            for g in miss:
                what = 'a cheaper up-to-date offer of the SAME model you showed' if g.get('same_model') else 'a cheaper item that meets the same constraints'
                fb.append(f"- coverage: {what} was left out: {g['title']} product_id={g['product_id']} offer {g['offer']['offer_id']} "
                          f"price {g['offer']['price']}. Include it (sellers, with its token in the text) or say concretely why it does not fit.")
            msgs.append({'role': 'assistant', 'content': final.get('_raw') or json.dumps({'text': final.get('text')}, ensure_ascii=False)})
            msgs.append({'role': 'user', 'content': '\n'.join(fb)})
            try:
                m = _call(msgs, True, time.time() - t0, usage)
                f2 = B._parse_final(m.content)
                if (f2.get('text') or '').strip() and not f2.get('_parse_error'):
                    f2['_raw'] = m.content; final = f2; log['regenerated'] = True
                    viol, miss = evaluate(final)
            except Exception as e:
                log['regen_error'] = str(e)[:120]
        log['violations_final'] = viol; log['coverage_missing_final'] = [m_['product_id'] for m_ in miss]
        text = final.get('text') or ''
        if viol:
            text = strip_claims(text, viol)
        blocks_raw = list(final.get('blocks') or [])
        miss = [g for g in miss if not _mentioned(g, final.get('text') or '')]
        if miss:   # deterministic injection of the left-out cheaper qualifying items
            blocks_raw.append({'type': 'product_cards', 'items': [{'product_id': g['product_id'], 'note': 'ارزان‌تر و با همین شرایط'} for g in miss]})
            blocks_raw.append({'type': 'sellers', 'items': [{'offer_id': g['offer']['offer_id'], 'note': 'ارزان‌تر و با همین شرایط'} for g in miss]})
            text += '\nگزینهٔ ارزان‌ترِ دیگری هم با همین شرایط هست: ' + '؛ '.join(f"{_short(g['title'])} {_TOKS(g)}" for g in miss) + '.'
        text, log['sanitized_raw'] = sanitize_boilerplate(text)
        if not _TOK.search(text):   # owner: always state the main recommendation's price (rounded) in prose
            text, log['price_added'] = _add_main_price(text, blocks_raw, seen)
        # cards ⊇ products the text names (by price token): the bubble never talks about a product that has no card
        _ment = []
        for _k, _id in _TOK.findall(text):
            _p = _id if _k == 'product' else (RO.execute('SELECT product_id FROM offers WHERE offer_id=?', (_id,)).fetchone() or [None])[0]
            if _p and _p not in _ment: _ment.append(_p)
        _pc = next((b for b in blocks_raw if isinstance(b, dict) and b.get('type') == 'product_cards'), None)
        _have = {it.get('product_id') for b in blocks_raw if isinstance(b, dict) and b.get('type') == 'product_cards' for it in (b.get('items') or []) if isinstance(it, dict)}
        _add = [p_ for p_ in _ment if p_ not in _have]
        if _add:
            if _pc is None:
                _pc = {'type': 'product_cards', 'items': []}; blocks_raw.insert(0, _pc)
            _pc['items'] = list(_pc.get('items') or []) + [{'product_id': p_} for p_ in _add]
            seen |= set(_add); log['cards_added_for_text'] = _add
        try:
            _cb, _ = B.hydrate([b for b in blocks_raw if isinstance(b, dict) and b.get('type') == 'product_cards'], seen)
            _RUN.cards = card_prices(_cb)
        except Exception:
            _RUN.cards = {}
        _RUN.ok_prices = []
        text = render_text(text, seen, log)
        text = price_guard(text, _RUN.cards, log)
        text = re.sub(r'(?<![\u0600-\u06FF])(?:با|از|حدود|حدوداً|تقریباً)\s+از\s+(?=[0-9۰-۹])', 'از ', text)   # «با از ۳٬۸۵۰٬۰۰۰» / «از از» -> «از …»
        _RUN.cards = _RUN.ok_prices = None
        blocks, hlog = B.hydrate(blocks_raw, seen)
        _emit('cards', {'items': [it for b in blocks if b.get('type') == 'product_cards' for it in b.get('items', [])]})   # final, checked selection (once)
        for b in blocks:
            for it in b.get('items', []) + b.get('products', []):
                for kk in ('price_toman', 'min_price', 'median_price'):
                    if isinstance(it, dict) and it.get(kk): seen_nums.append(float(it[kk]))
        for x in re.findall(r'[\d۰-۹][\d۰-۹٬,]{4,}', text):   # rendered prices are DB facts
            try: seen_nums.append(float(x.translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹', '0123456789')).replace('٬', '').replace(',', '')))
            except ValueError: pass
        for b in blocks:
            if b['type'] == 'verify':
                b['draft'] = True
        notes = []                       # owner decision 2026-10-23: the server appends no labels/disclaimers to the text
        text, log['sanitized'] = sanitize_boilerplate(text)
        text = no_km(text)
        for a_, b_ in ((r'\bsuspicious(_low)?\b', 'مشکوک'), (r'\bstale\b', 'قدیمی')):
            text = re.sub(a_, b_, text, flags=re.I)
        mission = final.get('mission') if isinstance(final.get('mission'), dict) else dict(mission_in)
        # server facts carried to the next turn: the lowest price shown now (reference for «ارزون‌تر»)
        ps = [it['price_toman'] for b in blocks if b['type'] in ('sellers', 'verify') for it in b['items'] if it.get('price_toman') and not it.get('suspicious_low')]
        ps += [it['min_price'] for b in blocks if b['type'] == 'product_cards' for it in b['items'] if it.get('min_price') and not it.get('min_price_suspicious_low')]
        if ps:
            mission['_shown_min_price'] = int(min(ps))
        elif mission_in.get('_shown_min_price'):
            mission['_shown_min_price'] = mission_in['_shown_min_price']
        if _RUN.constraints_new or _RUN.constraints:   # server-kept search constraints for follow-ups
            mission['_constraints'] = _RUN.constraints_new or _RUN.constraints
        hlog.update({'unverified_price_mentions': B.price_mentions_check(text, seen_nums), 'latin_runs_in_text': B._LATIN_RUN.findall(text),
                     'parse_repaired': bool(final.get('_parse_repaired')), 'raw_final': (final.get('_raw') or '')[:3000],
                     'sellers_outside_area': B._area_check(blocks, mission), 'fallback': None, 'v3plus': log, 'v3plus_appended_notes': notes,
                     'product_knowledge': _run('pk'), 'find_products_calls': [{'args': c['args'], 'n': len(c['result_ids'])} for c in _run('fp')]})
        titles = ' '.join(json.dumps(b, ensure_ascii=False) for b in blocks).lower() + ' ' + ' '.join(str(x.get('content', '')) for x in msgs if x.get('role') == 'tool').lower()
        hlog['latin_words_not_in_data'] = sorted({w for w in re.findall(r'[A-Za-z][A-Za-z\-]{2,}', text) if w.lower() not in titles})
        usage['cost_embed_this_process'] = round(COST['embed'], 5)
        sug = _clean_next(final.get('next'))
        qs, log['questions_dropped'] = validate_questions(final.get('questions'))
        return {'urgent_now': bool(final.get('urgent_now')), 'map_pins': final.get('map_pins') if isinstance(final.get('map_pins'), dict) else None, 'text': text, 'blocks': blocks, 'mission': mission, 'usage': usage, 'tool_trace': trace, 'hydration_log': hlog, 'engine': 'v3plus',
                'suggestions': sug, 'questions': qs,
                'elapsed_s': round(time.time() - t0, 1),
                'history_entry': {'role': 'assistant', 'content': json.dumps({'text': text, 'shown_ids': B.summarize_blocks(blocks).split('\n') if blocks else [], 'mission': mission}, ensure_ascii=False)}}
    finally:
        _RUN.fp = _RUN.pk = _RUN.facts = None

_NEXT_BAD = re.compile(r'زنگ|تماس|بخر|خرید کن|سفارش|رزرو|پرداخت|پیامک|واتس|\[\[|_[0-9a-f]{8}|[0-9]{5,}')
def _clean_next(v):
    """model-predicted next user prompts (same completion, no extra call): short, Persian, no calls/purchases/ids/prices"""
    out = []
    for x in (v if isinstance(v, list) else []):
        x = re.sub(r'\s+', ' ', str(x or '')).strip(' «»"')
        if 3 <= len(x) <= 60 and not _NEXT_BAD.search(x) and x not in out:
            out.append(x)
    return out[:3]

# ---------------------------------------------------------------- boilerplate sanitizer (logged; applied before display)
_SENT_SPLIT = re.compile(r'(?<=[.!؟?\n])')
_ASK = r'(بپرسید|بپرس|بپرسین|تأیید کنید|تایید کنید|تأیید بگیرید|استعلام بگیرید|استعلام کنید|چک کنید|هماهنگ کنید|مطمئن شوید|مطمئن شید)'
BOILERPLATE_DROP = [       # whole sentence is boilerplate -> drop (only if it carries no price token / digits)
    ('draft', re.compile(r'پیش[‌ ]?نویس')),
    ('no_real_call', re.compile(r'تماس(ی)? واقعی|تماسی (گرفته|انجام) نشد|با فروشگاه تماس نگرفتم')),
    ('consider_registered', re.compile(r'قیمت[‌ ]?(های|ها)? ثبت[‌ ]?شده را در نظر بگیرید')),
    ('ad_not_stock', re.compile(r'(آگهی|پیشنهاد)[‌ ]?(ها)?\s*(به[‌ ]?معنای|یعنی|به معنی)\s*موجودی|موجودی[^.!؟]{0,25}تضمین\s*(نمی[‌ ]?کند|نمی[‌ ]?شود|نیست)')),
    ('ask_before_going', re.compile(r'(پیش|قبل) از (رفتن|مراجعه|خرید|حرکت)[^.!؟]{0,60}' + _ASK + r'|' + _ASK + r'[^.!؟]{0,10}$')),
    ('price_may_change', re.compile(r'قیمت[‌ ]?(ها)?[^.!؟]{0,20}ممکن است (به[‌ ]?روز نباشد|تغییر کرده باشد)')),
    ('specs_label_sentence', re.compile(r'اطلاعات فنی[^.!؟]{0,30}(سازنده|ترب)[^.!؟]{0,20}است')),
    ('fake_phone', re.compile(r'شماره[‌ ]?(های)? (تماس|تلفن)[^.!؟]{0,30}(آزمایشی|نمایشی|واقعی نیست)')),
]
BOILERPLATE_CLAUSE = [     # remove just the clause inside an otherwise useful sentence
    ('hours_disclaimer', re.compile(r'\s*[(؛،\-—]?\s*(ساعت ثبت[‌ ]?شده\s*[؛،:]?\s*)?تعطیلی[‌ ]?ها(ی رسمی)? لحاظ نشده( است)?\s*\)?')),
    ('hours_registered', re.compile(r'ساعت ثبت[‌ ]?شدهٔ?\s*')),
    ('ask_clause', re.compile(r'\s*[،؛]?\s*(و\s*)?(پیش|قبل) از (رفتن|مراجعه|خرید)\s*[^.!؟،؛]{0,50}' + _ASK)),
    ('confirm_clause', re.compile(r'\s*(و\s*)?تأیید (بند و )?موجودی (پیش|قبل) از مراجعه')),
    ('provenance_tag', re.compile(r'\s*[—\-]\s*طبق مشخصات (عمومی سازنده \(نه داده[‌ ]?های ترب\)|ثبت[‌ ]?شده در ترب|آگهی دیگری از همین مدل در ترب)')),
    ('needs_reconfirm', re.compile(r'\s*[،؛]?\s*(و\s*)?(قیمت[‌ ]?(آن|اش|ش)?\s*)?نیاز به تأیید (دوباره|مجدد)( دارد)?')),
    ('not_torob_data', re.compile(r'\s*\(نه داده[‌ ]?های ترب\)')),
    ('registered_word', re.compile(r'(?<=قیمت)[‌ ]?(های)?\s*ثبت[‌ ]?شده(?=\s)')),
]
_DIGMAP = str.maketrans('۰۱۲۳۴۵۶۷۸۹٫', '0123456789.')
_KM_RX = re.compile(r'(?:(?:حدود|حدوداً|تقریباً)\s*)?([0-9۰-۹]+(?:[.٫][0-9۰-۹]+)?)\s*(?:کیلومتر|کیلو ?متر|km)(\s*(?:دورتر|فاصله(?:\s*(?:دارد|داره))?|راه))?')
_PCT_RX = re.compile(r'([0-9۰-۹]+[.٫][0-9۰-۹]+)\s*(٪|درصد)')
def naturalize_numbers(text, log):
    def km(m):
        try:
            k = float(m.group(1).translate(_DIGMAP))
        except ValueError:
            return m.group(0)
        new = natural_km(k)
        tail = (m.group(2) or '').strip()
        if tail.endswith(('دارد', 'داره')):      # «… فاصله دارد» -> keep a verb
            new += ' دارد' if k > 3 else ' است'
        log.append({'rule': 'distance_natural', 'removed': m.group(0).strip(), 'to': new})
        return new
    text = _KM_RX.sub(km, text)
    def pct(m):
        v = int(float(m.group(1).translate(_DIGMAP)) + 0.5)
        log.append({'rule': 'decimal_percent', 'removed': m.group(0)})
        return f'{_fa(str(v))}{m.group(2) if m.group(2) == "٪" else " " + m.group(2)}'
    return _PCT_RX.sub(pct, text)

_KM_WORDS = {'یک': 1, 'دو': 2, 'سه': 3, 'چهار': 4, 'پنج': 5, 'شش': 6, 'هفت': 7, 'هشت': 8, 'نه': 9, 'ده': 10}
_KM_RX = re.compile(r'(?:(?:حدود|حدوداً|تقریباً)\s*)?([0-9۰-۹]+(?:[٫.][0-9۰-۹]+)?|یک|دو|سه|چهار|پنج|شش|هفت|هشت|نه|ده)\s*کیلومتر(?:ی)?'
                    r'(?:[^،؛.\n]{0,40}?(?:فاصله\s*(?:داره|دارد|دارن|دارند)|دوره|دور است|دورن|دورند))?')
def no_km(text):
    """owner rule: distance only in words, never km numbers"""
    def rep(m):
        g = m.group(1)
        try: v = float(_KM_WORDS.get(g) or g.translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹٫', '0123456789.')))
        except ValueError: v = 6
        return 'همین نزدیکیه' if v < 1.5 else ('نزدیکه' if v < 5 else ('کمی دورتره' if v < 12 else 'دوره'))
    return _KM_RX.sub(rep, text or '')

def sanitize_boilerplate(text):
    """strip banned boilerplate the model (or older server code) may still emit. Returns (text, log list)."""
    log, out = [], []
    text = naturalize_numbers(text or '', log)
    for sent in _SENT_SPLIT.split(text or ''):
        if not sent.strip():
            out.append(sent); continue
        has_fact = bool(_TOK.search(sent) or re.search(r'[0-9۰-۹]', sent))
        hit = next((k for k, rx in BOILERPLATE_DROP if rx.search(sent)), None)
        if hit and not has_fact:
            log.append({'rule': hit, 'removed': sent.strip()[:160]}); continue
        for k, rx in BOILERPLATE_CLAUSE + ([] if not hit else [(hit, BOILERPLATE_DROP[[x for x, _ in BOILERPLATE_DROP].index(hit)][1])]):
            new = rx.sub('', sent)
            if new != sent:
                log.append({'rule': k, 'removed': (set(sent.split()) - set(new.split())) and ' '.join(w for w in sent.split() if w not in new.split())[:120]}); sent = new
        out.append(sent)
    t = ''.join(out)
    t = re.sub(r'[ \t]{2,}', ' ', t)
    t = re.sub(r'\s+([،؛.!؟])', r'\1', t)
    t = re.sub(r'([،؛])\s*([.!؟])', r'\2', t)
    t = re.sub(r'\n{2,}', '\n', t).strip()
    return (t or (text or '').strip()), log

# ---------------------------------------------------------------- clarifying questions (same completion; schema-validated)
_QTYPES = ('single', 'multi', 'text', 'range')
_QBAD = re.compile(r'تماس|زنگ|شماره|کارت بانکی|رمز|آدرس منزل|کد ملی')
def validate_questions(v):
    out, dropped = [], []
    for q in (v if isinstance(v, list) else [])[:5]:
        try:
            if not isinstance(q, dict): raise ValueError('not an object')
            qid = re.sub(r'[^a-z0-9_]', '', str(q.get('id') or '').lower())[:32]
            title = re.sub(r'\s+', ' ', str(q.get('title') or '')).strip()
            typ = q.get('type')
            if not qid or not (3 <= len(title) <= 90) or typ not in _QTYPES: raise ValueError('id/title/type')
            if _QBAD.search(title) or re.search(r'[A-Za-z]{4,}', title): raise ValueError('banned/latin title')
            opts = []
            for o in (q.get('options') or [])[:8]:
                if isinstance(o, str): o = {'label': o, 'value': o}
                lab = re.sub(r'\s+', ' ', str((o or {}).get('label') or '')).strip()
                if 1 <= len(lab) <= 40 and not _QBAD.search(lab) and lab not in [x['label'] for x in opts]:
                    opts.append({'label': lab, 'value': str(o.get('value') if o.get('value') not in (None, '') else lab)[:40]})
            if typ in ('single', 'multi') and len(opts) < 2: raise ValueError('needs >=2 options')
            if typ == 'text': opts = []
            if qid in [x['id'] for x in out]: raise ValueError('duplicate id')
            out.append({'id': qid, 'title': title, 'type': typ, 'options': opts[:6],
                        'allow_custom': bool(q.get('allow_custom', typ in ('text', 'range')) or typ == 'text')})
        except Exception as e:
            dropped.append({'q': str(q)[:160], 'why': str(e)[:60]})
        if len(out) == 3: break
    return out, dropped

def _add_main_price(text, blocks_raw, seen):
    """model gave no price token: add one short natural sentence with the first recommended item's price (token -> DB)"""
    for b in blocks_raw:
        if not isinstance(b, dict):
            continue
        items = b.get('items') or []
        if b.get('type') == 'product_cards' and items and isinstance(items[0], dict) and items[0].get('product_id') in seen:
            p = product_facts(items[0]['product_id'])
            if p and p.get('min_price_offer'):
                tok = f"[[offer:{(p['cheapest_fresh_offer'] or p['min_price_offer'])['offer_id']}]]"
                return text.rstrip() + f' {_short(p["title"], 40)} از {tok} شروع می‌شه.', p['product_id']
        if b.get('type') == 'sellers' and items and isinstance(items[0], dict) and items[0].get('offer_id') in seen:
            o = offer_facts(items[0]['offer_id'])
            if o and o.get('price'):
                pf = product_facts(o['product_id'])
                return text.rstrip() + f' {_short((pf or {}).get("title") or "", 40)} با [[offer:{o["offer_id"]}]].', o['offer_id']
    return text, None

def _TOKS(g):
    return f"[[offer:{g['offer']['offer_id']}]]"

def _short(t, n=48):
    t = (t or '').split('|')[0].strip()
    return t if len(t) <= n else t[:n].rsplit(' ', 1)[0]

def _mentioned(g, text):
    """the text names this item (its model code / offer token) -> the model addressed it; don't inject it"""
    t = norm(text)
    if g['offer']['offer_id'] in text:
        return True
    code = g['family'].split(':', 1)[-1]
    return bool(code) and len(code) >= 3 and re.search(r'[a-z0-9]', code) is not None and code in t
