import { NextRequest, NextResponse } from "next/server";

import { API_BASE_URL } from "@/lib/config";

export async function POST(request: NextRequest) {
  try {
    const formData = await request.formData();
    const upstream = await fetch(`${API_BASE_URL}/api/test/simulate`, {
      method: "POST",
      body: formData,
    });

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
          error instanceof Error ? error.message : "Simulation proxy failed.",
      },
      { status: 500 },
    );
  }
}

