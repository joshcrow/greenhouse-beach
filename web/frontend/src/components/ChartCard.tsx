import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import Card from '@mui/material/Card'
import CardContent from '@mui/material/CardContent'
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
type MetricType = 'temperature' | 'humidity'

interface ApiDataPoint {
  timestamp: string
  interior_temp: number | null
  interior_humidity: number | null
  exterior_temp: number | null
  exterior_humidity: number | null
}

interface ChartDataPoint {
  timestamp: string
  inside: number | null
  outside: number | null
}

interface ApiResponse {
  resolution: string
  points: ApiDataPoint[]
}

async function fetchChartData(range: TimeRange, metric: MetricType): Promise<ChartDataPoint[]> {
  const res = await fetch(`/api/history?range=${range}&metric=${metric}`)
  if (!res.ok) throw new Error('Failed to fetch chart data')
  const response: ApiResponse = await res.json()
  const data = response.points || []
  
  // Transform API response to chart format
  return data.map((point) => ({
    timestamp: point.timestamp,
    inside: metric === 'temperature' ? point.interior_temp : point.interior_humidity,
    outside: metric === 'temperature' ? point.exterior_temp : point.exterior_humidity,
  }))
}

export function ChartCard() {
  const [range, setRange] = useState<TimeRange>('24h')
  const [metric, setMetric] = useState<MetricType>('temperature')

  const { data, isLoading } = useQuery({
    queryKey: ['chart', range, metric],
    queryFn: () => fetchChartData(range, metric),
    staleTime: 5 * 60 * 1000,
  })

  const formatXAxis = (timestamp: string) => {
    const date = new Date(timestamp)
    if (range === '24h') {
      return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    }
    return date.toLocaleDateString([], { month: 'short', day: 'numeric' })
  }

  const formatTooltip = (value: number) => {
    const rounded = Math.round(value * 10) / 10
    return metric === 'temperature' ? `${rounded}°F` : `${rounded}%`
  }

  return (
    <Card>
      <CardContent>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2, flexWrap: 'wrap', gap: 1 }}>
          <Typography variant="h6" component="h2">
            {metric === 'temperature' ? 'Temperature' : 'Humidity'}
          </Typography>
          <Box sx={{ display: 'flex', gap: 1 }}>
            <ToggleButtonGroup
              value={metric}
              exclusive
              onChange={(_: React.MouseEvent<HTMLElement>, newMetric: MetricType | null) => newMetric && setMetric(newMetric)}
              size="small"
            >
              <ToggleButton value="temperature">Temp</ToggleButton>
              <ToggleButton value="humidity">Humidity</ToggleButton>
            </ToggleButtonGroup>
            <ToggleButtonGroup
              value={range}
              exclusive
              onChange={(_: React.MouseEvent<HTMLElement>, newRange: TimeRange | null) => newRange && setRange(newRange)}
              size="small"
            >
              <ToggleButton value="24h">24h</ToggleButton>
              <ToggleButton value="7d">7d</ToggleButton>
              <ToggleButton value="30d">30d</ToggleButton>
            </ToggleButtonGroup>
          </Box>
        </Box>

        {isLoading ? (
          <Skeleton variant="rectangular" height={200} />
        ) : !data?.length ? (
          <Typography color="text.secondary" textAlign="center" sx={{ py: 4 }}>
            No data available for this time range
          </Typography>
        ) : (
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={data} margin={{ top: 5, right: 5, left: -20, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#333" />
              <XAxis
                dataKey="timestamp"
                tickFormatter={formatXAxis}
                stroke="#888"
                fontSize={12}
                tickLine={false}
              />
              <YAxis
                stroke="#888"
                fontSize={12}
                tickLine={false}
                tickFormatter={(v: number) => metric === 'temperature' ? `${v}°` : `${v}%`}
              />
              <Tooltip
                formatter={formatTooltip}
                labelFormatter={(label: string) => new Date(label).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                contentStyle={{ backgroundColor: '#1e1e1e', border: '1px solid #333', fontSize: '12px' }}
                position={{ y: 0 }}
                wrapperStyle={{ pointerEvents: 'none' }}
              />
              <Legend />
              <Line
                type="monotone"
                dataKey="inside"
                name="Inside"
                stroke="#6b9b5a"
                strokeWidth={2}
                dot={false}
              />
              <Line
                type="monotone"
                dataKey="outside"
                name="Outside"
                stroke="#60a5fa"
                strokeWidth={2}
                dot={false}
              />
            </LineChart>
          </ResponsiveContainer>
        )}
      </CardContent>
    </Card>
  )
}
