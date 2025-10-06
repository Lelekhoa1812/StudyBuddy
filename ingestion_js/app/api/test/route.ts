import { NextRequest, NextResponse } from 'next/server'

export async function POST(req: NextRequest) {
  return NextResponse.json({ message: 'Test POST endpoint works' })
}

export async function GET(req: NextRequest) {
  return NextResponse.json({ message: 'Test GET endpoint works' })
}
