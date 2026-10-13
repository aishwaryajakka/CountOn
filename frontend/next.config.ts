import type { NextConfig } from 'next';
const config: NextConfig = { poweredByHeader: false, turbopack: { root: process.cwd() }, allowedDevOrigins: ['127.0.0.1', 'localhost'] };
export default config;
