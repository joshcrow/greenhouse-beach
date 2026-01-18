import { useQuery } from '@tanstack/react-query'
import Box from '@mui/material/Box'
import { keyframes } from '@mui/material/styles'
import { fetchStatus } from '../api'

const pulse = keyframes`
  0% { opacity: 1; }
  50% { opacity: 0.4; }
  100% { opacity: 1; }
`

export function ConnectionPulse() {
  const { isError, isFetching } = useQuery({
    queryKey: ['status'],
    queryFn: fetchStatus,
  })

  const color = isError ? 'error.main' : 'success.main'

  return (
    <Box
      sx={{
        width: 12,
        height: 12,
        borderRadius: '50%',
        backgroundColor: color,
        animation: isFetching ? `${pulse} 1s ease-in-out infinite` : 'none',
        transition: 'background-color 0.3s',
      }}
      title={isError ? 'Connection error' : 'Connected'}
    />
  )
}
