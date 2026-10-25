import { NextRequest, NextResponse } from "next/server";

// Browser-side proxy: the Render API has no CORS (see backend/main.py), so the
// live-refreshing Recent activity component reads it through this route.
export async function GET(request: NextRequest) {
  const base = process.env.RENDER_API_URL;
  if (!base) {
    return NextResponse.json({ detail: "RENDER_API_URL is not set" }, { status: 500 });
  }
  const res = await fetch(`${base}/api/recent-swap-activity?${request.nextUrl.searchParams}`, {
    cache: "no-store",
  });
  return new NextResponse(await res.text(), {
    status: res.status,
    headers: { "content-type": "application/json" },
  });
}
