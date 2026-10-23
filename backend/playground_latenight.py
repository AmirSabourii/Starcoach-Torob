"""Late-night / «الان کجا بازه؟» scenario (DB only, no LLM): nearest OPEN shop with the product (even if farther) + a nearby
relevant bazaar as a possibility (shops not on Torob may still be open) + data for a mini-map. Open status = weekly_hours (shop_hours) vs
Tehran time, with a test override (`now`)."""
import json, os, re, statistics
from datetime import datetime, timedelta
import playground_drill as D
import playground_home as HOME
import playground_mall as MALL

HERE = os.path.dirname(os.path.abspath(__file__))
_DAYS = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']
_DAY_FA = {'sat': 'شنبه', 'sun': 'یکشنبه', 'mon': 'دوشنبه', 'tue': 'سه‌شنبه', 'wed': 'چهارشنبه', 'thu': 'پنجشنبه', 'fri': 'جمعه'}
TIME_RX = re.compile(r'(همین\s*)?الان|این\s*ساعت|کجا\s*باز|امشب|نصف\s*شب|نیمه\s*شب|دیر\s*وقت|فوری|اورژانسی|همین\s*امشب|شبانه\s*روزی|۲۴\s*ساعته|24\s*ساعته')
_FA = str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹')

def parse_now(now=None, day=None):
    """`now`: 'HH:MM' | 'fri 23:30' | ISO 'YYYY-MM-DDTHH:MM'; `day`: sat..fri. Returns (datetime in Tehran, overridden: bool)."""
    real = datetime.now(D.TEHRAN)
    s = str(now or '').strip().lower()
    if not s and not day:
        return real, False
    d = real
    m = re.match(r'^(\d{4}-\d{2}-\d{2})[t ](\d{1,2}):(\d{2})$', s)
    if m:
        y, mo, dd = map(int, m.group(1).split('-'))
        return real.replace(year=y, month=mo, day=dd, hour=int(m.group(2)), minute=int(m.group(3)), second=0, microsecond=0), True
    m = re.search(r'(\d{1,2}):(\d{2})', s)
    dk = (day or '').strip().lower()[:3] or next((k for k in _DAYS if k in s), None)
    if dk in _DAYS:
        d = d + timedelta(days=(_DAYS.index(dk) - d.weekday()) % 7)
    if m:
        d = d.replace(hour=min(int(m.group(1)), 23), minute=min(int(m.group(2)), 59), second=0, microsecond=0)
    return d, True

def _shifts_by_shop(sids, day):
    out = {}
    if not sids:
        return out
    sids = list(sids)
    for i in range(0, len(sids), 900):
        part = sids[i:i + 900]
        for sid, st, a, b in D.q(f"SELECT shop_id,status,start_time,end_time FROM shop_hours WHERE day=? AND shop_id IN ({','.join('?' * len(part))})", (day, *part)):
            e = out.setdefault(sid, {'declared': [], 'closed': False})
            if st == 'declared' and a and b and not (a[:5] == '00:00' and b[:5] == '00:00'):
                e['declared'].append((a[:5], '24:00' if b[:5] in ('00:00', '23:59') else b[:5]))
            elif st == 'closed':
                e['closed'] = True
    known = {r[0] for i in range(0, len(sids), 900) for r in D.q(f"SELECT DISTINCT shop_id FROM shop_hours WHERE shop_id IN ({','.join('?' * len(sids[i:i + 900]))})", tuple(sids[i:i + 900]))}
    for s in known:
        out.setdefault(s, {'declared': [], 'closed': False})
    return out

def status_at(sids, now):
    """{sid: {'state': open|closed|unknown, 'until': 'HH:MM'|None, 'opens_at': 'HH:MM'|None}} at `now`"""
    day = _DAYS[now.weekday()]; hm = now.strftime('%H:%M')
    sh = _shifts_by_shop(sids, day)
    out = {}
    for s in sids:
        e = sh.get(s)
        if e is None:
            out[s] = {'state': 'unknown', 'until': None, 'opens_at': None}; continue
        cur = next(((a, b) for a, b in sorted(e['declared']) if a <= hm < b), None)
        if cur:
            out[s] = {'state': 'open', 'until': cur[1], 'opens_at': None}
        else:
            nxt = next((a for a, b in sorted(e['declared']) if a > hm), None)
            out[s] = {'state': 'closed', 'until': None, 'opens_at': nxt}
    return out

def _toman(n):
    return f'{int(n):,}'.replace(',', '٬').translate(_FA) + ' تومان'

def _until_fa(u):
    if not u: return 'نامشخص'
    return 'نیمه‌شب' if u == '24:00' else u.translate(_FA)

def is_late(now):
    if now is None:
        now = parse_now(None)[0]
    hm = now.strftime('%H:%M')
    return hm >= '21:00' or hm < '08:30'

def maybe_defer(msg, now):
    """decide BEFORE the agent runs whether the late-night post-step may replace the cards (then the server streams cards once, from the final)"""
    return bool(TIME_RX.search(msg or ''))      # explicit time words only (never the clock alone)

def _hubs_for(categories):
    b = json.load(open(os.path.join(HERE, 'bazaars.json')))
    out = []
    for g in b['groups']:
        if any(re.search(g['category_pattern'], c or '') for c in categories):
            out += [dict(h, group=g['group']) for h in g['hubs']]
    if not out:     # audio / small gadgets are not a bazaars.json group: they are sold in the same mobile-accessory hubs
        alias = 'هدفون|هدست|هندزفری|اسپیکر|ایرپاد|ساعت هوشمند|مچ بند|فلش|رم|کابل'
        if any(re.search(alias, c or '') for c in categories):
            g = next((g for g in b['groups'] if 'شارژر گوشی' in g['category_pattern']), None)
            out = [dict(h, group=g['group']) for h in g['hubs']] if g else []
    return out

_HH_CACHE = {}
def _hub_hours(h, now):
    k = (h.get('hub_name'), h['center']['lat'], now.weekday(), now.strftime('%H:%M'))
    if k not in _HH_CACHE:
        _HH_CACHE[k] = _hub_hours_(h, now)
    return _HH_CACHE[k]

def _hub_hours_(h, now):
    """typical closing time today of shops within the hub radius (from weekly_hours) + how many of them are open now"""
    la, lo, r = h['center']['lat'], h['center']['lon'], max(h.get('radius_km') or 0.7, 0.5)
    dlat, dlon = r / 111.0, r / 90.0
    sids = [x[0] for x in D.q('SELECT shop_id,lat,lon FROM shops WHERE lat BETWEEN ? AND ? AND lon BETWEEN ? AND ?', (la - dlat, la + dlat, lo - dlon, lo + dlon))
            if HOME._hav(la, lo, x[1], x[2]) <= r]
    sh = _shifts_by_shop(sids, _DAYS[now.weekday()])
    ends = [max(b for a, b in e['declared']) for e in sh.values() if e['declared']]
    st = status_at(sids, now)
    n_open = sum(1 for v in st.values() if v['state'] == 'open')
    if len(ends) < 5:
        return {'typical_close': None, 'label': 'نامشخص', 'n_shops': len(sids), 'n_with_hours': len(ends), 'n_open_now': n_open}
    med = sorted(ends)[len(ends) // 2]
    return {'typical_close': med, 'label': f'معمولاً تا حدود {_until_fa(med)}', 'n_shops': len(sids), 'n_with_hours': len(ends), 'n_open_now': n_open}

def build(pids, msg, now, user_pt, user_label, llm_flag=False, categories=None):
    """-> None (normal answer stands) or {'block': late_night block, 'text', 'product_id', 'offer_id'}"""
    pids = [p for p in (pids or []) if p]
    cats = list(categories or [])
    for p in pids:
        h = D.product_head(p)
        if h and h['category'] and h['category'] not in cats: cats.append(h['category'])
    if not cats:
        return None
    ula, ulo = user_pt
    # relevant offers: the shown products first, then the same categories
    rows = D.q(f'''SELECT o.offer_id,o.product_id,o.shop_id,o.price_toman,s.name,s.lat,s.lon,s.location_label,p.persian_title,p.category_name
                   FROM offers o JOIN shops s USING(shop_id) JOIN products p USING(product_id)
                   WHERE p.category_name IN ({','.join('?' * len(cats[:3]))}) AND o.price_toman IS NOT NULL AND o.price_status='ok' AND s.lat IS NOT NULL''', tuple(cats[:3]))
    if not rows:
        return None
    shops = {}
    for oid, pid, sid, price, name, la, lo, label, title, cat in rows:
        km = HOME._hav(ula, ulo, la, lo)
        e = shops.setdefault(sid, {'shop_id': sid, 'name': name, 'lat': la, 'lon': lo, 'label': label, 'km': km, 'offers': []})
        e['offers'].append({'offer_id': oid, 'product_id': pid, 'price': int(price), 'title': title, 'shown': pid in pids})
    st = status_at(list(shops), now)
    near = sorted(shops.values(), key=lambda x: x['km'])
    near_known = [x for x in near if st[x['shop_id']]['state'] != 'unknown'][:6]
    closed_near = [x for x in near_known if st[x['shop_id']]['state'] == 'closed']
    time_words = bool(TIME_RX.search(msg or ''))
    majority_closed = len(near_known) >= 3 and len(closed_near) / len(near_known) >= 0.6
    trigger = time_words      # ONLY explicit time urgency in the message; llm flag / closed-majority are recorded, never trigger
    if not trigger:
        return None
    opened = [x for x in near if st[x['shop_id']]['state'] == 'open']
    best = opened[0] if opened else None
    hubs = _hubs_for(cats)
    hub = min(hubs, key=lambda h: HOME._hav(ula, ulo, h['center']['lat'], h['center']['lon'])) if hubs else None
    hm = now.strftime('%H:%M')
    blk = {'type': 'late_night', 'now': hm, 'day': _DAY_FA[_DAYS[now.weekday()]], 'user': {'lat': ula, 'lon': ulo, 'label': user_label},
           'trigger': {'time_words': time_words, 'llm_flag': bool(llm_flag), 'nearby_closed': f'{len(closed_near)}/{len(near_known)}'},
           'shop': None, 'bazaar': None, 'n_closer_closed': 0}
    parts = []
    pid = oid = None
    if best:
        _st = {t for (t,) in D.q('SELECT persian_title FROM products WHERE product_id IN (%s)' % ','.join('?' * len(pids)), tuple(pids))} if pids else set()
        for x in best['offers']:
            x['shown'] = x['shown'] or x['title'] in _st     # same listing title under another product id = same product
        o = sorted(best['offers'], key=lambda x: (not x['shown'], x['price']))[0]
        pid, oid = o['product_id'], o['offer_id']
        closer_closed = [x for x in near if x['km'] < best['km'] and st[x['shop_id']]['state'] == 'closed']
        blk['n_closer_closed'] = len(closer_closed)
        place = HOME.place_label(best['lat'], best['lon'], best['label'])[0]
        loc = MALL.parse_address((D.q('SELECT address FROM shops WHERE shop_id=?', (best['shop_id'],)) or [[None]])[0][0])
        blk['shop'] = {'shop_id': best['shop_id'], 'name': best['name'], 'place': place, 'lat': best['lat'], 'lon': best['lon'],
                       'distance_label': HOME.coarse_distance(best['km']), 'until': st[best['shop_id']]['until'], 'until_fa': _until_fa(st[best['shop_id']]['until']),
                       'product_id': pid, 'offer_id': oid, 'product_title': o['title'], 'price_toman': o['price'], 'same_product': o['shown'],
                       'location': ' · '.join(x for x in [loc['mall'], loc['floor_label'], loc['unit_label']] if x) or None,
                       'routes': MALL.route_links(best['lat'], best['lon'])}
        if closer_closed:
            parts.append(f"الان ساعت {hm.translate(_FA)}ه و فروشگاه‌های نزدیک‌تر بسته‌اند.")
        what = 'همین محصول' if o['shown'] else 'یه گزینه از همین دسته'
        parts.append(f"نزدیک‌ترین جایی که الان بازه «{best['name']}»ه، {place} ({HOME.coarse_distance(best['km'])})؛ {what} اونجا {_toman(o['price'])}ه و تا {_until_fa(st[best['shop_id']]['until'])} بازه.")
    else:
        nxt = sorted([x for x in near_known if st[x['shop_id']]['opens_at']], key=lambda x: (st[x['shop_id']]['opens_at'], x['km']))
        parts.append(f"الان ساعت {hm.translate(_FA)}ه و طبق ساعت‌های ثبت‌شده، فروشگاه‌های ترب که این نوع کالا رو دارن الان بسته‌اند.")
        when = 'امروز'
        if not nxt:     # nothing later today -> tomorrow's first opening
            t2 = (now + timedelta(days=1)).replace(hour=0, minute=0)
            st2 = status_at([x['shop_id'] for x in near_known], t2)
            nxt = sorted([x for x in near_known if st2[x['shop_id']]['opens_at']], key=lambda x: (st2[x['shop_id']]['opens_at'], x['km']))
            st, when = {**st, **{k: v for k, v in st2.items()}}, 'فردا'
        if nxt:
            ns = nxt[0]
            blk['next_open'] = {'shop_id': ns['shop_id'], 'name': ns['name'], 'when': when, 'opens_at': st[ns['shop_id']]['opens_at'], 'distance_label': HOME.coarse_distance(ns['km'])}
            parts.append(f"نزدیک‌ترینشون، «{ns['name']}» ({HOME.coarse_distance(ns['km'])})، {when} از {st[ns['shop_id']]['opens_at'].translate(_FA)} باز می‌کنه.")
    if hub:
        hk = HOME._hav(ula, ulo, hub['center']['lat'], hub['center']['lon'])
        hh = _hub_hours(hub, now)
        name = hub.get('display_name') or hub['hub_name']
        blk['bazaar'] = {'name': name, 'known_for': hub.get('known_for'), 'lat': hub['center']['lat'], 'lon': hub['center']['lon'],
                         'distance_label': HOME.coarse_distance(hk), 'hours_label': hh['label'], 'hours': hh, 'routes': MALL.route_links(hub['center']['lat'], hub['center']['lon'])}
        dist = {'همین نزدیکی': 'همین نزدیکیه', 'نزدیک': 'نزدیکتونه', 'کمی دورتر': 'کمی دورتره', 'دور': 'از شما دوره'}.get(HOME.coarse_distance(hk), 'نزدیکه')
        hours_txt = f"ساعت کاری ثبت‌شدهٔ مغازه‌هاش {hh['label']}ه" if hh['typical_close'] else 'ساعت کاری معمولش نامشخصه'
        extra = f" طبق ساعت‌های ثبت‌شده {str(hh['n_open_now']).translate(_FA)} مغازه اونجا الان بازن (نه لزوماً با همین محصول)." if hh['n_open_now'] and best else ''
        parts.append(f"بازار {name} هم {dist} و {hours_txt}؛ ممکنه مغازه‌هایی که تو ترب نیستن هنوز باز باشن.{extra}")
    return {'block': blk, 'text': ' '.join(parts), 'product_id': pid, 'offer_id': oid}
