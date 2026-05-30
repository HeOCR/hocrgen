# heocr-review

A private Cloudflare Pages + D1 review mini-site for the hocrgen pipeline. It is operator tooling, not part of the public pipeline: a single reviewer (`shaypal5@gmail.com`) signs in through Cloudflare Access, makes approve/reject/defer decisions on items emitted by `hocrgen` into a `review_queue.json`, and exports those decisions back into `review_data/manual_decisions/` so the next `hocrgen build-release` can consume them.

Created by [Shay Palachy Affek ](http://www.shaypalachy.com/).

This directory is intentionally not under `src/`. It contains no Python code, no tests, and no roadmap milestone notation.

## Stack

- Cloudflare Pages (static `public/` hosting)
- Cloudflare Pages Functions (`functions/` directory, API routes)
- Cloudflare D1 (SQLite-backed database, binding name `DB`)
- Cloudflare Access (gates the site to one operator email)
- Node.js ESM scripts (`*.mjs`) using `sharp` for image resizing
- Vanilla HTML/CSS/JS — no framework, no bundler

## First-time setup

1. Create a Cloudflare account at <https://cloudflare.com> using the operator email `shaypal5@gmail.com`.
2. Enable Cloudflare Zero Trust on that account (the free plan is sufficient).
3. Create an API token under **My Profile → API Tokens** with these permissions:
   - **D1 — Edit**
   - **Cloudflare Pages — Edit**
   - **Account Settings — Read**

   Save the token outside the repo at `~/.config/heocr/cloudflare_api_token.env` with these contents (no quotes, no trailing whitespace):

   ```sh
   export CLOUDFLARE_ACCOUNT_ID=<your-account-id>
   export CLOUDFLARE_API_TOKEN=<your-token>
   ```

4. From the repo root, install dependencies:

   ```sh
   cd review_app && npm install
   ```

5. Source the token file in every new shell that runs deploy or seed/export scripts:

   ```sh
   source ~/.config/heocr/cloudflare_api_token.env
   ```

6. Create the D1 database and copy the returned `database_id` into `wrangler.toml`:

   ```sh
   npx wrangler d1 create heocr-review-db
   ```

7. Apply the initial migration to the remote database:

   ```sh
   npx wrangler d1 migrations apply heocr-review-db --remote
   ```

8. Deploy the Pages project. The first run creates the project on the Cloudflare side:

   ```sh
   bash scripts/deploy.sh
   ```

9. In the Cloudflare dashboard, go to **Workers & Pages → heocr-review → Settings → Cloudflare Access** and enable Access. Create an Access application for `heocr-review.pages.dev` and add a policy named "Allow shaypal5@gmail.com" with email OTP (no SSO required). Repeat the policy for any branch-preview hostnames Cloudflare generates if you intend to expose them.
10. In the same dashboard, under **Settings → Environment variables**, add `ALLOWED_REVIEWER_EMAILS=shaypal5@gmail.com` (comma-separated; the middleware refuses any other email as defense in depth against an over-broad Access policy).
11. Verify the gate is active:

    ```sh
    curl -I https://heocr-review.pages.dev/
    ```

    The response must be a Cloudflare Access challenge (302/HTML), not `200 OK`. If you see `200 OK`, Access is not yet enforcing — fix the policy before treating the app as private.

## Local development

Cloudflare provides `wrangler pages dev` for running the site locally without going through Access:

```sh
cd review_app
HEOCR_REVIEW_DEV_BYPASS=true npx wrangler pages dev public
```

`HEOCR_REVIEW_DEV_BYPASS=true` skips the middleware's Access checks. Use it **only** for local development — never set it in the Pages dashboard.

For a more realistic local round-trip you can also seed a local D1 database with `npx wrangler d1 migrations apply heocr-review-db --local` and run the seed/export scripts against `--local` (this requires editing the scripts to add a `--local` flag — out of scope for v0).

## Operator runbook

### Seeding a review batch

```sh
hocrgen build-release --profile profile_open_v1          # if not already run
hocrgen export-review-queue --output /tmp/heocr_queue.json
source ~/.config/heocr/cloudflare_api_token.env
node review_app/scripts/seed_batch.mjs \
  --queue-file /tmp/heocr_queue.json \
  --run-dir .work/<run_id> \
  --batch-label "YYYY-MM-DD review" \
  --dataset-version alpha-v0 \
  --milestone "F6 — partial" \
  --active-blockers 4 \
  --benchmark-coverage "1 / 3"
bash review_app/scripts/deploy.sh
# Visit https://heocr-review.pages.dev/ — the "Start Review" button is now active.
```

`seed_batch.mjs` resizes each preview asset to a `<= 300px` JPEG thumbnail and a `<= 1600px` full-resolution JPEG, base64-encodes both, and inserts one row per item into D1. If a referenced preview path does not exist on disk the row is still inserted but with `preview_b64` and `full_image_b64` set to `NULL`. Any previously active batch is closed before the new batch is marked `active`.

### Exporting decisions after reviewing

```sh
source ~/.config/heocr/cloudflare_api_token.env
node review_app/scripts/export_decisions.mjs --batch-id <batch_id>
# → writes review_data/manual_decisions/<review_item_id>.json
# → run hocrgen build-release again to apply decisions
```

Each emitted JSON matches the `ReviewDecisionRecord` shape in `src/hocrgen/manifests/models.py`. Items with no decision yet are skipped (and printed in the summary).

### Spot-checking the database

```sh
bash review_app/scripts/check_d1.sh
```

This prints row counts for `review_batches`, `review_items`, `review_decisions`, and the active-batch count.

## Security notes

- Never commit `~/.config/heocr/cloudflare_api_token.env`. It is intentionally outside the repo.
- Never commit anything written to `review_exports/` — that directory is `.gitignore`d.
- Verify Cloudflare Access protects every hostname Cloudflare assigns (stable, branch, PR preview) before treating the app as private. A fresh deploy is unprotected until the Access application policy is in place.
- The middleware enforces two layers on top of Access: a presence check on `Cf-Access-Jwt-Assertion` (rejects requests that did not traverse Access), and an `ALLOWED_REVIEWER_EMAILS` allowlist (rejects emails that Access lets through but should not be reviewers). Full JWKS-backed JWT signature verification is a known follow-up.
- The `database_id` in `wrangler.toml` is not a secret and may be committed once it is set.
- The mini-site has no append-only audit log on its own. The export step is the durable record: decisions are not "final" until they land in `review_data/manual_decisions/` on a git-tracked branch.

## Known limitations (v0)

These are deliberate v0 trade-offs, called out so they don't surprise the next person who touches this code.

- **Image storage is base64-in-D1, not R2.** Each preview and full-resolution JPEG is base64-encoded into a TEXT column. This wastes ~33% storage and forces a base64 decode in the Worker on every image fetch. The right fix is to migrate binary assets to R2 and store only metadata in D1; this is a follow-up, not a v0 blocker. The `/api/image` endpoint sets aggressive `Cache-Control` so the per-request decode cost is paid once per browser per image.
- **Seed atomicity is per-statement-file.** Batch metadata (close-old, insert-new, stats) all land in a single `wrangler d1 execute --file`, which is atomic on D1's side. Per-item INSERTs run as separate `--file` invocations because base64 blobs can push the combined SQL past D1's 5 MB per-file limit. If a per-item INSERT fails mid-batch, the partial batch stays `active` and the operator must clean up manually before re-seeding.
- **`pipeline_stats` is a generic key-value table.** It is acceptable for one-screen dashboard rendering and is intentionally not schematized.
- **`review_items.raw_record` is stored but never served.** It is reserved for a future per-item detail view; the items list endpoint deliberately omits it.
- **SQL is built with manual single-quote escaping** in the seed and export scripts. Wrangler's CLI does not expose bound parameters for `--file`. Operator input is trusted; the D1 HTTP API would be the right place to introduce parameterized statements.

## Credits

Created by [Shay Palachy Affek ](http://www.shaypalachy.com/) [GitHub](https://github.com/shaypal5)
