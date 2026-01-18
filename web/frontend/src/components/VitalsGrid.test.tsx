import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { VitalsGrid } from './VitalsGrid'

// Mock the API
vi.mock('../api', () => ({
  fetchStatus: vi.fn(),
}))

import { fetchStatus } from '../api'

const mockFetchStatus = fetchStatus as ReturnType<typeof vi.fn>

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  })
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
}

describe('VitalsGrid', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders loading skeleton initially', () => {
    mockFetchStatus.mockReturnValue(new Promise(() => {})) // Never resolves
    render(<VitalsGrid />, { wrapper: createWrapper() })
    
    // Should show skeleton loaders
    expect(screen.getAllByRole('progressbar').length).toBeGreaterThan(0)
  })

  it('renders sensor values when data loads', async () => {
    mockFetchStatus.mockResolvedValue({
      sensors: {
        interior_temp: 68,
        exterior_temp: 42,
        interior_humidity: 55,
        satellite_battery: 3.8,
      },
      stale: {
        interior_temp: false,
        exterior_temp: false,
        interior_humidity: false,
        satellite_battery: false,
      },
    })

    render(<VitalsGrid />, { wrapper: createWrapper() })

    // Wait for data to load
    expect(await screen.findByText('68')).toBeInTheDocument()
    expect(await screen.findByText('42')).toBeInTheDocument()
  })

  it('shows stale indicator for stale data', async () => {
    mockFetchStatus.mockResolvedValue({
      sensors: {
        interior_temp: 68,
        exterior_temp: null,
        interior_humidity: 55,
        satellite_battery: 3.8,
      },
      stale: {
        interior_temp: false,
        exterior_temp: true,
        interior_humidity: false,
        satellite_battery: false,
      },
    })

    render(<VitalsGrid />, { wrapper: createWrapper() })

    // Wait for stale chip to appear
    expect(await screen.findByText('Stale')).toBeInTheDocument()
  })

  it('renders error state on fetch failure', async () => {
    mockFetchStatus.mockRejectedValue(new Error('Network error'))

    render(<VitalsGrid />, { wrapper: createWrapper() })

    expect(await screen.findByText(/failed to load/i)).toBeInTheDocument()
  })
})
