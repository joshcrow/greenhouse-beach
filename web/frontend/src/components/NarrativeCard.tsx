import { useEffect, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import Card from '@mui/material/Card'
import CardContent from '@mui/material/CardContent'
import Typography from '@mui/material/Typography'
import Box from '@mui/material/Box'
import Skeleton from '@mui/material/Skeleton'
import Chip from '@mui/material/Chip'
import IconButton from '@mui/material/IconButton'
import RefreshIcon from '@mui/icons-material/Refresh'
import { fetchNarrative, refreshNarrative } from '../api'

const STALE_THRESHOLD_MS = 60 * 60 * 1000 // 60 minutes

function isNarrativeStale(generatedAt: string | null): boolean {
  if (!generatedAt) return true
  const age = Date.now() - new Date(generatedAt).getTime()
  return age > STALE_THRESHOLD_MS
}

export function NarrativeCard() {
  const queryClient = useQueryClient()
  const hasAutoRefreshed = useRef(false)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['narrative'],
    queryFn: fetchNarrative,
    staleTime: 60 * 1000, // 1 minute
    refetchInterval: 5 * 60 * 1000, // 5 minutes
  })

  const refreshMutation = useMutation({
    mutationFn: refreshNarrative,
    onSuccess: (newData) => {
      queryClient.setQueryData(['narrative'], newData)
    },
  })

  // Auto-refresh if narrative is stale (>60 mins old) on first load
  useEffect(() => {
    if (
      data &&
      !hasAutoRefreshed.current &&
      !refreshMutation.isPending &&
      isNarrativeStale(data.generated_at)
    ) {
      hasAutoRefreshed.current = true
      refreshMutation.mutate()
    }
  }, [data, refreshMutation])

  if (isLoading) {
    return (
      <Card>
        <CardContent>
          <Skeleton variant="text" width="60%" height={32} />
          <Skeleton variant="text" width="80%" />
          <Skeleton variant="text" width="100%" />
          <Skeleton variant="text" width="90%" />
        </CardContent>
      </Card>
    )
  }

  if (isError) {
    return (
      <Card sx={{ borderColor: 'error.main', borderWidth: 2 }}>
        <CardContent>
          <Typography color="error">Failed to load narrative</Typography>
        </CardContent>
      </Card>
    )
  }

  const generatedAt = data?.generated_at
    ? new Date(data.generated_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    : null

  return (
    <Card>
      <CardContent>
        <Box sx={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', mb: 1 }}>
          <Box sx={{ flex: 1 }}>
            <Typography variant="h5" component="h2" sx={{ fontWeight: 600 }}>
              {data?.headline || 'No update available'}
            </Typography>
          </Box>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            {data?.cached && (
              <Chip label="Cached" size="small" variant="outlined" color="warning" />
            )}
            <IconButton
              size="small"
              onClick={() => refreshMutation.mutate()}
              disabled={refreshMutation.isPending}
              title="Refresh narrative"
            >
              <RefreshIcon
                sx={{
                  animation: refreshMutation.isPending ? 'spin 1s linear infinite' : 'none',
                  '@keyframes spin': {
                    '0%': { transform: 'rotate(0deg)' },
                    '100%': { transform: 'rotate(360deg)' },
                  },
                }}
              />
            </IconButton>
          </Box>
        </Box>

        <Typography
          variant="body1"
          sx={{ mb: 2 }}
          dangerouslySetInnerHTML={{ __html: data?.body || '' }}
        />

        {generatedAt && (
          <Typography variant="caption" color="text.secondary">
            Updated at {generatedAt}
          </Typography>
        )}

        {refreshMutation.isError && (
          <Typography variant="caption" color="error" sx={{ display: 'block', mt: 1 }}>
            {(refreshMutation.error as Error)?.message || 'Failed to refresh'}
          </Typography>
        )}
      </CardContent>
    </Card>
  )
}
