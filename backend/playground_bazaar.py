"""«بورس» (Tehran trade hubs) lookup from bazaars.json (built from the DB by build_bazaars.py). Pure data, no LLM."""
import json, os, re
import playground_drill as D
HERE = os.path.dirname(os.path.abspath(__file__))
_B = {'data': None, 'mtime': 0}
GROUP_WORDS = {   # extra everyday words -> group (the group regexes cover category names)
    'برق ساختمان و روشنایی': r'برق|لوازم برقی|روشنایی|لامپ|چراغ|سیم|کابل برق|پریز|فیوز|لوستر|ال ای دی',
    'دوربین مداربسته و امنیتی': r'مدار ?بسته|دوربین امنیتی|دزدگیر|آیفون تصویری|cctv',
    'موبایل و لوازم جانبی': r'موبایل|گوشی|قاب|گلس|شارژر|پاوربانک|هندزفری',
    'کامپیوتر و لپ‌تاپ': r'کامپیوتر|لپ ?تاپ|لپتاپ|مانیتور|کیس|پرینتر|قطعات کامپیوتر|مودم|کارت گرافیک',
    'ابزار و صنعتی': r'ابزار|دریل|فرز|آچار|صنعتی|پمپ|جوش|پنوماتیک',
    'مبلمان': r'مبل|مبلمان|صندلی|میز|کمد|کاناپه',
    'پوشاک و کفش': r'لباس|پوشاک|کفش|کتانی|مانتو|پیراهن|شلوار|کیف',
    'ساعت': r'ساعت',
    'لوازم خانگی': r'لوازم خانگی|یخچال|لباسشویی|جارو|تلویزیون|کولر|اجاق|مایکروویو',
    'عطر و آرایشی': r'عطر|ادکلن|آرایشی|لوازم آرایش',
}

def data():
    p = os.path.join(HERE, 'bazaars.json')
    m = os.path.getmtime(p)
    if _B['data'] is None or m != _B['mtime']:
        _B['data'], _B['mtime'] = json.load(open(p, encoding='utf-8')), m
    return _B['data']

def group_for(text=None, category=None):
    for g in data()['groups']:
        if category and re.search(g['category_pattern'], category):
            return g
    t = (text or '') + ' ' + (category or '')
    best = None
    for g in data()['groups']:
        if re.search(GROUP_WORDS.get(g['group'], r'$^'), t):
            best = best or g
    return best

def _shop_rows(ids):
    out = []
    for sid in ids:
        r = D.q('SELECT shop_id,name,address,location_label,lat,lon FROM shops WHERE shop_id=?', (sid,))
        if r:
            sid, name, addr, lab, lat, lon = r[0]
            out.append({'shop_id': sid, 'name': name, 'address': addr or D.UNKNOWN, 'area': lab or D.UNKNOWN, 'lat': lat, 'lon': lon,
                        'map_url': f'https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=17/{lat}/{lon}' if lat is not None else None})
    return out

_FA = str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹')
def evidence_fa(h):
    """Persian one-liner from the hub's evidence (counts only, no distances)"""
    ev = h.get('evidence') or ''
    m = re.match(r'(\d+) of (\d+) hub shops mention «([^»]+)»', ev)
    if m:
        return f"{m.group(1)} فروشگاه از {m.group(2)} فروشگاه این محدوده در آدرسشان «{m.group(3)}» آمده است.".translate(_FA)
    m = re.match(r'(\d+) shops with (\d+) offers', ev)
    if m:
        return f"{m.group(1)} فروشگاه با {m.group(2)} پیشنهاد در این محدوده هستند؛ نام محدوده از برچسب محلهٔ بیشتر این فروشگاه‌ها آمده است.".translate(_FA)
    return f"{h.get('shop_count', 0)} فروشگاه در این محدوده هستند.".translate(_FA)

def lookup(text=None, category=None, n_shops=4):
    g = group_for(text, category)
    if not g or not g['hubs']:
        return None
    hubs = []
    for h in g['hubs'][:2]:
        c = h['center']
        hubs.append({'name': h['display_name'], 'hub_name': h['hub_name'], 'named_by': h['named_by'], 'center': c,
                     'map_url': f"https://www.openstreetmap.org/?mlat={c['lat']}&mlon={c['lon']}#map=16/{c['lat']}/{c['lon']}",
                     'shop_count': h['shop_count'], 'share_of_group_offers': h['share_of_group_offers'],
                     'shops': _shop_rows(h['sample_shop_ids'][:n_shops]), 'evidence': h['evidence'], 'evidence_fa': evidence_fa(h)})
    return {'group': g['group'], 'shops_total': g['shops_total'], 'hubs': hubs,
            'note': 'برآورد از روی آدرس و موقعیت فروشگاه‌های این داده؛ نه فهرست کامل بازار', 'llm_calls': 0}

def summary_for_prompt():
    """compact (<~300 tokens) list for the V3+ system prompt"""
    parts = []
    for g in data()['groups']:
        hs = [f"{h['display_name']} {int(round(h['share_of_group_offers'] * 100))}%" for h in g['hubs'][:2]]
        if hs:
            parts.append(f"{g['group']}: " + '، '.join(hs))
    return ('TEHRAN TRADE HUBS («بورس») computed from this DB (share of the group\'s offers; central Tehran dominates this dataset): '
            + ' | '.join(parts) + '. For «X کجا بخرم/بورس X کجاست» call bazaar_hubs and name the hub plus 2–3 of its real shops (map block with their shop_ids).')
