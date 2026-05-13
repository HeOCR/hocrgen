CREATE TABLE review_batches (
    batch_id    TEXT PRIMARY KEY,
    batch_label TEXT,
    seeded_at   TEXT NOT NULL,
    item_count  INTEGER NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending'
);

CREATE TABLE review_items (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id           TEXT NOT NULL REFERENCES review_batches(batch_id),
    review_item_id     TEXT NOT NULL UNIQUE,
    item_id            TEXT NOT NULL,
    source_id          TEXT NOT NULL,
    canonical_item_id  TEXT NOT NULL,
    title              TEXT,
    source_url         TEXT,
    review_reasons     TEXT NOT NULL,
    suggested_decision TEXT NOT NULL,
    privacy_flag       TEXT NOT NULL,
    preview_b64        TEXT,
    full_image_b64     TEXT,
    raw_record         TEXT NOT NULL
);

CREATE TABLE review_decisions (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    review_item_id TEXT NOT NULL,
    item_id        TEXT NOT NULL,
    batch_id       TEXT NOT NULL,
    reviewer_email TEXT NOT NULL,
    decision       TEXT NOT NULL,
    rationale      TEXT NOT NULL,
    notes          TEXT,
    decided_at     TEXT NOT NULL,
    UNIQUE(review_item_id, reviewer_email)
);

CREATE TABLE pipeline_stats (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
