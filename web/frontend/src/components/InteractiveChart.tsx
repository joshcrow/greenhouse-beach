import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import Box from '@mui/material/Box'
import Typography from '@mui/material/Typography'
import Skeleton from '@mui/material/Skeleton'
import ToggleButtonGroup from '@mui/material/ToggleButtonGroup'
import ToggleButton from '@mui/material/ToggleButton'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts'

type TimeRange = '24h' | '7d' | '30d'

interface DataPoint {
  timestamp: string
  interior_temp: number | null
  exterior_temp: number | null
  interior_humidity: number | null
  exterior_humidity: number | null
}

interface HistoryResponse {
  range: string
  data: DataPoint[]
}

async function fetchHistory(range: TimeRange): Promise<HistoryResponse> {
  const res = await fetch(`/api/history/${range}`)
  if (!res.ok) throw new Error('Failed to fetch history')
  return res.json()
}

function formatTime(timestamp: string, range: TimeRange): string {
  const date = new Date(timestamp)
  if (range === '24h') {
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  }
  return date.toLocaleDateString([], { month: 'short', day: 'numeric' })
}

const COLORS = {
  interior_temp: '#6b9b5a',
  exterior_temp: '#60a5fa',
  interior_humidity: '#8cb87a',
  exterior_humidity: '#93c5fd',
}

type MetricType = 'temperature' | 'humidity'

export function InteractiveChart() {
  const [range, setRange] = useState<TimeRange>('24h')
  const [metric, setMetric] = useState<MetricType>('temperature')

  const { data, isLoading, isError } = useQuery({
    queryKey: ['history', range],
    queryFn: () => fetchHistory(range),
    staleTime: 5 * 60 * 1000, // 5 minutes
  })

  if (isLoading) {
    return <Skeleton variant="rectangular" height={300} />
  }

  if (isError || !data?.data?.length) {
    return (
      <Box sx={{ height: 300, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <Typography color="text.secondary">No chart data available</Typography>
      </Box>
    )
  }

  const chartData = data.data.map((point) => ({
    ...point,
    time: formatTime(point.timestamp, range),
  }))

  const isTemp = metric === 'temperature'
  const insideKey = isTemp ? 'interior_temp' : 'interior_humidity'
  const outsideKey = isTemp ? 'exterior_temp' : 'exterior_humidity'
  const unit = isTemp ? '°F' : '%'

  return (
    <Box>
      <Box sx={{ display: 'flex', justifyContent: 'center', gap: 2, mb: 2, flexWrap: 'wrap' }}>
        <ToggleButtonGroup
          value={metric}
          exclusive
          onChange={(_, newMetric) => newMetric && setMetric(newMetric)}
          size="small"
        >
          <ToggleButton value="temperature">Temp</ToggleButton>
          <ToggleButton value="humidity">Humidity</ToggleButton>
        </ToggleButtonGroup>
        <ToggleButtonGroup
          value={range}
          exclusive
          onChange={(_, newRange) => newRange && setRange(newRange)}
          size="small"
        >
          <ToggleButton value="24h">24h</ToggleButton>
          <ToggleButton value="7d">7d</ToggleButton>
          <ToggleButton value="30d">30d</ToggleButton>
        </ToggleButtonGroup>
      </Box>

      <ResponsiveContainer width="100%" height={280}>
        <LineChart data={chartData} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#2d2d2d" />
          <XAxis
            dataKey="time"
            stroke="#a3a3a3"
            fontSize={12}
            tickLine={false}
          />
          <YAxis
            stroke="#a3a3a3"
            fontSize={12}
            tickLine={false}
            domain={isTemp ? [30, 90] : [0, 100]}
            unit={unit}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: '#1E1E1E',
              border: '1px solid #2d2d2d',
              borderRadius: 8,
            }}
            labelStyle={{ color: '#f5f5f5' }}
          />
          <Legend />
          <Line
            type="monotone"
            dataKey={insideKey}
            name={isTemp ? 'Inside' : 'Inside Humidity'}
            stroke={COLORS[insideKey]}
            strokeWidth={2}
            dot={false}
            connectNulls
          />
          <Line
            type="monotone"
            dataKey={outsideKey}
            name={isTemp ? 'Outside' : 'Outside Humidity'}
            stroke={COLORS[outsideKey]}
            strokeWidth={2}
            dot={false}
            connectNulls
          />
        </LineChart>
      </ResponsiveContainer>
    </Box>
  )
}
