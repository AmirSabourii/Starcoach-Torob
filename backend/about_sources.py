"""Keyless product-text sources for «دربارهٔ این محصول»: Digikala public JSON (search + product page text) and Wikipedia.
Identity matching is deterministic (model code / brand + distinctive tokens); nothing here calls an LLM."""
import html, json, subprocess, re, time, urllib.error, urllib.parse, urllib.request
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36'
FA_DIG = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')
STOP = set('و با در از به برای مدل سایز حجم رنگ ظرفیت اینچ میل میلی متر گیگابایت حافظه رم تا ای ایی یک دو the and with for of size new اصل اصلی اورجینال'.split())
UNIT = re.compile(r'^(\d+(gb|tb|mb|g|k|mp|w|v|a|hz|mah|ml|mm|cm|inch|in|fps|p))$|^(4g|5g|3g|lte|uhd|fhd|hd|4k|8k|2k)$', re.I)
_JAR = '/tmp/about_dk_cookies.txt'

def _get(url, timeout=6):
    if 'digikala.com' in url:      # DigiCDN sets a plain edge cookie via 307 and expects it back; curl's cookie jar handles that like a browser
        r = subprocess.run(['curl', '-s', '-L', '--max-redirs', '4', '-m', str(timeout + 3), '-A', UA, '-c', _JAR, '-b', _JAR, url],
                           capture_output=True, timeout=timeout + 5)
        if r.returncode != 0 or not r.stdout:
            raise RuntimeError(f'curl rc={r.returncode}')
        return r.stdout.decode('utf-8', 'replace')
    hd = {'User-Agent': UA, 'Accept': 'application/json,text/html;q=0.9', 'Accept-Language': 'fa-IR,fa;q=0.9,en;q=0.8'}
    return urllib.request.urlopen(urllib.request.Request(url, headers=hd), timeout=timeout).read().decode('utf-8', 'replace')

def clean(s):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', s or ''))).strip()

def norm(t):
    t = (t or '').translate(FA_DIG).lower().replace('ي', 'ی').replace('ك', 'ک').replace('\u200c', ' ')
    return t

def nkey(t):
    return re.sub(r'[^a-z0-9]', '', norm(t))

def toks(t):
    t = norm(t)
    return [w for w in re.findall(r'[a-z0-9]+(?:[\-.][a-z0-9]+)*|[\u0600-\u06FF]+', t) if w not in STOP and len(w) > 1]

def model_codes(title):
    """Latin/digit tokens that look like a model code (have a digit, not a unit) e.g. LTP-VT02BL-1AUDF, HDW1200TRQP-A, A3949, S25, U8000F."""
    out = []
    for w in re.findall(r'[A-Za-z0-9]+(?:[\-.][A-Za-z0-9]+)*', norm(title)):
        if re.search(r'\d', w) and re.search(r'[a-z]', w) and not UNIT.match(w) and len(nkey(w)) >= 3:
            out.append(w)
    return out

def dk_search(q, n=8):
    j = json.loads(_get('https://api.digikala.com/v1/search/?' + urllib.parse.urlencode({'q': q})))
    return [{'id': p['id'], 'title_fa': p.get('title_fa') or '', 'title_en': p.get('title_en') or '', 'brand': ((p.get('data_layer') or {}).get('brand') or '')}
            for p in (j.get('data') or {}).get('products', [])[:n]]

def dk_product(dk_id):
    p = json.loads(_get(f'https://api.digikala.com/v2/product/{int(dk_id)}/'))['data']['product']
    url = 'https://www.digikala.com/product/dkp-%d/' % int(dk_id)
    texts = []
    rv = p.get('review') or {}
    if rv.get('description'): texts.append(clean(rv['description']))
    ex = p.get('expert_reviews') or {}
    for k in ('short_review', 'description'):
        if ex.get(k) and clean(ex[k]) not in texts: texts.append(clean(ex[k]))
    for sec in ex.get('review_sections') or []:
        for it in sec.get('sections') or []:
            t = clean(it.get('text') or '')
            if len(t) > 60 and t not in texts: texts.append(t)
    pc = p.get('pros_and_cons') or {}
    pros = [clean(x.get('title') if isinstance(x, dict) else x) for x in pc.get('advantages') or []]
    cons = [clean(x.get('title') if isinstance(x, dict) else x) for x in pc.get('disadvantages') or []]
    specs = []
    for g in p.get('specifications') or []:
        for a in g.get('attributes') or []:
            v = '، '.join(clean(x) for x in a.get('values') or [] if clean(x))
            if v and len(v) < 120: specs.append(f"{a.get('title')}: {v}")
    return {'title_fa': p.get('title_fa') or '', 'title_en': p.get('title_en') or '', 'url': url, 'texts': texts,
            'pros': [x for x in pros if x][:5], 'cons': [x for x in cons if x][:5], 'specs': specs[:14],
            'brand': ((p.get('brand') or {}).get('title_fa') or '') + ' ' + ((p.get('brand') or {}).get('title_en') or '')}

def wiki(q, lang='en'):
    j = json.loads(_get(f'https://{lang}.wikipedia.org/w/api.php?' + urllib.parse.urlencode({'action': 'query', 'list': 'search', 'srsearch': q, 'format': 'json', 'srlimit': 3})))
    out = []
    for r in j.get('query', {}).get('search', [])[:3]:
        e = json.loads(_get(f'https://{lang}.wikipedia.org/w/api.php?' + urllib.parse.urlencode({'action': 'query', 'prop': 'extracts', 'exintro': 1, 'explaintext': 1,
                                                                                                    'exsentences': 6, 'titles': r['title'], 'format': 'json'})))
        ex = next(iter(e.get('query', {}).get('pages', {}).values()), {}).get('extract', '')
        if ex:
            out.append({'title': r['title'], 'url': f'https://{lang}.wikipedia.org/wiki/' + urllib.parse.quote(r['title'].replace(' ', '_')), 'text': ex[:900]})
    return out

# ---------------- identity matching (deterministic) ----------------
TRANS = {'آیفون': 'iphone', 'اپل': 'apple', 'سامسونگ': 'samsung', 'شیائومی': 'xiaomi', 'سونی': 'sony', 'هوآوی': 'huawei', 'نوکیا': 'nokia',
         'ایسوس': 'asus', 'لنوو': 'lenovo', 'ایسر': 'acer', 'انکر': 'anker', 'کاسیو': 'casio', 'اشنایدر': 'schneider', 'بوش': 'bosch',
         'فیلیپس': 'philips', 'پاناسونیک': 'panasonic', 'کانن': 'canon', 'نیکون': 'nikon', 'داهوا': 'dahua', 'گلکسی': 'galaxy', 'ردمی': 'redmi',
         'پوکو': 'poco', 'شارپ': 'sharp', 'توشیبا': 'toshiba', 'هیوندای': 'hyundai', 'لگرند': 'legrand', 'نیلپر': 'nilper', 'جولیوس': 'julius',
         'دانهیل': 'dunhill', 'ونس': 'vans', 'دیور': 'dior', 'دیزایر': 'desire', 'رد': 'red', 'بلو': 'blue', 'ماین': 'mine', 'پور': 'pour',
         'هوم': 'homme', 'ایر': 'air', 'پرو': 'pro', 'مکس': 'max', 'اولترا': 'ultra', 'لایتنینگ': 'lightning', 'ایرپاد': 'airpods', 'ایرپادز': 'airpods',
         'ایرپادز': 'airpods', 'اسلیم': 'slim', 'ساندکور': 'soundcore', 'مینی': 'mini', 'پلاس': 'plus', 'لایت': 'lite', 'نوت': 'note',
         'آلفا': 'alpha', 'ارپادز': 'earpods', 'ایرپادس': 'airpods', 'واچ': 'watch', 'پد': 'pad', 'اینتنس': 'intense', 'بلک': 'black', 'گلد': 'gold'}
FA_PHRASE = {'مک بوک': 'macbook', 'پلی استیشن': 'playstation', 'ایکس ویژن': 'x.vision', 'هایک ویژن': 'hikvision', 'جی بی ال': 'jbl',
             'ال جی': 'lg', 'اچ پی': 'hp', 'تی پی لینک': 'tp-link', 'مارک جوزف': 'marc joseph', 'مارک ژوزف': 'marc joseph', 'ایکس باکس': 'xbox'}
ALIAS = {'ps5': 'playstation5', 'ps4': 'playstation4', 'home': 'homme', 'xvision': 'x.vision'}
# words that make a different variant when present on the candidate but absent from ours
VARIANT = set('edition ultra pro plus max mini lite nc anc ii iii iv v vi fe blue red black gold intense edge fold flip slim kit body usb-c lightning'.split())
SOFT = {'alpha', 'galaxy', 'soundcore', 'macbook'}
CATS = [{'عطر', 'ادکلن', 'ادو', 'پرفیوم', 'تویلت', 'اسپری'}, {'کلید', 'فیوز'}, {'هندزفری', 'هدفون', 'ایرپاد', 'هدست'}, {'گوشی', 'موبایل'}, {'لپ', 'لپتاپ', 'نوت', 'بوک'}]
CUT = re.compile(r'\s(?:با|رایحه|سایز|حجم|ظرفیت|رزولوشن|لنز|کانکتور|بند)\s|\|')

def _head(t):
    for m in CUT.finditer(t):
        if len(t[:m.start()].split()) >= 4:
            return t[:m.start()]
    return t
GENERIC_LAT = {'utp', 'ftp', 'sftp', 'bsi', 'cmos', 'uhd', 'hd', 'smart', 'led', 'oled', 'qled', 'dual', 'sim', 'ram', 'ssd', 'wifi', 'pour'}

def _fa2lat(t):
    t = norm(t)
    for k, v in FA_PHRASE.items():
        t = re.sub(r'(?<![\u0600-\u06FF])' + k + r'(?![\u0600-\u06FF])', ' ' + v + ' ', t)
    return ' '.join(TRANS.get(w, w) for w in re.findall(r'[^\s]+', t))

def identity(title, brand_fa):
    full = norm(title)
    head = _head(re.sub(r'\([^)]*\)', ' ', full) + ' ')
    lat_head = _fa2lat(head)
    brand_lat = _fa2lat(brand_fa or '').strip() if brand_fa and brand_fa != 'نامشخص' else ''
    ident = []
    for w in re.findall(r'[a-z0-9]+(?:[\-.][a-z0-9]+)*', lat_head):
        if UNIT.match(w) or w in STOP or len(w) < 2 or re.fullmatch(r'[\d.\-]+', w) or w in GENERIC_LAT or w in brand_lat.split():
            continue
        ident.append(ALIAS.get(w, w))
    for w in model_codes(full):          # model codes anywhere in the title (e.g. M5 after the |)
        w = ALIAS.get(w, w)
        if w not in ident: ident.append(w)
    if not brand_lat:                     # no brand column: first known brand word in the title
        for w in lat_head.split():
            if w in TRANS.values() and w not in VARIANT: brand_lat = w; break
    ident = [w for w in dict.fromkeys(ident) if w != brand_lat]
    fa_toks = [w for w in toks(head) if re.search(r'[\u0600-\u06FF]', w) or w.isdigit()]
    return {'ident': ident, 'brand_lat': brand_lat, 'brand_fa': '' if brand_fa == 'نامشخص' else (brand_fa or ''), 'fa_toks': fa_toks, 'head': head, 'full_lat': _fa2lat(full)}

def _has(tok, cand_lat, cand_key, cand_words):
    k = nkey(tok)
    if len(k) <= 4:
        return k in {nkey(w) for w in cand_words} or (k.isalpha() is False and re.search(r'(?<![a-z0-9])' + re.escape(k) + r'(?![a-z0-9])', cand_lat.replace('-', '')) is not None)
    return k in cand_key

ACC_RX = re.compile(r'محافظ|گلس|کاور|قاب|کیف|لوازم جانبی|مناسب برای|سازگار با|شارژر|برچسب|اسکرین|protector|tempered glass', re.I)

def match(idn, cand):
    """-> (ok, score, why). cand: {'title_fa','title_en','brand'}"""
    if ACC_RX.search(cand['title_fa'] + ' ' + cand['title_en']) and not ACC_RX.search(idn['head']):
        return False, 0, 'accessory_for'      # e.g. «محافظ صفحه نمایش … مناسب برای ساعت میبرو GS Pro» is not the watch
    lat = _fa2lat(cand['title_fa'] + ' ' + cand['title_en'])
    lat = ' '.join(ALIAS.get(w, w) for w in lat.split())
    words = re.findall(r'[a-z0-9]+(?:[\-.][a-z0-9]+)*', lat)
    key = nkey(lat)
    cb = norm(cand.get('brand') or '')
    if idn['brand_fa'] or idn['brand_lat']:
        bhit = (idn['brand_fa'] and norm(idn['brand_fa']) in norm(cand['title_fa'] + ' ' + cb)) or (idn['brand_lat'] and nkey(idn['brand_lat']) in nkey(lat + ' ' + _fa2lat(cb)))
        if not bhit:
            return False, 0, 'brand'
        if cb and cb not in ('متفرقه', 'نامشخص') and idn['brand_fa'] and norm(idn['brand_fa']) not in cb and nkey(idn['brand_lat'] or 'zzz') not in nkey(_fa2lat(cb)):
            return False, 0, 'other_brand'
    miss = [t for t in idn['ident'] if t not in SOFT and not _has(t, lat, key, words)]
    if miss and not (len(idn['ident']) >= 4 and len(miss) == 1):
        return False, 0, 'missing:' + ','.join(miss)
    ours = set(nkey(w) for w in idn['ident']) | set(nkey(w) for w in re.findall(r'[a-z0-9]+(?:[\-.][a-z0-9]+)*', idn['full_lat']))
    extra = [w for w in words if w in VARIANT and nkey(w) not in ours]
    if extra:
        return False, 0, 'variant:' + ','.join(extra)
    cfa = set(toks(cand['title_fa']))
    cat = next((w for w in idn['fa_toks'] if not w.isdigit()), None)
    if cat:
        grp = next((g for g in CATS if cat in g), {cat})
        if not (grp & cfa):
            return False, 0, 'category:' + cat
    cov = sum(1 for w in idn['fa_toks'] if w in cfa) / max(1, len(idn['fa_toks']))
    if not idn['ident'] and cov < 0.6:
        return False, 0, f'low_overlap:{cov:.2f}'
    return True, len(idn['ident']) * 2 + cov + (0.3 if cand['title_en'] else 0), 'ok'

def find_dk(title, brand_fa, log=None):
    """Best Digikala product for this title, or None. Up to 3 searches; deterministic identity check."""
    idn = identity(title, brand_fa)
    full = re.sub(r'\([^)]*\)', ' ', norm(title).split('|')[0])
    qs = [' '.join(idn['head'].split()[:9]), ' '.join(full.split()[:10])]
    if idn['ident']:
        qs.append(((idn['brand_fa'] or idn['brand_lat']) + ' ' + ' '.join(idn['ident'])).strip())
    best, seen, t0 = None, set(), time.time()
    for q in dict.fromkeys(qs):
        if time.time() - t0 > 14:          # keep the drawer request well under the UI timeout
            break
        try:
            res = dk_search(q)
        except Exception as e:
            if log is not None: log.append(f'dk_search: {type(e).__name__}')
            continue
        for r in res:
            if r['id'] in seen: continue
            seen.add(r['id'])
            ok, sc, why = match(idn, r)
            if ok and (not best or sc > best[0]): best = (sc, r)
        if best: break
    return (best[1] if best else None), idn

def wiki_match(idn):
    core = [t for t in idn['ident'] if t not in SOFT]
    if not core or all(t in VARIANT for t in core):
        return None
    q = ' '.join([idn['brand_lat']] + [{'playstation5': 'PlayStation 5'}.get(t, t) for t in idn['ident']]).strip()
    for w in wiki(q, 'en'):
        tk = nkey(w['title'])
        if all(nkey(t) in tk for t in core) and (not idn['brand_lat'] or nkey(idn['brand_lat']) in nkey(w['title'] + ' ' + w['text'][:300])):
            return w
    return None
