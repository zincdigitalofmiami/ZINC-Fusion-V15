'use client'

import { useState, useEffect, type FormEvent } from 'react'
import { useRouter } from 'next/navigation'

export default function LoginPage() {
  const router = useRouter()
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [status, setStatus] = useState<'idle' | 'submitting' | 'success'>('idle')
  const [checkingAuth, setCheckingAuth] = useState(true)

  // Check if already authenticated on mount
  useEffect(() => {
    async function checkAuth() {
      try {
        // Try to access a protected endpoint
        const res = await fetch('/api/zl/chart', { 
          method: 'HEAD',
          credentials: 'same-origin' 
        })
        if (res.ok) {
          // Already logged in - redirect to dashboard
          const nextPath = new URLSearchParams(window.location.search).get('next')
          const destination = nextPath && nextPath.startsWith('/') ? nextPath : '/dashboard'
          router.replace(destination)
          return
        }
      } catch {
        // Not authenticated, show login form
      }
      setCheckingAuth(false)
    }
    checkAuth()
  }, [router])

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (status !== 'idle' || !password.trim()) return

    setError(null)
    setStatus('submitting')

    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password }),
        credentials: 'same-origin',
      })

      const data = await res.json().catch(() => ({ ok: false, error: 'Invalid response' }))

      if (!res.ok || !data.ok) {
        setError(data.error || 'Login failed')
        setPassword('')
        setStatus('idle')
        return
      }

      // Success!
      setStatus('success')
      
      // Small delay to ensure cookie is persisted before redirect
      await new Promise(resolve => setTimeout(resolve, 100))
      
      const nextPath = new URLSearchParams(window.location.search).get('next')
      const destination = nextPath && nextPath.startsWith('/') ? nextPath : '/dashboard'
      
      // Use router.push first to update Next.js cache, then hard reload
      router.push(destination)
      
      // Fallback: if router.push doesn't trigger navigation, force it
      setTimeout(() => {
        window.location.href = destination
      }, 300)

    } catch (err) {
      setError('Network error. Please try again.')
      setStatus('idle')
    }
  }

  // Show loading while checking auth
  if (checkingAuth) {
    return (
      <div className="main-content" style={{ maxWidth: 520, margin: '0 auto', paddingTop: 120 }}>
        <div className="card" style={{ marginTop: 60, textAlign: 'center' }}>
          <div style={{ color: 'var(--text-muted)' }}>Checking authentication...</div>
        </div>
      </div>
    )
  }

  const isDisabled = status !== 'idle'

  return (
    <div className="main-content" style={{ maxWidth: 520, margin: '0 auto', paddingTop: 120 }}>
      <div className="card" style={{ marginTop: 60 }}>
        <h1 style={{ fontSize: 28, fontWeight: 700, marginBottom: 10 }}>
          Client Login
        </h1>
        <p style={{ color: 'var(--text-muted)', marginBottom: 20 }}>
          Enter the client password to access the dashboard.
        </p>

        <form onSubmit={onSubmit}>
          <div style={{ display: 'flex', gap: 12 }}>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Password"
              autoComplete="current-password"
              autoFocus
              disabled={isDisabled}
              style={{
                flex: 1,
                padding: '12px 14px',
                borderRadius: 10,
                border: '1px solid var(--border)',
                background: 'var(--surface-2)',
                color: 'var(--text)',
                outline: 'none',
                opacity: isDisabled ? 0.7 : 1,
              }}
            />
            <button
              type="submit"
              disabled={isDisabled || !password.trim()}
              style={{
                padding: '12px 20px',
                borderRadius: 10,
                border: 'none',
                background: status === 'success' 
                  ? '#22c55e' 
                  : (isDisabled || !password.trim()) 
                    ? 'var(--surface-3)' 
                    : 'var(--accent)',
                color: (isDisabled || !password.trim()) && status !== 'success' 
                  ? 'var(--text-muted)' 
                  : 'white',
                fontWeight: 600,
                cursor: (isDisabled || !password.trim()) ? 'not-allowed' : 'pointer',
                transition: 'all 0.15s ease',
                minWidth: 100,
              }}
            >
              {status === 'success' ? '✓ Success' : status === 'submitting' ? 'Signing in…' : 'Sign in'}
            </button>
          </div>

          {error && (
            <div 
              style={{ 
                marginTop: 12, 
                padding: '10px 14px',
                borderRadius: 8,
                background: 'rgba(239, 83, 80, 0.1)',
                border: '1px solid rgba(239, 83, 80, 0.3)',
                color: '#ef5350', 
                fontSize: 13 
              }}
            >
              {error}
            </div>
          )}

          {status === 'success' && (
            <div 
              style={{ 
                marginTop: 12, 
                padding: '10px 14px',
                borderRadius: 8,
                background: 'rgba(34, 197, 94, 0.1)',
                border: '1px solid rgba(34, 197, 94, 0.3)',
                color: '#22c55e', 
                fontSize: 13 
              }}
            >
              Redirecting to dashboard...
            </div>
          )}
        </form>
      </div>
    </div>
  )
}
