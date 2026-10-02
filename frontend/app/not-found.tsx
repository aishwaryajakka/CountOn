import Link from 'next/link';
export default function NotFound() { return <main className="standalone card empty-state"><h1>This page isn’t here</h1><p>Let’s get you back to what you’re counting on.</p><Link className="button primary" href="/dashboard">Back to Home</Link></main>; }
