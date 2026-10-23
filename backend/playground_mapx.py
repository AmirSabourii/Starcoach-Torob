"""Interactive map (home «نقشه» toggle): pins for the current chat/search context, ETA by travel mode, open-on-arrival,
«اینجا چی داره؟» for any point, and map-pin filters from chat. DB + bazaars.json only, no LLM.
Distances are never shown as numbers; travel time is an approximate «حدوداً N دقیقه»."""
import json, math, os, re, time
from datetime import timedelta
import playground_drill as D
import playground_home as HOME
import playground_latenight as LN
import playground_mall as MALL

HERE = os.path.dirname(os.path.abspath(__file__))
_FA = str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹')
MODES = ('metro', 'car', 'walk')
MODE_FA = {'metro': 'مترو', 'car': 'ماشین', 'walk': 'پیاده'}

# curated Tehran neighbourhood centroids (approximate public centroids) on top of the app's area list
EXTRA_HOODS = [('جردن', 35.7745, 51.4183), ('یوسف‌آباد', 35.7330, 51.4040), ('امیرآباد', 35.7340, 51.3890), ('ولیعصر', 35.7290, 51.4110),
               ('نیاوران', 35.8150, 51.4700), ('فرمانیه', 35.7960, 51.4690), ('شریعتی', 35.7400, 51.4440), ('مطهری', 35.7270, 51.4280),
               ('جمهوری', 35.6941, 51.4108), ('منوچهری', 35.7004, 51.4192), ('تهرانسر', 35.6930, 51.2400), ('چیتگر', 35.7280, 51.2190),
               ('گیشا', 35.7330, 51.3770), ('زعفرانیه', 35.8030, 51.4140), ('ونک', 35.7570, 51.4100)]

def hoods():
    a = HOME.areas()['areas']
    seen = {x['label'] for x in a}
    out = [{'key': x['key'], 'label': x['label'], 'lat': x['lat'], 'lon': x['lon']} for x in a]
    for n, la, lo in EXTRA_HOODS:
        if n not in seen:
            out.append({'key': nearest_area_key(la, lo), 'label': n, 'lat': la, 'lon': lo})
    return {'hoods': out, 'llm_calls': 0}

def nearest_area_key(lat, lon):
    a = HOME.areas()['areas']
    return min(a, key=lambda x: HOME._hav(lat, lon, x['lat'], x['lon']))['key']

def eta_min(km, mode, now=None):
    """rough door-to-door minutes: straight line × 1.35 road factor; Tehran speeds (car 18 km/h day, 30 late night, +5 min parking;
    walk 4.5 km/h; metro = 12 min walking to/from stations + 5 min wait + ride at 32 km/h, or walking if it is closer than 1.5 km)"""
    if km is None:
        return None
    road = km * 1.35
    walk = road / 4.5 * 60
    if mode == 'walk':
        m = walk
    elif mode == 'car':
        late = now is not None and (now.hour >= 22 or now.hour < 6)
        m = road / (30 if late else 18) * 60 + 5
    else:
        m = walk if km < 1.5 else 12 + 5 + km * 1.2 / 32 * 60
    return max(3, int(m))

def round_min(m):
    if m is None:
        return None
    return m if m < 10 else (int(5 * round(m / 5)) if m < 60 else int(10 * round(m / 10)))

def eta_label(m):
    if m is None:
        return 'نامشخص'
    r = round_min(m)
    return f'حدوداً {str(r).translate(_FA)} دقیقه'

ARR = {'open': 'تا برسی بازه', 'closed': 'تا برسی بسته‌ست', 'unknown': 'ساعت کاری نامشخص'}

def arrival(sids_eta, now):
    """{sid: (eta_min)} -> {sid: {'now': state, 'arrive': state, 'label', 'until', 'opens_at'}} using weekly_hours at now and at now+eta"""
    sids = list(sids_eta)
    st_now = LN.status_at(sids, now)
    by_t = {}
    for s, m in sids_eta.items():
        by_t.setdefault(m or 0, []).append(s)
    out = {}
    for m, ss in by_t.items():
        st = LN.status_at(ss, now + timedelta(minutes=m))
        for s in ss:
            a = st[s]['state']
            out[s] = {'now': st_now[s]['state'], 'arrive': a, 'label': ARR[a], 'until': st_now[s]['until'] or st[s]['until'],
                      'until_fa': LN._until_fa(st_now[s]['until'] or st[s]['until']) if (st_now[s]['until'] or st[s]['until']) else None,
                      'opens_at': st[s]['opens_at']}
    return out

_HUBS = {'v': None}
def hubs():
    if _HUBS['v'] is None:
        b = json.load(open(os.path.join(HERE, 'bazaars.json')))
        seen, hs = set(), []
        for g in b['groups']:
            for h in g['hubs']:
                k = (round(h['center']['lat'], 3), round(h['center']['lon'], 3))
                if k in seen:
                    for x in hs:
                        if (round(x['lat'], 3), round(x['lon'], 3)) == k: x['groups'].append(g['group'])
                    continue
                seen.add(k)
                hs.append({'name': h['display_name'], 'hub_name': h['hub_name'], 'aka': [h['hub_name']] + list(h.get('also_mentioned') or []),
                           'lat': h['center']['lat'], 'lon': h['center']['lon'], 'radius_km': float(h.get('radius_km') or 0.6),
                           'groups': [g['group']], '_raw': h})
        _HUBS['v'] = hs
    return _HUBS['v']

def _ctx_offers(pids=None, q=None, categories=None, limit_products=300):
    """[(shop_id, name, lat, lon, product_id, price)] for the context: product ids > text query > categories"""
    if pids:
        ph = ','.join('?' * len(pids))
        return D.q(f'''SELECT o.shop_id,s.name,s.lat,s.lon,o.product_id,o.price_toman FROM offers o JOIN shops s USING(shop_id)
                       WHERE o.product_id IN ({ph}) AND o.price_toman>0 AND s.lat IS NOT NULL AND (o.price_status='ok' OR o.price_status IS NULL)''', tuple(pids))
    if q and q.strip():
        terms = [t for t in HOME.T.norm(q).split() if len(t) > 1][:4]
        if terms:
            fts = ' '.join('"' + t.replace('"', '') + '"*' for t in terms)
            return D.q(f'''SELECT o.shop_id,s.name,s.lat,s.lon,o.product_id,o.price_toman FROM offers o JOIN shops s USING(shop_id)
                           WHERE o.product_id IN (SELECT product_id FROM products_fts WHERE products_fts MATCH ? LIMIT {limit_products})
                           AND o.price_toman>0 AND s.lat IS NOT NULL AND (o.price_status='ok' OR o.price_status IS NULL)''', (fts,))
    if categories:
        ph = ','.join('?' * len(categories))
        return D.q(f'''SELECT o.shop_id,s.name,s.lat,s.lon,o.product_id,o.price_toman FROM offers o JOIN shops s USING(shop_id) JOIN products p USING(product_id)
                       WHERE p.category_name IN ({ph}) AND o.price_toman>0 AND s.lat IS NOT NULL AND o.price_status='ok' ''', tuple(categories))
    return []

def _nearby_shops(lat, lon, box=0.05):
    return D.q('''SELECT shop_id,name,lat,lon FROM shops WHERE lat BETWEEN ? AND ? AND lon BETWEEN ? AND ?
                  AND shop_id IN (SELECT DISTINCT shop_id FROM offers)''', (lat - box, lat + box, lon - box, lon + box))

def _shop_rows(rows, with_price):
    by = {}
    for r in rows:
        e = by.setdefault(r[0], {'shop_id': r[0], 'name': r[1] or 'نامشخص', 'lat': r[2], 'lon': r[3], 'price_from': None, 'product_id': None})
        if with_price and r[5] and (e['price_from'] is None or r[5] < e['price_from']):
            e['price_from'] = int(r[5]); e['product_id'] = r[4]
    return list(by.values())

def in_hub(h, lat, lon):
    return HOME._hav(h['lat'], h['lon'], lat, lon) <= h['radius_km']

def find_hub(text):
    t = (text or '').replace('ي', 'ی').replace('ك', 'ک')
    for h in hubs():
        for a in sorted(h['aka'], key=len, reverse=True):
            if a and len(a) >= 3 and a in t:
                return h
    return None

def _decorate(shops, lat, lon, mode, now):
    for s in shops:
        s['_km'] = HOME._hav(lat, lon, s['lat'], s['lon'])
        s['eta_min'] = eta_min(s['_km'], mode, now)
    arr = arrival({s['shop_id']: s['eta_min'] for s in shops}, now)
    for s in shops:
        a = arr[s['shop_id']]
        s.update({'open_now': a['now'], 'arrive': a['arrive'], 'arrive_label': a['label'], 'until_fa': a['until_fa'],
                  'eta_label': eta_label(s['eta_min']), 'eta_min': round_min(s['eta_min']), 'distance_label': HOME.coarse_distance(s['_km']),
                  'routes': MALL.route_links(s['lat'], s['lon'])})
    return shops

def apply_filter(shops, f):
    f = f or {}
    out = shops
    if f.get('hub'):
        h = next((x for x in hubs() if x['name'] == f['hub'] or x['hub_name'] == f['hub']), None) or find_hub(f['hub'])
        if h:
            out = [s for s in out if in_hub(h, s['lat'], s['lon'])]
    if f.get('only_open'):
        out = [s for s in out if s['arrive'] == 'open']
    if f.get('cheapest'):
        priced = sorted([s for s in out if s.get('price_from')], key=lambda s: s['price_from'])
        out = priced[:8] if priced else out
    return out

def filter_label(f):
    f = f or {}
    parts = []
    if f.get('only_open'): parts.append('فقط بازها')
    if f.get('cheapest'): parts.append('ارزون‌ترین‌ها')
    if f.get('hub'):
        h = next((x for x in hubs() if x['name'] == f['hub'] or x['hub_name'] == f['hub']), None)
        parts.append('بازار ' + (h['hub_name'] if h else f['hub']))
    return ' · '.join(parts) or None

def pins(lat, lon, mode='metro', now=None, ctx=None, q=None, flt=None, limit=40):
    t0 = time.time()
    now = now or LN.parse_now()[0]
    mode = mode if mode in MODES else 'metro'
    ctx = ctx or {}
    rows = _ctx_offers(pids=ctx.get('pids'), q=None if ctx.get('pids') else q)
    with_price = bool(rows)
    if rows:
        shops = _shop_rows(rows, True)
        label = ctx.get('label') if ctx.get('pids') else q
    else:
        shops = _shop_rows([(r[0], r[1], r[2], r[3], None, None) for r in _nearby_shops(lat, lon)], False)
        label = None
    for s in shops:
        s['_km'] = HOME._hav(lat, lon, s['lat'], s['lon'])
    flt = flt or {}
    if flt.get('hub'):
        h = next((x for x in hubs() if x['name'] == flt['hub'] or x['hub_name'] == flt['hub']), None) or find_hub(flt['hub'])
        if h:
            shops = [s for s in shops if in_hub(h, s['lat'], s['lon'])]
    shops = sorted(shops, key=lambda s: s['_km'])[:max(limit, 60) if flt else limit]
    shops = _decorate(shops, lat, lon, mode, now)
    shops = apply_filter(shops, {k: v for k, v in flt.items() if k != 'hub'})[:limit]
    for s in shops:
        s.pop('_km', None)
    hs = [{'name': h['name'], 'hub_name': h['hub_name'], 'lat': h['lat'], 'lon': h['lon'], 'radius_km': h['radius_km']} for h in hubs()]
    return {'user': {'lat': lat, 'lon': lon}, 'mode': mode, 'mode_fa': MODE_FA[mode], 'now': now.strftime('%H:%M'), 'context': label, 'priced': with_price,
            'filter': flt, 'filter_label': filter_label(flt), 'pins': shops, 'hubs': hs, 'n': len(shops), 'ms': int((time.time() - t0) * 1000), 'llm_calls': 0}

def here(plat, plon, ulat, ulon, mode='metro', now=None, ctx=None, k=3):
    """«اینجا چی داره؟»: nearest relevant shops to a tapped point (context product/category first) + the bazaar there, ETA from the shopper"""
    t0 = time.time()
    now = now or LN.parse_now()[0]
    ctx = ctx or {}
    rows = _ctx_offers(pids=ctx.get('pids'))
    shops = _shop_rows(rows, True) if rows else []
    shops = [s for s in shops if HOME._hav(plat, plon, s['lat'], s['lon']) <= 1.5]
    relevant = bool(shops)
    if len(shops) < k:
        more = _shop_rows([(r[0], r[1], r[2], r[3], None, None) for r in _nearby_shops(plat, plon, 0.02)], False)
        have = {s['shop_id'] for s in shops}
        shops += [s for s in more if s['shop_id'] not in have]
    shops = sorted(shops, key=lambda s: HOME._hav(plat, plon, s['lat'], s['lon']))[:k]
    shops = _decorate(shops, ulat, ulon, mode, now)
    for s in shops:
        s.pop('_km', None)
        if not s.get('price_from'):
            s['sells'] = '، '.join(c['name'] for c in HOME._main_categories(s['shop_id'], 2)) or None
    hb = sorted(hubs(), key=lambda h: HOME._hav(plat, plon, h['lat'], h['lon']))
    bz = None
    if hb and HOME._hav(plat, plon, hb[0]['lat'], hb[0]['lon']) <= 2.0:
        h = hb[0]
        hh = LN._hub_hours(h['_raw'], now)
        km = HOME._hav(ulat, ulon, h['lat'], h['lon'])
        bz = {'name': h['name'], 'lat': h['lat'], 'lon': h['lon'], 'hours_label': hh['label'], 'eta_label': eta_label(eta_min(km, mode, now)),
              'known_for': ' · '.join(h['groups'][:3]), 'routes': MALL.route_links(h['lat'], h['lon'])}
    place = HOME.place_label(plat, plon, None)[0] if hasattr(HOME, 'place_label') else None
    n = len(shops)
    sub = ({1: 'یه مغازهٔ نزدیک این نقطه', 2: 'دو مغازهٔ نزدیک این نقطه', 3: 'سه مغازهٔ نزدیک این نقطه'}.get(n, 'مغازهٔ ثبت‌شده‌ای نزدیک این نقطه نیست'))
    if relevant and ctx.get('label'):
        sub += f' که «{ctx["label"][:30]}» دارن'
    return {'point': {'lat': plat, 'lon': plon, 'place': place}, 'subtitle': sub, 'shops': shops, 'bazaar': bz, 'relevant': relevant,
            'ms': int((time.time() - t0) * 1000), 'llm_calls': 0}

# ---------------------------------------------------------------- chat → map pins
PIN_RX = re.compile(r'پین|روی\s*نقشه|رو\s*نقشه|تو\s*نقشه|نقشه')
_OPEN_RX = re.compile(r'\bباز(ها|ه|ن)?\b|بازها')
_CHEAP_RX = re.compile(r'ارزون|ارزان|کم\s*قیمت')
_ALL_RX = re.compile(r'همه(\s*رو|ی\s*مغازه)|پاکش\s*کن|فیلتر\s*رو\s*بردار')

def parse_pin_cmd(msg, from_map=False):
    """$0 fast path: «فقط مغازه‌های باز رو پین کن», «ارزون‌ترین‌ها رو نشون بده» (map composer), «مغازه‌های علاءالدین» → filter dict or None"""
    m = (msg or '').strip()
    if len(m) > 80 or not (PIN_RX.search(m) or from_map):
        return None
    f = {}
    if _ALL_RX.search(m):
        return {'clear': True}
    if _OPEN_RX.search(m): f['only_open'] = True
    if _CHEAP_RX.search(m): f['cheapest'] = True
    h = find_hub(m)
    if h: f['hub'] = h['name']
    return f or None

def pin_reply(res, f):
    n = res['n']
    nfa = str(n).translate(_FA)
    if f.get('clear'):
        return f'فیلترها رو برداشتم؛ {nfa} مغازه روی نقشه‌ست.'
    if not n:
        return 'با این فیلتر مغازه‌ای روی نقشه نموند؛ فیلتر رو بردار یا محدوده رو عوض کن.'
    what = []
    if f.get('cheapest'): what.append('ارزون‌تر')
    if f.get('only_open'): what.append('باز')
    hub = f'ِ بازار {next((h["hub_name"] for h in hubs() if h["name"] == f.get("hub")), f.get("hub"))}' if f.get('hub') else ''
    return f'{nfa} مغازهٔ {" و ".join(what) + " " if what else ""}{hub.strip("ِ ") + " " if hub else ""}رو پین کردم'.replace('  ', ' ')
