import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useMutation } from '@tanstack/react-query'
import Card from '@mui/material/Card'
import CardContent from '@mui/material/CardContent'
import Typography from '@mui/material/Typography'
import Box from '@mui/material/Box'
import TextField from '@mui/material/TextField'
import Button from '@mui/material/Button'
import Skeleton from '@mui/material/Skeleton'
import Alert from '@mui/material/Alert'
import Collapse from '@mui/material/Collapse'
import Chip from '@mui/material/Chip'
import Divider from '@mui/material/Divider'
import EmojiEventsIcon from '@mui/icons-material/EmojiEvents'
import LeaderboardIcon from '@mui/icons-material/Leaderboard'
import { fetchRiddle, submitGuess } from '../api'

interface PlayerStats {
  display_name: string
  points: number
  wins: number
  rank: number
  season: string
}

async function fetchPlayerStats(): Promise<PlayerStats | null> {
  try {
    const res = await fetch('/api/riddle/stats')
    if (!res.ok) return null
    return res.json()
  } catch {
    return null
  }
}

interface YesterdayRiddle {
  question: string
  answer: string
  date: string
}

async function fetchYesterdayRiddle(): Promise<YesterdayRiddle | null> {
  try {
    const res = await fetch('/api/riddle/yesterday')
    if (!res.ok) return null
    return res.json()
  } catch {
    return null
  }
}

export function RiddleCard() {
  const [guess, setGuess] = useState('')
  const [result, setResult] = useState<{
    type: 'success' | 'error' | 'info'
    message: string
  } | null>(null)

  const { data: riddle, isLoading, isError } = useQuery({
    queryKey: ['riddle'],
    queryFn: fetchRiddle,
    staleTime: 60 * 60 * 1000, // 1 hour (riddle changes daily)
  })

  const { data: stats } = useQuery({
    queryKey: ['riddle-stats'],
    queryFn: fetchPlayerStats,
    staleTime: 5 * 60 * 1000,
  })

  const { data: yesterdayRiddle } = useQuery({
    queryKey: ['riddle-yesterday'],
    queryFn: fetchYesterdayRiddle,
    staleTime: 60 * 60 * 1000,
  })

  const guessMutation = useMutation({
    mutationFn: submitGuess,
    onSuccess: (data) => {
      if (data.correct) {
        setResult({
          type: 'success',
          message: data.message + (data.is_first ? ' (First solver!)' : ''),
        })
        setGuess('')
      } else if (data.already_solved) {
        setResult({ type: 'info', message: data.message })
      } else {
        setResult({ type: 'error', message: data.message })
      }
    },
    onError: (error: Error) => {
      setResult({ type: 'error', message: error.message })
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (guess.trim()) {
      setResult(null)
      guessMutation.mutate(guess.trim())
    }
  }

  if (isLoading) {
    return (
      <Card>
        <CardContent>
          <Skeleton variant="text" width="40%" />
          <Skeleton variant="text" width="100%" />
          <Skeleton variant="rectangular" height={56} sx={{ mt: 2 }} />
        </CardContent>
      </Card>
    )
  }

  if (isError || !riddle?.active) {
    return (
      <Card>
        <CardContent>
          <Typography variant="overline" color="text.secondary">
            Daily Riddle
          </Typography>
          <Typography color="text.secondary">
            No riddle available. Check back after the morning Gazette!
          </Typography>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardContent>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
          <Typography variant="overline" color="text.secondary">
            Daily Riddle
          </Typography>
          {stats && (
            <Box sx={{ display: 'flex', gap: 0.5 }}>
              <Chip
                size="small"
                icon={<EmojiEventsIcon />}
                label={`#${stats.rank}`}
                color="primary"
                variant="outlined"
              />
              <Chip
                size="small"
                label={`${stats.points} pts`}
                variant="outlined"
              />
            </Box>
          )}
        </Box>
        <Typography variant="body1" sx={{ mb: 2, fontStyle: 'italic' }}>
          "{riddle.question}"
        </Typography>

        <Collapse in={!!result}>
          <Alert
            severity={result?.type || 'info'}
            onClose={() => setResult(null)}
            sx={{ mb: 2 }}
          >
            {result?.message}
          </Alert>
        </Collapse>

        <Box component="form" onSubmit={handleSubmit} sx={{ display: 'flex', gap: 1 }}>
          <TextField
            size="small"
            placeholder="Your guess..."
            value={guess}
            onChange={(e) => setGuess(e.target.value)}
            disabled={guessMutation.isPending}
            fullWidth
            inputProps={{ maxLength: 200 }}
          />
          <Button
            type="submit"
            variant="contained"
            disabled={!guess.trim() || guessMutation.isPending}
            sx={{ minWidth: 80 }}
          >
            {guessMutation.isPending ? '...' : 'Guess'}
          </Button>
        </Box>

        {yesterdayRiddle && (
          <>
            <Divider sx={{ my: 2 }} />
            <Box>
              <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.5 }}>
                Yesterday's Riddle
              </Typography>
              <Typography variant="body2" sx={{ fontStyle: 'italic', mb: 0.5 }}>
                "{yesterdayRiddle.question}"
              </Typography>
              <Typography variant="body2" color="primary" sx={{ fontWeight: 600 }}>
                Answer: {yesterdayRiddle.answer}
              </Typography>
            </Box>
          </>
        )}

        <Divider sx={{ my: 2 }} />
        <Button
          component={Link}
          to="/leaderboard"
          startIcon={<LeaderboardIcon />}
          size="small"
          sx={{ textTransform: 'none' }}
        >
          View Leaderboard
        </Button>
      </CardContent>
    </Card>
  )
}
