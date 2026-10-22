"""Tool-grounded Persian shopping agent (chat/completions + function calling)."""
import json, os, time
from openai import OpenAI
from tools import TOOLS

MODEL = 'gpt-6-luna'
DEFAULT_BASE_URL = 'https://ai.boxapi.ir/ai/v1'
MAX_TOOL_ROUNDS = 4
MAX_COMPLETION_TOKENS = 600
_client = None


def current_model():
    return os.environ.get('BOXAPI_MODEL') or MODEL


def current_base_url():
    return os.environ.get('BOXAPI_BASE_URL') or DEFAULT_BASE_URL


def client():
    global _client
    if _client is None:
        key = os.environ.get('BOXAPI_API_KEY') or ''
        if not key:
            raise RuntimeError('BOXAPI_API_KEY is not set')
        _client = OpenAI(api_key=key, base_url=current_base_url())
    return _client


SYSTEM_PROMPT = """تو «دستیار خرید حضوری ترب» هستی: به کاربر کمک می‌کنی محصول را پیدا کند و بفهمد کدام فروشگاه‌های فیزیکی در تهران آن را با چه قیمتی دارند.
تاریخ امروز: ۲۰۲۶-۱۰-۲۲ (۳۰ مهر ۱۴۰۵). همه‌ی قیمت‌ها به تومان است.

قوانین قطعی:
1. فقط و فقط بر اساس خروجی ابزارها جواب بده. هیچ محصول، قیمت، فروشگاه، مشخصات فنی، آدرس یا شماره‌ای را از خودت نساز یا حدس نزن. اگر ابزار چیزی برنگرداند، صادقانه بگو «در داده‌های من موجود نیست».
2. برای هر سؤال درباره‌ی محصول/قیمت/فروشگاه اول ابزار را صدا بزن (معمولاً search_products، بعد find_stores_for_product).
3. وقتی کاربر خودِ دستگاه را می‌خواهد (مثلاً گوشی)، نتایجی که پرچم ACCESSORY_OR_PART (قاب، گلس، باتری، تاچ و...) یا KNOCKOFF_طرح دارند را هرگز به‌عنوان قیمت آن محصول گزارش نکن. کالای استوک/کارکرده را حتماً با همین عنوان مشخص کن.
4. اگر نتیجه‌ها فقط PARTIAL_MATCH هستند یا یادداشت NO EXACT MATCH آمده، یعنی محصول دقیق احتمالاً در داده نیست؛ صریح بگو که آن مدل را نداری و فقط در صورت تمایل، جایگزین واقعیِ موجود را با برچسب «جایگزین» پیشنهاد بده.
4b. اگر خروجی جستجو match_confidence=low یا results خالی با closest_non_matching_alternatives داشت، یعنی کالای درخواستی پیدا نشده؛ آن‌ها را به‌عنوان کالای درخواستی معرفی نکن. موارد زیر کلید «not_matching_request» را هرگز به‌عنوان همان کالا گزارش نکن. اگر suggested_clarifying_question آمد و درخواست مبهم است، از آن استفاده کن.
4e. کشف و مرور (کاربر مدل مشخصی ندارد): برای «چه برندهایی ... دارید»، «تو دسته‌ی ... چیا هست»، «ارزون‌ترین ...»، «با X میلیون چی بخرم» و «شبیه X ولی ارزون‌تر» از browse_catalog استفاده کن (نه search_products). برای «ارزون‌ترین» sort_by=price؛ برای بودجه max_price=بودجه و sort_by=price_desc یا popularity. برای گوشی هوشمند exclude_basic_phones=true. برای «شبیه X ولی ارزون‌تر» اول قیمت معمول X اصل را بگیر (median پرفروش‌ترین نسخهٔ اصل؛ قیمت‌های خیلی پایین برند اصلی معمولاً کپی‌اند)، سپس browse_catalog با همان دسته، max_price کمتر از آن، exclude_brand=برند X و sort_by=popularity، و ۳–۵ گزینهٔ پرفروش واقعی را با قیمت پیشنهاد بده.
   در پاسخ فقط ۳ تا ۵ گزینهٔ واقعی با قیمت واقعی بیاور (نه فهرست طولانی). برای فهرست برندها، همهٔ برندهای خروجی brands را با تعداد بگو. موارد دارای پرچم SUSPICIOUS یا BASIC_FEATURE_PHONE یا USED را بدون توضیح پیشنهاد نکن. هرگز محصول یا برندی را که در خروجی ابزار نیست نام نبر.
   اگر درخواست واقعاً مبهم است (دسته مشخص نیست، یا category_warning آمد)، فقط یک سؤال روشن بپرس (مثلاً دسته و بودجه) و می‌توانی ۲–۳ دستهٔ نمونه پیشنهاد بدهی.
4f. مرور فروشگاه‌ها: برای «فروشگاه‌های فلان محله/پاساژ» از search_stores با address_contains؛ برای «کدوم فروشگاه‌ها قسطی دارن» از search_stores با installment_any=true و تعداد کل، تعداد هر سرویس و ۳–۵ فروشگاه نمونه (ترجیحاً با پرداخت حضوری) را بگو.
4d. اگر کاربر «نزدیک‌ترین» را پرسید ولی موقعیتش (مختصات) به تو داده نشده و کالا یا نوع مغازه را هم نگفته، ابزاری صدا نزن و با یک سؤال مشخص (با علامت ؟) موقعیت و نوع کالا را بپرس.
4c. برای «نزدیک‌ترین موبایل‌فروشی/فروشگاهِ یک دسته» از search_stores با sells_category و موقعیت کاربر استفاده کن؛ خروجی آن معتبر است (بر اساس پیشنهادهای واقعی فروش).
5. ابهام: اگر درخواست چند نسخه‌ی واقعی دارد (حافظه، اکتیو/نات‌اکتیو/استوک، نوع دوشاخه و...) یا خیلی کلی است (فقط برند، «یه گوشی خوب»، «کابل»، «نزدیک‌ترین مغازه» بدون محصول/موقعیت)، یک سؤال شفاف‌کننده بپرس و در صورت وجود، نسخه‌های واقعی را با قیمتشان فهرست کن؛ یکی را حدسی انتخاب نکن.
6. تازگی قیمت: هر قیمتی با stale_price=true یا بیش از ۹۰ روز از آخرین تغییرش گذشته، باید با هشدار «این قیمت قدیمی است (تاریخ ...)» گفته شود و در صورت وجود، ارزان‌ترین جایگزین به‌روز (cheapest_fresh_plausible_alternative) را هم بگو. قیمت‌های suspicious_price یا outlier_warning را «غیرعادی/احتمالاً خطا» علامت بزن.
7. سؤال «نزدیک‌ترین»: همیشه ۳ فروشگاهِ اولِ مرتب‌شده بر اساس فاصله را با نام، فاصله (کیلومتر)، قیمت و تاریخ قیمت فهرست کن (نه فقط یکی). اگر نزدیک‌ترین فروشگاه دور است، صادقانه بگو دور است.
7b. سؤال «مقایسه‌ی قیمت بین مغازه‌ها»: کمترین و بیشترین قیمت (بازه)، تعداد فروشگاه‌ها و ۳ تا ۵ فروشگاهِ ارزان‌تر را بگو؛ قیمت‌های غیرعادی را جدا علامت بزن.
7c. اگر چند ردیفِ کاتالوگ در واقع همان کالا هستند (عنوان یکسان یا فقط نوشتار متفاوت مثل «ایرپاد 4 ANC» / «AirPods 4 نویز کنسلینگ»)، همه‌ی product_idهای آن‌ها را با هم به find_stores_for_product بده؛ ولی تک‌گوشی (چپ/راست)، استوک و لوازم جانبی را قاطی نکن.
8. اقساط/پرداخت: فقط بر اساس payment_options فروشگاه (اسنپ‌پی، ترب‌پی، دیجی‌پی، تارا، ازکی‌وام؛ کانال in_person یعنی حضوری، unknown یعنی نامشخص) یا installment_mentioned_in_offer بگو؛ اگر شاهدی نیست، بگو ثبت نشده.
9. شماره تلفن‌ها در این دیتاست ساختگی/شبیه‌سازی‌شده هستند: هر وقت شماره دادی، حتماً بگو «این شماره در داده‌ی نمایشی ساختگی است و باید جداگانه تأیید شود».
10. این داده‌ها را نداری و باید صادقانه رد کنی: موجودی انبار/تعداد، نظرات و امتیاز کاربران، تاریخچه یا نمودار قیمت (فقط آخرین قیمت و تاریخ تغییرش هست)، کد تخفیف، نرخ ارز، فروشگاه‌های خارج از تهران، کالاهای خارج از کاتالوگ. در این موارد عدد یا اطلاعات ساختگی نده.
11. پاسخ کوتاه، فارسی و دقیق باشد: نام محصول، نام فروشگاه، قیمت (با جداکننده‌ی هزارگان)، فاصله و تاریخ به‌روزرسانی. حداکثر ۵ فروشگاه/محصول فهرست کن مگر کاربر بیشتر بخواهد.
"""

TOOL_SCHEMAS = [
    {'type': 'function', 'function': {
        'name': 'search_products',
        'description': 'Search the product catalogue (Persian/English, normalised FTS). Returns product_id, title, brand, category, price range from valid offers, n_shops and flags (ACCESSORY_OR_PART, KNOCKOFF_طرح, USED_OR_STOCK, PARTIAL_MATCH). Use filters for brand/category/price ceilings.',
        'parameters': {'type': 'object', 'properties': {
            'query': {'type': 'string', 'description': 'product words, e.g. "گوشی سامسونگ S25 FE 256"'},
            'brand': {'type': 'string', 'description': 'Persian brand name e.g. سامسونگ, اپل, شیائومی, انکر, جی بی ال, ایسوس'},
            'category': {'type': 'string', 'description': 'category words e.g. "گوشی موبایل", "تلویزیون", "ساعت هوشمند", "لپ تاپ", "کولر گازی"'},
            'min_price': {'type': 'number', 'description': 'toman'}, 'max_price': {'type': 'number', 'description': 'toman'},
            'limit': {'type': 'integer', 'description': 'max 15, default 10'}}, 'required': ['query']}}},
    {'type': 'function', 'function': {
        'name': 'compare_products', 'description': 'Side-by-side key specs and price ranges for 2-4 product_ids.',
        'parameters': {'type': 'object', 'properties': {'product_ids': {'type': 'array', 'items': {'type': 'string'}}}, 'required': ['product_ids']}}},
    {'type': 'function', 'function': {
        'name': 'find_stores_for_product',
        'description': 'Physical shops carrying a product (or a list of same-title product_ids) with each shop\'s cheapest valid offer, distance from user (haversine km), price date, stale flag (>90 days), warranty, payment options. sort_by "distance" (needs user location) or "price". Optional filters: max_distance_km, address_contains (e.g. mall name "علاالدین"), require_warranty, payment_provider (e.g. "اسنپ‌پی").',
        'parameters': {'type': 'object', 'properties': {
            'product_id': {'anyOf': [{'type': 'string'}, {'type': 'array', 'items': {'type': 'string'}}]},
            'user_lat': {'type': 'number'}, 'user_lon': {'type': 'number'}, 'max_distance_km': {'type': 'number'},
            'limit': {'type': 'integer'}, 'sort_by': {'type': 'string', 'enum': ['distance', 'price']},
            'address_contains': {'type': 'string'}, 'require_warranty': {'type': 'boolean'}, 'payment_provider': {'type': 'string'}},
            'required': ['product_id']}}},
    {'type': 'function', 'function': {
        'name': 'compare_stores', 'description': 'Compare specific shops for one product: price, distance, freshness, warranty, payment options.',
        'parameters': {'type': 'object', 'properties': {'shop_ids': {'type': 'array', 'items': {'type': 'string'}},
            'product_id': {'type': 'string'}, 'user_lat': {'type': 'number'}, 'user_lon': {'type': 'number'}}, 'required': ['shop_ids', 'product_id']}}},
    {'type': 'function', 'function': {
        'name': 'check_store_freshness', 'description': 'Price freshness: days since last_price_changed_at (ref 2026-10-22) and stale flag, for an offer_id, a product_id+shop_id, or all offers of a product_id (newest first, with counts updated in last 30 days).',
        'parameters': {'type': 'object', 'properties': {'offer_id': {'type': 'string'}, 'product_id': {'type': 'string'}, 'shop_id': {'type': 'string'}}}}},
    {'type': 'function', 'function': {
        'name': 'contact_store', 'description': 'Shop details by shop_id or shop name: address, phone (FAKE/simulated in this dataset), website, instagram, weekly hours, payment options.',
        'parameters': {'type': 'object', 'properties': {'shop_id': {'type': 'string'}, 'shop_name': {'type': 'string'}}}}},
    {'type': 'function', 'function': {
        'name': 'search_stores', 'description': 'Find shops (not product-specific) by name, address/mall text, payment provider (اسنپ‌پی/ترب‌پی/دیجی پی/تارا/ازکی‌وام), in-person payment channel, or category they sell (e.g. "گوشی موبایل"); sorted by distance when user location given.',
        'parameters': {'type': 'object', 'properties': {'name': {'type': 'string'}, 'address_contains': {'type': 'string'},
            'payment_provider': {'type': 'string'}, 'in_person_only': {'type': 'boolean'}, 'sells_category': {'type': 'string'},
            'user_lat': {'type': 'number'}, 'user_lon': {'type': 'number'}, 'limit': {'type': 'integer'},
            'installment_any': {'type': 'boolean', 'description': 'shops offering ANY installment/BNPL provider; returns totals per provider + examples'}}}}},
    {'type': 'function', 'function': {
        'name': 'browse_catalog', 'description': 'Browse a whole CATEGORY (no specific model): list brands (facets with counts and price ranges), cheapest items, best items within a budget, popular items. Excludes knock-offs, accessories and used/stock by default. Use for: «چه برندهایی ... دارید», «تو دسته‌ی ... چیا هست», «ارزون‌ترین ...», «با X میلیون چی بخرم», «شبیه X ولی ارزون‌تر».',
        'parameters': {'type': 'object', 'properties': {'category': {'type': 'string', 'description': 'e.g. گوشی, لپتاپ, تلویزیون, هندزفری, ساعت هوشمند, کنسول بازی, اسپیکر, گیم'},
            'brand': {'type': 'string'}, 'min_price': {'type': 'number'}, 'max_price': {'type': 'number'},
            'sort_by': {'type': 'string', 'enum': ['popularity', 'price', 'price_desc'], 'description': 'price = cheapest first; price_desc = best you can get within max_price; popularity = most shops'},
            'limit': {'type': 'integer'}, 'include_used': {'type': 'boolean'}, 'title_contains': {'type': 'string'},
            'exclude_basic_phones': {'type': 'boolean', 'description': 'drop feature phones (memory in MB) when the shopper wants a smartphone'},
            'exclude_brand': {'type': 'string', 'description': 'drop this brand, e.g. for «شبیه ایرپاد ولی ارزون‌تر» exclude اپل'}}}}},
]

LOC_TOOLS = {'find_stores_for_product', 'compare_stores', 'search_stores'}


def _call(messages, tools_enabled=True):
    kw = dict(model=current_model(), messages=messages, max_completion_tokens=MAX_COMPLETION_TOKENS, reasoning_effort='none', tools=TOOL_SCHEMAS)
    if not tools_enabled:
        kw['tool_choice'] = 'none'
    for attempt in range(3):
        try:
            return client().chat.completions.create(**kw)
        except Exception as e:
            if attempt == 2:
                raise
            time.sleep(2 * (attempt + 1))


def run_agent(question, user_lat=None, user_lon=None):
    sys_prompt = SYSTEM_PROMPT
    if user_lat is not None:
        sys_prompt += f'\nموقعیت فعلی کاربر: lat={user_lat}, lon={user_lon} (برای ابزارهای فروشگاه همین را بفرست).'
    else:
        sys_prompt += '\nموقعیت کاربر مشخص نیست؛ اگر سؤال به «نزدیک من» نیاز دارد، موقعیت را بپرس.'
    messages = [{'role': 'system', 'content': sys_prompt}, {'role': 'user', 'content': question}]
    calls, usage = [], {'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0, 'cost': 0.0, 'api_calls': 0}
    final = ''
    for rnd in range(MAX_TOOL_ROUNDS + 1):
        resp = _call(messages, tools_enabled=rnd < MAX_TOOL_ROUNDS)
        u = resp.usage
        usage['prompt_tokens'] += u.prompt_tokens; usage['completion_tokens'] += u.completion_tokens
        usage['total_tokens'] += u.total_tokens; usage['api_calls'] += 1
        usage['cost'] += float(getattr(u, 'cost', 0) or (u.model_extra or {}).get('cost', 0) or 0)
        msg = resp.choices[0].message
        if not msg.tool_calls:
            final = msg.content or ''
            break
        messages.append({'role': 'assistant', 'content': msg.content, 'tool_calls': [
            {'id': tc.id, 'type': 'function', 'function': {'name': tc.function.name, 'arguments': tc.function.arguments}} for tc in msg.tool_calls]})
        for tc in msg.tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or '{}')
            except Exception:
                args = {}
            if name in LOC_TOOLS and user_lat is not None and args.get('user_lat') is None:
                args['user_lat'], args['user_lon'] = user_lat, user_lon
            try:
                result = TOOLS[name](**args) if name in TOOLS else {'error': f'unknown tool {name}'}
            except Exception as e:
                result = {'error': f'{type(e).__name__}: {e}'}
            out = json.dumps(result, ensure_ascii=False, default=str)
            calls.append({'name': name, 'args': args, 'result': out[:20000]})
            messages.append({'role': 'tool', 'tool_call_id': tc.id, 'content': out[:12000]})
    return {'final_answer': final, 'tool_calls': calls, 'usage': usage, 'raw': {'rounds': rnd + 1}}


if __name__ == '__main__':
    import sys
    r = run_agent(sys.argv[1] if len(sys.argv) > 1 else 'قیمت iPhone 15 Pro چنده؟')
    print(r['final_answer']); print([c['name'] for c in r['tool_calls']], r['usage'])
