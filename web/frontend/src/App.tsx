import { Routes, Route } from 'react-router-dom'
import Box from '@mui/material/Box'
import AppBar from '@mui/material/AppBar'
import Toolbar from '@mui/material/Toolbar'
import Typography from '@mui/material/Typography'
import Container from '@mui/material/Container'

import { ConnectionPulse } from './components/ConnectionPulse'
import { CameraCard } from './components/CameraCard'
import { VitalsGrid } from './components/VitalsGrid'
import { NarrativeCard } from './components/NarrativeCard'
import { RiddleCard } from './components/RiddleCard'
import { ChartCard } from './components/ChartCard'
import { useStatusWebSocket } from './hooks/useWebSocket'
import { TimelapsePage } from './pages/TimelapsePage'
import { LeaderboardPage } from './pages/LeaderboardPage'

function HomePage() {
  // Connect to WebSocket for real-time sensor updates
  useStatusWebSocket()

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
      {/* App Bar */}
      <AppBar position="sticky" elevation={0}>
        <Toolbar>
          <Typography variant="h6" component="h1" sx={{ flexGrow: 1, fontWeight: 700 }}>
            Straight Outta Colington
          </Typography>
          <ConnectionPulse />
        </Toolbar>
      </AppBar>

      {/* Main Content */}
      <Container
        component="main"
        maxWidth="sm"
        sx={{
          flex: 1,
          py: 2,
          display: 'flex',
          flexDirection: 'column',
          gap: 2,
        }}
      >
        {/* Narrative (Email-style headline at top) */}
        <NarrativeCard />

        {/* Greenhouse Camera Image */}
        <CameraCard />

        {/* Vitals Grid (Sensor Cards) */}
        <VitalsGrid />

        {/* Temperature/Humidity Chart */}
        <ChartCard />

        {/* Riddle Game */}
        <RiddleCard />
      </Container>
    </Box>
  )
}

function App() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/timelapse" element={<TimelapsePage />} />
      <Route path="/leaderboard" element={<LeaderboardPage />} />
    </Routes>
  )
}

export default App
