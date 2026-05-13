export async function onRequestGet(context) {
  const row = await context.env.DB
    .prepare(
      "SELECT batch_id, batch_label, seeded_at, item_count, status FROM review_batches WHERE status = 'active' LIMIT 1"
    )
    .first();
  return Response.json(row ?? null);
}
