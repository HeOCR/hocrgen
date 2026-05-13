// Serve preview or full-resolution JPEGs for a review item. Both kinds are
// stored as base64 in D1 (a known v0 limitation; see review_app/README.md
// "Storage limitations"). The Worker decodes on every request, so aggressive
// caching is important — once an image has been served once, the browser
// should not re-fetch it on subsequent loads.

export async function onRequestGet(context) {
  const url = new URL(context.request.url);
  const id = url.searchParams.get("id");
  const kind = url.searchParams.get("kind") === "preview" ? "preview" : "full";
  if (!id) {
    return new Response("missing id", { status: 400 });
  }

  const column = kind === "preview" ? "preview_b64" : "full_image_b64";
  const row = await context.env.DB
    .prepare(`SELECT ${column} AS data FROM review_items WHERE review_item_id = ?`)
    .bind(id)
    .first();

  if (!row || !row.data) {
    return new Response("not found", { status: 404 });
  }

  const binary = Uint8Array.from(atob(row.data), (c) => c.charCodeAt(0));
  return new Response(binary, {
    headers: {
      "Content-Type": "image/jpeg",
      // review_item_id + kind is stable per batch, so we can cache aggressively.
      "Cache-Control": "private, max-age=86400, immutable",
    },
  });
}
