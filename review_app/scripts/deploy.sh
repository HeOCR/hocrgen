#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REVIEW_APP_DIR="$(dirname "$SCRIPT_DIR")"

TOKEN_FILE="${HEOCR_CF_TOKEN_FILE:-$HOME/.config/heocr/cloudflare_api_token.env}"
if [[ -f "$TOKEN_FILE" ]]; then
  # shellcheck source=/dev/null
  source "$TOKEN_FILE"
fi

cd "$REVIEW_APP_DIR"
npx wrangler pages deploy public \
  --project-name heocr-review \
  --branch main \
  --commit-dirty=true \
  --skip-caching

echo ""
echo "Deployed. Stable URL: https://heocr-review.pages.dev/"
echo "Verify Access is protecting it: curl -I https://heocr-review.pages.dev/"
