const API_BASE = '/api'

export interface SensorStatus {
  sensors: {
    interior_temp: number | null
    interior_humidity: number | null
    exterior_temp: number | null
    exterior_humidity: number | null
    satellite_battery: number | null
    satellite_pressure: number | null
  }
  stale: Record<string, boolean>
  last_seen: Record<string, string>
  updated_at: string
}

export interface Narrative {
  subject: string
  headline: string
  body: string
  generated_at: string | null
  cached: boolean
  fallback?: boolean
  rate_limited?: boolean
  retry_after?: number
}

export interface Riddle {
  question: string
  date: string
  active: boolean
}

export interface GuessResult {
  correct: boolean | null
  points?: number
  is_first?: boolean
  rank?: number
  message: string
  already_solved?: boolean
}

export interface LeaderboardPlayer {
  display_name: string
  points: number
  wins: number
}

export interface Leaderboard {
  season_start: string
  players: LeaderboardPlayer[]
}

export async function fetchStatus(): Promise<SensorStatus> {
  const res = await fetch(`${API_BASE}/status`)
  if (!res.ok) throw new Error('Failed to fetch status')
  return res.json()
}

export async function fetchNarrative(): Promise<Narrative> {
  const res = await fetch(`${API_BASE}/narrative`)
  if (!res.ok) throw new Error('Failed to fetch narrative')
  return res.json()
}

export async function refreshNarrative(): Promise<Narrative> {
  const res = await fetch(`${API_BASE}/narrative/refresh`, { method: 'POST' })
  if (!res.ok) {
    const error = await res.json()
    throw new Error(error.message || 'Failed to refresh narrative')
  }
  return res.json()
}

export async function fetchRiddle(): Promise<Riddle> {
  const res = await fetch(`${API_BASE}/riddle`)
  if (!res.ok) {
    if (res.status === 404) {
      return { question: '', date: '', active: false }
    }
    throw new Error('Failed to fetch riddle')
  }
  return res.json()
}

export async function submitGuess(guess: string): Promise<GuessResult> {
  const res = await fetch(`${API_BASE}/riddle/guess`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ guess }),
  })
  if (!res.ok) throw new Error('Failed to submit guess')
  return res.json()
}

export async function fetchLeaderboard(): Promise<Leaderboard> {
  const res = await fetch(`${API_BASE}/leaderboard`)
  if (!res.ok) throw new Error('Failed to fetch leaderboard')
  return res.json()
}

export function getChartUrl(range: '24h' | '7d' | '30d'): string {
  return `${API_BASE}/charts/${range}`
}
