#!/usr/bin/env bash
# Print bootstrap admin token for development pairing
set -euo pipefail
echo "Bootstrap admin token (set NOVA_BOOTSTRAP_ADMIN_ENABLED=true):"
grep NOVA_BOOTSTRAP_ADMIN_TOKEN .env.example | cut -d= -f2
