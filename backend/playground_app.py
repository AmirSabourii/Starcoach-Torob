"""Torob Playground: current (agent.py) vs V3 (agent_v3) vs JEV (agent_jev) vs V3+ (agent_v3plus).
Run:  source /workspace/.venv/bin/activate && cd /workspace/torob/eval && PLAYGROUND_TOKEN=... uvicorn playground_app:app --port 8765
Thin adapter only: the agents are imported unchanged."""
import os, time, json, threading, secrets, re
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse

HERE = os.path.dirname(os.path.abspath(__file__))
TOKEN = os.environ.get('PLAYGROUND_TOKEN') or secrets.token_urlsafe(16)
SESSION_CAP = float(os.environ.get('PLAYGROUND_SPEND_CAP', '0.50'))   # hard stop for this process (USD)
PROJECT_BASE = float(os.environ.get('PLAYGROUND_PROJECT_BASE', '0.82'))
SPEND_F = os.path.join(HERE, 'playground_spent.txt')

import agent as CUR
import agent_v3 as A
import agent_jev as J
import agent_v3plus as P          # V3+ (separate instance of v3 code + product_knowledge + consultant prompt)
import sqlite3, tools as T, gt_lib
import playground_drill as D
import playground_lists as LST
import playground_about as AB     # product details (DB) + «دربارهٔ این محصول» (keyless web search + 1 short LLM call, cached)
import playground_project as PRJ   # «خرید یکجا»: plan (1 LLM call) -> server search+optimizer (no LLM) -> 1 tiny summary call
import playground_home as HOME   # /app home page data: tiles, category listing, deals, areas, map shops (pure SQLite, no LLM)
import playground_bazaar as BZ   # saved lists / basket (user_lists.sqlite), no AI     # drill-down / related / templates: pure SQLite + stored embeddings, no LLM

# thin adapter: tools.con (used by agent.py tools + recall) was opened with check_same_thread=True in the import thread;
# reopen it shareable across the server's worker threads (same DB, same functions). All engine calls are serialized below.
_c = sqlite3.connect(gt_lib.DB, check_same_thread=False)
_c.row_factory = sqlite3.Row
_c.create_function('dist_km', 4, gt_lib.haversine, deterministic=True)
_c.create_function('regexp', 2, lambda p, s: s is not None and re.search(p, s) is not None, deterministic=True)
T.con = _c

DB_LOCK = threading.Lock()          # all three engines share sqlite connections (tools.con, A.RO) -> one engine at a time
SPEND_LOCK = threading.Lock()
STATE = {'spent': float(open(SPEND_F).read() or 0) if os.path.exists(SPEND_F) else 0.0, 'calls': 0}   # persisted across restarts
SESS = {}                            # (sid, version) -> {'hist': [...], 'mission': ..., 'cur_turns': [...]}
_SQL = threading.local()

def _trace(stmt):
    lst = getattr(_SQL, 'lst', None)
    if lst is not None and len(lst) < 400:
        lst.append(stmt)
A.RO.set_trace_callback(_trace)
P.RO.set_trace_callback(_trace)

def _add_spend(c):
    with SPEND_LOCK:
        STATE['spent'] += c; STATE['calls'] += 1
        open(SPEND_F, 'w').write(f"{STATE['spent']:.6f}\n")

def _sqls():
    seen, out = set(), []
    for s in getattr(_SQL, 'lst', []) or []:
        k = re.sub(r'\s+', ' ', s).strip()
        if k in seen: continue
        seen.add(k); out.append(k)
    out.sort(key=len, reverse=True)
    return [s[:1500] for s in out[:8]], len(out)

def _sess(sid, v):
    return SESS.setdefault((sid, v), {'hist': [], 'mission': None, 'cur_turns': [], 'mem': _new_mem()})

# ------------------------------------------------------------------ V3+ structured session memory (server-side, per (sid, version))
def _new_mem():
    return {'turns': [], 'last_products': [], 'products': [], 'shops': [], 'last_shops': [], 'selections': [], 'category': None, 'cleared': [], 'prefs': {}}

_PRICE_RX = re.compile(r'[\d۰-۹][\d۰-۹٬,.]*\s*(?:میلیون|هزار)?\s*تومان')
def _trim_answer(t, n=260):
    t = _PRICE_RX.sub('[قیمت]', re.sub(r'\s+', ' ', t or '')).strip()   # remembered prices are never reused: the model must re-fetch
    return t if len(t) <= n else t[:n].rsplit(' ', 1)[0] + '…'

def _shown(blocks):
    prods, shops = [], []
    def addp(pid, title, cat=None):
        if pid and pid not in [x['id'] for x in prods]: prods.append({'id': pid, 'name': D._short(title, 40), 'cat': cat})
    def adds(sid, name):
        if sid and sid not in [x['id'] for x in shops]: shops.append({'id': sid, 'name': D._short(name, 30)})
    for b in blocks or []:
        if b.get('type') == 'product_cards':
            for p in b['items']: addp(p.get('product_id'), p.get('title'), p.get('category'))
        elif b.get('type') == 'compare':
            for p in b['products']: addp(p.get('product_id'), p.get('title'), p.get('category'))
        elif b.get('type') in ('sellers', 'verify'):
            for o in b['items']:
                if o.get('product_id'): addp(o['product_id'], o.get('product_title'), o.get('category'))
                sh = o.get('shop') or {}
                adds(sh.get('shop_id'), sh.get('name'))
        elif b.get('type') == 'map':
            for p in b['pins']: adds(p.get('shop_id'), p.get('name'))
        elif b.get('type') == 'plan':
            for st in b['steps']:
                sh = st.get('shop') or {}
                adds(sh.get('shop_id'), sh.get('name'))
    return prods, shops

def _mem_view(s):
    """small structured view (UI chips + injected context). Budget/area/features live in the V3+ mission; we read them from there."""
    m, mi = s['mem'], s.get('mission') or {}
    cons = mi.get('_constraints') or {}
    feats = cons.get('required_terms') if isinstance(cons, dict) else None
    return {'goal': mi.get('goal'), 'category': m.get('category'), 'budget_toman': mi.get('budget_toman'), 'area': mi.get('area'),
            'area_latlon': mi.get('area_latlon'), 'features': feats or None, 'notes': mi.get('notes'),
            'last_products': m['last_products'][:8], 'products': m['products'][:10], 'shops': m['shops'][:6], 'last_shops': m['last_shops'][:6],
            'selections': m['selections'][-5:], 'excluded_shop_ids': mi.get('excluded_shop_ids') or None, 'prefs': m.get('prefs') or None}

def _mem_chips(s):
    v, out = _mem_view(s), []
    if v['category']: out.append({'key': 'category', 'label': v['category']})
    pb = (v['prefs'] or {}).get('budget')
    if pb:      # the shopper's own answer (keeps a range like «۳ تا ۸ میلیون»)
        out.append({'key': 'pref:budget', 'label': 'بودجه ' + pb['answer'][:24]})
    elif v['budget_toman']:
        try: out.append({'key': 'budget', 'label': 'بودجه ' + D.fa_money(float(v['budget_toman']))})
        except Exception: pass
    if v['area']: out.append({'key': 'area', 'label': str(v['area'])[:24]})
    if v['features']: out.append({'key': 'features', 'label': '، '.join(str(x) for x in v['features'][:2])[:28]})
    if v['products']: out.append({'key': 'products', 'label': f"{D._FA and str(len(v['products'])).translate(D._FA)} کالای دیده‌شده"})
    for qid, pv in (v['prefs'] or {}).items():
        if qid != 'budget': out.append({'key': 'pref:' + qid, 'label': pv['answer'][:26]})
    if v['selections']: out.append({'key': 'selections', 'label': 'انتخاب: ' + v['selections'][-1]['name'][:22]})
    return out

def _mem_message(s):
    """compact context injected as a system message before the recent turns (kept ~<600 tokens)"""
    v = _mem_view(s)
    L = ['Session memory (server-kept; ids/names only — NEVER reuse a remembered price: re-fetch prices with tools).']
    for k, lab in (('goal', 'intent'), ('category', 'category'), ('budget_toman', 'budget_toman'), ('area', 'area'), ('area_latlon', 'area_latlon'),
                   ('features', 'required features'), ('excluded_shop_ids', 'excluded shops')):
        if v[k]: L.append(f'- {lab}: {json.dumps(v[k], ensure_ascii=False) if not isinstance(v[k], str) else v[k]}')
    if v['last_products']:
        L.append('- last answer showed products in this order (for «اولی/دومی/همین/ارزون‌ترش»): ' + '; '.join(f"{i+1}) {p['name']} [{p['id']}]" for i, p in enumerate(v['last_products'])))
    older = [p for p in v['products'] if p['id'] not in {x['id'] for x in v['last_products']}][:5]
    if older: L.append('- shown earlier: ' + '; '.join(f"{p['name']} [{p['id']}]" for p in older))
    if v['last_shops']: L.append('- shops shown last: ' + '; '.join(f"{i+1}) {x['name']} [{x['id']}]" for i, x in enumerate(v['last_shops'])))
    if v['prefs']: L.append('- shopper already answered (do not ask again): ' + '; '.join(f"{p['title']} → {p['answer']}" for p in v['prefs'].values()))
    if v['selections']: L.append('- user opened in the details panel (most recent last): ' + '; '.join(f"{x['kind']} {x['name']} [{x['id']}]" for x in v['selections']))
    return '\n'.join(L)

def _call_hist(s, msg):
    """structural context for V3+: memory message + last 4 user/assistant pairs (assistant text trimmed, prices masked) + new message"""
    h = [{'role': 'system', 'content': _mem_message(s)}]
    for u, a in s['mem']['turns'][-4:]:
        h += [{'role': 'user', 'content': u[:300]}, {'role': 'assistant', 'content': a}]
    return h + [{'role': 'user', 'content': msg}]

def _update_mem(s, msg, r):
    m = s['mem']
    prods, shops = _shown(r.get('blocks'))
    goal = (s.get('mission') or {}).get('goal')
    if not prods and goal and m.get('_goal') and goal != m.get('_goal'):   # topic changed and this turn showed nothing: drop the old topic's category/products
        m['category'] = None; m['last_products'] = []
    if goal: m['_goal'] = goal
    m['turns'].append((msg, _trim_answer(r.get('text'))))
    m['turns'] = m['turns'][-4:]
    if prods:
        m['last_products'] = prods[:8]
        m['products'] = (prods + [p for p in m['products'] if p['id'] not in {x['id'] for x in prods}])[:10]
        cats = [p['cat'] for p in prods if p.get('cat')]
        if cats: m['category'] = max(set(cats), key=cats.count)
    pairs = [{'shop_id': (o.get('shop') or {}).get('shop_id'), 'product_id': o.get('product_id'), 'name': (o.get('shop') or {}).get('name')}
             for b in (r.get('blocks') or []) if b.get('type') in ('sellers', 'verify') for o in (b.get('items') or []) if isinstance(o, dict)]
    pairs = [x for x in pairs if x['shop_id'] and x['product_id']]
    if pairs:     # for «بسته بود / جواب نداد» follow-ups
        m['offer_ctx'] = (pairs + [x for x in m.get('offer_ctx', []) if x['shop_id'] not in {y['shop_id'] for y in pairs}])[:12]
    if shops:
        m['last_shops'] = shops[:6]
        m['shops'] = (shops + [x for x in m['shops'] if x['id'] not in {y['id'] for y in shops}])[:6]
    return prods, shops

def _suggestions(model_sug, blocks, prods, shops, s):
    out, src = [], []
    for x in model_sug or []:
        if x not in out: out.append(x); src.append('model')
    for b in blocks or []:
        if b.get('type') == 'chips':
            for x in b.get('options', []):
                if len(out) < 3 and x not in out and not D._BAD.search(x): out.append(x); src.append('chips')
    mv = _mem_view(s) if s else {}
    for x in D.template_suggestions(prods, shops, mv):
        if len(out) < 3 and x not in out: out.append(x); src.append('template')
    return out[:3], src[:3]

def _list_hook(blocks):
    """«به لیست اضافه کنم؟»: the answer's top recommended item (first seller offer, else first product card) — added on click, no AI"""
    for b in blocks or []:
        if b.get('type') in ('sellers', 'verify'):
            for o in b['items']:
                if o.get('offer_id') and o.get('product_id'):
                    return {'label': 'به لیست اضافه کنم؟', 'product_id': o['product_id'], 'shop_id': o.get('shop_id'), 'offer_id': o['offer_id'],
                            'title': o.get('product_title'), 'shop_name': (o.get('shop') or {}).get('name')}
    for b in blocks or []:
        if b.get('type') == 'product_cards' and b['items']:
            p = b['items'][0]
            return {'label': 'به لیست اضافه کنم؟', 'product_id': p['product_id'], 'shop_id': None, 'offer_id': None, 'title': p.get('title'), 'shop_name': None}
    return None

def _related_for(blocks, k=8):
    prods, _ = _shown(blocks)
    try:
        return D.related([p['id'] for p in prods][:6], k=k)
    except Exception as e:
        return []

def _project_turn(s, msg, ans, t0, goal=None):
    """V3+ project intent -> questions (existing cards) or an editable needs checklist; returns None if the model says it's not a project.
    goal: set when the V3+ agent itself chose start_project (its goal text); the regex fast path passes None."""
    pend = s.get('project_pending'); goal_in = goal
    goal = pend if (pend and ans) else (goal or msg)
    r = PRJ.plan(goal, ans, A.client, A._usage_cost, _add_spend, P.validate_questions)
    if r['stage'] == 'not_project' and not pend:
        return None, r
    u = r.get('usage') or {}
    out = {'text': P.sanitize_boilerplate(r.get('say') or r.get('title') or '')[0], 'blocks': [], 'engine': 'v3plus-project', 'related': [], 'suggestions': [],
           'questions': r.get('questions') or [], 'memory': {'chips': _mem_chips(s)}, 'list_hook': None, 'bazaar': None,
           'debug': {'project_plan': {k: r.get(k) for k in ('stage', 'goal', 'title', 'questions_dropped', 'elapsed_s')}}}
    if r['stage'] == 'questions':
        s['project_pending'] = goal
    else:
        s.pop('project_pending', None)
        s['project'] = {'goal': goal, 'title': r.get('title'), 'needs': r.get('needs')}
        out['project'] = {'stage': 'needs', 'goal': goal, 'title': r.get('title'), 'assumptions': r.get('assumptions'), 'needs': r.get('needs') or [],
                          'area': next((a.get('answer') for a in (ans or []) if re.search(r'area|location|region|neighborhood', str(a.get('id')))), None)}
    s['mem']['turns'] = (s['mem']['turns'] + [[msg, out['text'][:200]]])[-4:]
    out['metrics'] = {'latency_s': round(time.time() - t0, 1), 'llm_calls': 1, 'tokens': (u.get('prompt_tokens') or 0) + (u.get('completion_tokens') or 0),
                      'prompt_tokens': u.get('prompt_tokens'), 'completion_tokens': u.get('completion_tokens'), 'cost_usd': u.get('cost_usd')}
    out['project_route'] = 'agent' if goal_in else ('answers' if (pend and ans) else 'regex')   # who routed to the planner (UI badge)
    out['ok'] = True; out['version'] = 'v3plus'
    return out, r

_FU_PREFIX = re.compile(r'^دربارهٔ همین فهرست «خرید یکجا»[^:]*:\s*')
def _project_followup(s, msg, uip, t0):
    """Deterministic plan revision (no LLM): «ارزون‌ترش کن» -> cheapest plan, «فقط از یه بازار» -> one-stop plan,
    «نزدیک X باشه» -> re-search around X. Needs come from the session's plan (chat flow) or the on-screen plan items.
    Returns None for other follow-ups (e.g. «X رو عوض کن") so the agent handles them (with start_project disabled, no questions)."""
    q = _FU_PREFIX.sub('', msg).strip()
    try:
        ctx = json.loads(uip.get('plan') or '{}') if isinstance(uip.get('plan'), str) else (uip.get('plan') or {})
    except Exception:
        ctx = {}
    near = re.search(r'نزدیک(?:\s*به)?\s+([\u0600-\u06FF][\u0600-\u06FF ]{1,20}?)(?:\s+(?:باشه|باشد|بشه|باشن|بگیر|پیدا کن)|[.!؟]|$)', q)
    if re.search(r'ارزون|ارزان|کم[‌ ]?هزینه|اقتصادی|کم[‌ ]?تر خرج', q):
        op, key = 'cheaper', 'cheapest'
    elif re.search(r'(یه|یک|همون|همین)\s*(بازار|جا|فروشگاه|مغازه)|یک[‌ ]?جا بخرم|همه از یه', q):
        op, key = 'one_place', 'one_stop'
    elif near:
        op, key = 'nearer', 'balanced'
    else:
        return None
    sp = s.get('project') or {}
    needs = [dict(n) for n in (sp.get('needs') or []) if isinstance(n, dict)]
    if not needs:                 # rebuild from the plan on screen (item names + quantities)
        needs = [{'id': f'n{i+1}', 'item': it.get('item'), 'query': it.get('item'), 'qty': it.get('qty') or 1}
                 for i, it in enumerate(ctx.get('items') or []) if isinstance(it, dict) and it.get('item')]
    if not needs:
        return None
    area = near.group(1).strip() if op == 'nearer' else (ctx.get('area') or None)
    with DB_LOCK:
        res = PRJ.search(needs, area)
    plans = res.get('plans') or []
    pl = next((p for p in plans if p['key'] == key), None) or next((p for p in plans if key in (p.get('also') or []) or p['name'] == key), None) or (plans[0] if plans else None)
    if not pl:
        return None
    old_total, old_shops = ctx.get('total_toman'), ctx.get('n_shops')
    tot = P.fmt_toman_text(pl['total_toman']) if pl.get('total_toman') else None
    if op == 'cheaper':
        if old_total and pl['total_toman'] and pl['total_toman'] < old_total * 0.995:
            a_, b_ = P.fmt_toman_text(pl['total_toman']), P.fmt_toman_text(old_total)
            if a_ == b_: a_, b_ = P.fmt_toman(pl['total_toman']), P.fmt_toman(old_total)      # rounding would hide the saving
            text = f"نسخهٔ ارزان‌تر آماده شد: جمعش {a_} می‌شه (قبلاً {b_})، از {P._fa(pl['n_shops'])} فروشگاه."
        else:
            text = f"ارزان‌تر از این فهرست با همین اقلام پیدا نشد؛ ارزان‌ترین ترکیب {tot} است، از {P._fa(pl['n_shops'])} فروشگاه."
    elif op == 'one_place':
        hub = (pl.get('hub') or {}).get('name')
        text = (f"همه رو از {P._fa(pl['n_shops'])} فروشگاه" + (f" در {hub}" if hub else '') + f" می‌شه گرفت؛ جمعش {tot}"
                + (f" (فهرست فعلی {P.fmt_toman_text(old_total)} از {P._fa(old_shops)} فروشگاه)." if old_total and old_shops else '.'))
    else:
        text = f"فهرست با فروشگاه‌های نزدیک {area} دوباره چیده شد؛ جمعش {tot}، از {P._fa(pl['n_shops'])} فروشگاه."
    if res.get('not_found'):
        text += ' برای ' + '، '.join(x['item'] for x in res['not_found'][:3]) + ' گزینه‌ای پیدا نشد.'
    rows = pl.get('rows') or []
    blocks = [{'type': 'product_cards', 'items': [{'product_id': r_['product_id']} for r_ in rows if r_.get('product_id')][:12]},
              {'type': 'sellers', 'items': [{'offer_id': r_['offer_id']} for r_ in rows if r_.get('offer_id')][:12]}]
    seen = set(x['product_id'] for x in blocks[0]['items']) | set(x['offer_id'] for x in blocks[1]['items'])
    blocks, _hl = P.B.hydrate(blocks, seen)
    s['mem']['turns'] = (s['mem']['turns'] + [[msg, text[:200]]])[-4:]
    others = [t for o, t in (('cheaper', 'ارزون‌ترش کن'), ('one_place', 'فقط از یه بازار')) if o != op]
    out = {'text': text, 'blocks': blocks, 'engine': 'v3plus-project-revise', 'related': [], 'questions': [], 'suggestions': others,
           'memory': {'chips': _mem_chips(s)}, 'list_hook': None, 'bazaar': None,
           'project_result': dict(res, selected=pl['key'], revision=op, title=ctx.get('title') or sp.get('title'), goal=ctx.get('goal') or sp.get('goal')),
           'debug': {'project_followup': {'op': op, 'plan_key': pl['key'], 'area': area, 'needs_from': 'session' if sp.get('needs') else 'screen',
                                          'old_total': old_total, 'new_total': pl.get('total_toman'), 'old_shops': old_shops, 'new_shops': pl.get('n_shops')}},
           'metrics': {'latency_s': round(time.time() - t0, 1), 'llm_calls': 0, 'tokens': 0, 'cost_usd': 0.0}, 'ok': True, 'version': 'v3plus'}
    return out

import playground_latenight as LN
def _late(s, msg, r, out, dbg):
    """«الان کجا بازه؟» (explicit time words only): nearest OPEN shop + nearby bazaar + mini-map data (DB only), ADDED to the normal answer."""
    t_ = time.time()
    now, ovr = s.get('_now') or LN.parse_now()
    area = s.get('_area_name') or ((s.get('mission') or {}).get('_ui_area') or {}).get('name') or 'ونک'
    pt = HOME.area_point(area) or HOME.area_point('ونک')
    pids = [it.get('product_id') for b in out['blocks'] if b.get('type') == 'product_cards' for it in (b.get('items') or [])]
    cats = None
    if not pids:
        try: cats = P._infer_categories(msg)
        except Exception: cats = None
    res = LN.build(pids, msg, now, pt, HOME._PRETTY.get(area, area) if hasattr(HOME, '_PRETTY') else area, llm_flag=r.get('urgent_now'), categories=cats)
    dbg['late_night'] = {'now': now.strftime('%a %H:%M'), 'override': ovr, 'fired': bool(res), 'ms': int((time.time() - t_) * 1000), 'llm_flag': r.get('urgent_now'),
                         'trigger': res and res['block']['trigger']}
    if not res:
        return
    blk = res['block']
    # additive: the normal answer and its product cards stay; the late-night block goes right after the cards, its text after the answer
    bl = list(out['blocks'])
    has_cards = any(b_.get('type') == 'product_cards' and b_.get('items') for b_ in bl)
    if not has_cards and res['product_id']:     # the agent found no product: the open shop's product becomes the card (DB), text = the late-night answer
        add, _ = P.B.hydrate([{'type': 'product_cards', 'items': [{'product_id': res['product_id']}]}], {res['product_id']})
        bl = add + [b_ for b_ in bl if b_.get('type') not in ('product_cards', 'sellers')]
        out['text'] = ''
    i = next((k + 1 for k, b_ in enumerate(bl) if b_.get('type') == 'product_cards'), 0)
    out['blocks'] = bl[:i] + [blk] + bl[i:]
    out['text'] = (out.get('text') or '').rstrip() + ('\n\n' if out.get('text') else '') + res['text']
    out['suggestions'] = (['نزدیک‌ترین بازِ دیگه؟'] + [x for x in (out.get('suggestions') or []) if x != 'نزدیک‌ترین بازِ دیگه؟'])[:4]
    if s['mem']['turns']:
        s['mem']['turns'][-1] = (s['mem']['turns'][-1][0], out['text'][:200])

def _map_after(s, msg, r, out):
    """map context for the «نقشه» toggle (= the products of this answer) + LLM-decided map_pins + ETA/open-on-arrival on the late-night card"""
    pids = [it.get('product_id') for b in out['blocks'] if b.get('type') == 'product_cards' for it in (b.get('items') or []) if it.get('product_id')]
    if pids:
        t0 = next((it.get('title') for b in out['blocks'] if b.get('type') == 'product_cards' for it in (b.get('items') or [])), '') or ''
        s['_map_ctx'] = {'pids': pids[:6], 'label': ' '.join(t0.split()[:4]), 'ts': time.time()}
    mp = r.get('map_pins')
    if isinstance(mp, dict) and any(mp.get(k) for k in ('only_open', 'cheapest', 'hub')):
        f = {k: mp[k] for k in ('only_open', 'cheapest', 'hub') if mp.get(k)}
        s['_map_filter'] = f
        lat, lon, mode = _travel(s)
        res = MX.pins(lat, lon, mode, (s.get('_now') or LN.parse_now())[0], ctx=_map_ctx(s), flt=f)
        out['blocks'].append({'type': 'map_pins', 'filter': f, 'filter_label': res['filter_label'], 'n': res['n']})
    lat, lon, mode = _travel(s)
    now = (s.get('_now') or LN.parse_now())[0]
    for b in out['blocks']:
        if b.get('type') == 'late_night' and b.get('shop'):
            sh = b['shop']
            m_ = MX.eta_min(HOME._hav(lat, lon, sh['lat'], sh['lon']), mode, now)
            a_ = MX.arrival({sh['shop_id']: m_}, now)[sh['shop_id']]
            sh['eta_label'], sh['arrive_label'], sh['arrive'], sh['mode'] = MX.eta_label(m_), a_['label'], a_['arrive'], mode
            b['user'].update({'lat': lat, 'lon': lon})

_CLOSED_RX = re.compile(r'بسته\s*(بود|ه\b|‌ست|است|بودن)|تعطیل\s*(بود|ه\b|است)|جواب\s*ن(داد|می‌?د[هن]|میده)|در\s*دسترس\s*نبود|برنداشت|باز\s*نبود')
def _closed_followup(s, msg, t0):
    """«بسته بود» / «جواب نداد» about a shop in context -> 3 nearest open alternatives with the same product (DB only, no LLM)"""
    if not _CLOSED_RX.search(msg) or len(msg) > 120:
        return None
    m = s['mem']
    cands = []
    sc = s.get('_shop_ctx')
    if sc and time.time() - sc.get('ts', 0) < 3600: cands.append(sc)
    cands += [x for x in m.get('offer_ctx', []) if x['shop_id'] not in {c['shop_id'] for c in cands}]
    if not cands:
        return None
    nm = D.norm(msg) if hasattr(D, 'norm') else msg
    named = [c for c in cands if c.get('name') and len(c['name']) >= 3 and (c['name'] in msg or c['name'].split()[0] in msg)]
    c = named[0] if named else cands[0]
    alt = MALL.alternatives(c['shop_id'], c['product_id'])
    if not alt:
        return None
    items = alt['items']
    sname = alt['shop_name']
    if items:
        op = next((x for x in items if x['is_open']), None)
        text = (f"اگه {sname} بسته بود، {P._fa(len(items))} فروشگاهِ نزدیکش " + ('همین محصول' if all(x['same_product'] for x in items) else 'همین مدل') + ' رو دارن'
                + (f"؛ {op['shop_name']} الان بازه ({op['distance_label']}، {P.fmt_toman(op['price_toman'])})." if op else '؛ ساعت کاری‌شون ثبت نشده، قبل از رفتن بپرس.'))
    else:
        text = f"فروشگاه دیگه‌ای که الان باز باشه و همین محصول رو داشته باشه پیدا نکردم."
    pids = []
    for x in items:
        if x['product_id'] not in pids: pids.append(x['product_id'])
    blocks = [{'type': 'product_cards', 'items': [{'product_id': p_} for p_ in pids]},
              {'type': 'sellers', 'items': [{'offer_id': x['offer_id'], 'note': x['open_badge']} for x in items]}]
    seen = set(pids) | {x['offer_id'] for x in items}
    blocks, _hl = P.B.hydrate(blocks, seen)
    m['turns'] = (m['turns'] + [[msg, text[:200]]])[-4:]
    return {'text': text, 'blocks': blocks, 'engine': 'v3plus-closed-alternatives', 'related': [], 'questions': [], 'suggestions': [],
            'memory': {'chips': _mem_chips(s)}, 'list_hook': None, 'bazaar': None, 'alternatives': alt,
            'debug': {'closed_followup': {'shop_id': c['shop_id'], 'product_id': c['product_id'], 'by': 'name' if named else 'context', 'n': len(items)}},
            'metrics': {'latency_s': round(time.time() - t0, 2), 'llm_calls': 0, 'tokens': 0, 'cost_usd': 0.0}, 'ok': True, 'version': 'v3plus'}

import playground_mapx as MX

def _travel(s):
    """the shopper's start point + travel mode for ETAs: /app map onboarding (neighbourhood / geolocation) > chosen area > ونک"""
    t = s.get('_travel') or {}
    area = s.get('_area_name') or 'ونک'
    pt = (t['lat'], t['lon']) if t.get('lat') is not None else (HOME.area_point(area) or HOME.area_point('ونک'))
    return pt[0], pt[1], t.get('mode') or 'metro'

def _map_ctx(s):
    c = s.get('_map_ctx') or {}
    return c if c and time.time() - c.get('ts', 0) < 7200 else {}

def _map_pin_cmd(s, msg, t0):
    """«فقط مغازه‌های باز رو پین کن» / «مغازه‌های علاءالدین» / (from the map composer) «ارزون‌ترین‌ها رو نشون بده» -> map_pins action ($0, no LLM)"""
    f = MX.parse_pin_cmd(msg, from_map=bool(s.pop('_from_map', False)))
    if not f:
        return None
    if f.get('clear'):
        f = {}
        clear = True
    else:
        clear = False
        f = {**(s.get('_map_filter') or {}), **f}
    s['_map_filter'] = f
    lat, lon, mode = _travel(s)
    now = (s.get('_now') or LN.parse_now())[0]
    res = MX.pins(lat, lon, mode, now, ctx=_map_ctx(s), flt=f)
    text = MX.pin_reply(res, {'clear': True} if clear else f)
    s['mem']['turns'] = (s['mem']['turns'] + [[msg, text[:200]]])[-4:]
    return {'text': text, 'blocks': [{'type': 'map_pins', 'filter': f, 'filter_label': res['filter_label'], 'n': res['n']}], 'engine': 'v3plus-map-pins',
            'related': [], 'questions': [], 'suggestions': [], 'memory': {'chips': _mem_chips(s)}, 'list_hook': None, 'bazaar': None,
            'debug': {'map_pins': {'filter': f, 'n': res['n'], 'ms': res['ms']}},
            'metrics': {'latency_s': round(time.time() - t0, 2), 'llm_calls': 0, 'tokens': 0, 'cost_usd': 0.0}, 'ok': True, 'version': 'v3plus'}

def run_version(v, sid, msg):
    s = _sess(sid, v)
    t0 = time.time()
    if v == 'v3plus':
        try:
            mp = _map_pin_cmd(s, msg, t0)
            if mp: return mp
        except Exception as e:
            print('map pin command failed, using the agent:', type(e).__name__, e, flush=True)
        try:
            cf = _closed_followup(s, msg, t0)
            if cf: return cf
        except Exception as e:
            print('closed follow-up failed, using the agent:', type(e).__name__, e, flush=True)
    uip = (s.get('mission') or {}).get('_ui_project') if v == 'v3plus' else None
    if uip:                      # follow-up about the «خرید یکجا» plan on screen: revise it, never re-plan / re-ask
        s.pop('_answers', None); s.pop('project_pending', None)
        try:
            fu = _project_followup(s, msg, uip, t0)
            if fu:
                s['mission'].pop('_ui_project', None)
                return fu
        except Exception as e:
            print('project follow-up failed, using the agent:', type(e).__name__, e, flush=True)
        s['_no_project_once'] = True          # agent path (e.g. «X رو عوض کن»): start_project disabled for this turn
    elif v == 'v3plus':
        ans = s.pop('_answers', None)
        if PRJ.is_project(msg) or (s.get('project_pending') and ans):
            try:
                out, _r = _project_turn(s, msg, ans, t0)
                if out: return out
            except Exception as e:
                print('project turn failed, falling back to the agent:', type(e).__name__, e, flush=True)
    EC = P.COST if v == 'v3plus' else A.COST
    emb0 = EC['embed']
    try:
        if v == 'current':
            # agent.py is single-turn: the adapter passes the last turns as plain context
            q = msg
            if s['cur_turns']:
                ctx = '\n'.join(f"کاربر: {u}\nدستیار: {a[:400]}" for u, a in s['cur_turns'][-3:])
                q = f"گفتگوی قبلی (برای زمینه):\n{ctx}\n\nپیام جدید کاربر: {msg}"
            with DB_LOCK:
                r = CUR.run_agent(q)
            s['cur_turns'].append((msg, r['final_answer']))
            u = r['usage']
            dbg = {'tool_calls': [{'name': c['name'], 'args': c['args'], 'result_preview': c['result'][:600]} for c in r['tool_calls']],
                   'raw': r.get('raw')}
            out = {'text': r['final_answer'], 'blocks': [], 'engine': 'current', 'debug': dbg}
        else:
            with DB_LOCK:
                _SQL.lst = []
                s['hist'].append({'role': 'user', 'content': msg})
                try:
                    if v == 'v3':
                        r = A.run_agent_v3(s['hist'], session_mission=s['mission'])
                    elif v == 'v3plus':
                        ch = _call_hist(s, msg)
                        P._RUN.on_event = _STREAM_CB.get(sid)        # /api/send_stream progress events (None for /api/send)
                        try:
                            r = P.run_agent_v3plus(ch, session_mission=s['mission'], allow_project=not s.pop('_no_project_once', False),
                                               single_tool_round=False)
                        finally:
                            P._RUN.on_event = None
                    else:
                        r = J.run_agent_jev(s['hist'], mission=s['mission'], enable_check=True)
                except Exception:
                    s['hist'].pop(); raise
                if r.get('project_intent'):          # V3+ agent called start_project: not an answer turn
                    s['hist'].pop(); _SQL.lst = None
                else:
                    s['hist'].append(r['history_entry']); s['mission'] = r['mission']
                    if uip: (s['mission'] or {}).pop('_ui_project', None)    # per-request context only
                    sqls, nsql = _sqls(); _SQL.lst = None
            if r.get('project_intent'):              # -> «خرید یکجا» planner (questions or needs checklist); +1 plan call
                c0 = float(r['usage'].get('cost') or 0); _add_spend(c0)
                pout, _pr = _project_turn(s, msg, None, t0, goal=r.get('project_goal'))
                if pout is None:                     # planner disagreed -> regular agent answer (rare)
                    s['_no_project_once'] = True
                    return run_version(v, sid, msg)
                m_ = pout['metrics']; m_['llm_calls'] = (m_.get('llm_calls') or 1) + (r['usage'].get('api_calls') or 1)
                m_['cost_usd'] = round(float(m_.get('cost_usd') or 0) + c0, 6)
                pout['debug']['project_route'] = {'by': 'agent:start_project', 'goal': r.get('project_goal'), 'agent_cost_usd': round(c0, 6)}
                return pout
            u = dict(r['usage'])
            hl = r.get('hydration_log') or {}
            dbg = {'engine': r.get('engine', 'v3'), 'tool_trace': r.get('tool_trace'),
                   'sql_used (longest first, of %d distinct)' % nsql: sqls,
                   'hydration': {k: hl.get(k) for k in ('kept', 'dropped', 'repaired', 'unverified_price_mentions', 'latin_words_not_in_data', 'fallback', 'fallback_from_jev',
                                                        'product_knowledge', 'db_label_fixed', 'v3plus_appended_notes') if k in hl},
                   'mission': {k: vv for k, vv in (r.get('mission') or {}).items() if k != '_aliases'},
                   'llm_steps': (r.get('usage') or {}).get('llm_steps')}
            if v == 'jev':
                jd = r.get('jev') or {}
                dbg['jev_params'] = jd.get('params')
                dbg['guards'] = jd.get('guards')
                dbg['candidate_categories'] = [c if isinstance(c, str) else (c.get('name') if isinstance(c, dict) else c) for c in (jd.get('candidates') or [])][:40]
                dbg['fetch'] = jd.get('fetch')
                dbg['check'] = jd.get('check') or jd.get('check_error')
                dbg['fallback_reason'] = hl.get('fallback_from_jev')
            out = {'text': r['text'], 'blocks': r['blocks'], 'engine': r.get('engine', v), 'debug': dbg}
            # $0 server-side extras (pure DB): related products for every engine with product ids; V3+ also memory + next prompts
            t1 = time.time()
            out['related'] = _related_for(r['blocks'])
            if v == 'v3plus':
              try:
                prods, shops = _update_mem(s, msg, r)
                out['questions'] = [] if uip else (r.get('questions') or [])     # plan follow-ups never re-ask
                # rule: questions INSTEAD of an answer -> question sheet; questions WITH an answer (products shown) -> refinement chips, no sheet
                if out['questions'] and any(b.get('type') in ('product_cards', 'sellers', 'compare', 'plan') and (b.get('items') or b.get('products'))
                                            for b in (r.get('blocks') or [])):
                    out['refine'] = [{'id': q.get('id'), 'title': q.get('title'), 'options': [o if isinstance(o, str) else str(o.get('label') or '') for o in (q.get('options') or []) if isinstance(o, (str, dict))][:4]}
                                     for q in out['questions'][:2]]
                    out['refine'] = [q for q in out['refine'] if len([o for o in q['options'] if o]) >= 2] or None
                    out['questions'] = []
                _vl = (r.get('hydration_log') or {}).get('v3plus') or {}
                dbg['sanitizer_removed'] = (_vl.get('sanitized_raw') or []) + (_vl.get('sanitized') or [])
                dbg['questions_dropped'] = ((r.get('hydration_log') or {}).get('v3plus') or {}).get('questions_dropped')
                if r.get('engine') != 'v3plus':      # agent.py fallback path: same boilerplate sanitizer
                    out['text'], dbg['sanitized_fallback'] = P.sanitize_boilerplate(out['text'])
                out['suggestions'], dbg['suggestion_sources'] = _suggestions(r.get('suggestions'), r['blocks'], prods, shops, s)
                out['blocks'] = [b for b in out['blocks'] if b.get('type') != 'chips']   # chips merged into suggestions
                out['memory'] = {'chips': _mem_chips(s)}
                out['list_hook'] = _list_hook(r['blocks'])
                used_bz = any((t or {}).get('tool') == 'bazaar_hubs' for t in (r.get('tool_trace') or []))
                if used_bz or re.search(r'کجا (بخرم|بگیرم|پیدا)|بورس|بازار', msg):
                    bz_args = next(((t or {}).get('args') or {} for t in (r.get('tool_trace') or []) if (t or {}).get('tool') == 'bazaar_hubs'), {})
                    out['bazaar'] = BZ.lookup(bz_args.get('need') or msg, bz_args.get('category'))
                if not uip and r.get('engine') == 'v3plus':
                    _late(s, msg, r, out, dbg)
                    _map_after(s, msg, r, out)
                dbg['session_memory_injected'] = {'chars': len(ch[0]['content']), 'approx_tokens': len(ch[0]['content']) // 3, 'turns_sent': (len(ch) - 2) // 2,
                                                  'text': ch[0]['content']}
              except Exception as e:     # extras must never break an answer
                dbg['extras_error'] = f'{type(e).__name__}: {e}'[:200]
            dbg['extras_ms_no_llm'] = int((time.time() - t1) * 1000)
        emb = EC['embed'] - emb0 if v != 'current' else 0.0
        cost = float(u.get('cost') or 0) + max(0.0, emb)
        _add_spend(cost)
        out['metrics'] = {'latency_s': round(time.time() - t0, 1), 'llm_calls': u.get('api_calls'),
                          'tokens': (u.get('prompt_tokens') or 0) + (u.get('completion_tokens') or 0),
                          'prompt_tokens': u.get('prompt_tokens'), 'completion_tokens': u.get('completion_tokens'), 'cost_usd': round(cost, 6)}
        out['ok'] = True
    except Exception as e:
        out = {'ok': False, 'text': f'خطا: {type(e).__name__}: {str(e)[:300]}', 'blocks': [], 'debug': {}, 'metrics': {'latency_s': round(time.time() - t0, 1)}}
    out['version'] = v
    return out

app = FastAPI()

@app.middleware('http')
async def _access_log(request: Request, call_next):
    # timestamped access log (Tehran) with latency: uvicorn's default log has no time, which hid the drawer bug's timeline
    t = time.time()
    try:
        resp = await call_next(request)
        code = resp.status_code
    except Exception as e:
        code = f'EXC {type(e).__name__}'; raise
    finally:
        if not request.url.path.startswith('/pg/static'):
            print(f"[{time.strftime('%H:%M:%S')}] {request.client.host if request.client else '-'} {request.method} {request.url.path} -> {locals().get('code')} {int((time.time() - t) * 1000)}ms", flush=True)
    return resp
def _auth(req: Request):
    if not secrets.compare_digest(req.query_params.get('token', ''), TOKEN):
        raise HTTPException(403, 'token required')

import playground_tryon as TRYON          # virtual try-on (پرو مجازی) via AvalAI: /api/tryon*
TRYON.init(auth=_auth)
app.include_router(TRYON.router)
import playground_mallguide as MALLGUIDE  # «راهنمای رسیدن داخل پاساژ»: /api/shop/{sid}/mallguide (+ /facts)
MALLGUIDE.init(auth=_auth, add_spend=_add_spend, can_spend=lambda need: _cap_ok(need), client_fn=A.client)
app.include_router(MALLGUIDE.router)

@app.get('/')
def root():
    return HTMLResponse('<p dir="rtl">Playground: /playground?token=…</p>')

@app.get('/playground')
def page(req: Request):
    _auth(req)
    return HTMLResponse(open(os.path.join(HERE, 'playground.html'), encoding='utf-8').read())

@app.get('/pg/static/{name}')
def static(name: str, req: Request):
    p = os.path.join(HERE, 'playground_static', os.path.basename(name))
    if not os.path.exists(p): raise HTTPException(404)
    return FileResponse(p, headers={'Cache-Control': 'max-age=86400'})

def _status():
    return {'llm_cost_process_usd': round(A.COST['llm'] + P.COST['llm'], 6), 'embed_cost_process_usd': round(A.COST['embed'] + P.COST['embed'], 6),
            'recall_api_cost_usd': round(getattr(__import__('recall'), 'STATS', {}).get('cost', 0.0), 6),
            'spent_session': round(STATE['spent'], 6), 'calls': STATE['calls'], 'cap_session': SESSION_CAP, 'project_base': PROJECT_BASE,
            'project_total_est': round(PROJECT_BASE + STATE['spent'], 4)}

@app.get('/api/status')
def status(req: Request):
    _auth(req); return _status()

@app.post('/api/send')
async def send(req: Request):
    _auth(req)
    b = await req.json()
    msg = (b.get('message') or '').strip()[:500]
    sid = str(b.get('sid') or 'anon')[:64]
    mode = b.get('mode')
    if not msg: raise HTTPException(400, 'empty message')
    if b.get('new_conversation') and mode == 'v3plus':      # new chat: no mission/memory/topic carried over from an earlier conversation
        SESS.pop((sid, 'v3plus'), None)
    ans = b.get('answers')
    if isinstance(ans, list) and mode == 'v3plus':      # answers to a question card -> remembered preferences (V3+ memory)
        s_ = _sess(sid, 'v3plus')
        s_['_answers'] = [a for a in ans[:3] if isinstance(a, dict)]     # consumed by a pending «خرید یکجا» plan
        for a in ans[:3]:
            if isinstance(a, dict) and a.get('id') and a.get('answer'):
                s_['mem'].setdefault('prefs', {})[re.sub(r'[^a-z0-9_]', '', str(a['id']).lower())[:32]] = {'title': str(a.get('title') or '')[:80], 'answer': str(a['answer'])[:80]}
    ui_area = str(b.get('area') or '').strip()[:40]
    if ui_area and mode == 'v3plus':        # /app location chip: the shopper's chosen Tehran area, passed as a server fact (not a hard filter)
        s_ = _sess(sid, 'v3plus')
        mi_ = s_.get('mission') or {}
        s_['_area_name'] = ui_area
        mi_['_ui_area'] = {'name': ui_area, 'note': 'Tehran area the shopper picked in the app (default ونک); use it for near/nearest-shop questions and as the default area; not a hard filter for other searches'}
        s_['mission'] = mi_
    if mode == 'v3plus':        # current Tehran time (or the test override `now`/`day`) as a server fact; used by the late-night post-step
        s_ = _sess(sid, 'v3plus')
        _now, _ovr = LN.parse_now(b.get('now') or req.query_params.get('now'), b.get('day') or req.query_params.get('day'))
        s_['_now'] = (_now, _ovr)
        mi_ = s_.get('mission') or {}
        mi_['_ui_now'] = {'tehran_time': _now.strftime('%H:%M'), 'weekday': _now.strftime('%a').lower(), 'note': 'current Tehran time (opening hours are checked by the server)'}
        s_['mission'] = mi_
    tr_ = b.get('travel')
    if isinstance(tr_, dict) and mode == 'v3plus':     # /app map onboarding: start point + travel mode (ETA / open-on-arrival)
        s_ = _sess(sid, 'v3plus')
        try:
            s_['_travel'] = {'mode': tr_.get('mode') if tr_.get('mode') in MX.MODES else 'metro',
                             'lat': float(tr_['lat']) if tr_.get('lat') is not None else None, 'lon': float(tr_['lon']) if tr_.get('lon') is not None else None}
        except (TypeError, ValueError):
            pass
    if b.get('from_map') and mode == 'v3plus':
        _sess(sid, 'v3plus')['_from_map'] = True
    ui_shop = str(b.get('shop_id') or '').strip()[:64]
    if ui_shop and mode == 'v3plus':        # /app shop sheet: question about one shop -> its DB facts as a server fact (this request only)
        facts = HOME.shop_facts(ui_shop)
        if facts:
            s_ = _sess(sid, 'v3plus')
            mi_ = s_.get('mission') or {}
            mi_['_ui_shop'] = facts
            s_['mission'] = mi_
            if b.get('product_id') and D.product_head(str(b['product_id'])[:64]):
                s_['_shop_ctx'] = {'shop_id': ui_shop, 'product_id': str(b['product_id'])[:64], 'name': facts.get('name'), 'ts': time.time()}
    ui_proj = b.get('project')
    if isinstance(ui_proj, dict) and mode == 'v3plus':   # /app «خرید یکجا» results screen: the plan on screen, so follow-ups refer to it
        s_ = _sess(sid, 'v3plus')
        mi_ = s_.get('mission') or {}
        mi_['_ui_project'] = {'note': 'The shopper is looking at this «خرید یکجا» plan (computed from the DB) and asks a follow-up about it. Refer to these items/shops/prices; use tools to find cheaper/other options when asked.',
                              'plan': json.dumps(ui_proj, ensure_ascii=False)[:1800]}
        s_['mission'] = mi_
    vers = ['current', 'v3', 'jev', 'v3plus'] if mode == 'compare' else [mode]
    if any(v not in ('current', 'v3', 'jev', 'v3plus') for v in vers): raise HTTPException(400, 'bad mode')
    need = 0.004 * len(vers)
    if STATE['spent'] + need > SESSION_CAP:
        return JSONResponse({'error': f'سقف هزینهٔ این جلسه (${SESSION_CAP}) پر شده است؛ ارسال متوقف شد.', 'status': _status()}, status_code=402)
    import asyncio
    loop = asyncio.get_running_loop()
    with ThreadPoolExecutor(4) as ex:
        res = await asyncio.gather(*[loop.run_in_executor(ex, run_version, v, sid, msg) for v in vers])
    return {'results': res, 'status': _status()}

_STREAM_CB = {}     # sid -> progress callback while a /api/send_stream request runs

def _sse(event, data):
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

@app.post('/api/send_stream')
async def send_stream(req: Request):
    """Same body and same final payload as /api/send, as Server-Sent Events (V3+ only; /api/send is unchanged).
    events: status {stage, n_found?} … -> cards {items[]} (once: the final agent-selected, server-checked product cards, same objects as final)
    -> text {chunk} … -> final {results, status} | error {error}. Raw tool results are never sent as cards."""
    from fastapi.responses import StreamingResponse
    import asyncio
    _auth(req); b = await req.json()
    if b.get('mode') != 'v3plus': raise HTTPException(400, 'send_stream supports mode=v3plus only')
    sid = str(b.get('sid') or 'anon')[:64]
    loop = asyncio.get_running_loop(); q = asyncio.Queue(); sent_cards = []
    _now_s, _ = LN.parse_now(b.get('now') or req.query_params.get('now'), b.get('day') or req.query_params.get('day'))
    defer = LN.maybe_defer(str(b.get('message') or ''), _now_s)   # late-night post-step may replace the cards -> stream them once, from the final
    def cb(kind, data):            # runs in the agent thread
        if kind == 'products':      # contract: raw search results are never streamed as cards
            return
        if kind == 'cards' and defer and False:     # late-night block is additive now: the agent's cards stream as usual
            return
        if kind == 'cards':
            if sent_cards: return   # at most one cards event per turn
            if not (data.get('items') or []): return   # empty agent selection: the final's cards (e.g. late-night block) are streamed once at the end
            sent_cards.append(1)
            data = {'items': data.get('items') or [], 'final': True}
        loop.call_soon_threadsafe(q.put_nowait, (kind, data))
    _STREAM_CB[sid] = cb
    task = asyncio.ensure_future(send(req))       # request body is cached by Starlette, so send() re-reads it
    async def gen():
        t0 = time.time()
        try:
            yield _sse('status', {'stage': 'received', 't_ms': 0})
            while True:
                if task.done() and q.empty(): break
                try:
                    kind, data = await asyncio.wait_for(q.get(), 0.2)
                except asyncio.TimeoutError:
                    continue
                data = dict(data, t_ms=int((time.time() - t0) * 1000))
                yield _sse(kind, data)
            res = task.result()
            if isinstance(res, JSONResponse):
                yield _sse('error', json.loads(res.body)); return
            r0 = (res.get('results') or [{}])[0]
            fin_cards = [it for b in (r0.get('blocks') or []) if b.get('type') == 'product_cards' for it in b.get('items', [])]
            if not sent_cards and fin_cards:      # non-agent paths (plan revision, fallback): same contract, cards before text
                sent_cards.append(1)
                yield _sse('cards', {'items': fin_cards, 'final': True, 't_ms': int((time.time() - t0) * 1000)})
            txt = r0.get('text') or ''
            for i in range(0, len(txt), 40):      # final checked text (server-rendered prices), in small chunks
                yield _sse('text', {'chunk': txt[i:i + 40], 't_ms': int((time.time() - t0) * 1000)})
            yield _sse('final', dict(res, t_ms=int((time.time() - t0) * 1000)))
        except Exception as e:
            yield _sse('error', {'error': f'{type(e).__name__}: {str(e)[:200]}'})
        finally:
            if _STREAM_CB.get(sid) is cb: _STREAM_CB.pop(sid, None)
    return StreamingResponse(gen(), media_type='text/event-stream', headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})

def _sid(req, b=None):
    return str((b or {}).get('sid') or req.query_params.get('sid') or 'anon')[:64]

@app.get('/api/product/{pid}/offers')
def api_offers(pid: str, req: Request):
    _auth(req)
    r = D.product_offers(pid[:64])
    if not r: raise HTTPException(404, 'product not found')
    return r

@app.get('/api/shop/{sid}')
def api_shop(sid: str, req: Request):
    _auth(req)
    r = D.shop(sid[:64])
    if not r: raise HTTPException(404, 'shop not found')
    return r

@app.get('/api/product/{pid}/related')
def api_related(pid: str, req: Request):
    _auth(req)
    if not D.product_head(pid[:64]): raise HTTPException(404, 'product not found')
    k = max(1, min(int(req.query_params.get('k') or 8), 12))
    return {'product_id': pid, 'related': D.related([pid[:64]], k=k), 'llm_calls': 0}

@app.get('/api/product/{pid}/details')
def api_product_details(pid: str, req: Request):
    """full DB record: head fields + images + grouped specs + offer stats (no LLM)"""
    _auth(req)
    d = AB.details(pid[:64])
    if not d: raise HTTPException(404, 'product not found')
    return d

# ------------------------------------------------------------------ «کجای پاساژه؟» + «بسته بود؟ جایگزین بده»
import playground_mall as MALL

# ---------------------------------------------------------------- interactive map (home «نقشه» toggle) — DB + bazaars.json, no LLM
def _map_args(req, b=None):
    qp = req.query_params; b = b or {}
    g = lambda k: b.get(k) if b.get(k) is not None else qp.get(k)
    sid = str(g('sid') or '')[:64]
    s = SESS.get((sid, 'v3plus')) if sid else None
    now = LN.parse_now(g('now'), g('day'))[0]
    mode = g('mode') if g('mode') in MX.MODES else ((s or {}).get('_travel') or {}).get('mode') or 'metro'
    try:
        lat, lon = float(g('lat')), float(g('lon'))
    except (TypeError, ValueError):
        lat, lon, _m = _travel(s) if s else (*HOME.area_point(g('area') or 'ونک'), None)
    return s, now, mode, lat, lon

@app.get('/api/map/hoods')
def api_map_hoods(req: Request):
    _auth(req)
    return MX.hoods()

@app.get('/api/map/pins')
def api_map_pins(req: Request):
    _auth(req)
    s, now, mode, lat, lon = _map_args(req)
    qp = req.query_params
    flt = {}
    if qp.get('only_open') in ('1', 'true'): flt['only_open'] = True
    if qp.get('cheapest') in ('1', 'true'): flt['cheapest'] = True
    if qp.get('hub'): flt['hub'] = qp.get('hub')[:60]
    if qp.get('use_session_filter') in ('1', 'true') and s:
        flt = {**(s.get('_map_filter') or {}), **flt}
    ctx = _map_ctx(s) if s and qp.get('ctx') != '0' else {}
    return MX.pins(lat, lon, mode, now, ctx=ctx, q=qp.get('q') or None, flt=flt)

@app.post('/api/map/filter')
async def api_map_filter(req: Request):
    """the ✕ on the filter pill: clear the session's map filter"""
    _auth(req)
    b = await req.json()
    s = SESS.get((str(b.get('sid') or '')[:64], 'v3plus'))
    if s: s['_map_filter'] = {k: v for k, v in (b.get('filter') or {}).items() if k in ('only_open', 'cheapest', 'hub') and v}
    return {'ok': True}

@app.post('/api/map/command')
async def api_map_command(req: Request):
    """map composer: a pin command is answered here ($0); anything else -> {pin: false} and the app asks it in the chat"""
    _auth(req)
    b = await req.json()
    sid = str(b.get('sid') or '')[:64]
    msg = str(b.get('message') or '').strip()[:200]
    if not sid or not msg:
        raise HTTPException(400, 'sid and message required')
    s = _sess(sid, 'v3plus')
    tr_ = b.get('travel')
    if isinstance(tr_, dict):
        try: s['_travel'] = {'mode': tr_.get('mode') if tr_.get('mode') in MX.MODES else 'metro', 'lat': float(tr_['lat']), 'lon': float(tr_['lon'])}
        except (KeyError, TypeError, ValueError): pass
    if b.get('now') or b.get('day'):
        s['_now'] = LN.parse_now(b.get('now'), b.get('day'))
    s['_from_map'] = True
    r = _map_pin_cmd(s, msg, time.time())
    s.pop('_from_map', None)
    if not r:
        return {'pin': False}
    return {'pin': True, 'text': r['text'], 'filter': r['blocks'][0]['filter'], 'filter_label': r['blocks'][0]['filter_label'], 'n': r['blocks'][0]['n'], 'llm_calls': 0}

@app.post('/api/map/here')
async def api_map_here(req: Request):
    """«اینجا چی داره؟» for a tapped / long-pressed point"""
    _auth(req)
    b = await req.json()
    s, now, mode, ulat, ulon = _map_args(req, {k: b.get(k) for k in ('sid', 'now', 'day', 'mode', 'area')} | {'lat': b.get('ulat'), 'lon': b.get('ulon')})
    try:
        plat, plon = float(b['lat']), float(b['lon'])
    except (KeyError, TypeError, ValueError):
        raise HTTPException(400, 'lat/lon required')
    if not (35.4 < plat < 35.95 and 51.0 < plon < 51.75):
        return {'point': {'lat': plat, 'lon': plon, 'place': None}, 'subtitle': 'این نقطه بیرون از محدودهٔ داده‌های تهرانه', 'shops': [], 'bazaar': None, 'llm_calls': 0}
    return MX.here(plat, plon, ulat, ulon, mode, now, ctx=_map_ctx(s) if s else {})
@app.get('/api/shop/{sid}/place')
def api_shop_place(sid: str, req: Request):
    """parsed mall/floor/unit/block from the DB address + cached web lookup (if any) + route links ($0)"""
    _auth(req)
    r = MALL.place_info(sid[:64])
    if r is None: raise HTTPException(404, 'shop not found')
    return r

@app.post('/api/shop/{sid}/place/find')
def api_shop_place_find(sid: str, req: Request):
    """«پیدا کردن جای دقیق»: one BoxAPI web_search call (cached per shop); accepted only with a cited page naming this shop"""
    _auth(req)
    c = MALL.cached_find(sid[:64])
    if c: return c
    if STATE['spent'] + 0.003 > SESSION_CAP: return {'shop_id': sid, 'status': 'spend_cap', 'llm_calls': 0}
    r = MALL.find_exact(sid[:64], A.client, _add_spend)
    if r is None: raise HTTPException(404, 'shop not found')
    return r

@app.get('/api/shop/{sid}/alternatives')
def api_shop_alternatives(sid: str, req: Request, product_id: str = ''):
    """3 nearest other shops with the same product/model that are open now (or hours unknown); DB only"""
    _auth(req)
    r = MALL.alternatives(sid[:64], product_id[:64] or None)
    if r is None: raise HTTPException(404, 'shop not found')
    return r

@app.post('/api/route/multi')
async def api_route_multi(req: Request):
    """{shops:[{shop_id,lat,lon}], start?:[lat,lon]} -> nearest-neighbour order + Google Maps multi-stop link"""
    _auth(req); b = await req.json()
    st = b.get('start') if isinstance(b.get('start'), list) and len(b.get('start')) == 2 else None
    return MALL.multi_route([x for x in (b.get('shops') or []) if isinstance(x, dict)][:12], tuple(st) if st else None) or {'order': [], 'url': None}

_ABOUT_LOCK = threading.Lock()
@app.get('/api/product/{pid}/about')
def api_product_about(pid: str, req: Request):
    """«دربارهٔ این محصول»: lazy; cached per product on disk; empty sentences => UI hides the section"""
    _auth(req)
    if not D.product_head(pid[:64]): raise HTTPException(404, 'product not found')
    with _ABOUT_LOCK:                       # one search+LLM at a time -> no duplicate spend on double-open
        if STATE['spent'] + 0.002 > SESSION_CAP and not os.path.exists(os.path.join(AB.CACHE_DIR, pid[:64] + '.json')):
            return {'product_id': pid, 'sentences': [], 'sources': [], 'status': 'spend_cap', 'llm_calls': 0}
        r = AB.about(pid[:64], A.client, A._usage_cost, _add_spend)
    if not r: return {'product_id': pid, 'sentences': [], 'sources': [], 'status': 'empty', 'llm_calls': 0}
    out = {k: r.get(k) for k in ('product_id', 'sentences', 'sources', 'status', 'cached', 'llm_calls', 'cost_usd', 'query', 'n_relevant')}
    # which source numbers each sentence cited; older cache entries kept no refs -> refs: [] (never re-calls the LLM)
    out['cited'] = r.get('cited') or [{'text': t, 'refs': []} for t in (r.get('sentences') or [])]
    return out

# ------------------------------------------------------------------ «خرید یکجا» (one-stop project shopping)
def _cap_ok(need=0.004):
    return STATE['spent'] + need <= SESSION_CAP

@app.post('/api/project/plan')
async def api_project_plan(req: Request):
    """{goal, answers?, force?} -> {stage: questions|needs|not_project, questions[], needs[], title, say, assumptions}  (1 LLM call)"""
    _auth(req); b = await req.json()
    goal = str(b.get('goal') or '').strip()[:400]
    if not goal: raise HTTPException(400, 'empty goal')
    if not _cap_ok(): raise HTTPException(402, 'spend cap')
    import asyncio
    r = await asyncio.get_running_loop().run_in_executor(None, lambda: PRJ.plan(goal, b.get('answers'), A.client, A._usage_cost, _add_spend, P.validate_questions, bool(b.get('force'))))
    return r

@app.post('/api/project/search')
async def api_project_search(req: Request):
    """{needs:[…], area?, goal?, summarize?=true} -> {plans[], not_found[], candidates{}, summary}  (search+optimizer: no LLM; summary: 1 tiny call)"""
    _auth(req); b = await req.json()
    needs = [n for n in (b.get('needs') or []) if isinstance(n, dict)][:16]
    if not needs: raise HTTPException(400, 'empty needs')
    import asyncio
    loop = asyncio.get_running_loop()
    def work():
        with DB_LOCK:
            return PRJ.search(needs, (b.get('area') or None))
    r = await loop.run_in_executor(None, work)
    r['summary'], r['summary_usage'] = '', None
    if b.get('summarize', True) and r['plans'] and _cap_ok(0.002):
        try:
            txt, u = await loop.run_in_executor(None, lambda: PRJ.summary(b.get('goal') or '', r, A.client, A._usage_cost, _add_spend, P.fmt_toman_text))
            r['summary'], r['summary_usage'] = P.sanitize_boilerplate(txt)[0], u; r['llm_calls'] = 1
        except Exception as e:
            r['summary_error'] = f'{type(e).__name__}: {str(e)[:100]}'
    return r

@app.post('/api/project/save')
async def api_project_save(req: Request):
    """{cid, name, rows:[{product_id, shop_id, offer_id, qty}]} -> lists state + list_id (feature-3 storage)"""
    _auth(req); b = await req.json()
    rows = [r for r in (b.get('rows') or []) if isinstance(r, dict) and r.get('product_id')][:30]
    if not rows: raise HTTPException(400, 'empty rows')
    cid = b.get('cid')
    lid = _lst(LST.create, cid, (str(b.get('name') or 'خرید یکجا'))[:40])
    n = 0
    for r in rows:
        iid, _, _dup = _lst(LST.add_item, cid, r['product_id'], r.get('shop_id'), r.get('offer_id'), lid)
        q_ = int(r.get('qty') or 1)
        if q_ > 1: _lst(LST.set_qty, cid, iid, q_)
        n += 1
    return dict(_lst(LST.get_all, cid), list_id=lid, n_saved=n)

@app.get('/api/bazaar')
def api_bazaar(req: Request):
    """«بورس این کالا»: ?product_id=… or ?category=… or ?q=<text>"""
    _auth(req)
    cat, q = req.query_params.get('category'), req.query_params.get('q')
    pid = req.query_params.get('product_id')
    if pid:
        h = D.product_head(pid[:64])
        if not h: raise HTTPException(404, 'product not found')
        cat = h['category']; q = q or h['title']
    r = BZ.lookup(q, cat)
    return r or {'group': None, 'hubs': [], 'llm_calls': 0}

@app.get('/api/memory')
def api_memory(req: Request):
    _auth(req)
    s = _sess(_sid(req), req.query_params.get('version') or 'v3plus')
    return {'chips': _mem_chips(s), 'view': _mem_view(s), 'injected': _mem_message(s), 'turns': s['mem']['turns']}

@app.post('/api/memory/select')
async def api_mem_select(req: Request):
    """a card/seller opened in the drawer -> remembered as the user's selection (V3+ memory)"""
    _auth(req)
    b = await req.json()
    v = b.get('version') if b.get('version') in ('v3plus',) else None
    if not v: return {'ok': True, 'ignored': True}
    kind, i = b.get('kind'), str(b.get('id') or '')[:64]
    if kind == 'product': h = D.product_head(i); name = h and h['title']
    elif kind == 'shop': h = D.q('SELECT name FROM shops WHERE shop_id=?', (i,)); name = h and h[0][0]
    else: raise HTTPException(400, 'bad kind')
    if not name: raise HTTPException(404)
    s = _sess(_sid(req, b), v)
    if kind == 'shop' and b.get('product_id') and D.product_head(str(b['product_id'])[:64]):
        s['_shop_ctx'] = {'shop_id': i, 'product_id': str(b['product_id'])[:64], 'name': name, 'ts': time.time()}
    sel = [x for x in s['mem']['selections'] if x['id'] != i] + [{'kind': kind, 'id': i, 'name': D._short(name, 40)}]
    s['mem']['selections'] = sel[-5:]
    return {'ok': True, 'chips': _mem_chips(s)}

@app.post('/api/memory/clear')
async def api_mem_clear(req: Request):
    _auth(req)
    b = await req.json()
    s = _sess(_sid(req, b), b.get('version') or 'v3plus')
    key, mi, m = b.get('key') or 'all', (s.get('mission') or {}), s['mem']
    if key in ('budget', 'all'): mi.pop('budget_toman', None)
    if key in ('area', 'all'): mi.pop('area', None); mi.pop('area_latlon', None)
    if key in ('features', 'all'):
        if isinstance(mi.get('_constraints'), dict): mi['_constraints'].pop('required_terms', None)
    if key in ('category', 'all'): m['category'] = None; mi.pop('goal', None)
    if key in ('products', 'all'): m['products'] = []; m['last_products'] = []; m['shops'] = []; m['last_shops'] = []; mi.pop('selected_product_id', None); mi.pop('selected_shop_id', None)
    if key in ('selections', 'all'): m['selections'] = []
    if key.startswith('pref:'): m.get('prefs', {}).pop(key[5:], None)
    if key == 'all': m['prefs'] = {}
    if key == 'all': m['turns'] = []; s['hist'] = []; mi.pop('_constraints', None); mi.pop('_shown_min_price', None); mi.pop('notes', None)
    s['mission'] = mi
    return {'ok': True, 'chips': _mem_chips(s)}

# ------------------------------------------------------------------ saved lists / virtual basket (no AI)
def _lst(fn, *a, **k):
    try:
        return fn(*a, **k)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except KeyError as e:
        raise HTTPException(404, str(e).strip("'"))

@app.get('/api/lists')
def api_lists(req: Request):
    _auth(req); return _lst(LST.get_all, req.query_params.get('cid'))

@app.post('/api/lists')
async def api_list_create(req: Request):
    _auth(req); b = await req.json()
    lid = _lst(LST.create, b.get('cid'), b.get('name'))
    return dict(_lst(LST.get_all, b.get('cid')), created_list_id=lid)

@app.post('/api/lists/{list_id}/rename')
async def api_list_rename(list_id: str, req: Request):
    _auth(req); b = await req.json(); _lst(LST.rename, b.get('cid'), list_id, b.get('name')); return _lst(LST.get_all, b.get('cid'))

@app.post('/api/lists/{list_id}/delete')
async def api_list_delete(list_id: str, req: Request):
    _auth(req); b = await req.json(); _lst(LST.delete, b.get('cid'), list_id); return _lst(LST.get_all, b.get('cid'))

@app.post('/api/lists/{list_id}/refresh')
async def api_list_refresh(list_id: str, req: Request):
    _auth(req); b = await req.json(); ch = _lst(LST.refresh, b.get('cid'), list_id)
    return dict(_lst(LST.get_all, b.get('cid')), changes=ch)

@app.post('/api/lists/items')
async def api_item_add(req: Request):
    _auth(req); b = await req.json()
    iid, lid, dup = _lst(LST.add_item, b.get('cid'), b.get('product_id'), b.get('shop_id'), b.get('offer_id'), b.get('list_id'))
    return dict(_lst(LST.get_all, b.get('cid')), item_id=iid, list_id=lid, already_saved=dup)

@app.post('/api/lists/items/{item_id}/delete')
async def api_item_del(item_id: str, req: Request):
    _auth(req); b = await req.json(); _lst(LST.remove_item, b.get('cid'), item_id); return _lst(LST.get_all, b.get('cid'))

@app.post('/api/lists/items/{item_id}/move')
async def api_item_move(item_id: str, req: Request):
    _auth(req); b = await req.json(); _lst(LST.move_item, b.get('cid'), item_id, b.get('to_list_id')); return _lst(LST.get_all, b.get('cid'))

@app.post('/api/lists/items/{item_id}/qty')
async def api_item_qty(item_id: str, req: Request):
    _auth(req); b = await req.json(); _lst(LST.set_qty, b.get('cid'), item_id, b.get('qty')); return _lst(LST.get_all, b.get('cid'))

@app.post('/api/reset')
async def reset(req: Request):
    _auth(req)
    b = await req.json()
    sid = str(b.get('sid') or 'anon')[:64]
    for v in (['current', 'v3', 'jev', 'v3plus'] if b.get('version') == 'all' else [b.get('version')]):
        SESS.pop((sid, v), None)
    return {'ok': True}


# ------------------------------------------------------------------ /app: real home page (Vite build in playground_app_dist/), same-origin API
from fastapi.staticfiles import StaticFiles
APP_DIST = os.path.join(HERE, 'playground_app_dist')

@app.get('/app')
@app.get('/app/')
def app_page(req: Request):
    _auth(req)
    return FileResponse(os.path.join(APP_DIST, 'index.html'), headers={'Cache-Control': 'no-store'})

if os.path.isdir(os.path.join(APP_DIST, 'assets')):
    app.mount('/app/assets', StaticFiles(directory=os.path.join(APP_DIST, 'assets')), name='app_assets')

@app.get('/api/home/tiles')
def api_home_tiles(req: Request):
    _auth(req); return HOME.tiles()

@app.get('/api/home/category/{key}')
def api_home_category(key: str, req: Request):
    _auth(req)
    qp = req.query_params
    r = HOME.category(key[:20], (qp.get('sub') or None), max(0, int(qp.get('offset') or 0)), max(1, min(int(qp.get('limit') or 20), 60)))
    if not r: raise HTTPException(404, 'unknown tile')
    return r

@app.get('/api/home/deals')
def api_home_deals(req: Request):
    _auth(req); return HOME.deals(max(1, min(int(req.query_params.get('limit') or 10), 40)))

@app.get('/api/home/areas')
def api_home_areas(req: Request):
    _auth(req); return HOME.areas()

@app.get('/api/home/shops')
def api_home_shops(req: Request):
    _auth(req)
    qp = req.query_params
    return HOME.map_shops(qp.get('area') or 'ونک', qp.get('tile') or None, qp.get('q') or None, max(1, min(int(qp.get('limit') or 80), 150)))

# /app product + shop screens (additive, DB-only, no LLM)
@app.get('/api/home/cards')
def api_home_cards(req: Request):
    _auth(req)
    ids = [x for x in (req.query_params.get('ids') or '').split(',') if x.startswith('product_')][:12]
    return HOME.card_info(ids)

@app.get('/api/home/sellers/{pid}')
def api_home_sellers(pid: str, req: Request):
    _auth(req)
    r = HOME.sellers(pid[:64], req.query_params.get('area') or None)
    if not r: raise HTTPException(404, 'product not found')
    return r

@app.get('/api/home/shop/{shop_id}')
def api_home_shop(shop_id: str, req: Request):
    _auth(req)
    r = HOME.shop_plus(shop_id[:64], (req.query_params.get('product_id') or None))
    if not r: raise HTTPException(404, 'shop not found')
    return r
