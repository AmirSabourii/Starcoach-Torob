#!/bin/bash
# One-shot Liara setup + deploy via the Liara REST API (https://openapi.liara.ir/paas.yaml).
# Secrets are read from env files and NEVER echoed.
#   LIARA_ENV   (default /workspace/torob/secrets/.env_liara)      -> LIARA_API_TOKEN
#   APP_ENV     (default /workspace/torob/secrets/.env_liara_app)  -> LIARA_APP_NAME, PLAYGROUND_TOKEN, BOXAPI_API_KEY
#   AVALAI_ENV  (default /workspace/torob/eval/.env_avalai)        -> AVALAI_API_KEY
#   DATA_SRC    (default /workspace/torob/deploy/data)              -> torob.sqlite.gz, product_emb.f16.npy, product_emb_ids.json
# Steps: create app -> create disk -> set envs -> FTP upload data -> source deploy -> release -> check /app/
# Usage: deploy/liara_setup.sh [all|app|disk|envs|data|deploy|check]
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
set -a
. "${LIARA_ENV:-/workspace/torob/secrets/.env_liara}"
. "${APP_ENV:-/workspace/torob/secrets/.env_liara_app}"
. "${AVALAI_ENV:-/workspace/torob/eval/.env_avalai}"
set +a
API=https://api.iran.liara.ir
APP="${LIARA_APP_NAME:-torob-assistant-hk26}"
PLAN="${LIARA_PLAN:-small-g2}"; BUNDLE="${LIARA_BUNDLE:-basic}"
NETWORK_ID="${LIARA_NETWORK_ID:-}"          # g2 plans need a private network id (GET /v1/networks)
DISK=data; DISK_SIZE="${DISK_SIZE:-2}"     # GB
DATA_SRC="${DATA_SRC:-/workspace/torob/deploy/data}"
api() { local m=$1 p=$2; shift 2; curl -sS -m 900 -X "$m" -H "Authorization: Bearer $LIARA_API_TOKEN" "$API$p" "$@"; }
step=${1:-all}

if [[ $step == all || $step == app ]]; then
  [ -n "$NETWORK_ID" ] || NETWORK_ID=$(api GET /v1/networks | python3 -c "import json,sys;n=json.load(sys.stdin).get('networks',[]);print(n[0]['_id'] if n else '')")
  echo "[app] create $APP plan=$PLAN bundle=$BUNDLE"
  api POST /v1/projects -H 'Content-Type: application/json' \
    -d "{\"name\":\"$APP\",\"planID\":\"$PLAN\",\"bundlePlanID\":\"$BUNDLE\",\"platform\":\"docker\",\"network\":\"$NETWORK_ID\",\"readOnlyRootFilesystem\":false}" -w ' HTTP %{http_code}\n'
fi
if [[ $step == all || $step == disk ]]; then
  echo "[disk] create $DISK ${DISK_SIZE}G"
  api POST "/v1/projects/$APP/disks" -H 'Content-Type: application/json' -d "{\"name\":\"$DISK\",\"size\":\"$DISK_SIZE\"}" -w ' HTTP %{http_code}\n'
fi
if [[ $step == all || $step == envs ]]; then
  echo "[envs] set (values hidden)"
  python3 - "$APP" > /tmp/liara_envs.json <<'PY'
import json, os, sys
keys = {'BOXAPI_API_KEY': os.environ['BOXAPI_API_KEY'], 'AVALAI_API_KEY': os.environ['AVALAI_API_KEY'],
        'PLAYGROUND_TOKEN': os.environ['PLAYGROUND_TOKEN'], 'PLAYGROUND_SPEND_CAP': '0.50',
        'DATA_DIR': '/data', 'TOROB_DB_PATH': '/data/torob.sqlite', 'PORT': '8000',
        'TRYON_MODEL': os.environ.get('TRYON_MODEL', 'gemini-2.5-flash-image'), 'TRYON_API': 'native',
        'TRYON_CAP_USD': '2.0', 'TRYON_PER_SESSION': '3', 'MALLGUIDE_CAP_USD': '0.10'}
for k in ('AVALAI_BASE_URL', 'AVALAI_NATIVE_URL'):
    if os.environ.get(k): keys[k] = os.environ[k]
print(json.dumps({'project': sys.argv[1], 'variables': [{'key': k, 'value': v} for k, v in keys.items()]}))
PY
  chmod 600 /tmp/liara_envs.json
  api POST /v1/projects/update-envs -H 'Content-Type: application/json' --data @/tmp/liara_envs.json -o /dev/null -w ' HTTP %{http_code}\n'
  rm -f /tmp/liara_envs.json
fi
if [[ $step == all || $step == data ]]; then
  echo "[data] create FTP access on disk and upload DB (.gz) + embeddings"
  api POST "/v1/projects/$APP/disks/$DISK/ftp" -H 'Content-Type: application/json' -d '{"username":"torobftp","readOnly":false}' -o /tmp/liara_ftp.json -w ' HTTP %{http_code}\n'
  chmod 600 /tmp/liara_ftp.json
  read -r FUSER FPASS FHOST < <(python3 -c "import json;d=json.load(open('/tmp/liara_ftp.json'));print(d['username'],d['password'],d['host'])")
  for f in torob.sqlite.gz product_emb.f16.npy product_emb_ids.json; do
    echo "  upload $f"; curl -sS --ftp-pasv -T "$DATA_SRC/$f" --user "$FUSER:$FPASS" "ftp://$FHOST/$f" -w '  ok %{http_code} %{size_upload}B\n'
  done
  rm -f /tmp/liara_ftp.json   # (delete FTP access afterwards in console: Disks -> FTP)
  # start.sh gunzips /data/torob.sqlite.gz -> /data/torob.sqlite on first boot
fi
if [[ $step == all || $step == deploy ]]; then
  TAR=/tmp/torob_src.tar.gz
  tar --exclude='./frontend/node_modules' --exclude='./frontend/dist' --exclude='*.sqlite*' --exclude='*.npy' --exclude='.env' --exclude='__pycache__' -czf "$TAR" -C "$HERE" .
  echo "[deploy] upload source $(du -h $TAR | cut -f1)"
  SID=$(api POST "/v2/projects/$APP/sources" -F "file=@$TAR" | python3 -c "import json,sys;d=json.load(sys.stdin);print(d.get('sourceID') or d)")
  echo "  sourceID=$SID"
  api POST "/v2/projects/$APP/releases" -H 'Content-Type: application/json' \
    -d "{\"sourceID\":\"$SID\",\"port\":8000,\"type\":\"docker\",\"disks\":[{\"name\":\"$DISK\",\"mountTo\":\"/data\"}],\"message\":\"hackathon snapshot\"}" -w ' HTTP %{http_code}\n'
  echo "  follow build: GET /v1/projects/$APP/releases ; logs: GET /v1/projects/$APP/logs"
fi
if [[ $step == all || $step == check ]]; then
  URL="https://$APP.liara.run"
  echo "[check] $URL/app/?token=*** -> $(curl -s -o /dev/null -m 30 -w '%{http_code}' "$URL/app/?token=$PLAYGROUND_TOKEN")"
fi
