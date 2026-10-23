# Deploying to Liara (Iranian PaaS)

Docker platform app. Code is baked into the image; the 703 MB SQLite DB and the embeddings live on a
Liara **disk** mounted at `/data` (they are NOT in git). `backend/start.sh` links them into the code dir at boot.

## Layout
```
backend/            FastAPI app (playground_app:app) + routers + agents + prompt + prebuilt UI (playground_app_dist/)
backend/start.sh    entrypoint: unpacks /data/torob.sqlite.gz on first boot, symlinks data/caches from /data, runs uvicorn
backend/requirements.txt
frontend/           React/Vite source (build: cd frontend && npm ci && npm run build; copy dist/ -> backend/playground_app_dist/)
Dockerfile, .dockerignore, liara.json
deploy/liara_setup.sh   one-shot API setup (create app, disk, envs, FTP data upload, source deploy, check)
.env.example        all env var names (no values)
```

## Data files needed on the disk (`/data`)
| file | size | source |
|---|---|---|
| `torob.sqlite.gz` (unpacked to `torob.sqlite` on first boot) | 181 MB gz / 737 MB raw | `build_eval_db.py` or `/workspace/torob/deploy/data/` |
| `product_emb.f16.npy` | 116 MB | `embed_products.py` |
| `product_emb_ids.json` | 8 MB | `embed_products.py` |
`user_lists.sqlite`, `playground_spent.txt` and all caches (`/data/cache/*`) are created at runtime.
Disk size: 2 GB is enough (raw DB + gz + embeddings ≈ 1.05 GB). After the first boot you may delete `torob.sqlite.gz`.

Alternative to FTP: put `torob.sqlite.gz` in object storage and set `TOROB_DB_URL` to a pre-signed URL;
`start.sh` downloads + unpacks it on first boot if `/data/torob.sqlite` is missing.

## Environment variables (Liara console -> app -> Settings -> Environment variables)
See `.env.example`. Required: `BOXAPI_API_KEY`, `AVALAI_API_KEY`, `PLAYGROUND_TOKEN`, `PLAYGROUND_SPEND_CAP=0.50`,
`DATA_DIR=/data`, `TOROB_DB_PATH=/data/torob.sqlite`. Optional: `TRYON_MODEL`, `TRYON_API`, `TRYON_CAP_USD`,
`TRYON_PER_SESSION`, `MALLGUIDE_CAP_USD`, `AVALAI_BASE_URL`, `AVALAI_NATIVE_URL`, `TOROB_DB_URL`.

## Plan
Cheapest workable: **small-g2** (0.5 GB RAM, 0.5 vCPU, 5 GB storage) + feature bundle **basic**
(Liara: small-g2 475,000 Toman/month ≈ 659.72/h; basic bundle 275,000 Toman/month ≈ 381.94/h; total 750,000 Toman/month).
g2 plans require a private network id (`GET /v1/networks`) and a bundle plan when creating the app.
Note: idle RSS ≈ 140 MB; first embedding search loads ~230 MB more. If the app is OOM-killed, resize to `medium-g2`
(`POST /v1/projects/<app>/resize {"planID":"medium-g2"}`).

## Steps (API, scripted)
```
# prerequisites: Liara wallet balance > 0 (min credit 20,000 Toman), secrets files present
deploy/liara_setup.sh app     # POST /v1/projects
deploy/liara_setup.sh disk    # POST /v1/projects/<app>/disks  {name:data,size:2}
deploy/liara_setup.sh envs    # POST /v1/projects/update-envs
deploy/liara_setup.sh data    # POST /v1/projects/<app>/disks/data/ftp  + curl FTP upload of 3 files
deploy/liara_setup.sh deploy  # POST /v2/projects/<app>/sources (tar.gz) + POST /v2/projects/<app>/releases (disk mount /data)
deploy/liara_setup.sh check   # GET https://<app>.liara.run/app/?token=...  -> 200
```
Or with the CLI: `npm i -g @liara/cli && liara login && liara deploy` (uses `liara.json`; set the app name there).

## Using the app
`https://<app>.liara.run/app/?token=<PLAYGROUND_TOKEN>` (every endpoint requires `?token=`; without it -> 403).

## Security notes
- No secrets are in the repo; all come from env vars. `.env*` (except `.env.example`) is git-ignored.
- uvicorn access logs include the query string, i.e. the `?token=`; rotate `PLAYGROUND_TOKEN` after the demo.
- Delete the FTP access on the disk after uploading the data.

## Local run
```
cd backend && pip install -r requirements.txt
DATA_DIR=/path/to/data TOROB_DB_PATH=/path/to/torob.sqlite PORT=8799 HOST=127.0.0.1 \
  PLAYGROUND_TOKEN=... BOXAPI_API_KEY=... AVALAI_API_KEY=... ./start.sh
```
