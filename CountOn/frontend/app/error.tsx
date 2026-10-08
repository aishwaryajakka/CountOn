'use client';
import { ErrorState } from '@/components/ui';
export default function PageError({ reset }: { error: Error & { digest?: string }; reset: () => void }) { return <main className="standalone"><ErrorState error={new Error('Something interrupted this page. Please try again.')} retry={reset} /></main>; }
