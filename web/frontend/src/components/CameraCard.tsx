import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import Card from '@mui/material/Card'
import CardContent from '@mui/material/CardContent'
import CardMedia from '@mui/material/CardMedia'
import Typography from '@mui/material/Typography'
import Box from '@mui/material/Box'
import Skeleton from '@mui/material/Skeleton'
import Dialog from '@mui/material/Dialog'
import IconButton from '@mui/material/IconButton'
import Button from '@mui/material/Button'
import CloseIcon from '@mui/icons-material/Close'
import ZoomInIcon from '@mui/icons-material/ZoomIn'
import PlayCircleOutlineIcon from '@mui/icons-material/PlayCircleOutline'

const CAMERA_URL = '/api/camera/latest'

async function checkCameraAvailable(): Promise<{ available: boolean; timestamp: string }> {
  try {
    const res = await fetch(CAMERA_URL)
    if (!res.ok) return { available: false, timestamp: '' }
    // Just check if we got a valid image response
    const contentType = res.headers.get('Content-Type') || ''
    if (!contentType.startsWith('image/')) return { available: false, timestamp: '' }
    return { 
      available: true, 
      timestamp: res.headers.get('X-Capture-Time') || new Date().toISOString() 
    }
  } catch {
    return { available: false, timestamp: '' }
  }
}

export function CameraCard() {
  const [lightboxOpen, setLightboxOpen] = useState(false)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['camera-available'],
    queryFn: checkCameraAvailable,
    staleTime: 5 * 60 * 1000, // 5 minutes
    refetchInterval: 5 * 60 * 1000,
  })


  if (isLoading) {
    return (
      <Card>
        <Skeleton variant="rectangular" height={200} />
        <CardContent>
          <Skeleton variant="text" width="60%" />
        </CardContent>
      </Card>
    )
  }

  if (isError || !data?.available) {
    return (
      <Card>
        <CardContent>
          <Typography color="text.secondary" textAlign="center">
            Camera image unavailable
          </Typography>
        </CardContent>
      </Card>
    )
  }

  const timestamp = data.timestamp 
    ? new Date(data.timestamp).toLocaleString([], { dateStyle: 'short', timeStyle: 'short' })
    : ''

  const imageUrl = CAMERA_URL

  return (
    <>
      <Card
        sx={{ cursor: 'pointer', position: 'relative' }}
        onClick={() => setLightboxOpen(true)}
      >
        <CardMedia
          component="img"
          height="200"
          image={imageUrl}
          alt="Greenhouse camera"
          sx={{ objectFit: 'cover' }}
        />
        <Box
          sx={{
            position: 'absolute',
            top: 8,
            right: 8,
            bgcolor: 'rgba(0,0,0,0.6)',
            borderRadius: 1,
            p: 0.5,
          }}
        >
          <ZoomInIcon fontSize="small" />
        </Box>
        <CardContent sx={{ py: 1, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Typography variant="caption" color="text.secondary">
            {timestamp}
          </Typography>
          <Button
            component={Link}
            to="/timelapse"
            size="small"
            startIcon={<PlayCircleOutlineIcon />}
            sx={{ textTransform: 'none' }}
          >
            View Timelapses
          </Button>
        </CardContent>
      </Card>

      {/* Lightbox */}
      <Dialog
        open={lightboxOpen}
        onClose={() => setLightboxOpen(false)}
        maxWidth="lg"
        fullWidth
        PaperProps={{
          sx: { bgcolor: 'transparent', boxShadow: 'none' },
        }}
      >
        <Box sx={{ position: 'relative' }}>
          <IconButton
            onClick={() => setLightboxOpen(false)}
            sx={{
              position: 'absolute',
              top: 8,
              right: 8,
              bgcolor: 'rgba(0,0,0,0.6)',
              '&:hover': { bgcolor: 'rgba(0,0,0,0.8)' },
            }}
          >
            <CloseIcon />
          </IconButton>
          <Box
            component="img"
            src={imageUrl}
            alt="Greenhouse camera full size"
            sx={{
              width: '100%',
              maxHeight: '90vh',
              objectFit: 'contain',
            }}
          />
        </Box>
      </Dialog>
    </>
  )
}
