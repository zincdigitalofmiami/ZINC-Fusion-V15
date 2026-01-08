'use client'

import Link from 'next/link'
import Image from 'next/image'
import { usePathname, useRouter } from 'next/navigation'
import { useState } from 'react'

const navItems = [
  { href: '/dashboard', label: 'Dashboard' },
  { href: '/strategy', label: 'Strategy' },
  { href: '/legislation', label: 'Legislation' },
  { href: '/sentiment', label: 'Sentiment' },
  { href: '/vegas-intel', label: 'Vegas Intel' },
]

export default function Header() {
  const pathname = usePathname()
  const router = useRouter()
  const [loggingOut, setLoggingOut] = useState(false)

  // Don't show logout on login page or home page
  const showLogout = pathname !== '/login' && pathname !== '/'

  async function handleLogout() {
    if (loggingOut) return
    setLoggingOut(true)
    
    try {
      await fetch('/api/auth/logout', { 
        method: 'POST',
        credentials: 'same-origin'
      })
    } catch {
      // Even if the request fails, redirect to login
    }
    
    // Hard redirect to clear all state
    window.location.href = '/login'
  }

  return (
    <header className="header">
      <nav className="nav-container">
        <Link href="/" className="logo">
          <Image 
            src="/logo.svg" 
            alt="ZINC FUSION" 
            width={200} 
            height={50}
            priority
          />
        </Link>
        <ul className="nav-links">
          {navItems.map((item) => (
            <li key={item.href}>
              <Link
                href={item.href}
                className={pathname === item.href ? 'active' : ''}
              >
                {item.label}
              </Link>
            </li>
          ))}
          {showLogout && (
            <li>
              <button
                onClick={handleLogout}
                disabled={loggingOut}
                style={{
                  background: 'transparent',
                  border: 'none',
                  color: 'var(--text-muted)',
                  cursor: loggingOut ? 'not-allowed' : 'pointer',
                  padding: '8px 12px',
                  fontSize: 14,
                  fontFamily: 'inherit',
                  opacity: loggingOut ? 0.5 : 1,
                  transition: 'color 0.15s ease',
                }}
                onMouseEnter={(e) => e.currentTarget.style.color = 'var(--text)'}
                onMouseLeave={(e) => e.currentTarget.style.color = 'var(--text-muted)'}
              >
                {loggingOut ? 'Logging out...' : 'Logout'}
              </button>
            </li>
          )}
        </ul>
      </nav>
    </header>
  )
}
