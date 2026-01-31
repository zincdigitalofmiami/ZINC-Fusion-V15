import { NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'

// FastAPI backend URL - use env var or default to local
const FUSION_API_URL = process.env.FUSION_API_URL || 'http://localhost:8000'

export async function GET() {
  try {
    const response = await fetch(`${FUSION_API_URL}/api/market-drivers`, {
      headers: {
        'Content-Type': 'application/json',
      },
      // 30 second timeout
      signal: AbortSignal.timeout(30000),
    })

    if (!response.ok) {
      throw new Error(`FastAPI returned ${response.status}`)
    }

    const data = await response.json()
    return NextResponse.json(data)
  } catch (error) {
    console.error('Market drivers fetch failed:', error)
    return NextResponse.json(
      { error: 'Market drivers fetch failed' },
      { status: 500 }
    )
  }
}
