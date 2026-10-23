# «راهنمای رسیدن داخل پاساژ» (mall guide stories): integration

These new files are self-contained. No existing file was edited.
- Backend: `/workspace/torob/eval/playground_mallguide.py` (APIRouter). It writes its cache to `/workspace/torob/eval/mallguide_cache/` (`mall_<key>.json`, one file per mall).
- Frontend: `/workspace/torob-app/src/mallguide/{MallGuide.tsx, mallguideApi.ts, mallguide.css}`. It reuses `../api`, `../fmt`, `../StatusBar`, `../assets/m-avatar.png` and `../mascot3d/assets/{wave,idle,search,found}-{body,leaves}.webp` read-only.
- Dev harness (not in the build): `/workspace/torob-app/mallguide-dev/` (vite on :5199 → test server `/workspace/torob-mallguide-dev/server.py` on :8797).

## 1. Backend: `playground_app.py` (3 lines)
Put these right after the TRYON block (currently lines 589–591, after `app.include_router(TRYON.router)`):
```python
import playground_mallguide as MALLGUIDE  # «راهنمای رسیدن داخل پاساژ»: /api/shop/{sid}/mallguide (+ /facts)
MALLGUIDE.init(auth=_auth, add_spend=_add_spend, can_spend=lambda need: _cap_ok(need), client_fn=A.client)
app.include_router(MALLGUIDE.router)
```
(`_cap_ok` is defined later in the file. The lambda resolves it at call time, so the order is fine.) Then restart uvicorn.

## 2. Frontend: `src/Shop.tsx` (2 edits)
a) Add the import at the top:
```tsx
import { MallGuide } from './mallguide/MallGuide'
```
b) In `ShopSheet`, put the entry row directly under the one-line mall location, i.e. after
`<LocLine sid={s.shop_id} loc={s.location} place={s.place} />` and before `<div className="cs-actions">` (the «مسیریابی» button):
```tsx
<MallGuide sid={s.shop_id} pid={pid} sbar={sbar}
  onContact={() => setSub('contact')}
  onAsk={() => scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: 'smooth' })} />
```
- It renders **nothing** when the shop is not in a mall (`eligible:false`), so no chip or row appears.
- The entry row is the spec's row («راهنمای رسیدن داخل پاساژ» / «۴ مرحلهٔ کوتاه تا جلوی مغازه», mall-0-entry). If you also want the short chip «راه رسیدن داخل پاساژ» somewhere else (e.g. a chat shop card), use the lower-level parts:
  ```tsx
  import { MallGuideStory } from './mallguide/MallGuide'; import { getGuide } from './mallguide/mallguideApi'
  // const g = await getGuide(sid, pid); if (g.eligible) show <button>راه رسیدن داخل پاساژ</button> → <MallGuideStory guide={g} sbar={sbar} onClose={…} />
  ```
- The story portals into `.screen`, falling back to `body` (`position:absolute; inset:0; z-index:900`). It sits above the shop sheet. «تماس» closes the story first, then calls `onContact` (the existing ContactSheet: phone as text plus copy, no tel:).
- Optional props: `autoplay` (default **false** per spec, 6 s/step, never on the last step).

## 3. Endpoint contract
`GET /api/shop/{sid}/mallguide?pid=&token=` costs $0 and is fast (DB address plus cached facts).
`POST /api/shop/{sid}/mallguide/facts?pid=&token=` returns the same shape. On the first open of a mall it runs ONE BoxAPI web_search (gpt-6-luna, effort low, ≈$0.001–0.003) and caches the result per mall forever. It respects the app's spend cap through `can_spend`. `<MallGuide>` calls it lazily when the story opens and `facts_status == "not_fetched"`.
```jsonc
{ "eligible": true, "reason": "not_in_mall",          // reason only when eligible=false
  "shop_id": "...", "shop_name": "...", "address": "<raw DB address>",
  "mall": "پاساژ چارسو", "mall_key": "چارسو", "street": "خیابان جمهوری", "hint": null,
  "floor": {"level": 1, "label": "طبقهٔ اول", "raw": "طبقه اول"} | null,   // level 0 همکف, <0 basement, null = نیم‌طبقه
  "unit":  {"label": "پلاک C۲۱", "raw": "پلاک C21", "kind": "plak|unit"} | null,
  "entry": {"title": "راهنمای رسیدن داخل پاساژ", "sub": "۴ مرحلهٔ کوتاه تا جلوی مغازه"},
  "steps": [
    {"n":1,"kind":"arrive","title":"به پاساژ چارسو برس","text":"<street>","text2":"داخل که شدی، بزن بریم مرحلهٔ بعد",
     "visual":{"type":"building","lat":..,"lon":..},"links":{"google":"…","neshan":"…"},"facts":[{"key":"parking","text":"…","source":{"title","url","host"}}]},
    {"n":2,"kind":"floor","title":"برو طبقهٔ اول","text":"با آسانسور یا پله برو طبقهٔ اول، بعد بزن مرحلهٔ بعد",
     "modes":[{"key":"elevator","label":"آسانسور","text":"…","source":{…}},{"key":"stairs","label":"پله","text":"…"}],   // modes only with a cited lift
     "visual":{"type":"floors","target":1,"label":"طبقهٔ اول","levels":[1,0]}, "source":{…}?},
    {"n":3,"kind":"unit","title":"پلاک C۲۱ رو پیدا کن","text":"شماره‌ها معمولاً بالای در مغازه‌هاست؛ دنبال C۲۱ و تابلوی «…» بگرد",
     "visual":{"type":"corridor","unit":"C۲۱","name":"…"}},
    {"n":4,"kind":"shop","title":"رسیدی!","text":"<shop>، طبقهٔ اول، پلاک C۲۱",
     "visual":{"type":"shop","name":"…","unit_label":"پلاک C۲۱","open":true|false|null,"open_label":"باز است تا ۲۱:۰۰"|null,"price_toman":3550000|null,"price_label":"از ۳٬۵۵۰٬۰۰۰ تومان"|null}}],
  "sources": [{"n":1,"title":"…","url":"…","host":"…"}],
  "facts_status": "not_fetched|cached|spend_cap|error", "llm_calls": 0 }
```
Fallback rules: no floor drops step 2. No unit while the floor is known gives step 3 «سراغ {shop} رو بپرس» / «…از نگهبانی یا اطلاعات پاساژ بگیر». If the mall is known but both floor and unit are missing, only steps 1 and 4 run. Not in a mall means `eligible:false`.

## 4. Truthfulness rules (implemented)
- Mall, floor and unit come only from the DB address. The parser is `playground_mall.parse_address` plus these refinements: the mall name is cut at its keyword; negative floors are kept as written («منفی ۱» / «زیرهمکف» / «زیرزمین»); half floors are handled; units with Persian letters like «واحد تی ۱۲» or «واحد شماره ۲۵» are parsed; «۲۱۰.۱» keeps its decimal; **«پلاک» counts as the unit only when it comes after the mall segment** (before it, it is the street number; the base parser got that wrong).
- Elevator and escalator appear only when the cited page was downloaded and states it. Any other fact needs a url_citation from the search call. If the page is readable, it must name the mall and the fact's keyword. Facts without a citation are dropped. The floor stack draws only ground…target (those floors must exist) plus one unlabeled ghost slab. Neighbouring unit boxes are blank (no invented numbers).
- Photo mode: the hook exists (`steps[0].photo`), but no photo is shown unless it has a verified source. None is enabled currently, so the illustrated style is used.
