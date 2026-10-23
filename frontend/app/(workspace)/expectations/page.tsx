'use client';

import { useMemo, useState } from 'react';
import { useBoard } from '@/components/app-shell';
import { ExpectationCard } from '@/components/expectation';
import { ExpectationActionsModal } from '@/components/expectation-actions-modal';
import { EmptyState, ErrorState, Loading, NewExpectationLink, PageHeader } from '@/components/ui';
import type { Expectation, ExpectationType } from '@/lib/types';
import {
  getExpectationPresentationStatus,
  statusLabels,
  type PresentationStatus,
} from '@/lib/presentation';
import { ArrowUpDown, RotateCcw, Search, X } from 'lucide-react';

const mainFilters: { value: 'all' | PresentationStatus; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'attention', label: 'Attention' },
  { value: 'monitoring', label: 'Monitoring' },
  { value: 'match', label: 'Matched' },
  { value: 'waiting', label: 'Waiting' },
  { value: 'resolved', label: 'Resolved' },
];

type SortOption = 'newest' | 'attention' | 'deadline' | 'evaluated';

export default function Expectations() {
  const board = useBoard();
  const [filter, setFilter] = useState<'all' | PresentationStatus>('all');
  const [search, setSearch] = useState('');
  const [sourceFilter, setSourceFilter] = useState('all');
  const [typeFilter, setTypeFilter] = useState<'all' | ExpectationType>('all');
  const [deadlineFilter, setDeadlineFilter] = useState<'all' | 'has_deadline' | 'no_deadline'>('all');
  const [sort, setSort] = useState<SortOption>('newest');
  const [managingExp, setManagingExp] = useState<Expectation | null>(null);

  const rows = useMemo(() => board.data ?? [], [board.data]);

  // Comprehensive Filtering
  const filtered = useMemo(() => {
    return rows.filter((row) => {
      const exp = row.expectation;
      const status = getExpectationPresentationStatus(exp, row.latest);

      // Status filter
      if (filter !== 'all' && status !== filter) return false;

      // Search filter (claim, metric, sources)
      if (search.trim()) {
        const query = search.trim().toLowerCase();
        const matchesClaim = exp.claim.toLowerCase().includes(query);
        const matchesMetric = (exp.metric ?? '').toLowerCase().includes(query);
        const matchesSource = exp.evidence_sources.some((s) => s.toLowerCase().includes(query));
        if (!matchesClaim && !matchesMetric && !matchesSource) return false;
      }

      // Source filter
      if (sourceFilter !== 'all') {
        const matches = exp.evidence_sources.some((s) => {
          const lower = s.toLowerCase();
          if (sourceFilter === 'utility') return lower.includes('utility') || lower.includes('electric');
          if (sourceFilter === 'ring') return lower.includes('ring') || lower.includes('camera');
          if (sourceFilter === 'bee') return lower.includes('bee') || lower.includes('wearable');
          if (sourceFilter === 'google') return lower.includes('google') || lower.includes('gmail');
          if (sourceFilter === 'microsoft') return lower.includes('microsoft') || lower.includes('outlook');
          if (sourceFilter === 'delivery') return lower.includes('delivery') || lower.includes('package');
          return lower.includes(sourceFilter);
        });
        if (!matches) return false;
      }

      // Type filter
      if (typeFilter !== 'all' && exp.type !== typeFilter) return false;

      // Deadline filter
      if (deadlineFilter === 'has_deadline' && !exp.deadline) return false;
      if (deadlineFilter === 'no_deadline' && exp.deadline) return false;

      return true;
    });
  }, [rows, filter, search, sourceFilter, typeFilter, deadlineFilter]);

  // Sorting
  const sorted = useMemo(() => {
    const list = [...filtered];
    list.sort((a, b) => {
      if (sort === 'attention') {
        const statusA = getExpectationPresentationStatus(a.expectation, a.latest);
        const statusB = getExpectationPresentationStatus(b.expectation, b.latest);
        if (statusA === 'attention' && statusB !== 'attention') return -1;
        if (statusA !== 'attention' && statusB === 'attention') return 1;
        return Date.parse(b.expectation.created_at) - Date.parse(a.expectation.created_at);
      }
      if (sort === 'deadline') {
        if (!a.expectation.deadline && !b.expectation.deadline) return 0;
        if (!a.expectation.deadline) return 1;
        if (!b.expectation.deadline) return -1;
        return Date.parse(a.expectation.deadline) - Date.parse(b.expectation.deadline);
      }
      if (sort === 'evaluated') {
        const timeA = a.latest ? Date.parse(a.latest.created_at) : 0;
        const timeB = b.latest ? Date.parse(b.latest.created_at) : 0;
        return timeB - timeA;
      }
      // 'newest' default
      return Date.parse(b.expectation.created_at) - Date.parse(a.expectation.created_at);
    });
    return list;
  }, [filtered, sort]);

  function resetFilters() {
    setFilter('all');
    setSearch('');
    setSourceFilter('all');
    setTypeFilter('all');
    setDeadlineFilter('all');
    setSort('newest');
  }

  const hasActiveFilters =
    filter !== 'all' ||
    search.trim() !== '' ||
    sourceFilter !== 'all' ||
    typeFilter !== 'all' ||
    deadlineFilter !== 'all';

  return (
    <>
      <PageHeader
        eyebrow="Monitoring Center"
        title="What you're counting on"
        description="Clear signals from real evidence. Matched expectations stay quiet; mismatches get attention."
        action={<NewExpectationLink />}
      />

      {/* Main Status Filter Tabs */}
      <div className="filters" aria-label="Filter expectations by status" style={{ marginBottom: '1rem' }}>
        {mainFilters.map((item) => {
          const count =
            item.value === 'all'
              ? rows.length
              : rows.filter((row) => getExpectationPresentationStatus(row.expectation, row.latest) === item.value)
                  .length;

          return (
            <button
              className={`filter ${filter === item.value ? 'selected' : ''}`}
              key={item.value}
              onClick={() => setFilter(item.value)}
              aria-pressed={filter === item.value}
            >
              {item.label}
              <span>{count}</span>
            </button>
          );
        })}
      </div>

      {/* Search & Filter Controls Bar */}
      <div
        className="card"
        style={{
          padding: '1rem',
          marginBottom: '1.5rem',
          backgroundColor: 'var(--color-bg-surface, #ffffff)',
          border: '1px solid var(--color-border, #e6ebf2)',
        }}
      >
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '0.75rem', alignItems: 'center' }}>
          {/* Search Input */}
          <div style={{ position: 'relative', width: '100%' }}>
            <Search
              size={16}
              style={{
                position: 'absolute',
                left: '10px',
                top: '50%',
                transform: 'translateY(-50%)',
                color: 'var(--color-text-secondary, #667085)',
              }}
            />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search expectations, metrics, sources…"
              style={{
                width: '100%',
                paddingLeft: '32px',
                paddingRight: search ? '28px' : '10px',
                paddingTop: '0.5rem',
                paddingBottom: '0.5rem',
                borderRadius: '8px',
                border: '1px solid var(--color-control-border, #d9e0e9)',
                fontSize: '0.875rem',
              }}
            />
            {search && (
              <button
                type="button"
                onClick={() => setSearch('')}
                aria-label="Clear search"
                style={{
                  position: 'absolute',
                  right: '8px',
                  top: '50%',
                  transform: 'translateY(-50%)',
                  background: 'transparent',
                  border: 0,
                  cursor: 'pointer',
                  color: 'var(--color-text-secondary, #667085)',
                }}
              >
                <X size={14} />
              </button>
            )}
          </div>

          {/* Source/Provider Filter */}
          <div>
            <select
              aria-label="Filter by provider"
              value={sourceFilter}
              onChange={(e) => setSourceFilter(e.target.value)}
              style={{
                width: '100%',
                padding: '0.5rem',
                borderRadius: '8px',
                border: '1px solid var(--color-control-border, #d9e0e9)',
                fontSize: '0.875rem',
              }}
            >
              <option value="all">All sources</option>
              <option value="utility">Utility (Electricity/Gas)</option>
              <option value="ring">Ring (Camera/Doorbell · SIMULATED)</option>
              <option value="bee">Bee (Wearable · SIMULATED)</option>
              <option value="google">Google / Gmail</option>
              <option value="microsoft">Microsoft / Outlook</option>
              <option value="delivery">Delivery / Carrier</option>
            </select>
          </div>

          {/* Type Filter */}
          <div>
            <select
              aria-label="Filter by check type"
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value as 'all' | ExpectationType)}
              style={{
                width: '100%',
                padding: '0.5rem',
                borderRadius: '8px',
                border: '1px solid var(--color-control-border, #d9e0e9)',
                fontSize: '0.875rem',
              }}
            >
              <option value="all">All check types</option>
              <option value="numeric_comparison">Numeric comparison</option>
              <option value="boolean">Boolean confirmation</option>
              <option value="temporal">Temporal deadline</option>
              <option value="event">Event check</option>
            </select>
          </div>

          {/* Deadline Filter */}
          <div>
            <select
              aria-label="Filter by deadline"
              value={deadlineFilter}
              onChange={(e) => setDeadlineFilter(e.target.value as 'all' | 'has_deadline' | 'no_deadline')}
              style={{
                width: '100%',
                padding: '0.5rem',
                borderRadius: '8px',
                border: '1px solid var(--color-control-border, #d9e0e9)',
                fontSize: '0.875rem',
              }}
            >
              <option value="all">All deadlines</option>
              <option value="has_deadline">Has deadline</option>
              <option value="no_deadline">No deadline</option>
            </select>
          </div>

          {/* Sort Dropdown */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
            <ArrowUpDown size={15} color="var(--color-text-secondary, #667085)" />
            <select
              aria-label="Sort expectations"
              value={sort}
              onChange={(e) => setSort(e.target.value as SortOption)}
              style={{
                width: '100%',
                padding: '0.5rem',
                borderRadius: '8px',
                border: '1px solid var(--color-control-border, #d9e0e9)',
                fontSize: '0.875rem',
                fontWeight: 500,
              }}
            >
              <option value="newest">Sort: Newest</option>
              <option value="attention">Sort: Attention First</option>
              <option value="deadline">Sort: Deadline</option>
              <option value="evaluated">Sort: Recently Evaluated</option>
            </select>
          </div>
        </div>

        {hasActiveFilters && (
          <div style={{ marginTop: '0.75rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span className="caption">
              Showing {sorted.length} of {rows.length} expectations
            </span>
            <button
              className="text-link"
              onClick={resetFilters}
              style={{ fontSize: '0.8rem', display: 'inline-flex', alignItems: 'center', gap: '0.3rem' }}
            >
              <RotateCcw size={13} />
              Reset filters
            </button>
          </div>
        )}
      </div>

      {/* Main Content Area */}
      {board.loading ? (
        <Loading />
      ) : board.error ? (
        <ErrorState error={board.error} retry={board.reload} />
      ) : !rows.length ? (
        <EmptyState
          title="You’re not counting on anything yet."
          description="Start with one thing you’d like a little more clarity on."
          action={<NewExpectationLink first />}
        />
      ) : !sorted.length ? (
        <EmptyState
          title="No matching expectations."
          description="None of your expectations match the selected filters or search query."
          action={
            <button className="button secondary" onClick={resetFilters}>
              Clear filters & search
            </button>
          }
        />
      ) : (
        <>
          {(
            ['attention', 'monitoring', 'match', 'waiting', 'resolved', 'cancelled'] as PresentationStatus[]
          ).map((status) => {
            const items = sorted.filter(
              (row) => getExpectationPresentationStatus(row.expectation, row.latest) === status
            );
            return items.length ? (
              <section className="section expectation-group" key={status}>
                <div className="section-heading">
                  <h2>
                    <span className={`group-dot ${status}`} />
                    {statusLabels[status]}
                  </h2>
                  <span className="caption">
                    {items.length} expectation{items.length === 1 ? '' : 's'}
                  </span>
                </div>
                <div className="grid two">
                  {items.map((row) => (
                    <ExpectationCard
                      key={row.expectation.id}
                      row={row}
                      onManage={(exp) => setManagingExp(exp)}
                    />
                  ))}
                </div>
              </section>
            ) : null;
          })}
        </>
      )}

      {/* Expectation Actions Modal */}
      {managingExp && (
        <ExpectationActionsModal
          expectation={managingExp}
          isOpen={!!managingExp}
          onClose={() => setManagingExp(null)}
          onUpdated={() => board.reload()}
        />
      )}
    </>
  );
}
