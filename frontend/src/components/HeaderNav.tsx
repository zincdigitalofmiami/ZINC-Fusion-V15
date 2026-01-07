'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

const navItems = [
  { label: 'Home', path: '/' },
  { label: 'Dashboard', path: '/dashboard' },
  { label: 'Strategy', path: '/strategy' },
  { label: 'Legislation', path: '/legislation' },
  { label: 'Sentiment', path: '/sentiment' },
  { label: 'Vegas Intel', path: '/vegas-intel' },
];

export default function HeaderNav() {
  const pathname = usePathname();

  return (
    <header className="header">
      <div className="nav-container">
        <Link href="/" className="text-2xl font-bold text-text-strong no-underline">
          ZINC Fusion V15
        </Link>
        <nav className="nav-links">
          {navItems.map((item) => (
            <Link
              key={item.path}
              href={item.path}
              className={pathname === item.path ? 'active' : ''}
            >
              {item.label}
            </Link>
          ))}
        </nav>
      </div>
    </header>
  );
}
