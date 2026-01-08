'use client'

import { useRouter } from 'next/navigation'
import { useState, type FormEvent } from 'react'

export default function LoginPage() {
  const router = useRouter()
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
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ password }),
      })

      if (!res.ok) {
        let message = 'Login failed'

        const data: unknown = await res.json().catch(() => null)
        if (data && typeof data === 'object') {
          const record = data as Record<string, unknown>
          if (typeof record.error === 'string' && record.error.trim().length > 0) {
            message = record.error
          }
        }

        setError(message)
        return
      }

      const nextPath = new URLSearchParams(window.location.search).get('next')
      router.replace(nextPath && nextPath.startsWith('/') ? nextPath : '/dashboard')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="main-content" style={{ maxWidth: 520, margin: '0 auto', paddingTop: 80 }}>
      <div className="card" style={{ marginTop: 40 }}>
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
              style={{
                flex: 1,
                padding: '12px 14px',
                borderRadius: 10,
                border: '1px solid var(--border)',
                background: 'var(--surface-2)',
                color: 'var(--text)',
                outline: 'none',
              }}
            />
            <button
              type="submit"
              disabled={isSubmitting}
              style={{
                padding: '12px 14px',
                borderRadius: 10,
                border: '1px solid var(--border-strong)',
                background: 'var(--accent)',
                color: 'var(--text-strong)',
                fontWeight: 700,
                cursor: isSubmitting ? 'not-allowed' : 'pointer',
                opacity: isSubmitting ? 0.7 : 1,
              }}
            >
              {isSubmitting ? 'Signing in…' : 'Sign in'}
            </button>
          </div>

          {error ? (
            <div style={{ marginTop: 12, color: 'var(--down)', fontSize: 13 }}>{error}</div>
          ) : null}
        </form>
      </div>
    </div>
  )
}
