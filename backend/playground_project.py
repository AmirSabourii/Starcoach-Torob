"""«خرید یکجا» — one-stop project shopping assistant.
plan(): ONE short LLM call -> clarifying questions OR a structured needs list (domain knowledge only, no prices/shops).
search(): pure server side (lexical product search + DB offers) -> candidates per need + 2-3 optimized plans.
summary(): ONE tiny LLM call (1-3 Persian sentences) over server-computed plan facts.
Prices/shops/stock come ONLY from the DB; shops are linked by shop_id."""
import json, math, re, time, statistics
import tools as T
import playground_drill as D
import playground_bazaar as BZ

MODEL = 'gpt-6-luna'
FA2EN = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')
PROJECT_RE = re.compile(r'سیم[‌ ]?کشی|برق[‌ ]?کشی|سیم کشی|تجهیز|راه[‌ ]?اندازی|خرید یکجا|یکجا بخرم|همه رو یکجا|خون[هة]ٔ? جدید|خانهٔ? جدید|جهیزیه|'
                        r'(وسایل|لوازم|تجهیزات)\s+(آشپزخ|حموم|حمام|مغازه|دفتر|اتاق|واحد|خونه|خانه)|دوربین\s*(مدار\s*بسته|مداربسته).{0,30}(مغازه|واحد|خونه|خانه|\d|[۰-۹]|تا)|'
                        r'(مغازه|واحد|آپارتمان|خونه|خانه|دفتر).{0,25}(متری|متر)')

def is_project(msg):
    return bool(PROJECT_RE.search(msg or ''))

_SYS = """You plan ONE-STOP shopping projects for a Persian shopping assistant whose catalogue is Torob (Tehran shops). Reply with JSON only.
Decide one of:
A) Not a multi-item project -> {"intent":"other"}
B) Project, but key facts are missing (size m², counts, quality tier, budget, preferred Tehran area) AND "force" is false ->
   {"intent":"project","title":"<short Persian title>","say":"<1 short warm Persian sentence to the user>","questions":[<=3 objects {"id":"latin_snake","title":"Persian question <=80 chars","type":"single|multi|text|range","options":["Persian label",...],"allow_custom":true}]}
   Ask only what really changes the list (usually size/count and quality tier; area of Tehran as optional). Never ask what the user already said.
C) Otherwise (or when force is true: assume sensible defaults and mention them in "assumptions") ->
   {"intent":"project","title":"...","say":"<1 short warm Persian sentence, e.g. what the list covers>","assumptions":"<=12 Persian words listing ONLY the assumed facts (e.g. «۸۰ متر، کیفیت استاندارد، ۴ دوربین»), no advice/disclaimers","needs":[6-12 objects]}
   need = {"id":"n1","item":"Persian item name","query":"2-4 Persian words exactly as Iranian shop titles write it, e.g. «سیم افشان 2.5», «کلید مینیاتوری 16 آمپر», «پریز برق توکار», «دی وی آر 4 کانال», «هارد اینترنال 1 ترابایت»","must":["<=2 tokens that must appear in the product title, Latin digits (e.g. «2.5», «16»)"],"avoid":["words that mark a different product, e.g. for a light switch: «پریز»"],"category_hint":"Persian category word","qty":<number in purchase units>,"unit":"عدد|حلقه ۱۰۰ متری|بسته|متر","specs":"short required specs (Persian)","priority":"essential|optional","why":"<=12 Persian words","attrs":{"system":"ip|analog|any (CCTV only: cameras/recorder/cable/connectors)","poles":<int or null>,"amps":<int or null>,"cross_section_mm2":<number or null>,"mp":<int or null>,"channels":<int or null>,"volt":<int or null>}}
   CCTV: pick ONE system for the whole list (IP cameras + NVR + network cable/PoE, or analog AHD/TVI/CVI cameras + DVR/XVR + coax RG59 + BNC) and set attrs.system on every CCTV item accordingly.
Domain knowledge (use realistic quantities): apartment wiring ~80 m²: wire 1.5 mm² for lighting (2-3 rolls of 100 m), 2.5 mm² for sockets (2-3 rolls), 4 mm² for kitchen/cooler/AC (1 roll), MCB 10A x3-4 and 16A x4-6 and 25A x1-2, 1 RCD (residual current), 1 distribution panel box, sockets ~20, switches ~12, LED panel lights ~10, conduit/flex hose, junction boxes. CCTV for N cameras: N cameras (bullet/dome), DVR/XVR (analog) or NVR (IP) with >=N channels, surveillance HDD 1-2 TB, coax or network cable (one 100-305 m roll), 12V power supply/adapters, BNC/DC connectors.
Kitchen move-in: core appliances + cookware. Never state prices, shops or brands as facts. Persian text everywhere except ids."""

def _llm_json(client_fn, cost_fn, add_spend, sys_, user, max_tokens):
    r = client_fn().chat.completions.create(model=MODEL, messages=[{'role': 'system', 'content': sys_}, {'role': 'user', 'content': user}],
                                            max_completion_tokens=max_tokens, reasoning_effort='none', response_format={'type': 'json_object'}, timeout=40)
    c = cost_fn(r.usage); add_spend(c)
    u = r.usage
    return json.loads(r.choices[0].message.content or '{}'), {'cost_usd': round(c, 6), 'prompt_tokens': u.prompt_tokens, 'completion_tokens': u.completion_tokens}

def _clean_attrs(a):
    out = {}
    if not isinstance(a, dict): return out
    if a.get('system') in ('ip', 'analog'): out['system'] = a['system']
    for k, typ in (('poles', int), ('amps', int), ('cross_section_mm2', float), ('mp', int), ('channels', int), ('volt', int)):
        try:
            v = typ(a[k]) if a.get(k) not in (None, '', 'null') else None
            if v and v > 0: out[k] = v
        except Exception: pass
    return out

def _clean_need(n, i):
    if not isinstance(n, dict) or not n.get('item') or not n.get('query'):
        return None
    try: qty = float(n.get('qty') or 1)
    except Exception: qty = 1.0
    qty = max(1, min(int(round(qty)), 500))
    return {'id': re.sub(r'[^a-z0-9_]', '', str(n.get('id') or f'n{i+1}').lower())[:12] or f'n{i+1}',
            'item': str(n['item'])[:60], 'query': str(n['query'])[:60], 'must': [str(x).translate(FA2EN)[:20] for x in (n.get('must') or [])][:2], 'avoid': [str(x)[:20] for x in (n.get('avoid') or [])][:4],
            'category_hint': str(n.get('category_hint') or '')[:40], 'qty': qty, 'unit': str(n.get('unit') or 'عدد')[:20],
            'specs': str(n.get('specs') or '')[:120], 'priority': 'optional' if n.get('priority') == 'optional' else 'essential',
            'why': str(n.get('why') or '')[:90], 'enabled': True, 'attrs': _clean_attrs(n.get('attrs'))}

def plan(goal, answers, client_fn, cost_fn, add_spend, validate_questions, force=False):
    t0 = time.time()
    ans_txt = '\n'.join(f"- {a.get('title')}: {a.get('answer')}" for a in (answers or []) if isinstance(a, dict))
    user = json.dumps({'goal': goal, 'answers': ans_txt or None, 'force': bool(force or answers)}, ensure_ascii=False)
    j, usage = _llm_json(client_fn, cost_fn, add_spend, _SYS, user, 1300)
    out = {'goal': goal, 'intent': j.get('intent') or 'other', 'title': str(j.get('title') or '')[:60], 'say': str(j.get('say') or '')[:220], 'llm_calls': 1, 'usage': usage}
    if out['intent'] != 'project':
        out['stage'] = 'not_project'
    elif j.get('needs') and (force or answers or not j.get('questions')):
        needs = [x for x in (_clean_need(n, i) for i, n in enumerate(j['needs'][:14])) if x]
        seen = set(); needs = [n for n in needs if not (n['id'] in seen or seen.add(n['id']))]
        out.update(stage='needs', needs=needs, assumptions=str(j.get('assumptions') or '')[:160])
    else:
        qs, dropped = validate_questions(j.get('questions'))
        out.update(stage='questions', questions=qs, questions_dropped=dropped)
        if not qs:   # nothing valid to ask -> force the list (second call only in this rare case)
            return plan(goal, [{'title': 'پیش‌فرض', 'answer': 'معمولی'}], client_fn, cost_fn, add_spend, validate_questions, force=True)
    out['elapsed_s'] = round(time.time() - t0, 1)
    return out

# ----------------------------------------------------------------- server-side search (no LLM)
def _n(s):
    return re.sub(r'\s+', ' ', (s or '').translate(FA2EN).replace('ي', 'ی').replace('ك', 'ک').replace('\u200c', ' ')).lower()

ROLL_RE = re.compile(r'حلقه|کلاف|(100|۱۰۰|305|۳۰۵|200|50)\s*متر')

def _offers_for(pid, title, image):
    po = D.product_offers(pid) or {}
    out = []
    for o in po.get('offers', []):
        if not o['price_toman'] or o['suspicious'] or not o['shop_id']:
            continue
        geo = T._shop_geo(o['shop_id'])
        out.append({'offer_id': o['offer_id'], 'product_id': pid, 'title': title, 'image': image, 'shop_id': o['shop_id'], 'shop_name': o['shop_name'],
                    'area': o['shop_area'], 'lat': geo[2], 'lon': geo[3], 'price_toman': o['price_toman'], 'stale': o['stale'],
                    'date_fa': o['date_fa'], 'age_days': o['age_days'], 'sys': attrs_of(title).get('system')})
    return out

HEAD_ALT = {'فیوز': ['فیوز', 'مینیاتوری'], 'هارد': ['هارد', 'اچ دی دی', 'hdd'], 'دی': ['دی وی آر', 'dvr', 'xvr', 'ان وی آر', 'nvr'],
            'آداپتور': ['آداپتور', 'منبع تغذیه', 'adapter'], 'منبع': ['منبع تغذیه', 'آداپتور'], 'لامپ': ['لامپ'], 'پنل': ['پنل', 'چراغ']}
CONFLICT = {'کلید': ['پریز', 'مینیاتوری', 'محافظ جان', 'چندراهی'], 'پریز': ['چندراهی', 'سیار', 'محافظ', 'کلید مینیاتوری'],
            'سیم': ['سیار', 'چندراهی', 'کابلشو', 'لخت کن'], 'دوربین': ['پایه', 'قاب', 'کیف', 'باتری', 'پک ', 'پکیج', 'کیت', 'ست ', 'ضبط', 'دی وی آر', 'dvr', 'nvr', 'xvr'], 'کابل': ['کانکتور', 'تستر', 'آچار'], 'فیش': ['فیش آی', 'fish eye', 'پاناروما', 'فیشر']}

# ---- structural attributes (parsed from titles and from need text; DB titles are the only source for products)
WIRE_SECTIONS = {0.75, 1.0, 1.5, 2.5, 4.0, 6.0, 10.0, 16.0, 25.0}
_PW = {'تک': 1, 'یک': 1, 'دو': 2, 'سه': 3, 'چهار': 4}
def _num(x):
    try: return float(x)
    except Exception: return None

def attrs_of(text, head=None):
    t = _n(text)
    a = {}
    m = re.search(r'(?<![\d.])(\d{1,3})\s*(?:آمپر|a\b|amp)', t)
    if m: a['amps'] = int(m.group(1))
    m = re.search(r'(?<![\d.])([1-4])\s*(?:پل|p\b|pole)', t) or re.search(r'(تک|یک|دو|سه|چهار)\s*پل', t)
    if m: a['poles'] = _PW.get(m.group(1)) or int(m.group(1))
    m = re.search(r'(?<![\d.])(\d{1,2}(?:\.\d)?)\s*(?:مگا\s*پیکسل|مگاپیکسل|mp\b|مگ\b)', t)
    if m: a['mp'] = _num(m.group(1))
    m = re.search(r'(?<![\d.])(\d{1,2})\s*(?:کانال|ch\b|channel)', t)
    if m: a['channels'] = int(m.group(1))
    m = re.search(r'(?<![\d.])(\d{1,3})\s*(?:ولت|v\b)', t)
    if m: a['volt'] = int(m.group(1))
    if head in ('سیم', 'کابل') and not re.search(r'شبکه|cat|rg|ترکیبی|کواکسیال|دوربین|hdmi|usb', t):
        secs = []
        for m in re.finditer(r'(?<![\d.])(\d{1,2}(?:\.\d{1,2})?)(?![\d.])(?!\s*(?:متر|متری|آمپر|ولت|عدد|رشته|پل|ترابایت|گیگ))', t):
            v = _num(m.group(1))
            if v in WIRE_SECTIONS: secs.append(v)
        if secs: a['sections'] = sorted(set(secs))
    sysm = None
    if re.search(r'(?<![a-z])nvr|ان وی آر|تحت شبکه|\bip\b|ipc[- ]|ds-2cd|\bpoe\b|cat ?5|cat ?6|کابل شبکه|سوکت شبکه|rj45|بیسیم|وای ?فای|wifi', t): sysm = 'ip'
    if re.search(r'(?<![a-z])dvr|(?<![a-z])xvr|دی وی آر|ایکس وی آر|\bahd\b|\btvi\b|\bcvi\b|hdcvi|توربو|آنالوگ|hac[- ]|ds-2ce|\buvc|rg ?59|rg ?6\b|کواکسیال|کابل ترکیبی|\bbnc\b|بی ان سی|بی‌ان‌سی', t):
        sysm = 'mixed' if sysm == 'ip' else 'analog'
    cctv = re.search(r'دوربین|مدار ?بسته|(?<![a-z])nvr|(?<![a-z])dvr|(?<![a-z])xvr|دی وی آر|ان وی آر|ایکس وی آر|\bbnc\b|بی ان سی|rg ?59|\bpoe\b|ضبط کننده', t)
    if sysm and sysm != 'mixed' and cctv: a['system'] = sysm
    return a

def need_attrs(need):
    """attrs requested by the need: planner attrs win; otherwise parsed from the need's own words"""
    head = _n(need.get('query')).split(' ')[0] if need.get('query') else None
    a = attrs_of(' '.join([need.get('item') or '', need.get('query') or '']), head)
    if a.get('sections'):
        a['cross_section_mm2'] = a.pop('sections')[0]
    a.pop('system', None)     # system words in a need's text (e.g. «فیش BNC») describe the item, not a project choice
    for k, v in (need.get('attrs') or {}).items():
        a[k] = v
    return a

def attr_conflict(title, need):
    """None if the title is consistent with the need's numeric specs; else a short reason"""
    na = need.get('_na') if need.get('_na') is not None else need_attrs(need)
    head = _n(need.get('query')).split(' ')[0] if need.get('query') else None
    ta = attrs_of(title, head)
    for k in ('amps', 'poles', 'volt'):
        if na.get(k) and ta.get(k) and int(na[k]) != int(ta[k]): return f'{k} {ta[k]}≠{na[k]}'
    for k in ('mp', 'channels'):
        if na.get(k) and ta.get(k) and ta[k] < na[k]: return f'{k} {ta[k]}<{na[k]}'
    if na.get('cross_section_mm2') and ta.get('sections') and float(na['cross_section_mm2']) not in ta['sections']:
        return f"mm2 {ta['sections']}≠{na['cross_section_mm2']}"
    return None

def _title_ok(title, need):
    t = _n(title)
    q = _n(need.get('query'))
    head = q.split(' ')[0] if q else ''
    alts = HEAD_ALT.get(head, [head] if len(head) >= 2 else [])
    if alts and not any(_n(a) in t for a in alts):
        return False
    for bad in CONFLICT.get(head, []) + [_n(x) for x in need.get('avoid') or []]:
        if bad and _n(bad) in t and _n(bad) not in q:
            return False
    na = need.get('_na') if need.get('_na') is not None else need_attrs(need)
    covered = set()
    if na.get('mp'): covered |= {'مگاپیکسل', 'مگا پیکسل', 'mp'}
    if na.get('channels'): covered |= {'کانال'}
    if na.get('amps'): covered |= {'آمپر'}
    if na.get('poles'): covered |= {'پل'}
    if na.get('volt'): covered |= {'ولت'}
    nums = {str(int(v)) if float(v).is_integer() else str(v) for k, v in na.items() if isinstance(v, (int, float))}
    for m in need.get('must') or []:
        m = _n(m)
        if not m or m in covered or m in nums: continue     # numeric specs are checked structurally (attr_conflict), not as substrings
        if re.fullmatch(r'[\d.]+', m):     # numeric must-token = whole number (so «2» doesn't match «32»)
            if not re.search(r'(?<![\d.])' + re.escape(m) + r'(?![\d]|\.\d)', t): return False
        elif m not in t: return False
    return attr_conflict(title, need) is None

def candidates(need, k_products=25):
    tried, res, seen = [], [], set()
    qs = [need['query'], need['item']]
    if re.search(r'دوربین|دی وی آر|ان وی آر|ضبط', need['query'] + need['item']):    # diversify CCTV pools so both systems are represented
        sysw = (need.get('attrs') or {}).get('system')
        qs += ([need['query'] + ' AHD', need['query'] + ' توربو'] if sysw != 'ip' else []) + ([need['query'] + ' تحت شبکه'] if sysw != 'analog' else [])
    for qq in dict.fromkeys(qs):
        r = T.search_products_lexical(qq, limit=15)
        tried.append(qq)
        for x in r.get('results', []):
            if x['product_id'] in seen or any(str(f).startswith(('USED', 'KNOCK')) for f in x.get('flags', [])):
                continue
            seen.add(x['product_id']); res.append(x)
    pool = [x for x in res if _title_ok(x['title'], need)]
    if 'حلقه' in need.get('unit', '') or 'متر' in need.get('unit', ''):
        rolls = [x for x in pool if ROLL_RE.search(_n(x['title']))]
        pool = rolls or pool
    alt = None
    if not pool and res:
        a = res[0]; alt = {'product_id': a['product_id'], 'title': a['title'], 'min_price': a.get('min_price'), 'category': a.get('category')}
    pool = pool[:k_products]
    opts, prods = [], []
    for x in pool:
        h = D.product_head(x['product_id']) or {}
        os_ = _offers_for(x['product_id'], h.get('title') or x['title'], h.get('image'))
        if os_:
            prods.append({'product_id': x['product_id'], 'title': h.get('title') or x['title'], 'image': h.get('image'), 'category': x.get('category'),
                          'min_price': min(o['price_toman'] for o in os_), 'n_offers': len(os_), 'n_fresh': sum(not o['stale'] for o in os_)})
            opts += os_
    n_out = 0
    is_roll = 'حلقه' in need.get('unit', '') or 'متر' in need.get('unit', '')
    if is_roll and len(opts) >= 6:      # per-metre / accessory listings hiding among unit/roll products: drop offers < 30% of the offer median (DB data only)
        med = statistics.median(o['price_toman'] for o in opts)
        keep = [o for o in opts if o['price_toman'] >= 0.3 * med]
        n_out = len(opts) - len(keep); opts = keep
    opts.sort(key=lambda o: _eff(o))
    prods.sort(key=lambda p: p['min_price'])
    return {'need_id': need['id'], 'queries_tried': tried, 'products': prods[:4], 'options': opts[:40], 'n_low_outliers_dropped': n_out,
            'alternative': None if opts else alt}

def _eff(o):
    # stale >30d deprioritized (still allowed); a row that breaks the plan's system is heavily penalised (and badged, never silent)
    return o['price_toman'] * (1.15 if o['stale'] else 1.0) * (1.6 if o.get('incompatible') else 1.0) * (1.3 if o.get('unverified') else 1.0)

CORE_RE = re.compile(r'دوربین|ضبط|دی وی آر|ان وی آر|nvr|dvr|xvr')
def _is_core(need):
    t = _n((need.get('item') or '') + ' ' + (need.get('query') or ''))
    return bool(CORE_RE.search(t)) and not re.search(r'کابل|فیش|تغذیه|آداپتور|هارد|پایه|قاب|کانکتور|سوکت', t)

# ----------------------------------------------------------------- optimizer
def _spread(shops):
    pts = [(s['lat'], s['lon']) for s in shops if s.get('lat') is not None]
    if len(pts) < 2: return 0.0
    return max(T.haversine(a[0], a[1], b[0], b[1]) for i, a in enumerate(pts) for b in pts[i + 1:])

def _cost(assign, needs_q, lam, mu, user_c=None, nu=0):
    shops = {}
    tot = 0.0
    for nid, o in assign.items():
        tot += _eff(o) * needs_q[nid]
        shops[o['shop_id']] = o
    c = tot + lam * max(0, len(shops) - 1) + mu * _spread(list(shops.values()))
    if user_c and nu:
        ds = [T.haversine(user_c[0], user_c[1], s['lat'], s['lon']) for s in shops.values() if s.get('lat') is not None]
        c += nu * (max(ds) if ds else 0)
    return c

def _local_search(start, opts, needs_q, lam, mu, user_c=None, nu=0):
    cur = dict(start); best = _cost(cur, needs_q, lam, mu, user_c, nu)
    for _ in range(30):
        improved = False
        # 1) move an item to a shop already used
        used = {o['shop_id'] for o in cur.values()}
        for nid in cur:
            for o in opts[nid]:
                if o['shop_id'] in used and o is not cur[nid]:
                    trial = dict(cur); trial[nid] = o
                    c = _cost(trial, needs_q, lam, mu, user_c, nu)
                    if c < best - 1: cur, best, improved = trial, c, True
        # 2) close a shop: move all its items to other used shops (or any shop)
        for sid in list({o['shop_id'] for o in cur.values()}):
            trial = dict(cur); ok = True
            others = {o['shop_id'] for n_, o in cur.items() if o['shop_id'] != sid}
            for nid, o in cur.items():
                if o['shop_id'] == sid:
                    alts = [x for x in opts[nid] if x['shop_id'] in others] or [x for x in opts[nid] if x['shop_id'] != sid]
                    if not alts: ok = False; break
                    trial[nid] = alts[0]
            if ok:
                c = _cost(trial, needs_q, lam, mu, user_c, nu)
                if c < best - 1: cur, best, improved = trial, c, True
        if not improved: break
    return cur

def _greedy_cover(opts, needs_q):
    left = set(opts); chosen = []
    while left:
        by = {}
        for nid in left:
            for o in opts[nid]:
                d = by.setdefault(o['shop_id'], {})
                if nid not in d or _eff(o) < _eff(d[nid]): d[nid] = o
        sid = max(by, key=lambda s: (len(by[s]), -sum(_eff(o) * needs_q[n] for n, o in by[s].items())))
        chosen.append(sid); left -= set(by[sid])
    assign = {}
    for nid in opts:   # cheapest option among chosen shops
        assign[nid] = min((o for o in opts[nid] if o['shop_id'] in chosen), key=_eff)
    return assign

def _hub_of(shops):
    pts = [s for s in shops if s.get('lat') is not None]
    if not pts: return None
    hubs = {}
    for g in BZ.data()['groups']:
        for h in g['hubs']:
            hubs.setdefault(h['display_name'], (h['center']['lat'], h['center']['lon']))
    best = None
    for name, c in hubs.items():
        n_in = sum(T.haversine(c[0], c[1], s['lat'], s['lon']) <= 1.2 for s in pts)
        if n_in and (not best or n_in > best[1]): best = (name, n_in)
    if best and best[1] == len(pts): return {'name': best[0], 'all_shops_in_hub': True}
    if best and best[1] >= len(pts) / 2: return {'name': best[0], 'all_shops_in_hub': False}
    return None

def _plan_out(key, name, assign, needs, not_found):
    nmap = {n['id']: n for n in needs}
    rows, shops = [], {}
    for nid, o in assign.items():
        n = nmap[nid]
        rows.append({'need_id': nid, 'item': n['item'], 'qty': n['qty'], 'unit': n['unit'], 'priority': n['priority'],
                     'product_id': o['product_id'], 'title': o['title'], 'image': o['image'], 'offer_id': o['offer_id'],
                     'shop_id': o['shop_id'], 'shop_name': o['shop_name'], 'shop_area': o['area'],
                     'price_toman': o['price_toman'], 'line_total_toman': o['price_toman'] * n['qty'],
                     'stale': o['stale'], 'date_fa': o['date_fa'], 'age_days': o['age_days'], 'badge': 'قدیمی' if o['stale'] else 'به‌روز',
                     'system': o.get('sys'), 'incompatible': bool(o.get('incompatible')), 'unverified': bool(o.get('unverified')),
                     'compat_badge': 'ناسازگار احتمالی' if o.get('incompatible') else ('سیستم نامشخص' if o.get('unverified') else None)})
        s = shops.setdefault(o['shop_id'], {'shop_id': o['shop_id'], 'name': o['shop_name'], 'area': o['area'], 'lat': o['lat'], 'lon': o['lon'],
                                            'map_url': f"https://www.openstreetmap.org/?mlat={o['lat']}&mlon={o['lon']}#map=17/{o['lat']}/{o['lon']}" if o['lat'] is not None else None,
                                            'n_items': 0})
        s['n_items'] += 1
    order = [n['id'] for n in needs]
    rows.sort(key=lambda r: order.index(r['need_id']))
    sl = list(shops.values())
    return {'key': key, 'name': name, 'n_incompatible': sum(r['incompatible'] for r in rows), 'n_unverified': sum(r['unverified'] for r in rows), 'total_toman': sum(r['line_total_toman'] for r in rows), 'n_unknown': len(not_found),
            'total_is_partial': bool(not_found), 'n_items_found': len(rows), 'n_shops': len(sl), 'n_stale': sum(r['stale'] for r in rows),
            'spread_km': round(_spread(sl), 1), 'hub': _hub_of(sl), 'shops': sl, 'rows': rows}

def _three(opts, nq, user_c):
    """-> [(key, assignment, objective)] for cheapest / one_stop / balanced"""
    cheap = {nid: min(o, key=_eff) for nid, o in opts.items()}
    base = sum(_eff(o) * nq[nid] for nid, o in cheap.items())
    fewest = _local_search(_greedy_cover(opts, nq), opts, nq, lam=base * 10, mu=0)       # shop count dominates
    lam, mu = max(0.04 * base, 300_000), 0.01 * base
    nu = 0.01 * base if user_c else 0
    bal = min((_local_search(cheap, opts, nq, lam, mu, user_c, nu), _local_search(fewest, opts, nq, lam, mu, user_c, nu)),
              key=lambda a: _cost(a, nq, lam, mu, user_c, nu))
    tot = lambda a: sum(_eff(o) * nq[n] for n, o in a.items())
    return [('cheapest', cheap, tot(cheap)),
            ('one_stop', fewest, len({o['shop_id'] for o in fewest.values()}) * 1e12 + tot(fewest)),
            ('balanced', bal, _cost(bal, nq, lam, mu, user_c, nu))]

def search(needs, area=None):
    t0 = time.time()
    needs = [n for n in (needs or []) if n.get('enabled', True)][:16]
    for i, n in enumerate(needs):
        n.setdefault('id', f'n{i+1}'); n['qty'] = max(1, min(int(n.get('qty') or 1), 500)); n.setdefault('unit', 'عدد'); n.setdefault('priority', 'essential')
        n.setdefault('item', n.get('query')); n.setdefault('query', n.get('item')); n.setdefault('must', [])
    cands = {n['id']: candidates(n) for n in needs}
    opts = {nid: c['options'] for nid, c in cands.items() if c['options']}
    not_found = [{'need_id': n['id'], 'item': n['item'], 'alternative': cands[n['id']]['alternative']} for n in needs if not cands[n['id']]['options']]
    user_c = None
    if area:
        ra = T.resolve_area(area)
        user_c = ra.get('centre')
    plans = []
    if opts:
        nq = {n['id']: n['qty'] for n in needs}
        in_play = {o['sys'] for os_ in opts.values() for o in os_ if o.get('sys')}
        fixed = {(n.get('attrs') or {}).get('system') for n in needs} - {None}
        systems = sorted(fixed) if len(fixed) == 1 else (['ip', 'analog'] if in_play >= {'ip'} or in_play >= {'analog'} else [None])
        if systems != [None] and not in_play: systems = [None]
        best = {}
        core = {n['id']: _is_core(n) for n in needs}
        for S in systems:
            if S is None:
                o_s = opts
            else:     # one system per plan: keep compatible/unknown options; if a need has none, keep the rest but badge them
                o_s = {}
                for nid, os_ in opts.items():
                    if core.get(nid):      # cameras / recorders define the system: verified same-system first, then unknown (badged), then other (badged)
                        ok = [o for o in os_ if o.get('sys') == S] or [dict(o, unverified=True) for o in os_ if o.get('sys') is None]
                    else:
                        ok = [o for o in os_ if o.get('sys') in (None, S)]
                    o_s[nid] = ok if ok else [dict(o, incompatible=True) for o in os_]
            for key, a, obj in _three(o_s, nq, user_c):
                obj += sum(bool(o.get('incompatible')) and core.get(n_) for n_, o in a.items()) * 1e13   # cameras+recorder of one system always win
                best.setdefault(key, []).append((S, a, obj, sum(_eff(o) * nq[n_] for n_, o in a.items())))
        for key, lst in best.items():     # a system whose basket is >2x the other's is never picked just to save one shop
            mt = min(x[3] for x in lst)
            best[key] = min(lst, key=lambda x: x[2] + (1e14 if x[3] > 2 * mt else 0))
        seen = {}
        for key, name in (('cheapest', 'ارزان‌ترین کل سبد'), ('one_stop', 'کمترین فروشگاه / همه از یک‌جا'), ('balanced', 'متعادل')):
            S, a = best[key][0], best[key][1]
            sig = tuple(sorted((k, v['offer_id']) for k, v in a.items()))
            if sig in seen:
                seen[sig]['also'] = seen[sig].get('also', []) + [name]; continue
            p = _plan_out(key, name, a, needs, not_found); p['system'] = S
            p['system_label'] = {'ip': 'سیستم تحت شبکه (IP)', 'analog': 'سیستم آنالوگ (AHD/TVI/CVI)'}.get(S)
            seen[sig] = p; plans.append(p)
    return {'needs': needs, 'candidates': {nid: {'products': c['products'], 'n_options': len(c['options']), 'queries_tried': c['queries_tried'], 'n_low_outliers_dropped': c['n_low_outliers_dropped']} for nid, c in cands.items()},
            'plans': plans, 'not_found': not_found, 'area': area, 'area_centre': user_c,
            'rules': {'stale_days': D.STALE_DAYS, 'stale_penalty': '+15% in optimisation', 'suspicious': 'excluded (<40% of median)',
                      'balanced_weights': 'extra shop ≈ max(4% basket, 300k toman); +1% basket per km spread'},
            'llm_calls': 0, 'elapsed_s': round(time.time() - t0, 2)}

_SUM_SYS = ("You write 1-3 short, warm, natural Persian sentences summarising shopping plans for the user (like a friend who knows the bazaar). "
            "Use ONLY the given facts; prices are already rounded strings — copy them as-is or omit. Mention the trade-off between plans and, if given, the hub name. "
            "No disclaimers, no lists, no English. Reply JSON {\"text\":\"...\"}")

def summary(goal, res, client_fn, cost_fn, add_spend, fmt_money):
    facts = {'goal': goal, 'plans': [{'name': p['name'] + (' (= ' + '، '.join(p['also']) + ')' if p.get('also') else ''), 'total': fmt_money(p['total_toman']) if p['total_toman'] else None,
                                      'shops': p['n_shops'], 'hub': (p.get('hub') or {}).get('name'), 'items_found': p['n_items_found']} for p in res['plans']],
             'not_found_items': [x['item'] for x in res['not_found']]}
    j, usage = _llm_json(client_fn, cost_fn, add_spend, _SUM_SYS, json.dumps(facts, ensure_ascii=False), 160)
    return str(j.get('text') or '').strip()[:400], usage
