'use client'

import Link from 'next/link'
import Image from 'next/image'
import { usePathname, useRouter } from 'next/navigation'
import { useState } from 'react'
import { Menu } from 'lucide-react'
import { QuantAdminSidebar } from './layout/QuantAdminSidebar'

const navItems = [
  { href: '/dashboard', label: 'Dashboard' },
  { href: '/quant', label: 'Quant' },
  { href: '/strategy', label: 'Strategy' },
  { href: '/legislation', label: 'Legislation' },
  { href: '/sentiment', label: 'Sentiment' },
  { href: '/vegas-intel', label: 'Vegas Intel' },
]

export default function Header() {
  const pathname = usePathname()
  const router = useRouter()
  const [loggingOut, setLoggingOut] = useState(false)
  const [isAdminOpen, setIsAdminOpen] = useState(false)

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
    <>
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
                  onClick={() => setIsAdminOpen(true)}
                  className="flex items-center gap-2 px-3 py-2 text-slate-400 hover:text-white transition-colors rounded-lg hover:bg-white/5"
                  aria-label="Open Admin Menu"
                >
                  <Menu size={20} />
                </button>
              </li>
            )}
          </ul>
        </nav>
      </header>

      <QuantAdminSidebar 
        isOpen={isAdminOpen} 
        onClose={() => setIsAdminOpen(false)}
        onLogout={handleLogout}
      />
    </>
  )
}
