# heocr-review

A private Cloudflare Pages + D1 review mini-site for the hocrgen pipeline. It is operator tooling, not part of the public pipeline: a single reviewer (`shaypal5@gmail.com`) signs in through Cloudflare Access, makes approve/reject/defer decisions on items emitted by `hocrgen` into a `review_queue.json`, and exports those decisions back into `review_data/manual_decisions/` so the next `hocrgen build-release` can consume them.

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
10. Verify the gate is active:

    ```sh
    curl -I https://heocr-review.pages.dev/
    ```

    The response must be a Cloudflare Access challenge (302/HTML), not `200 OK`. If you see `200 OK`, Access is not yet enforcing — fix the policy before treating the app as private.

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
- The `database_id` in `wrangler.toml` is not a secret and may be committed once it is set.
- The mini-site has no append-only audit log on its own. The export step is the durable record: decisions are not "final" until they land in `review_data/manual_decisions/` on a git-tracked branch.
