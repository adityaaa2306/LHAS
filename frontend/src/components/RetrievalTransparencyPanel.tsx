import React, { useState } from 'react';
import { ChevronDown, ChevronRight, Search, Shield, Target, Zap } from 'lucide-react';
import type { RetrievalPlanStats } from '@/types/ingestion';

interface RetrievalTransparencyPanelProps {
  plan: RetrievalPlanStats | null | undefined;
}

function ScoreBadge({ value, label }: { value: number; label: string }) {
  const pct = Math.round(value * 100);
  const color =
    pct >= 70 ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
    : pct >= 40 ? 'bg-amber-50 text-amber-700 border-amber-200'
    : 'bg-red-50 text-red-700 border-red-200';
  return (
    <div className={`rounded-lg border px-3 py-2 text-center ${color}`}>
      <p className="text-lg font-semibold tabular-nums">{pct}%</p>
      <p className="text-[10px] font-medium uppercase tracking-wide opacity-80">{label}</p>
    </div>
  );
}

export const RetrievalTransparencyPanel: React.FC<RetrievalTransparencyPanelProps> = ({ plan }) => {
  const [expanded, setExpanded] = useState(true);
  const [showQueries, setShowQueries] = useState(false);
  const [showRejected, setShowRejected] = useState(false);

  if (!plan?.plan) return null;

  const inner = plan.plan;
  const entities = inner.entities ?? [];
  const searches = inner.searches ?? [];
  const executions = plan.executions ?? [];
  const rejected = plan.rejected_papers ?? [];
  const coverage = plan.coverage;

  return (
    <div className="border-b border-neutral-100 px-5 py-4">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center gap-2 text-left"
      >
        {expanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
        <Search size={14} className="text-blue-600" />
        <h3 className="text-xs font-semibold uppercase tracking-wide text-neutral-500">
          Retrieval reasoning
        </h3>
        <span className="ml-auto text-xs text-neutral-400">
          {plan.queries_executed ?? executions.length} searches
        </span>
      </button>

      {expanded && (
        <div className="mt-3 space-y-4">
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <ScoreBadge value={plan.confidence_score ?? 0} label="Confidence" />
            <ScoreBadge value={coverage?.coverage_score ?? 0} label="Coverage" />
            <div className="rounded-lg border border-neutral-100 bg-neutral-50 px-3 py-2 text-center">
              <p className="text-lg font-semibold tabular-nums">{plan.after_qc ?? plan.total_candidates ?? 0}</p>
              <p className="text-[10px] font-medium uppercase tracking-wide text-neutral-500">After QC</p>
            </div>
            <div className="rounded-lg border border-neutral-100 bg-neutral-50 px-3 py-2 text-center">
              <p className="text-lg font-semibold tabular-nums text-red-600">{plan.rejected_count ?? rejected.length}</p>
              <p className="text-[10px] font-medium uppercase tracking-wide text-neutral-500">Rejected</p>
            </div>
          </div>

          {entities.length > 0 && (
            <div>
              <div className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold text-neutral-600">
                <Target size={12} /> Detected entities
              </div>
              <div className="flex flex-wrap gap-1.5">
                {entities.map((e) => (
                  <span
                    key={e.name}
                    className="rounded-full border border-blue-100 bg-blue-50 px-2 py-0.5 text-[11px] text-blue-800"
                    title={e.drug_class ? `Class: ${e.drug_class}` : e.entity_type}
                  >
                    {e.canonical_names?.[0] || e.name}
                    {e.drug_class && (
                      <span className="ml-1 text-blue-500">({e.drug_class})</span>
                    )}
                  </span>
                ))}
              </div>
            </div>
          )}

          {inner.intent?.research_goals && inner.intent.research_goals.length > 0 && (
            <div>
              <div className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold text-neutral-600">
                <Zap size={12} /> Research intent
              </div>
              <div className="flex flex-wrap gap-1">
                {inner.intent.research_goals.slice(0, 8).map((g) => (
                  <span key={g} className="rounded bg-neutral-100 px-1.5 py-0.5 text-[10px] text-neutral-600">
                    {g}
                  </span>
                ))}
              </div>
            </div>
          )}

          {Object.keys(plan.source_counts ?? {}).length > 0 && (
            <div>
              <div className="mb-1.5 text-xs font-semibold text-neutral-600">Papers per source</div>
              <div className="flex flex-wrap gap-1.5">
                {Object.entries(plan.source_counts ?? {}).map(([src, count]) => (
                  <span key={src} className="rounded-full bg-neutral-100 px-2 py-0.5 text-[10px] font-medium text-neutral-600">
                    {src}: {count}
                  </span>
                ))}
              </div>
            </div>
          )}

          <div>
            <button
              type="button"
              onClick={() => setShowQueries((v) => !v)}
              className="flex items-center gap-1 text-xs font-semibold text-neutral-600 hover:text-neutral-900"
            >
              {showQueries ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
              Search strategies ({searches.length} planned, {executions.length} executed)
            </button>
            {showQueries && (
              <ul className="mt-2 max-h-40 space-y-1 overflow-y-auto rounded-lg border border-neutral-100 bg-neutral-50/80 p-2">
                {(executions.length ? executions : searches).slice(0, 30).map((item, i) => (
                  <li key={i} className="text-[11px] text-neutral-700">
                    <span className="font-medium text-neutral-500">
                      {'source' in item ? item.source : (item as { source: string }).source}
                    </span>
                    {' · '}
                    <span className="text-neutral-400">
                      {'strategy' in item ? item.strategy : ''}
                    </span>
                    {'papers_found' in item && item.papers_found !== undefined && (
                      <span className="ml-1 text-emerald-600">+{item.papers_found}</span>
                    )}
                    <p className="truncate text-neutral-600">
                      {'query' in item ? item.query : ''}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {rejected.length > 0 && (
            <div>
              <button
                type="button"
                onClick={() => setShowRejected((v) => !v)}
                className="flex items-center gap-1 text-xs font-semibold text-neutral-600 hover:text-neutral-900"
              >
                {showRejected ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                <Shield size={12} className="text-red-400" />
                Rejected irrelevant ({plan.rejected_count ?? rejected.length})
              </button>
              {showRejected && (
                <ul className="mt-2 max-h-28 space-y-1 overflow-y-auto rounded-lg border border-red-100 bg-red-50/50 p-2">
                  {rejected.slice(0, 15).map((r) => (
                    <li key={r.paper_id} className="text-[11px]">
                      <p className="truncate font-medium text-neutral-700">{r.title}</p>
                      <p className="text-red-600">{r.reason}</p>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {coverage?.dimensions_missing && coverage.dimensions_missing.length > 0 && (
            <p className="text-[11px] text-amber-700">
              Coverage gaps filled: {coverage.dimensions_missing.join(', ')}
              {coverage.gap_fill_searches ? ` (${coverage.gap_fill_searches} extra searches)` : ''}
            </p>
          )}
        </div>
      )}
    </div>
  );
};
