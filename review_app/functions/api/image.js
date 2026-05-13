export async function onRequestGet(context) {
  const url = new URL(context.request.url);
  const id = url.searchParams.get("id");
  if (!id) {
    return new Response("missing id", { status: 400 });
  }

  const row = await context.env.DB
    .prepare("SELECT full_image_b64 FROM review_items WHERE review_item_id = ?")
    .bind(id)
    .first();

  if (!row || !row.full_image_b64) {
    return new Response("not found", { status: 404 });
  }

  const binary = Uint8Array.from(atob(row.full_image_b64), (c) => c.charCodeAt(0));
  return new Response(binary, {
    headers: {
      "Content-Type": "image/jpeg",
      "Cache-Control": "private, max-age=3600",
    },
  });
}
