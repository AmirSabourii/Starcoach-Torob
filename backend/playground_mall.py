"""«کجای پاساژه؟» (address parse + optional cited web lookup), routing links, open/closed badges and «بسته بود؟ جایگزین بده» (DB only)."""
import json, os, re, time, threading
from datetime import datetime
import playground_drill as D
import playground_home as HOME

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, 'mall_cache'); os.makedirs(CACHE, exist_ok=True)
_LOCK = threading.Lock()
_FA2EN = str.maketrans('۰۱۲۳۴۵۶۷۸۹', '0123456789')
_ORD = {'اول': 1, 'یکم': 1, 'دوم': 2, 'سوم': 3, 'چهارم': 4, 'پنجم': 5, 'ششم': 6, 'هفتم': 7, 'هشتم': 8, 'نهم': 9, 'دهم': 10,
        'یازدهم': 11, 'دوازدهم': 12}
_MALL = re.compile(r'(پاساژ|مجتمع(?:\s*تجاری)?|مرکز\s*خرید|ساختمان\s*تجاری|سرای|سرا\s|تیمچه|برج\s*تجاری|بازارچه|میدان\s*تره\s*بار)')
_NOT_HERE = re.compile(r'^(رو\s*‌?\s*به\s*‌?\s*روی|روبروی|جنب|نبش|پشت|کنار|بین|نرسیده|بعد\s*از|قبل\s*از|سر\s*کوچه|ابتدای|انتهای|تقاطع)')

def _num(t):
    t = (t or '').translate(_FA2EN).strip()
    m = re.match(r'^-?\d+', t)
    return int(m.group(0)) if m else None

def _floor(seg):
    s = seg.replace('\u200c', ' ').strip()
    if re.search(r'زیر\s*همکف|منفی\s*(یک|1|۱)|زیرزمین', s): return -1, 'زیرهمکف'
    if re.search(r'منفی\s*(دو|2|۲)', s): return -2, 'طبقهٔ منفی ۲'
    if re.search(r'همکف', s): return 0, 'همکف'
    if re.search(r'نیم\s*طبقه|بالکن', s): return None, 'نیم‌طبقه'
    m = re.search(r'طبقه(?:\s*ی|ٔ)?\s*(\S+)', s)
    if m:
        w = m.group(1)
        n = _ORD.get(w, _num(w))
        if n is not None: return n, f'طبقهٔ {str(n).translate(D._FA)}'
    return None, None

def parse_address(addr):
    """{in_mall, mall, floor, floor_label, unit, unit_label, block} from the DB address (no LLM)"""
    out = {'in_mall': False, 'mall': None, 'floor': None, 'floor_label': None, 'unit': None, 'unit_label': None, 'block': None}
    if not addr or addr == D.UNKNOWN:
        return out
    segs = [x.strip() for x in re.split(r'[،,]', addr) if x.strip()]
    plak = None
    for sg in segs:
        if not out['mall'] and _MALL.search(sg) and not _NOT_HERE.search(sg):
            out['mall'] = re.sub(r'\s+', ' ', sg)[:50]; out['in_mall'] = True
        if out['floor_label'] is None and re.search(r'طبقه|همکف|زیرزمین|منفی\s*(یک|1|۱)|بالکن', sg):
            out['floor'], out['floor_label'] = _floor(sg)
        m = re.search(r'(واحد|غرفه|فروشگاه|مغازه)\s*([A-Za-z]?\s?[0-9۰-۹][0-9۰-۹/\-]*(?:\s*و\s*[0-9۰-۹]+)?)', sg)
        if m and not out['unit']:
            out['unit'] = m.group(2).strip(); out['unit_label'] = f"{'غرفهٔ' if m.group(1) == 'غرفه' else 'واحد'} {m.group(2).translate(D._FA).strip().upper()}"
        m = re.search(r'پلاک\s*([A-Za-z]?\s?[0-9۰-۹][0-9۰-۹/\-]*(?:\s*و\s*[0-9۰-۹]+)?)', sg)
        if m and plak is None: plak = m.group(1).strip()
        m = re.search(r'بلوک\s*(\S+(?:\s*(?:شرقی|غربی|شمالی|جنوبی))?)', sg)
        if m and not out['block']: out['block'] = 'بلوک ' + m.group(1).translate(D._FA)
    if not out['unit'] and plak and (out['in_mall'] or out['floor_label']):     # inside a mall «پلاک» is the shop's unit number
        out['unit'] = plak; out['unit_label'] = 'پلاک ' + plak.translate(D._FA).upper()
    if out['block'] and not out['in_mall']:
        out['in_mall'] = True; out['mall'] = out['mall'] or out['block']
    return out

def route_links(lat, lon):
    if lat is None or lon is None:
        return None
    return {'google': f'https://www.google.com/maps/dir/?api=1&destination={lat:.6f},{lon:.6f}',
            'neshan': f'https://neshan.org/maps/routing/car/destination/{lat:.6f},{lon:.6f}'}

def multi_route(points, start=None):
    """nearest-neighbour order (from start, else from the first point) + Google Maps multi-stop link (≤ 9 waypoints)"""
    pts = [p for p in points if p.get('lat') is not None]
    if not pts:
        return None
    rest, order = pts[:], []
    cur = start or (rest[0]['lat'], rest[0]['lon'])
    while rest:
        nx = min(rest, key=lambda p: HOME._hav(cur[0], cur[1], p['lat'], p['lon']))
        order.append(nx); rest.remove(nx); cur = (nx['lat'], nx['lon'])
    order = order[:10]
    dest = order[-1]; way = order[:-1]
    url = f'https://www.google.com/maps/dir/?api=1&destination={dest["lat"]:.6f},{dest["lon"]:.6f}&travelmode=walking'
    if way:
        url += '&waypoints=' + '%7C'.join(f'{p["lat"]:.6f},{p["lon"]:.6f}' for p in way)
    return {'order': [p.get('shop_id') for p in order], 'url': url}

def status(sid, now=None):
    """open_now + a short badge: «الان بازه» / «امروز تعطیل» / «الان بسته» / None (hours unknown)"""
    now = now or datetime.now(D.TEHRAN)
    o = HOME.open_now(sid, now)
    if not o['known']:
        return dict(o, badge=None, state='unknown')
    if o['open']:
        return dict(o, badge='الان بازه', state='open')
    day = HOME._DAY_KEYS[now.weekday()]
    rows = D.q("SELECT 1 FROM shop_hours WHERE shop_id=? AND day=? AND status='declared' AND NOT (start_time LIKE '00:00%' AND end_time LIKE '00:00%')", (sid, day))
    return dict(o, badge='الان بسته' if rows else 'امروز تعطیل', state='closed_now' if rows else 'closed_today')

def statuses(sids, now=None):
    now = now or datetime.now(D.TEHRAN)
    return {s: status(s, now) for s in sids}

def alternatives(sid, pid, k=3, now=None):
    """3 nearest OTHER shops selling the same product (else the same model in the same category) that are open now or have unknown hours.
    Distance is from the closed shop (the shopper is there). DB only, $0."""
    now = now or datetime.now(D.TEHRAN)
    me = D.q('SELECT name,lat,lon FROM shops WHERE shop_id=?', (sid,))
    if not me:
        return None
    name, la, lo = me[0]
    my_mall = parse_address((D.q('SELECT address FROM shops WHERE shop_id=?', (sid,)) or [[None]])[0][0])['mall']
    head = D.product_head(pid) if pid else None
    if not head:
        return {'shop_id': sid, 'shop_name': name, 'product_id': pid, 'items': [], 'reason': 'no_product', 'llm_calls': 0}
    def cands(pids):
        ph = ','.join('?' * len(pids))
        return D.q(f'''SELECT o.offer_id,o.product_id,o.shop_id,o.price_toman,o.last_price_changed_at,s.name,s.lat,s.lon,s.location_label,p.persian_title
                       FROM offers o JOIN shops s USING(shop_id) JOIN products p USING(product_id)
                       WHERE o.product_id IN ({ph}) AND o.shop_id<>? AND o.price_toman IS NOT NULL''', (*pids, sid))
    rows, basis = cands([pid]), 'same_product'
    model = (head.get('model') or '').strip()
    if model and model not in (D.UNKNOWN, 'نامشخص'):
        sib = [r[0] for r in D.q('SELECT product_id FROM products WHERE model=? AND category_name=? AND product_id<>? LIMIT 40', (model, head['category'], pid))]
        if sib:
            extra = cands(sib)
            if len({r[2] for r in rows}) < 6:
                rows += extra
                if extra: basis = 'same_product+same_model'
    ps = sorted(r[3] for r in rows if r[3])
    med = ps[len(ps) // 2] if ps else None
    rows = [r for r in rows if not med or 0.4 * med <= r[3] <= 2.5 * med]     # drop suspicious price outliers
    best = {}
    for r in rows:
        oid, p_, s_, price, changed, sname, slat, slon, label, ptitle = r
        km = HOME._hav(la, lo, slat, slon) if la is not None and slat is not None else None
        prev = best.get(s_)
        key = (p_ != pid, price)
        if prev is None or key < prev['_key']:
            best[s_] = {'_key': key, 'offer_id': oid, 'product_id': p_, 'same_product': p_ == pid, 'product_title': ptitle, 'shop_id': s_, 'shop_name': sname,
                        'price_toman': int(price), 'place': HOME.place_label(slat, slon, label)[0], 'lat': slat, 'lon': slon, '_km': km}
    pool = []
    for s_, x in best.items():
        st = status(s_, now)
        if st['state'] in ('closed_now', 'closed_today'):
            continue
        x['open_badge'] = 'الان بازه' if st['state'] == 'open' else 'ساعت نامشخص'
        x['open_label'] = st['label']; x['is_open'] = st['state'] == 'open'
        pool.append(x)
    # nearest first; open-now shops before unknown-hours ones at a similar distance
    pool.sort(key=lambda x: ((x['_km'] if x['_km'] is not None else 99) + (0 if x['is_open'] else 0.6), x['price_toman']))
    out = []
    for x in pool[:k]:
        km = x.pop('_km'); x.pop('_key', None)
        if km is None: x['distance_label'] = 'فاصله نامشخص'
        elif km < 0.15:
            om = parse_address((D.q('SELECT address FROM shops WHERE shop_id=?', (x['shop_id'],)) or [[None]])[0][0])['mall']
            x['distance_label'] = 'همین پاساژ' if om and my_mall and om.replace(' ', '')[:12] == my_mall.replace(' ', '')[:12] else 'چند قدم آن‌طرف‌تر'
        else: x['distance_label'] = HOME.coarse_distance(km)
        x['routes'] = route_links(x['lat'], x['lon'])
        out.append(x)
    return {'shop_id': sid, 'shop_name': name, 'product_id': pid, 'product_title': head['title'], 'basis': basis, 'items': out,
            'now': now.strftime('%H:%M'), 'llm_calls': 0}

# ------------------------------------------------------------------ optional cited web lookup for floor / unit
_SYS = ('You locate a shop inside a Tehran shopping mall for a shopping app. Use web_search (Persian queries) to find a page that names EXACTLY this shop '
        '(same shop name) in this mall and states its floor and/or unit number. Reply with ONE JSON object only, no prose: '
        '{"floor": "<as written, e.g. طبقه ۲ / همکف>" or null, "unit": "<unit / پلاک / واحد>" or null, "landmark": "<short Persian landmark inside the mall>" or null, '
        '"source_url": "<the page that names this shop>" or null}. If no page clearly names this exact shop with its floor/unit, return all nulls. Never guess. '
        'After the JSON, add one line: «منبع:» followed by the citation of that page (so it is cited).')

def _cp(sid):
    return os.path.join(CACHE, re.sub(r'[^a-z0-9_]', '', sid) + '.json')

def cached_find(sid):
    p = _cp(sid)
    if os.path.exists(p):
        try: return dict(json.load(open(p)), cached=True)
        except Exception: return None
    return None

def find_exact(sid, client_fn, add_spend):
    c = cached_find(sid)
    if c:
        return c
    s = D.q('SELECT name,address FROM shops WHERE shop_id=?', (sid,))
    if not s:
        return None
    name, addr = s[0]
    pa = parse_address(addr)
    res = {'shop_id': sid, 'status': 'unknown', 'floor': None, 'unit': None, 'landmark': None, 'source_url': None, 'source_title': None,
           'llm_calls': 0, 'cost_usd': 0.0, 'ts': time.strftime('%Y-%m-%d %H:%M')}
    if not pa['in_mall']:
        res['status'] = 'not_in_mall'; return res
    with _LOCK:
        t0 = time.time()
        r = client_fn().responses.create(model='gpt-6-luna', instructions=_SYS, input=f'Shop name: {name}\nMall: {pa["mall"]}\nAddress (from our DB): {addr}',
                                         tools=[{'type': 'web_search'}], reasoning={'effort': 'low'}, max_output_tokens=400, timeout=40)
        d = r.model_dump()
    c_ = float((d.get('usage') or {}).get('cost') or 0); add_spend(c_)
    res.update(llm_calls=1, cost_usd=round(c_, 6), latency_s=round(time.time() - t0, 1))
    msg = next((o for o in d.get('output', []) if o.get('type') == 'message'), None)
    part = next((x for x in (msg or {}).get('content', []) if x.get('type') == 'output_text'), None) if msg else None
    txt = (part or {}).get('text') or ''
    cited = {str(a.get('url', '')).split('?utm_')[0]: a.get('title') for a in (part or {}).get('annotations') or [] if a.get('type') == 'url_citation'}
    searched = {(o.get('action') or {}).get('query') for o in d.get('output', []) if o.get('type') == 'web_search_call'}
    res['searches'] = [x for x in searched if x]
    res['cited_urls'] = list(cited)[:5]
    try:
        j = json.loads(re.search(r'\{.*\}', txt, re.S).group(0))
    except Exception:
        j = {}
    url = str(j.get('source_url') or '').split('?utm_')[0]
    # accept only when the model cites a real page from its own search results (url_citation) and gives a floor or unit
    ok_url = url.startswith('http') and (url in cited or any(url.rstrip('/') == u.rstrip('/') for u in cited))
    db_unit = (pa.get('unit') or '').translate(_FA2EN).upper().replace(' ', '')
    web_unit = re.sub(r'[^0-9A-Z/]', '', str(j.get('unit') or '').translate(_FA2EN).upper())
    db_fl, web_fl = pa.get('floor'), _floor('طبقه ' + str(j.get('floor')))[0] if j.get('floor') else None
    unit_is_shop = bool(pa.get('unit_label')) and (not pa['unit_label'].startswith('پلاک') or pa.get('floor') is not None)   # a bare «پلاک» may be the building number
    conflict = (unit_is_shop and db_unit and web_unit and db_unit != web_unit) or (db_fl is not None and web_fl is not None and db_fl != web_fl)
    if ok_url and conflict:
        res['why'] = 'web page disagrees with the DB address'; res['raw'] = txt[:300]
    elif ok_url and (j.get('floor') or j.get('unit')):
        res.update(status='ok', floor=(str(j['floor'])[:30] if j.get('floor') else None), unit=(str(j['unit'])[:30] if j.get('unit') else None),
                   landmark=(str(j['landmark'])[:60] if j.get('landmark') else None), source_url=url, source_title=(cited.get(url) or '')[:90])
    else:
        res['raw'] = txt[:300]; res['why'] = 'no cited page names this shop' if not ok_url else 'no floor/unit'
    json.dump(res, open(_cp(sid), 'w'), ensure_ascii=False)
    return res

def place_info(sid):
    s = D.q('SELECT address,lat,lon FROM shops WHERE shop_id=?', (sid,))
    if not s:
        return None
    pa = parse_address(s[0][0])
    pa['needs_lookup'] = pa['in_mall'] and not (pa['floor_label'] and pa['unit_label'])
    pa['web'] = cached_find(sid)
    pa['routes'] = route_links(s[0][1], s[0][2])
    return pa
