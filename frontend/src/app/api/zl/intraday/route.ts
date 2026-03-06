import { NextResponse } from 'next/server'

export async function GET() {
  return NextResponse.json(
    {
      error: 'This endpoint has been deprecated',
      replacement: '/api/zl/price-1d',
      detail: 'Use /api/zl/price-1d for the daily chart and /api/zl/live for the current price.',
    },
    {
      status: 410,
      headers: { 'Cache-Control': 'no-store, max-age=0' },
    },
  )
}
