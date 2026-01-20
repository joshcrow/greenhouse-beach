import { useRef, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import Card from '@mui/material/Card'
import CardContent from '@mui/material/CardContent'
import Typography from '@mui/material/Typography'
import Box from '@mui/material/Box'
import CircularProgress from '@mui/material/CircularProgress'
import Button from '@mui/material/Button'
import VideoLibraryIcon from '@mui/icons-material/VideoLibrary'
import Hls from 'hls.js'

// HLS stream URL - proxied through API to Pi's mediamtx
const HLS_STREAM_URL = '/api/stream/cam/main_stream.m3u8'

export function LiveStreamCard() {
  const videoRef = useRef<HTMLVideoElement>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [isLive, setIsLive] = useState(false)

  useEffect(() => {
    const video = videoRef.current
    if (!video) return

    let hls: Hls | null = null

    if (Hls.isSupported()) {
      hls = new Hls({
        enableWorker: true,
        lowLatencyMode: true,
        backBufferLength: 90,
      })

      hls.loadSource(HLS_STREAM_URL)
      hls.attachMedia(video)

      hls.on(Hls.Events.MANIFEST_PARSED, () => {
        setIsLoading(false)
        setIsLive(true)
        video.play().catch(() => {
          // Autoplay might be blocked, that's ok
        })
      })

      hls.on(Hls.Events.ERROR, (_, data) => {
        if (data.fatal) {
          setError('Stream unavailable')
          setIsLoading(false)
          setIsLive(false)
        }
      })
    } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
      // Safari native HLS support
      video.src = HLS_STREAM_URL
      video.addEventListener('loadedmetadata', () => {
        setIsLoading(false)
        setIsLive(true)
        video.play().catch(() => {})
      })
      video.addEventListener('error', () => {
        setError('Stream unavailable')
        setIsLoading(false)
      })
    } else {
      setError('HLS not supported in this browser')
      setIsLoading(false)
    }

    return () => {
      if (hls) {
        hls.destroy()
      }
    }
  }, [])

  return (
    <Card
      sx={{
        overflow: 'hidden',
      }}
    >
      <Box sx={{ position: 'relative', paddingTop: '56.25%' /* 16:9 aspect ratio */ }}>
        {isLoading && (
          <Box
            sx={{
              position: 'absolute',
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              backgroundColor: '#171717',
            }}
          >
            <CircularProgress size={40} sx={{ color: '#6b9b5a' }} />
          </Box>
        )}
        {error && !isLoading && (
          <Box
            sx={{
              position: 'absolute',
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              backgroundColor: '#171717',
              color: '#666',
            }}
          >
            <Typography variant="body2">{error}</Typography>
          </Box>
        )}
        <video
          ref={videoRef}
          style={{
            position: 'absolute',
            top: 0,
            left: 0,
            width: '100%',
            height: '100%',
            objectFit: 'cover',
            display: isLoading || error ? 'none' : 'block',
          }}
          muted
          playsInline
          controls
        />
      </Box>
      <CardContent sx={{ py: 1.5, px: 2 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Typography variant="body2" color="text.secondary">
              📹 {isLive ? 'Live Stream' : 'Stream'}
            </Typography>
            {isLive && (
              <Box
                sx={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 0.5,
                  backgroundColor: 'rgba(239, 68, 68, 0.2)',
                  color: '#ef4444',
                  px: 1,
                  py: 0.25,
                  borderRadius: 1,
                  fontSize: '0.75rem',
                  fontWeight: 600,
                }}
              >
                <Box
                  sx={{
                    width: 6,
                    height: 6,
                    borderRadius: '50%',
                    backgroundColor: '#ef4444',
                    animation: 'pulse 2s infinite',
                    '@keyframes pulse': {
                      '0%, 100%': { opacity: 1 },
                      '50%': { opacity: 0.5 },
                    },
                  }}
                />
                LIVE
              </Box>
            )}
          </Box>
          <Button
            component={Link}
            to="/timelapse"
            size="small"
            startIcon={<VideoLibraryIcon />}
            sx={{ color: 'text.secondary', textTransform: 'none' }}
          >
            Timelapses
          </Button>
        </Box>
      </CardContent>
    </Card>
  )
}
