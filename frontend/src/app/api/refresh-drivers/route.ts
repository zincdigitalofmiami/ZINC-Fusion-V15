import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const MESSAGE = "Manual refresh is unavailable because the legacy Inngest runtime has been removed.";

export async function POST() {
  return NextResponse.json(
    {
      status: "disabled",
      message: MESSAGE,
    },
    { status: 410 },
  );
}

export async function GET() {
  return NextResponse.json({
    available: false,
    method: "POST",
    status: "disabled",
    message: MESSAGE,
  });
}
