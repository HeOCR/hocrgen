export async function onRequest(context) {
  const email = context.request.headers.get("Cf-Access-Authenticated-User-Email");
  if (!email && context.env.DEV_BYPASS !== "true") {
    return new Response("Unauthorized", { status: 401 });
  }
  return context.next();
}
