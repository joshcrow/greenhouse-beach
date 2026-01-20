import Box from '@mui/material/Box'
import AppBar from '@mui/material/AppBar'
import Toolbar from '@mui/material/Toolbar'
import Typography from '@mui/material/Typography'
import Container from '@mui/material/Container'
import IconButton from '@mui/material/IconButton'
import ArrowBackIcon from '@mui/icons-material/ArrowBack'
import { Link } from 'react-router-dom'

import { LiveStreamCard } from '../components/LiveStreamCard'

export function LivePage() {
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
      <AppBar position="sticky" elevation={0}>
        <Toolbar>
          <IconButton
            component={Link}
            to="/"
            edge="start"
            color="inherit"
            sx={{ mr: 2 }}
          >
            <ArrowBackIcon />
          </IconButton>
          <Typography variant="h6" component="h1" sx={{ flexGrow: 1, fontWeight: 700 }}>
            Live Stream
          </Typography>
        </Toolbar>
      </AppBar>

      <Container
        component="main"
        maxWidth="md"
        sx={{
          flex: 1,
          py: 2,
          display: 'flex',
          flexDirection: 'column',
          gap: 2,
        }}
      >
        <LiveStreamCard />
        
        <Typography variant="body2" color="text.secondary" sx={{ textAlign: 'center' }}>
          720p @ 15fps • ~5 second delay
        </Typography>
      </Container>
    </Box>
  )
}
