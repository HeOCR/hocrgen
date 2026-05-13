// Authentication gate for the heocr-review mini-site.
//
// Cloudflare Access is the primary gate: it injects the
// Cf-Access-Authenticated-User-Email and Cf-Access-Jwt-Assertion headers
// when a request has been authenticated against the Access application.
//
// We layer two extra defenses on top:
//   1. Reject requests that are missing Cf-Access-Jwt-Assertion entirely.
//      A request without it never traversed Access (a custom hostname or
//      Worker route that bypasses Access would not get this header).
//      NOTE: this is a presence check, not a signature verification.
//      Full JWKS-backed JWT verification is a TODO follow-up.
//   2. Reject requests whose email is not in ALLOWED_REVIEWER_EMAILS
//      (comma-separated env binding, set in the Pages project dashboard).
//      This catches over-broad Access policies.
//
// HEOCR_REVIEW_DEV_BYPASS=true skips both checks for `wrangler pages dev`.

export async function onRequest(context) {
  if (context.env.HEOCR_REVIEW_DEV_BYPASS === "true") {
    return context.next();
  }

  const email = context.request.headers.get("Cf-Access-Authenticated-User-Email");
  const assertion = context.request.headers.get("Cf-Access-Jwt-Assertion");
  if (!email || !assertion) {
    return new Response("Unauthorized", { status: 401 });
  }

  const allowedRaw = context.env.ALLOWED_REVIEWER_EMAILS ?? "";
  const allowed = allowedRaw
    .split(",")
    .map((entry) => entry.trim().toLowerCase())
    .filter(Boolean);
  if (allowed.length > 0 && !allowed.includes(email.toLowerCase())) {
    return new Response("Forbidden", { status: 403 });
  }

  return context.next();
}
