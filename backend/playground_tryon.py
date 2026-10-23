"""Virtual try-on («پرو مجازی») via AvalAI — Google Nano Banana image editing (default gemini-2.5-flash-image; see MODEL note below).

Mount (no side effects on import):
    import playground_tryon as TRYON
    TRYON.init(auth=_auth)            # optional: reuse the app's token check (else PLAYGROUND_TOKEN / playground_token.txt)
    app.include_router(TRYON.router)

Endpoints
  GET  /api/tryon/eligibility/{product_id}?token=   -> {eligible, mode, kind, noun, cta, busy_text, title, image, remaining}
  POST /api/tryon?token=                             -> multipart (product_id, mode, sid, photo=<file>)  OR JSON {product_id, mode, sid, photo_b64}
  GET  /api/tryon/img/{key}.jpg?token=               -> generated JPEG (cached by hash)
Privacy: the user's photo is never written to disk (only the generated result, keyed by a hash)."""
import base64, hashlib, io, json, os, re, threading, time, urllib.error, urllib.request

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(HERE, 'torob.sqlite')
BASE_URL = os.environ.get('AVALAI_BASE_URL', 'https://api.avalai.ir/v1')
NATIVE_URL = os.environ.get('AVALAI_NATIVE_URL', 'https://api.avalai.ir/v1beta')
# 'edits'  = OpenAI-compatible POST /v1/images/edits (multipart image[] + prompt) — AvalAI rejects Gemini models here (kept for other models).
# 'native' = Gemini generateContent through AvalAI (/v1beta, inline_data images; AvalAI's recommended route for Nano Banana). 'openai' = /v1/chat/completions.
API_STYLE = os.environ.get('TRYON_API', 'native')
ASPECTS = {'1:1': 1.0, '2:3': 2 / 3, '3:2': 1.5, '3:4': 0.75, '4:3': 4 / 3, '4:5': 0.8, '5:4': 1.25, '9:16': 9 / 16, '16:9': 16 / 9, '21:9': 21 / 9}
# The user's pick was «Nano Banana 2 Lite» = AvalAI id 'gemini-3.1-flash-lite-image' ($0.0336/img), BUT on AvalAI that model ignores input
# images whenever image output is requested (tested 2026-10-23 on /v1/chat/completions and /v1beta generateContent: prompt image tokens = 0,
# an unrelated room was generated) and /v1/images/edits rejects it (unsupported_model). So the default is the nearest Nano Banana that edits:
# 'gemini-2.5-flash-image' («Nano Banana», $0.039/img). Override with TRYON_MODEL.
MODEL = os.environ.get('TRYON_MODEL', 'gemini-2.5-flash-image')
_PRICES = {   # from AvalAI /v1/models pricing ($ per 1M tokens; output_cost_per_image at 1K)
    'gemini-2.5-flash-image':      {'per_image': 0.039,  'input': 0.30, 'image_input': 0.30, 'output': 2.5, 'image_output': 30.0},
    'gemini-3.1-flash-lite-image': {'per_image': 0.0336, 'input': 0.25, 'image_input': 0.25, 'output': 1.5, 'image_output': 30.0},
    'gemini-3.1-flash-image':      {'per_image': 0.0672, 'input': 0.50, 'image_input': 0.50, 'output': 3.0, 'image_output': 60.0},
}
_P = _PRICES.get(MODEL, _PRICES['gemini-2.5-flash-image'])
PRICE_PER_IMAGE = _P['per_image']
PRICE_TOK = {k: _P[k] * 1e-6 for k in ('input', 'image_input', 'output', 'image_output')}
PER_SESSION = int(os.environ.get('TRYON_PER_SESSION', '3'))
CAP_USD = float(os.environ.get('TRYON_CAP_USD', '2.0'))                  # hard total spend cap for the demo
TIMEOUT_S = float(os.environ.get('TRYON_TIMEOUT', '90'))
MAX_BYTES = 8 * 1024 * 1024
MAX_SIDE = 1024
PROMPT_VERSION = 'v3'   # bump to invalidate cached results when the prompt changes
OUT_DIR = os.environ.get('TRYON_OUT', os.path.join(HERE, 'v3plus_runs', 'tryon_aval', 'cache'))

_FA = str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹')
router = APIRouter()
_auth_fn = None
_lock = threading.Lock()
_inflight: dict = {}

def init(auth=None, out_dir=None):
    global _auth_fn, OUT_DIR
    _auth_fn = auth
    if out_dir: OUT_DIR = out_dir

# ------------------------------------------------------------------ eligibility (exact category names from torob.sqlite)
# kind -> (noun, verb phrase used in «دارم {noun} رو {verb}…»)
_ROOM = {}
def _r(noun, *cats):
    for c in cats: _ROOM[c] = noun
_r('مبل', 'سایر  مبل راحتی', 'مبل استیل و سلطنتی', 'مبل تخت\u200cخواب شو', 'مبل راحتی ال', 'مبل راحتی چستر', 'مبل کلاسیک', 'سایر مبلمان',
   'مبلمان باغی و فضای باز', 'مبلمان اداری')
_r('صندلی', 'صندلی', 'سایر صندلی', 'صندلی راک', 'صندلی غذاخوری و رستورانی', 'صندلی مدیریتی', 'صندلی کارمندی', 'صندلی کانتر و اپنی',
   'صندلی گیمینگ', 'سایر صندلی اداری', 'صندلی انتظار', 'صندلی کنفرانس')
_r('میز', 'سایر میز', 'میز بار و کافی بار', 'میز تلویزیون', 'میز جلو مبلی و عسلی', 'میز مدیریت', 'میز کارمندی و اداری',
   'میز کامپیوتر و تحریر', 'میز کانتر', 'میز کنسول', 'میز گیمینگ', 'میز و صندلی آرایش', 'میز کنفرانس')
_r('میز و صندلی', 'ست میز و صندلی غذاخوری')
_r('فرش', 'فرش ماشینی', 'فرش دستبافت', 'فرش آشپزخانه', 'روفرشی', 'گلیم')
_r('تابلو', 'تابلو فرش', 'تابلو و قاب عکس')
_r('لوستر', 'لوستر و چراغ تزئینی')
_r('آباژور', 'آباژور و چراغ خواب')
_r('چراغ', 'چراغ دیواری')
_r('ساعت', 'ساعت دیواری٬ رومیزی و تزئینی')
_r('گلدان', 'گلدان و گل مصنوعی', 'استند و پایه گلدان')
_r('آینه', 'آینه دکوراتیو', 'آینه کنسول')
_r('کوسن', 'کوسن')
_r('پرده', 'رومیزی و پرده', 'پرده و توری در و پنجره')
_r('تخت', 'تخت خواب')
_r('پاتختی', 'پاتختی')
_r('کمد', 'کمد، بوفه و قفسه دیواری')
_r('کتابخانه', 'کتابخانه')
_r('جاکفشی', 'جاکفشی و جالباسی')
_r('کاور مبل', 'کاور و شال مبل')
_r('کاغذ دیواری', 'پوستر و کاغذ دیواری')
_r('وسیلهٔ دکوری', 'مجسمه', 'ست دکوری', 'گوی دکوراتیو', 'فانوس دکوری', 'شمع و جاشمعی', 'کشتی دکوراتیو', 'حروف دکوراتیو')
_r('تلویزیون', 'تلویزیون')
_r('یخچال', 'یخچال', 'یخچال فریزر بالاپایین', 'یخچال فریزر در فرانسوی', 'یخچال فریزر دوقلو', 'یخچال فریزر ساید بای ساید')
_r('لباسشویی', 'ماشین لباسشویی')

_PERSON = {}   # category -> (noun, verb)
def _p(noun, verb, *cats):
    for c in cats: _PERSON[c] = (noun, verb)
_TAN = 'تنت می\u200cکنم'
_p('پیراهن', _TAN, 'پیراهن مردانه', 'بلوز و پیراهن زنانه', 'بلوز مردانه')
_p('تیشرت', _TAN, 'تیشرت و پولوشرت', 'تاپ و تیشرت زنانه', 'نیم تنه و کراپ زنانه')
_p('شومیز', _TAN, 'شومیز و تونیک زنانه')
_p('هودی', _TAN, 'سویشرت و هودی مردانه', 'سویشرت و هودی زنانه', 'هودی و سویشرت')
_p('ژاکت', _TAN, 'ژاکت و پلیور', 'ژاکت و پلیور زنانه', 'ژاکت و پلیور مردانه')
_p('کت', _TAN, 'کت و جلیقه', 'کت و جلیقه زنانه', 'کت و جلیقه مردانه')
_p('کت و شلوار', _TAN, 'کت و شلوار مردانه', 'کت و شلوار زنانه', 'کت و دامن زنانه')
_p('کاپشن', _TAN, 'کاپشن، بارانی و پالتو مردانه', 'کاپشن، بارانی و پالتو زنانه', 'پافر مردانه', 'پافر زنانه')
_p('مانتو', _TAN, 'مانتو و شلوار زنانه', 'مانتو، پانچ و رویه', 'عبای زنانه')
_p('شلوار', 'پات می\u200cکنم', 'شلوار رسمی و راحتی مردانه', 'شلوار و لگ', 'شلوارک مردانه', 'شلوارک زنانه')
_p('دامن', _TAN, 'دامن زنانه')
_p('لباس', _TAN, 'لباس مجلسی زنانه', 'سارافون زنانه', 'سایر پوشاک زنانه', 'سایر پوشاک مردانه')
_p('کراوات', 'برات می\u200cبندم', 'کراوات')
_p('کفش', 'پات می\u200cکنم', 'کتانی و کفش اسپرت', 'کفش مجلسی و رسمی مردانه', 'کفش پاشنه بلند و مجلسی زنانه', 'کفش کالج مردانه',
   'کفش کالج زنانه', 'سایر کفش زنانه', 'سایر کفش مردانه', 'صندل و دمپایی زنانه', 'صندل و دمپایی مردانه', 'صندل مجلسی زنانه')
_p('بوت', 'پات می\u200cکنم', 'بوت و نیم بوت', 'بوت و نیم بوت زنانه', 'بوت و نیم بوت مردانه')
_p('ساعت', 'دستت می\u200cبندم', 'ساعت مچی عقربه\u200c ای و دیجیتالی', 'ساعت و مچ بند هوشمند')
_p('عینک', 'به چشمت می\u200cزنم', 'عینک آفتابی', 'عینک طبی', 'فریم و قاب عینک')
_p('کیف', 'دستت می\u200cدم', 'کیف و کوله', 'کیف اداری', 'کیف کمری و بادی بگ')
_p('کلاه', 'سرت می\u200cکنم', 'کلاه و شال گردن')
_p('روسری', 'سرت می\u200cکنم', 'روسری', 'شال')
_p('کمربند', 'برات می\u200cبندم', 'کمربند')
_p('گردنبند', 'گردنت می\u200cندازم', 'گردنبند')
_p('دستبند', 'دستت می\u200cکنم', 'دستبند و بنگل')
_p('انگشتر', 'دستت می\u200cکنم', 'انگشتر')
_p('گوشواره', 'برات می\u200cندازم', 'گوشواره')

def eligibility(category):
    c = (category or '').strip()
    if c in _ROOM:
        n = _ROOM[c]
        return {'mode': 'room', 'kind': 'home', 'noun': n, 'cta': 'در خانهٔ خودت امتحان کن', 'busy_text': f'دارم {n} رو توی اتاقت می\u200cچینم…',
                'ask': 'یه عکس از اتاقت بده'}
    if c in _PERSON:
        n, v = _PERSON[c]
        return {'mode': 'person', 'kind': 'fashion', 'noun': n, 'cta': 'روی عکس خودت امتحان کن', 'busy_text': f'دارم {n} رو {v}…',
                'ask': 'یه عکس تمام‌قد یا نیم‌تنه از خودت بده'}
    return None

# ------------------------------------------------------------------ helpers
class TryOnError(Exception):
    def __init__(self, code, fa, status=400):
        super().__init__(code); self.code, self.fa, self.status = code, fa, status

def _err(e: TryOnError, **extra):
    return JSONResponse({'ok': False, 'status': 'error', 'code': e.code, 'error': e.fa, 'detail': e.fa, **extra}, status_code=e.status)

def _check_auth(req: Request):
    if _auth_fn:
        _auth_fn(req); return
    tok = os.environ.get('PLAYGROUND_TOKEN')
    if not tok:
        try: tok = open(os.path.join(HERE, 'playground_token.txt')).read().strip()
        except Exception: tok = None
    import secrets
    if not tok or not secrets.compare_digest(req.query_params.get('token', ''), tok):
        raise TryOnError('auth', 'لینک معتبر نیست؛ لینک تازه را باز کنید.', 403)

def _api_key():
    k = os.environ.get('AVALAI_API_KEY')
    if k: return k
    try:
        for line in open(os.path.join(HERE, '.env_avalai'), encoding='utf-8'):
            line = line.strip()
            if line.startswith('AVALAI_API_KEY'):
                return line.split('=', 1)[1].strip().strip('"\'')
    except Exception:
        pass
    return None

def _db_product(pid):
    import sqlite3
    con = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
    try:
        r = con.execute('SELECT product_id,persian_title,category_name,image_urls,brand_name FROM products WHERE product_id=?', (pid,)).fetchone()
        if not r: return None
        try: urls = [u for u in json.loads(r[3] or '[]') if isinstance(u, str)]
        except Exception: urls = []
        mp = None
        try:
            mp = con.execute("SELECT MIN(price_toman) FROM offers WHERE product_id=? AND price_toman>0", (pid,)).fetchone()[0]
        except Exception:
            pass
        return {'product_id': r[0], 'title': r[1] or '', 'category': r[2] or '', 'images': urls, 'brand': r[4] or '', 'min_price': mp}
    finally:
        con.close()

def _jpeg(im, maxside, q=88):
    from PIL import Image, ImageOps
    im = ImageOps.exif_transpose(im)
    if im.mode in ('RGBA', 'LA', 'P'):
        im = im.convert('RGBA'); bg = Image.new('RGB', im.size, (255, 255, 255)); bg.paste(im, mask=im.split()[-1]); im = bg
    im = im.convert('RGB'); im.thumbnail((maxside, maxside), Image.LANCZOS)
    b = io.BytesIO(); im.save(b, 'JPEG', quality=q); return b.getvalue(), im.size

def validate_photo(data: bytes):
    from PIL import Image
    if not data:
        raise TryOnError('no_photo', 'عکسی فرستاده نشد.')
    if len(data) > MAX_BYTES:
        raise TryOnError('too_large', 'حجم عکس بیشتر از ۸ مگابایت است؛ عکس کوچک‌تری انتخاب کن.', 413)
    try:
        im = Image.open(io.BytesIO(data)); fmt = im.format; im.load()
    except Exception:
        raise TryOnError('not_image', 'فایل فرستاده‌شده عکس معتبر نیست.')
    if fmt not in ('JPEG', 'PNG', 'WEBP', 'MPO', 'HEIF', 'AVIF'):
        raise TryOnError('bad_format', 'فقط عکس JPEG، PNG یا WEBP قبول است.', 415)
    w, h = im.size
    if min(w, h) < 256:
        raise TryOnError('too_small', 'عکس خیلی کوچک است؛ عکسی با حداقل ۲۵۶ پیکسل بفرست.')
    if max(w, h) / min(w, h) > 3:
        raise TryOnError('bad_ratio', 'عکس خیلی کشیده است؛ یک عکس معمولی بفرست.')
    return _jpeg(im, MAX_SIDE)

def _phash(jpeg_bytes):
    """perceptual dHash (8x8 = 64 bits, on a blurred 9x8 grayscale) + aspect of the normalized photo, so the same picture re-encoded /
    resized client-side maps to the same cache key (a byte hash would miss and re-bill). Different photos practically never collide."""
    from PIL import Image, ImageFilter
    im = Image.open(io.BytesIO(jpeg_bytes))
    w, h = im.size
    g = im.convert('L').resize((72, 64), Image.LANCZOS).filter(ImageFilter.GaussianBlur(2)).resize((9, 8), Image.BOX)
    px = list(g.getdata())
    bits = 0
    for y in range(8):
        for x in range(8):
            bits = (bits << 1) | (px[y * 9 + x] > px[y * 9 + x + 1])
    return bits.to_bytes(8, 'big') + f'{round(w / h, 1)}'.encode()

def product_images(urls, n=1):
    from PIL import Image
    out = []
    for u in urls[:4]:
        try:
            req = urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0'})
            data = urllib.request.urlopen(req, timeout=10).read(6 * 1024 * 1024)
            out.append(_jpeg(Image.open(io.BytesIO(data)), 768, 86)[0])
        except Exception:
            continue
        if len(out) >= n: break
    return out

def build_prompt(p, mode, noun):
    item = f"«{p['title']}» (category: {p['category']}{', brand: ' + p['brand'] if p.get('brand') else ''}; Persian noun: {noun})"
    if mode == 'room':
        return ("You are a photo editor. IMAGE 1 is a photo of the user's room. IMAGE 2 is a product photo of " + item + ".\n"
                "TASK: place EXACTLY this product (from IMAGE 2) into the room in IMAGE 1, realistically, in the most natural spot for it "
                "(floor / wall / ceiling / table as appropriate).\n"
                "STRICT RULES:\n"
                "- Keep the room UNCHANGED: same walls, floor, windows, doors, furniture, objects, camera angle, framing, perspective and lighting. Do not remove, move, restyle or add anything else.\n"
                "- The product must be the SAME item as IMAGE 2: identical shape, proportions, colour, material, pattern and details. Do not redesign it; ignore IMAGE 2's background, text and watermarks.\n"
                "- Realistic scale relative to the room, correct perspective, contact shadows and light matching the room.\n"
                "- Output ONE photorealistic photo with the same aspect ratio and framing as IMAGE 1. No text, no logos, no watermark, no borders, no collage, no side-by-side.")
    return ("You are a photo editor. IMAGE 1 is a photo of a person. IMAGE 2 is a product photo of " + item + ".\n"
            "TASK: dress the person in IMAGE 1 in EXACTLY this item from IMAGE 2 (replace only the matching garment; if it is an accessory such as shoes, a watch, glasses, a bag or a hat, put it on naturally).\n"
            "STRICT RULES:\n"
            "- Keep the person UNCHANGED: same face, identity, facial features, expression, skin tone, hair, body shape, pose and hands. Do not beautify, slim or alter the body.\n"
            "- Keep the background, camera angle, framing and lighting unchanged; keep other clothing unchanged unless the new item covers it.\n"
            "- The item must be the SAME as IMAGE 2: identical colour, pattern, material, cut and details; realistic fit, folds and shadows for this body. Ignore IMAGE 2's background, model, text and watermarks.\n"
            "- Output ONE photorealistic photo with the same aspect ratio and framing as IMAGE 1. No text, no logos, no watermark, no borders, no collage, no side-by-side.")

def _extract_image(msg):
    for im in (msg.get('images') or []):
        u = (im.get('image_url') or {}).get('url') if isinstance(im, dict) else None
        if u and u.startswith('data:image'): return u
    c = msg.get('content')
    if isinstance(c, list):
        for part in c:
            if isinstance(part, dict) and part.get('type') == 'image_url':
                u = (part.get('image_url') or {}).get('url')
                if u: return u
    if isinstance(c, str):
        m = re.search(r'data:image/[a-z]+;base64,[A-Za-z0-9+/=]+', c)
        if m: return m.group(0)
    return None

def _cost(usage):
    if not usage: return PRICE_PER_IMAGE
    for k in ('cost', 'total_cost', 'cost_usd'):
        if usage.get(k) is not None:
            try: return float(usage[k])
            except Exception: pass
    pd = usage.get('prompt_tokens_details') or {}
    cd = usage.get('completion_tokens_details') or {}
    p_img = pd.get('image_tokens') or 0
    p_txt = max(0, (usage.get('prompt_tokens') or 0) - p_img)
    c_img = cd.get('image_tokens') or 0
    c_txt = max(0, (usage.get('completion_tokens') or 0) - c_img)
    if not c_img and (usage.get('completion_tokens') or 0) >= 1000:   # image tokens folded into completion
        c_img, c_txt = usage['completion_tokens'], 0
    return p_txt * PRICE_TOK['input'] + p_img * PRICE_TOK['image_input'] + c_txt * PRICE_TOK['output'] + c_img * PRICE_TOK['image_output']

def _aspect(size):
    r = size[0] / size[1]
    return min(ASPECTS, key=lambda k: abs(ASPECTS[k] - r))

def _cost_native(um):
    if not um: return PRICE_PER_IMAGE
    def by_mod(lst):
        d = {}
        for x in lst or []:
            d[str(x.get('modality', '')).upper()] = d.get(str(x.get('modality', '')).upper(), 0) + (x.get('tokenCount') or 0)
        return d
    p = by_mod(um.get('promptTokensDetails')); c = by_mod(um.get('candidatesTokensDetails'))
    p_img = p.get('IMAGE', 0); p_txt = max(0, (um.get('promptTokenCount') or 0) - p_img)
    c_img = c.get('IMAGE', 0)
    c_txt = max(0, (um.get('candidatesTokenCount') or 0) - c_img) + (um.get('thoughtsTokenCount') or 0)
    if not c_img and (um.get('candidatesTokenCount') or 0) >= 1000:
        c_img, c_txt = um['candidatesTokenCount'], um.get('thoughtsTokenCount') or 0
    return p_txt * PRICE_TOK['input'] + p_img * PRICE_TOK['image_input'] + c_txt * PRICE_TOK['output'] + c_img * PRICE_TOK['image_output']

def _http_json(url, payload, headers):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method='POST', headers={'Content-Type': 'application/json', **headers})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try: txt = e.read().decode('utf-8', 'replace')[:400]
        except Exception: txt = ''
        if e.code == 429:
            raise TryOnError('rate_limited', 'سرویس الان شلوغ است؛ چند ثانیه بعد دوباره امتحان کن.', 429)
        if e.code in (401, 403):
            raise TryOnError('upstream_auth', 'دسترسی به مدل تصویری برقرار نشد؛ پرو مجازی فعلاً در دسترس نیست.', 503)
        if e.code == 400 and re.search(r'safety|policy|block', txt, re.I):
            raise TryOnError('refused', 'مدل این عکس را نپذیرفت؛ عکس دیگری امتحان کن.', 422)
        if e.code == 402 or re.search(r'credit|balance|insufficient', txt, re.I):
            raise TryOnError('no_credit', 'اعتبار سرویس تصویر تمام شده است.', 503)
        raise TryOnError('upstream_error', f'ساخت تصویر با خطا روبه‌رو شد (کد {e.code})؛ دوباره امتحان کن.', 502)
    except TryOnError:
        raise
    except Exception as e:
        if 'timed out' in str(e).lower() or isinstance(e, TimeoutError):
            raise TryOnError('timeout', 'ساخت تصویر بیش از حد طول کشید؛ دوباره امتحان کن.', 504)
        raise TryOnError('network', 'ارتباط با سرویس تصویر برقرار نشد؛ دوباره امتحان کن.', 502)

def call_avalai_native(photo_jpeg, prod_jpegs, prompt, aspect):
    key = _api_key()
    if not key:
        raise TryOnError('not_configured', 'سرویس پرو مجازی پیکربندی نشده است.', 503)
    parts = [{'text': prompt}, {'inline_data': {'mime_type': 'image/jpeg', 'data': base64.b64encode(photo_jpeg).decode()}}]
    for pj in prod_jpegs:
        parts.append({'inline_data': {'mime_type': 'image/jpeg', 'data': base64.b64encode(pj).decode()}})
    payload = {'contents': [{'role': 'user', 'parts': parts}],
               'generationConfig': {'responseModalities': ['TEXT', 'IMAGE'], 'imageConfig': {'aspectRatio': aspect}}}
    t0 = time.time()
    d = _http_json(f"{NATIVE_URL.rstrip('/')}/models/{MODEL}:generateContent", payload, {'x-goog-api-key': key})
    cand = (d.get('candidates') or [{}])[0]
    um = d.get('usageMetadata') or {}
    img, txt = None, ''
    for part in ((cand.get('content') or {}).get('parts') or []):
        idata = part.get('inlineData') or part.get('inline_data')
        if idata and idata.get('data') and not img:
            img = idata['data']
        elif part.get('text'):
            txt += part['text']
    meta = {'model': d.get('modelVersion') or MODEL, 'usage': um, 'cost_usd': round(_cost_native(um), 6), 'elapsed_s': round(time.time() - t0, 1),
            'finish_reason': cand.get('finishReason') or (d.get('promptFeedback') or {}).get('blockReason'), 'model_text': txt[:300], 'api': 'native', 'aspect': aspect}
    if not img:
        if not d.get('candidates') or not um.get('candidatesTokenCount'):
            meta['cost_usd'] = round(_cost_native({**um, 'candidatesTokenCount': um.get('candidatesTokenCount') or 0}) if um else 0.0, 6)
        e = TryOnError('no_image', 'مدل برای این عکس تصویری نساخت؛ عکس دیگری امتحان کن.', 422); e.meta = meta; raise e
    return base64.b64decode(img), meta

def _multipart(fields, files):
    import uuid
    bnd = 'tryon' + uuid.uuid4().hex
    out = io.BytesIO()
    for k, v in fields:
        out.write(f'--{bnd}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    for k, fname, data, ctype in files:
        out.write(f'--{bnd}\r\nContent-Disposition: form-data; name="{k}"; filename="{fname}"\r\nContent-Type: {ctype}\r\n\r\n'.encode())
        out.write(data); out.write(b'\r\n')
    out.write(f'--{bnd}--\r\n'.encode())
    return out.getvalue(), 'multipart/form-data; boundary=' + bnd

def call_avalai_edits(photo_jpeg, prod_jpegs, prompt):
    key = _api_key()
    if not key:
        raise TryOnError('not_configured', 'سرویس پرو مجازی پیکربندی نشده است.', 503)
    files = [('image[]', 'photo.jpg', photo_jpeg, 'image/jpeg')] + [('image[]', f'product{i}.jpg', pj, 'image/jpeg') for i, pj in enumerate(prod_jpegs)]
    body, ctype = _multipart([('model', MODEL), ('prompt', prompt), ('n', '1')], files)
    req = urllib.request.Request(BASE_URL.rstrip('/') + '/images/edits', data=body, method='POST',
                                 headers={'Authorization': 'Bearer ' + key, 'Content-Type': ctype})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
            d = json.loads(r.read())
    except urllib.error.HTTPError as e:
        try: txt = e.read().decode('utf-8', 'replace')[:400]
        except Exception: txt = ''
        _raise_http(e.code, txt)
    except Exception as e:
        if 'timed out' in str(e).lower() or isinstance(e, TimeoutError):
            raise TryOnError('timeout', 'ساخت تصویر بیش از حد طول کشید؛ دوباره امتحان کن.', 504)
        raise TryOnError('network', 'ارتباط با سرویس تصویر برقرار نشد؛ دوباره امتحان کن.', 502)
    usage = d.get('usage') or {}
    item = (d.get('data') or [{}])[0]
    meta = {'model': d.get('model') or MODEL, 'usage': usage, 'cost_usd': round(_cost(usage) if usage else PRICE_PER_IMAGE, 6),
            'elapsed_s': round(time.time() - t0, 1), 'finish_reason': None, 'model_text': (item.get('revised_prompt') or '')[:300], 'api': 'edits'}
    raw = None
    if item.get('b64_json'):
        raw = base64.b64decode(item['b64_json'])
    elif item.get('url'):
        u = item['url']
        if u.startswith('data:image'):
            raw = base64.b64decode(u.split(',', 1)[1])
        else:
            try: raw = urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0'}), timeout=30).read()
            except Exception: raw = None
    if not raw:
        e = TryOnError('no_image', 'مدل برای این عکس تصویری نساخت؛ عکس دیگری امتحان کن.', 422); e.meta = meta; raise e
    return raw, meta

def _raise_http(code, txt):
    if code == 429:
        raise TryOnError('rate_limited', 'سرویس الان شلوغ است؛ چند ثانیه بعد دوباره امتحان کن.', 429)
    if code in (401, 403):
        raise TryOnError('upstream_auth', 'دسترسی به مدل تصویری برقرار نشد؛ پرو مجازی فعلاً در دسترس نیست.', 503)
    if code == 400 and re.search(r'safety|policy|block', txt, re.I):
        raise TryOnError('refused', 'مدل این عکس را نپذیرفت؛ عکس دیگری امتحان کن.', 422)
    if code == 402 or re.search(r'credit|balance|insufficient', txt, re.I):
        raise TryOnError('no_credit', 'اعتبار سرویس تصویر تمام شده است.', 503)
    raise TryOnError('upstream_error', f'ساخت تصویر با خطا روبه‌رو شد (کد {code})؛ دوباره امتحان کن.', 502)

def call_avalai(photo_jpeg, prod_jpegs, prompt):
    key = _api_key()
    if not key:
        raise TryOnError('not_configured', 'سرویس پرو مجازی پیکربندی نشده است.', 503)
    content = [{'type': 'text', 'text': prompt},
               {'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,' + base64.b64encode(photo_jpeg).decode()}}]
    for pj in prod_jpegs:
        content.append({'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,' + base64.b64encode(pj).decode()}})
    body = json.dumps({'model': MODEL, 'messages': [{'role': 'user', 'content': content}], 'modalities': ['image', 'text']}).encode()
    req = urllib.request.Request(BASE_URL.rstrip('/') + '/chat/completions', data=body, method='POST',
                                 headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
            d = json.loads(r.read())
    except urllib.error.HTTPError as e:
        try: txt = e.read().decode('utf-8', 'replace')[:400]
        except Exception: txt = ''
        if e.code == 429:
            raise TryOnError('rate_limited', 'سرویس الان شلوغ است؛ چند ثانیه بعد دوباره امتحان کن.', 429)
        if e.code in (401, 403):
            raise TryOnError('upstream_auth', 'دسترسی به مدل تصویری برقرار نشد؛ پرو مجازی فعلاً در دسترس نیست.', 503)
        if e.code == 400 and re.search(r'safety|policy|block', txt, re.I):
            raise TryOnError('refused', 'مدل این عکس را نپذیرفت؛ عکس دیگری امتحان کن.', 422)
        raise TryOnError('upstream_error', f'ساخت تصویر با خطا روبه‌رو شد (کد {e.code})؛ دوباره امتحان کن.', 502)
    except Exception as e:
        if 'timed out' in str(e).lower() or isinstance(e, TimeoutError):
            raise TryOnError('timeout', 'ساخت تصویر بیش از حد طول کشید؛ دوباره امتحان کن.', 504)
        raise TryOnError('network', 'ارتباط با سرویس تصویر برقرار نشد؛ دوباره امتحان کن.', 502)
    ch = (d.get('choices') or [{}])[0]
    msg = ch.get('message') or {}
    usage = d.get('usage') or {}
    meta = {'model': d.get('model') or MODEL, 'usage': usage, 'cost_usd': round(_cost(usage), 6), 'elapsed_s': round(time.time() - t0, 1),
            'finish_reason': ch.get('finish_reason'), 'model_text': (msg.get('content') if isinstance(msg.get('content'), str) else '' or '')[:300]}
    img = _extract_image(msg)
    if not img:
        e = TryOnError('no_image', 'مدل برای این عکس تصویری نساخت؛ عکس دیگری امتحان کن.', 422); e.meta = meta; raise e
    raw = base64.b64decode(img.split(',', 1)[1])
    return raw, meta

# ------------------------------------------------------------------ session limit + spend ledger (small JSON file next to the cache)
def _ledger_path(): return os.path.join(OUT_DIR, '_ledger.json')
def _ledger():
    try: return json.load(open(_ledger_path()))
    except Exception: return {'spent_usd': 0.0, 'sessions': {}, 'n': 0}
def _save_ledger(L):
    os.makedirs(OUT_DIR, exist_ok=True)
    tmp = _ledger_path() + '.tmp'; json.dump(L, open(tmp, 'w')); os.replace(tmp, _ledger_path())

def remaining(sid):
    with _lock:
        return max(0, PER_SESSION - int(_ledger()['sessions'].get(sid, 0)))

def _sid_of(req: Request, given):
    s = (given or req.headers.get('x-session-id') or '').strip()[:64]
    if not s:
        s = 'ip_' + (req.client.host if req.client else 'anon')
    return s

def _img_url(key, req: Request):
    return f"/api/tryon/img/{key}.jpg?token={req.query_params.get('token', '')}"

# ------------------------------------------------------------------ core
def run_tryon(pid, mode, photo_bytes, sid):
    p = _db_product(pid)
    if not p:
        raise TryOnError('not_found', 'این محصول پیدا نشد.', 404)
    el = eligibility(p['category'])
    if not el:
        raise TryOnError('not_eligible', 'پرو مجازی فقط برای مبلمان، دکوراسیون و لوازم خانه یا پوشاک، کفش و اکسسوری فعال است.', 400)
    mode = mode or el['mode']
    if mode not in ('room', 'person'):
        raise TryOnError('bad_mode', 'حالت باید room یا person باشد.')
    if mode != el['mode']:
        raise TryOnError('mode_mismatch', 'این محصول برای ' + ('عکس اتاق' if el['mode'] == 'room' else 'عکس خودت') + ' مناسب است، نه ' +
                         ('عکس اتاق.' if mode == 'room' else 'عکس آدم.'), 400)
    photo, size = validate_photo(photo_bytes)
    key = hashlib.sha256(b'|'.join([MODEL.encode(), PROMPT_VERSION.encode(), mode.encode(), pid.encode(), _phash(photo)])).hexdigest()[:32]
    out = os.path.join(OUT_DIR, key + '.jpg')
    base = {'product_id': pid, 'mode': mode, 'noun': el['noun'], 'key': key}
    if os.path.exists(out):
        meta = {}
        try: meta = json.load(open(out[:-4] + '.json'))
        except Exception: pass
        return {**base, 'cached': True, 'cost_usd': 0.0, 'model': meta.get('model', MODEL), 'elapsed_s': 0.0, 'width': meta.get('width'), 'height': meta.get('height')}
    # single-flight per key (double taps / retries while generating)
    with _lock:
        ev = _inflight.get(key)
        if ev is None:
            L = _ledger()
            used = int(L['sessions'].get(sid, 0))
            if used >= PER_SESSION:
                raise TryOnError('limit', f'سقف {str(PER_SESSION).translate(_FA)} پرو مجازی برای این نشست پر شده است.', 429)
            if L['spent_usd'] + PRICE_PER_IMAGE > CAP_USD:
                raise TryOnError('cap', 'سقف هزینهٔ این نسخهٔ آزمایشی پر شده است.', 402)
            L['sessions'][sid] = used + 1; _save_ledger(L)            # reserve
            _inflight[key] = threading.Event(); owner = True
        else:
            owner = False
    if not owner:
        ev.wait(TIMEOUT_S + 30)
        if os.path.exists(out):
            return {**base, 'cached': True, 'cost_usd': 0.0, 'model': MODEL, 'elapsed_s': 0.0}
        raise TryOnError('upstream_error', 'ساخت تصویر با خطا روبه‌رو شد؛ دوباره امتحان کن.', 502)
    try:
        prods = product_images(p['images'], n=1)
        if not prods:
            raise TryOnError('no_product_image', 'عکس این محصول در دسترس نیست؛ پرو مجازی ممکن نشد.', 502)
        prompt = build_prompt(p, mode, el['noun'])
        meta = None
        try:
            if API_STYLE == 'edits':
                raw, meta = call_avalai_edits(photo, prods, prompt)
            elif API_STYLE == 'native':
                raw, meta = call_avalai_native(photo, prods, prompt, _aspect(size))
            else:
                raw, meta = call_avalai(photo, prods, prompt)
        except TryOnError as e:
            meta = getattr(e, 'meta', None)
            raise
        finally:
            if meta:   # billed even when no image came back
                with _lock:
                    L = _ledger(); L['spent_usd'] = round(L['spent_usd'] + meta['cost_usd'], 6); L['n'] = L.get('n', 0) + 1; _save_ledger(L)
        from PIL import Image
        im = Image.open(io.BytesIO(raw))
        jb, (w, h) = _jpeg(im, 1536, 90)
        os.makedirs(OUT_DIR, exist_ok=True)
        tmp = out + '.tmp'; open(tmp, 'wb').write(jb); os.replace(tmp, out)
        json.dump({**meta, 'product_id': pid, 'mode': mode, 'input_size': size, 'width': w, 'height': h, 'ts': time.time(), 'prompt': prompt},
                  open(out[:-4] + '.json', 'w'), ensure_ascii=False, indent=1)
        return {**base, 'cached': False, 'cost_usd': meta['cost_usd'], 'model': meta['model'], 'elapsed_s': meta['elapsed_s'], 'width': w, 'height': h}
    except Exception:
        with _lock:   # refund the session slot on failure
            L = _ledger(); L['sessions'][sid] = max(0, int(L['sessions'].get(sid, 1)) - 1); _save_ledger(L)
        raise
    finally:
        with _lock:
            e = _inflight.pop(key, None)
        if e: e.set()

# ------------------------------------------------------------------ routes
@router.get('/api/tryon/eligibility/{pid}')
def api_tryon_eligibility(pid: str, req: Request):
    try:
        _check_auth(req)
        p = _db_product(pid[:64])
        if not p: raise TryOnError('not_found', 'این محصول پیدا نشد.', 404)
        el = eligibility(p['category'])
        sid = _sid_of(req, req.query_params.get('sid'))
        return {'ok': True, 'eligible': bool(el), 'product_id': pid, 'category': p['category'], 'title': p['title'],
                'image': p['images'][0] if p['images'] else None, 'min_price': p['min_price'], **(el or {}),
                'remaining': remaining(sid), 'per_session': PER_SESSION}
    except TryOnError as e:
        return _err(e)

@router.post('/api/tryon')
async def api_tryon(req: Request):
    from starlette.concurrency import run_in_threadpool
    try:
        _check_auth(req)
        ct = req.headers.get('content-type', '')
        if int(req.headers.get('content-length') or 0) > MAX_BYTES * 1.4 + 65536:
            raise TryOnError('too_large', 'حجم عکس بیشتر از ۸ مگابایت است؛ عکس کوچک‌تری انتخاب کن.', 413)
        if 'multipart/form-data' in ct:
            form = await req.form()
            pid, mode, sid = str(form.get('product_id') or ''), str(form.get('mode') or ''), str(form.get('sid') or '')
            f = form.get('photo') or form.get('image')
            data = await f.read() if f is not None and hasattr(f, 'read') else b''
        else:
            b = await req.json()
            pid, mode, sid = str(b.get('product_id') or ''), str(b.get('mode') or ''), str(b.get('sid') or '')
            s = str(b.get('photo_b64') or b.get('photo') or '')
            if s.startswith('data:'): s = s.split(',', 1)[-1]
            try: data = base64.b64decode(s, validate=False) if s else b''
            except Exception: raise TryOnError('not_image', 'فایل فرستاده‌شده عکس معتبر نیست.')
        if not pid.startswith('product_'):
            raise TryOnError('bad_product', 'شناسهٔ محصول معتبر نیست.')
        sid = _sid_of(req, sid)
        r = await run_in_threadpool(run_tryon, pid[:64], mode.strip().lower(), data, sid)
        return {'ok': True, 'status': 'done', **r, 'image_url': _img_url(r['key'], req), 'remaining': remaining(sid),
                'caption': 'تصویر نمایشی با هوش مصنوعی'}
    except TryOnError as e:
        sid2 = locals().get('sid')
        return _err(e, remaining=remaining(sid2) if isinstance(sid2, str) and sid2 else None)
    except HTTPException:
        raise   # the app's own auth (init(auth=_auth)) → 403 as usual
    except Exception:
        return _err(TryOnError('server', 'مشکلی پیش آمد؛ دوباره امتحان کن.', 500))

@router.get('/api/tryon/img/{name}')
def api_tryon_img(name: str, req: Request):
    try:
        _check_auth(req)
    except TryOnError as e:
        return _err(e)
    m = re.fullmatch(r'([0-9a-f]{32})\.jpg', name)
    path = os.path.join(OUT_DIR, m.group(1) + '.jpg') if m else None
    if not path or not os.path.exists(path):
        return _err(TryOnError('not_found', 'تصویر پیدا نشد.', 404))
    return FileResponse(path, media_type='image/jpeg', headers={'Cache-Control': 'private, max-age=86400'})
