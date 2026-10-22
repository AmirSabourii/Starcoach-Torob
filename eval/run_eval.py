#!/usr/bin/env python3
"""Run the agent over eval_set.json and score objectively against SQL ground truth.
  python run_eval.py --tag run1            # call model for all 60 items, then score
  python run_eval.py --rescore run1        # re-score saved answers (no API calls)
  python run_eval.py --tag dbg --only L01,A02
"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "..", "backend", "app", "engine")))
import argparse, json, os, re, statistics, time
from build_eval_db import norm
from gt_lib import shop_offers

HERE = os.path.dirname(os.path.abspath(__file__))
RUNS = os.path.join(HERE, 'runs')

# ---------------------------------------------------------------- text helpers
def _n(s):
    s = (s or '').translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩٬٫', '01234567890123456789,.'))
    return s.replace('\u200c', ' ')


def numbers(text):
    t = _n(text)
    vals = []
    for a, b in re.findall(r'(\d+(?:\.\d+)?)\s*میلیون\s*و\s*(\d+(?:\.\d+)?)\s*هزار', t):
        vals.append(float(a) * 1e6 + float(b) * 1e3)
    for a, u in re.findall(r'(\d+(?:\.\d+)?)\s*(میلیارد|میلیون|هزار|M\b)', t):
        vals.append(float(a) * {'میلیارد': 1e9, 'میلیون': 1e6, 'هزار': 1e3, 'M': 1e6}[u])
    for m in re.findall(r'\d{1,3}(?:[,]\d{3})+|\d{1,3}(?:\.\d{3}){2,}|\d{4,}', t):
        vals.append(float(m.replace(',', '').replace('.', '')))
    return vals


def has_price(text, target, tol=0.012):
    if not target:
        return False
    return any(abs(v - target) / target <= tol for v in numbers(text))


def key(s):
    return re.sub(r'\s+', '', norm(_n(s or '')).replace('ء', ''))


def has_name(text, name):
    return bool(name) and key(name) in key(text)


def rx(text, pat):
    return re.search(pat, _n(text)) is not None


REFUSE = r'(موجود نیست|وجود ندارد|ندارم|نداریم|در (داده|دیتاست|اطلاعات|کاتالوگ)|ثبت نشده|در دسترس نیست|نمی\s?توانم|نمیتونم|پیدا نکردم|یافت نشد|خارج از|اطلاعاتی|نیست)'
CLARIFY = r'(کدام|کدوم|چه مدلی|چه نوع|منظورتان|منظورتون|بودجه|مشخص کنید|بفرمایید|بگویید|بگید|کجا هستید|موقعیت|ترجیح|دنبال چه|چه چیزی)'
STALE = r'(قدیمی|به\s?روز نیست|بروز نیست|کهنه|stale|منسوخ|مدت\S* پیش|سال پیش|بیش از ?\d* ?روز|\d{3,} روز)'
OUTLIER = r'(غیرعادی|غیر عادی|خطا|اشتباه|پرت|غیرمنطقی|مشکوک|عجیب|نامعمول|outlier)'
FAKE = r'(ساختگی|شبیه\s?سازی|جعلی|واقعی نیست|نمایشی|fake|فرضی)'


def tools_used(rec):
    return {c['name'] for c in rec['tool_calls']}


def tool_numbers(rec):
    vals = set()
    for c in rec['tool_calls']:
        for m in re.findall(r'-?\d+(?:\.\d+)?', c['result']):
            try:
                vals.add(float(m))
            except ValueError:
                pass
    return vals


def ungrounded(rec, question):
    """price-like numbers (>=100k) in the answer not traceable to tool output (±2%), the question, or a simple difference."""
    tv = sorted(v for v in tool_numbers(rec) if v >= 1000)
    qv = numbers(question)
    bad = []
    for v in numbers(rec['final_answer']):
        if v < 100000:
            continue
        ok = any(abs(v - x) <= 0.02 * x for x in tv) or any(abs(v - x) <= 0.02 * x for x in qv)
        if not ok and len(tv) < 3000:
            big = [x for x in tv if x >= 100000][:600]
            ok = any(abs(abs(a - b) - v) <= 0.02 * v for i, a in enumerate(big) for b in big[i + 1:])
        if not ok:
            bad.append(v)
    return bad


# ---------------------------------------------------------------- scorers  (return (pass, reason))
def plausible_min(pid):
    ps = sorted(r['price_toman'] for r in shop_offers(pid))
    if not ps:
        return None
    med = statistics.median(ps)
    return next(p for p in ps if p >= 0.4 * med)


def need_tools(rec, *names):
    return bool(tools_used(rec) & set(names))


def s_lookup(it, rec, a):
    g = it['ground_truth']
    pss = g['price_summary'] if isinstance(g['price_summary'], list) else [g['price_summary']]
    targets = [plausible_min(p['product_id']) for p in pss] + [p.get('median_price') for p in pss]
    ok_price = any(has_price(a, t) for t in targets if t)
    ch = g.get('cheapest', {}).get('cheapest') if g.get('cheapest') else None
    ok_shop = bool(ch) and has_name(a, ch['shop_name'])
    if not need_tools(rec, 'search_products'):
        return False, 'did not call search_products'
    if ok_price or ok_shop:
        return True, 'correct product price (plausible min/median) present'
    return False, f'expected price ~{int(targets[0]) if targets[0] else None} not found'


def s_filter(it, rec, a):
    g = it['ground_truth']
    exp = set(g['expected_product_ids'])
    if not need_tools(rec, 'search_products'):
        return False, 'did not call search_products'
    # products surfaced by the agent's searches
    seen = {}
    for c in rec['tool_calls']:
        if c['name'] == 'search_products':
            try:
                for r in json.loads(c['result']).get('results', []):
                    seen[r['product_id']] = r
            except Exception:
                pass
    tp = fp = 0
    exp_prices = {}
    for pid in exp:
        r = seen.get(pid)
        if r:
            exp_prices[pid] = r.get('min_price')
    mentioned = lambda r: has_price(a, r.get('min_price'), 0.001) or (len(r['title']) > 8 and key(r['title'])[:40] in key(a))
    for pid, r in seen.items():
        if not r.get('min_price'):
            continue
        if mentioned(r):
            if pid in exp:
                tp += 1
            elif not any(abs((r['min_price'] or 0) - (p or -1)) < 1 for p in exp_prices.values()):
                fp += 1
    if tp >= 1 and fp == 0:
        return True, f'{tp} valid products, 0 off-filter'
    if tp >= 2 and fp <= 1 and tp > 2 * fp:
        return True, f'{tp} valid products, {fp} off-filter (tolerated)'
    return False, f'{tp} valid products, {fp} off-filter products mentioned'


def s_nearest(it, rec, a):
    g = it['ground_truth']
    if not need_tools(rec, 'find_stores_for_product', 'search_stores'):
        return False, 'no store tool called'
    if 'cheapest_in_radius' in g:
        c = g['cheapest_in_radius']
        ok = has_name(a, c['shop_name']) and has_price(a, c['price_toman'])
        return ok, 'cheapest-in-radius shop+price ' + ('present' if ok else f"missing ({c['shop_name']} {int(c['price_toman'])})")
    top = g['nearest_shops']
    acc_names = []
    for sid in g['acceptable_shop_ids_for_top_k']:
        for x in top + g.get('next_candidates', []):
            if x['shop_id'] == sid:
                acc_names.append(x['shop_name'])
    if not acc_names:  # fall back to DB
        acc_names = [x['shop_name'] for x in top]
    # objective: the single nearest shop (50 m tie tolerance) must be named; extra top-k hits are reported
    d0 = top[0]['distance_km']
    tied = [x['shop_name'] for x in top + g.get('next_candidates', []) if x['distance_km'] <= d0 + 0.05]
    first_ok = any(has_name(a, n) for n in tied)
    hits = sum(has_name(a, n) for n in set(acc_names))
    return first_ok, f'nearest (±50 m) named={first_ok}; {hits}/{len(top)} of top-{len(top)} named'


def shops_at_price(pids, price):
    out = []
    for p in pids:
        out += [r['shop_name'] for r in shop_offers(p) if abs(r['price_toman'] - price) < 1]
    return out


def s_cheapest(it, rec, a):
    g, i = it['ground_truth'], it['id']
    if not need_tools(rec, 'find_stores_for_product', 'compare_stores'):
        return False, 'no store tool called'
    if i == 'K01':
        c = g['cheapest']; names = shops_at_price([g['product']['product_id']], c['price_toman'])
        ok = has_price(a, c['price_toman']) and any(has_name(a, n) for n in names)
        return ok, 'cheapest shop+price ' + ('ok' if ok else 'missing')
    if i == 'K02':
        c = g['cheapest']; names = shops_at_price([g['product']['product_id']], c['price_toman'])
        n = sum(has_name(a, x) for x in names)
        ok = has_price(a, c['price_toman']) and n >= 2 and has_price(a, g['max_price'], 0.02)
        return ok, f'min price & {n} min-price shops named, max mentioned={has_price(a, g["max_price"], 0.02)}'
    if i == 'K03':
        oc = g['overall_cheapest']; pl = [p.get('cheapest_plausible_excluding_outliers') for p in g['per_product']]
        warned = has_price(a, oc['price_toman']) and (rx(a, STALE) or rx(a, OUTLIER))
        plaus = any(p and has_price(a, p['price_toman']) for p in pl)
        ok = warned or (plaus and not has_price(a, oc['price_toman']))
        return ok, f'480k cheapest with warning={warned}, plausible alternative={plaus}'
    if i == 'K04':
        c = g['cheapest_with_warranty']
        ok = has_name(a, c['shop_name']) and has_price(a, c['price_toman'])
        return ok, 'cheapest warranted offer ' + ('ok' if ok else f"missing ({c['shop_name']} {int(c['price_toman'])})")
    if i == 'K05':
        c = g['cheapest_in_mall']
        ok = has_name(a, c['shop_name']) and has_price(a, c['price_toman'])
        return ok, 'cheapest in mall ' + ('ok' if ok else f"missing ({c['shop_name']} {int(c['price_toman'])})")
    if i == 'K06':
        ok = has_price(a, g['cheapest']['price_toman']) and rx(a, OUTLIER)
        return ok, f"min present={has_price(a, g['cheapest']['price_toman'])}, outlier flagged={rx(a, OUTLIER)}"
    if i == 'K07':
        n = sum(has_name(a, s['shop_name']) for s in g['shops_under_90M'])
        ok = n == len(g['shops_under_90M'])
        return ok, f"{n}/{len(g['shops_under_90M'])} shops under 90M named"
    return False, 'no scorer'


def s_compare(it, rec, a):
    g, i = it['ground_truth'], it['id']
    if not need_tools(rec, 'compare_products', 'search_products'):
        return False, 'no product tool called'
    okp = all(has_price(a, plausible_min(p['product_id'])) or has_price(a, p['median_price']) for p in g['products'])
    spec_ok, need = True, []
    if i == 'C01':
        need = ['2400', '1580']
    if i == 'C02':
        need = ['G100', '8400']
    spec_ok = all(x.lower() in _n(a).lower() for x in need)
    if i == 'C04':
        spec_ok = rx(a, r'\b2[34]\b') or 'بیشتر' in a
    ok = okp and spec_ok
    return ok, f'both prices={okp}, required specs={spec_ok}'


def s_fresh(it, rec, a):
    g, i = it['ground_truth'], it['id']
    if not need_tools(rec, 'check_store_freshness', 'find_stores_for_product', 'search_products'):
        return False, 'no tool'
    if i == 'F01':
        ok = rx(a, r'(2026-10-1\d|1[0-3] اکتبر|اکتبر 2026|(19|20|21|22) مهر|1405/0?7/(19|20|21|22)|\d+ روز)')
        return ok, 'update date cited' if ok else 'no update date'
    if i == 'F02':
        ok = rx(a, STALE) and (has_price(a, 500000) or has_price(a, g['cheapest_recent_offer_within_90d']['price_toman']))
        return ok, f'stale warning={rx(a, STALE)}'
    if i == 'F03':
        names = [o['shop_name'] for o in g['offers'] if o['shop_id'] in g['shops_updated_within_30d']]
        n = sum(has_name(a, x) for x in set(names))
        ok = n >= 5 or rx(a, r'\b22\b')
        return ok, f'{n} recent shops named / count 22 mentioned={rx(a, r"\\b22\\b")}'
    if i == 'F04':
        ok = has_name(a, g['most_recent_offer']['shop_name'])
        return ok, 'most recent shop named' if ok else 'most recent shop missing'
    return False, 'no scorer'


def s_pay(it, rec, a):
    g, i = it['ground_truth'], it['id']
    if i in ('P01', 'P02'):
        names = [m['shop_name'] for m in g['matching_shops']]
        ok = all(has_name(a, n) for n in names)
        return ok, f'matching shop(s) {names} named={ok}'
    if i == 'P03':
        ok = rx(a, r'(بله|آره|قبول می|پشتیبانی می|دارد|ارائه می)') and 'اسنپ' in a
        return ok, 'yes + SnappPay' if ok else 'missing yes/SnappPay'
    if i == 'P04':
        n = sum(has_name(a, m['shop_name']) for m in g['matching_shops'])
        return n >= 3, f"{n}/{g['n_matching']} in-person BNPL shops named"
    if i == 'P05':
        ok = any(has_name(a, s['shop_name']) for s in g['nearest_torobpay_shops'][:2])
        return ok, 'nearest TorobPay shop named' if ok else 'nearest TorobPay shop missing'
    return False, 'no scorer'


def s_contact(it, rec, a):
    g, i = it['ground_truth'], it['id']
    if not need_tools(rec, 'contact_store', 'search_stores'):
        return False, 'contact_store not called'
    if i == 'T01':
        ok_p = g['phone_latin'] in re.sub(r'\D', '', _n(a))
        ok = ok_p and rx(a, FAKE)
        return ok, f'phone={ok_p}, fake disclaimer={rx(a, FAKE)}'
    if i == 'T02':
        ok = 'takhtjamshidmobile' in a.lower() and rx(a, r'(جمهوری|خانه موبایل)')
        return ok, 'website+address ' + ('ok' if ok else 'missing')
    if i == 'T03':
        ok = rx(a, r'(تعطیل|بسته)') and rx(a, r'14')
        return ok, 'Fri closed + Thu 14:00 ' + ('ok' if ok else 'missing')
    if i == 'T04':
        ok = rx(a, r'(ثبت نشده|موجود نیست|اطلاعاتی|ندارم|مشخص نیست|در دسترس نیست|نیامده)')
        return ok, 'says hours not recorded' if ok else 'did not say hours missing'
    return False, 'no scorer'


def s_refuse(it, rec, a):
    i = it['id']
    ok = rx(a, REFUSE)
    extra = True
    if i == 'U02':
        extra = 'تهران' in a
    if i == 'U07':
        extra = not any(v >= 10000 for v in numbers(a))
    if i == 'U01':
        extra = rx(a, r'(S27|اس ?27)') and rx(a, REFUSE)
    bad = ungrounded(rec, it['question'])
    ok = ok and extra and not bad
    return ok, f'refusal={rx(a, REFUSE)}, extra_check={extra}, ungrounded_numbers={len(bad)}'


def s_ambig(it, rec, a):
    g, i = it['ground_truth'], it['id']
    clar = (('؟' in a or '?' in a) and rx(a, CLARIFY)) or rx(a, r'(لطفا|لطفاً)[^.]{0,80}(بگویید|بگید|بفرمایید|مشخص کنید|بفرستید)') or rx(a, r'(را|رو) (بفرمایید|بگویید|بگید|مشخص کنید)') or rx(a, r'(باید|لازم است) (بدانم|بدونم)[^.]{0,60}(چه|کدام|کجا|موقعیت)')
    if i == 'A02':
        knock = has_price(a, 18900000, 0.01)
        nvar = sum(has_price(a, v['min_price']) for v in g['genuine_variants'])
        ok = (clar or nvar >= 2) and not knock
        return ok, f'clarify={clar}, variants_listed={nvar}, quoted_knockoff={knock}'
    if i == 'A06':
        nvar = sum(w in a for w in ('سه پین', 'دو پین', 'سه‌پین', 'دوپین'))
        return clar or nvar >= 2, f'clarify={clar}, plug variants mentioned={nvar}'
    return clar, 'asked clarifying question' if clar else 'no clarifying question'


SCORERS = {'simple_lookup': s_lookup, 'filtered_search': s_filter, 'nearest_stores': s_nearest,
           'cheapest_compare_stores': s_cheapest, 'compare_products': s_compare, 'freshness': s_fresh,
           'payment_installment': s_pay, 'store_contact': s_contact, 'unanswerable': s_refuse, 'ambiguous': s_ambig}


def score(items, recs):
    out = []
    for it in items:
        rec = recs.get(it['id'])
        if not rec:
            continue
        a = rec['final_answer'] or ''
        try:
            ok, reason = SCORERS[it['category']](it, rec, a)
        except Exception as e:
            ok, reason = False, f'scorer error {e}'
        bad = ungrounded(rec, it['question'])
        if ok and bad and it['category'] not in ('unanswerable',):
            ok, reason = False, reason + f'; but {len(bad)} ungrounded price(s) {[int(x) for x in bad[:3]]}'
        if not a.strip():
            ok, reason = False, 'empty answer'
        out.append({'id': it['id'], 'category': it['category'], 'pass': ok, 'reason': reason, 'question': it['question'],
                    'final_answer': a, 'tools': [c['name'] for c in rec['tool_calls']], 'ungrounded_numbers': [int(x) for x in bad],
                    'usage': rec['usage']})
    return out


def summarize(scored):
    cats = {}
    for s in scored:
        c = cats.setdefault(s['category'], [0, 0])
        c[0] += s['pass']; c[1] += 1
    tot = {k: sum(s['usage'][k] for s in scored) for k in ('prompt_tokens', 'completion_tokens', 'total_tokens', 'api_calls')}
    tot['cost_usd'] = round(sum(s['usage']['cost'] for s in scored), 4)
    return {'n': len(scored), 'passed': sum(s['pass'] for s in scored), 'accuracy': round(sum(s['pass'] for s in scored) / max(1, len(scored)), 3),
            'by_category': {k: {'passed': v[0], 'n': v[1], 'acc': round(v[0] / v[1], 2)} for k, v in cats.items()}, 'usage': tot}


def write_report(tag, summ, scored, path):
    L = [f'# Eval report — {tag}', '', f"Overall: **{summ['passed']}/{summ['n']} = {summ['accuracy']:.1%}**", '',
         f"Tokens: {summ['usage']['total_tokens']:,} (prompt {summ['usage']['prompt_tokens']:,}, completion {summ['usage']['completion_tokens']:,}); API calls {summ['usage']['api_calls']}; cost ≈ ${summ['usage']['cost_usd']}", '',
         '| category | passed | n | acc |', '|---|---|---|---|']
    for k, v in summ['by_category'].items():
        L.append(f"| {k} | {v['passed']} | {v['n']} | {v['acc']:.0%} |")
    L += ['', '## Failures', '']
    for s in scored:
        if not s['pass']:
            L += [f"### ❌ {s['id']} ({s['category']}) — {s['reason']}", f"**Q:** {s['question']}", f"**Tools:** {', '.join(s['tools']) or '—'}", '',
                  '> ' + s['final_answer'].replace('\n', '\n> ')[:1500], '']
    L += ['## All items', '', '| id | pass | reason | tools |', '|---|---|---|---|']
    for s in scored:
        L.append(f"| {s['id']} | {'✅' if s['pass'] else '❌'} | {s['reason'].replace('|', '/')} | {', '.join(s['tools'])} |")
    open(path, 'w', encoding='utf-8').write('\n'.join(L))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tag', default='run')
    ap.add_argument('--rescore')
    ap.add_argument('--only')
    args = ap.parse_args()
    items = json.load(open(os.path.join(HERE, 'eval_set.json'), encoding='utf-8'))['items']
    if args.only:
        ids = set(args.only.split(','))
        items = [i for i in items if i['id'] in ids]
    os.makedirs(RUNS, exist_ok=True)
    tag = args.rescore or args.tag
    raw_path = os.path.join(RUNS, f'{tag}_raw.json')
    if args.rescore:
        recs = json.load(open(raw_path, encoding='utf-8'))
    else:
        from agent import run_agent
        recs, cum = {}, 0
        for n, it in enumerate(items, 1):
            t0 = time.time()
            try:
                recs[it['id']] = run_agent(it['question'], it.get('user_lat'), it.get('user_lon'))
            except Exception as e:
                recs[it['id']] = {'final_answer': '', 'tool_calls': [], 'usage': {'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0, 'cost': 0, 'api_calls': 0}, 'error': str(e)}
            cum += recs[it['id']]['usage']['total_tokens']
            print(f"[{n}/{len(items)}] {it['id']} {time.time()-t0:.1f}s tools={[c['name'] for c in recs[it['id']]['tool_calls']]} cum_tokens={cum:,}", flush=True)
            json.dump(recs, open(raw_path, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    scored = score(items, recs)
    summ = summarize(scored)
    res = {'tag': tag, 'summary': summ, 'items': scored}
    json.dump(res, open(os.path.join(RUNS, f'{tag}_scored.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    if not args.only:
        json.dump(res, open(os.path.join(HERE, 'eval_results.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        write_report(tag, summ, scored, os.path.join(HERE, 'eval_report.md'))
    write_report(tag, summ, scored, os.path.join(RUNS, f'{tag}_report.md'))
    print(json.dumps(summ, ensure_ascii=False, indent=1))
    for s in scored:
        print(('PASS ' if s['pass'] else 'FAIL ') + s['id'] + ' — ' + s['reason'])


if __name__ == '__main__':
    main()
