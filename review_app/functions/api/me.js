export async function onRequestGet(context) {
  const email = context.request.headers.get("Cf-Access-Authenticated-User-Email") ?? "dev@local";
  return Response.json({ email });
}
