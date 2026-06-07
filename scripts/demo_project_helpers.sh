#!/usr/bin/env bash
# Shared helpers for demo scripts — save/restore active project across demo runs.
set -euo pipefail

SAVED_ACTIVE_PROJECT_ROOT=""

demo_save_active_project() {
  SAVED_ACTIVE_PROJECT_ROOT=""
  if [[ -z "${TOKEN:-}" ]]; then
    return 0
  fi
  local tmp http
  tmp="$(mktemp "${TMPDIR:-/tmp}/nova-demo-save-proj.XXXXXX")"
  if ! http="$(curl -sS --connect-timeout 3 --max-time 15 -w "%{http_code}" -o "$tmp" \
    -H "Authorization: Bearer $TOKEN" \
    "${NOVA_API_URL:-http://localhost:8000}/api/v1/projects/active")"; then
    rm -f "$tmp"
    return 0
  fi
  if [[ "$http" -ge 400 ]]; then
    rm -f "$tmp"
    return 0
  fi
  SAVED_ACTIVE_PROJECT_ROOT="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1])).get('project_root',''))" "$tmp" 2>/dev/null || true)"
  rm -f "$tmp"
}

demo_restore_active_project() {
  if [[ -z "${TOKEN:-}" || -z "$SAVED_ACTIVE_PROJECT_ROOT" ]]; then
    return 0
  fi
  curl -sS --connect-timeout 3 --max-time 15 -X POST \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"project_root\":\"$SAVED_ACTIVE_PROJECT_ROOT\"}" \
    "${NOVA_API_URL:-http://localhost:8000}/api/v1/projects/active" >/dev/null 2>&1 || true
}
