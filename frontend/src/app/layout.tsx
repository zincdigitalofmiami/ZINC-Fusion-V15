import type { Metadata } from 'next';
import type { ReactNode } from 'react';
import { Inter } from 'next/font/google';
import localFont from 'next/font/local';
import './globals.css';
import StatusBar from '@/components/StatusBar';
import Header from '@/components/Header';

// Fallback font (Inter)
const inter = Inter({ 
  subsets: ['latin'],
  display: 'swap',
  variable: '--font-inter',
});

// Primary font: Tasa Orbiter (load locally if available, fallback to Inter)
// To use Tasa Orbiter, add the font files to public/fonts/ and uncomment below:
// const tasaOrbiter = localFont({
//   src: [
//     { path: '../../public/fonts/TasaOrbiter-Regular.woff2', weight: '400' },
//     { path: '../../public/fonts/TasaOrbiter-Medium.woff2', weight: '500' },
//     { path: '../../public/fonts/TasaOrbiter-Bold.woff2', weight: '700' },
//   ],
//   variable: '--font-sans',
//   display: 'swap',
// });

export const metadata: Metadata = {
  title: 'ZINC Fusion V15',
  description: 'Institutional-Grade Commodity Intelligence',
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={`dark ${inter.variable}`} suppressHydrationWarning>
      <body className="bg-background text-foreground antialiased">
        <StatusBar />
        <Header />
        {children}
      </body>
    </html>
  );
}
