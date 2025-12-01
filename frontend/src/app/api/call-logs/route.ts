import { NextRequest, NextResponse } from "next/server";

import { API_BASE_URL } from "@/lib/config";

export async function GET(request: NextRequest) {
  const limit = request.nextUrl.searchParams.get("limit") ?? "20";
  try {
    const upstream = await fetch(
      `${API_BASE_URL}/api/call-logs?limit=${limit}`,
      {
        method: "GET",
        cache: "no-store",
      },
    );
    const payload = await upstream.text();
    const headers = upstream.headers.get("content-type") ?? "application/json";
    return new NextResponse(payload, {
      status: upstream.status,
      headers: {
        "content-type": headers,
      },
    });
  } catch (error) {
    return NextResponse.json(
      {
        detail:
          error instanceof Error ? error.message : "Failed to load call logs.",
      },
      { status: 500 },
    );
  }
}

