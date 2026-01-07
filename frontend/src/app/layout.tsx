import type { Metadata } from 'next';
import type { ReactNode } from 'react';
import './globals.css';
import StatusBar from '@/components/StatusBar';
import HeaderNav from '@/components/HeaderNav';

export const metadata: Metadata = {
  title: 'ZINC Fusion V15',
  description: 'Institutional-Grade Commodity Intelligence',
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <StatusBar />
        <HeaderNav />
        <main className="container">{children}</main>
      </body>
    </html>
  );
}
