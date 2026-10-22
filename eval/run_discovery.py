"""Run + score discovery/browsing tests. usage: python run_discovery.py --tag d1 [--only D01,D02] [--rescore d1]"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "..", "backend", "app", "engine")))
import argparse, json, re, sys, time
from run_eval import numbers, has_price, rx, ungrounded, CLARIFY
from tools import norm, con
import recall

TESTS = json.load(open('discovery_tests.json'))['tests']
SHOPS = {sid: re.sub(r'\s+', '', norm(nm)) for sid, nm in con.execute('SELECT shop_id, name FROM shops') if nm and len(re.sub(r'\s+', '', nm)) >= 6}
BRAND_AL = {'لنوو': ['لنوو', 'lenovo'], 'ایسوس': ['ایسوس', 'asus'], 'اچ‌پی': ['اچ‌پی', 'اچ پی', 'hp'], 'ام اس آی': ['ام اس آی', 'msi'],
            'اپل': ['اپل', 'apple', 'مک بوک', 'macbook'], 'دل': [' دل ', 'dell', '«دل»', 'دل،', '**دل**'], 'ایسر': ['ایسر', 'acer'],
            'مایکروسافت': ['مایکروسافت', 'microsoft', 'surface'], 'سامسونگ': ['سامسونگ', 'samsung'], 'سونی': ['سونی', 'sony']}
NEG = r'(ندار|نیست|پیدا نشد|ثبت نشده|موجود نیست)'


def option_lines(a):
    return [l for l in a.splitlines() if re.match(r'\s*([-*•]|\d+[.)\-]|[۰-۹]+[.)\-])\s+', l)]


def latin_tokens_missing(rec):
    blob = re.sub(r'\s+', '', ' '.join(c['result'] for c in rec['tool_calls']).lower())
    toks = set(re.findall(r'[A-Za-z][A-Za-z0-9\-]*\d[A-Za-z0-9\-]*|\b\d+[A-Za-z]{2,}[A-Za-z0-9]*', rec['final_answer']))
    return sorted(t for t in toks if re.sub(r'\s+', '', t.lower()) not in blob and t.lower() not in ('5g', '4g', '3g'))


GENERIC = {'watch', 'ultra', 'mini', 'plus', 'lite', 'pro', 'max', 'black', 'white', 'blue', 'gray', 'silver', 'gold', 'green', 'edition',
           'digital', 'standard', 'wireless', 'bluetooth', 'gaming', 'smart', 'active', 'series', 'slim', 'apple', 'samsung', 'xiaomi', 'redmi',
           'sony', 'anker', 'soundcore', 'galaxy', 'iphone', 'with', 'version', 'global', 'note', 'buds', 'band', 'speaker', 'headphone', 'case', 'amoled', 'air', 'ram', 'ssd', 'gb', 'tws', 'anc', 'for', 'and', 'the', 'new', 'led', 'usb', 'oled', 'qled', 'smart'}


def _titles(obj, acc):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == 'title' and isinstance(v, str):
                acc.add(v)
            else:
                _titles(v, acc)
    elif isinstance(obj, list):
        for v in obj:
            _titles(v, acc)
    return acc


def products_mentioned(rec):
    # distinct catalogue products whose model code (latin/digit token) appears in the answer
    acc = set()
    for c in rec['tool_calls']:
        try:
            _titles(json.loads(c['result']), acc)
        except Exception:
            pass
    ak = re.sub(r'\s+', '', norm(rec['final_answer']).lower())
    groups = set()
    for t in acc:
        toks = {x for x in re.findall(r'[a-z0-9\-+]+', norm(t).lower())
                if ((re.search(r'\d', x) and len(x) >= 2) or (x.isalpha() and len(x) >= 3 and x not in GENERIC))
                and x not in ('5g', '4g', '2023', '2024', '2025', '2026')}
        hit = frozenset(x for x in toks if x in ak)
        if hit:
            groups.add(hit)
    # collapse groups that are subsets of others
    g = [x for x in groups if not any(x < y for y in groups)]
    return len(g)


def option_products(a):
    # bulleted lines carrying a price whose head (text before — / : / ؛) is a product, not a shop name
    n, priced = 0, 0
    for l in option_lines(a):
        if not [v for v in numbers(l) if v >= 100000]:
            continue
        priced += 1
        head = re.split(r'[—:؛–]| - ', re.sub(r'^\s*([-*•]|\d+[.)\-]|[۰-۹]+[.)\-])\s+', '', l))[0]
        hk = re.sub(r'\s+', '', norm(head.replace('*', '')))
        if hk and not any(n_ == hk or (len(hk) >= 6 and n_ in hk and len(hk) < len(n_) + 4) for n_ in SHOPS.values()):
            n += 1
    return n if n else min(priced, 1)


def shops_named(a):
    k = re.sub(r'\s+', '', norm(a))
    return {sid for sid, n in SHOPS.items() if n in k}


def score(t, rec):
    a, q = rec['final_answer'], t['question']
    g, why = t['ground_truth'], []
    ung = ungrounded(rec, q)
    lat = latin_tokens_missing(rec)
    opts = option_lines(a)
    nq = a.count('؟') + a.count('?')
    clar = nq >= 1 and bool(rx(a, CLARIFY))
    prices = [v for v in numbers(a) if v >= 100000 and not any(abs(v - x) <= 0.02 * x for x in numbers(q))]
    hard = []
    if ung: hard.append(f'ungrounded numbers {ung[:3]}')
    if lat: hard.append(f'model tokens not in tool output {lat[:4]}')
    if len(opts) > 12: hard.append(f'overlong list ({len(opts)} lines)')
    if nq > 3: hard.append(f'{nq} questions (should ask ONE)')
    if prices and not rec['tool_calls']: hard.append('prices without any tool call')
    knock_lines = [l for l in a.splitlines() if 'طرح' in l and not re.search(r'(تقلبی|اصل نیست|اورجینال نیست|کپی|غیراصل|نیستند|نیست)', l)]
    if knock_lines: hard.append('recommends a "طرح" knock-off')
    ok = False
    m, i = t['mode'], t['id']
    n_opt = option_products(a)
    if i == 'D04':
        found = [b for b, al in BRAND_AL.items() if any(x.lower() in f' {a.lower()} ' for x in al)]
        absent = [b for b in g['absent_brands'] if b.lower() in a.lower() and not re.search(re.escape(b) + r'[^\n]{0,40}' + NEG, a, re.I)]
        ok = len(found) >= 5 and not absent
        why.append(f'brands named={len(found)} {found[:6]}, absent brands claimed={absent}')
    elif i == 'D05':
        fam = sum(bool(re.search(p, a, re.I)) for p in (r'ps5|پلی ?استیشن ?(۵|5)', r'xbox|ایکس ?باکس', r'ps4|پلی ?استیشن ?(۴|4)', r'nintendo|نینتندو'))
        ok = fam >= 2 and len(prices) >= 1
        why.append(f'console families={fam}, prices={len(prices)}')
    elif i in ('D06', 'D13'):
        c3 = g['cheapest5'][:3] + g.get('cheapest5_smartphones', [])[:3]
        hit = [r['title'][:30] for r in c3 if has_price(a, r['plausible_min']) or any(has_price(a, x) for x in [con.execute('SELECT min_price FROM product_stats WHERE product_id=?', (r['product_id'],)).fetchone()[0]] if x)]
        ok = bool(hit)
        why.append(f'cheapest-3 present={hit}')
    elif m.startswith('store_list'):
        named = shops_named(a)
        gt = set(g['shop_ids'])
        good, bad = named & gt, named - gt
        need = 1 if m == 'store_list_strict' else 2
        ok = (len(good) >= need and len(named) <= 12 and (not bad if m == 'store_list_strict' else len(bad) <= len(good) // 2)) or (clar and m != 'store_list_strict' and not named)
        if i == 'D09':
            prov = sum(p in a for p in g['providers'])
            ok = ok and (prov >= 1 or clar)
            why.append(f'providers mentioned={prov}')
        why.append(f'shops named: {len(good)} correct, {len(bad)} outside GT, clarify={clar}')
    else:   # shortlist_or_clarify (vague / budget / similar_cheaper)
        b = t.get('budget_toman')
        over = [v for v in prices if b and v > b * 1.02] if i != 'D10' else []
        if i == 'D10':
            under = [v for v in prices if v < b]
            ok = (len(set(under)) >= 2 and n_opt >= 2) or clar
            why.append(f'products={n_opt}, prices cheaper than AirPods ({int(b):,})={len(set(under))}, clarify={clar}')
        else:
            short = 2 <= n_opt <= (5 if i == 'D15' else 10) and len(prices) >= 2
            ok = (short or clar) and not over
            why.append(f'options={n_opt}, prices={len(prices)}, over_budget={over[:3]}, clarify={clar}')
    if hard:
        ok = False
    return ok, '; '.join(hard + why)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--tag', default='d1'); ap.add_argument('--only'); ap.add_argument('--rescore')
    A = ap.parse_args()
    tests = [t for t in TESTS if not A.only or t['id'] in A.only.split(',')]
    if A.rescore:
        recs = json.load(open(f'discovery/{A.rescore}_raw.json')); tag = A.rescore
    else:
        from agent import run_agent
        recs, tag = {}, A.tag
        for t in tests:
            t0 = time.time()
            r = run_agent(t['question'])
            recs[t['id']] = {'final_answer': r['final_answer'], 'tool_calls': [{'name': c['name'], 'args': c['args'], 'result': c['result'] if isinstance(c['result'], str) else json.dumps(c['result'], ensure_ascii=False)} for c in r['tool_calls']], 'usage': r['usage']}
            print(f"[{t['id']}] {time.time()-t0:.1f}s tools={[c['name'] for c in r['tool_calls']]} cost=${r['usage']['cost']:.4f}", flush=True)
        json.dump(recs, open(f'discovery/{tag}_raw.json', 'w'), ensure_ascii=False, indent=1)
    out = []
    for t in tests:
        if t['id'] not in recs:
            continue
        ok, why = score(t, recs[t['id']])
        out.append({'id': t['id'], 'kind': t['kind'], 'question': t['question'], 'pass': ok, 'reason': why,
                    'tools': [c['name'] for c in recs[t['id']]['tool_calls']], 'final_answer': recs[t['id']]['final_answer']})
        print(('PASS' if ok else 'FAIL'), t['id'], '—', why)
    agent_cost = sum(r['usage']['cost'] for k, r in recs.items() if any(o['id'] == k for o in out))
    summ = {'n': len(out), 'passed': sum(o['pass'] for o in out), 'agent_cost_usd': round(agent_cost, 4), 'recall_layer_stats': recall.STATS}
    json.dump({'tag': tag, 'summary': summ, 'items': out}, open(f'discovery/{tag}_scored.json', 'w'), ensure_ascii=False, indent=1)
    print(json.dumps(summ, ensure_ascii=False))


if __name__ == '__main__':
    main()
