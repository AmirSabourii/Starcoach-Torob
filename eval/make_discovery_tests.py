"""Discovery / browsing tests with DB-computed ground truth -> discovery_tests.json"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "..", "backend", "app", "engine")))
import json, statistics, sqlite3
from gt_lib import connect, shop_offers
con = connect()
KNOCK = ('طرح', 'کپی', 'های کپی', 'replica')


def pmin(pid):
    ps = sorted(r['price_toman'] for r in shop_offers(pid))
    if not ps:
        return None
    med = statistics.median(ps)
    return next(p for p in ps if p >= 0.4 * med)


def cat_items(cat_like, where='', args=(), exact=False):
    op = '=' if exact else 'LIKE'
    rows = con.execute(f'''SELECT p.product_id, p.persian_title, p.brand_name, p.category_name, s.n_shops FROM products p JOIN product_stats s USING(product_id)
                          WHERE p.category_name {op} ? AND s.n_priced>0 {where}''', (cat_like, *args)).fetchall()
    out = []
    for pid, t, b, c, n in rows:
        if any(k in t for k in KNOCK):
            continue
        m = pmin(pid)
        if m:
            out.append({'product_id': pid, 'title': t, 'brand': b, 'category': c, 'n_shops': n, 'plausible_min': m})
    return sorted(out, key=lambda r: r['plausible_min'])


def shops_where(sql, args=()):
    return [dict(shop_id=a, shop_name=b) for a, b in con.execute(sql, args).fetchall()]


T = []
def add(id, kind, q, criteria, gt=None, budget=None, mode='shortlist_or_clarify'):
    T.append(dict(id=id, kind=kind, question=q, budget_toman=budget, mode=mode, criteria=criteria, ground_truth=gt or {}))


gaming = [r for c in ('دیسک بازی پلی استیشن', 'دسته بازی (گیم پد)', 'لوازم جانبی کنسول') for r in cat_items(c, exact=True)]
g5 = [r for r in gaming if r['plausible_min'] <= 5e6]
add('D01', 'vague', 'یه کادو زیر ۵ میلیون برای یه نفر که عاشق گیمه چی بخرم؟',
    'small grounded shortlist (2-8) of real gaming items each <=5M, or ONE clarifying question; no invented items',
    {'n_gaming_items_under_5M': len(g5), 'examples': g5[:3] + g5[-3:]}, budget=5e6)
add('D02', 'vague', 'نمی‌دونم چی می‌خوام، یه چیز جالب تکنولوژی نشونم بده',
    'ONE clarifying question (budget/interest) or a small grounded shortlist; no dump, no invented items')
hp = cat_items('هدفون، هدست و هندزفری', exact=True)
hp3 = [r for r in hp if r['plausible_min'] <= 3e6]
add('D03', 'budget', 'یه هندزفری خوب می‌خوام بودجه‌ام ۳ میلیونه',
    '2-8 real headphones/earbuds with real prices <=3M (or ONE clarifying question about wired/wireless)', {'n_under_3M': len(hp3), 'examples': hp3[-5:]}, budget=3e6)
br = con.execute("SELECT brand_name, COUNT(*) FROM products WHERE category_name='لپ تاپ و نوت بوک' AND brand_name IS NOT NULL GROUP BY 1 ORDER BY 2 DESC").fetchall()
add('D04', 'category_browse', 'چه برندهایی لپتاپ دارید؟', 'names >=3 real laptop brands from the catalogue, none that are absent',
    {'brands': [{'brand': b, 'n_products': n} for b, n in br],
     'absent_brands': ['هواوی', 'huawei', 'گیگابایت', 'gigabyte', 'ریزر', 'razer', 'توشیبا', 'toshiba', 'شیائومی', 'xiaomi', 'هونور', 'honor']}, mode='list')
cons = [r for c in ('کنسول بازی  PS5', 'کنسول بازی Xbox', 'کنسول بازی  PS4', 'سایر کنسول بازی') for r in cat_items(c, exact=True)]
add('D05', 'category_browse', 'تو دسته‌ی کنسول بازی چیا هست؟', 'mentions >=2 real console families (PS5/Xbox/PS4/Nintendo...) with real prices; no dump',
    {'n_consoles': len(cons), 'families_present': ['ps5', 'xbox', 'ps4'] + (['nintendo'] if any('نینتندو' in r['title'] or 'nintendo' in r['title'].lower() for r in cons) else [])}, mode='list')
tv = cat_items('تلویزیون', exact=True)
add('D06', 'category_browse', 'ارزون‌ترین تلویزیون‌هاتون؟', 'lists cheapest real TVs; must include at least one of the 3 cheapest plausible TV prices',
    {'cheapest5': tv[:5]}, mode='list')
ph = [r for r in cat_items('گوشی موبایل', exact=True) if r['plausible_min'] <= 20e6]
add('D07', 'budget', 'با ۲۰ میلیون چه گوشی‌هایی می‌تونم بخرم؟', '2-8 real phones each <=20M, knock-offs excluded',
    {'n_phones_under_20M': len(ph), 'top_under_budget': ph[-6:]}, budget=20e6)
ferd = shops_where("SELECT shop_id, name FROM shops WHERE location_label='فردوسی' OR address LIKE '%میدان فردوسی%'")
add('D08', 'store_browse', 'نزدیک میدان فردوسی چه فروشگاه‌هایی هست؟', 'names >=2 real shops located around Ferdowsi (area label/address), <=12 names, or asks what they want to buy',
    {'n_shops': len(ferd), 'shop_ids': [s['shop_id'] for s in ferd]}, mode='store_list')
inst = shops_where("SELECT DISTINCT s.shop_id, s.name FROM shops s JOIN shop_payment_options p USING(shop_id) WHERE p.provider_name IN ('اسنپ‌پی','ترب‌پی','دیجی پی','تارا','ازکی‌وام')")
add('D09', 'store_browse', 'کدوم فروشگاه‌ها پرداخت قسطی دارن؟', 'names >=2 real BNPL shops + provider names (or asks area/category), <=12 names',
    {'n_shops': len(inst), 'shop_ids': [s['shop_id'] for s in inst], 'providers': ['اسنپ‌پی', 'ترب‌پی', 'دیجی پی', 'تارا', 'ازکی‌وام']}, mode='store_list')
ap = [r for r in hp if ('ایرپاد' in r['title'] or 'airpods' in r['title'].lower()) and r['brand'] == 'اپل' and r['plausible_min'] > 5e6 and 'p9' not in r['title'].lower() and not any(w in r['title'] for w in ('گوش چپ', 'گوش راست', 'اوپن باکس', 'استوک', 'کیس'))]  # drop clones like 'P9' mislabeled as Apple
ap_min = min(r['plausible_min'] for r in ap)
add('D10', 'similar_cheaper', 'چیزی شبیه ایرپاد ولی ارزون‌تر؟', 'suggests >=2 real non-Apple, non-knock-off wireless earbuds cheaper than genuine AirPods',
    {'cheapest_genuine_airpods': min(ap, key=lambda r: r['plausible_min']), 'airpods_min_price': ap_min}, budget=ap_min)
sw = [r for r in cat_items('ساعت و مچ بند هوشمند', exact=True) if r['plausible_min'] <= 10e6]
add('D11', 'budget', 'یه ساعت هوشمند خوب تا ۱۰ میلیون معرفی کن', '2-8 real smartwatches each <=10M (or ONE clarifying question about phone OS)',
    {'n_under_10M': len(sw), 'examples': sw[-5:]}, budget=10e6)
add('D12', 'vague', 'یه اسپیکر بلوتوثی برای مهمونی می‌خوام', 'ONE clarifying question (budget/size) or 2-8 real speakers with prices')
sam = [r for r in cat_items('گوشی موبایل', exact=True) if r['brand'] == 'سامسونگ' or 'سامسونگ' in r['title']]
sam_smart = [r for r in sam if 'مگابایت' not in r['title'] and 'سامسونگ' in r['title'] and r['plausible_min'] >= 25e6]  # genuine Samsung smartphones; sub-25M Galaxy flagships are clone listings
add('D13', 'category_browse', 'گوشی سامسونگ ارزون چی دارید؟', 'lists real cheap Samsung phones; includes one of the 3 cheapest genuine Samsung prices (basic phones) or one of the 3 cheapest Samsung smartphones',
    {'cheapest5': sam[:5], 'cheapest5_smartphones': sam_smart[:5]}, mode='list')
sk = shops_where("""SELECT DISTINCT s.shop_id, s.name FROM shops s JOIN offers o USING(shop_id) JOIN products p USING(product_id)
                    WHERE (s.location_label='شیخ هادی' OR s.address LIKE '%شیخ هادی%') AND p.category_name LIKE '%کنسول بازی%' AND o.price_toman IS NOT NULL""")
add('D14', 'store_browse', 'کدوم فروشگاه‌های شیخ هادی کنسول بازی دارن؟', 'names >=1 real Sheikh-Hadi shop (area label or address) with console offers, no shop outside that set',
    {'n_shops': len(sk), 'shop_ids': [s['shop_id'] for s in sk]}, mode='store_list_strict')
add('D15', 'vague', 'یه چیزی برای خونه می‌خوام', 'very vague: ONE clarifying question (what kind/budget) or <=5 grounded items; no dump')
json.dump({'n': len(T), 'tests': T}, open('discovery_tests.json', 'w'), ensure_ascii=False, indent=1)
for t in T:
    print(t['id'], t['question'], {k: (v if not isinstance(v, list) else len(v)) for k, v in t['ground_truth'].items() if k not in ('examples', 'cheapest5', 'top_under_budget')})
print('cheapest TVs', [(r['title'][:30], r['plausible_min']) for r in tv[:3]], 'samsung', [(r['title'][:30], r['plausible_min']) for r in sam[:3]], 'airpods', ap_min)
