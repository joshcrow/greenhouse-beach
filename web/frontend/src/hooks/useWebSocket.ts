import { useEffect, useRef, useCallback, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'

interface WebSocketOptions {
  onMessage?: (data: unknown) => void
  reconnectInterval?: number
  maxReconnectAttempts?: number
}

type ConnectionStatus = 'connecting' | 'connected' | 'disconnected' | 'error'

export function useWebSocket(url: string, options: WebSocketOptions = {}) {
  const {
    onMessage,
    reconnectInterval = 3000,
    maxReconnectAttempts = 10,
  } = options

  const [status, setStatus] = useState<ConnectionStatus>('disconnected')
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectAttempts = useRef(0)
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout>>()

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return

    setStatus('connecting')
    
    // Build WebSocket URL
    const wsUrl = url.startsWith('ws')
      ? url
      : `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}${url}`

    try {
      wsRef.current = new WebSocket(wsUrl)

      wsRef.current.onopen = () => {
        setStatus('connected')
        reconnectAttempts.current = 0
      }

      wsRef.current.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          onMessage?.(data)
        } catch (e) {
          console.error('Failed to parse WebSocket message:', e)
        }
      }

      wsRef.current.onclose = () => {
        setStatus('disconnected')
        
        // Attempt reconnect with exponential backoff
        if (reconnectAttempts.current < maxReconnectAttempts) {
          const delay = reconnectInterval * Math.pow(1.5, reconnectAttempts.current)
          reconnectAttempts.current++
          reconnectTimeoutRef.current = setTimeout(connect, delay)
        }
      }

      wsRef.current.onerror = () => {
        setStatus('error')
      }
    } catch (e) {
      setStatus('error')
    }
  }, [url, onMessage, reconnectInterval, maxReconnectAttempts])

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current)
    }
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }
    setStatus('disconnected')
  }, [])

  useEffect(() => {
    connect()
    return () => disconnect()
  }, [connect, disconnect])

  return { status, connect, disconnect }
}

/**
 * Hook that connects to the status WebSocket and updates React Query cache
 */
export function useStatusWebSocket() {
  const queryClient = useQueryClient()

  const handleMessage = useCallback((data: unknown) => {
    const message = data as { type: string; sensors?: unknown; stale?: unknown }
    
    if (message.type === 'status') {
      // Update the status query cache with new data
      queryClient.setQueryData(['status'], (old: unknown) => ({
        ...(old as object),
        sensors: message.sensors,
        stale: message.stale,
      }))
    }
  }, [queryClient])

  return useWebSocket('/api/ws/status', { onMessage: handleMessage })
}
