"""«راه رسیدن داخل پاساژ» — Instagram-story-style step-by-step guide to a shop INSIDE a mall/passage.

Mount (no side effects on import; nothing in playground_app.py changes except these lines):
    import playground_mallguide as MALLGUIDE
    MALLGUIDE.init(auth=_auth, add_spend=_add_spend, can_spend=_cap_ok, client_fn=A.client)   # all optional
    app.include_router(MALLGUIDE.router)

Endpoints
  GET  /api/shop/{sid}/mallguide?pid=&token=        -> guide built from the DB address (+ cached cited mall facts). $0, fast.
  POST /api/shop/{sid}/mallguide/facts?pid=&token=  -> runs ONE BoxAPI web_search for the shop's mall (cached per mall forever),
                                                       then returns the same guide with the cited facts merged. ≈ $0.002 on a miss, $0 on a hit.

Response: {eligible, reason?, shop_id, shop_name, mall, mall_key, street, floor:{level,label,raw}|null, unit:{label,raw}|null,
           steps:[{kind, title, text, visual, source?, links?}], sources:[{n,title,url}], facts_status, llm_calls}
  kind: arrive | floor | unit | shop.  A step whose data is missing in the address is skipped (never invented).
Truthfulness: floor/unit come only from the shop's DB address (parser = playground_mall.parse_address + refinements below);
elevator/escalator are mentioned only when a cited page (url_citation from the web search) says so; any fact without a citation is dropped."""
import json, os, re, threading, time, urllib.request
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool

import playground_drill as D
import playground_home as HOME
import playground_mall as MALL

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.environ.get('MALLGUIDE_CACHE', os.path.join(HERE, 'mallguide_cache')); os.makedirs(CACHE, exist_ok=True)
MODEL = 'gpt-6-luna'
CAP_USD = float(os.environ.get('MALLGUIDE_CAP_USD', '0.10'))     # own hard cap (used when the app's can_spend is not given)
UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36'
_FA = D._FA
_FA2EN = str.maketrans('۰۱۲۳۴۵۶۷۸۹', '0123456789')

router = APIRouter()
_auth_fn = None
_add_spend = None
_can_spend = None
_client_fn = None
_spent = {'usd': 0.0}
_lock = threading.Lock()
_mall_locks: dict = {}

def init(auth=None, add_spend=None, can_spend=None, client_fn=None, cache_dir=None):
    global _auth_fn, _add_spend, _can_spend, _client_fn, CACHE
    _auth_fn, _add_spend, _can_spend, _client_fn = auth, add_spend, can_spend, client_fn
    if cache_dir:
        CACHE = cache_dir; os.makedirs(CACHE, exist_ok=True)

def _check_auth(req: Request):
    if _auth_fn:
        _auth_fn(req); return
    tok = os.environ.get('PLAYGROUND_TOKEN') or (open(os.path.join(HERE, 'playground_token.txt')).read().strip()
                                                  if os.path.exists(os.path.join(HERE, 'playground_token.txt')) else '')
    if tok and req.query_params.get('token') != tok:
        raise HTTPException(403, 'bad token')

def _client():
    if _client_fn:
        return _client_fn()
    from openai import OpenAI
    return OpenAI(api_key=os.environ['BOXAPI_API_KEY'], base_url='https://ai.boxapi.ir/ai/v1', timeout=45, max_retries=0)

def _spend(c):
    _spent['usd'] += c
    if _add_spend:
        _add_spend(c)

def _may_spend(need=0.004):
    if _can_spend:
        return bool(_can_spend(need))
    return _spent['usd'] + need <= CAP_USD

def fa(x):
    return str(x).translate(_FA)

# ------------------------------------------------------------------ address -> mall / floor / unit (reuses playground_mall.parse_address)
_MALL_KW = MALL._MALL
_NOT_HERE = MALL._NOT_HERE
_ORD = MALL._ORD
_NUMW = {'یک': 1, 'دو': 2, 'سه': 3, 'چهار': 4, 'پنج': 5}

def mall_key(name):
    """spelling-insensitive key: علاالدین / علاءالدین / علائدین / علا الدین -> one cache entry per mall"""
    s = (name or '').replace('\u200c', '').replace(' ', '')
    s = s.translate(_FA2EN)
    s = re.sub(r'[ءئأإؤ]', '', s).replace('ي', 'ی').replace('ك', 'ک')
    s = s.replace('علادین', 'علالدین').replace('علاالدین', 'علالدین')
    s = re.sub(r'^(پاساژ|مجتمعتجاری|مجتمع|مرکزخرید|ساختمانتجاری|سرای|تیمچه|برجتجاری|بازارچه)', '', s)
    return s[:40]

def _segs(addr):
    return [x.strip() for x in re.split(r'[،,]', addr or '') if x.strip()]

def _mall_seg(segs):
    for i, sg in enumerate(segs):
        m = _MALL_KW.search(sg)
        if m and not _NOT_HERE.search(sg):
            return i, re.sub(r'\s+', ' ', sg[m.start():]).strip()[:50]      # «سعدی جنوبی بوشهری پاساژ بوشهری» -> «پاساژ بوشهری»
    return None, None

def parse_floor(seg_text):
    """{level:int|None, label, raw}  level: 0 = همکف, -1 = زیرهمکف/منفی ۱/زیرزمین, None = نیم‌طبقه/میانی (no integer level)"""
    s = seg_text.replace('\u200c', ' ').translate(_FA2EN)
    s = re.sub(r'\s+', ' ', s).strip()
    m = re.search(r'منفی\s*(\d+|یک|دو|سه)|طبقه\s*-\s*(\d+)|\(?\bB\s*(\d)\)?', s)
    if m:
        n = m.group(1) or m.group(2) or m.group(3)
        n = _NUMW.get(n, None) if not str(n).isdigit() else int(n)
        if n:
            lab = f'طبقهٔ منفی {fa(n)}'
            if 'زیرزمین' in s and n == 1: lab += ' (زیرزمین)'
            return {'level': -n, 'label': lab}
    if re.search(r'زیر\s*همکف', s): return {'level': -1, 'label': 'زیرهمکف'}
    if 'زیرزمین' in s: return {'level': -1, 'label': 'زیرزمین'}
    m = re.search(r'(نیم\s*طبقه|میان\s*طبقه|طبقه\s*میانی|بالکن)\s*(\S+)?', s)
    if m:
        w = (m.group(2) or '')
        n = _ORD.get(w, int(w) if w.isdigit() else None)
        base = 'بالکن' if 'بالکن' in m.group(1) else ('طبقهٔ میانی' if 'میانی' in m.group(1) else 'نیم‌طبقه')
        return {'level': None, 'label': base + (f' {"" if base == "بالکن" else ""}{_ORD_FA.get(n, fa(n))}' if n else ''), 'half_above': n}
    if re.search(r'همکف', s): return {'level': 0, 'label': 'همکف'}
    m = re.search(r'طبقه(?:\s*ی|ٔ)?\s*(\S+)', s)
    if m:
        w = m.group(1)
        n = _ORD.get(w, _NUMW.get(w, int(re.match(r'\d+', w).group(0)) if re.match(r'\d+', w) else None))
        if n is not None and 0 < n < 40: return {'level': n, 'label': f'طبقهٔ {_ORD_FA.get(n, fa(n))}'}
    return None
_ORD_FA = {1: 'اول', 2: 'دوم', 3: 'سوم', 4: 'چهارم', 5: 'پنجم', 6: 'ششم', 7: 'هفتم', 8: 'هشتم', 9: 'نهم', 10: 'دهم'}

_UNIT = re.compile(r'(واحد|غرفه|مغازه|فروشگاه)\s*(?:شماره\s*)?((?:[A-Za-z]|تی|بی|ای|سی|دی)?\s?-?\s?[0-9۰-۹]+[A-Za-z]?(?:\s*[/\-.]\s*[0-9۰-۹]+)?(?:\s*و\s*[0-9۰-۹]+)?)')
_PLAK = re.compile(r'پلاک\s*([A-Za-z]?\s?[0-9۰-۹]+[A-Za-z]?(?:\s*[/\-.]\s*[0-9۰-۹]+)?(?:\s*و\s*[0-9۰-۹]+)?)')

def parse(addr):
    """mall, street, floor, unit from the raw DB address. Base = playground_mall.parse_address (the app's parser); refinements:
    clean mall name, negative floors as written («منفی ۱» vs «زیرهمکف»), half floors, Persian letter units («واحد تی ۱۲»),
    and «پلاک» counted as the shop unit only when it comes AFTER the mall segment (before it, it is the street number)."""
    base = MALL.parse_address(addr)
    out = {'in_mall': bool(base['in_mall']), 'hint': None, 'mall': None, 'street': None, 'floor': None, 'unit': None, 'base': base}
    segs = _segs(addr)
    mi, mname = _mall_seg(segs)
    if mi is None:
        if base['in_mall'] and base.get('mall'):        # «بلوک …» only — keep the app's decision but no mall name to walk to
            mname = base['mall']; mi = next((i for i, sg in enumerate(segs) if base['mall'] in sg), 0)
        else:
            out['in_mall'] = False
            return out
    out['mall'] = mname
    out['street'] = '، '.join(sg for sg in segs[:mi]) or None
    seg_m = segs[mi]
    tail = segs[mi:]
    inner = [seg_m[_MALL_KW.search(seg_m).end():] if _MALL_KW.search(seg_m) else ''] + tail[1:]
    for sg in inner:
        if re.search(r'طبقه|همکف|زیرزمین|منفی|بالکن|\bB\d', sg):
            f = parse_floor(sg)
            if f:
                f['raw'] = sg.strip(); out['floor'] = f; break
    for sg in inner:
        m = _UNIT.search(sg)
        if m:
            kind = 'غرفهٔ' if m.group(1) == 'غرفه' else 'واحد'
            v = re.sub(r'\s+', ' ', m.group(2)).strip()
            out['unit'] = {'label': f'{kind} {fa(v).upper()}', 'raw': sg.strip(), 'kind': 'unit'}
            break
    for sg in inner:                                        # in-mall landmarks written in the address («راسته چمدان فروش ها», «بلوک B»)
        m = re.search(r'(راسته|بلوک|سالن|ردیف|ورودی|ضلع)\s*\S.*', sg)
        if m and len(m.group(0)) <= 40:
            out['hint'] = re.sub(r'\s+', ' ', m.group(0)).translate(_FA); break
    if not out['unit']:
        for sg in inner:
            m = _PLAK.search(sg)
            if m:
                v = re.sub(r'\s+', '', m.group(1))
                out['unit'] = {'label': f'پلاک {fa(v).upper()}', 'raw': sg.strip(), 'kind': 'plak'}
                break
    return out

# ------------------------------------------------------------------ cited mall facts (ONE web_search per mall, cached)
_FSYS = ('You collect verified practical facts about ONE shopping mall/passage in Tehran for a wayfinding guide in a shopping app. '
         'Use web_search (Persian queries first). Report ONLY facts that a page you cite explicitly states about THIS mall. '
         'Reply with ONE JSON object, no prose before it:\n'
         '{"facts": [{"key": "entrances|floors|elevator|escalator|parking|hours", "fa": "<short Persian sentence, max 12 words>", '
         '"source_url": "<page that states it>"}], "image_url": "<direct image URL of THIS mall from a cited page>" or null}\n'
         'Rules: floors = number of floors; elevator/escalator only if the page explicitly says the mall has one; never guess; '
         'omit any fact you cannot cite; an empty list is fine. After the JSON add one line «منابع:» citing the pages.')
_KW = {'elevator': r'آسانسور|elevator|lift', 'escalator': r'پله\s*‌?\s*برقی|escalator', 'parking': r'پارکینگ|parking',
       'floors': r'طبقه|floor', 'entrances': r'ورودی|درب|entrance', 'hours': r'ساعت|باز|hour|open'}

def _fact_path(key):
    return os.path.join(CACHE, 'mall_' + re.sub(r'[^\w]', '', key) + '.json')

def cached_facts(key):
    p = _fact_path(key)
    if os.path.exists(p):
        try: return json.load(open(p))
        except Exception: return None
    return None

def _fetch(url, n=400_000, timeout=7):
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': UA, 'Accept-Language': 'fa,en;q=0.8'}), timeout=timeout)
        return r.read(n).decode('utf-8', 'replace'), r.headers.get('Content-Type', '')
    except Exception:
        return None, None

def _norm(t):
    t = (t or '').replace('\u200c', '').replace(' ', '').replace('&nbsp;', '')
    t = re.sub(r'[ءئأإؤ]', '', t).replace('ي', 'ی').replace('ك', 'ک')
    return t.replace('علادین', 'علالدین').replace('علاالدین', 'علالدین')

def _ukey(u):
    from urllib.parse import unquote
    u = unquote(str(u).split('?utm_')[0].split('#')[0]).strip().rstrip('/').lower()
    return re.sub(r'^https?://(www\.)?', '', u)

def _build(res):
    """(re)derive facts/sources/photo from the stored model JSON + its url_citations ($0; used again by rebuild())"""
    txt = res.get('raw') or ''
    cp = res.get('cited_pages') or {}
    cited = {k: v['title'] for k, v in cp.items()}; full = {k: v['url'] for k, v in cp.items()}
    res['facts'], res['sources'], res['photo'] = [], [], None
    try:
        j = json.loads(re.search(r'\{.*\}', txt, re.S).group(0))
    except Exception:
        j = {}
    core = [_norm(re.sub(r'\s*[0-9۰-۹]+$', '', re.sub(_MALL_KW, '', res['mall'])).strip())]      # «پاساژ علاالدین ۲» -> «علالدین»
    pages, urls = {}, []
    for f in (j.get('facts') or [])[:8]:
        if not isinstance(f, dict): continue
        k, t, u = str(f.get('key') or ''), str(f.get('fa') or '').strip(), _ukey(str(f.get('source_url') or ''))
        if k not in _KW or not t or len(t) > 90 or u not in cited:
            continue                                                      # no url_citation for that page -> dropped
        if u not in pages: pages[u] = _fetch(full[u])[0]
        page = pages[u]
        verified = None                                                   # None = page not machine-readable (bot wall / JS) -> citation only
        if page and any(_norm(w) in _norm(page) for w in core):
            verified = bool(re.search(_KW[k], page, re.I))
            if not verified: continue                                     # readable page about this mall that does not say it -> dropped
        if k in ('elevator', 'escalator') and verified is not True:
            continue                                                      # lifts are claimed only when we could read the cited page saying so
        if u not in urls: urls.append(u); res['sources'].append({'n': len(urls), 'title': cited[u] or full[u].split('/')[2], 'url': full[u], 'host': full[u].split('/')[2].replace('www.', '')})
        if any(x['key'] == k for x in res['facts']): continue
        res['facts'].append({'key': k, 'fa': t, 'src': urls.index(u) + 1, 'page_verified': verified})
    img = str(j.get('image_url') or '')
    if img.startswith('http'):
        host_ok = any(img.split('/')[2].replace('www.', '').endswith(u.split('/')[0]) or u.split('/')[0].endswith(img.split('/')[2].replace('www.', '')) for u in cited)
        page_has = any(p and img.split('?')[0].split('/')[-1] in p for p in pages.values())
        if host_ok and page_has:
            try:
                rr = urllib.request.urlopen(urllib.request.Request(img, headers={'User-Agent': UA}), timeout=7)
                if rr.status == 200 and rr.headers.get('Content-Type', '').startswith('image/') and int(rr.headers.get('Content-Length') or 30000) > 15000:
                    src = next((v for k, v in cp.items() if pages.get(k) and img.split('?')[0].split('/')[-1] in pages[k]), None)
                    res['photo'] = {'url': img, 'source': src, 'verified': 'loads+on_cited_page', 'needs_human_check': True}
            except Exception:
                pass
    res['status'] = 'ok' if res['facts'] else 'no_cited_facts'
    return res

def rebuild(key):
    c = cached_facts(key)
    if c and c.get('cited_pages') is not None:
        _build(c); json.dump(c, open(_fact_path(key), 'w'), ensure_ascii=False, indent=1)
    return c

def fetch_facts(mall_name, street, key):
    """one BoxAPI Responses web_search call; keep a fact only if its source_url is one of the call's url_citations; when the page can be
    downloaded we additionally require the mall name AND the fact's keyword on the page (elevator/escalator never kept unverified)."""
    c = cached_facts(key)
    if c is not None:
        return c
    res = {'mall_key': key, 'mall': mall_name, 'status': 'empty', 'facts': [], 'sources': [], 'photo': None, 'llm_calls': 0, 'cost_usd': 0.0,
           'ts': time.strftime('%Y-%m-%d %H:%M')}
    t0 = time.time()
    r = _client().responses.create(model=MODEL, instructions=_FSYS, input=f'Mall: {mall_name}\nStreet (from our DB): {street or "-"}\nCity: Tehran',
                                   tools=[{'type': 'web_search'}], reasoning={'effort': 'low'}, max_output_tokens=1400, timeout=45)
    d = r.model_dump()
    cost = float((d.get('usage') or {}).get('cost') or 0); _spend(cost)
    res.update(llm_calls=1, cost_usd=round(cost, 6), latency_s=round(time.time() - t0, 1))
    msg = next((o for o in d.get('output', []) if o.get('type') == 'message'), None)
    part = next((x for x in (msg or {}).get('content', []) if x.get('type') == 'output_text'), None) if msg else None
    txt = (part or {}).get('text') or ''
    cited, full = {}, {}
    for a in (part or {}).get('annotations') or []:
        if a.get('type') == 'url_citation' and str(a.get('url', '')).startswith('http'):
            cited[_ukey(a['url'])] = (a.get('title') or '')[:90]; full.setdefault(_ukey(a['url']), str(a['url']).split('?utm_')[0])
    res['searches'] = [x for x in {(o.get('action') or {}).get('query') for o in d.get('output', []) if o.get('type') == 'web_search_call'} if x]
    res['raw'] = txt[:3000]; res['cited_pages'] = {k: {'title': cited[k], 'url': full[k]} for k in list(full)[:10]}
    _build(res)
    res['status'] = 'ok' if res['facts'] else 'no_cited_facts'
    json.dump(res, open(_fact_path(key), 'w'), ensure_ascii=False, indent=1)
    return res

# ------------------------------------------------------------------ guide
def _offer_price(sid, pid):
    if not pid: return None
    r = D.q('SELECT MIN(price_toman) FROM offers WHERE shop_id=? AND product_id=? AND price_toman IS NOT NULL AND price_toman>0', (sid, pid))
    return int(r[0][0]) if r and r[0][0] else None

def _levels(target, n_floors=None):
    """floors drawn in the building stack: ground .. target only (these must exist). A cited floor count is NOT used: it may or may not include basements."""
    lo, hi = min(0, target), max(0, target)
    return list(range(hi, lo - 1, -1))

def guide(sid, pid=None, now=None):
    s = D.q('SELECT name,address,lat,lon FROM shops WHERE shop_id=?', (sid,))
    if not s:
        return None
    name, addr, lat, lon = s[0]
    p = parse(addr)
    out = {'shop_id': sid, 'shop_name': name, 'address': addr, 'eligible': False, 'mall': p['mall'], 'mall_key': None, 'street': p['street'],
           'floor': p['floor'], 'unit': p['unit'], 'hint': p['hint'], 'steps': [], 'sources': [], 'facts_status': 'none', 'llm_calls': 0}
    if not p['in_mall']:
        out['reason'] = 'not_in_mall'; return out
    out['eligible'] = True
    key = mall_key(p['mall']); out['mall_key'] = key
    fc = cached_facts(key)
    facts = {f['key']: f for f in (fc or {}).get('facts', [])}
    srcs = (fc or {}).get('sources', [])
    out['facts_status'] = 'cached' if fc is not None else 'not_fetched'
    used = set()
    def src(k):
        f = facts.get(k)
        if not f: return None
        used.add(f['src']); x = next((y for y in srcs if y['n'] == f['src']), None)
        return {'title': x['title'], 'url': x['url'], 'host': x.get('host') or x['url'].split('/')[2].replace('www.', '')} if x else None
    # 1 arrive  (copy: /workspace/torob/ux_handoff/spec-mall.md)
    door = p['hint'] if p['hint'] and p['hint'].startswith('ورودی') else None          # «ورودی درب جمهوری» from the address
    st = {'kind': 'arrive', 'title': f'به {p["mall"]} برس', 'text': p['street'] or '',
          'text2': (f'از {door} وارد شو؛ بعد بزن مرحلهٔ بعد' if door else 'داخل که شدی، بزن بریم مرحلهٔ بعد'),
          'visual': {'type': 'building', 'lat': lat, 'lon': lon}, 'links': MALL.route_links(lat, lon), 'facts': []}
    for k in ('entrances', 'parking', 'hours'):
        if k in facts: st['facts'].append({'key': k, 'text': facts[k]['fa'], 'source': src(k)})
    st['facts'] = st['facts'][:2]
    out['steps'].append(st)
    # 2 floor — dropped when the address has no floor
    f = p['floor']
    if f:
        lv, lab = f['level'], f['label']
        go = lab if lv != 0 else 'همکف'
        if lv == 0:
            st = {'kind': 'floor', 'title': 'همین طبقهٔ همکفه', 'text': 'مغازه همکفه؛ لازم نیست طبقه عوض کنی.', 'modes': []}
        else:
            # transport modes: elevator / escalator only with a cited source; stairs always (no claim about the building)
            modes = []
            if 'elevator' in facts: modes.append({'key': 'elevator', 'label': 'آسانسور', 'text': f'با آسانسور برو {go}، بعد بزن مرحلهٔ بعد', 'source': src('elevator')})
            if 'escalator' in facts: modes.append({'key': 'escalator', 'label': 'پله‌برقی', 'text': f'با پله‌برقی برو {go}، بعد بزن مرحلهٔ بعد', 'source': src('escalator')})
            if modes: modes.append({'key': 'stairs', 'label': 'پله', 'text': f'با پله برو {go}، بعد بزن مرحلهٔ بعد'})
            st = {'kind': 'floor', 'title': f'برو {go}', 'text': f'با آسانسور یا پله برو {go}، بعد بزن مرحلهٔ بعد' if not modes else modes[0]['text'], 'modes': modes}
            if modes and modes[0].get('source'): st['source'] = modes[0]['source']
        st['visual'] = {'type': 'floors', 'target': lv, 'label': lab, 'levels': _levels(lv) if lv is not None else None, 'half_above': f.get('half_above')}
        out['steps'].append(st)
    # 3 unit — unknown unit -> honest «ask» step (spec fallback); floor+unit both unknown -> no step 3
    u = p['unit']
    if u:
        num = u['label'].split(' ', 1)[1] if ' ' in u['label'] else u['label']
        out['steps'].append({'kind': 'unit', 'title': f'{u["label"]} رو پیدا کن',
                             'text': f'شماره‌ها معمولاً بالای در مغازه‌هاست؛ دنبال {num} و تابلوی «{name}» بگرد' + (f' ({p["hint"]})' if p['hint'] and not p['hint'].startswith('ورودی') else ''),
                             'visual': {'type': 'corridor', 'unit': num, 'unit_label': u['label'], 'name': name}})
    elif f:
        out['steps'].append({'kind': 'unit', 'title': f'سراغ {name} رو بپرس', 'text': 'شمارهٔ واحد رو نداریم؛ سراغ مغازه رو از نگهبانی یا اطلاعات پاساژ بگیر',
                             'visual': {'type': 'corridor', 'unit': None, 'name': name}})
    # 4 shop
    o = HOME.open_now(sid, now or datetime.now(D.TEHRAN))
    price = _offer_price(sid, pid)
    where = '، '.join(x for x in [name, (f['label'] if f else None), (u['label'] if u else None)] if x) if (f or u) else f'{name}، {p["mall"]}'
    out['steps'].append({'kind': 'shop', 'title': 'رسیدی!', 'text': where,
                         'visual': {'type': 'shop', 'name': name, 'unit_label': u['label'] if u else None,
                                    'open': o['open'] if o['known'] else None, 'open_label': o['label'] if o['known'] else None,
                                    'price_toman': price, 'price_label': f'از {fa(f"{price:,}").replace(",", "٬")} تومان' if price else None}})
    for i, x in enumerate(out['steps']):
        x['n'] = i + 1
    out['entry'] = {'title': 'راهنمای رسیدن داخل پاساژ', 'sub': f'{fa(len(out["steps"]))} مرحلهٔ کوتاه تا جلوی مغازه'}
    out['sources'] = [x for x in srcs if x['n'] in used]
    ph = (fc or {}).get('photo')
    if ph and not ph.get('needs_human_check') and (ph.get('source') or {}).get('url'):     # photo mode only with a known source (spec §5)
        out['steps'][0]['photo'] = {'url': ph['url'], 'source_title': ph['source'].get('title') or ph['source']['url'].split('/')[2], 'source_url': ph['source']['url']}
    return out

def _mall_lock(key):
    with _lock:
        return _mall_locks.setdefault(key, threading.Lock())

def guide_with_facts(sid, pid=None):
    g = guide(sid, pid)
    if not g or not g['eligible'] or g['facts_status'] == 'cached':
        return g
    with _mall_lock(g['mall_key']):
        if cached_facts(g['mall_key']) is None:
            if not _may_spend(0.004):
                return dict(g, facts_status='spend_cap')
            try:
                fetch_facts(g['mall'], g['street'], g['mall_key'])
            except Exception as e:
                return dict(g, facts_status='error', facts_error=type(e).__name__)
    g2 = guide(sid, pid); g2['llm_calls'] = 1
    return g2

@router.get('/api/shop/{sid}/mallguide')
def api_mallguide(sid: str, req: Request, pid: str = ''):
    _check_auth(req)
    g = guide(sid[:64], pid[:64] or None)
    if g is None: raise HTTPException(404, 'shop not found')
    return g

@router.post('/api/shop/{sid}/mallguide/facts')
async def api_mallguide_facts(sid: str, req: Request, pid: str = ''):
    _check_auth(req)
    g = await run_in_threadpool(guide_with_facts, sid[:64], pid[:64] or None)
    if g is None: raise HTTPException(404, 'shop not found')
    return g
