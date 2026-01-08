'use client'

import { useState, type FormEvent } from 'react'

export default function LoginPage() {
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setIsSubmitting(true)

    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password }),
        credentials: 'same-origin', // Ensure cookies are included
      })

      const data = await res.json().catch(() => ({ ok: false, error: 'Invalid response' }))

      if (!res.ok || !data.ok) {
        setError(data.error || 'Login failed')
        setPassword('') // Clear password on error
        setIsSubmitting(false)
        return
      }

      // Success - use hard redirect to ensure middleware sees the new cookie
      const nextPath = new URLSearchParams(window.location.search).get('next')
      const destination = nextPath && nextPath.startsWith('/') ? nextPath : '/dashboard'
      
      // Hard redirect ensures fresh request with new cookie
      window.location.href = destination
    } catch (err) {
      setError('Network error. Please try again.')
      setIsSubmitting(false)
    }
  }

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
              disabled={isSubmitting}
              style={{
                flex: 1,
                padding: '12px 14px',
                borderRadius: 10,
                border: '1px solid var(--border)',
                background: 'var(--surface-2)',
                color: 'var(--text)',
                outline: 'none',
                opacity: isSubmitting ? 0.7 : 1,
              }}
            />
            <button
              type="submit"
              disabled={isSubmitting || !password.trim()}
              style={{
                padding: '12px 20px',
                borderRadius: 10,
                border: 'none',
                background: isSubmitting || !password.trim() ? 'var(--surface-3)' : 'var(--accent)',
                color: isSubmitting || !password.trim() ? 'var(--text-muted)' : 'white',
                fontWeight: 600,
                cursor: isSubmitting || !password.trim() ? 'not-allowed' : 'pointer',
                transition: 'all 0.15s ease',
              }}
            >
              {isSubmitting ? 'Signing in…' : 'Sign in'}
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
        </form>
      </div>
    </div>
  )
}
