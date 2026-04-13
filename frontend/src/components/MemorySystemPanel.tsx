import React from 'react';
import { Activity, AlertTriangle, GitBranch, History, ShieldCheck } from 'lucide-react';

import { apiClient } from '@/services/api';
import { MemoryGraphPanel } from '@/components/MemoryGraphPanel';
import { ScrollFadePanel } from '@/components/ScrollFadePanel';
import type {
  MemoryGraphResponse,
  DriftMetric,
  MemoryContradiction,
  MemoryOverview,
  MemoryProvenanceEvent,
  MissionSnapshot,
} from '@/types';

interface MemorySystemPanelProps {
  missionId: string;
}

export const MemorySystemPanel: React.FC<MemorySystemPanelProps> = ({ missionId }) => {
  const [overview, setOverview] = React.useState<MemoryOverview | null>(null);
  const [snapshots, setSnapshots] = React.useState<MissionSnapshot[]>([]);
  const [drift, setDrift] = React.useState<DriftMetric[]>([]);
  const [contradictions, setContradictions] = React.useState<MemoryContradiction[]>([]);
  const [provenance, setProvenance] = React.useState<MemoryProvenanceEvent[]>([]);
  const [graph, setGraph] = React.useState<MemoryGraphResponse | null>(null);
  const [graphError, setGraphError] = React.useState<string | null>(null);
  const [showAllContradictions, setShowAllContradictions] = React.useState(false);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        setLoading(true);
        setError(null);
        setGraphError(null);
        const [overviewRes, snapshotsRes, driftRes, contradictionsRes, provenanceRes, graphRes] = await Promise.all([
          apiClient.getMemoryOverview(missionId),
          apiClient.getMemorySnapshots(missionId),
          apiClient.getMemoryDrift(missionId),
          apiClient.getMemoryContradictions(missionId),
          apiClient.getMemoryProvenance(missionId, { limit: 8 }),
          apiClient.getMemoryGraph(missionId, { max_nodes: 48, max_edges: 120 }).catch((err) => {
            setGraphError(err instanceof Error ? err.message : 'Failed to load graph');
            return null;
          }),
        ]);
        if (cancelled) return;
        setOverview(overviewRes);
        setSnapshots((snapshotsRes?.snapshots || []) as MissionSnapshot[]);
        setDrift((driftRes?.drift || []) as DriftMetric[]);
        setContradictions((contradictionsRes?.contradictions || []) as MemoryContradiction[]);
        setProvenance((provenanceRes?.events || []) as MemoryProvenanceEvent[]);
        setGraph((graphRes as MemoryGraphResponse | null) ?? null);
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : 'Failed to load memory state');
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    void load();
    return () => {
      cancelled = true;
    };
  }, [missionId]);

  return (
    <div className="bg-white rounded-lg border border-neutral-200 shadow-sm">
      <div className="px-5 py-4 border-b border-neutral-200 flex items-center gap-3">
        <ShieldCheck className="w-5 h-5 text-emerald-600" />
        <div>
          <h3 className="text-lg font-semibold text-neutral-900">Memory System</h3>
          <p className="text-sm text-neutral-600">Audit trail, graph state, belief revisions, drift, and checkpoints.</p>
        </div>
      </div>

      {loading ? (
        <div className="p-5 text-sm text-neutral-600">Loading memory state...</div>
      ) : error ? (
        <div className="p-5 text-sm text-red-700 bg-red-50">{error}</div>
      ) : (
        <div className="p-5 space-y-5">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <StatChip label="Graph Nodes" value={String(overview?.graph.node_count || 0)} icon={GitBranch} />
            <StatChip label="Edges" value={String(overview?.graph.edge_count || 0)} icon={Activity} />
            <StatChip label="Contradictions" value={String(overview?.graph.contradictions || 0)} icon={AlertTriangle} />
            <StatChip label="Provenance" value={String(overview?.audit.provenance_events || 0)} icon={History} />
          </div>

          <MemoryGraphPanel graph={graph} error={graphError} />

          {overview?.belief_state && (
            <section className="rounded-lg border border-blue-200 bg-blue-50 p-4">
              <div className="flex items-center justify-between gap-3 mb-2">
                <h4 className="text-sm font-semibold text-neutral-900">Belief Revision State</h4>
                <span className="text-xs font-medium text-blue-700">
                  {overview.belief_state.latest_revision_type || 'No revision yet'}
                </span>
              </div>
              <div className="flex flex-wrap gap-3 text-xs text-neutral-700">
                <span>Confidence {(overview.belief_state.current_confidence_score ?? 0).toFixed(2)}</span>
                <span>Direction {overview.belief_state.dominant_evidence_direction || 'mixed'}</span>
                <span>Drift {overview.belief_state.drift_trend || 'stabilizing'}</span>
                <span>{overview.belief_state.operator_action_required ? 'Operator review required' : 'Auto-updates enabled'}</span>
              </div>
            </section>
          )}

          <section className="rounded-lg border border-neutral-200 bg-neutral-50 p-4">
            <div className="flex items-center justify-between gap-3 mb-2">
              <h4 className="text-sm font-semibold text-neutral-900">Latest Belief Snapshot</h4>
              <span className="text-xs font-medium text-neutral-600">
                Cycle {overview?.latest_snapshot?.cycle_number ?? 0}
              </span>
            </div>
            <p className="text-sm text-neutral-700 mb-3">
              {overview?.latest_snapshot?.current_belief_statement || 'No memory snapshot has been written yet.'}
            </p>
            <div className="flex flex-wrap gap-3 text-xs text-neutral-600">
              <span>Confidence {(overview?.latest_snapshot?.current_confidence_score ?? 0).toFixed(2)}</span>
              <span>Direction {overview?.latest_snapshot?.dominant_evidence_direction || 'mixed'}</span>
              <span>Checkpoints {overview?.audit.checkpoints || 0}</span>
            </div>
          </section>

          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
            <section className="rounded-lg border border-neutral-200 p-4">
              <h4 className="text-sm font-semibold text-neutral-900 mb-3">Drift Tracker</h4>
              <div className="space-y-3">
                {drift.slice(0, 4).map((item) => (
                  <div key={item.id} className="flex items-start justify-between gap-3 text-sm">
                    <div>
                      <div className="font-medium text-neutral-800">Cycle {item.cycle_number}</div>
                      <div className="text-neutral-600">
                        Direction {item.direction_stability ? 'stable' : 'changed'} · contradiction rate {item.contradiction_rate.toFixed(2)}
                      </div>
                    </div>
                    <div className={`font-semibold ${item.confidence_delta >= 0 ? 'text-emerald-700' : 'text-red-700'}`}>
                      {item.confidence_delta >= 0 ? '+' : ''}{item.confidence_delta.toFixed(2)}
                    </div>
                  </div>
                ))}
                {drift.length === 0 && <div className="text-sm text-neutral-500">No drift history yet.</div>}
              </div>
            </section>

            <section className="rounded-lg border border-neutral-200 p-4">
              <div className="mb-3 flex items-center justify-between gap-3">
                <h4 className="text-sm font-semibold text-neutral-900">Active Contradictions</h4>
                {contradictions.length > 4 && (
                  <button
                    type="button"
                    onClick={() => setShowAllContradictions(true)}
                    className="rounded-full border border-neutral-200 bg-white px-2.5 py-1 text-[11px] font-semibold text-neutral-600 transition hover:bg-neutral-50"
                  >
                    View all
                  </button>
                )}
              </div>
              <div className="space-y-3">
                {contradictions.slice(0, 4).map((item) => (
                  <MemoryContradictionCard key={item.id} item={item} />
                ))}
                {contradictions.length === 0 && <div className="text-sm text-neutral-500">No active contradictions recorded.</div>}
              </div>
            </section>
          </div>

          <section className="rounded-lg border border-neutral-200 p-4">
            <h4 className="text-sm font-semibold text-neutral-900 mb-3">Recent Provenance</h4>
            <ScrollFadePanel heightClassName="h-[10.75rem]">
              <div className="space-y-3 pb-8">
                {provenance.map((event) => (
                  <div key={event.id} className="flex items-start justify-between gap-3 text-sm border-b border-neutral-100 pb-3 last:border-b-0 last:pb-0">
                    <div>
                      <div className="font-medium text-neutral-800">{event.event_type}</div>
                      <div className="text-neutral-600">{event.actor}</div>
                    </div>
                    <div className="text-right text-xs text-neutral-500">
                      {event.timestamp ? new Date(event.timestamp).toLocaleString() : 'Unknown time'}
                    </div>
                  </div>
                ))}
                {provenance.length === 0 && <div className="text-sm text-neutral-500">No provenance entries yet.</div>}
              </div>
            </ScrollFadePanel>
          </section>

          <section className="rounded-lg border border-neutral-200 p-4">
            <h4 className="text-sm font-semibold text-neutral-900 mb-3">Snapshot History</h4>
            <div className="space-y-2">
              {snapshots.slice(0, 5).map((snapshot) => (
                <div key={snapshot.id} className="flex items-center justify-between gap-3 text-sm">
                  <div>
                    <div className="font-medium text-neutral-800">Cycle {snapshot.cycle_number}</div>
                    <div className="text-neutral-600">
                      {snapshot.papers_ingested_count} papers · {snapshot.claims_extracted_count} claims · {snapshot.active_contradictions_count} contradictions
                    </div>
                  </div>
                  <div className="text-xs text-neutral-500">{snapshot.timestamp ? new Date(snapshot.timestamp).toLocaleString() : 'Pending'}</div>
                </div>
              ))}
              {snapshots.length === 0 && <div className="text-sm text-neutral-500">No mission snapshots yet.</div>}
            </div>
          </section>
        </div>
      )}

      {showAllContradictions && (
        <MemoryContradictionsModal
          contradictions={contradictions}
          onClose={() => setShowAllContradictions(false)}
        />
      )}
    </div>
  );
};

const StatChip: React.FC<{
  label: string;
  value: string;
  icon: React.ComponentType<{ className?: string }>;
}> = ({ label, value, icon: Icon }) => (
  <div className="rounded-lg border border-neutral-200 bg-neutral-50 px-3 py-3">
    <div className="flex items-center gap-2 text-neutral-600 mb-1">
      <Icon className="w-4 h-4" />
      <span className="text-xs font-medium">{label}</span>
    </div>
    <div className="text-xl font-semibold text-neutral-900">{value}</div>
  </div>
);

const MemoryContradictionCard: React.FC<{ item: MemoryContradiction }> = ({ item }) => (
  <div className="rounded-md bg-red-50 border border-red-100 p-3">
    <div className="flex items-center justify-between gap-3">
      <span className="text-sm font-medium text-red-900">{item.resolution_status}</span>
      <span className="text-xs text-red-700">weight {item.edge_weight.toFixed(2)}</span>
    </div>
    <div className="mt-2 text-sm font-semibold text-neutral-900">
      {(item.intervention_canonical || 'Unknown intervention')} · {(item.outcome_canonical || 'Unknown outcome')}
    </div>
    <div className="mt-1 text-xs text-red-700">
      {item.direction_a || 'unclear'} vs {item.direction_b || 'unclear'} · population {item.population_overlap || 'unknown'}
    </div>
    {item.claim_a_statement && (
      <div className="mt-3 rounded-md border border-white/70 bg-white/70 px-3 py-2">
        <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-neutral-500">Claim A</p>
        <p className="mt-1 text-sm text-neutral-800">{item.claim_a_statement}</p>
        {item.claim_a_paper_title && (
          <p className="mt-1 text-xs text-neutral-500">{item.claim_a_paper_title}</p>
        )}
      </div>
    )}
    {item.claim_b_statement && (
      <div className="mt-2 rounded-md border border-white/70 bg-white/70 px-3 py-2">
        <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-neutral-500">Claim B</p>
        <p className="mt-1 text-sm text-neutral-800">{item.claim_b_statement}</p>
        {item.claim_b_paper_title && (
          <p className="mt-1 text-xs text-neutral-500">{item.claim_b_paper_title}</p>
        )}
      </div>
    )}
    {item.justification && (
      <div className="text-xs text-red-800 mt-2">{item.justification}</div>
    )}
  </div>
);

const MemoryContradictionsModal: React.FC<{
  contradictions: MemoryContradiction[];
  onClose: () => void;
}> = ({ contradictions, onClose }) => (
  <>
    <div className="fixed inset-0 z-40 bg-black/50" onClick={onClose} />
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="max-h-[88vh] w-full max-w-4xl overflow-hidden rounded-2xl border border-neutral-200 bg-white shadow-[0_24px_80px_rgba(15,23,42,0.22)]">
        <div className="flex items-center justify-between border-b border-neutral-200 px-5 py-4">
          <div>
            <h3 className="text-lg font-semibold text-neutral-950">All Active Contradictions</h3>
            <p className="text-sm text-neutral-500">Readable contradiction records from mission memory.</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-full border border-neutral-200 px-3 py-1.5 text-sm font-medium text-neutral-700 transition hover:bg-neutral-50"
          >
            Close
          </button>
        </div>
        <ScrollFadePanel heightClassName="h-[70vh]" className="bg-neutral-50/50">
          <div className="space-y-3 p-5 pb-8">
            {contradictions.map((item) => (
              <MemoryContradictionCard key={item.id} item={item} />
            ))}
          </div>
        </ScrollFadePanel>
      </div>
    </div>
  </>
);
