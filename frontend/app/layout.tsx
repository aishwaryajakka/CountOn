import type { Metadata } from 'next';
import { Inter, Space_Grotesk } from 'next/font/google';
import { AuthProvider } from '@/components/auth-provider';
import './globals.css';

const inter = Inter({ subsets: ['latin'], variable: '--font-inter', display: 'swap' });
const space = Space_Grotesk({ subsets: ['latin'], variable: '--font-space', display: 'swap' });
export const metadata: Metadata = { title: { default: 'CountOn — Calm monitoring', template: '%s · CountOn' }, description: 'Know when reality stops matching what you expected. Calm monitoring. Clear signals.' };
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return <html lang="en" className={`${inter.variable} ${space.variable}`}><body><AuthProvider>{children}</AuthProvider></body></html>;
}
