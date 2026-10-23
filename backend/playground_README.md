# Torob Playground (فعلی / V3 / JEV / V3+) — setup notes (built 2026-10-22, Asia/Tehran)

## What it is
FastAPI app `playground_app.py` + single-page UI `playground.html` (static: `playground_static/` = Vazirmatn font, logo, mascot from /workspace/torob-ux/src-v2).
- `GET /playground?token=TOKEN` – the page (403 without the token). Token in `playground_token.txt` (chmod 600).
- `POST /api/send?token=…` {message, mode: current|v3|jev|compare, sid} · `POST /api/reset?token=…` {version|all, sid} · `GET /api/status?token=…`
- Versions: «فعلی» = agent.run_agent, «V3» = agent_v3.run_agent_v3, «JEV» = agent_jev.run_agent_jev(enable_check=True), «مقایسه» = same message to all three (confirm() cost warning before each send; side by side on desktop, stacked on mobile).
- Per-version server-side session keyed by (browser sid in localStorage, version): v3/JEV keep {hist, mission}; agent.py is single-turn, so the adapter prepends the last 3 turns as plain-text context. Reset button per version (+ «همه» in compare mode). Compare-mode turns are also appended to each version's own history.
- Per answer: latency, LLM calls, tokens, cost (from usage dicts; v3/JEV also add any embedding-cost delta), collapsible «دیباگ» JSON: JEV → jev_params, guards, candidate_categories, fetch (sql_notes/top), check, fallback_reason, SQL used (captured via sqlite trace callback on A.RO, longest 8 distinct); V3 → tool_trace + SQL used + hydration log; current → tool_calls (+ result preview).
- Blocks (product_cards, sellers, verify, compare, map, plan, chips) are rendered as v2-styled cards (RTL, Vazirmatn, same card/pill/tile look). They are already hydrated server-side from torob.sqlite by A.hydrate inside the agents; the UI never invents prices. Chips are clickable. Map = list of pins with OpenStreetMap links (no embedded map). agent.py has no blocks (text only).
- Spend: top bar shows "this session" spend (persisted in `playground_spent.txt`, survives restarts) + project estimate (base $0.82). HARD session cap PLAYGROUND_SPEND_CAP=0.10 USD: the server refuses sends (HTTP 402) once reached.

## Adapter notes (no agent files modified)
- tools.con was opened with check_same_thread=True at import; playground_app reopens it shareable (same DB + same SQL functions) and assigns tools.con.
- All engine calls run under one DB lock (tools.con and agent_v3.RO are shared) → compare mode runs the 3 engines one after another (latency of the request ≈ sum; each version's own latency is measured separately).

## Running processes
- Server: `uvicorn playground_app:app --host 127.0.0.1 --port 8765` log: /workspace/torob/eval/playground_server.log
- Tunnel: `playground_tunnel.sh` (supervisor loop) → ssh -R via Pinggy free (SSH wrapped in TLS on 443 via openssl ProxyCommand), logs: /workspace/torob/eval/playground_tunnel_pinggy.log; current public URL always in /workspace/torob/eval/playground_url.txt (history in playground_url_history.txt)
- Find PIDs: `pgrep -af "uvicorn playground_app|playground_tunnel.sh|a.pinggy.io"`
- Stop: `pkill -f playground_tunnel.sh; pkill -f a.pinggy.io; pkill -f "uvicorn playground_app"`
- Start:
```
cd /workspace/torob/eval && source /workspace/.venv/bin/activate
PLAYGROUND_TOKEN=$(cat playground_token.txt) PLAYGROUND_SPEND_CAP=0.10 nohup setsid uvicorn playground_app:app --host 127.0.0.1 --port 8765 > playground_server.log 2>&1 < /dev/null &
nohup setsid ./playground_tunnel.sh > /dev/null 2>&1 < /dev/null &
sleep 15; cat playground_url.txt
```

## Tunnel caveats (honest)
- cloudflared quick tunnel: installed (/usr/local/bin/cloudflared 2026.10.3) but FAILS here: the box egress blocks port 7844 (QUIC and HTTP2) → Cloudflare 530. localtunnel (loca.lt): registers but returns 502 (data port blocked). tunnelmole: uses port 8083 (blocked). serveo/localhost.run: port 22 blocked, TLS on 443 refused.
- Pinggy free works, BUT: (1) each tunnel expires after 60 min; the supervisor reconnects automatically and the hostname CHANGES each time → always read playground_url.txt; (2) browsers first see a Pinggy "Caution… served for free through pinggy.io" interstitial — tap the continue button once (sets a cookie); curl/scripts can send header `X-Pinggy-No-Screen: 1`; (3) it is a third-party free relay: fine for a demo, not for anything sensitive.
- A stable URL needs a paid/registered tunnel (Pinggy Pro, ngrok account, named Cloudflare tunnel — the latter still needs port 7844) or the Liara deploy.

## Smoke (done once, 2026-10-22 ~20:50 Tehran) — results in playground_smoke_run1_compare.json, playground_smoke_run2.json
Message «ارزان‌ترین پلی استیشن ۵» through the public URL. Run 1 (compare): V3 answered; current + JEV hit a sqlite cross-thread error (fixed via the adapter above). Run 2: JEV and current, single mode — both answered. Task spend $0.0059.
Screenshots ($0, rendered from the recorded smoke answers at 390px): playground_shot_jev.png, playground_shot_compare.png.

## V3+ (added 2026-10-22 ~22:25 Tehran)
- 5th option «V3+» = `agent_v3plus.run_agent_v3plus` (separate instance of v3 code + product_knowledge + consultant prompt `v3plus_prompt.txt`). «مقایسه» now runs all 4 engines (≈4× cost, confirm dialog). Details and eval: `v3plus_eval_report.md`. Backups of the pre-V3+ files: `v3plus_runs/playground_app.before_v3plus.py`, `v3plus_runs/playground.before_v3plus.html`.
- Tunnel caveat seen: when ssh exits with "server not responding", an orphan `openssl s_client` can keep the supervisor's pipe open and block reconnection; `pkill -f "openssl s_client -quiet -connect a.pinggy.io"` unblocks it (the loop then reconnects with a new URL).

## Drill-down, related products, next prompts, V3+ session memory (added 2026-10-23 ~10:30 Tehran) — all $0 LLM
- New module `playground_drill.py` (pure SQLite + stored `product_emb.f16.npy`; imports no LLM/HTTP client).
- Endpoints (same token): `GET /api/product/{id}/offers` (all offers + shop by shop_id, price, date_fa, age_days, labels «قدیمی» >30 d / «مشکوک» <40% of median (needs ≥3 priced offers), sorted fresh+cheap → stale → suspicious → unpriced, «نامشخص» for unknowns, note «پیشنهاد ثبت‌شده؛ موجودی تضمین نیست»), `GET /api/shop/{id}` (address, area, city, lat/lon + OSM link, per-day hours from shop_hours, payment options, categories, fast delivery, website/instagram, phone only as «شمارهٔ نمایشی دیتاست، واقعی نیست», no tel:, 8 recent offers), `GET /api/product/{id}/related?k=8`, `GET /api/memory?sid&version`, `POST /api/memory/select`, `POST /api/memory/clear`.
- `/api/send`: every engine answer gets `related` (≤8 cards: same category/model family ranked by stored embeddings, lowest fresh DB price). V3+ also gets `suggestions` (3 next prompts: model's `next` key in the same completion → chips block → server templates) and `memory.chips`.
- V3+ context is now structural: system message "Session memory" (intent, category, budget, area, features, last-shown products in order, shops, drawer selections; prices masked) + last 4 turns (assistant text trimmed to 260 chars) instead of the whole raw history. Debug shows `session_memory_injected`.
- agent_v3plus.py: returns `suggestions` from the final JSON `next` (filtered: no calls/purchases/ids/prices). Prompt: `next` key added. Backups: v3plus_runs/backup_<ts>/.
- Evidence: v3plus_runs/drill_evidence/.
- Box rebooted ~09:50 on 2026-10-23: /workspace/.venv recreated (fastapi uvicorn openai numpy playwright) and openssh-client reinstalled (tunnel needs ssh).

## Tone / no server labels / clarifying questions (2026-10-23 ~13:50 Tehran)
- agent_v3plus.py: prose prices are plain (e.g. «۱۶۲٫۹۵ میلیون تومان», distance only when known); no dates/«قدیمی»/«مشکوک» in text (cards keep badges); spec provenance labels, hours label, draft line and knowledge note removed; `sanitize_boilerplate()` (BOILERPLATE_DROP / BOILERPLATE_CLAUSE regex lists, logged in debug `sanitizer_removed`) runs on the raw model text and again after rendering (and on the agent.py fallback text in playground_app); `validate_questions()` validates the model's `questions` (≤3, id/title/type single|multi|text|range, 2–6 options, no Latin/contact words).
- v3plus_prompt.txt: new STYLE section with BAD/GOOD examples, hours/verify disclaimers removed, `questions` schema.
- /api/send returns `questions` (V3+); answering a card sends a composed Persian message + `answers` → stored as session prefs (memory chips, injected as "shopper already answered").
- Evidence: v3plus_runs/tone_evidence/. Backup: v3plus_runs/backup_20261023_132153/.

---

## API for final UI

**Common rules**
- Base: `http://127.0.0.1:8765`, or the public URL from `playground_url.txt` (it rotates about every 60 min).
- Every call needs `?token=<TOKEN>`. Over the tunnel, also send the header `X-Pinggy-No-Screen: true`.
- All responses are JSON in UTF-8 and Persian. Errors look like `{"detail": "..."}` with status 403 (token), 404 (unknown id), 400 (bad input) or 402 (spend cap).
- Prices are integers in **toman**, read only from the DB. A missing value is `null` and the UI shows «نامشخص».
- Shops are always linked by `shop_id`.
- `phone_display` is a fake dataset number. Never render it as `tel:`, and always show `phone_note`.
- `llm_calls` in a response says whether the call spent anything. Every endpoint except `/api/send` and `/api/product/{id}/about` is `0`.

### Chat
| Method | Path | Body / query | Returns |
|---|---|---|---|
| POST | `/api/send` | `{message, sid, mode: "current"\|"v3"\|"jev"\|"v3plus"\|"compare", answers?: [{id,title,answer}]}` | `{results:[R], status}` |
| POST | `/api/reset` | `{sid, version: <mode>\|"all"}` | `{ok}` |
| GET | `/api/status` | – | spend counters: `spent_session`, `calls`, `cap_session`, `project_base`, `llm_cost_process_usd`, … |

`R` (one per version):
- `text`: Persian prose. Price tokens are already rendered, and there are no server-added labels.
- `blocks`: cards, `[{type: products|sellers|verify|map|…, items:[…]}]`. Product items carry `product_id`; offer items carry `offer_id`, `shop_id`, `price_toman`, and `shop{name, area, …}`.
- `related`: `[{product_id, title, image, price{…}, similarity, why}]`
- `suggestions`: `[str]`, up to 3 next-prompt chips.
- `questions`: `[{id, title, type: single|multi|text|range, options[], allow_custom, min?, max?}]`. Answers come back through `answers`.
- `memory`: V3+ memory chips `[{key, label}]`.
- `list_hook`: `{label:"به لیست اضافه کنم؟", product_id, shop_id, offer_id, title, shop_name}` or `null`.
- `bazaar`: same object as `/api/bazaar`, or `null`.
- `metrics`: `{latency_s, llm_calls, tokens, prompt_tokens, completion_tokens, cost_usd}`
- `debug`: tool_trace, sanitizer_removed, … (dev only).
- `ok`, `version`, `engine`

### Product & shop (DB only)
| Method | Path | Returns |
|---|---|---|
| GET | `/api/product/{pid}/offers` | `{product_id,title,brand,category,model,image, min_price,min_fresh_price,median_price, n_offers,n_shops,n_priced,n_stale,n_suspicious, rules{stale_days:30,suspicious_ratio:0.4,median_needs_priced_offers:3}, note, offers:[{offer_id,shop_id,shop_name,shop_area,shop_has_address,shop_has_location,shop_lat\|null,shop_lon\|null,price_toman\|null,price_note,date,date_fa,age_days,stale,suspicious,labels[],seller_title,warranty}]}`. Sorted fresh and cheap first. |
| GET | `/api/product/{pid}/details` | `{product_id,title,brand,category,model,image, images:[url≤12], specs:[{section, items:[{key,value}]}], n_specs, stats{n_offers,n_shops,n_priced,min_price,min_fresh_price,median_price,max_price,n_stale,n_suspicious,latest_price_change_fa}, llm_calls:0}` |
| GET | `/api/product/{pid}/about` | `{product_id, sentences:[str 2–5], cited:[{text, refs:[n]}], sources:[{n,title,url,engine:"boxapi_web_search"\|"digikala"\|"wikipedia"}], status, cached, llm_calls, cost_usd, query, n_relevant}`. See the notes below the table. |
| GET | `/api/product/{pid}/related?k=8` | `{product_id, related:[{product_id,title,brand,category,image,similarity,same_model,price{…},n_offers,n_shops,why}]}`. Built from stored embeddings, no API call. |
| GET | `/api/shop/{sid}` | `{shop_id,name,address,area,city,lat,lon,map_url, hours:[{day,hours,today}],hours_note, categories[],n_categories,payment_options[],fast_delivery,website,instagram, phone_display,phone_note, n_offers,n_products,last_price_change_fa, recent_offers:[{offer_id,product_id,title,price_toman,date_fa,age_days,labels}]}` |

Notes on `/about` (v3, 2026-10-23 18:xx — current):
- Engine: BoxAPI's own web search. BoxAPI docs don't document it; found by testing: **Responses API** `POST https://ai.boxapi.ir/ai/v1/responses` with `model:"gpt-6-luna"`, `tools:[{"type":"web_search"}]` (`reasoning:{effort:"low"}`, `max_output_tokens:900`). The answer's `output[].content[].annotations[]` carry `url_citation {url,title,start_index,end_index}`. Not supported: chat `web_search_options` / `plugins` (400 unknown parameter), chat `tools:[{type:"web_search"}]` (400), `openai/gpt-6-luna:online` and `perplexity/sonar*` (403 model_not_allowed).
- Input: DB title, brand, model, category, plus an accessory flag computed from the DB title (محافظ/گلس/کاور/قاب/…); 2–4 Persian sentences, one per line, each ending with its web citation; NONE if the exact product can't be confirmed; no prices/sellers/warranty; no colour/size/capacity not in the title.
- Code checks: lines without a citation or with price/seller words are dropped; for a device, any sentence claiming it is an accessory («محافظ صفحه», «نه خود…») rejects the whole note (`contradicts_db_type`); for an accessory, the note must say so (`accessory_not_described`); at least one cited page title/URL must contain the model code (`model_not_in_sources`, e.g. Dahua HDW1200TRQP-A vs pages about HDW1200TRQ). `cited[i].refs` are 1-based indexes into `sources` (deduped URLs).
- Cache `about_cache_v3/`. If the web-search call itself errors, the v2 Digikala path below is used (`web_search_error` set); v2 now also rejects «… مناسب برای …»/protector/case listings (the Mibro GS Pro bug: Digikala matched «محافظ صفحه نمایش … مناسب برای ساعت میبرو GS Pro»; the DB item is the watch, 11.9M toman, category ساعت و مچ بند هوشمند).
- Test (`v3plus_runs/about_web/`): 10 products → 9 ok, 1 correctly withheld (Dahua: sources were a different variant); ≈$0.0011 per call (0.0006–0.0022), 4–7 s (one 13.6 s).

Notes on `/about` (v2, 2026-10-23; code in `playground_about.py` + `about_sources.py`):
- `status` is one of: `ok`, `no_matching_source`, `model_unsure`, `model_output_rejected`, `llm_error`, `spend_cap`, `empty`.
- If `sentences` is empty, the UI hides the section. While loading, the drawer shows «در حال جمع‌آوری اطلاعات از منابع…» (timeout 45 s), then the section or nothing.
- `cited[i].refs` lists the `sources[].n` numbers that sentence i cited (the UI shows them as small superscripts next to numbered source links).
- Steps:
  1. Identity from the DB title/brand: brand (Persian→Latin map), model codes (Latin+digit tokens, units like 256GB/4K/5G excluded) and distinctive tokens (e.g. «دیزایر رد» → desire red, «مک بوک ایر» → macbook air).
  2. Digikala public JSON search (up to 3 queries: cleaned title, full title, brand + codes) → deterministic match: same brand (a different seller brand such as a knock-off is rejected), every model code / distinctive token present, same product type (category guard), no extra variant word (Ultra/Pro/NC/Digital Edition/Blue/USB-C…). Then the matched product page's text: description, expert-review sections, pros/cons and specs.
  3. English Wikipedia article only if its title contains every model token (e.g. EarPods).
  4. One gpt-6-luna call (≤250 output tokens, reasoning `none`) over the numbered passages; it must cite `[n]` and output NONE for a different model. Sentences without a citation or mentioning price/seller/warranty/delivery are dropped; at least 2 must remain.
  - Bing HTML was dropped as the main source (from this box it often returns generic/unrelated pages); Torob's own site answers with a captcha and is not used; Google needs JS.
- The result is cached to `about_cache_v2/{pid}.json` (old v1 negatives in `about_cache/` are ignored) and is not cached on errors.
- Calls are serialized by a lock, so opening the same product twice cannot cause double spend.
- Evaluation (21 diverse products, `v3plus_runs/about_fix/`): before 0–5/21 could even reach the LLM (5 `would_call_llm`, 11 `no_relevant_snippets`, 5 `no_model_key`); after **16/21 ok (76%)**, 5 cleanly hidden (no matching source: no-name UBOX cam, Julius JA1393A, Vans «Dior», Nilper GAR111, Xiaomi TV «A Pro»).

### Bazaars / «بورس این کالا» (data-driven, `bazaars.json` built by `build_bazaars.py`)
`GET /api/bazaar?product_id=…` (or `?category=…`, or `?q=<free text>`) returns:

`{group, shops_total, hubs:[{name, hub_name, named_by:"address_mentions"|"location_label", center:[lat,lon], map_url, shop_count, share_of_group_offers, shops:[{shop_id,name,area,address,lat,lon}](≤4), evidence, evidence_fa}](≤2), note, llm_calls:0}`

`evidence_fa` is a Persian sentence with Persian digits and no distances, for example «۵۱۳ فروشگاه از ۷۵۹ فروشگاه این محدوده در آدرسشان «لاله زار» آمده است.»

When nothing matches, it returns `{group:null, hubs:[]}`.

A hub gets a bazaar name only when two things hold: at least 20% of the hub's shops mention that name in their address, and the name's location is no more than 1 km from the hub center. The same data is available to V3+ as the tool `bazaar_hubs(need)`, and a compact summary is in its system prompt.

### V3+ session memory
| Method | Path | Body / query | Returns |
|---|---|---|---|
| GET | `/api/memory?sid=&version=v3plus` | – | `{chips:[{key,label}], view{goal,category,budget_toman,area,features,products,shops,selections,prefs,…}, injected:str, turns}` |
| POST | `/api/memory/select` | `{sid, version:"v3plus", kind:"product"\|"shop", id}` | `{ok, chips}` |
| POST | `/api/memory/clear` | `{sid, version, key:"all"\|<chip key>}` | `{ok, chips}` |

### Saved lists / virtual basket (no AI; `user_lists.sqlite`; `cid` = anonymous id in localStorage `pg_cid`)
Every list call returns the full state `L`:

`{client_id, lists:[{list_id, name, n_items, items:[I], total_toman, n_unknown_price, total_is_partial, shops:[{shop_id,name,address,area,lat,lon,map_url,n_items}], created_at, updated_at}], note}`

The item `I` is:

`{item_id, product_id, shop_id, offer_id, title, image, qty, price_toman|null (snapshot), price_date_fa, labels, price_basis, shop:{shop_id,name,address,area,lat,lon,map_url}, added_at, refreshed_at}`

The default list «لیست من» is created automatically. Ids belonging to another `cid` return 404.

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/api/lists?cid=` | – | `L` |
| POST | `/api/lists` | `{cid, name}` | `L + created_list_id` |
| POST | `/api/lists/{list_id}/rename` | `{cid, name}` | `L` |
| POST | `/api/lists/{list_id}/delete` | `{cid}` | `L` |
| POST | `/api/lists/{list_id}/refresh` | `{cid}` | `L + changes:[{item_id, title, old_price, new_price} | {item_id, status:"product_missing"}]`. Re-reads prices from the DB. |
| POST | `/api/lists/items` | `{cid, product_id, shop_id?, offer_id?, list_id?}` | `L + item_id, list_id, already_saved` |
| POST | `/api/lists/items/{item_id}/delete` | `{cid}` | `L` |
| POST | `/api/lists/items/{item_id}/move` | `{cid, to_list_id}` | `L` |
| POST | `/api/lists/items/{item_id}/qty` | `{cid, qty}` | `L` |

How `add_item` picks the snapshot price, in order:
1. the given offer;
2. else the cheapest offer at the given shop;
3. else the best fresh price.

### UI components (playground.html)
- `pcard` / `rcard`: product cards with a ♡/♥ save button.
- Drawer, top to bottom:
  - summary
  - «دربارهٔ این محصول» (lazy; hidden when empty; sources are small host links)
  - gallery (scroll-snap)
  - key-value stats
  - specs grouped into collapsible `<details>`
  - seller offers (each with a save button)
  - «بورس این کالا» card
  - related products
- Shop view: address, OSM link, hours, fake phone with its note, recent offers.
- «لیست‌های من» panel: tabs, inline rename, total, refresh, move/remove, and a Leaflet map (falls back to OSM links).
- Chips (suggestions, memory, hook) and question cards.

### Streaming chat: `POST /api/send_stream` (SSE, V3+ only)
Same JSON body as `/api/send` (`mode` must be `v3plus`); `/api/send` is unchanged. Response `text/event-stream`, each event `event: <name>\ndata: <json>\n\n`; every data has `t_ms` (ms since the request):
- `status` `{stage:"received"|"thinking"|"searching"|"writing"|"checking", step?, tools?:[names], tool?, n_found?}` — progress only (keeps the mascot busy); `n_found` = how many products a search tool returned. **Raw tool results are never sent as cards** (the old `products` event is gone: it showed unselected search hits, e.g. MacBooks for «لپ تاپ مناسب گیم», that were then replaced).
- `cards` `{items:[…], final:true}` — sent **at most once per turn, before any text**: exactly the agent-selected, server-checked `product_cards` items of the final answer (same objects/order as in `final`). Emitted right after the answer check (claim/coverage/price checks, regeneration). Non-agent turns (plan revision, fallback) send it from the final payload, still before text. The server also adds a card for every product the text names by price token (text product mentions ⊆ cards; logged `hydration.v3plus.cards_added_for_text`).
- `text` `{chunk}` — the final, server-checked text in 40-char chunks.
- `final` `{results:[…], status}` — exactly the `/api/send` payload. Or `error` `{error}` (e.g. spend cap).
- Frontend contract (/workspace/torob-app `App.tsx`/`Chat.tsx`): render cards once from `cards` and never replace/reorder them; a second `cards` event is ignored with `console.error`; if `final` cards differ from shown cards (impossible by design) the shown ones stay and a `console.error` is logged; with no `cards` event, `final` renders as usual.
- Measured (`v3plus_runs/sse_cards/timeline.json`, public URL): exactly 1 `cards` event per turn, before text, identical to final. Time to first card ≈ total minus ~0.2 s (gaming laptop 19.8 s / 5 rounds; headphones 6.7 s; phone 9.7 s); before the fix the first (raw, later replaced) cards came at ~2.8 s.

Speed changes (2026-10-23): V3+ `MAX_STEPS` 8→5 and a prompt «SPEED» rule (all tool calls in one parallel step, usually one tool round); `text_search` results cached 15 min per (query,k); per-LLM-round timing in `usage.llm_steps` [{ms,in,out,tools}]. Before→after on 3 queries (`v3plus_runs/speed/`): 25.3/13.1/12.4 s → 7.1/13.4/9.0 s (avg 16.9 → 9.8 s); LLM rounds 8/4/4 → 2/4/3. Each round ≈2–4 s of BoxAPI latency; tools are ms except embedding search (~2 s).

### Price consistency + plan follow-ups (2026-10-23 18:5x)
- Text prices = card prices: when a product is on a product card, its `[[offer:…]]`/`[[product:…]]` token renders «از <card min> تومان» with the SAME min the /app card shows (`playground_home.card_info`: fresh, non-suspicious offers). Then `price_guard()` scans every spoken «… تومان» amount: if it is not a card's min/max (±1%) or a DB-token price of a product without a card, it is rewritten to «از <card min> تومان» for the card named in that sentence (or the only card). Logged in `hydration.v3plus.price_card_aligned / price_guard_rewritten`. Test: `v3plus_runs/price_fix/test3.json`.
- Plan follow-ups: when `/api/send` carries `project` (→ mission `_ui_project`), V3+ never re-plans or asks questions. «ارزون‌ترش کن» → cheapest plan, «فقط از یه بازار» / «یه جا» → one-stop plan, «نزدیک X باشه» → re-search around X: deterministic `PRJ.search` over the session's needs (or the on-screen items), $0, ~2 s. Response: `engine:"v3plus-project-revise"`, text with old vs new total, `blocks` (product_cards + sellers of the new plan), and **`project_result`** = the `/api/project/search` payload plus `selected` (plan key), `revision` (cheaper|one_place|nearer), `title`, `goal`. Other follow-ups («X رو عوض کن») go to the agent with start_project disabled, a prompt rule to show alternatives, and `questions` forced to []. Tests: `v3plus_runs/project_followup/`.

### «خرید یکجا»: one-stop project shopping (feature 4)
**Flow**
1. Chat (V3+): project intent is detected two ways, then routed to `PRJ.plan` (one gpt-6-luna JSON call):
   - fast path: regex `PRJ.is_project` (e.g. «سیم‌کشی … ۸۰ متری») → planner directly, no agent call;
   - otherwise the V3+ agent decides in its normal first completion: it has a `start_project(goal)` tool (prompt: call FIRST and ALONE when the request needs a list of several different kinds of items — kitchen, home office, gaming setup, baby room, dorm, café, CCTV for a shop, rewiring; never for one product/one kind of product, gifts, prices or follow-ups). The agent loop returns `{project_intent, project_goal}` immediately and `run_version` calls the planner with that goal (so a routed turn = 1 agent step + 1 plan call). If the planner says `not_project`, the turn is re-run once with the tool disabled.
   - responses carry `project_route: "agent"|"regex"|"answers"`; the UI shows a small badge «🧺 درخواست چندقلمی تشخیص داده شد · خرید یکجا». Debug: `debug.project_route`.
   - test (`v3plus_runs/project_intent/test16.json`): 10 project phrasings (9 not caught by the regex) + 6 single-product asks → 16/16 correct, $0.020.
2. The plan call returns one of two things:
   - question cards: the existing `questions` format, answered through `/api/send` with `answers`. The pending goal is kept per session.
   - the needs checklist, returned as `R.project`.
3. The UI shows an editable checklist (toggle items, change qty, optional Tehran area), then «جستجوی همه» calls `/api/project/search`. Search and the optimizer are server-side with no LLM. One tiny LLM call writes the summary.
4. «ذخیره در لیست» calls `/api/project/save`, which creates a new list through the feature-3 storage.

`R.project` (from `/api/send`) = `{stage:"needs", goal, title, assumptions, area, needs:[N]}`

`N` = `{id, item, query, must:[≤2], avoid:[], category_hint, qty, unit, specs, priority:"essential"|"optional", why, enabled}`

| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/api/project/plan` | `{goal, answers?:[{id,title,answer}], force?}` | `{goal, intent, stage:"questions"\|"needs"\|"not_project", title, say, questions?, needs?, assumptions?, usage, llm_calls:1}` |
| POST | `/api/project/search` | `{needs:[N], area?, goal?, summarize?=true}` | `{plans:[PL], not_found:[{need_id,item,alternative:{product_id,title,min_price,category}\|null}], candidates:{need_id:{products[≤4],n_options,queries_tried,n_low_outliers_dropped}}, area, area_centre, rules, summary, summary_usage, llm_calls:0\|1, elapsed_s}` |
| POST | `/api/project/save` | `{cid, name, rows:[{product_id,shop_id,offer_id,qty}]}` | lists state `L` + `list_id, n_saved` |

`PL` = `{key:"cheapest"|"one_stop"|"balanced", name, also?:[names of identical plans], total_toman, total_is_partial, n_unknown, n_items_found, n_shops, n_stale, spread_km, hub:{name, all_shops_in_hub}|null, shops:[{shop_id,name,area,lat,lon,map_url,n_items}], rows:[{need_id,item,qty,unit,priority,product_id,title,image,offer_id,shop_id,shop_name,shop_area,price_toman,line_total_toman,stale,date_fa,age_days,badge:"به‌روز"|"قدیمی"}]}`

**Server rules**
- **Candidates:**
  - Lexical search runs on `query` and on `item`.
  - A title is kept only if it contains the head noun (or a known alias), every `must` token, and no conflicting word (for example a «پریز» title for a light switch).
  - Used and knock-off listings are dropped.
  - For roll units, titles with حلقه/۱۰۰ متر are preferred, and offers below 30% of the offer median (per-metre listings) are dropped.
  - Suspicious offers (below 40% of the product median) are excluded.
  - Stale offers (older than 30 days) stay in, but get a +15% penalty in the optimizer.
- **Plans:**
  - cheapest: the per-item minimum.
  - one_stop: a greedy shop cover, then a local search where the shop count dominates.
  - balanced: a local search on total + an extra-shop penalty of max(4% of the basket, 300k toman) + 1% of the basket per km of spread (haversine) + 1% per km from the user's area if one is given.
  - Identical plans are merged (`also`).
  - The hub is the bazaar from `bazaars.json` within 1.2 km of the plan's shops.
- **Prices:** every price and shop in a plan comes from the DB. Evidence is in `v3plus_runs/f4_project/verify_db.py` (0 mismatches).

**Structural compatibility (feature 4, part A)**
- **Planner attrs:** each need can carry `attrs: {system: ip|analog, poles, amps, cross_section_mm2, mp, channels, volt}`. If an attr is missing, it is parsed from the need's own words.
- **Title attrs:** product titles are parsed the same way by `attrs_of`:
  - amps, poles (تک/دو/…/2P), MP, channels, volts;
  - wire cross-sections (ignoring lengths);
  - CCTV system: IP (IPC, NVR, تحت شبکه, PoE, network) or analog (DVR, XVR, AHD/TVI/CVI, HAC, DS-2CE, RG59, کابل ترکیبی, BNC).
- **Matching:**
  - amps, poles and volts must be equal; MP and channels must be at least the requested value; the cross-section must be among the title's sections.
  - A numeric `must` token matches only as a whole number, so «2» no longer matches «32».
- **One system per plan:**
  - Each plan type (cheapest, one_stop, balanced) is optimized separately for the ip system and the analog system.
  - Core items (cameras, recorders) take same-system offers first. If none exist, they take unknown-system offers with the badge «سیستم نامشخص»; failing that, other-system offers with «ناسازگار احتمالی».
  - Accessories take same-system or unknown offers, otherwise «ناسازگار احتمالی».
  - A mismatch on a core item is lexicographically worst. A system whose basket costs more than twice the other's is never picked.
- **Plan and row fields:** a plan gets `system`, `system_label`, `n_incompatible`, `n_unverified`. A row gets `system`, `incompatible`, `unverified`, `compat_badge`.

## /app: real home page (added 2026-10-23 ~17:35 Tehran)
- `GET /app?token=…` serves the Vite build in `playground_app_dist/` (source: /workspace/torob-app, built from /workspace/torob-ux/react-home). Static files are under `/app/assets`. The API calls are same-origin.
- New GET endpoints (no LLM, `playground_home.py`): `/api/home/tiles`, `/api/home/category/{key}?sub&offset&limit`, `/api/home/deals?limit`, `/api/home/areas`, `/api/home/shops?area&tile|q&limit`.
- `/api/send` accepts an optional `area`. In v3plus it is stored as the mission fact `_ui_area`, which is not a hard filter.
- Deals rule: `playground_home.DEAL_RULE`.
- Backup: v3plus_runs/backup_20261023_171019_home/.

### /app product + shop screens (additive, DB-only, no LLM)
- `GET /api/home/cards?ids=product_…,…` — chat product cards: fresh-first price range (`min_price`/`max_price`), `n_shops`, top 1–2 shop areas (`area_label`).
- `GET /api/home/sellers/{pid}?area=ونک` — one card per shop (its best offer) + `fast_delivery` (shops.supports_fast_delivery), `installment`/`installment_providers` (shop_payment_options provider ∈ ترب‌پی، اسنپ‌پی، دیجی پی، تارا، ازکی‌وام), `warranty_info` (offers.warranty_months / warranty JSON; «بدون گارانتی» and «تست و تحویل…» = no warranty), `place` («بازار X» only when the shop is inside a bazaars.json hub radius, else shops.location_label), coarse `distance_label` + `near_rank` (no km), `cheapest`, `updated_fa`. Prices > 3× the product median are flagged `suspicious` (display only) and left out of ranges.
- `GET /api/home/shop/{shop_id}?product_id=…` — `/api/shop` fields + `open_now` (from shop_hours, Tehran time), `main_categories` with product counts, installment flags, `offer` (this product in this shop), `directions_url` (Google Maps from lat/lon).
- `POST /api/send` accepts `shop_id` (v3plus): the shop's DB facts are put in the session mission as `_ui_shop` (the app uses a separate `<sid>_shop` session), so shop-sheet questions are answered from shop data; unknowns (parking, stock) are said to be not recorded.

### Round budget, questions-with-answer, plan-update card (2026-10-23 19:05 Tehran)
- **LLM rounds enforced in code** (`agent_v3plus.py`): round 1 = tools (prompt asks for all calls in parallel); round 2 = answer with `tool_choice:"none"`.
  A second tool round (narrowed to find_products/text_search/product_knowledge/sql/geocode_area) is allowed only if round 1 returned nothing usable (error or 0 in-area results). Hard max 3 LLM calls.
  Answer-check repair is done in code (strip unsupported claims + inject left-out cheaper items + price guard); an LLM regeneration happens only if stripping would leave < 40 chars.
  `area:"user"` without a device location now falls back to the mission point / no area filter (it used to waste a round).
- **Questions rule**: if the answer shows products, `questions` is `[]` and the questions come as `refine:[{id,title,options[]}]` → chips under the answer (tap = sends the phrased answer, e.g. «بودجه‌ام تا ۱۰۰ میلیون»). The question sheet opens only when `questions` is non-empty, i.e. there is no product answer.
- **Plan follow-ups** (`project_result` with `selected`, `revision`, `title`, `goal`): the chat shows a «🧺 <title> · نسخهٔ ارزان‌تر / از یک بازار / فروشگاه‌های نزدیک‌تر» card (plan, total, items, shops, hub) whose button opens the same «خرید یکجا» plan screen with the revised plan's tab selected.
- debug now carries `llm_steps` (ms, tokens, tools per round).

### «کجای پاساژه؟», routing, «بسته بود؟ جایگزین بده» (2026-10-23 19:40 Tehran) — module `playground_mall.py`
No new pages: everything lives in the shop sheet, the product sellers list and chat.
- `GET /api/shop/{sid}/place` ($0) → `{in_mall, mall, floor, floor_label, unit, unit_label, block, needs_lookup, web, routes}` parsed from the DB address
  (پاساژ/مجتمع/مرکز خرید/ساختمان تجاری/سرای/تیمچه/بلوک…, طبقه N / اول…/همکف/زیرهمکف/منفی یک, واحد/غرفه/پلاک incl. A12). Of 3,591 mall shops: floor 3,114, unit 3,434, both 3,006.
  Also embedded in `/api/home/shop/{sid}` as `location`, plus `routes`, `open_state`, `open_badge`.
- `POST /api/shop/{sid}/place/find` (1 BoxAPI Responses call, `gpt-6-luna` + `tools:[{type:"web_search"}]`, effort low, ≈$0.0006–0.002, cached in `mall_cache/`) →
  `{status: ok|unknown|not_in_mall|spend_cap, floor, unit, landmark, source_url, source_title, cited_urls, why}`. `ok` only if the model's source URL is one of its own url_citations
  and gives a floor/unit; rejected when it contradicts the DB (a DB «پلاک» counts as the shop's unit only when the DB also has a floor). Anything else → «نامشخص».
- Routing: `routes = {neshan: https://neshan.org/maps/routing/car/destination/LAT,LON, google: https://www.google.com/maps/dir/?api=1&destination=LAT,LON}` (one button, tiny choice).
  «مسیر خرید روی نقشه» (plan screen): nearest-neighbour order from the selected area → one Google Maps multi-stop link (`waypoints`, walking, ≤10 stops); the order is shown as a toast.
  `POST /api/route/multi {shops:[{shop_id,lat,lon}], start?:[lat,lon]}` → `{order, url}` (same algorithm, server side).
- Open/closed: `open_state` = open | closed_now | closed_today | unknown and `open_badge` «الان بازه» / «الان بسته» / «امروز تعطیل» / null, from `shop_hours` vs Tehran time;
  on every seller row of `/api/home/sellers/{pid}` and in the shop sheet. No phone links anywhere.
- `GET /api/shop/{sid}/alternatives?product_id=` ($0, DB only) → `{shop_name, product_title, basis: same_product|same_product+same_model, items:[{shop_id, shop_name, offer_id, product_id,
  same_product, price_toman, place, distance_label, open_badge «الان بازه»|«ساعت نامشخص», is_open, routes}]}`: the 3 nearest other shops (distance from the closed shop, in words:
  همین پاساژ / چند قدم آن‌طرف‌تر / همین نزدیکی / نزدیک / کمی دورتر / دور) that are open now or have unknown hours; price outliers (<0.4× or >2.5× median) dropped.
- Chat: «بسته بود» / «جواب نداد» / «تعطیل بود» … about a shop in context (shop sheet opened with a product → `/api/memory/select {kind:'shop', id, product_id}`, or a shop shown in a sellers block,
  or a shop named in the message) → engine `v3plus-closed-alternatives`, no LLM: short text + product card + `alternatives` (rendered as the same list).
- UI: shop sheet «جای دقیق مغازه» chips + «پیدا کردن جای دقیق» (only for mall shops missing floor/unit) + source link; «مسیریابی تا فروشگاه» → «نشان | گوگل‌مپ»;
  «بسته بود؟ جایگزین بده» (prominent when closed; also under the product card and on the «ترب برام زنگ بزنه» mock); seller rows show the badge and «جایگزین باز ←» (opens the sheet with the list loaded).
  Deep link `/app/?shop=<shop_id>&pid=<product_id>` opens a shop sheet.
