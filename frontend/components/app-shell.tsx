'use client';
import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import Image from 'next/image';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { Bell, Clock3, Home, Link2, ListChecks, LogOut, Menu, Settings, X } from 'lucide-react';
import { useAuth, useIdentity } from './auth-provider';
import { getSupabase } from '@/lib/supabase';
import { api } from '@/lib/api';
import { useResource } from '@/hooks/use-resource';
import { Loading, Logo } from './ui';

const loadBoard = (signal: AbortSignal) => api.board(signal);
type BoardState = ReturnType<typeof useResource<Awaited<ReturnType<typeof loadBoard>>>>;
const BoardContext = createContext<BoardState | null>(null);
export function useBoard() { const state = useContext(BoardContext); if (!state) throw new Error('Workspace provider required'); return state; }
const navigation = [{ href: '/dashboard', label: 'Home', icon: Home }, { href: '/expectations', label: 'Expectations', icon: ListChecks }, { href: '/integrations', label: 'Connected Accounts', icon: Link2 }, { href: '/notifications', label: 'Notifications', icon: Bell }, { href: '/activity', label: 'Activity', icon: Clock3 }];
export function Avatar() {
  const { name, email } = useIdentity();
  return email?.toLowerCase() === 'demo@counton.app' ? <Image src="/ashley-reference.png" width={38} height={38} sizes="38px" alt="Ashley’s demo portrait" className="avatar" /> : <span className="avatar initials" aria-hidden="true">{name.slice(0, 1).toUpperCase()}</span>;
}
function Workspace({ children }: { children: ReactNode }) {
  const board = useResource(loadBoard);
  const pathname = usePathname();
  const { name } = useIdentity();
  const [open, setOpen] = useState(false);
  const [signoutError, setSignoutError] = useState<string | null>(null);
  const [signingOut, setSigningOut] = useState(false);
  const sidebar = useRef<HTMLElement>(null);
  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const controls = () => Array.from(sidebar.current?.querySelectorAll<HTMLElement>('a[href], button:not(:disabled)') ?? []).filter(element => element.getClientRects().length > 0);
    controls()[0]?.focus();
    const trapFocus = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { setOpen(false); return; }
      if (event.key !== 'Tab') return;
      const elements = controls(); const first = elements[0]; const last = elements.at(-1);
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    };
    document.addEventListener('keydown', trapFocus);
    return () => { document.removeEventListener('keydown', trapFocus); document.body.style.overflow = overflow; if (previous instanceof HTMLElement) previous.focus(); };
  }, [open]);
  const active = (href: string) => pathname === href || (href === '/expectations' && pathname.startsWith('/expectations/'));
  async function signOut() {
    setSigningOut(true); setSignoutError(null);
    const { error } = await getSupabase().auth.signOut({ scope: 'local' });
    if (error) { setSignoutError('Couldn’t sign out. Please try again.'); setSigningOut(false); }
  }
  return <BoardContext.Provider value={board}><a className="skip-link" href="#main-content" tabIndex={open ? -1 : undefined} aria-hidden={open || undefined}>Skip to content</a><div className="app-shell">{open && <button className="drawer-backdrop" tabIndex={-1} aria-hidden="true" onClick={() => setOpen(false)} />}
    <aside ref={sidebar} className={`sidebar ${open ? 'is-open' : ''}`} role={open ? 'dialog' : undefined} aria-modal={open ? true : undefined} aria-label="Main navigation"><div className="sidebar-brand"><Link href="/dashboard" aria-label="CountOn Home" onClick={() => setOpen(false)}><Logo /></Link><button className="icon-button mobile-only" aria-label="Close navigation" onClick={() => setOpen(false)}><X size={22} /></button></div>
      <nav>{navigation.map(({ href, label, icon: Icon }) => <Link key={href} href={href} className={`nav-link ${active(href) ? 'active' : ''}`} aria-current={active(href) ? 'page' : undefined} onClick={() => setOpen(false)}><Icon size={19} strokeWidth={1.7} /><span>{label}</span>{href === '/expectations' && board.data && <span className="nav-count">{board.data.length}</span>}</Link>)}</nav>
      <div className="sidebar-bottom"><Link className={`nav-link ${active('/settings') ? 'active' : ''}`} href="/settings" onClick={() => setOpen(false)}><Settings size={19} />Profile / Settings</Link><div className="account-strip"><Avatar /><div><strong>{name}</strong><span>Your personal workspace</span></div><button className="icon-button" onClick={signOut} disabled={signingOut} aria-label="Sign out"><LogOut size={18} /></button></div>{signoutError && <p role="alert" className="inline-error">{signoutError}</p>}</div>
    </aside>
    <div className="workspace" inert={open}><header className="topbar"><div className="topbar-left"><button className="icon-button mobile-only" aria-label="Open navigation" aria-expanded={open} onClick={() => setOpen(true)}><Menu size={22} /></button><span className="topbar-title">{navigation.find(item => active(item.href))?.label ?? 'Your workspace'}</span></div><div className="topbar-right"><span className="workspace-pill"><span className="status-dot" />Calm monitoring</span><Link href="/settings" aria-label="Your profile"><Avatar /></Link></div></header><main id="main-content" className="page-content" tabIndex={-1}>{children}</main><footer className="app-footer">Calm monitoring. Clear signals.<span>CountOn</span></footer></div>
  </div></BoardContext.Provider>;
}
export function AppShell({ children }: { children: ReactNode }) {
  const { loading, session, error } = useAuth();
  const router = useRouter();
  useEffect(() => { if (!loading && !session) router.replace('/login'); }, [loading, session, router]);
  if (loading || !session) return <div className="auth-loading"><Logo /><Loading label={error ?? 'Restoring your session'} /></div>;
  return <Workspace key={session.user.id}>{children}</Workspace>;
}
