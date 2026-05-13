#!/usr/bin/env bash
set -euo pipefail
TOKEN_FILE="${HEOCR_CF_TOKEN_FILE:-$HOME/.config/heocr/cloudflare_api_token.env}"
if [[ -f "$TOKEN_FILE" ]]; then
  # shellcheck source=/dev/null
  source "$TOKEN_FILE"
fi

npx wrangler d1 execute heocr-review-db --remote --command \
  "SELECT 'batches' AS tbl, COUNT(*) AS n FROM review_batches
   UNION ALL SELECT 'items', COUNT(*) FROM review_items
   UNION ALL SELECT 'decisions', COUNT(*) FROM review_decisions
   UNION ALL SELECT 'active_batch', COUNT(*) FROM review_batches WHERE status='active';"
