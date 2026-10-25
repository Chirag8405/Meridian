import { NextRequest, NextResponse } from "next/server";

// Browser-side proxy for the grounded assistant (the Render API has no CORS,
// see backend/main.py). Forwards the visitor's address as x-client-ip so the
// backend's per-client rate limit sees the visitor, not this server.
const MAX_BODY_CHARS = 4000;
const UNAVAILABLE = "The assistant is unavailable right now. The rest of the dashboard is unaffected.";

export async function POST(request: NextRequest) {
  const base = process.env.RENDER_API_URL;
  if (!base) {
    return NextResponse.json({ detail: UNAVAILABLE }, { status: 503 });
  }
  const declared = Number(request.headers.get("content-length") ?? "0");
  if (!Number.isFinite(declared) || declared > MAX_BODY_CHARS * 4) {
    return NextResponse.json({ detail: "Request too large." }, { status: 413 });
  }
  const body = await request.text();
  if (body.length > MAX_BODY_CHARS) {
    return NextResponse.json({ detail: "Request too large." }, { status: 413 });
  }
  const clientIp = request.headers.get("x-forwarded-for")?.split(",")[0]?.trim();
  try {
    const res = await fetch(`${base}/api/assistant/chat`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        ...(clientIp ? { "x-client-ip": clientIp } : {}),
        ...(process.env.ASSISTANT_PROXY_SECRET ? { "x-proxy-secret": process.env.ASSISTANT_PROXY_SECRET } : {}),
      },
      body,
      cache: "no-store",
      signal: AbortSignal.timeout(35_000),
    });
    const headers: Record<string, string> = { "content-type": "application/json" };
    const retryAfter = res.headers.get("retry-after");
    if (retryAfter) headers["retry-after"] = retryAfter;
    return new NextResponse(await res.text(), { status: res.status, headers });
  } catch {
    // Render asleep, restarting or unreachable: degrade to the same message as a 503.
    return NextResponse.json({ detail: UNAVAILABLE }, { status: 503 });
  }
}
