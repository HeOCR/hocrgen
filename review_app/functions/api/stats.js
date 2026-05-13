export async function onRequestGet(context) {
  const db = context.env.DB;

  const statsRows = await db
    .prepare("SELECT key, value, updated_at FROM pipeline_stats")
    .all();
  const stats = {};
  for (const row of statsRows.results ?? []) {
    stats[row.key] = { value: row.value, updated_at: row.updated_at };
  }

  const activeBatch = await db
    .prepare("SELECT batch_id FROM review_batches WHERE status = 'active' LIMIT 1")
    .first();

  let reviewQueueDepth = 0;
  if (activeBatch?.batch_id) {
    const depth = await db
      .prepare(
        `SELECT COUNT(*) AS n FROM review_items ri
         WHERE ri.batch_id = ?
           AND NOT EXISTS (
             SELECT 1 FROM review_decisions rd
             WHERE rd.review_item_id = ri.review_item_id
           )`
      )
      .bind(activeBatch.batch_id)
      .first();
    reviewQueueDepth = depth?.n ?? 0;
  }

  return Response.json({
    stats,
    review_queue_depth: reviewQueueDepth,
    active_batch_id: activeBatch?.batch_id ?? null,
  });
}
