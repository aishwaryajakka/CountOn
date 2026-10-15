import type { NextConfig } from 'next';
const config: NextConfig = { poweredByHeader: false, turbopack: { root: process.cwd() }, async headers() { return [{ source: '/auth/:path*', headers: [ { key: 'Cache-Control', value: 'no-store' }, { key: 'Referrer-Policy', value: 'no-referrer' }, { key: 'X-Frame-Options', value: 'DENY' }, { key: 'Content-Security-Policy', value: "frame-ancestors 'none'" } ] }, { source: '/oauth/consent', headers: [
  { key: 'Cache-Control', value: 'no-store' },
  { key: 'Referrer-Policy', value: 'no-referrer' },
  { key: 'Content-Security-Policy', value: "frame-ancestors 'none'" },
  { key: 'X-Frame-Options', value: 'DENY' },
] }]; }, allowedDevOrigins: ['127.0.0.1', 'localhost'] };
export default config;
