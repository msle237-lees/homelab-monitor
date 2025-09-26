#!/usr/bin/env bash
# Smoke test for Homelab Machines API (single table: machines)

set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$ROOT_DIR"

PORT="${PORT:-8000}"
BASE="http://127.0.0.1:${PORT}"

LOGFILE="${ROOT_DIR}/smoke_uvicorn.log"
PIDFILE="${ROOT_DIR}/.smoke_server.pid"

: "${DB_PATH:=auv_database.db}"
if [[ "${FRESH_DB:-1}" == "1" && -f "$DB_PATH" ]]; then
  rm -f "$DB_PATH"
fi

cleanup() {
  if [[ -f "$PIDFILE" ]]; then
    kill "$(cat "$PIDFILE")" 2>/dev/null || true
    rm -f "$PIDFILE"
  fi
}
trap cleanup EXIT

python -m uvicorn run:app --host 127.0.0.1 --port "$PORT" --workers 1 >"$LOGFILE" 2>&1 &
echo $! > "$PIDFILE"

echo "Waiting for API to come up on ${BASE} ..."
for i in {1..60}; do
  if curl -fsS "${BASE}/" >/dev/null; then
    echo "API is up."
    break
  fi
  sleep 0.25
  if [[ $i -eq 60 ]]; then
    echo "ERROR: API did not become ready. Last 50 log lines:"
    tail -n 50 "$LOGFILE" || true
    exit 1
  fi
done

# 1) Root check
ROOT_JSON="$(curl -fsS "${BASE}/")"
echo "$ROOT_JSON" | grep -q '"ok": *true' || { echo "Root response missing ok=true"; exit 1; }

# 2) Create/Upsert a machine
CREATE_JSON="$(
  curl -fsS -X POST "${BASE}/machines" \
    -F MACHINE_ID="host-001" \
    -F MACHINE_NAME="NAS-01" \
    -F CPU_CORES="16" \
    -F RAM_USED="$((8 * 1024 * 1024 * 1024))" \
    -F RAM_TOTAL="$((32 * 1024 * 1024 * 1024))" \
    -F STORAGE_USED="$((2 * 1024 * 1024 * 1024 * 1024))" \
    -F STORAGE_TOTAL="$((8 * 1024 * 1024 * 1024 * 1024))" \
    -F CPU_TEMPS="52.5" \
    -F NETWORK_USAGE="$((12500000))"
)"
echo "Create: $CREATE_JSON"
echo "$CREATE_JSON" | grep -q '"MACHINE_ID":[[:space:]]*"host-001"' || { echo "Create failed"; exit 1; }

# 3) List
LIST_JSON="$(curl -fsS "${BASE}/machines?limit=5")"
echo "List: $LIST_JSON"
echo "$LIST_JSON" | grep -q '"items":' || { echo "List failed"; exit 1; }

# 4) Get single
GET_JSON="$(curl -fsS "${BASE}/machines/host-001")"
echo "Get: $GET_JSON"
echo "$GET_JSON" | grep -q '"MACHINE_NAME":[[:space:]]*"NAS-01"' || { echo "Get failed"; exit 1; }

# 5) Update subset
UPDATE_JSON="$(
  curl -fsS -X PUT "${BASE}/machines/host-001" \
    -F MACHINE_NAME="NAS-01A" \
    -F CPU_TEMPS="55.0"
)"
echo "Update: $UPDATE_JSON"
echo "$UPDATE_JSON" | grep -q '"MACHINE_NAME":[[:space:]]*"NAS-01A"' || { echo "Update failed"; exit 1; }

# 6) Delete
HTTP_CODE="$(curl -s -o /dev/null -w "%{http_code}" -X DELETE "${BASE}/machines/host-001")"
[[ "$HTTP_CODE" == "204" ]] || { echo "Delete failed: $HTTP_CODE"; exit 1; }

# 7) Ensure gone
HTTP_CODE="$(curl -s -o /dev/null -w "%{http_code}" "${BASE}/machines/host-001")"
[[ "$HTTP_CODE" == "404" ]] || { echo "Expected 404 after delete, got $HTTP_CODE"; exit 1; }

echo "SMOKE TEST PASS ✅"
