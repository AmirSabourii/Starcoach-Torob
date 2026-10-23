"""«دربارهٔ این محصول» (v2: Digikala public product text + Wikipedia, see about_sources.py; Bing kept as a helper) -> ONE short BoxAPI call that writes
3–5 Persian sentences ONLY from the snippets (with source links). Cached per product_id on disk. Empty when nothing reliable."""
import html, json, os, re, time, urllib.parse, urllib.request
import playground_drill as D
HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(HERE, 'about_cache'); os.makedirs(CACHE_DIR, exist_ok=True)
UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36'
WIKI_UA = 'TorobPlaygroundDemo/1.0 (hackathon; contact: none)'
MODEL = 'gpt-6-luna'
MAX_OUT = 250

def _get(url, ua=UA, timeout=6):
    req = urllib.request.Request(url, headers={'User-Agent': ua, 'Accept-Language': 'en-US,en;q=0.8,fa;q=0.6'})
    return urllib.request.urlopen(req, timeout=timeout).read().decode('utf-8', 'replace')

def _clean(s):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', s or ''))).strip()

def bing(q, n=6):
    h = _get('https://www.bing.com/search?' + urllib.parse.urlencode({'q': q, 'setlang': 'en', 'cc': 'us'}))
    out = []
    for blk in re.findall(r'<li class="b_algo"(.*?)</li>', h, re.S):
        a = re.search(r'<h2[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', blk, re.S)
        p = re.search(r'<p[^>]*>(.*?)</p>', blk, re.S) or re.search(r'class="b_caption"[^>]*>(.*?)</div>', blk, re.S)
        if a and p:
            url = html.unescape(a.group(1))
            if 'bing.com/ck/' in url:      # tracking redirect: real url is base64 in u=a1...
                m = re.search(r'[?&]u=a1([^&]+)', url)
                if m:
                    import base64
                    try: url = base64.urlsafe_b64decode(m.group(1) + '=' * (-len(m.group(1)) % 4)).decode()
                    except Exception: pass
            out.append({'title': _clean(a.group(2)), 'url': url, 'snippet': _clean(p.group(1))[:400], 'engine': 'bing'})
        if len(out) >= n:
            break
    return out

def wikipedia(q, lang='en', n=1):
    j = json.loads(_get(f'https://{lang}.wikipedia.org/w/api.php?' + urllib.parse.urlencode({'action': 'query', 'list': 'search', 'srsearch': q, 'format': 'json', 'srlimit': 2}), WIKI_UA))
    out = []
    for r in j.get('query', {}).get('search', [])[:n]:
        e = json.loads(_get(f'https://{lang}.wikipedia.org/w/api.php?' + urllib.parse.urlencode({'action': 'query', 'prop': 'extracts', 'exintro': 1, 'explaintext': 1,
                                                                                                    'exsentences': 5, 'titles': r['title'], 'format': 'json'}), WIKI_UA))
        ex = next(iter(e.get('query', {}).get('pages', {}).values()), {}).get('extract', '')
        if ex:
            out.append({'title': r['title'] + ' — Wikipedia', 'url': f'https://{lang}.wikipedia.org/wiki/' + urllib.parse.quote(r['title'].replace(' ', '_')),
                        'snippet': ex[:700], 'engine': 'wikipedia'})
    return out

FA_EN = {'آیفون': 'iPhone', 'اپل': 'Apple', 'سامسونگ': 'Samsung', 'شیائومی': 'Xiaomi', 'سونی': 'Sony', 'هوآوی': 'Huawei', 'نوکیا': 'Nokia',
         'ال جی': 'LG', 'ایسوس': 'ASUS', 'لنوو': 'Lenovo', 'اچ پی': 'HP', 'دل': 'Dell', 'ایسر': 'Acer', 'انکر': 'Anker', 'جی بی ال': 'JBL',
         'کاسیو': 'Casio', 'اشنایدر': 'Schneider', 'بوش': 'Bosch', 'فیلیپس': 'Philips', 'پاناسونیک': 'Panasonic', 'کانن': 'Canon', 'نیکون': 'Nikon',
         'هایک ویژن': 'Hikvision', 'داهوا': 'Dahua', 'گلکسی': 'Galaxy', 'پلی استیشن': 'PlayStation', 'ایکس باکس': 'Xbox', 'مک بوک': 'MacBook',
         'آیپد': 'iPad', 'ایرپاد': 'AirPods', 'ردمی': 'Redmi', 'پوکو': 'Poco', 'شارپ': 'Sharp', 'توشیبا': 'Toshiba', 'تی پی لینک': 'TP-Link'}
def _norm_key(t):
    return re.sub(r'[^a-z0-9]', '', (t or '').lower())

def _query_terms(pid):
    h = D.product_head(pid)
    if not h:
        return None
    specs = {k: v for _, k, v in D.q('SELECT section,key,value FROM product_specs WHERE product_id=?', (pid,))}
    title = (h['title'] or '').split('|')[0]
    name_spec = next((v for k, v in specs.items() if k in ('نام محصول', 'مدل') and v and len(re.findall(r'[A-Za-z]', v)) >= 3), None)
    base = name_spec or title
    words = [w for w in re.findall(r'[A-Za-z0-9][A-Za-z0-9\-\.+]*', base) if not re.fullmatch(r'[\d.]+', w) or len(w) >= 2]
    words = [w for w in words if '/' not in w and w != 'f' and not re.fullmatch(r'\d+\.\d+(-\d+(\.\d+)?)?', w)]
    en = [v for k, v in FA_EN.items() if re.search(r'(?<![\u0600-\u06FF])' + k + r'(?![\u0600-\u06FF])', title)]
    brand_lat = next((v for k, v in specs.items() if k in ('شرکت سازنده', 'برند', 'سازنده') and re.search(r'[A-Za-z]', v or '')), None) or (FA_EN.get(h['brand']) if h['brand'] else None)
    lead = [x for x in ([brand_lat] if brand_lat else []) + en if x and x.lower() not in ' '.join(words).lower()]
    q = ' '.join(dict.fromkeys(lead + words)).strip()
    series = [x for x in en if x not in (brand_lat,) and x.lower() not in ' '.join(words).lower() and x not in ('Sony', 'Apple', 'Samsung', 'Xiaomi')]
    q2 = ' '.join(dict.fromkeys(series + words)).strip()   # model-centric variant (Bing sometimes collapses brand-led queries)
    digit_toks = sorted([w for w in words if re.search(r'\d', w)], key=len, reverse=True)
    key = None
    if digit_toks:
        t = digit_toks[0]
        key = _norm_key(t) if re.search(r'[A-Za-z]', t) or '-' in t else _norm_key((en[-1] if en else (brand_lat or '')) + t)
    elif words:
        key = _norm_key(max(words, key=len))
    if not q or not key or len(key) < 3:
        return {'head': h, 'query': q or title, 'model_token': None, 'key': None, 'brand': brand_lat or h['brand']}
    return {'head': h, 'query': q, 'queries': list(dict.fromkeys([x for x in (q2, q) if x])), 'model_token': digit_toks[0] if digit_toks else max(words, key=len), 'key': key, 'brand': brand_lat or h['brand']}

_SYS = ('You write a short factual product note in Persian for a shopping app. Use ONLY facts stated in the numbered passages. '
        'Ignore anything you know from elsewhere. Write 3-5 short, natural Persian sentences (friendly, not salesy) about what the product is, '
        'its main features and who it suits; end each sentence with the passage number(s) it comes from, like [2] or [1][3]. '
        'Never mention prices, sellers, shops, warranty, delivery or discounts. '
        'The passages were pre-matched to this product by brand and model code. Variants that differ only in storage/RAM, screen size, colour, '
        'region, bundled lens or package are acceptable: then only state facts shared by the product (do not repeat a capacity, size or colour '
        'that differs from the product title). Output exactly NONE only if the passages are clearly about a different model or product type, '
        'or say too little to write 2 sentences.')
CACHE_V2 = os.path.join(HERE, 'about_cache_v2'); os.makedirs(CACHE_V2, exist_ok=True)
CACHE_DIR = CACHE_V2          # app's spend-cap check looks here for an existing cache entry
_BAD = re.compile(r'تومان|ریال|دلار|\$|€|قیمت|دیجی ?کالا|دیجی‌کالا|گارانتی|ارسال|تخفیف|فروشنده|فروشگاه')

def _passages(dk, wk):
    ps = []
    if dk:
        src = {'title': dk['title_fa'][:90], 'url': dk['url'], 'engine': 'digikala'}
        for t in dk['texts'][:4]:
            ps.append(dict(src, text=t[:700]))
        if dk['pros'] or dk['cons']:
            ps.append(dict(src, text=('نقاط قوت: ' + '، '.join(dk['pros']) if dk['pros'] else '') + (' | نقاط ضعف: ' + '، '.join(dk['cons']) if dk['cons'] else '')))
        if dk['specs']:
            ps.append(dict(src, text='مشخصات: ' + ' ؛ '.join(dk['specs'])[:700]))
    if wk:
        ps.append({'title': wk['title'] + ' — Wikipedia', 'url': wk['url'], 'engine': 'wikipedia', 'text': wk['text'][:800]})
    return ps

def about_dk(pid, client_fn, cost_fn, add_spend, force=False):
    """v2 (fallback): Digikala public product text (+ English Wikipedia) matched to the product by a deterministic identity check
    (brand + model code / distinctive tokens, category guard, variant guard) -> ONE short cited LLM call. Empty when unsure."""
    import about_sources as S
    pid = pid[:64]
    cp = os.path.join(CACHE_V2, re.sub(r'[^a-z0-9_]', '', pid) + '.json')
    if os.path.exists(cp) and not force:
        d = json.load(open(cp)); d['cached'] = True; return d
    h = D.product_head(pid)
    if not h:
        return None
    t0 = time.time(); errs = []
    res = {'product_id': pid, 'query': (h['title'] or '').split('|')[0].strip(), 'sentences': [], 'cited': [], 'sources': [], 'status': 'empty',
           'llm_calls': 0, 'cost_usd': 0.0, 'version': 2}
    dk = wk = None
    try:
        cand, idn = S.find_dk(h['title'] or '', h['brand'] or '', errs)
        res['identity'] = {'brand': idn['brand_lat'] or idn['brand_fa'], 'tokens': idn['ident']}
        if cand:
            res['matched'] = {'source': 'digikala', 'title': cand['title_fa'][:120]}
            dk = S.dk_product(cand['id'])
    except Exception as e:
        errs.append(f'digikala: {type(e).__name__}: {str(e)[:80]}'); idn = None
    try:
        if idn: wk = S.wiki_match(idn)
    except Exception as e:
        errs.append(f'wikipedia: {type(e).__name__}')
    ps = _passages(dk, wk)
    res['n_passages'] = res['n_relevant'] = len(ps)
    if errs: res['search_errors'] = errs
    if not ps or (len(ps) == 1 and ps[0]['text'].startswith('مشخصات')):
        res['status'] = 'no_matching_source'
    else:
        user = f"Product: {h['title']} (brand: {h['brand']})\n\n" + '\n'.join(f"[{i+1}] (source: {p['title']}) {p['text']}" for i, p in enumerate(ps))
        try:
            r = client_fn().chat.completions.create(model=MODEL, messages=[{'role': 'system', 'content': _SYS}, {'role': 'user', 'content': user}],
                                                    max_completion_tokens=MAX_OUT, reasoning_effort='none', timeout=15)
            c = cost_fn(r.usage); add_spend(c)
            res['llm_calls'], res['cost_usd'] = 1, round(c, 6)
            txt = (r.choices[0].message.content or '').strip()
            if txt and 'NONE' not in txt[:10]:
                sents = [x.strip() for x in re.split(r'(?<=[.!؟\]])\s+(?=[^\[])', txt) if x.strip()]
                used, cited = set(), []
                for s_ in sents:
                    refs = sorted({int(n) for n in re.findall(r'\[(\d+)\]', s_) if 1 <= int(n) <= len(ps)})
                    if not refs or _BAD.search(s_):
                        continue
                    used |= set(refs)
                    cited.append({'text': re.sub(r'\s*\[\d+\]', '', s_).strip(), 'refs': refs})
                if len(cited) >= 2:
                    srcs, umap = [], {}
                    for i in sorted(used):          # one source entry per URL; refs renumbered to source order
                        u = ps[i - 1]['url']
                        if u not in umap:
                            umap[u] = len(srcs) + 1
                            srcs.append({'n': umap[u], 'title': ps[i - 1]['title'], 'url': u, 'engine': ps[i - 1]['engine']})
                    for c_ in cited:
                        c_['refs'] = sorted({umap[ps[i - 1]['url']] for i in c_['refs']})
                    res.update(sentences=[c_['text'] for c_ in cited[:5]], cited=cited[:5], sources=srcs, status='ok')
                else:
                    res['status'] = 'model_output_rejected'
            else:
                res['status'] = 'model_unsure'
        except Exception as e:
            res['status'] = 'llm_error'; res['error'] = f'{type(e).__name__}: {str(e)[:120]}'
    res['elapsed_s'] = round(time.time() - t0, 1)
    if res['status'] != 'llm_error' and not errs:
        json.dump(res, open(cp, 'w'), ensure_ascii=False)
    return res

# ---------------------------------------------------------------- v3: BoxAPI built-in web search (Responses API, tools=[{type:"web_search"}])
CACHE_V3 = os.path.join(HERE, 'about_cache_v3'); os.makedirs(CACHE_V3, exist_ok=True)
CACHE_DIR = CACHE_V3          # app's spend-cap check looks here for an existing cache entry
ACC_DB = re.compile(r'محافظ|گلس|کاور|قاب|کیف|بند ساعت|بند یدک|لوازم جانبی|مناسب برای|سازگار با|شارژر|کابل|برچسب|اسکرین|پایه|استند|فیلم محافظ')
ACC_CLAIM = re.compile(r'محافظ صفحه|گلس|لوازم جانبی|اکسسوری|نه خود|نه خودِ|کاور گوشی|قاب گوشی|screen protector', re.I)   # «قاب» alone = watch case, so not here
_WSYS = ('You write a short factual product note in Persian for a shopping app. Use the web_search tool to find pages about EXACTLY the product below '
         '(same brand, same model/series name, same product type). Then write 2-4 short, natural Persian sentences (not salesy), ONE sentence per line, '
         'about what it is, its main features and who it suits. Every line must end with its web citation. Use only facts from pages about this exact '
         'model; never use pages about a different generation/variant (e.g. "Pro 2" is not "Pro"). Never mention prices, sellers, shops, warranty, '
         'delivery or discounts. Do not state a colour, size or capacity unless the product title has it. {ACC} If you cannot confirm the exact product on the web, output exactly: NONE')

def _accessory(title, cat):
    t = (title or '') + ' ' + (cat or '')
    return bool(ACC_DB.search(title or '')) and not re.match(r'\s*(گوشی|ساعت هوشمند|لپ ?تاپ|تلویزیون|هدفون|دوربین)\b', title or '')

def about_web(pid, client_fn, cost_fn, add_spend):
    import about_sources as S
    h = D.product_head(pid)
    if not h:
        return None
    t0 = time.time()
    acc = _accessory(h['title'], h['category'])
    accline = ('IMPORTANT: this item is an ACCESSORY (e.g. a screen protector, case or strap) — describe it as that accessory and which device it fits; '
               'never describe the device itself as the item.' if acc else
               'This item is the device itself (not an accessory): describe the device; ignore pages that sell accessories for it.')
    brand = '' if h['brand'] in (None, '', D.UNKNOWN, 'نامشخص') else h['brand']
    user = (f"Product (from our database): {h['title']}\nBrand: {brand or '-'}\nModel: {h.get('model') or '-'}\nCategory: {h['category']}\n"
            f"Search in English and Persian if useful.")
    res = {'product_id': pid, 'query': (h['title'] or '').split('|')[0].strip(), 'sentences': [], 'cited': [], 'sources': [], 'status': 'empty',
           'llm_calls': 0, 'cost_usd': 0.0, 'version': 3, 'engine': 'boxapi_web_search', 'is_accessory': acc}
    r = client_fn().responses.create(model=MODEL, instructions=_WSYS.replace('{ACC}', accline), input=user, tools=[{'type': 'web_search'}],
                                     reasoning={'effort': 'low'}, max_output_tokens=900, timeout=40)
    d = r.model_dump()
    c = float((d.get('usage') or {}).get('cost') or 0); add_spend(c)
    res['llm_calls'], res['cost_usd'] = 1, round(c, 6)
    msg = next((o for o in d.get('output', []) if o.get('type') == 'message'), None)
    part = next((x for x in (msg or {}).get('content', []) if x.get('type') == 'output_text'), None) if msg else None
    res['searches'] = [((o.get('action') or {}).get('query')) for o in d.get('output', []) if o.get('type') == 'web_search_call']
    txt = (part or {}).get('text') or ''
    anns = [a for a in (part or {}).get('annotations') or [] if a.get('type') == 'url_citation' and str(a.get('url', '')).startswith('http')]
    if not txt.strip() or txt.strip().upper().startswith('NONE'):
        res['status'] = 'model_unsure'
    else:
        urls, cited, pos = [], [], 0
        for line in txt.split('\n'):
            st, en = pos, pos + len(line); pos = en + 1
            if not line.strip():
                continue
            la = [a for a in anns if a['start_index'] < en + 1 and a['end_index'] > st]
            clean = re.sub(r'\s*\(\[[^\]]*\]\([^)]*\)\)|\[[^\]]*\]\(https?://[^)]*\)|https?://\S+', '', line)
            clean = re.sub(r'^[\s\-•*\d.]+', '', clean).strip().rstrip('،, ')
            if not la or len(clean) < 12 or _BAD.search(clean) or re.search(r'^(source|منبع|منابع)', clean, re.I):
                continue
            if not acc and ACC_CLAIM.search(clean):          # contradicts the DB: the DB item is the device itself
                res['status'] = 'contradicts_db_type'; cited = []; break
            refs = []
            for a in la:
                u = a['url'].split('?utm_')[0]
                if u not in urls:
                    urls.append(u); res['sources'].append({'n': len(urls), 'title': (a.get('title') or '')[:90], 'url': u, 'engine': 'boxapi_web_search'})
                refs.append(urls.index(u) + 1)
            cited.append({'text': clean, 'refs': sorted(set(refs))})
        if res['status'] == 'contradicts_db_type':
            res['sources'] = []
        elif len(cited) < 2:
            res['status'] = 'model_output_rejected'; res['sources'] = []
        else:
            idn = S.identity(h['title'], h['brand'])
            core = [t for t in idn['ident'] if t not in S.SOFT]
            blob = S.nkey(' '.join(x['title'] + ' ' + urllib.parse.unquote(x['url']) for x in res['sources']))
            if core and not any(S.nkey(t) in blob for t in core):    # no cited page names this model -> not confirmed
                res['status'] = 'model_not_in_sources'; res['sources'] = []
            elif acc and not any(ACC_CLAIM.search(x['text']) or ACC_DB.search(x['text']) for x in cited):
                res['status'] = 'accessory_not_described'; res['sources'] = []
            else:
                res.update(sentences=[x['text'] for x in cited[:4]], cited=cited[:4], status='ok')
    res['raw_text'] = txt[:1500]
    res['elapsed_s'] = round(time.time() - t0, 1)
    return res

def about(pid, client_fn, cost_fn, add_spend, force=False):
    """v3: BoxAPI web search (one Responses call). Falls back to the v2 Digikala path only if the web-search call itself fails."""
    pid = pid[:64]
    cp = os.path.join(CACHE_V3, re.sub(r'[^a-z0-9_]', '', pid) + '.json')
    if os.path.exists(cp) and not force:
        d = json.load(open(cp)); d['cached'] = True; return d
    try:
        res = about_web(pid, client_fn, cost_fn, add_spend)
    except Exception as e:
        err = f'{type(e).__name__}: {str(e)[:120]}'
        res = about_dk(pid, client_fn, cost_fn, add_spend, force=True)
        if res is not None:
            res['web_search_error'] = err
        return res
    if res is not None:
        json.dump(res, open(cp, 'w'), ensure_ascii=False)
    return res

def details(pid):
    h = D.product_head(pid)
    if not h:
        return None
    r = D.q('SELECT image_urls, specs FROM products WHERE product_id=?', (pid,))[0]
    try: imgs = json.loads(r[0]) if r[0] else []
    except Exception: imgs = []
    rows = D.q('SELECT section,key,value FROM product_specs WHERE product_id=?', (pid,))
    if not rows and r[1]:
        try: rows = [(x.get('section'), x.get('key'), x.get('value')) for x in json.loads(r[1])]
        except Exception: rows = []
    secs = {}
    for sec, k, v in rows:
        if k and v not in (None, ''):
            secs.setdefault(sec or 'مشخصات', []).append({'key': k, 'value': str(v)})
    po = D.product_offers(pid) or {}
    stats = {k: po.get(k) for k in ('n_offers', 'n_shops', 'n_priced', 'min_price', 'min_fresh_price', 'median_price', 'n_stale', 'n_suspicious')}
    prices = [o['price_toman'] for o in po.get('offers', []) if o['price_toman']]
    stats['max_price'] = max(prices) if prices else None
    dates = [o['date'] for o in po.get('offers', []) if o.get('date')]
    stats['latest_price_change_fa'] = D.jalali(max(dates)) if dates else D.UNKNOWN
    return dict(h, images=[u for u in imgs if isinstance(u, str)][:12], specs=[{'section': s, 'items': it} for s, it in secs.items()],
                n_specs=sum(len(x) for x in secs.values()), stats=stats, llm_calls=0)
