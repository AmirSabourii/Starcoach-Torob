#!/usr/bin/env python3
"""Author eval questions and compute ground truth directly via SQL on torob.sqlite. No LLM calls.
Outputs eval_set.json and eval_set.md. Deterministic / idempotent."""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "..", "backend", "app", "engine")))
import json, os, re
from gt_lib import *

HERE = os.path.dirname(os.path.abspath(__file__))
ITEMS = []
LOC = {  # realistic user positions inside the dataset bbox (lat 35.64–35.81, lon 51.31–51.51)
    'tajrish': (35.8044, 51.4337, 'میدان تجریش'),
    'saadatabad': (35.7775, 51.3540, 'شهرک غرب / سعادت‌آباد (نزدیک خوشه آسمان)'),
    'jannatabad': (35.7385, 51.3100, 'جنت‌آباد جنوبی'),
    'valiasr': (35.7117, 51.4069, 'میدان ولیعصر'),
    'tehranpars': (35.7300, 51.5200, 'تهرانپارس'),
    'kianshahr': (35.6420, 51.4450, 'کیانشهر'),
    'enghelab': (35.7009, 51.3910, 'میدان انقلاب'),
    'ferdowsi': (35.7013, 51.4204, 'میدان فردوسی'),
}
P = {  # product ids chosen from exploration (see data_findings.md)
    's25fe': 'product_6c62d575e3d247f6f29e051a', 'a56_256': 'product_e743ce86bbc5c2a0c9bd16f4',
    'a17_128_4': 'product_d24b597176bdf2a82035dcc2', 'redmi_n15': 'product_519f1ee3c5057b0b1f98d9d4',
    'poco_x7pro': 'product_175c8e43d2bd61614f667e3a', 'ip16_128': 'product_76d08413c6fa1d8efc4cea19',
    'ip17_256': 'product_497ca33998585791fa1bd139', 'charger20_a': 'product_df1dfb162403cf73df70fdf3',
    'charger20_b': 'product_99316b03484cd879f989633b', 'silex_lite': 'product_ea14709af5027eb47228dae3',
    'silex_805': 'product_98c1e1a7d51493c9d1cf80dd', 'aura5': 'product_241eb5d0978b4382eddeeddf',
    'stage320': 'product_5ed27d0acc3f28d667f5abef', 'ps5_dig': 'product_fef87f08e57d174809f5dc93',
    'ps5_std': 'product_d979f62ee7d610cd5a71b9f0', 'ps5_pro': 'product_276a0d054f2f0174819277bc',
    'xbox_s': 'product_1810be1d3dd6fbd02d38b4c0', 'xbox_x': 'product_6b6c2d4adff0a28917d7952e',
    'airpods_pro3_a': 'product_13dcd3e74bde3139871f4b7f', 'airpods_pro3_b': 'product_e4516e047e6d6a15b53ae808',
    'airpods4_anc': 'product_af79a481acdade4e9d1460fe', 'anker_lib5': 'product_2c4c5fe50cb2c8305ca7e3e2',
    'watch11': 'product_7e355a8fc49afcd4df77a875', 'sony65': 'product_331f30694cc0c5fed285a4c1',
    'mi_tv65': 'product_2b26b9cf3b3279ce39630a32', 'contactor_lc1d09': 'product_a338cc47f344fc7dd94aaf4a',
}


def add(id_, cat, q, gt, must, difficulty='medium', loc=None, notes=None):
    it = {'id': id_, 'category': cat, 'difficulty': difficulty, 'question': q}
    if loc:
        lat, lon, label = LOC[loc]
        it.update(user_lat=lat, user_lon=lon, user_location_label=label)
    it['ground_truth'] = gt
    it['correct_answer_must'] = must
    if notes:
        it['notes'] = notes
    ITEMS.append(it)


def ps(key):
    return price_summary(P[key])

# ---------------------------------------------------------------- 1. simple lookup
add('L01', 'simple_lookup', 'قیمت گوشی سامسونگ S25 FE با حافظه ۲۵۶ و رم ۸ چنده؟',
    {'expected_product_ids': [P['s25fe']], 'price_summary': ps('s25fe')},
    'Identify product_6c62…; quote a price range from the dataset (min ≈ 184,000,000 toman, max ≈ 223,675,000) and/or the cheapest shop; mention it is sold in many (34) shops. No invented prices.', 'easy')
add('L02', 'simple_lookup', 'آیفون ۱۶ معمولی ۱۲۸ گیگ نات‌اکتیو چند درمیاد؟',
    {'expected_product_ids': [P['ip16_128']], 'price_summary': ps('ip16_128')},
    'Quote the dataset price range for the iPhone 16 128GB Not-Active product; must not use iPhone 16 Pro/Pro Max or "طرح اپل" knock-off prices. Should note outlier spread (min 175M vs median).', 'easy')
add('L03', 'simple_lookup', 'قیمت ایرپاد پرو ۳ چقدره؟',
    {'expected_product_ids': [P['airpods_pro3_a'], P['airpods_pro3_b']],
     'price_summary': [ps('airpods_pro3_a'), ps('airpods_pro3_b')]},
    'Two catalogue entries share the title "هدفون بی سیم اپل مدل ایرپاد پرو 3"; correct answer quotes ~60.5M–68M toman. A 3.1M offer exists on the second entry and is an implausible outlier (likely a copy/part) – answer must not present 3.1M as the normal price without caveat. Must not quote AirPods Pro 2 / AirPods 4.', 'medium')
add('L04', 'simple_lookup', 'PS5 Pro دیجیتال الان چنده؟',
    {'expected_product_ids': [P['ps5_pro']], 'price_summary': ps('ps5_pro')},
    'Quote dataset price range for "کنسول بازی سونی PS5 Pro Digital" (≈319.9M–385M toman). Must not confuse with PS5 Slim.', 'easy')
add('L05', 'simple_lookup', 'ردمی نوت ۱۵ با ۲۵۶ گیگ حافظه قیمتش چنده؟',
    {'expected_product_ids': [P['redmi_n15']], 'price_summary': ps('redmi_n15'),
     'distractors_to_avoid': [r['product_id'] for r in search("p.category_name='گوشی موبایل' AND p.title_norm LIKE '%redmi note 15%' AND p.product_id<>?", (P['redmi_n15'],))]},
    'Must pick Redmi Note 15 256/8 (not Note 15 Pro / Pro+). Quote ≈84.9M–109M range.', 'easy')
add('L06', 'simple_lookup', 'Apple Watch Series 11 42mm چند؟',
    {'expected_product_ids': [P['watch11']], 'price_summary': ps('watch11')},
    'English query must map to the Persian title "ساعت هوشمند اپل واچ سری ۱۱ آلومینیوم ۴۲ میلی‌متری…"; quote ≈84M–99.5M.', 'medium')
add('L07', 'simple_lookup', 'اسپیکر هارمن کاردن Aura Studio 5 کجا و چند می‌فروشن؟',
    {'expected_product_ids': [P['aura5']], 'price_summary': ps('aura5'), 'cheapest': cheapest(P['aura5'])},
    'Quote cheapest shop + price and a plausible range; the 680M max is a clear outlier (≫ median) and should not be presented as typical.', 'medium')

# ---------------------------------------------------------------- 2. filtered search
def fs(where, args=()):
    rows = search(where, args)
    return {'n_matching_products': len(rows), 'expected_product_ids': [r['product_id'] for r in rows],
            'cheapest_5': rows[:5]}

g = fs("p.category_name='گوشی موبایل' AND p.brand_name='سامسونگ' AND s.min_price<=?", (60_000_000,))
add('S01', 'filtered_search', 'گوشی سامسونگ زیر ۶۰ میلیون تومن چی هست؟',
    g | {'filter': "category=گوشی موبایل AND brand=سامسونگ AND cheapest valid offer <= 60,000,000"},
    'Every product listed must be in expected_product_ids (precision) and quoted price must be ≤60M from a real offer. Listing several real options (e.g. Galaxy A07 64/4 from ≈38.9M) is sufficient; must not list accessories or non-Samsung phones.', 'medium')
g = fs("p.category_name='ساعت و مچ بند هوشمند' AND p.brand_name='شیائومی' AND s.min_price<=?", (10_000_000,))
add('S02', 'filtered_search', 'ساعت هوشمند شیائومی تا ۱۰ میلیون پیشنهاد بده', g,
    'Recommend only products from expected_product_ids with a real offer ≤10M (e.g. Redmi Watch 5 Lite ≈9.4M, Redmi Watch 5 Active ≈6.78M, Mi Band 10 ≈8.9M).', 'medium')
g = fs("p.category_name='تلویزیون' AND regexp('(^|[^0-9.])55([^0-9]|$)', p.title_norm) AND s.min_price<=?", (120_000_000,))
add('S03', 'filtered_search', 'تلویزیون ۵۵ اینچ زیر ۱۲۰ میلیون می‌خوام، چه گزینه‌هایی هست؟', g,
    'All suggestions must be 55-inch TVs from expected_product_ids priced ≤120M (title-based size filter). Must not suggest 50/65-inch or TV stands.', 'hard',
    notes='Size filter is title-based (digits normalised); a model doing spec-based filtering may legitimately find a superset — grade by precision.')
g = fs("p.category_name='هدفون، هدست و هندزفری' AND p.brand_name='انکر' AND s.min_price<=?", (3_000_000,))
add('S04', 'filtered_search', 'هندزفری یا هدفون انکر زیر ۳ میلیون سراغ داری؟', g,
    'Only Anker headphones in expected_product_ids with a real offer ≤3M (e.g. Soundcore R50i from 1.39M).', 'medium')
g = fs("p.category_name='کولر گازی' AND p.title_norm LIKE '%اینورتر%' AND (p.title_norm LIKE '%24000%' OR p.title_norm LIKE '%24 هزار%') AND s.min_price IS NOT NULL")
add('S05', 'filtered_search', 'کولر گازی اینورتر ۲۴ هزار چه مدل‌هایی دارید و قیمتشون چنده؟', g,
    'List inverter 24000-BTU AC models from expected_product_ids with their real cheapest price. Must not include non-inverter models or 12/30k units.', 'hard')
g = fs("p.category_name='لپ تاپ و نوت بوک' AND p.brand_name='ایسوس' AND s.min_price<=?", (150_000_000,))
add('S06', 'filtered_search', 'لپ‌تاپ ایسوس تا ۱۵۰ میلیون تومن چی موجوده؟', g,
    'Only ASUS laptops from expected_product_ids with real offer ≤150M; if few, say so honestly.', 'medium')
g = fs("p.category_name='اسپیکر و سیستم صوتی' AND p.brand_name='جی بی ال' AND s.min_price<=? AND s.n_shops>=5", (20_000_000,))
add('S07', 'filtered_search', 'اسپیکر بلوتوثی JBL زیر ۲۰ میلیون که تو چند تا مغازه باشه می‌خوام', g | {'filter': 'brand=جی بی ال, category=اسپیکر و سیستم صوتی, min price ≤20M, carried by ≥5 shops'},
    'Suggestions must come from expected_product_ids (e.g. JBL GO4 from 5.5M, Go 5 ≈8.1M, Clip 5 ≈8.9M, Flip 7 ≈19.53M). Bonus: mention number of shops.', 'medium')

# ---------------------------------------------------------------- 3. nearest stores
def near_item(id_, q, key_or_pids, loc, k=3, must='', diff='medium', extra=''):
    pids = [P[x] for x in key_or_pids] if isinstance(key_or_pids, list) else [P[key_or_pids]]
    lat, lon, _ = LOC[loc]
    g = {'expected_product_ids': pids, 'k': k} | nearest(pids, lat, lon, k=k)
    add(id_, 'nearest_stores', q, g, must or f'List the {k} nearest shops (by straight-line distance from the user) that carry the product with a valid price, with shop name, approximate distance and price; shop set must match acceptable_shop_ids_for_top_k (ties within 50 m allowed). Must not invent shops.', diff, loc=loc)

near_item('N01', 'من الان میدون تجریشم، نزدیک‌ترین جایی که S25 FE داره کجاست؟', 's25fe', 'tajrish')
near_item('N02', 'دنبال PS5 اسلیم دیجیتال هستم، نزدیک من کجا می‌تونم حضوری بخرم؟', 'ps5_dig', 'saadatabad')
near_item('N03', 'شارژر ۲۰ وات اپل سه‌پین رو نزدیک خونه‌م کجا پیدا کنم؟', ['charger20_a', 'charger20_b'], 'jannatabad',
          must='The title "شارژر اپل توان 20 وات سه پین" exists as two product_ids; union both. List the 3 nearest shops with distance & price.')
near_item('N04', 'من کیانشهرم؛ ردمی نوت ۱۵ رو نزدیک‌ترین جا کجا می‌فروشن؟ چقدر راهه؟', 'redmi_n15', 'kianshahr',
          must='Nearest shops are far (central Tehran); a correct answer gives the nearest ones with their (large) distance honestly rather than claiming a shop in Kianshahr.', diff='hard')
# category-level nearest
lat, lon, _ = LOC['tehranpars']
rows = [dict(r) for r in con.execute('''SELECT s.shop_id, s.name shop_name, s.address, s.location_label,
        round(dist_km(?,?,s.lat,s.lon),3) distance_km, COUNT(DISTINCT o.product_id) n_phone_products
        FROM shops s JOIN offers o USING(shop_id) JOIN products p USING(product_id)
        WHERE p.category_name='گوشی موبایل' AND o.price_toman IS NOT NULL GROUP BY s.shop_id ORDER BY distance_km LIMIT 5''', (lat, lon))]
add('N05', 'nearest_stores', 'نزدیک‌ترین موبایل‌فروشی به من کجاست؟ (تهرانپارس هستم)',
    {'definition': 'shops with ≥1 valid-priced offer in category گوشی موبایل, ordered by distance', 'nearest_shops': rows[:3],
     'next_candidates': rows[3:], 'acceptable_shop_ids_for_top_k': [r['shop_id'] for r in rows if r['distance_km'] <= rows[2]['distance_km'] + 0.05]},
    'Return the nearest phone-selling shops with distance; should not rely on free-form shop category_names only (offers are the ground truth).', 'medium', loc='tehranpars')
P.update(airpods4_anc_b='product_d145d125dbf5e185c3a80029', airpods4_anc_c='product_94bc1b6742d5abe41fe95723',
         airpods4_anc_d='product_5add81126e89fb96b4fa4a58', airpods4_anc_e='product_7e7f3f7463a0f200a086a733', airpods4_anc_f='product_7fa8c3a43559c5266b7aef75')
near_item('N06', 'میدون انقلابم، ایرپاد ۴ نویز کنسلینگ رو نزدیک‌ترین جا چند می‌دن؟',
          ['airpods4_anc', 'airpods4_anc_b', 'airpods4_anc_c', 'airpods4_anc_d', 'airpods4_anc_e', 'airpods4_anc_f'], 'enghelab',
          must='AirPods 4 ANC (full set) is listed under 6 catalogue entries (2 identical titles + 4 variants of the name); union them, excluding single-ear and used listings. Name the nearest shop(s) with distance and price.')
# combined: cheapest within radius
lat, lon, _ = LOC['ferdowsi']
rad = [dict(r) for r in con.execute('''SELECT o.shop_id, s.name shop_name, MIN(o.price_toman) price_toman,
        round(dist_km(?,?,s.lat,s.lon),3) distance_km FROM offers o JOIN shops s USING(shop_id)
        WHERE o.product_id=? AND o.price_toman IS NOT NULL GROUP BY o.shop_id HAVING distance_km<=1.0 ORDER BY price_toman''', (lat, lon, P['a17_128_4']))]
add('N07', 'nearest_stores', 'تو شعاع یک کیلومتری میدون فردوسی، ارزون‌ترین جایی که گلکسی A17 با ۱۲۸ گیگ و رم ۴ داره کجاست؟',
    {'expected_product_ids': [P['a17_128_4']], 'radius_km': 1.0, 'n_shops_in_radius': len(rad),
     'cheapest_in_radius': rad[0] if rad else None, 'top5_in_radius_by_price': rad[:5],
     'global_cheapest': cheapest(P['a17_128_4'])['cheapest']},
    'Must apply both the 1 km radius and the price sort; answer = cheapest_in_radius shop and price.', 'hard', loc='ferdowsi')

# ---------------------------------------------------------------- 4. cheapest / compare stores
add('K01', 'cheapest_compare_stores', 'ارزون‌ترین جا برای سامسونگ A56 با ۲۵۶ گیگ و ۸ رم کجاست؟',
    cheapest(P['a56_256'], k=5), 'Name the cheapest shop (shop name + price exactly as in ground truth); optionally next 2.', 'easy')
c = cheapest(P['silex_805'], k=5)
add('K02', 'cheapest_compare_stores', 'قیمت دزدگیر سیم‌کارتی سایلکس SG8-805S رو بین مغازه‌ها مقایسه کن',
    c, 'Give the price spread (min→max), the 3–5 cheapest shops with prices, and number of shops (≈49).', 'medium')
c = cheapest(P['charger20_a'], k=5); c2 = cheapest(P['charger20_b'], k=5)
add('K03', 'cheapest_compare_stores', 'شارژر ۲۰ وات اپل سه پین ارزون‌ترین کجاست؟',
    {'expected_product_ids': [P['charger20_a'], P['charger20_b']], 'per_product': [c, c2],
     'overall_cheapest': min([c['cheapest'], c2['cheapest']], key=lambda r: r['price_toman'])},
    'Union of both same-titled products. The 480,000 offer is cheapest but its last price change is ~Dec-2025 (stale) and far below the median shop price (~3.5M) – a good answer flags it as old/suspicious and also gives the cheapest plausible, recent offer.', 'hard')
# cheapest PS5 slim standard with warranty
rows = [dict(r) for r in con.execute('''SELECT o.shop_id, s.name shop_name, MIN(o.price_toman) price_toman, o.warranty_provider, o.warranty_months
        FROM offers o JOIN shops s USING(shop_id) WHERE o.product_id=? AND o.price_toman IS NOT NULL
        AND o.warranty_provider IS NOT NULL AND o.warranty_provider NOT IN ('بدون گارانتی') GROUP BY o.shop_id ORDER BY price_toman''', (P['ps5_std'],))]
add('K04', 'cheapest_compare_stores', 'PS5 اسلیم استاندارد رو ارزون‌ترین با گارانتی کی می‌ده؟',
    {'expected_product_ids': [P['ps5_std']], 'offers_with_warranty': rows, 'cheapest_with_warranty': rows[0] if rows else None,
     'cheapest_any': cheapest(P['ps5_std'])['cheapest'], 'note': 'warranty = warranty_provider not null and not "بدون گارانتی"'},
    'If offers_with_warranty is empty, must say no offer with a recorded warranty exists (and may give cheapest overall). Otherwise name the cheapest warranted offer.', 'hard')
ALA = r'(پاساژ|مجتمع|بازار موبایل|مریم)\s*علا\s*ء?\s*الدین|(پاساژ|مجتمع)\s*علالدین'
rows = [dict(r) for r in con.execute('''SELECT o.shop_id, s.name shop_name, s.address, MIN(o.price_toman) price_toman FROM offers o JOIN shops s USING(shop_id)
        WHERE o.product_id=? AND o.price_toman IS NOT NULL AND regexp(?, s.address_norm) GROUP BY o.shop_id ORDER BY price_toman''', (P['s25fe'], ALA))]
add('K05', 'cheapest_compare_stores', 'تو پاساژ علاءالدین S25 FE رو کدوم مغازه ارزون‌تر می‌ده؟',
    {'expected_product_ids': [P['s25fe']], 'mall_filter_regex_on_normalized_address': ALA, 'n_shops_in_mall': len(rows),
     'cheapest_in_mall': rows[0] if rows else None, 'all_in_mall_by_price': rows},
    'Mall filter must cope with spelling variants (علاالدین/علاءالدین/علاالدین ۲/۳). Answer = cheapest_in_mall shop and price.', 'hard')
c = cheapest(P['stage320'], k=5)
add('K06', 'cheapest_compare_stores', 'اسپیکر JBL PartyBox Stage 320 فرق قیمتش بین مغازه‌ها چقدره؟',
    c | {'price_summary': ps('stage320')},
    'Report min (87.8M) and a realistic range; must flag the 860M max as an obvious outlier/data error rather than a real spread.', 'medium')
rows = [dict(r) for r in con.execute('''SELECT o.shop_id, s.name shop_name, MIN(o.price_toman) price_toman FROM offers o JOIN shops s USING(shop_id)
        WHERE o.product_id=? AND o.price_toman IS NOT NULL GROUP BY o.shop_id HAVING price_toman<=90000000 ORDER BY price_toman''', (P['xbox_s'],))]
add('K07', 'cheapest_compare_stores', 'کدوم مغازه‌ها ایکس‌باکس سری S رو زیر ۹۰ میلیون می‌دن؟',
    {'expected_product_ids': [P['xbox_s']], 'shops_under_90M': rows, 'n': len(rows)},
    'List exactly the shops in shops_under_90M (with prices); none outside.', 'medium')

# ---------------------------------------------------------------- 5. compare products
def cmp_item(id_, q, keys, must, diff='medium', fields=None):
    g = {'expected_product_ids': [P[k] for k in keys],
         'products': [{'product_id': P[k], 'title': product(P[k])['persian_title'], 'min_price': ps(k).get('min_price'),
                       'median_price': ps(k).get('median_price'), 'n_shops': ps(k)['n_shops'], 'specs': specs(P[k], fields)} for k in keys]}
    add(id_, 'compare_products', q, g, must, diff)

cmp_item('C01', 'S25 FE رو با A56 (هر دو ۲۵۶ گیگ) مقایسه کن؛ دوربین و پردازنده و قیمت', ['s25fe', 'a56_256'],
         'Specs must match dataset: S25 FE = Exynos 2400 + 8MP telephoto, 4900 mAh, 45W; A56 = Exynos 1580, 5MP macro, no telephoto. Prices from dataset (S25 FE ≈184M+, A56 ≈116.8M+). No invented specs.', 'medium')
cmp_item('C02', 'ردمی نوت ۱۵ بهتره یا پوکو X7 پرو؟ فرقشون چیه؟', ['redmi_n15', 'poco_x7pro'],
         'Use dataset specs only: Redmi Note 15 (256/8) = Helio G100 Ultra, 108MP main, 6000 mAh, 4G only (no 5G), from ≈84.9M; Poco X7 Pro (512/12) = Dimensity 8400-Ultra, 50MP main, 6000 mAh, 5G, from ≈121.5M. Note the storage/RAM differ. Fields absent from the dataset (e.g. Poco refresh rate) must not be invented.', 'hard')
cmp_item('C03', 'آیفون ۱۶ ۱۲۸ نات اکتیو یا آیفون ۱۷ ۲۵۶؟ اختلاف قیمتشون چقدره؟', ['ip16_128', 'ip17_256'],
         'Compute price difference from dataset (cheapest-to-cheapest and/or median-to-median) and state which is which; outlier caveat for iPhone 16 spread.', 'medium')
cmp_item('C04', 'PS5 اسلیم دیجیتال یا ایکس‌باکس سری X؛ کدوم ارزون‌تره و کدوم تو مغازه‌های بیشتری هست؟', ['ps5_dig', 'xbox_x'],
         'Compare min/median prices and n_shops from ground truth; note PS5 Digital has an extreme 1.65B outlier.', 'medium')
cmp_item('C05', 'تلویزیون سونی ۶۵ اینچ 65S30 رو با شیائومی A Pro ۶۵ اینچ مقایسه کن', ['sony65', 'mi_tv65'],
         'Prices from dataset; specs only if present in product_specs (else say not available).', 'medium')

# ---------------------------------------------------------------- 6. freshness
def fresh(pid):
    rows = [dict(r) for r in con.execute('''SELECT o.shop_id, s.name shop_name, o.price_toman, o.last_price_changed_at FROM offers o JOIN shops s USING(shop_id)
            WHERE o.product_id=? ORDER BY o.last_price_changed_at DESC''', (pid,))]
    for r in rows:
        r['days_old'] = days_old(r['last_price_changed_at'])
    return rows
r = fresh(P['s25fe'])
add('F01', 'freshness', 'قیمت S25 FE که می‌گی مال کِیه؟ به‌روزه؟',
    {'expected_product_ids': [P['s25fe']], 'latest_price_change': r[0]['last_price_changed_at'], 'oldest_price_change': r[-1]['last_price_changed_at'],
     'n_offers': len(r), 'n_updated_within_30d_of_ref': sum(1 for x in r if x['days_old'] is not None and x['days_old'] <= 30),
     'cheapest_offer_date': cheapest(P['s25fe'])['cheapest']['last_price_changed_at'], 'reference_date': REF_DATE.date().isoformat()},
    'Must cite last_price_changed_at dates from the dataset (e.g. most recent ≈2026-10-12/13 UTC) and not claim real-time prices.', 'easy')
c = cheapest(P['contactor_lc1d09'], k=3)
add('F02', 'freshness', 'کنتاکتور اشنایدر LC1D09M7 ارزون‌ترین چنده؟ این قیمت جدیده یا قدیمی؟',
    c | {'cheapest_days_old': days_old(c['cheapest']['last_price_changed_at']),
         'cheapest_recent_offer_within_90d': next((compact(x) for x in shop_offers(P['contactor_lc1d09']) if days_old(x['last_price_changed_at']) <= 90), None)},
    'Cheapest offer (500,000) was last changed in May-2023 → must warn it is very stale (>3 years) and offer the cheapest recently-updated alternative.', 'hard')
rows = fresh(P['ps5_dig'])
add('F03', 'freshness', 'از مغازه‌هایی که PS5 دیجیتال دارن، قیمت کدوما تو یه ماه اخیر آپدیت شده؟',
    {'expected_product_ids': [P['ps5_dig']], 'reference_date': REF_DATE.date().isoformat(), 'window_days': 30,
     'shops_updated_within_30d': sorted({x['shop_id'] for x in rows if x['days_old'] is not None and x['days_old'] <= 30}),
     'shops_older_than_30d': sorted({x['shop_id'] for x in rows if x['days_old'] is None or x['days_old'] > 30}), 'offers': rows},
    'Split shops by last_price_changed_at within 30 days of 2026-10-22; list counts/names consistent with ground truth.', 'hard')
rows = fresh(P['silex_lite'])
add('F04', 'freshness', 'کدوم مغازه قیمت دزدگیر سایلکس SG8 LITE رو از همه تازه‌تر آپدیت کرده؟',
    {'expected_product_ids': [P['silex_lite']], 'most_recent_offer': rows[0], 'top3_most_recent': rows[:3]},
    'Name the shop with the most recent last_price_changed_at and the date/price.', 'medium')

# ---------------------------------------------------------------- 7. payment / installments
def pay_item(id_, q, pid_keys, must, diff='medium', providers=None, channel=None):
    pids = [P[k] for k in pid_keys]
    ph = ','.join('?' * len(pids))
    prov = providers or BNPL
    rows = [dict(r) for r in con.execute(f'''SELECT o.shop_id, s.name shop_name, MIN(o.price_toman) price_toman,
            (SELECT group_concat(provider_name||':'||channel, ', ') FROM shop_payment_options po WHERE po.shop_id=s.shop_id) payment_options,
            MAX(o.description LIKE '%اقساط%' OR o.description LIKE '%قسط%') installment_in_description
            FROM offers o JOIN shops s USING(shop_id) WHERE o.product_id IN ({ph}) GROUP BY o.shop_id''', pids)]
    out = []
    for r in rows:
        opts = [x for x in (r['payment_options'] or '').split(', ') if x]
        bn = [x for x in opts if x.split(':')[0] in prov and (channel is None or x.endswith(':' + channel))]
        if bn or (providers is None and r['installment_in_description']):
            r['matching_payment_options'] = bn
            out.append(r)
    out.sort(key=lambda r: (r['price_toman'] is None, r['price_toman']))
    add(id_, 'payment_installment', q, {'expected_product_ids': pids, 'providers_considered': prov, 'channel_filter': channel,
        'n_shops_carrying': len(rows), 'matching_shops': out, 'n_matching': len(out)}, must, diff)

pay_item('P01', 'می‌خوام آیفون ۱۶ ۱۲۸ نات اکتیو رو قسطی بخرم، کدوم مغازه‌ها شرایط اقساط دارن؟', ['ip16_128'],
         'Installment evidence = shop BNPL payment option (اسنپ‌پی/ترب‌پی/دیجی‌پی/تارا/ازکی‌وام) OR offer description mentioning اقساط/قسط. Must list matching_shops and must not claim installments for other shops.', 'hard')
pay_item('P02', 'سامسونگ S25 FE رو با اسنپ‌پی کجا می‌شه خرید؟', ['s25fe'],
         'Only shops carrying S25 FE whose payment_options include اسنپ‌پی; if none, say honestly none recorded.', 'medium', providers=['اسنپ\u200cپی'])
s = shop('shop_343a5f1dcbeb33366f3f7635')
add('P03', 'payment_installment', 'فروشگاه «مهرین رویسا» اسنپ‌پی حضوری قبول می‌کنه؟',
    {'shop_id': s['shop_id'], 'shop_name': s['name'], 'payment_options': s['payment_options'], 'answer': 'yes – اسنپ‌پی, channel in_person'},
    'Answer yes, citing اسنپ‌پی in_person from the dataset.', 'easy')
rows = [dict(r) for r in con.execute('''SELECT DISTINCT s.shop_id, s.name shop_name, s.address FROM shops s JOIN shop_payment_options po USING(shop_id)
        WHERE po.channel='in_person' AND regexp(?, s.address_norm) ORDER BY s.shop_id''', (ALA,))]
for r in rows:
    r['in_person_providers'] = [x[0] for x in con.execute("SELECT provider_name FROM shop_payment_options WHERE shop_id=? AND channel='in_person'", (r['shop_id'],))]
add('P04', 'payment_installment', 'تو پاساژ علاءالدین کدوم مغازه‌ها پرداخت اقساطی حضوری (مثل اسنپ‌پی یا دیجی‌پی) دارن؟',
    {'mall_filter_regex_on_normalized_address': ALA, 'matching_shops': rows, 'n_matching': len(rows)},
    'List shops from matching_shops (in-person BNPL channel); must not include shops whose channel is "unknown" as confirmed in-person.', 'hard')
lat, lon, _ = LOC['tajrish']
rows = [dict(r) for r in con.execute('''SELECT DISTINCT s.shop_id, s.name shop_name, s.location_label, round(dist_km(?,?,s.lat,s.lon),3) distance_km
        FROM shops s JOIN shop_payment_options po USING(shop_id) WHERE po.provider_name='ترب\u200cپی' ORDER BY distance_km LIMIT 5''', (lat, lon))]
add('P05', 'payment_installment', 'نزدیک تجریش مغازه‌ای هست که ترب‌پی داشته باشه؟',
    {'nearest_torobpay_shops': rows, 'note': 'any channel; channel shown in shop payment_options'},
    'Name the nearest ترب‌پی shop(s) with distance; should mention whether channel is in_person or unknown.', 'medium', loc='tajrish')

# ---------------------------------------------------------------- 8. store contact / info
k = cheapest(P['a56_256'])['cheapest']
s = shop(k['shop_id'])
add('T01', 'store_contact', 'شماره تماس مغازه‌ای که A56 ۲۵۶ رو ارزون‌تر از همه می‌ده چیه؟',
    {'resolved_shop': k, 'phone': s['phone'], 'phone_latin': s['phone_latin'], 'address': s['address'], 'phone_is_synthetic_in_dataset': True},
    'Two-hop: find cheapest shop then return its phone exactly as in dataset (Persian or Latin digits) + address. Must not invent a different number. (Phones in this dataset are synthetic; grader checks equality with dataset.)', 'medium')
s = shop('shop_51d0c1a6edf81ba759726bab')
add('T02', 'store_contact', 'آدرس و سایت «موبایل تخت جمشید» رو بده',
    {'shop': {k_: s[k_] for k_ in ('shop_id', 'name', 'address', 'website_url', 'instagram', 'phone')}},
    'Return the dataset address and website_url (https://takhtjamshidmobile.com/); instagram is null → say not available.', 'easy')
s = shop('shop_3f93a30a9e66c6dece07cdff')
add('T03', 'store_contact', 'فروشگاه «فرورا رویس» جمعه‌ها بازه؟ پنجشنبه تا کی کار می‌کنه؟',
    {'shop_id': s['shop_id'], 'weekly_hours': s['weekly_hours'], 'answer': {'fri': s['weekly_hours']['fri']['status'],
     'thu': s['weekly_hours']['thu']['shifts'][0]}},
    'Friday = closed; Thursday 10:00–14:00 (from weekly_hours).', 'easy')
# shop with empty hours
sid = con.execute("SELECT o.shop_id FROM offers o JOIN shops s USING(shop_id) WHERE s.weekly_hours IN ('{}') AND o.product_id=? LIMIT 1", (P['s25fe'],)).fetchone()
sid = sid[0] if sid else None
s = shop(sid) if sid else None
add('T04', 'store_contact', f'ساعت کاری فروشگاه «{s["name"]}» چیه؟' if s else 'N/A',
    {'shop_id': sid, 'weekly_hours': s['weekly_hours'] if s else None, 'expected_behavior': 'say working hours are not recorded; may offer phone/address'},
    'weekly_hours is empty for this shop → must say hours are not available in the data and not invent them.', 'medium')

# ---------------------------------------------------------------- 9. unanswerable / out-of-dataset (negative tests)
def neg(id_, q, why, check=None):
    g = {'expected_behavior': 'refuse', 'reason': why}
    if check:
        g['evidence'] = check
    add(id_, 'unanswerable', q, g, 'Honestly say the dataset does not contain this; no invented products/prices/stores. May offer a related in-dataset alternative clearly labelled.', 'medium')

neg('U01', 'قیمت گلکسی S27 اولترا چنده؟', 'No such product exists in the dataset.',
    {'phones_matching_s27': con.execute("SELECT COUNT(*) FROM products WHERE category_name='گوشی موبایل' AND title_norm LIKE '%s27%'").fetchone()[0],
     'note': 'non-phone items with "S27" in title exist (monitors, projectors, generators) and must not be presented as a Galaxy S27'})
neg('U02', 'تو اصفهان کجا PS5 می‌فروشن؟', 'All shops are in Tehran (lat 35.64–35.81, lon 51.31–51.51); no Isfahan shops.',
    {'lat_range': list(con.execute('SELECT MIN(lat),MAX(lat),MIN(lon),MAX(lon) FROM shops').fetchone())})
neg('U03', 'فروشگاه مهرین رویسا چند تا آیفون ۱۶ تو انبارش موجود داره؟', 'No stock/quantity column in the dataset.')
neg('U04', 'نظر خریدارها درباره ایرپاد پرو ۳ چیه؟ امتیازش چنده؟', 'No reviews/ratings in the dataset.')
neg('U05', 'قیمت آیفون ۱۶ شش ماه پیش چقدر بود؟ نمودار قیمتش رو بده', 'Only the current price and its last_price_changed_at exist; no price history.')
neg('U06', 'شیر پرچرب یه لیتری کجا ارزون‌تره؟', 'No groceries/dairy in the dataset.',
    {'products_matching': con.execute("SELECT COUNT(*) FROM products WHERE title_norm LIKE '%شیر پرچرب%' OR category_name LIKE '%لبنیات%'").fetchone()[0]})
neg('U07', 'قیمت دلار امروز چنده؟', 'Out of scope (no FX data); assistant should decline.')
neg('U08', 'کد تخفیف برای خرید S25 FE دارید؟', 'No coupon/discount data in the dataset.')

# ---------------------------------------------------------------- 10. ambiguous
add('A01', 'ambiguous', 'قیمت سامسونگ چنده؟',
    {'expected_behavior': 'clarify', 'n_samsung_products': con.execute("SELECT COUNT(*) FROM products WHERE brand_name='سامسونگ'").fetchone()[0],
     'n_samsung_phones': con.execute("SELECT COUNT(*) FROM products WHERE brand_name='سامسونگ' AND category_name='گوشی موبایل'").fetchone()[0]},
    'Ask which Samsung product/category (thousands of products); may suggest popular phones, but must not give a single price.', 'easy')
rows = search("p.category_name='گوشی موبایل' AND p.title_norm LIKE '%iphone 15 pro%'", order='s.n_shops DESC')
add('A02', 'ambiguous', 'قیمت iPhone 15 Pro چنده؟',
    {'expected_behavior': 'clarify_or_list_variants',
     'genuine_variants': [r for r in rows if 'طرح' not in r['persian_title'] and 'max' not in r['persian_title'].lower()],
     'pro_max_variants_not_asked': [r['product_id'] for r in rows if 'max' in r['persian_title'].lower() and 'طرح' not in r['persian_title']],
     'knockoffs_to_exclude': [r['product_id'] for r in rows if 'طرح' in r['persian_title']]},
    'Several real variants (stock vs active, 256 vs 512). Correct: ask storage/condition or list variants with their prices (≈189M–210M). MUST NOT quote the ~18.9M "طرح اپل" knock-off or accessories (cases, LCD, battery) as the iPhone price.', 'hard')
add('A03', 'ambiguous', 'نزدیک‌ترین مغازه کجاست؟',
    {'expected_behavior': 'clarify', 'missing': ['product or category', 'user location']},
    'Ask what product and where the user is (or request location).', 'easy')
add('A04', 'ambiguous', 'یه گوشی خوب می‌خوام',
    {'expected_behavior': 'clarify', 'missing': ['budget', 'brand/OS preference', 'priority (camera/battery)'],
     'n_phone_products': con.execute("SELECT COUNT(*) FROM products WHERE category_name='گوشی موبایل'").fetchone()[0]},
    'Ask budget/preferences; if suggesting, only real dataset phones with real prices.', 'easy')
cats = [dict(r) for r in con.execute("SELECT category_name, COUNT(*) n FROM products WHERE title_norm LIKE 'کابل%' GROUP BY 1 ORDER BY n DESC LIMIT 6")]
add('A05', 'ambiguous', 'کابل می‌خوام، چند؟',
    {'expected_behavior': 'clarify', 'top_categories_for_title_starting_with_کابل': cats},
    'Ask which type: building electrical cable vs phone/USB/HDMI/network cable etc.; no single price.', 'easy')
add('A06', 'ambiguous', 'شارژر اپل ۲۰ وات چنده؟',
    {'expected_behavior': 'clarify_or_list_variants',
     'variants': search("p.title_norm LIKE 'شارژر اپل توان 20 وات%' AND s.n_shops>=2", order='s.n_shops DESC')},
    'Variants differ by plug (سه پین / دو پین گرد / دو پین تخت) and bundled cable; ask or list with prices. Note two identical-title "سه پین" listings.', 'medium')


CAT_FA = {'simple_lookup': 'جستجوی ساده محصول', 'filtered_search': 'جستجو با فیلتر', 'nearest_stores': 'نزدیک‌ترین فروشگاه',
          'cheapest_compare_stores': 'ارزان‌ترین / مقایسه فروشگاه‌ها', 'compare_products': 'مقایسه محصولات', 'freshness': 'تازگی قیمت',
          'payment_installment': 'پرداخت / اقساط', 'store_contact': 'اطلاعات تماس فروشگاه', 'unanswerable': 'خارج از دیتاست (تست منفی)',
          'ambiguous': 'مبهم / نیاز به شفاف‌سازی'}


def _shrink(o, depth=0):
    """Trim long lists for the human-readable view (JSON keeps everything)."""
    if isinstance(o, dict):
        return {k: _shrink(v, depth + 1) for k, v in o.items() if k not in ('weekly_hours',) or depth > 0}
    if isinstance(o, list):
        lim = 8
        out = [_shrink(x, depth + 1) for x in o[:lim]]
        if len(o) > lim:
            out.append(f'… (+{len(o) - lim} more, see eval_set.json)')
        return out
    if isinstance(o, float) and o.is_integer():
        return int(o)
    return o


def write_md(meta):
    L = ['# Torob in-person shopping assistant — Eval set', '',
         f"Generated by `make_eval_set.py` from `torob.sqlite` (no LLM). Items: **{meta['n_items']}**. Reference date for freshness: **{meta['reference_date']}**.", '',
         '## Conventions', '',
         f"- Prices: toman; {meta['price_rule']}.", f"- {meta['shop_price']}.", f"- Distance: {meta['distance']}.",
         f"- Outliers: {meta['outlier_rule']}.", f"- Installment (BNPL) providers: {', '.join(meta['bnpl_providers'])}; also offer descriptions containing اقساط/قسط.",
         '- Shop phone numbers in the dataset are synthetic; graders check equality with the dataset value only.',
         '- `expected_behavior: refuse` = must honestly say not in dataset; `clarify` = must ask a clarifying question (or list real variants) instead of guessing.', '',
         '## Breakdown', '', '| category | n |', '|---|---|']
    for c, n in meta['by_category'].items():
        L.append(f'| {c} ({CAT_FA[c]}) | {n} |')
    cur = None
    for it in ITEMS:
        if it['category'] != cur:
            cur = it['category']
            L += ['', f'## {cur} — {CAT_FA[cur]}', '']
        L += [f"### {it['id']} · {it['difficulty']}", '', f"**Q:** {it['question']}", '']
        if 'user_lat' in it:
            L += [f"**User location:** {it['user_lat']}, {it['user_lon']} ({it['user_location_label']})", '']
        L += [f"**Correct answer must:** {it['correct_answer_must']}", '']
        if it.get('notes'):
            L += [f"_Note:_ {it['notes']}", '']
        L += ['<details><summary>ground truth</summary>', '', '```json',
              json.dumps(_shrink(it['ground_truth']), ensure_ascii=False, indent=1, default=str), '```', '</details>', '']
    with open(os.path.join(HERE, 'eval_set.md'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(L))


def main():
    meta = {'db': 'torob.sqlite', 'reference_date': REF_DATE.date().isoformat(), 'price_rule': 'price_toman NULL if <1000 or >1e11 (or missing)',
            'distance': 'haversine straight-line km from (user_lat,user_lon) to shop lat/lon',
            'shop_price': "a shop's price for a product = its cheapest valid offer (variants collapse)",
            'outlier_rule': 'suspicious if < 0.4× or > 2.5× median of per-shop prices',
            'bnpl_providers': BNPL, 'n_items': len(ITEMS)}
    by = {}
    for it in ITEMS:
        by[it['category']] = by.get(it['category'], 0) + 1
    meta['by_category'] = by
    with open(os.path.join(HERE, 'eval_set.json'), 'w', encoding='utf-8') as f:
        json.dump({'meta': meta, 'items': ITEMS}, f, ensure_ascii=False, indent=2, default=str)
    write_md(meta)
    print(json.dumps(meta, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
