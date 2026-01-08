'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'

const navItems = [
  { href: '/dashboard', label: 'Dashboard' },
  { href: '/strategy', label: 'Strategy' },
  { href: '/legislation', label: 'Legislation' },
  { href: '/sentiment', label: 'Sentiment' },
  { href: '/vegas-intel', label: 'Vegas Intel' },
]

export default function Header() {
  const pathname = usePathname()

  return (
    <header className="header">
      <nav className="nav-container">
        <Link href="/" className="logo">
          ZINC FUSION
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
        </ul>
      </nav>
    </header>
  )
}
