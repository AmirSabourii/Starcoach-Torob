# استارکوچ — دستیار خرید حضوری ترب

Persian, RTL, mobile-first shopping assistant over the Torob Starcoach dataset. The assistant answers only from tool results: products, in-person shops in Tehran, price, distance, freshness, warranty and recorded payment options.

The agent, the eight tools and the recall layer are the validated off-repo implementation, packaged under `backend/app/engine/`. The UI is the `src-v2` design (Vazirmatn, cards, step trail), wired to this API.

## Evaluation

Full write-up: [`eval/FINAL_REPORT.md`](eval/FINAL_REPORT.md). Same harness and datasets live in `eval/` (`eval_set.json` 60 questions, `recall_tests.json`, `discovery_tests.json`).

| Check | Result |
| --- | --- |
| 60 grounded scenarios, cleanest full run (run2, lexical) | **98.3%** |
| Same 60 with the recall layer, full run3 | **93.3%** (95.0% after rescoring) |
| Honest refusals (stock, reviews, price history, and the other unanswerable items) | **8/8** |
| Recall@5 on deliberately badly written queries | **0.97** (hit@5 1.00; lexical baseline was 0.48) |
| Discovery / browse scenarios | **15/15** |

The “100%” figure in the report is not a clean full run. It swaps four items from small re-runs into run3. The cleanest full-run numbers are run2 at 98.3% and run3 at 93.3% (95% rescored).

Re-run (needs `BOXAPI_API_KEY`, the built database, and for the embedding row the `.npy` cache):

```bash
python scripts/build_db.py
python eval/run_eval.py --tag run1
python eval/recall_eval.py
python eval/run_discovery.py --tag d1
```

Reports already in the repo: `eval/eval_report.md`, `eval/recall_results.json`, `eval/discovery_report.md`, `eval/data_findings.md`. Saved model transcripts are not committed.

## Model

| | |
| --- | --- |
| Chat model | `gpt-6-luna` (`BOXAPI_MODEL`) |
| Base URL | `https://ai.boxapi.ir/ai/v1` (`BOXAPI_BASE_URL`) |
| Key | `BOXAPI_API_KEY` at deploy time. Never committed. |
| Completion cap | `max_completion_tokens` (this model rejects `max_tokens`) |
| Tool calling | `reasoning_effort="none"` on `/v1/chat/completions` |
| Embeddings | `text-embedding-3-small`, 256-d, optional cache |

Recall is **on** by default (`TOROB_RECALL=1`): alias / synonym dictionary, digit and ZWNJ and ك/ي normalisation, LLM query expansion, embedding fallback, match-grader. `TOROB_RECALL=0` is the lexical baseline. Without the embedding file the embedding step returns nothing. Without an API key the expander and grader fail closed; catalogue HTTP search then stays on the lexical tool so the UI still shows rows. `/chat` itself does not answer until the key is set, and it does not invent products.

Price staleness inside the tools is **90 days** from the reference date 2026-10-22.

## Tools

| Tool | Role |
| --- | --- |
| `search_products` | Normalised FTS over title, brand, model, category, plus the recall layer. |
| `compare_products` | Specs and price range for 2–4 ids. |
| `find_stores_for_product` | Shops, haversine distance, last price change, stale flag. |
| `compare_stores` | Those shops side by side. |
| `check_store_freshness` | Days since `last_price_changed_at`. |
| `contact_store` | Address, hours, payment. Phone numbers are **FAKE**. No dial action. |
| `search_stores` | By area label, category sold, or installment provider, with counts. |
| `browse_catalog` | Whole category: brands, counts, price ranges, a short sorted list. Drops knock-offs, accessories, used items and basic phones; flags clones. |

Not in the data, and not shown as if they were: stock counts, user reviews, price history.

## Data

Download only (never commit the zip, the CSVs, the sqlite file, or embeddings):

`https://startech.s3.ir-central1.arvanstorage.ir/starcoach-dataset-v16-cap300-csv.zip`

Joins: `offers.shop_id` → `shops.shop_id`, `offers.product_id` → `products.product_id`.

`scripts/build_db.py` calls `build_eval_db.build`: `norm()` (Arabic yeh/kaf, ZWNJ, digits), FTS5 on normalised title + brand + model + category, parsed `product_specs`, prices outside `[1000, 1e11]` stored as NULL with `price_status`, plus `shop_categories`, `shop_hours`, `shop_payment_options`. Rebuilds are idempotent (temp file, then replace).

## Run locally

Python 3.12.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# optional: put BOXAPI_API_KEY in .env — do not commit .env

python scripts/build_db.py
# CSVs already extracted:
# python scripts/build_db.py --skip-download

# once, only if you want the embedding fallback (calls the API, writes gitignored files):
# python scripts/embed_products.py

uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

Open `http://127.0.0.1:8000`.

- The composer posts to `POST /chat` and renders the model’s answer plus the tool steps (understand → search → distance filter → rank) using the counts in the tool JSON.
- Product cards show the last price change and a stale warning. Store lists are sorted by distance.
- Compare, installment, guided questions and the no-result state are the same screen.
- If the key is missing, `/chat` returns 503 and the suggestion chips still render catalogue cards from the tools, labelled as not from the model.
- Design frames, unchanged, are under `/screens/` (for example `/screens/overview.html`).
- `GET /health` returns 200 even before the database exists, so a deploy can boot first and load data after.

Checks that do not call the model:

```bash
python3 -m unittest discover -s tests -v
```

## Deploy on Liara

The app is one Docker service (API + UI) on port 8000. `liara.json` uses the Docker platform and a `/health` check. The image does not contain the dataset.

```bash
# from the repo root, with the Liara CLI logged in
liara deploy --app starcoach-torob --platform docker --port 8000
```

Attach a disk mounted at `/data` (create the disk in Liara first; an unknown disk name fails the deploy). Then set:

```text
DATABASE_PATH=/data/torob.sqlite
DATA_DIR=/data
BOXAPI_API_KEY=...          # secret, not in git
BOXAPI_BASE_URL=https://ai.boxapi.ir/ai/v1
BOXAPI_MODEL=gpt-6-luna
```

On the disk, once:

```bash
python scripts/build_db.py
python scripts/embed_products.py   # optional
```

`docker compose up --build` is the same layout locally (`./data` → `/data`).

## Layout

```text
backend/app/engine/     validated tools, agent, recall, build_eval_db, gt_lib, embed_products
backend/app/api/        /chat, /health, catalogue and store routes
backend/app/main.py     serves the API and frontend/
frontend/               live RTL UI, Vazirmatn, assets
frontend/screens/       design pages from the UX pack
design/research.md      UX rationale
eval/                   harness, datasets, FINAL_REPORT.md
scripts/build_db.py     download zip → sqlite
scripts/embed_products.py
```

## Tests in this repo

`tests/test_wiring.py` builds a tiny CSV with the real builder and checks normalisation, dirty prices, FTS (including Arabic kaf), distance order, the 90-day stale flag, browse filters, installment counts, the fake-phone warning, `/health` without a database, static files, and that the chat call uses `max_completion_tokens` and `reasoning_effort='none'`. It does not call BoxAPI.
