'use client';
import { useEffect, useRef, type ReactNode } from 'react';
import Link from 'next/link';
import { AlertCircle, ArrowRight, Check, ShieldCheck, X, type LucideIcon } from 'lucide-react';
import { ApiError } from '@/lib/api';
import { statusLabels, type PresentationStatus } from '@/lib/presentation';

export function Logo({ light = false }: { light?: boolean }) {
  return <span className={`logo ${light ? 'light' : ''}`}><span className="logo-symbol" aria-hidden="true"><span /></span><span>Count<span className="logo-on">On</span></span></span>;
}
export function Badge({ status }: { status: PresentationStatus }) {
  return <span className={`badge ${status}`}><span aria-hidden="true" className="status-dot" />{statusLabels[status]}</span>;
}
export function IconBox({ icon: Icon, tone = 'blue' }: { icon: LucideIcon; tone?: string }) {
  return <span className={`icon-box ${tone}`}><Icon size={21} strokeWidth={1.7} aria-hidden="true" /></span>;
}
export function PageHeader({ eyebrow, title, description, action }: { eyebrow?: string; title: string; description: string; action?: ReactNode }) {
  return <header className="page-header"><div>{eyebrow && <div className="eyebrow"><span className="status-dot" />{eyebrow}</div>}<h1>{title}</h1><p>{description}</p></div>{action}</header>;
}
export function NewExpectationLink({ first = false }: { first?: boolean }) {
  return <Link className="button primary" href="/expectations/new"><span aria-hidden="true">+</span>{first ? 'Create your first expectation' : 'New expectation'}</Link>;
}
export function Loading({ label = 'Loading your workspace' }: { label?: string }) {
  return <div role="status" aria-live="polite" className="loading"><span className="sr-only">{label}</span><div className="skeleton short" /><div className="skeleton" /><div className="grid two"><div className="skeleton tall" /><div className="skeleton tall" /></div></div>;
}
export function EmptyState({ title, description, action, icon: Icon = ShieldCheck }: { title: string; description: string; action?: ReactNode; icon?: LucideIcon }) {
  return <div className="card empty-state"><Icon className="empty-icon" size={34} strokeWidth={1.5} aria-hidden="true" /><h2>{title}</h2><p>{description}</p>{action}</div>;
}
export function ErrorState({ error, retry }: { error: Error; retry?: () => void }) {
  const missing = error instanceof ApiError && (error.status === 404 || error.status === 422);
  return <div className="card error-state" role="alert"><AlertCircle size={26} aria-hidden="true" /><h2>{missing ? 'Expectation not found' : 'We couldn’t load this just now'}</h2><p>{missing ? 'It may have been removed, or it isn’t available to your account.' : error.message}</p>{error instanceof ApiError && error.requestId && <p className="caption">Request reference: {error.requestId}</p>}<div className="actions">{retry && !missing && <button className="button secondary" onClick={retry}>Try again</button>}<Link className="text-link" href="/dashboard">Back to Home <ArrowRight size={16} /></Link></div></div>;
}
export function Modal({ title, children, onClose }: { title: string; children: ReactNode; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    const previous = document.activeElement;
    dialog?.showModal();
    return () => { dialog?.close(); if (previous instanceof HTMLElement) previous.focus(); };
  }, []);
  return <dialog ref={ref} className="modal" aria-labelledby="modal-title" onCancel={event => { event.preventDefault(); onClose(); }} onClick={event => { if (event.target === event.currentTarget) onClose(); }}><div className="modal-body"><div className="section-heading"><h2 id="modal-title">{title}</h2><button className="icon-button" aria-label="Close dialog" onClick={onClose}><X size={20} /></button></div>{children}</div></dialog>;
}
export function QuietNote({ children }: { children: ReactNode }) {
  return <div className="quiet-note"><Check size={18} aria-hidden="true" /><p>{children}</p></div>;
}
