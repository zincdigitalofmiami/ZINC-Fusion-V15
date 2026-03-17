'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import Image from 'next/image'
import { usePathname } from 'next/navigation'

const navItems = [
  { href: '/dashboard', label: 'DASHBOARD' },
  { href: '/strategy', label: 'STRATEGY' },
  { href: '/legislation', label: 'LEGISLATION' },
  { href: '/sentiment', label: 'SENTIMENT' },
  { href: '/vegas-intel', label: 'VEGAS INTEL' },
]

export default function Header() {
  const pathname = usePathname()
  const [mobileOpen, setMobileOpen] = useState(false)

  // Close mobile menu on route change
  useEffect(() => {
    setMobileOpen(false)
  }, [pathname])

  return (
    <header className="header">
      <nav className="nav-container">
        <Link href="/" className="logo">
          <Image
            src="/logo.svg"
            alt="USO Fusion"
            width={250}
            height={50}
            priority
          />
        </Link>

        {/* Hamburger — visible below 768px only */}
        <button
          className="md:hidden"
          onClick={() => setMobileOpen((prev) => !prev)}
          aria-label="Toggle navigation"
          style={{
            background: 'none',
            border: 'none',
            color: '#fff',
            fontSize: '24px',
            cursor: 'pointer',
            padding: '4px 8px',
            lineHeight: 1,
          }}
        >
          {mobileOpen ? '✕' : '☰'}
        </button>

        <ul className={`nav-links${mobileOpen ? ' mobile-open' : ''}`}>
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
        </ul>
      </nav>
    </header>
  )
}
