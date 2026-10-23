"""Torob shopping assistant — JEV (JSON-Extract-Validate) decision model.
Pipeline per turn: prefilter (no LLM) -> 1 JEV call (strict JSON params) -> SQL fetch (no LLM) -> optional 1 check call -> deterministic Persian text.
Reuses agent_v3 for: geocode_area, km/jalali/median SQL helpers, read-only connection, hydration (the only source of prices/addresses),
log checks (price mentions, Latin runs) and as the FALLBACK engine (intent=unsure, 0 results after widening, JEV LLM error/invalid JSON).
API: run_agent_jev(messages_or_question, mission=None, enable_check=True, user_lat=None, user_lon=None)
     -> {text, blocks, mission, usage, tool_trace, hydration_log, elapsed_s, history_entry, engine, jev}"""
import json, math, os, re, statistics, time
from datetime import datetime
from build_eval_db import norm
import agent_v3 as A
import tools as T
import recall as R
from agent import sanitize_answer

MODEL = A.MODEL
JEV_TIMEOUT_S = 12.0
CHECK_TIMEOUT_S = 8.0
JEV_MAX_TOKENS = 700
CHECK_MAX_TOKENS = 450
N_CANDIDATES = 30
STALE_DAYS = 30
SUSPICIOUS_RATIO = 0.4
DEFAULT_RADIUS_KM = 3.0
RO = A.RO
LOG = []                    # process-wide event log (fallbacks, dropped ids) for the runner
FORCE = {'intent': None, 'jev_error': False}   # test hooks: force intent=unsure / induce an LLM error

CORE_CATS = ['گوشی موبایل', 'لپ تاپ و نوت بوک', 'هدفون، هدست و هندزفری', 'اسپیکر و سیستم صوتی', 'ساعت هوشمند', 'تبلت', 'کنسول بازی',
             'مانیتور', 'تلویزیون', 'دوربین عکاسی', 'ماوس', 'کیبورد', 'پاور بانک', 'مچ بند هوشمند', 'هارد اکسترنال', 'عطر و ادکلن', 'قهوه ساز', 'جارو برقی']
INTENTS = ('search', 'compare', 'sellers', 'store', 'clarify', 'chitchat', 'unsure')
SORTS = ('price', 'distance', 'offers', 'fresh')
DEFAULT_EXCLUDES = ['طرح', 'کپی', 'استوک', 'کارکرده', 'های کپی']
VARIANT_WORDS = T.VARIANT_WORDS

_CARD = {r[0]: r for r in RO.execute('SELECT category_name,n_products,n_priced,n_offers,top_brands,p10,p90,sample_titles,keywords FROM category_card')}
_CAT_BY_NORM = {norm(c): c for c in _CARD}
_SHOPS = {r[0]: r for r in RO.execute('SELECT shop_id,name,lat,lon,address_norm FROM shops')}


# ------------------------------------------------------------------ small utils
def _fa(x):
    return A._fa_digits(x)

def fmt_price(v):
    return _fa(f'{int(v):,}'.replace(',', '٬')) if v is not None else '—'

def fmt_km(v):
    return _fa(f'{v:.1f}'.replace('.', '٫'))

def _mill(v):
    if v is None:
        return '?'
    return f'{v / 1e6:.1f}M' if v < 1e8 else f'{v / 1e6:.0f}M'

def _words(t):
    t = re.sub(r'(\d)([a-z\u0600-\u06ff])', r'\1 \2', t or '')
    return re.findall(r'[\w\-./]+', t)

def _alts(term):
    """one must_term ('آیفون|iphone') -> normalised alternatives incl. the existing synonym tables"""
    out = []
    for a in str(term).split('|'):
        a = norm(a).strip()
        if not a:
            continue
        out.append(a)
        out += T.SYN.get(a, [])
        for members, targets in R.ALIAS_GROUPS:
            if a in members:
                out += targets
    seen = []
    for a in out:
        if a not in seen:
            seen.append(a)
    return seen

def _hit(alts, words, text):
    for a in alts:
        if ' ' in a:
            if a in text:
                return True
        elif a.isdigit() or len(a) <= 2:
            if a in words:
                return True
        elif any(w.startswith(a) for w in words) or (len(a) > 3 and a in text):
            return True
    return False

def _fts_group(alts):
    parts = []
    for a in alts:
        a = re.sub(r'["*():^{}+\-]', ' ', a).strip()
        if not a:
            continue
        parts.append(f'"{a}"' if (' ' in a or a.isdigit() or len(a) <= 2) else f'"{a}"*')
    return '(' + ' OR '.join(parts) + ')' if parts else None

def _now():
    now = datetime.now(A.TEHRAN)
    return now, ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'][now.weekday()]


# ------------------------------------------------------------------ 1. PRE-FILTER (no LLM)
_PLACE_WORDS = set()
for _k, (_lab, _v) in A.GEO.items():
    _PLACE_WORDS |= set(norm(_lab).split())
JEV_STOP = set(norm(w) for w in """خوب خوبی بهترین برای نزدیک نزدیکی نزدیکه حوالی میدان خیابان پاساژ مجتمع کجا کجاها ارزون ارزونتر ارزون‌تر ارزان ارزانتر ارزون‌ترش ارزونترش
میدن میده دارم داری نمیدونم نمی‌دونم چی چیه بخرم بگیرم میلیون میلیونی م تومن تومان تا مشکی سفید آبی قرمز طلایی رنگ غرب شرق شمال جنوب مرکز تهران الان کدوم کدام
بازن باز فروشگاه فروشگاه‌ها فروشگاهها مغازه قسطی قسط اقساطی ترجیحا ترجیحاً پرداخت حضوری داشته باشن باشه پیدا میشه می‌شه قیمتش قیمت چنده چند من هستم اینجا
این نه جای یه نزدیکتر نزدیک‌تر همین اون دیگه ممنون سلام لطفا یک ای ام تر ترین ها های رو را میدن کجاست میخوام می‌خوام فروشی انقلابم""".split())
_PREF_SKIP = {'گوشی', 'موبایل'}

def _clean_query(text):
    toks = []
    for w in re.sub(r'[؟?!،,.:;«»()\[\]]', ' ', norm(text or '')).split():
        if w in JEV_STOP or (w in _PLACE_WORDS and w not in _PREF_SKIP):
            continue
        toks.append(w)
    return ' '.join(toks)

def prefilter(text, k=N_CANDIDATES, n_core=8):
    """FTS5 + synonyms/fuzzy variants (recall.variants) + norm_fa over product titles AND category cards -> top-k category names.
    Product hits are weighted by popularity (n_shops); the main consumer categories always keep n_core slots for broad questions."""
    score = {}
    q = _clean_query(text)
    vs = R.variants(q)[:5] if q.strip() else []
    for vi, v in enumerate(vs):
        toks = [t for t in T._tokens(v) if t not in JEV_STOP]
        groups = [g for g in (T._fts_group(t) for t in toks) if g]
        if not groups:
            continue
        for mode, w in (('AND', 2.0), ('OR', 1.0)):
            if mode == 'AND' and len(groups) < 2:
                continue
            try:
                rows = RO.execute('SELECT f.category_name, COALESCE(s.n_shops,0) FROM products_fts f LEFT JOIN product_stats s ON s.product_id=f.product_id '
                                  'WHERE products_fts MATCH ? ORDER BY rank LIMIT 300', [f' {mode} '.join(groups)]).fetchall()
            except Exception:
                rows = []
            ww = w * (1.0 if vi == 0 else 0.8)
            for rank, (cn, ns) in enumerate(rows):
                c = _CAT_BY_NORM.get(cn)
                if c:
                    score[c] = score.get(c, 0) + ww * (1 + math.log1p(ns)) / (10 + rank)
        try:   # category-name / keyword side
            for col, w in (('name_norm', 3.0), ('keywords', 1.0)):
                rows = RO.execute('SELECT category_name FROM category_card_fts WHERE category_card_fts MATCH ? ORDER BY rank LIMIT 30',
                                  ['{%s} : (%s)' % (col, ' OR '.join(groups))]).fetchall()
                for rank, (c,) in enumerate(rows):
                    score[c] = score.get(c, 0) + w / (3 + rank) * (1.0 if vi == 0 else 0.8)
        except Exception:
            pass
    ranked = sorted(score, key=lambda c: -score[c])
    core = [c for c in CORE_CATS if c in _CARD]
    top = ranked[:k - n_core]
    for c in core + ranked[k - n_core:]:
        if len(top) >= k:
            break
        if c not in top:
            top.append(c)
    return top

def card_line(c):
    r = _CARD[c]
    brands = '، '.join(json.loads(r[4] or '[]'))
    samples = ' ; '.join(json.loads(r[7] or '[]'))
    return f'- {c} | {r[1]} products, {r[3]} offers | brands: {brands or "-"} | p10–p90: {_mill(r[5])}–{_mill(r[6])} | e.g. {samples}'


# ------------------------------------------------------------------ 2. JEV call
JEV_SYSTEM = """You are the decision model of «دستیار خرید حضوری ترب» (in-person shopping in Tehran stores). You do NOT write the answer and you do NOT see products/prices: you turn the conversation into search parameters as ONE strict JSON object; the server runs SQL and writes the answer from database rows.
Now: {NOW} Tehran (day code {DAY}).

Data truths: prices are historical snapshots with a last-change date (not live); an offer does NOT mean in stock; shop phone numbers and most shop names are fake/test data; ~85% of shops are central (Ferdowsi/Baharestan/Jomhouri/Charsu/Alaedin), other areas are thin; there is NO stock, colour or review data (a colour wish is never a filter — mention it in reason_fa as «رنگ در داده‌ها ثبت نشده»); accessories (cases, glass, parts, chargers) and «طرح»/copy knock-offs often share a device's name; many near-duplicate listings (storage variants).

Candidate categories (pre-filtered from the catalogue; name | size | top brands | p10–p90 price in toman | sample titles):
{CARDS}

Current mission (state from earlier turns; aliases P#/S# = products/shops shown earlier): {MISSION}

Output EXACTLY these keys:
{{"intent": "search|compare|sellers|store|clarify|chitchat|unsure",
 "categories": [1-3 names copied EXACTLY from the candidate list: the category of the device itself, not its accessories unless asked],
 "brands": [brand names as in the cards, e.g. "اپل","سامسونگ"; [] if none],
 "must_terms": [distinguishing words that must appear in the product title; give spelling alternatives with |, e.g. ["آیفون|iphone","17"], ["a56"], ["note|نوت","14"], ["s24|اس 24","ultra|اولترا"]; model numbers as separate terms; [] for a broad browse],
 "exclude_terms": [title words to exclude, e.g. ["pro|پرو","max|مکس","air"] when the base model is asked, or ["قاب","گلس"]],
 "price_min": int toman or null, "price_max": int toman or null,
 "area": "Tehran place as the shopper said it (e.g. «میدان فردوسی», «جمهوری», «غرب تهران», «پاساژ علاءالدین») or null",
 "sort": "price|distance|offers|fresh",
 "filters": {{"installment": bool, "open_now": bool, "warranty": bool}},
 "clarify_question": "Persian question or null", "chips": ["2-4 short Persian follow-up suggestions"],
 "mission_update": {{"goal": "Persian", "budget_toman": int|null, "area": str|null, "selected_product": "P# or null", "exclude_shops": ["S#", ...]}},
 "reason_fa": "1-2 short Persian sentences to the shopper saying what you are showing and why (no prices; only the shopper's own budget numbers)"}}

How to decide:
- search = find products (also "best X up to budget", "cheapest X": sort=price for cheapest, offers (popularity) for "good/best X"); compare = 2+ named products; sellers = where to buy one specific product (sort price or distance); store = questions about SHOPS (installments, open now, shops in a mall/area) — set categories to what the shops sell; clarify = ONLY if the request is truly impossible to act on (still fill categories/price so options can be shown); chitchat = greetings/off-topic; unsure = you cannot map the request to the catalogue at all.
- "N میلیون/م" = N*1,000,000 toman. "تا X" -> price_max=X; for "a good X up to X" also set price_min≈X/2.
- An area the shopper names is a real seller filter (put it in area). Keep the mission's area/budget/product when the follow-up still refers to them.
- Follow-ups refer to what was shown: «ارزون‌ترش» after a product = same category, price_max just below that product's price, similar brands/tier, sort=price, must_terms [] (the server also re-shows the same item's cheapest offer); «این فروشگاه نه، نزدیک‌تر» = same product (same must_terms), sort=distance, mission_update.exclude_shops=[the S# shown]; «رمش ۱۶ باشه» = add a must_term.
- If the exact item does not exist (no candidate/sample suggests it, e.g. an unreleased model), say so in reason_fa and set the parameters for the closest real item (e.g. PS5 instead of PS6) — do not set intent=unsure for that.
- Misspellings/colloquial forms (سامسونک, اپل۱۷, الترا) -> correct catalogue terms.
- reason_fa, clarify_question and chips must be entirely Persian (model names like PS5/A56 may be Latin)."""

def _jev_messages(hist, mission, cards):
    now, day = _now()
    m = {k: v for k, v in (mission or {}).items() if k != '_aliases'}
    sysm = JEV_SYSTEM.format(NOW=now.strftime('%Y-%m-%d %H:%M'), DAY=day, CARDS='\n'.join(cards), MISSION=json.dumps(m, ensure_ascii=False) if m else '{}')
    msgs = [{'role': 'system', 'content': sysm}]
    for h in hist[-8:]:
        msgs.append({'role': h['role'], 'content': str(h.get('content') or '')[:1800]})
    return msgs

def _llm(msgs, max_tokens, timeout, usage, trace, label):
    if FORCE.get('jev_error') and label == 'jev':
        raise RuntimeError('induced JEV error (test hook)')
    if FORCE.get('replay_raw') and label == 'jev':   # replay a RECORDED JEV output (no API call, $0) — used to re-test after a parser fix
        trace.append({'tool': 'llm:jev(replayed)', 'ms': 0, 'cost': 0.0})
        usage['api_calls_replayed'] = usage.get('api_calls_replayed', 0) + 1
        return FORCE['replay_raw']
    t = time.time()
    r = A.client().chat.completions.create(model=MODEL, messages=msgs, max_completion_tokens=max_tokens, reasoning_effort='none',
                                           response_format={'type': 'json_object'}, timeout=timeout)
    u = r.usage
    c = A._usage_cost(u)
    usage['prompt_tokens'] += u.prompt_tokens; usage['completion_tokens'] += u.completion_tokens
    usage['cost'] += c; usage['api_calls'] += 1; A.COST['llm'] += c
    trace.append({'tool': 'llm:' + label, 'ms': int((time.time() - t) * 1000), 'prompt_tokens': u.prompt_tokens, 'completion_tokens': u.completion_tokens, 'cost': round(c, 6)})
    return r.choices[0].message.content or ''

def _int_or_none(v):
    if v is None or v == '' or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return int(v) if v > 0 else None
    s = norm(str(v)).replace(',', '')
    m = re.search(r'\d+(\.\d+)?', s)
    if not m:
        return None
    x = float(m.group(0))
    if 'میلیون' in s or s.endswith('m'):
        x *= 1e6
    return int(x) if x > 0 else None

def _str_list(v, n=8):
    """list of strings; the model sometimes nests term lists: [["آیفون|iphone","17"]] -> 2 terms, [["a56","a 56"]] (no '|') -> 1 term 'a56|a 56'"""
    if v is None:
        return []
    if isinstance(v, str):
        v = [v]
    if not isinstance(v, list):
        raise ValueError('not a list')
    out = []
    for x in v:
        if isinstance(x, list):
            xs = [str(y).strip() for y in x if str(y).strip() and not isinstance(y, (list, dict))]
            if len(xs) > 1 and not any('|' in y for y in xs):
                out.append('|'.join(xs))
            else:
                out += xs
        elif isinstance(x, dict):
            raise ValueError('object inside a string list')
        elif str(x).strip():
            out.append(str(x).strip())
    return out[:n]

def validate(obj, candidates):
    """strict schema check with light coercion -> (params, error|None)"""
    if not isinstance(obj, dict):
        return None, 'output is not a JSON object'
    try:
        intent = str(obj.get('intent', '')).strip().lower()
        if intent not in INTENTS:
            return None, f'intent must be one of {INTENTS}, got {intent!r}'
        cats_in = _str_list(obj.get('categories'), 5)
        cats, unknown = [], []
        for c in cats_in:
            cc = c if c in _CARD else _CAT_BY_NORM.get(norm(c))
            (cats.append(cc) if cc else unknown.append(c))
        if cats_in and not cats and intent in ('search', 'compare', 'sellers'):
            return None, f'categories {unknown} are not real category names; copy them exactly from the candidate list'
        sort = str(obj.get('sort') or '').strip().lower() or None
        if sort not in SORTS:
            sort = 'price' if intent == 'sellers' else 'offers'
        f = obj.get('filters') or {}
        if not isinstance(f, dict):
            return None, 'filters must be an object'
        mu = obj.get('mission_update') or {}
        if not isinstance(mu, dict):
            return None, 'mission_update must be an object'
        p = {'intent': intent, 'categories': cats[:3], 'unknown_categories': unknown, 'brands': _str_list(obj.get('brands'), 6),
             'must_terms': _str_list(obj.get('must_terms'), 6), 'exclude_terms': _str_list(obj.get('exclude_terms'), 10),
             'price_min': _int_or_none(obj.get('price_min')), 'price_max': _int_or_none(obj.get('price_max')),
             'area': (str(obj.get('area')).strip() if obj.get('area') not in (None, '', 'null') else None), 'sort': sort,
             'filters': {k: bool(f.get(k)) for k in ('installment', 'open_now', 'warranty')},
             'clarify_question': (str(obj['clarify_question']).strip() if obj.get('clarify_question') not in (None, '', 'null') else None),
             'chips': _str_list(obj.get('chips'), 4), 'mission_update': mu, 'reason_fa': str(obj.get('reason_fa') or '').strip()}
    except ValueError as e:
        return None, f'type error: {e}'
    if p['price_min'] and p['price_max'] and p['price_min'] > p['price_max']:
        p['price_min'] = None
    return p, None

def jev_call(hist, mission, cands, usage, trace):
    cards = [card_line(c) for c in cands]
    msgs = _jev_messages(hist, mission, cards)
    raw = _llm(msgs, JEV_MAX_TOKENS, JEV_TIMEOUT_S, usage, trace, 'jev')
    try:
        obj = json.loads(raw)
    except Exception:
        obj = A._parse_final(raw)
    p, err = validate(obj, cands)
    if err is None:
        return p, raw, None
    msgs += [{'role': 'assistant', 'content': raw[:2000]},
             {'role': 'user', 'content': f'Your JSON was invalid: {err}. Return the corrected JSON object only, with exactly the required keys.'}]
    raw2 = _llm(msgs, JEV_MAX_TOKENS, JEV_TIMEOUT_S, usage, trace, 'jev_repair')
    try:
        obj2 = json.loads(raw2)
    except Exception:
        obj2 = A._parse_final(raw2)
    p2, err2 = validate(obj2, cands)
    if err2 is None:
        p2['_repaired'] = err
        return p2, raw2, None
    return None, raw2, f'invalid JSON after 1 repair: {err2} (first: {err})'


# ------------------------------------------------------------------ 3. SQL FETCH (no LLM)
def _area(p, mission, user_lat, user_lon):
    name = p.get('area')
    if name:
        g = A.tool_geocode_area(name)
        if g.get('found'):
            a = {'name': name, 'lat': g['lat'], 'lon': g['lon'], 'radius': g.get('suggested_radius_km') or DEFAULT_RADIUS_KM}
            if g.get('is_region'):
                a['region'] = next((r for r in A._REGION_PY if r in g['name']), None)
            if 'median location' in (g.get('source') or ''):   # a mall/passage: sellers whose address names it
                a['addr'] = norm(re.sub(r'^(پاساژ|مجتمع|مرکز خرید)\s*', '', name)).replace('آ', 'ا').replace('ء', '')
            return a, g
        return {'name': name, 'unknown': True}, g
    if user_lat is not None:
        return {'name': 'موقعیت شما', 'lat': user_lat, 'lon': user_lon, 'radius': DEFAULT_RADIUS_KM}, None
    return None, None

def _in_area(a, sid):
    s = _SHOPS.get(sid)
    if not a or a.get('unknown'):
        return True, None
    if not s or s[2] is None:
        return False, None
    km = T.haversine(a['lat'], a['lon'], s[2], s[3])
    if a.get('addr'):
        return a['addr'] in (s[4] or '').replace('آ', 'ا').replace('ء', ''), km
    if a.get('region'):
        return A._REGION_PY[a['region']](s[2], s[3]), km
    return km <= a['radius'], km

def _open_now_ids():
    now, day = _now()
    hh = now.strftime('%H:%M:%S')
    return {r[0] for r in RO.execute("SELECT shop_id FROM shop_hours WHERE day=? AND status='declared' AND start_time<=? AND end_time>?", (day, hh, hh))}

def _installment_ids():
    d = {}
    for sid, ch in RO.execute('SELECT shop_id, channel FROM shop_payment_options'):
        d[sid] = d.get(sid, False) or ch == 'in_person'
    return d

def _candidates(p, user_text, relax_cats=False):
    terms = [_alts(t) for t in p['must_terms']]
    terms = [t for t in terms if t]
    cats = [] if relax_cats else p['categories']
    ids = []
    if terms:
        groups = [g for g in (_fts_group(t) for t in terms) if g]
        for mode in ('AND', 'OR'):
            if mode == 'OR' and len(ids) >= 10:
                break
            try:
                ids += [r[0] for r in RO.execute('SELECT product_id FROM products_fts WHERE products_fts MATCH ? ORDER BY rank LIMIT 3000', [f' {mode} '.join(groups)])]
            except Exception:
                pass
        ids = list(dict.fromkeys(ids))
    elif cats:
        ids = [r[0] for r in RO.execute(f'SELECT product_id FROM products WHERE category_name IN ({",".join("?" * len(cats))})', cats)]
    elif p['brands']:
        ids = [r[0] for r in RO.execute(f'SELECT product_id FROM products WHERE brand_name IN ({",".join("?" * len(p["brands"]))})', p['brands'])]
    if not ids:
        return [], terms
    rows = []
    for i in range(0, len(ids), 900):
        ch = ids[i:i + 900]
        rows += RO.execute(f'''SELECT p.product_id,p.persian_title,p.title_norm,p.brand_name,p.category_name,p.model,COALESCE(s.n_shops,0),COALESCE(s.n_priced,0)
                               FROM products p LEFT JOIN product_stats s USING(product_id) WHERE p.product_id IN ({",".join("?" * len(ch))})''', ch).fetchall()
    uq = norm(user_text or '')
    excl = [_alts(t) for t in p['exclude_terms']] + [[w] for w in DEFAULT_EXCLUDES if w not in uq and not any(w in ' '.join(t) for t in terms)]
    brand_alts = set()
    for b in p['brands']:
        nb = norm(b); brand_alts.add(nb)
        for g in R.BRAND_ALIASES:
            if nb in g:
                brand_alts |= set(g)
    q_variants = {v for v, al in VARIANT_WORDS.items() if any(a in ' '.join(sum(terms, [])).split() for a in al)}
    out = []
    for pid, title, tn, br, cat, model, n_shops, n_priced in rows:
        if not n_priced:
            continue
        if cats and cat not in cats:
            continue
        tn = tn or ''
        text = f'{tn} {norm(br or "")}'
        words = _words(text)
        if brand_alts and not any(b in text for b in brand_alts if len(b) > 1):
            continue
        if any(_hit(e, words, text) for e in excl):
            continue
        cov = (sum(_hit(t, words, text) for t in terms) / len(terms)) if terms else 1.0
        extra_variant = sum(1 for v, al in VARIANT_WORDS.items() if v not in q_variants and any(a in words for a in al))
        acc = any(tn.startswith(w) for w in T.ACCESSORY_WORDS) or T._cat_acc(cat, ' '.join(tn.split()[:3]))
        if relax_cats and acc:      # outside the chosen categories, never fall back to cases/glass/parts
            continue
        out.append({'product_id': pid, 'title': title, 'brand': br, 'category': cat, 'model': model, 'n_shops': n_shops,
                    'cov': cov, 'extra_variant': extra_variant, 'acc': acc, 'tn': tn})
    if terms:
        full = [r for r in out if r['cov'] >= 0.999]
        out = full if full else [r for r in out if r['cov'] >= 0.5]
        for r in out:
            r['partial'] = not full
    out.sort(key=lambda r: (-r['cov'], r['acc'], r['extra_variant'], -r['n_shops']))
    return out[:400], terms

def _offers(pids):
    d = {}
    for i in range(0, len(pids), 900):
        ch = pids[i:i + 900]
        for r in RO.execute(f'''SELECT offer_id,product_id,shop_id,price_toman,last_price_changed_at,COALESCE(warranty_months,0) FROM offers
                                WHERE product_id IN ({",".join("?" * len(ch))}) AND price_toman IS NOT NULL''', ch):
            d.setdefault(r[1], []).append(r)
    return d

def fetch(p, mission, user_text, user_lat=None, user_lon=None):
    """products/offers/shops for the JEV params -> dict with ranked products (top 10) + sellers + notes; all values from the DB"""
    dbg = {'sql_notes': []}
    area, geo = _area(p, mission, user_lat, user_lon)
    dbg['area'] = area; dbg['geocode'] = geo
    excluded = set((mission or {}).get('excluded_shop_ids') or [])
    if p['intent'] == 'store':
        return fetch_shops(p, area, excluded, dbg)
    cands, terms = _candidates(p, user_text)
    relaxed = False
    if not cands and p['categories'] and terms:
        cands, terms = _candidates(p, user_text, relax_cats=True); relaxed = True
        dbg['sql_notes'].append('0 products inside the chosen categories -> category filter relaxed (must_terms kept)')
    dbg['n_candidates'] = len(cands)
    if not cands:
        return {'products': [], 'sellers': [], 'area': area, 'widened': False, 'relaxed': relaxed, 'dbg': dbg}
    offs = _offers([c['product_id'] for c in cands])
    lo, hi = p['price_min'] or 0, p['price_max'] or 1e13
    inst = _installment_ids() if p['filters']['installment'] else None
    opn = _open_now_ids() if p['filters']['open_now'] else None
    def ok_offer(o):
        if o[2] in excluded:
            return False
        if p['filters']['warranty'] and not o[5]:
            return False
        if inst is not None and o[2] not in inst:
            return False
        if opn is not None and o[2] not in opn:
            return False
        return True
    def build(widen):
        res = []
        for c in cands:
            allp = [o[3] for o in offs.get(c['product_id'], [])]
            if not allp:
                continue
            med = statistics.median(allp)
            rng = []
            for o in offs[c['product_id']]:
                if not ok_offer(o) or not (lo <= o[3] <= hi):
                    continue
                inside, km = _in_area(area, o[2]) if area else (True, None)
                if area and not area.get('unknown') and not inside and not widen:
                    continue
                rng.append((o, km))
            if not rng:
                continue
            real = [x for x in rng if not (len(allp) >= 3 and x[0][3] < SUSPICIOUS_RATIO * med)]
            if not real:      # only qualifies through a price far below its own median (data error / other item): skip it
                continue
            best_price = min(real, key=lambda x: x[0][3])
            nearest = min(rng, key=lambda x: (x[1] if x[1] is not None else 1e9, x[0][3]))
            mn_all = min(offs[c['product_id']], key=lambda o: o[3])
            last = max((o[4] or '') for o in offs[c['product_id']])
            dd = A._days_ago(best_price[0][4])
            res.append(dict(c, offers_in_scope=rng, best=best_price, nearest=nearest, min_price=int(mn_all[3]), median_price=int(med),
                            n_sellers=len({o[2] for o in offs[c['product_id']]}), last_change=last[:10], last_change_fa=A._jalali(last) if last else None,
                            suspicious=len(allp) >= 3 and mn_all[3] < SUSPICIOUS_RATIO * med, stale=dd is not None and dd > STALE_DAYS, best_days=dd,
                            scope_min=int(best_price[0][3])))
        return res
    res, widened = build(False), False
    if len(res) < 3 and p['price_min'] and not terms:   # «a good X up to budget»: a guessed lower bound must not empty a thin area
        lo = 0
        res2 = build(False)
        if len(res2) > len(res):
            res = res2
            dbg['sql_notes'].append('fewer than 3 items -> price_min relaxed')
    if not res and area and not area.get('unknown'):
        res, widened = build(True), True
        dbg['sql_notes'].append(f'no seller inside {area["name"]} -> widened to nearest sellers')
    full = [r['scope_min'] for r in res if r['cov'] >= 0.999]
    peer_med = statistics.median(full) if len(full) >= 3 else None
    for r in res:   # a 1-2 seller listing far below its peers' prices (n<3 offers, so the own-median rule cannot see it)
        r['suspicious_peer'] = bool(peer_med and r['scope_min'] < SUSPICIOUS_RATIO * peer_med and not r['suspicious'])
        if r['suspicious_peer']:
            r['peer_median'] = int(peer_med)
    s = p['sort']
    def key(r):
        k0 = (-r['cov'], r.get('acc', False), r['suspicious_peer'], r['extra_variant'])
        if s == 'price':   # a fresh offer ranks before a stale (>30 d) one; both stay visible
            return k0 + (bool(r['stale']), r['scope_min'])
        if s == 'distance':
            return k0 + (r['nearest'][1] if r['nearest'][1] is not None else 1e9, r['scope_min'])
        if s == 'fresh':
            return k0 + (-(datetime.fromisoformat(r['last_change']).timestamp() if r['last_change'] else 0),)
        return k0 + (-r['n_shops'],)
    if widened:
        res.sort(key=lambda r: (-r['cov'], r['suspicious_peer'], r['nearest'][1] if r['nearest'][1] is not None else 1e9))
    else:
        res.sort(key=key)
    # dedupe: same title always; in browse mode (no must_terms) also one card per model (variants merged) and round-robin over categories
    seen, out = set(), []
    for r in res:
        k = norm(r['title'])
        if not terms:
            k = (r['brand'] or '', norm(r['model'] or '') or norm(' '.join(r['tn'].split()[:4])))
        if k in seen:
            continue
        seen.add(k); out.append(r)
    if not terms and len(p['categories']) > 1:
        by = {c: [r for r in out if r['category'] == c] for c in p['categories']}
        rr = []
        while any(by.values()):
            for c in p['categories']:
                if by[c]:
                    rr.append(by[c].pop(0))
        out = rr
    ekm = None
    if excluded and s == 'distance' and area and area.get('lat'):
        kms = [T.haversine(area['lat'], area['lon'], _SHOPS[x][2], _SHOPS[x][3]) for x in excluded if x in _SHOPS and _SHOPS[x][2] is not None]
        ekm = min(kms) if kms else None
    return {'products': out[:10], 'area': area, 'widened': widened, 'relaxed': relaxed, 'dbg': dbg, 'excluded_km': ekm}

def fetch_shops(p, area, excluded, dbg):
    cats = p['categories']
    if cats:
        sids = {r[0] for r in RO.execute(f'SELECT DISTINCT shop_id FROM shop_categories WHERE category_name IN ({",".join("?" * len(cats))})', cats)}
    else:
        sids = set(_SHOPS)
    sids -= excluded
    inst = _installment_ids()
    if p['filters']['installment']:
        sids &= set(inst)
    if p['filters']['open_now']:
        sids &= _open_now_ids()
    rows, widened = [], False
    for widen in (False, True):
        rows = []
        for sid in sids:
            inside, km = _in_area(area, sid) if area else (True, None)
            if area and not area.get('unknown') and not inside and not widen:
                continue
            rows.append((sid, km))
        if rows or not area:
            break
        widened = True
        dbg['sql_notes'].append(f'no matching shop inside {area["name"]} -> nearest shops')
    n_off = {}
    if cats and rows:
        ids = [r[0] for r in rows]
        for i in range(0, len(ids), 900):
            ch = ids[i:i + 900]
            for sid, n in RO.execute(f'''SELECT o.shop_id, COUNT(*) FROM offers o JOIN products pr USING(product_id) WHERE o.shop_id IN ({",".join("?" * len(ch))})
                                         AND pr.category_name IN ({",".join("?" * len(cats))}) GROUP BY 1''', ch + cats):
                n_off[sid] = n
    rows.sort(key=lambda r: (not inst.get(r[0], False) if p['filters']['installment'] else 0, -(1 if n_off.get(r[0]) else 0),
                             r[1] if r[1] is not None and (widened or p['sort'] == 'distance') else 0, -n_off.get(r[0], 0)))
    shops = [{'shop_id': sid, 'km': km, 'n_offers_cat': n_off.get(sid, 0), 'in_person': inst.get(sid, False)} for sid, km in rows[:10]]
    return {'shops': shops, 'n_shops_total': len(rows), 'area': area, 'widened': widened, 'dbg': dbg, 'products': []}


# ------------------------------------------------------------------ 4. CHECK call (remove/reorder only)
CHECK_SYSTEM = """A shopper in Tehran asked for something; the server found these catalogue items (P# | title | category | lowest price toman).
Keep ONLY items that really are what the shopper asked for: drop accessories/parts (cases, glass, chargers, single earbuds), «طرح»/copy knock-offs, used/stock items unless asked, and wrong category/model (e.g. a Pro when the base model was asked).
You may only REMOVE and REORDER the given ids (best first); never add ids. For each kept item write one short Persian line why it fits (no prices).
Return JSON only: {"keep":[{"id":"P1","why":"..."}]}"""

def check_call(request, prods, usage, trace, plan=''):
    lines = [f'P{i + 1} | {r["title"]} | {r["category"]} | {r["scope_min"]}' for i, r in enumerate(prods)]
    raw = _llm([{'role': 'system', 'content': CHECK_SYSTEM}, {'role': 'user', 'content': f'Shopper: {request}\nAssistant plan (judge items against this; if it says the exact item is not in the data and the closest real alternative is shown, keep that alternative): {plan}\nItems:\n' + '\n'.join(lines)}],
               CHECK_MAX_TOKENS, CHECK_TIMEOUT_S, usage, trace, 'check')
    obj = json.loads(raw)
    keep, out = obj.get('keep') if isinstance(obj, dict) else None, []
    if not isinstance(keep, list):
        raise ValueError('check: no keep list')
    for k in keep:
        k = k if isinstance(k, dict) else {'id': k}
        m = re.fullmatch(r'P(\d+)', str(k.get('id', '')).strip())
        if not m or not (1 <= int(m.group(1)) <= len(prods)):
            continue           # an id that was not offered is ignored (never added)
        r = prods[int(m.group(1)) - 1]
        if any(x is r for x in out):
            continue
        out.append(dict(r, why=str(k.get('why') or '').strip()[:140]))
    return out, raw


# ------------------------------------------------------------------ 5. text + blocks (deterministic Persian, DB values only)
def _shop_name(sid):
    s = _SHOPS.get(sid)
    return s[1] if s else ''

def _clean_fa(s, allowed):
    s = sanitize_answer(s or '', allowed)
    return re.sub(r'\b(?:suspicious\w*|stale|offer_\w+|product_\w+|shop_\w+|min_price\w*)\b', '', s).strip()

def compose(p, data, mission, user_text):
    intent, prods, area = p['intent'], data.get('products') or [], data.get('area')
    allowed = ' | '.join([r['title'] for r in prods] + [_shop_name(s['shop_id']) for s in data.get('shops', [])])
    lines, blocks, aliases = [], [], {}
    reason = _clean_fa(p['reason_fa'], allowed)
    if reason:
        lines.append(reason)
    if area and area.get('unknown'):
        lines.append(f'محدودهٔ «{area["name"]}» را در جدول مکان‌ها پیدا نکردم؛ نتیجه‌ها از کل تهران است.')
    if data.get('widened'):
        lines.append(f'در محدودهٔ «{area["name"]}» فروشنده‌ای با این شرایط ثبت نشده؛ نزدیک‌ترین گزینه‌ها را آورده‌ام (فاصله کنار هر مورد).')
    if prods and prods[0].get('partial'):
        lines.append('مورد دقیقاً مطابق درخواست در داده‌ها پیدا نشد؛ نزدیک‌ترین موارد واقعی:')
    if data.get('excluded_km') is not None and p['sort'] == 'distance' and prods:   # compared with what is actually shown (after the check call)
        near = min((r['nearest'][1] for r in prods[:5] if r['nearest'][1] is not None), default=None)
        if near is not None and near >= data['excluded_km'] - 0.05:
            lines.append(f'فروشگاه نزدیک‌تری از فروشگاه قبلی (حدود {fmt_km(data["excluded_km"])} کیلومتر) برای این کالا ثبت نشده؛ این‌ها نزدیک‌ترین گزینه‌های بعدی‌اند:')
    if data.get('same_item'):
        si = data['same_item']
        lines.append(f'ارزان‌ترین قیمت ثبت‌شدهٔ همان «{si["title"]}» {fmt_price(si["price"])} تومان ({si["date_fa"]}) است؛ گزینه‌های ارزان‌تر:')
    if intent == 'store':
        shops = data.get('shops') or []
        if shops:
            lines.append(f'{_fa(data["n_shops_total"])} فروشگاه با این شرایط پیدا شد؛ چند مورد اول:')
        items = []
        for i, s in enumerate(shops[:8]):
            sh = A._shop(s['shop_id'])
            if not sh:
                continue
            aliases[f'S{i + 1}'] = s['shop_id']
            extra = []
            if sh.get('hours_today'):
                extra.append(f'ساعت امروز {_fa(sh["hours_today"])}')
            if p['filters']['installment'] and sh.get('installment'):
                extra.append('اقساط: ' + '، '.join(sh['installment'][:3]))
            if s['km'] is not None and area and not area.get('region'):
                extra.append(f'{fmt_km(s["km"])} کیلومتر')
            if i < 5:
                lines.append(f'{_fa(i + 1)}. {sh["name"]} — {(sh["address"] or "")[:70]}' + (f' ({"؛ ".join(extra)})' if extra else ''))
            items.append({'shop_id': s['shop_id'], 'note': '؛ '.join(extra)})
        if items:
            blocks.append({'type': 'sellers', 'items': items})
            blocks.append({'type': 'map', 'shop_ids': [x['shop_id'] for x in items], 'center': [area['lat'], area['lon']] if area and area.get('lat') else None})
        if p['filters']['open_now']:
            now, _ = _now()
            lines.append(f'«باز بودن» بر اساس ساعت کاری اعلام‌شدهٔ امروز و ساعت {_fa(now.strftime("%H:%M"))} است؛ پیش از رفتن تأیید کنید.')
        lines.append('نام فروشگاه‌ها و شماره‌های تماس در این داده آزمایشی‌اند.')
    else:
        show = prods[:5] if intent != 'sellers' else prods[:3]
        sellers = []
        for i, r in enumerate(show):
            aliases[f'P{i + 1}'] = r['product_id']
            o, km = r['best'] if p['sort'] != 'distance' else r['nearest']
            date_fa = A._jalali(o[4]) if o[4] else 'تاریخ نامشخص'
            t = f'{_fa(i + 1)}. {r["title"]}: {fmt_price(o[3])} تومان ({date_fa}) در «{_shop_name(o[2])}»'
            if km is not None and area and not area.get('region'):
                t += f'، {fmt_km(km)} کیلومتر از {area["name"]}'
            elif area and area.get('region') and not data.get('widened'):
                t += f' ({area["name"]})'
            t += f'؛ {_fa(r["n_sellers"])} فروشنده'
            if r['min_price'] < o[3] and not area and not (p['price_min'] or p['price_max']):
                t += f'، کمترین قیمت کل {fmt_price(r["min_price"])}'
            notes = []
            dd = A._days_ago(o[4])
            if dd is not None and dd > STALE_DAYS:
                notes.append(f'قیمت مربوط به حدود {_fa(int(dd))} روز پیش است و شاید به‌روز نباشد')
            if r['suspicious']:
                notes.append(f'کمترین قیمت ثبت‌شده ({fmt_price(r["min_price"])}) خیلی کمتر از میانه (حدود {fmt_price(r["median_price"])}) است؛ شاید خطا یا کالای دیگر باشد')
            if r.get('suspicious_peer'):
                notes.append(f'خیلی ارزان‌تر از موارد مشابه (میانه حدود {fmt_price(r["peer_median"])}) است؛ شاید خطا، کالای متفاوت یا کپی باشد')
            if notes:
                t += ' (' + '؛ '.join(notes) + ')'
            if r.get('why'):
                t += ' — ' + _clean_fa(r['why'], allowed)
            lines.append(t)
            sellers.append({'offer_id': o[0], 'note': date_fa})
            if intent == 'sellers' and i == 0:   # where-to-buy: more offers of the top product
                more = sorted(r['offers_in_scope'], key=lambda x: (x[0][3] if p['sort'] != 'distance' else (x[1] or 1e9)))
                for o2, km2 in more:
                    if o2[0] != o[0] and len(sellers) < 4 and o2[3] >= SUSPICIOUS_RATIO * r['median_price']:
                        sellers.append({'offer_id': o2[0], 'note': A._jalali(o2[4]) if o2[4] else ''})
        if show:
            blocks.append({'type': 'product_cards', 'items': [{'product_id': r['product_id'], 'note': r.get('why') or ''} for r in show]})
            if intent == 'compare' and len(show) >= 2:
                blocks.append({'type': 'compare', 'product_ids': [r['product_id'] for r in show[:3]], 'note': ''})
            blocks.append({'type': 'sellers', 'items': sellers})
            sids = list(dict.fromkeys(o['offer_id'] for o in sellers))
            shop_ids = list(dict.fromkeys(RO.execute('SELECT shop_id FROM offers WHERE offer_id=?', (x,)).fetchone()[0] for x in sids))
            for j, sid in enumerate(shop_ids):
                aliases[f'S{j + 1}'] = sid
            if area and area.get('lat'):
                blocks.append({'type': 'map', 'shop_ids': shop_ids, 'center': [area['lat'], area['lon']]})
            if len(prods) > len(show):
                lines.append(f'و {_fa(len(prods) - len(show))} مورد مشابه دیگر در فهرست.')
            lines.append('قیمت‌ها آخرین قیمت ثبت‌شده‌اند، نه موجودی فعلی؛ پیش از مراجعه با فروشگاه تأیید کنید. شماره‌های تماس این داده آزمایشی‌اند.')
    if intent in ('clarify', 'chitchat') and p['clarify_question']:
        lines.append(_clean_fa(p['clarify_question'], allowed))
    chips = [_clean_fa(c, allowed) for c in p['chips'] if c] or (['ارزان‌ترش', 'نزدیک‌تر به من', 'مقایسهٔ دو مورد اول'] if prods else [])
    chips = [c for c in chips if c][:4]
    if chips:
        blocks.append({'type': 'chips', 'options': chips})
    return '\n'.join(l for l in lines if l), blocks, aliases


# ------------------------------------------------------------------ mission
def merge_mission(old, p, data):
    m = dict(old or {})
    al = dict(m.get('_aliases') or {})
    mu = p.get('mission_update') or {}
    for k in ('goal', 'budget_toman', 'notes'):
        if mu.get(k) not in (None, ''):
            m[k] = mu[k]
    sp = mu.get('selected_product')
    if isinstance(sp, str) and sp in al:
        m['selected_product_id'] = al[sp]
    ex = list(m.get('excluded_shop_ids') or [])
    for s in mu.get('exclude_shops') or []:
        sid = al.get(str(s).strip()) or (str(s) if str(s) in _SHOPS else None)
        if sid and sid not in ex:
            ex.append(sid)
    m['excluded_shop_ids'] = ex
    return m

def _resolve_followup_excludes(old, p):
    """shops the shopper rejects THIS turn must be excluded from this turn's fetch already"""
    al = (old or {}).get('_aliases') or {}
    ex = list((old or {}).get('excluded_shop_ids') or [])
    for s in (p.get('mission_update') or {}).get('exclude_shops') or []:
        sid = al.get(str(s).strip()) or (str(s) if str(s) in _SHOPS else None)
        if sid and sid not in ex:
            ex.append(sid)
    return dict(old or {}, excluded_shop_ids=ex)


# ------------------------------------------------------------------ fallback
def _to_v3(hist, mission, user_lat, user_lon, usage, trace, reason, t0, jev_dbg):
    LOG.append({'event': 'fallback_v3', 'reason': reason, 'q': hist[-1]['content'] if hist else ''})
    m = {k: v for k, v in (mission or {}).items() if k != '_aliases'} or None
    v3hist = []
    for h in hist:   # v3 history entries carry the same {text, shown_ids, mission} JSON shape
        v3hist.append({'role': h['role'], 'content': h['content']})
    r = A.run_agent_v3(v3hist, session_mission=m, user_lat=user_lat, user_lon=user_lon)
    u = dict(usage)
    for k in ('prompt_tokens', 'completion_tokens', 'api_calls'):
        u[k] = u.get(k, 0) + r['usage'].get(k, 0)
    u['cost'] = u.get('cost', 0) + r['usage'].get('cost', 0)
    r['usage'] = u
    r['tool_trace'] = trace + r.get('tool_trace', [])
    r['hydration_log']['fallback_from_jev'] = reason
    r['engine'] = 'v3_fallback'
    r['jev'] = jev_dbg
    r['elapsed_s'] = round(time.time() - t0, 1)
    return r


# ------------------------------------------------------------------ main
def run_agent_jev(messages_or_question, mission=None, enable_check=True, user_lat=None, user_lon=None):
    t0 = time.time()
    hist = [{'role': 'user', 'content': messages_or_question}] if isinstance(messages_or_question, str) else list(messages_or_question)
    user_text = next((h['content'] for h in reversed(hist) if h['role'] == 'user'), '')
    usage = {'prompt_tokens': 0, 'completion_tokens': 0, 'cost': 0.0, 'api_calls': 0}
    trace, dbg = [], {}
    # 1. prefilter: current message + earlier user turns + mission goal (follow-ups like «ارزون‌ترش» carry no product words)
    ctx = ' '.join([h['content'] for h in hist if h['role'] == 'user'][-3:] + [str((mission or {}).get('goal') or '')])
    ts = time.time()
    cands = prefilter(ctx)
    trace.append({'tool': 'prefilter', 'ms': int((time.time() - ts) * 1000), 'n': len(cands)})
    dbg['candidates'] = cands
    # 2. JEV
    try:
        p, raw, err = jev_call(hist, mission, cands, usage, trace)
    except Exception as e:
        return _to_v3(hist, mission, user_lat, user_lon, usage, trace, f'jev_llm_error: {type(e).__name__}: {str(e)[:120]}', t0, dbg)
    dbg['raw_jev'] = (raw or '')[:3000]
    if err:
        return _to_v3(hist, mission, user_lat, user_lon, usage, trace, err, t0, dbg)
    if FORCE.get('intent'):
        p['intent'] = FORCE['intent']
    dbg['params'] = {k: v for k, v in p.items()}
    if p['intent'] == 'unsure':
        return _to_v3(hist, mission, user_lat, user_lon, usage, trace, 'intent=unsure', t0, dbg)
    # deterministic guards on the JEV params (logged in jev.guards)
    guards = []
    cheap_words = re.search(r'ارزون|ارزان|کمترین قیمت|cheap', norm(user_text))
    sel = (mission or {}).get('selected_product_id')
    sel_row = RO.execute('SELECT MIN(price_toman) FROM offers WHERE product_id=? AND price_toman IS NOT NULL', (sel,)).fetchone() if sel else None
    if p['intent'] in ('search', 'sellers') and not p['must_terms'] and p['price_max'] and not p['price_min']:
        if sel_row and sel_row[0] and p['price_max'] < sel_row[0] * 1.01:
            p['price_min'] = int(0.5 * sel_row[0]); p['sort'] = 'offers'; guards.append('cheaper-than-shown: price_min = 50% of the shown item, popularity order (same tier, not the cheapest basic models)')
        elif not cheap_words:
            p['price_min'] = int(0.4 * p['price_max']); guards.append('budget browse: price_min = 40% of budget (a "good X up to N" is a choice near the budget)')
            if p['sort'] == 'price':
                p['sort'] = 'offers'; guards.append('budget browse: sort price -> offers (popularity)')
    if p['sort'] == 'distance' and not p['area'] and user_lat is None:
        p['sort'] = 'price'; guards.append('sort distance without any area -> price (fresh first)')
    dbg['guards'] = guards
    # 3. SQL fetch
    m_now = _resolve_followup_excludes(mission, p)
    data = {'products': [], 'shops': []}
    ts = time.time()
    if p['intent'] in ('search', 'compare', 'sellers', 'store') or (p['intent'] == 'clarify' and (p['categories'] or p['must_terms'])):
        data = fetch(p, m_now, user_text, user_lat, user_lon)
    trace.append({'tool': 'sql_fetch', 'ms': int((time.time() - ts) * 1000), 'n_products': len(data.get('products') or []),
                  'n_shops': len(data.get('shops') or []), 'notes': data.get('dbg', {}).get('sql_notes')})
    dbg['fetch'] = {k: v for k, v in (data.get('dbg') or {}).items() if k != 'geocode'}
    dbg['fetch']['top'] = [(r['product_id'], r['title'][:60], r['scope_min']) for r in data.get('products') or []]
    # cheaper-than-shown follow-up: re-show the same item's cheapest offer
    if sel and p['intent'] in ('search', 'sellers') and p['price_max'] and data.get('products') is not None:
        r = RO.execute('SELECT o.price_toman,o.last_price_changed_at,p.persian_title FROM offers o JOIN products p USING(product_id) WHERE o.product_id=? AND o.price_toman IS NOT NULL ORDER BY o.price_toman LIMIT 1', (sel,)).fetchone()
        if r and r[0] > p['price_max']:
            data['same_item'] = {'title': r[2], 'price': int(r[0]), 'date_fa': A._jalali(r[1]) if r[1] else ''}
            data['products'] = [x for x in data['products'] if x['product_id'] != sel]
    searched = p['intent'] in ('search', 'compare', 'sellers', 'store')
    if searched and not data.get('products') and not data.get('shops'):
        return _to_v3(hist, mission, user_lat, user_lon, usage, trace, '0 results after widening', t0, dbg)
    # 4. check
    if enable_check and data.get('products') and p['intent'] != 'store':
        try:
            req = user_text if len(hist) == 1 else f'{(mission or {}).get("goal") or ""} — {user_text}'
            kept, craw = check_call(req, data['products'], usage, trace, plan=p['reason_fa'])
            dbg['check'] = {'kept': [k['product_id'] for k in kept], 'removed': [r['product_id'] for r in data['products'] if not any(k['product_id'] == r['product_id'] for k in kept)]}
            if kept:
                data['products'] = kept
            else:
                return _to_v3(hist, mission, user_lat, user_lon, usage, trace, 'check call removed every candidate (0 results)', t0, dbg)
        except Exception as e:   # a failed check call degrades to the unchecked SQL ranking (logged), it does not drop the turn
            dbg['check_error'] = f'{type(e).__name__}: {str(e)[:120]}'
    # 5. compose + hydrate
    text, blocks, aliases = compose(p, data, m_now, user_text)
    if not text.strip():
        return _to_v3(hist, mission, user_lat, user_lon, usage, trace, 'empty text', t0, dbg)
    hblocks, hlog = A.hydrate(blocks, set())
    if hlog['dropped']:
        LOG.append({'event': 'dropped_ids', 'ids': hlog['dropped'], 'q': user_text})
    newm = merge_mission(m_now, p, data)
    area = data.get('area')
    if area and area.get('lat') and p.get('area'):
        newm['area'], newm['area_latlon'] = p['area'], [area['lat'], area['lon']]
    if p['price_max']:
        newm.setdefault('budget_toman', p['price_max'])
    if aliases.get('P1') and not (p.get('mission_update') or {}).get('selected_product'):
        newm['selected_product_id'] = aliases['P1']
    newm['_aliases'] = aliases
    newm['last_params'] = {k: p[k] for k in ('categories', 'brands', 'must_terms', 'exclude_terms', 'price_min', 'price_max', 'area', 'sort')}
    # log-only checks (same as v3)
    seen_nums = [float(x) for x in re.findall(r'\d{5,}', json.dumps(hblocks))] + [float(v) for v in (p['price_min'], p['price_max']) if v]
    for b in hblocks:
        for it in b.get('items', []) + b.get('products', []):
            for k in ('price_toman', 'min_price', 'median_price'):
                if isinstance(it, dict) and it.get(k): seen_nums.append(float(it[k]))
    for r in data.get('products') or []:
        seen_nums += [float(o[3]) for o, _ in r['offers_in_scope']] + [r['min_price'], r['median_price']]
    if data.get('same_item'):
        seen_nums.append(float(data['same_item']['price']))
    hlog['unverified_price_mentions'] = A.price_mentions_check(text, seen_nums)
    hlog['latin_runs_in_text'] = A._LATIN_RUN.findall(re.sub('|'.join(re.escape(r['title']) for r in data.get('products') or [] if r.get('title')) or '^$', '', text))
    titles = (' '.join(json.dumps(b, ensure_ascii=False) for b in hblocks)).lower()
    hlog['latin_words_not_in_data'] = sorted({w for w in re.findall(r'[A-Za-z][A-Za-z\-]{2,}', text) if w.lower() not in titles})
    hlog['fallback'] = None
    lines = [f'{a} {i}' for a, i in aliases.items()]
    for r in (data.get('products') or [])[:5]:
        lines.append(f'{r["product_id"]} «{r["title"][:60]}» best {r["best"][0][3]}')
    hentry = {'role': 'assistant', 'content': json.dumps({'text': text[:900], 'shown': lines, 'mission': {k: v for k, v in newm.items() if k != '_aliases'}}, ensure_ascii=False)}
    return {'text': text, 'blocks': hblocks, 'mission': newm, 'usage': usage, 'tool_trace': trace, 'hydration_log': hlog,
            'elapsed_s': round(time.time() - t0, 1), 'history_entry': hentry, 'engine': 'jev', 'jev': dbg}
