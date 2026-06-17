#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERIFY_SCOPE=local exec "$SCRIPT_DIR/verify_integrations.sh" "$@"
