import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import Box from '@mui/material/Box'
import AppBar from '@mui/material/AppBar'
import Toolbar from '@mui/material/Toolbar'
import Typography from '@mui/material/Typography'
import Container from '@mui/material/Container'
import Card from '@mui/material/Card'
import CardContent from '@mui/material/CardContent'
import IconButton from '@mui/material/IconButton'
import Skeleton from '@mui/material/Skeleton'
import ArrowBackIcon from '@mui/icons-material/ArrowBack'

interface TimelapseData {
  daily: string | null
  weekly: string | null
  monthly: string | null
}

async function fetchTimelapses(): Promise<TimelapseData> {
  const res = await fetch('/api/timelapses')
  if (!res.ok) throw new Error('Failed to fetch timelapses')
  return res.json()
}

export function TimelapsePage() {
  const { data, isLoading } = useQuery({
    queryKey: ['timelapses'],
    queryFn: fetchTimelapses,
    staleTime: 10 * 60 * 1000,
  })

  const hasAny = data?.daily || data?.weekly || data?.monthly

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
      <AppBar position="sticky" elevation={0}>
        <Toolbar>
          <IconButton
            edge="start"
            color="inherit"
            component={Link}
            to="/"
            sx={{ mr: 2 }}
          >
            <ArrowBackIcon />
          </IconButton>
          <Typography variant="h6" component="h1" sx={{ fontWeight: 700 }}>
            Timelapse Gallery
          </Typography>
        </Toolbar>
      </AppBar>

      <Container component="main" maxWidth="sm" sx={{ flex: 1, py: 2 }}>
        {isLoading ? (
          <Card>
            <Skeleton variant="rectangular" height={200} />
            <CardContent>
              <Skeleton variant="text" width="60%" />
            </CardContent>
          </Card>
        ) : !hasAny ? (
          <Card>
            <CardContent>
              <Typography color="text.secondary" textAlign="center">
                No timelapses available yet. Check back after the first full day of captures.
              </Typography>
            </CardContent>
          </Card>
        ) : (
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            {data?.daily && (
              <Card>
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    Today's Timelapse
                  </Typography>
                  <Box
                    component="img"
                    src={data.daily}
                    alt="Daily timelapse"
                    sx={{ width: '100%', borderRadius: 1 }}
                  />
                </CardContent>
              </Card>
            )}

            {data?.weekly && (
              <Card>
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    This Week
                  </Typography>
                  <Box
                    component="video"
                    src={data.weekly}
                    controls
                    sx={{ width: '100%', borderRadius: 1 }}
                  />
                </CardContent>
              </Card>
            )}

            {data?.monthly && (
              <Card>
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    This Month
                  </Typography>
                  <Box
                    component="video"
                    src={data.monthly}
                    controls
                    sx={{ width: '100%', borderRadius: 1 }}
                  />
                </CardContent>
              </Card>
            )}
          </Box>
        )}
      </Container>
    </Box>
  )
}
