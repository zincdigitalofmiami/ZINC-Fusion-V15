'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'

const navItems = [
  { href: '/', label: 'Home', icon: '🏠' },
  { href: '/dashboard', label: 'Dashboard', icon: '📊' },
  { href: '/strategy', label: 'Strategy', icon: '🎯' },
  { href: '/legislation', label: 'Legislation', icon: '📜' },
  { href: '/sentiment', label: 'Sentiment', icon: '📈' },
  { href: '/vegas-intel', label: 'Vegas Intel', icon: '🎰' },
]

export default function Sidebar() {
  const pathname = usePathname()

  return (
    <aside className="sidebar">
      <div className="logo">
        <div className="logo-text">ZINC FUSION</div>
        <div className="logo-sub">V15 • Procurement Intelligence</div>
      </div>
      
      <nav className="nav-section">
        <div className="nav-label">Navigation</div>
        {navItems.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={`nav-item ${pathname === item.href ? 'active' : ''}`}
          >
            <span className="nav-icon">{item.icon}</span>
            {item.label}
          </Link>
        ))}
      </nav>
    </aside>
  )
}
