export async function onRequestGet(context) {
  const url = new URL(context.request.url);
  const batchId = url.searchParams.get("batch_id");
  if (!batchId) {
    return new Response("missing batch_id", { status: 400 });
  }
  const reviewer = context.request.headers.get("Cf-Access-Authenticated-User-Email") ?? "dev@local";
  const db = context.env.DB;

  const itemsResult = await db
    .prepare(
      `SELECT review_item_id, item_id, source_id, canonical_item_id, title, source_url,
              review_reasons, suggested_decision, privacy_flag,
              preview_b64
       FROM review_items
       WHERE batch_id = ?
       ORDER BY id ASC`
    )
    .bind(batchId)
    .all();

  const decisionsResult = await db
    .prepare(
      `SELECT review_item_id, decision, rationale, notes, decided_at
       FROM review_decisions
       WHERE batch_id = ? AND reviewer_email = ?`
    )
    .bind(batchId, reviewer)
    .all();
  const decisionByItem = new Map();
  for (const row of decisionsResult.results ?? []) {
    decisionByItem.set(row.review_item_id, row);
  }

  const items = (itemsResult.results ?? []).map((row) => {
    let reasons = [];
    try {
      reasons = JSON.parse(row.review_reasons);
    } catch (_) {
      reasons = [];
    }
    const decision = decisionByItem.get(row.review_item_id) ?? null;
    return {
      review_item_id: row.review_item_id,
      item_id: row.item_id,
      source_id: row.source_id,
      canonical_item_id: row.canonical_item_id,
      title: row.title,
      source_url: row.source_url,
      review_reasons: reasons,
      suggested_decision: row.suggested_decision,
      privacy_flag: row.privacy_flag,
      preview_b64: row.preview_b64,
      decided: decision !== null,
      decision: decision
        ? {
            decision: decision.decision,
            rationale: decision.rationale,
            notes: decision.notes,
            decided_at: decision.decided_at,
          }
        : null,
    };
  });

  return Response.json({ batch_id: batchId, items });
}
