import { useQuery } from '@tanstack/react-query'
import Grid from '@mui/material/Grid'
import Card from '@mui/material/Card'
import CardContent from '@mui/material/CardContent'
import Typography from '@mui/material/Typography'
import Box from '@mui/material/Box'
import Skeleton from '@mui/material/Skeleton'
import Chip from '@mui/material/Chip'
import ThermostatIcon from '@mui/icons-material/Thermostat'
import WaterDropIcon from '@mui/icons-material/WaterDrop'
import BatteryFullIcon from '@mui/icons-material/BatteryFull'
import BatteryAlertIcon from '@mui/icons-material/BatteryAlert'
import { fetchStatus } from '../api'

interface VitalCardProps {
  title: string
  value: string | number | null
  unit: string
  icon: React.ReactNode
  color: 'primary' | 'secondary' | 'warning' | 'error'
  stale?: boolean
  loading?: boolean
}

function VitalCard({ title, value, unit, icon, color, stale, loading }: VitalCardProps) {
  if (loading) {
    return (
      <Card>
        <CardContent>
          <Skeleton variant="text" width="60%" />
          <Skeleton variant="text" width="40%" height={48} />
        </CardContent>
      </Card>
    )
  }

  return (
    <Card
      sx={{
        position: 'relative',
        borderColor: stale ? 'warning.main' : undefined,
        borderWidth: stale ? 2 : 1,
      }}
    >
      <CardContent>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
          <Box sx={{ color: `${color}.main` }}>{icon}</Box>
          <Typography variant="body2" color="text.secondary">
            {title}
          </Typography>
          {stale && (
            <Chip
              label="Stale"
              size="small"
              color="warning"
              sx={{ ml: 'auto', height: 20, fontSize: '0.7rem' }}
            />
          )}
        </Box>
        <Typography variant="h3" component="div" sx={{ fontWeight: 700 }}>
          {value !== null ? value : '--'}
          <Typography component="span" variant="h5" color="text.secondary" sx={{ ml: 0.5 }}>
            {unit}
          </Typography>
        </Typography>
      </CardContent>
    </Card>
  )
}

function BatteryCard({ voltage, stale, loading }: { voltage: number | null; stale?: boolean; loading?: boolean }) {
  if (loading) {
    return (
      <Card>
        <CardContent>
          <Skeleton variant="text" width="60%" />
          <Skeleton variant="rectangular" height={24} />
        </CardContent>
      </Card>
    )
  }

  const isCritical = voltage !== null && voltage < 3.4
  const isLow = voltage !== null && voltage < 3.6
  const percentage = voltage !== null ? Math.min(100, Math.max(0, ((voltage - 3.0) / 1.2) * 100)) : 0

  return (
    <Card
      sx={{
        borderColor: isCritical ? 'error.main' : isLow ? 'warning.main' : stale ? 'warning.main' : undefined,
        borderWidth: isCritical || isLow || stale ? 2 : 1,
      }}
    >
      <CardContent>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
          <Box sx={{ color: isCritical ? 'error.main' : isLow ? 'warning.main' : 'success.main' }}>
            {isCritical || isLow ? <BatteryAlertIcon /> : <BatteryFullIcon />}
          </Box>
          <Typography variant="body2" color="text.secondary">
            Battery
          </Typography>
          {stale && (
            <Chip
              label="Stale"
              size="small"
              color="warning"
              sx={{ ml: 'auto', height: 20, fontSize: '0.7rem' }}
            />
          )}
        </Box>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          <Typography variant="h4" component="div" sx={{ fontWeight: 700, minWidth: 70 }}>
            {voltage !== null ? voltage.toFixed(2) : '--'}
            <Typography component="span" variant="body1" color="text.secondary">
              V
            </Typography>
          </Typography>
          <Box
            sx={{
              flex: 1,
              height: 12,
              borderRadius: 1,
              bgcolor: 'background.default',
              overflow: 'hidden',
            }}
          >
            <Box
              sx={{
                width: `${percentage}%`,
                height: '100%',
                bgcolor: isCritical ? 'error.main' : isLow ? 'warning.main' : 'success.main',
                transition: 'width 0.3s, background-color 0.3s',
              }}
            />
          </Box>
        </Box>
      </CardContent>
    </Card>
  )
}

export function VitalsGrid() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['status'],
    queryFn: fetchStatus,
  })

  if (isError) {
    return (
      <Card sx={{ borderColor: 'error.main', borderWidth: 2 }}>
        <CardContent>
          <Typography color="error">Failed to load sensor data</Typography>
        </CardContent>
      </Card>
    )
  }

  const sensors = data?.sensors
  const stale = data?.stale

  return (
    <Grid container spacing={2}>
      <Grid item xs={6}>
        <VitalCard
          title="Inside"
          value={sensors?.interior_temp ?? null}
          unit="°F"
          icon={<ThermostatIcon />}
          color="primary"
          stale={stale?.interior_temp}
          loading={isLoading}
        />
      </Grid>
      <Grid item xs={6}>
        <VitalCard
          title="Outside"
          value={sensors?.exterior_temp ?? null}
          unit="°F"
          icon={<ThermostatIcon />}
          color="secondary"
          stale={stale?.exterior_temp}
          loading={isLoading}
        />
      </Grid>
      <Grid item xs={6}>
        <VitalCard
          title="Humidity In"
          value={sensors?.interior_humidity ?? null}
          unit="%"
          icon={<WaterDropIcon />}
          color="primary"
          stale={stale?.interior_humidity}
          loading={isLoading}
        />
      </Grid>
      <Grid item xs={6}>
        <BatteryCard
          voltage={sensors?.satellite_battery ?? null}
          stale={stale?.satellite_battery}
          loading={isLoading}
        />
      </Grid>
    </Grid>
  )
}
