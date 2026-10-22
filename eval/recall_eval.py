#!/usr/bin/env python3
"""Measure retrieval recall on recall_tests.json for each layer combination."""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "..", "backend", "app", "engine")))
import json, os, sys, time
import tools, recall

HERE = os.path.dirname(os.path.abspath(__file__))
TESTS = json.load(open(os.path.join(HERE, 'recall_tests.json'), encoding='utf-8'))['tests']
MODES = {
    'baseline_lexical': None,
    '+alias_fuzzy': dict(alias=1, llm_expand=0, embed=0, grader=0),
    '+alias+llm_expand': dict(alias=1, llm_expand=1, embed=0, grader=0),
    '+alias+llm+embed': dict(alias=1, llm_expand=1, embed=1, grader=0),
    'full(+grader)': dict(alias=1, llm_expand=1, embed=1, grader=1),
}


def ids_of(results):
    out = []
    for r in results:
        out.append(r['product_id'])
        out += r.get('same_title_other_product_ids', [])
    return out


def run(modes):
    report = {}
    for name in modes:
        lay = MODES[name]
        per = []
        for t in TESTS:
            exp = set(t['expected_product_ids'])
            if lay is None:
                res = tools.search_products_lexical(t['query'], limit=10)['results']
            else:
                res = recall.search_products_hybrid(t['query'], limit=10, layers=lay)['results']
            row = {'id': t['id'], 'query': t['query'], 'top3': [r['title'][:60] for r in res[:3]]}
            for k in (5, 10):
                got = ids_of(res[:k])
                inter = exp & set(got)
                row[f'hit@{k}'] = int(bool(inter))
                row[f'recall@{k}'] = round(len(inter) / min(len(exp), k), 3)
            per.append(row)
        agg = {m: round(sum(r[m] for r in per) / len(per), 3) for m in ('hit@5', 'hit@10', 'recall@5', 'recall@10')}
        report[name] = {'aggregate': agg, 'per_query': per}
        print(name, agg, flush=True)
    return report


if __name__ == '__main__':
    modes = sys.argv[1].split(',') if len(sys.argv) > 1 else list(MODES)
    rep = run(modes)
    rep['_api_stats'] = recall.STATS
    path = os.path.join(HERE, 'recall_results.json')
    old = json.load(open(path, encoding='utf-8')) if os.path.exists(path) else {}
    old.update(rep)
    json.dump(old, open(path, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(recall.STATS)
