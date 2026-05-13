const VALID_DECISIONS = new Set([
  "approve",
  "reject",
  "defer",
  "needs_legal_review",
  "needs_privacy_review",
]);

export async function onRequestPost(context) {
  const reviewer = context.request.headers.get("Cf-Access-Authenticated-User-Email") ?? "dev@local";
  const contentType = context.request.headers.get("Content-Type") ?? "";
  if (!contentType.toLowerCase().startsWith("application/json")) {
    return new Response("Content-Type must be application/json", { status: 415 });
  }

  let body;
  try {
    body = await context.request.json();
  } catch (_) {
    return new Response("invalid JSON body", { status: 400 });
  }

  const { review_item_id, batch_id, decision, rationale, notes } = body ?? {};
  if (!review_item_id || !batch_id || !decision || !rationale) {
    return new Response("review_item_id, batch_id, decision, and rationale are required", { status: 400 });
  }
  if (!VALID_DECISIONS.has(decision)) {
    return new Response(`invalid decision: ${decision}`, { status: 400 });
  }

  const itemRow = await context.env.DB
    .prepare("SELECT item_id FROM review_items WHERE review_item_id = ? AND batch_id = ?")
    .bind(review_item_id, batch_id)
    .first();
  if (!itemRow) {
    return new Response("unknown review_item_id for this batch", { status: 404 });
  }

  const decidedAt = new Date().toISOString();
  await context.env.DB
    .prepare(
      `INSERT INTO review_decisions
         (review_item_id, item_id, batch_id, reviewer_email, decision, rationale, notes, decided_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?)
       ON CONFLICT(review_item_id, batch_id, reviewer_email) DO UPDATE SET
         decision = excluded.decision,
         rationale = excluded.rationale,
         notes = excluded.notes,
         decided_at = excluded.decided_at`
    )
    .bind(
      review_item_id,
      itemRow.item_id,
      batch_id,
      reviewer,
      decision,
      rationale,
      notes ?? null,
      decidedAt,
    )
    .run();

  return Response.json({ ok: true, decided_at: decidedAt });
}
