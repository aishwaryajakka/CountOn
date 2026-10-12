import type { Metadata } from 'next';
import localFont from 'next/font/local';
import { AuthProvider } from '@/components/auth-provider';
import './globals.css';

const inter = localFont({ src: '../public/fonts/inter-variable.ttf', weight: '100 900', variable: '--font-inter', display: 'swap' });
const space = localFont({ src: '../public/fonts/space-grotesk-variable.ttf', weight: '300 700', variable: '--font-space', display: 'swap' });
export const metadata: Metadata = { title: { default: 'CountOn — Calm monitoring', template: '%s · CountOn' }, description: 'Know when reality stops matching what you expected. Calm monitoring. Clear signals.' };
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return <html lang="en" className={`${inter.variable} ${space.variable}`}><body><AuthProvider>{children}</AuthProvider></body></html>;
}
