import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import Box from '@mui/material/Box'
import Tabs from '@mui/material/Tabs'
import Tab from '@mui/material/Tab'
import Typography from '@mui/material/Typography'
import List from '@mui/material/List'
import ListItem from '@mui/material/ListItem'
import ListItemText from '@mui/material/ListItemText'
import Skeleton from '@mui/material/Skeleton'
import IconButton from '@mui/material/IconButton'
import CloseIcon from '@mui/icons-material/Close'
import { fetchLeaderboard } from '../api'
import { InteractiveChart } from './InteractiveChart'

interface TabPanelProps {
  children?: React.ReactNode
  index: number
  value: number
}

function TabPanel({ children, value, index }: TabPanelProps) {
  return (
    <div role="tabpanel" hidden={value !== index}>
      {value === index && <Box sx={{ p: 2 }}>{children}</Box>}
    </div>
  )
}

function ChartsPanel() {
  return <InteractiveChart />
}

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

function TimelapsePanel() {
  const { data, isLoading } = useQuery({
    queryKey: ['timelapses'],
    queryFn: fetchTimelapses,
    staleTime: 10 * 60 * 1000, // 10 minutes
  })

  if (isLoading) {
    return <Skeleton variant="rectangular" height={200} />
  }

  const hasAny = data?.daily || data?.weekly || data?.monthly

  if (!hasAny) {
    return (
      <Typography color="text.secondary" textAlign="center">
        No timelapses available yet
      </Typography>
    )
  }

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      {data?.daily && (
        <Box>
          <Typography variant="subtitle2" color="text.secondary" gutterBottom>
            Today's Timelapse
          </Typography>
          <Box
            component="img"
            src={data.daily}
            alt="Daily timelapse"
            sx={{ width: '100%', borderRadius: 1 }}
          />
        </Box>
      )}
      {data?.weekly && (
        <Box>
          <Typography variant="subtitle2" color="text.secondary" gutterBottom>
            This Week
          </Typography>
          <Box
            component="video"
            src={data.weekly}
            controls
            sx={{ width: '100%', borderRadius: 1 }}
          />
        </Box>
      )}
      {data?.monthly && (
        <Box>
          <Typography variant="subtitle2" color="text.secondary" gutterBottom>
            This Month
          </Typography>
          <Box
            component="video"
            src={data.monthly}
            controls
            sx={{ width: '100%', borderRadius: 1 }}
          />
        </Box>
      )}
    </Box>
  )
}

function LeaderboardPanel() {
  const { data, isLoading } = useQuery({
    queryKey: ['leaderboard'],
    queryFn: fetchLeaderboard,
    staleTime: 5 * 60 * 1000, // 5 minutes
  })

  if (isLoading) {
    return (
      <Box>
        {[1, 2, 3].map((i) => (
          <Skeleton key={i} variant="rectangular" height={48} sx={{ mb: 1 }} />
        ))}
      </Box>
    )
  }

  if (!data?.players?.length) {
    return (
      <Typography color="text.secondary" textAlign="center">
        No scores yet this season
      </Typography>
    )
  }

  return (
    <List dense>
      {data.players.map((player, index) => (
        <ListItem
          key={player.display_name}
          sx={{
            bgcolor: index === 0 ? 'primary.dark' : 'transparent',
            borderRadius: 1,
            mb: 0.5,
          }}
        >
          <Typography
            variant="h6"
            sx={{ width: 32, fontWeight: 700, color: index < 3 ? 'warning.main' : 'text.secondary' }}
          >
            {index + 1}
          </Typography>
          <ListItemText
            primary={player.display_name}
            secondary={`${player.wins} wins`}
          />
          <Typography variant="h6" sx={{ fontWeight: 700 }}>
            {player.points}
          </Typography>
        </ListItem>
      ))}
    </List>
  )
}

interface BottomSheetProps {
  onClose: () => void
}

export function BottomSheet({ onClose }: BottomSheetProps) {
  const [tab, setTab] = useState(0)

  return (
    <Box sx={{ minHeight: 300 }}>
      {/* Handle */}
      <Box sx={{ display: 'flex', justifyContent: 'center', pt: 1 }}>
        <Box
          sx={{
            width: 40,
            height: 4,
            borderRadius: 2,
            bgcolor: 'divider',
          }}
        />
      </Box>

      {/* Header */}
      <Box sx={{ display: 'flex', alignItems: 'center', px: 2, pt: 1 }}>
        <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ flex: 1 }} variant="scrollable" scrollButtons="auto">
          <Tab label="Charts" />
          <Tab label="Timelapse" />
          <Tab label="Leaderboard" />
        </Tabs>
        <IconButton onClick={onClose} size="small">
          <CloseIcon />
        </IconButton>
      </Box>

      {/* Content */}
      <TabPanel value={tab} index={0}>
        <ChartsPanel />
      </TabPanel>
      <TabPanel value={tab} index={1}>
        <TimelapsePanel />
      </TabPanel>
      <TabPanel value={tab} index={2}>
        <LeaderboardPanel />
      </TabPanel>
    </Box>
  )
}
