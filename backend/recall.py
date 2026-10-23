"""Recall-hardening layer for search_products.
 1) alias / transliteration / script normalisation + glued-token splitting + fuzzy vocab correction  -> query variants
 2) LLM query expansion (gpt-6-luna, 1 cheap call, cached)
 3) embedding retrieval over cached product embeddings (text-embedding-3-small, 256-d)
 4) LLM match-grader (decider): keep true matches, drop accessories/knockoffs/other models, report confidence
Results of all retrievers are fused with weighted reciprocal-rank fusion."""
import difflib, json, os, re, threading
from build_eval_db import norm
import tools

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.path.join(HERE, 'llm_cache.json')
ENABLE = {k: os.environ.get(f'TOROB_{k.upper()}', '1') == '1' for k in ('alias', 'llm_expand', 'embed', 'grader')}
STATS = {'llm_calls': 0, 'embed_calls': 0, 'cost': 0.0, 'prompt_tokens': 0, 'completion_tokens': 0}
_lock = threading.Lock()

# ---------------------------------------------------------------- 1. lexical variants
ALIAS_GROUPS = [
    (['آیفون', 'ایفون', 'iphone', 'اپل', 'apple'], ['آیفون', 'iphone', 'اپل']),
    (['گلکسی', 'galaxy', 'samsung', 'سامسونگ'], ['سامسونگ', 'galaxy']),
    (['شیائومی', 'شیامی', 'شیاومی', 'xiaomi', 'mi'], ['شیائومی', 'xiaomi']),
    (['پرو', 'pro'], ['pro', 'پرو']), (['مکس', 'max'], ['max', 'مکس']), (['اولترا', 'ultra'], ['ultra', 'اولترا']),
    (['پلاس', 'plus'], ['plus', 'پلاس']), (['لایت', 'lite'], ['lite', 'لایت']), (['اسلیم', 'slim'], ['slim']),
    (['ردمی', 'redmi'], ['redmi']), (['نوت', 'note'], ['note']), (['پوکو', 'poco'], ['poco']), (['واچ', 'watch'], ['watch', 'واچ']),
    (['سری', 'series'], ['series', 'سری']), (['دیجیتال', 'digital'], ['digital']),
]
PHRASES = [  # regex on normalised query -> replacement
    (r'پلی ?استیشن ?(\d)', r'ps\1'), (r'پلی ?استیشن', 'ps5'), (r'playstation ?(\d)', r'ps\1'), (r'(ا|ای)کس ?باکس', 'xbox'),
    (r'ایر ?پاد(ز|س)?', 'ایرپاد'), (r'air ?pods?', 'airpods'), (r'مک ?بوک', 'مک بوک'), (r'جی ?بی ?ال', 'jbl'),
    (r'هارمن ?کارد(و|ا)?ن', 'هارمن کاردن'), (r'\bاورا\b', 'aura'), (r'استودیو', 'studio'), (r'فلیپ', 'flip'), (r'کلیپ', 'clip'),
    (r'پارتی ?باکس', 'partybox'), (r'ساندکور', 'soundcore'), (r'لیبرتی', 'liberty'), (r'اسپیکر', 'اسپیکر'),
]
LETTERS = {'اس': 's', 'اف': 'f', 'ای': 'e', 'ام': 'm', 'ایکس': 'x', 'اکس': 'x', 'جی': 'g', 'پی': 'p', 'تی': 't', 'وی': 'v',
           'سی': 'c', 'دی': 'd', 'بی': 'b', 'ال': 'l', 'کیو': 'q', 'آر': 'r', 'یو': 'u', 'اچ': 'h', 'کی': 'k', 'ان': 'n', 'زد': 'z'}
_vocab, _vocab_by_key = None, {}


def _fold(w):
    return w.replace('آ', 'ا').replace('أ', 'ا')


def _load_vocab():
    global _vocab
    if _vocab is None:
        c = tools.con
        c.execute("CREATE VIRTUAL TABLE IF NOT EXISTS temp.fts_vocab USING fts5vocab(main, products_fts, 'row')")
        _vocab = {t: d for t, d in c.execute('SELECT term, doc FROM temp.fts_vocab WHERE doc >= 2')}
        for t, d in _vocab.items():
            _vocab_by_key.setdefault((_fold(t)[:1], len(t)), []).append(t)
    return _vocab


def _known(w):
    return w.isdigit() or w in _load_vocab()


def _correct(tok):
    """fuzzy-correct / split an unknown token against the catalogue vocabulary"""
    v = _load_vocab()
    if len(tok) >= 5 and not tok.isdigit() and v.get(tok, 0) < 10:   # rare glued pair, e.g. پرومکس -> پرو مکس
        for i in range(2, len(tok) - 1):
            if v.get(tok[:i], 0) >= 50 and v.get(tok[i:], 0) >= 50:
                return f'{tok[:i]} {tok[i:]}'
    if _known(tok) or len(tok) < 3:
        return tok
    f = _fold(tok)
    exact = [t for t in _vocab_by_key.get((f[:1], len(tok)), []) if _fold(t) == f]
    if exact:
        return max(exact, key=lambda t: v[t])
    for i in range(2, len(tok) - 1):          # glued pair, e.g. پرومکس -> پرو مکس
        a, b = tok[:i], tok[i:]
        if v.get(a, 0) >= 20 and v.get(b, 0) >= 20:
            return f'{a} {b}'
    pool = []
    for L in range(len(tok) - 2, len(tok) + 3):
        pool += _vocab_by_key.get((f[:1], L), [])
    pool = [t for t in pool if v[t] >= 3]
    best = difflib.get_close_matches(f, [_fold(t) for t in pool], n=3, cutoff=0.75)
    if best:
        cands = [t for t in pool if _fold(t) in best]
        return max(cands, key=lambda t: (difflib.SequenceMatcher(None, f, _fold(t)).ratio(), v[t]))
    return tok


def _letters_to_latin(toks, aggressive):
    out, cur = [], ''
    for t in toks + ['']:
        if t in LETTERS:
            if cur and cur[-1].isdigit():
                out.append(cur); cur = ''
            cur += LETTERS[t]
        elif t.isdigit() and cur:
            cur += t
        else:
            if cur:
                if aggressive or len(cur) > 1:
                    out.append(cur)
                else:
                    out.append(next(k for k, v in LETTERS.items() if v == cur))
                cur = ''
            if t:
                out.append(t)
    return out


def variants(query):
    q = norm(query or '')
    q = re.sub(r'(\d)([^\d\s.,/x×])', r'\1 \2', q)
    q = re.sub(r'([^\d\s.,/a-z])(\d)', r'\1 \2', q)
    for pat, rep in PHRASES:
        q = re.sub(pat, rep, q)
    toks = q.split()
    toks = ' '.join(_correct(t) for t in toks).split()
    base = [' '.join(toks)]
    for aggressive in (False, True):
        lt = ' '.join(_letters_to_latin(toks, aggressive))
        if lt not in base:
            base.append(lt)
    out = list(base)
    for b in base:                               # brand / variant-word swaps
        bt = b.split()
        for i, t in enumerate(bt):
            for members, targets in ALIAS_GROUPS:
                if t in members:
                    for tg in targets:
                        if tg != t:
                            v = ' '.join(bt[:i] + [tg] + bt[i + 1:])
                            if v not in out:
                                out.append(v)
    v = _load_vocab()
    for b in list(out):                          # split glued compounds that are themselves in the vocab (پرومکس -> پرو مکس)
        bt, changed = [], False
        for t in b.split():
            sp = next((f'{t[:i]} {t[i:]}' for i in range(2, len(t) - 1) if len(t) >= 5 and not t.isdigit()
                       and v.get(t[:i], 0) >= 300 and v.get(t[i:], 0) >= 300), None)
            bt.append(sp or t); changed |= bool(sp)
        if changed and ' '.join(bt) not in out:
            out.append(' '.join(bt))
    orig = norm(query or '')
    if orig not in out:
        out.insert(0, orig)
    return out[:10]


# ---------------------------------------------------------------- LLM helpers (cached)
_cache = None


def _cache_get(k):
    global _cache
    if _cache is None:
        _cache = json.load(open(CACHE_PATH, encoding='utf-8')) if os.path.exists(CACHE_PATH) else {}
    return _cache.get(k)


def _cache_put(k, v):
    with _lock:
        _cache[k] = v
        json.dump(_cache, open(CACHE_PATH, 'w', encoding='utf-8'), ensure_ascii=False)


def _account(u):
    STATS['prompt_tokens'] += getattr(u, 'prompt_tokens', 0) or 0
    STATS['completion_tokens'] += getattr(u, 'completion_tokens', 0) or 0
    STATS['cost'] += float((getattr(u, 'model_extra', None) or {}).get('cost', 0) or 0)


def _chat_json(prompt, max_tokens=250):
    from agent import client, MODEL
    r = client().chat.completions.create(model=MODEL, messages=[{'role': 'user', 'content': prompt}], max_completion_tokens=max_tokens,
                                         reasoning_effort='none', response_format={'type': 'json_object'})
    STATS['llm_calls'] += 1
    _account(r.usage)
    try:
        return json.loads(r.choices[0].message.content or '{}')
    except Exception:
        m = re.search(r'\{.*\}', r.choices[0].message.content or '', re.S)
        return json.loads(m.group(0)) if m else {}


EXPAND_PROMPT = """You rewrite a shopper's (possibly misspelled, Persian/English-mixed) product query into search strings for a Persian product catalogue (Torob, Iran). Titles look like "گوشی آیفون 17 | حافظه 256 گیگابایت", "گوشی سامسونگ S25 FE 5G", "کنسول بازی سونی PS5 Slim Digital", "اسپیکر بلوتوثی جی بی ال مدل Flip 7".
Return JSON {"queries": [3-5 short strings]}: fix misspellings, give the official Latin model name, a Persian form, and a form with and without the brand word. Do not add storage/colour unless given. Query: """


def llm_expand(query):
    k = 'expand::' + query
    hit = _cache_get(k)
    if hit is not None:
        return hit
    try:
        res = _chat_json(EXPAND_PROMPT + json.dumps(query, ensure_ascii=False)).get('queries', [])[:5]
    except Exception:
        res = []
    res = [str(x) for x in res if isinstance(x, str)]
    _cache_put(k, res)
    return res


GRADE_PROMPT = """A shopper searched a Persian product catalogue. Decide which candidates are TRULY the product the shopper asked for.
Rules: storage/colour/region/active-not-active variants of the requested model MATCH. A different model/generation (e.g. 16 vs 17, Pro vs Pro Max, S26 vs S27), accessories/parts (قاب, گلس, باتری, کابل, شارژر, تاچ, single earbud) and "طرح"/replica items do NOT match - unless the shopper asked for that accessory. If the query is a generic category/brand browse (e.g. "گوشی سامسونگ", "ساعت هوشمند شیائومی"), every genuine item of that type/brand matches.
Return JSON {"match": [candidate numbers], "confidence": "high"|"medium"|"low", "clarify": "short Persian clarifying question if the request is ambiguous or nothing matches, else empty"}.
Query: %s
Candidates:
%s"""


def grade(query, results):
    lines = '\n'.join(f"{i}. {r['title']} [{r.get('category')}]" + (f" flags={r['flags']}" if r.get('flags') else '') for i, r in enumerate(results))
    k = 'grade::' + query + '::' + '|'.join(r['product_id'] for r in results)
    hit = _cache_get(k)
    if hit is None:
        try:
            hit = _chat_json(GRADE_PROMPT % (json.dumps(query, ensure_ascii=False), lines), max_tokens=200)
        except Exception:
            hit = {}
        _cache_put(k, hit)
    return hit


# ---------------------------------------------------------------- 3. embeddings
_emb, _emb_ids = None, None


def _load_emb():
    global _emb, _emb_ids
    if _emb is None:
        import numpy as np
        p = os.path.join(HERE, 'product_emb.f16.npy')
        if not os.path.exists(p):
            return None, None
        _emb = np.load(p).astype('float32')
        _emb_ids = json.load(open(os.path.join(HERE, 'product_emb_ids.json')))
    return _emb, _emb_ids


def embed_search(query, k=40):
    import numpy as np
    M, ids = _load_emb()
    if M is None:
        return []
    ck = 'emb::' + query
    vec = _cache_get(ck)
    if vec is None:
        from agent import client
        r = client().embeddings.create(model='text-embedding-3-small', input=[query], dimensions=256)
        STATS['embed_calls'] += 1
        _account(r.usage)
        vec = r.data[0].embedding
        _cache_put(ck, vec)
    v = np.array(vec, dtype='float32')
    v /= np.linalg.norm(v) + 1e-8
    sims = M @ v
    top = np.argpartition(-sims, k)[:k]
    top = top[np.argsort(-sims[top])]
    return [(ids[i], float(sims[i])) for i in top]


# ---------------------------------------------------------------- fusion
BRAND_ALIASES = [
    ['ایکس باکس', 'xbox', 'مایکروسافت', 'microsoft'], ['سونی', 'sony', 'playstation', 'ps5', 'ps4', 'پلی استیشن'],
    ['اپل', 'apple', 'آیفون', 'ایفون', 'iphone', 'ایرپاد', 'airpods', 'مک بوک', 'macbook'], ['سامسونگ', 'samsung', 'گلکسی', 'galaxy'],
    ['شیائومی', 'xiaomi', 'ردمی', 'redmi', 'poco', 'پوکو', 'می'], ['جی بی ال', 'jbl'], ['هارمن کاردن', 'harman', 'هارمن'],
    ['انکر', 'anker', 'ساندکور', 'soundcore'], ['هواوی', 'huawei'], ['ال جی', 'lg'], ['سایلکس', 'silex'],
]


def _brand_ok(r, brand):
    b = norm(brand)
    names = {b}
    for g in BRAND_ALIASES:
        if b in g or any(x in b for x in g if len(x) > 2):
            names |= set(g)
    txt = norm((r.get('brand') or '') + ' ' + (r.get('title') or '')).replace('\u200c', ' ')
    return any(n in txt for n in names if len(n) > 1)


def _passes_filters(r, brand, category, min_price, max_price):
    if brand and norm(brand) not in norm(r.get('brand') or '') and norm(brand) not in norm(r.get('title') or ''):
        return False
    if category:
        allowed = tools.resolved_category_names(category)
        if allowed is not None:
            if r.get('category') not in allowed:
                return False
        elif not any(t in norm(r.get('category') or '') for t in norm(category).split()):
            return False
    if (min_price is not None or max_price is not None):
        lo, hi = float(min_price or 0), float(max_price or 1e12)
        n = tools.con.execute('SELECT 1 FROM offers WHERE product_id=? AND price_toman BETWEEN ? AND ? LIMIT 1', (r['product_id'], lo, hi)).fetchone()
        if not n:
            return False
    return True


def retrieve(query, brand=None, category=None, min_price=None, max_price=None, pool=30, layers=None):
    """returns fused list of result dicts (no grading) + debug info"""
    layers = layers or ENABLE
    lists, dbg = [], {}
    filt = dict(brand=brand, category=category, min_price=min_price, max_price=max_price)
    vs = variants(query) if layers.get('alias') else [query]
    dbg['variants'] = vs
    for i, v in enumerate(vs):
        r = tools.search_products_lexical(v, limit=pool, _max_limit=pool, **filt)['results']
        lists.append((1.0 if i == 0 else 0.9, r))
    if brand:   # brand names are spelled many ways (ایکس‌باکس / xbox / مایکروسافت): also search without the hard brand filter
        nb = dict(filt, brand=None)
        for i, v in enumerate(vs[:4]):
            lists.append((0.7, tools.search_products_lexical(v, limit=pool, _max_limit=pool, **nb)['results']))
    if layers.get('llm_expand'):
        ex = llm_expand(query)
        dbg['llm_expansions'] = ex
        for v in ex:
            lists.append((0.8, tools.search_products_lexical(v, limit=pool, _max_limit=pool, **dict(filt, brand=None))['results']))
    if layers.get('embed'):
        hits = embed_search(query)
        rows = []
        for pid, sim in hits:
            d = tools.describe_product(pid, query)
            if d and _passes_filters(d, **dict(filt, brand=None)):
                d['semantic_similarity'] = round(sim, 3)
                rows.append(d)
        dbg['embedding_hits'] = len(rows)
        lists.append((0.8, rows))
    fused, rowmap = {}, {}
    for w, rows in lists:
        for rank, r in enumerate(rows):
            pid = r['product_id']
            pen = 0.5 if any(f.startswith(('ACCESSORY', 'KNOCKOFF')) for f in r.get('flags', [])) else 1.0
            fused[pid] = fused.get(pid, 0) + w * pen / (20 + rank)
            if pid not in rowmap or ('PARTIAL' in json.dumps(rowmap[pid].get('flags', [])) and 'PARTIAL' not in json.dumps(r.get('flags', []))):
                rowmap[pid] = r
    if brand:   # soft brand preference
        for p in fused:
            fused[p] *= 1.3 if _brand_ok(rowmap[p], brand) else 0.6
    order = sorted(fused, key=lambda p: -fused[p])
    return [rowmap[p] for p in order], dbg


def search_products_hybrid(query, brand=None, category=None, min_price=None, max_price=None, limit=10, layers=None):
    layers = layers or ENABLE
    limit = max(1, min(int(limit or 10), 15))
    fused, dbg = retrieve(query, brand, category, min_price, max_price, layers=layers)
    # collapse identical titles
    out, seen = [], {}
    for r in fused:
        k = norm(r['title'] or '')
        if k in seen:
            seen[k].setdefault('same_title_other_product_ids', []).append(r['product_id'])
            continue
        r = dict(r); seen[k] = r; out.append(r)
    top = out[:max(limit, 15)]
    res = {'query': query, 'filters': {k: v for k, v in dict(brand=brand, category=category, min_price=min_price, max_price=max_price).items() if v is not None},
           'retrieval': {k: v for k, v in dbg.items()}}
    if layers.get('grader') and top:
        g = grade(query, top)
        match = [i for i in g.get('match', []) if isinstance(i, int) and 0 <= i < len(top)]
        kept = [top[i] for i in match]
        for r in kept:
            r['grader'] = 'MATCH'
            if r.get('flags'):
                r['flags'] = [f for f in r['flags'] if not f.startswith('PARTIAL_MATCH')] or None
                if not r['flags']:
                    r.pop('flags')
        dropped = [r for i, r in enumerate(top) if i not in match]
        res['match_confidence'] = g.get('confidence', 'unknown')
        if g.get('clarify'):
            res['suggested_clarifying_question'] = g['clarify']
        if kept:
            res['results'] = kept[:limit]
            res['not_matching_request (do not present as the requested item)'] = [{'product_id': r['product_id'], 'title': r['title'], 'min_price': r.get('min_price')} for r in dropped[:5]]
        else:
            res['results'] = []
            res['closest_non_matching_alternatives'] = [{'product_id': r['product_id'], 'title': r['title'], 'min_price': r.get('min_price'), 'n_shops': r.get('n_shops')} for r in dropped[:5]]
            res['note'] = 'NO EXACT MATCH – the requested item does not appear in the dataset; alternatives listed are different products'
        if res['match_confidence'] == 'low' and kept:
            res['note'] = 'LOW CONFIDENCE match – consider asking the user a clarifying question'
    else:
        res['results'] = top[:limit]
    for r in res['results']:
        if 'same_title_other_product_ids' in r:
            r['note'] = 'other catalogue entries share this exact title; pass all ids to store tools'
    res['n_results'] = len(res['results'])
    return res
