import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

export async function GET() {
  return NextResponse.json(
    {
      error: "Quant overview is decommissioned",
    },
    { status: 410 },
  );
}
