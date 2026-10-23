#!/bin/bash
# Push data files to the app's /data disk through backend/data_loader.py (runs only while the DB is missing).
# usage: deploy/upload_data.sh [BASE_URL]   (token read from APP_ENV, never printed)
set -euo pipefail
set -a; . "${APP_ENV:-/workspace/torob/secrets/.env_liara_app}"; set +a
BASE="${1:-https://${LIARA_APP_NAME}.liara.run}"; SRC="${DATA_SRC:-/workspace/torob/deploy/data}"; CH=$((${CHUNK_MB:-20}*1024*1024))
for f in product_emb_ids.json product_emb.f16.npy torob.sqlite.gz; do
  size=$(stat -c %s "$SRC/$f"); off=0; echo "[upload] $f ($size B)"
  while [ $off -lt $size ]; do
    for try in 1 2 3 4 5; do
      r=$(dd if="$SRC/$f" bs=1M skip=$((off/1048576)) count=$((CH/1048576)) status=none | \
          curl -sS -m 300 -X PUT --data-binary @- -H 'Content-Type: application/octet-stream' \
          "$BASE/__upload/$f?token=$PLAYGROUND_TOKEN&offset=$off" -w ' %{http_code}' || echo ' 000')
      code=${r##* }; body=${r% *}
      if [ "$code" = 200 ] || [ "$code" = 409 ]; then off=$(python3 -c "import json,sys;print(json.loads(sys.argv[1])['have'])" "$body"); break; fi
      echo "  retry $try (HTTP $code)"; sleep 3
    done
    printf '  %s/%s\n' "$off" "$size"
  done
done
curl -sS -m 600 -X POST "$BASE/__done?token=$PLAYGROUND_TOKEN"; echo
