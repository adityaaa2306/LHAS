import React, { useState } from 'react';
import { ChevronDown, ChevronRight, Activity, AlertTriangle, CheckCircle2, XCircle } from 'lucide-react';
import type { PipelineDiagnostics } from '@/types';

interface MemoryPipelineDiagnosticsProps {
  diagnostics: PipelineDiagnostics | null;
  loading?: boolean;
}

function StageIcon({ ok }: { ok: boolean | string }) {
  if (ok === true || ok === 'ok') {
    return <CheckCircle2 size={14} className="text-emerald-500 shrink-0" />;
  }
  if (ok === false || ok === 'no_claims' || ok === 'no_edges_despite_claims') {
    return <XCircle size={14} className="text-red-500 shrink-0" />;
  }
  return <AlertTriangle size={14} className="text-amber-500 shrink-0" />;
}

export const MemoryPipelineDiagnostics: React.FC<MemoryPipelineDiagnosticsProps> = ({
  diagnostics,
  loading = false,
}) => {
  const [expanded, setExpanded] = useState(true);
  const [showPapers, setShowPapers] = useState(false);

  if (loading) {
    return (
      <div className="rounded-lg border border-neutral-200 bg-neutral-50 p-4 text-sm text-neutral-500">
        Loading pipeline diagnostics...
      </div>
    );
  }

  if (!diagnostics) return null;

  const stages = diagnostics.pipeline_stages || {};
  const health = diagnostics.stage_health || {};

  return (
    <section className="rounded-lg border border-neutral-200 bg-white p-4">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center gap-2 text-left"
      >
        {expanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
        <Activity size={14} className="text-emerald-600" />
        <h4 className="text-sm font-semibold text-neutral-900">Pipeline diagnostics</h4>
        <span className="ml-auto text-xs text-neutral-400">Developer view</span>
      </button>

      {expanded && (
        <div className="mt-4 space-y-4">
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <Metric label="Claims" value={stages.claims_extracted ?? 0} />
            <Metric label="Entities" value={stages.entities_indexed ?? 0} />
            <Metric label="Edges" value={stages.memory_graph_edges ?? 0} />
            <Metric label="Contradictions" value={stages.confirmed_contradictions ?? 0} />
          </div>

          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            <HealthRow label="Retrieval" status={health.retrieval} />
            <HealthRow label="PDF extraction" status={health.pdf_extraction} />
            <HealthRow label="Claim extraction" status={health.claim_extraction} />
            <HealthRow label="Entity extraction" status={health.entity_extraction} />
            <HealthRow label="Relationships" status={health.relationship_generation} />
            <HealthRow label="Contradictions" status={health.contradiction_detection} />
          </div>

          {diagnostics.contradiction_explanation && (
            <div className="rounded-md border border-blue-100 bg-blue-50 px-3 py-2 text-sm text-blue-900">
              {diagnostics.contradiction_explanation}
            </div>
          )}

          <div className="text-xs text-neutral-600 space-y-1">
            <p>
              Contradiction candidates evaluated: {stages.contradiction_candidates_evaluated ?? 0} ·
              Context resolved: {stages.context_resolved_pairs ?? 0} ·
              Ambiguous: {stages.ambiguous_pairs ?? 0}
            </p>
            <p>
              Papers with full text: {stages.papers_full_text_extracted ?? 0} / {stages.papers_retrieved ?? 0} ·
              Fully processed: {health.papers_fully_processed}
            </p>
          </div>

          <div>
            <button
              type="button"
              onClick={() => setShowPapers((v) => !v)}
              className="flex items-center gap-1 text-xs font-semibold text-neutral-600"
            >
              {showPapers ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
              Per-paper audit ({diagnostics.paper_audits?.length ?? 0})
            </button>
            {showPapers && (
              <ul className="mt-2 max-h-48 space-y-2 overflow-y-auto rounded border border-neutral-100 bg-neutral-50 p-2">
                {(diagnostics.paper_audits || []).map((paper) => (
                  <li key={paper.paper_id} className="text-[11px]">
                    <p className="truncate font-medium text-neutral-800">{paper.title}</p>
                    <p className="text-neutral-500">
                      {[
                        paper.stages?.downloaded && '✓ Downloaded',
                        paper.stages?.parsed && '✓ Parsed',
                        paper.stages?.chunks_created && `✓ ${paper.claims_count} claims`,
                        paper.stages?.entities_extracted && `✓ ${paper.entities_count} entities`,
                      ]
                        .filter(Boolean)
                        .join(' · ') || 'No stages completed'}
                    </p>
                    {paper.failure_reason && (
                      <p className="text-red-600">{paper.failure_reason}</p>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </section>
  );
};

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg border border-neutral-100 bg-neutral-50 px-3 py-2 text-center">
      <p className="text-lg font-semibold tabular-nums text-neutral-900">{value}</p>
      <p className="text-[10px] font-medium uppercase tracking-wide text-neutral-500">{label}</p>
    </div>
  );
}

function HealthRow({ label, status }: { label: string; status?: string }) {
  const ok = status === 'ok' || status?.includes('/');
  return (
    <div className="flex items-center gap-2 rounded-md bg-neutral-50 px-2 py-1.5 text-xs">
      <StageIcon ok={ok ? true : status || false} />
      <span className="font-medium text-neutral-700">{label}</span>
      <span className="ml-auto text-neutral-500">{status || 'unknown'}</span>
    </div>
  );
}
