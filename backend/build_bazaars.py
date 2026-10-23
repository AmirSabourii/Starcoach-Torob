"""Tehran bazaars ("بورس") from the DB: for each category group, cluster the locations of shops that have offers in that
group (weighted by offers), take concentration hubs, and name a hub ONLY with evidence: the most-mentioned candidate
place in the hub shops' own addresses (>=20% of hub shops) AND the candidate's coordinates within 1 km of the hub centre.
Output: bazaars.json. No LLM."""
import json, math, re, sqlite3, statistics, collections, time
DB = '/workspace/torob/eval/torob.sqlite'
c = sqlite3.connect(DB)

GROUPS = {
  'برق ساختمان و روشنایی': r'سیم و کابل برق|کلید و پریز|کلید و فیوز|فیوز|چراغ|لامپ|روشنایی|پروژکتور|ریسه|لوستر|کنتاکتور|رله|تابلو و جعبه برق|کابلشو|داکت|سیم سیار|کلید اتوماتیک|کلید حرارتی|ترمینال|لوله و خرطومی برق|آباژور',
  'دوربین مداربسته و امنیتی': r'دوربین مدار بسته|نظارتی|دزدگیر|آیفون صوتی|دوربین امنیتی',
  'موبایل و لوازم جانبی': r'گوشی موبایل|کیف و کاور گوشی|محافظ صفحه نمایش گوشی|شارژر گوشی|پاوربانک|باتری گوشی|تاچ و ال سی دی|قاب، شاسی و درب گوشی|فلت و برد گوشی|پایه نگهدارنده گوشی|کابل و تبدیل',
  'کامپیوتر و لپ‌تاپ': r'لپ تاپ|کامپیوتر|مانیتور|کیبورد|ماوس|هارد|کارت گرافیک|پردازنده|مادربرد|پرینتر|کارتریج|روتر|مودم|کابل شبکه|رک شبکه|سوییچ و اسپلیتر|حافظه رم|فلش مموری',
  'ابزار و صنعتی': r'ابزار|دریل|پیچ گوشتی|فرز|اره|آچار|جوش|کمپرسور|پنوماتیک|بلبرینگ|پمپ|الکتروموتور|اینورتر|سیم لخت',
  'مبلمان': r'مبل|صندلی|میز|کمد|تخت خواب|کاناپه|کتابخانه|جاکفشی',
  'پوشاک و کفش': r'پیراهن|شلوار|تیشرت|کفش|کتانی|مانتو|کاپشن|کراوات|لباس|کیف و کوله|جوراب',
  'ساعت': r'ساعت مچی|ساعت دیواری|ساعت و مچ بند هوشمند',
  'لوازم خانگی': r'یخچال|لباسشویی|ظرفشویی|جارو برقی|جاروبرقی|اتو|مایکروویو|کولر|بخاری|اجاق|سرخ کن|غذاساز|چای ساز|قهوه ساز|تلویزیون|هواکش',
  'عطر و آرایشی': r'عطر|ادکلن|آرایش|رژ لب|ریمل|کرم|رنگ مو|ماسک پوستی',
}
# candidate names: coordinates from shop addresses that mention them (median, >=10 shops) or the agents' area table
CANDS = ['لاله زار', 'علاءالدین', 'چارسو', 'جمهوری', 'حافظ', 'منوچهری', 'سعدی', 'امیرکبیر', 'استانبول', 'مخبرالدوله', 'بازار بزرگ', 'ارگ',
         'فردوسی', 'بهارستان', 'ناصرخسرو', 'امین حضور', 'پایتخت', 'شوش', 'یافت آباد', 'ولیعصر', 'تجریش', 'شیخ هادی', 'باغ فیض', 'آسمان']
ALIASES = {'لاله زار': ['لاله زار', 'لاله‌زار', 'لالهزار'], 'علاءالدین': ['علاءالدین', 'علالدین', 'علاالدین'], 'ناصرخسرو': ['ناصرخسرو', 'ناصر خسرو'],
           'امین حضور': ['امین حضور'], 'یافت آباد': ['یافت آباد', 'یافت‌آباد'], 'بازار بزرگ': ['بازار بزرگ']}
TOPIC = {'لاله زار': 'برق/روشنایی', 'علاءالدین': 'موبایل', 'چارسو': 'موبایل', 'پایتخت': 'کامپیوتر', 'امین حضور': 'ابزار/صنعتی', 'ناصرخسرو': 'ابزار/صنعتی',
         'یافت آباد': 'مبل', 'جمهوری': 'کامپیوتر/الکترونیک', 'حافظ': 'کامپیوتر/الکترونیک'}

import agent_v3 as A   # geocode table only (no LLM)
def km(a, b, c_, d):
    return 6371 * 2 * math.asin(math.sqrt(math.sin(math.radians(c_ - a) / 2) ** 2 + math.cos(math.radians(a)) * math.cos(math.radians(c_)) * math.sin(math.radians(d - b) / 2) ** 2))

cand = {}
for n in CANDS:
    al = ALIASES.get(n, [n])
    rows = []
    for a in al:
        rows += c.execute('SELECT lat,lon FROM shops WHERE address LIKE ? AND lat IS NOT NULL', (f'%{a}%',)).fetchall()
    if len(rows) >= 10:
        cand[n] = {'lat': round(statistics.median(r[0] for r in rows), 5), 'lon': round(statistics.median(r[1] for r in rows), 5),
                   'source': f'median of {len(rows)} shop addresses mentioning it', 'aliases': al}
    else:
        g = A.tool_geocode_area(n)
        if g.get('found') and g.get('lat'):
            cand[n] = {'lat': g['lat'], 'lon': g['lon'], 'source': 'agents area table (approx. centre)', 'aliases': al}

shops = {r[0]: r for r in c.execute('SELECT shop_id,name,address,lat,lon,location_label FROM shops WHERE lat IS NOT NULL')}
cats = [r[0] for r in c.execute('SELECT DISTINCT category_name FROM products WHERE category_name IS NOT NULL')]
out = {'built_at': time.strftime('%Y-%m-%dT%H:%M:%S+0330'), 'method': __doc__.strip(), 'candidates': cand, 'groups': []}
CELL = 0.004   # ~400 m
for g, rx in GROUPS.items():
    gcats = [x for x in cats if re.search(rx, x)]
    if not gcats:
        continue
    q = f"SELECT o.shop_id, COUNT(*) FROM offers o JOIN products p USING(product_id) WHERE p.category_name IN ({','.join('?' * len(gcats))}) GROUP BY o.shop_id"
    w = {sid: n for sid, n in c.execute(q, gcats) if sid in shops}
    tot_off, tot_shops = sum(w.values()), len(w)
    grid = collections.Counter()
    for sid, n in w.items():
        grid[(round(shops[sid][3] / CELL), round(shops[sid][4] / CELL))] += n
    hubs, used = [], set()
    for cell, _ in grid.most_common():
        if len(hubs) >= 3 or cell in used:
            continue
        clat, clon = cell[0] * CELL, cell[1] * CELL
        mem = [sid for sid in w if sid not in used and km(clat, clon, shops[sid][3], shops[sid][4]) <= 0.7]
        if not mem:
            continue
        n_off = sum(w[s] for s in mem)
        if n_off < 0.08 * tot_off or len(mem) < 5:
            continue
        lat = sum(shops[s][3] * w[s] for s in mem) / n_off; lon = sum(shops[s][4] * w[s] for s in mem) / n_off
        used |= set(mem)
        for cc in list(grid):
            if km(cc[0] * CELL, cc[1] * CELL, lat, lon) <= 0.7: used.add(cc)
        # evidence for a name: address mentions among hub shops + distance
        ment = collections.Counter()
        for s in mem:
            addr = shops[s][2] or ''
            for n, cd in cand.items():
                if any(a in addr for a in cd['aliases']): ment[n] += 1
        labels = collections.Counter(shops[s][5] for s in mem if shops[s][5])
        name, ev = None, None
        for n, k in ment.most_common():
            d = km(lat, lon, cand[n]['lat'], cand[n]['lon'])
            if k >= 0.2 * len(mem) and d <= 1.0:
                name, ev = n, f'{k} of {len(mem)} hub shops mention «{n}» in their address; candidate centre {d:.2f} km from hub centre ({cand[n]["source"]})'
                break
        also = [n for n, k in ment.most_common() if n != name and n in ('علاءالدین', 'چارسو', 'پایتخت', 'بازار بزرگ', 'امین حضور', 'ناصرخسرو', 'استانبول', 'منوچهری', 'سعدی')
                and k >= 0.1 * len(mem) and km(lat, lon, cand[n]['lat'], cand[n]['lon']) <= 1.0][:2]
        top = sorted(mem, key=lambda s: -w[s])[:8]
        hn = name or (labels.most_common(1)[0][0] if labels else None)
        prev = next((h for h in hubs if h['hub_name'] == hn), None)
        if prev:     # same named area split into two grid hubs -> one hub
            prev['shop_count'] += len(mem); prev['offer_count'] += n_off; prev['share_of_group_offers'] = round(prev['offer_count'] / tot_off, 3)
            prev['share_of_group_shops'] = round(prev['shop_count'] / tot_shops, 3); prev['merged_subhubs'] = prev.get('merged_subhubs', 1) + 1
            continue
        hubs.append({'hub_name': hn, 'display_name': hn + (f" ({' و '.join(also)})" if also else ''), 'also_mentioned': also, 'named_by': 'address_mentions+distance' if name else 'majority shops.location_label',
                     'known_for': TOPIC.get(name) if name else None,
                     'center': {'lat': round(lat, 5), 'lon': round(lon, 5)}, 'radius_km': 0.7, 'shop_count': len(mem), 'offer_count': n_off,
                     'share_of_group_offers': round(n_off / tot_off, 3), 'share_of_group_shops': round(len(mem) / tot_shops, 3),
                     'top_address_mentions': ment.most_common(4), 'location_labels': labels.most_common(3),
                     'sample_shop_ids': top, 'sample_shops': [{'shop_id': s, 'name': shops[s][1], 'n_offers_in_group': w[s]} for s in top[:5]],
                     'evidence': ev or f'{len(mem)} shops with {n_off} offers within 0.7 km; no candidate bazaar name met the address+distance test'})
    out['groups'].append({'group': g, 'category_pattern': rx, 'n_categories': len(gcats), 'shops_total': tot_shops, 'offers_total': tot_off, 'hubs': hubs})
json.dump(out, open('/workspace/torob/eval/bazaars.json', 'w'), ensure_ascii=False, indent=1)
for gr in out['groups']:
    print(gr['group'], gr['shops_total'], gr['offers_total'], [(h['display_name'], h['named_by'][:7], h['shop_count'], h['share_of_group_offers'], h['top_address_mentions'][:2]) for h in gr['hubs']])
print({k: (v['lat'], v['lon'], v['source'][:30]) for k, v in cand.items()})
