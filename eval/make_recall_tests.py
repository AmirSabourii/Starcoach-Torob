#!/usr/bin/env python3
"""Deliberately badly-written recall queries + SQL-computed ground-truth product_ids -> recall_tests.json"""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "..", "backend", "app", "engine")))
import json, os, re, sqlite3
HERE = os.path.dirname(os.path.abspath(__file__))
from gt_lib import db_path
con = sqlite3.connect(db_path())
con.create_function('regexp', 2, lambda p, s: s is not None and re.search(p, s) is not None)
NOT_ACC = "AND NOT regexp('طرح|چپ|راست|left|right|کیف|کاور|(^| )قاب( |$)|کابل|بند |گلس|محافظ', p.title_norm)"
TESTS = [
    ('R01', 'اپل ۱۷', 'brand-word swap (اپل vs آیفون) + Persian digits',
     "p.category_name='گوشی موبایل' AND regexp('(آیفون|iphone|اپل) ?17($|[^0-9e])', p.title_norm) AND NOT regexp('pro|پرو|max|مکس|air|ایر|plus|پلاس', p.title_norm)"),
    ('R02', 'ایفون17پرومکس', 'no spaces, missing آ, glued pro/max',
     "p.category_name='گوشی موبایل' AND regexp('(آیفون|iphone|اپل) ?17 ?(pro|پرو) ?(max|مکس)', p.title_norm)"),
    ('R03', 'گلکسی اس۲۵ اف ای', 'Latin model letters spelled in Persian (اس=S, اف ای=FE)',
     "p.category_name='گوشی موبایل' AND p.title_norm LIKE '%s25 fe%'"),
    ('R04', 'samsung a56', 'English brand, Persian titles',
     "p.category_name='گوشی موبایل' AND regexp('(^|[^a-z0-9])a56($|[^0-9])', p.title_norm)"),
    ('R05', 'شیامی ردمی نوت15', 'misspelled brand (شیامی) + glued digit',
     "p.category_name='گوشی موبایل' AND regexp('redmi note 15($| [^p])', p.title_norm) AND p.title_norm NOT LIKE '%pro%'"),
    ('R06', 'پلی استیشن۵ اسلیم', 'Persian transliteration of PlayStation 5 Slim',
     "p.category_name LIKE 'کنسول بازی%' AND regexp('(ps5|playstation 5).*slim', p.title_norm)"),
    ('R07', 'ایر پادز پرو3', 'split/misspelt AirPods + glued digit',
     "p.category_name='هدفون، هدست و هندزفری' AND regexp('(ایرپاد|airpods?) ?(پرو|pro) ?3', p.title_norm) AND NOT regexp('استوک|a300', p.title_norm)"),
    ('R08', 'هارمن کاردون اورا استودیو ۵', 'misspelt brand + Persian transliteration of model',
     "regexp('aura studio 5', p.title_norm)"),
    ('R09', 'جی\u200cبی\u200cال فلیپ٧', 'ZWNJ inside brand + Arabic-Indic digit + transliterated model',
     "p.category_name='اسپیکر و سیستم صوتی' AND regexp('flip ?7', p.title_norm)"),
    ('R10', 'مکبوک ایر ام5', 'glued مک‌بوک + M5 spelled ام',
     "p.category_name='لپ تاپ و نوت بوک' AND regexp('(مک ?بوک|macbook) ?(ایر|air)', p.title_norm) AND p.title_norm LIKE '%m5%'"),
    ('R11', 'ايفون ١٦', 'Arabic ي + Arabic-Indic digits, missing آ',
     "p.category_name='گوشی موبایل' AND regexp('(آیفون|iphone|اپل) ?16($|[^0-9e])', p.title_norm) AND NOT regexp('pro|پرو|max|مکس|plus|پلاس', p.title_norm)"),
    ('R12', 'اکس باکس سری اس', 'Persian transliteration of Xbox Series S',
     "p.category_name LIKE 'کنسول%' AND regexp('xbox series s($|[^a-z])', p.title_norm)"),
]
out = []
for tid, q, kind, where in TESTS:
    rows = con.execute(f'''SELECT p.product_id, p.persian_title, s.n_shops FROM products p JOIN product_stats s USING(product_id)
                           WHERE {where} {NOT_ACC} ORDER BY s.n_shops DESC''').fetchall()
    out.append({'id': tid, 'query': q, 'difficulty_kind': kind, 'gt_sql_where': where + ' ' + NOT_ACC,
                'expected_product_ids': [r[0] for r in rows], 'expected_titles': [r[1] for r in rows],
                'primary_product_id': rows[0][0]})
    print(tid, q, len(rows), rows[0][1])
json.dump({'metric': 'hit@k = any expected id in top-k; recall@k = |expected ∩ top-k| / min(|expected|, k)', 'tests': out},
          open(os.path.join(HERE, 'recall_tests.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
