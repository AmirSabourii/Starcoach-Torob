#!/bin/sh
# Container / local entrypoint. All secrets come from environment variables (never files in the image).
# Persistent data lives in $DATA_DIR (Liara disk mounted at /data). The code expects data files next to
# the .py files, so we symlink them from $DATA_DIR into the code dir at boot.
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
DATA_DIR="${DATA_DIR:-/data}"
TOROB_DB_PATH="${TOROB_DB_PATH:-$DATA_DIR/torob.sqlite}"
PORT="${PORT:-8000}"
mkdir -p "$DATA_DIR" 2>/dev/null || true

# 1) first boot: unpack the compressed DB if only the .gz was uploaded to the disk
if [ ! -s "$TOROB_DB_PATH" ] && [ -s "$TOROB_DB_PATH.gz" ]; then
  echo "[start] unpacking $TOROB_DB_PATH.gz ..."
  gunzip -c "$TOROB_DB_PATH.gz" > "$TOROB_DB_PATH.tmp" && mv "$TOROB_DB_PATH.tmp" "$TOROB_DB_PATH"
fi
# optional: download the DB from a (pre-signed) URL on first boot
if [ ! -s "$TOROB_DB_PATH" ] && [ -n "$TOROB_DB_URL" ]; then
  echo "[start] downloading DB from TOROB_DB_URL ..."
  python - <<PY
import os, urllib.request, gzip, shutil
u = os.environ['TOROB_DB_URL']; dst = os.environ.get('TOROB_DB_PATH', '$TOROB_DB_PATH')
tmp = dst + '.dl'
urllib.request.urlretrieve(u, tmp)
if u.split('?')[0].endswith('.gz'):
    with gzip.open(tmp, 'rb') as f, open(dst + '.tmp', 'wb') as o: shutil.copyfileobj(f, o)
    os.replace(dst + '.tmp', dst); os.remove(tmp)
else:
    os.replace(tmp, dst)
PY
fi
# 1b) still no DB: run the bootstrap upload server (data_loader.py) until the data has been pushed, then continue
if [ ! -s "$TOROB_DB_PATH" ]; then
  echo "[start] DB not found at $TOROB_DB_PATH -> starting data_loader on :$PORT (see DEPLOY.md)"
  python "$HERE/data_loader.py" || true
fi

# 2) link data files / writable state from the disk into the code dir
ln -sfn "$TOROB_DB_PATH" "$HERE/torob.sqlite"
for f in product_emb.f16.npy product_emb_ids.json user_lists.sqlite playground_spent.txt; do
  ln -sfn "$DATA_DIR/$f" "$HERE/$f"     # dangling links are fine: sqlite/open() create the target on the disk
done
for d in about_cache about_cache_v2 about_cache_v3 mall_cache mallguide_cache tryon_cache; do
  mkdir -p "$DATA_DIR/cache/$d"; rm -rf "$HERE/$d" 2>/dev/null || true; ln -sfn "$DATA_DIR/cache/$d" "$HERE/$d"
done
export TRYON_OUT="${TRYON_OUT:-$DATA_DIR/cache/tryon_cache}"
export MALLGUIDE_CACHE="${MALLGUIDE_CACHE:-$DATA_DIR/cache/mallguide_cache}"

[ -n "$PLAYGROUND_TOKEN" ] || echo "[start] WARNING: PLAYGROUND_TOKEN not set; a random one is generated and /app/ will be unusable -> set it."
cd "$HERE"
exec ${UVICORN:-uvicorn} playground_app:app --host "${HOST:-0.0.0.0}" --port "$PORT" --proxy-headers
