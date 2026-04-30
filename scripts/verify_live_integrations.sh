#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERIFY_SCOPE=live exec "$SCRIPT_DIR/verify_integrations.sh" "$@"
