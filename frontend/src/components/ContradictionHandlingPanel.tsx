import React from 'react';
import { AlertTriangle, CheckCircle2, HelpCircle, ShieldAlert } from 'lucide-react';

import { apiClient } from '@/services/api';
import { ScrollFadePanel } from '@/components/ScrollFadePanel';
import type {
  AmbiguousContradictionPair,
  ConfirmedContradiction,
  ContextResolvedPair,
  ContradictionOverview,
} from '@/types';

interface ContradictionHandlingPanelProps {
  missionId: string;
}

export const ContradictionHandlingPanel: React.FC<ContradictionHandlingPanelProps> = ({ missionId }) => {
  const [overview, setOverview] = React.useState<ContradictionOverview | null>(null);
  const [confirmed, setConfirmed] = React.useState<ConfirmedContradiction[]>([]);
  const [resolved, setResolved] = React.useState<ContextResolvedPair[]>([]);
  const [ambiguous, setAmbiguous] = React.useState<AmbiguousContradictionPair[]>([]);
  const [showConfirmedList, setShowConfirmedList] = React.useState(false);
  const [showConfirmedModal, setShowConfirmedModal] = React.useState(false);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  const groupedConfirmed = React.useMemo(() => {
    const severityRank: Record<string, number> = { LOW: 1, MEDIUM: 2, HIGH: 3 };
    const groups = new Map<
      string,
      {
        key: string;
        intervention: string;
        outcome: string;
        highestSeverity: 'LOW' | 'MEDIUM' | 'HIGH';
        pairCount: number;
        highSeverityCount: number;
        mediumSeverityCount: number;
        lowSeverityCount: number;
        maxWeight: number | null;
        directionCounts: Record<string, number>;
        claimIds: Set<string>;
      }
    >();

    for (const item of confirmed) {
      const intervention = item.intervention_canonical || 'Unknown intervention';
      const outcome = item.outcome_canonical || 'Unknown outcome';
      const key = `${intervention}::${outcome}`;
      const directionKey = `${item.direction_a} vs ${item.direction_b}`;
      if (!groups.has(key)) {
        groups.set(key, {
          key,
          intervention,
          outcome,
          highestSeverity: item.severity,
          pairCount: 0,
          highSeverityCount: 0,
          mediumSeverityCount: 0,
          lowSeverityCount: 0,
          maxWeight: item.edge_weight ?? null,
          directionCounts: {},
          claimIds: new Set<string>(),
        });
      }
      const group = groups.get(key)!;
      group.pairCount += 1;
      group.claimIds.add(item.claim_a_id);
      group.claimIds.add(item.claim_b_id);
      group.directionCounts[directionKey] = (group.directionCounts[directionKey] || 0) + 1;
      if ((item.edge_weight ?? -1) > (group.maxWeight ?? -1)) {
        group.maxWeight = item.edge_weight ?? null;
      }
      if (severityRank[item.severity] > severityRank[group.highestSeverity]) {
        group.highestSeverity = item.severity;
      }
      if (item.severity === 'HIGH') group.highSeverityCount += 1;
      else if (item.severity === 'MEDIUM') group.mediumSeverityCount += 1;
      else group.lowSeverityCount += 1;
    }

    return Array.from(groups.values()).sort((left, right) => {
      if (severityRank[right.highestSeverity] !== severityRank[left.highestSeverity]) {
        return severityRank[right.highestSeverity] - severityRank[left.highestSeverity];
      }
      return right.pairCount - left.pairCount;
    });
  }, [confirmed]);

  React.useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        setLoading(true);
        setError(null);
        const [overviewRes, confirmedRes, resolvedRes, ambiguousRes] = await Promise.all([
          apiClient.getContradictionOverview(missionId),
          apiClient.getConfirmedContradictions(missionId),
          apiClient.getResolvedContradictions(missionId),
          apiClient.getAmbiguousContradictions(missionId),
        ]);
        if (cancelled) return;
        setOverview(overviewRes as ContradictionOverview);
        setConfirmed((confirmedRes?.contradictions || []) as ConfirmedContradiction[]);
        setResolved((resolvedRes?.resolved_pairs || []) as ContextResolvedPair[]);
        setAmbiguous((ambiguousRes?.ambiguous_pairs || []) as AmbiguousContradictionPair[]);
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : 'Failed to load contradiction handling');
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [missionId]);

  const topicCount = overview?.topic_count ?? groupedConfirmed.length;

  return (
    <div className="overflow-hidden rounded-2xl border border-neutral-200/80 bg-white shadow-[0_12px_40px_rgba(15,23,42,0.06)]">
      <div className="border-b border-neutral-200 bg-gradient-to-r from-white via-neutral-50 to-white p-6">
        <div className="flex items-center gap-3">
          <AlertTriangle className="h-6 w-6 text-amber-600" />
          <div>
            <h3 className="text-xl font-semibold text-neutral-900">Contradiction Handling</h3>
            <p className="text-sm text-neutral-600">Confirmed conflicts only, with context-resolved and ambiguous pairs kept separate.</p>
          </div>
        </div>
      </div>

      {loading ? (
        <div className="p-6 text-sm text-neutral-600">Loading contradiction state...</div>
      ) : error ? (
        <div className="p-6 text-sm text-red-700 bg-red-50">{error}</div>
      ) : (
        <div className="space-y-5 p-6">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <button
              type="button"
              onClick={() => setShowConfirmedList((value) => !value)}
              className="text-left"
            >
              <StatCard label="Confirmed Pairs" value={overview?.confirmed_count ?? 0} tone="red" icon={AlertTriangle} interactive />
            </button>
            <StatCard label="Topics" value={topicCount} tone="slate" icon={HelpCircle} />
            <StatCard label="High Severity" value={overview?.high_severity_count ?? 0} tone="orange" icon={ShieldAlert} />
            <StatCard label="Context Resolved" value={overview?.context_resolved_count ?? 0} tone="green" icon={CheckCircle2} />
          </div>

          {showConfirmedList && (
            <section className="rounded-xl border border-red-200 bg-red-50/60 p-4">
              <div className="mb-3 flex items-center justify-between gap-3">
                <div>
                  <h4 className="text-sm font-semibold text-red-900">Confirmed Contradiction Pairs</h4>
                  <p className="text-xs text-red-700">
                    {confirmed.length} pair-level audit records across {topicCount} contradiction topic{topicCount === 1 ? '' : 's'}.
                    These are the raw pairings behind the grouped topics below.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setShowConfirmedModal(true)}
                  className="rounded-full border border-red-200 bg-white px-3 py-1 text-xs font-semibold text-red-700 transition hover:bg-red-50"
                >
                  View all
                </button>
              </div>
              <ScrollFadePanel heightClassName="h-[17rem]" className="border border-red-100 bg-white/70">
                <div className="space-y-3 p-3 pb-8">
                  {confirmed.map((item) => (
                    <ConfirmedPairCard key={item.id} item={item} />
                  ))}
                </div>
              </ScrollFadePanel>
            </section>
          )}

          <div className="rounded-xl border border-neutral-200 bg-neutral-50 p-4 text-sm text-neutral-700">
            Study-design asymmetry threshold: <span className="font-semibold text-neutral-900">{(overview?.asymmetry_threshold ?? 0.35).toFixed(2)}</span>
          </div>

          <div className="grid gap-4 xl:grid-cols-3">
            <ListCard
              title="Confirmed Contradiction Topics"
              subtitle={`${topicCount} topic${topicCount === 1 ? '' : 's'} covering ${confirmed.length} confirmed pair${confirmed.length === 1 ? '' : 's'}`}
              empty="No confirmed contradictions yet."
              action={confirmed.length > 0 ? (
                <button
                  type="button"
                  onClick={() => setShowConfirmedModal(true)}
                  className="rounded-full border border-neutral-200 bg-white px-2.5 py-1 text-[11px] font-semibold text-neutral-600 transition hover:bg-neutral-50"
                >
                  View all
                </button>
              ) : undefined}
            >
              {groupedConfirmed.map((item) => (
                <div key={item.key} className="rounded-xl border border-red-100 bg-red-50 p-3">
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-sm font-semibold text-red-900">{item.highestSeverity}</span>
                    <span className="text-xs text-red-700">{item.maxWeight ? `${Math.round(item.maxWeight * 100)}% top weight` : 'Pending weight'}</span>
                  </div>
                  <div className="mt-2 text-sm font-medium text-neutral-900">
                    {item.intervention} · {item.outcome}
                  </div>
                  <div className="mt-1 text-xs text-neutral-600">
                    {item.pairCount} confirmed pairs across {item.claimIds.size} claims
                  </div>
                  <div className="mt-2 flex flex-wrap gap-2 text-[11px]">
                    {Object.entries(item.directionCounts).map(([directionKey, count]) => (
                      <span key={directionKey} className="rounded-full bg-white/80 px-2 py-1 text-neutral-700">
                        {directionKey} · {count}
                      </span>
                    ))}
                  </div>
                  <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-neutral-700">
                    {item.highSeverityCount > 0 && <span>{item.highSeverityCount} high</span>}
                    {item.mediumSeverityCount > 0 && <span>{item.mediumSeverityCount} medium</span>}
                    {item.lowSeverityCount > 0 && <span>{item.lowSeverityCount} low</span>}
                  </div>
                </div>
              ))}
            </ListCard>

            <ListCard title="Context Resolved" empty="No context-resolved pairs yet.">
              {resolved.map((item) => (
                <div key={item.id} className="rounded-xl border border-emerald-100 bg-emerald-50 p-3">
                  <div className="text-sm font-semibold text-emerald-900">{item.resolution_reason.replaceAll('_', ' ')}</div>
                  <div className="mt-1 text-sm text-neutral-900">
                    {item.intervention_canonical || 'Unknown intervention'} · {item.outcome_canonical || 'Unknown outcome'}
                  </div>
                  {item.notes && <div className="mt-1 text-xs text-neutral-600">{item.notes}</div>}
                </div>
              ))}
            </ListCard>

            <ListCard
              title="Ambiguous Pairs"
              subtitle={`${overview?.ambiguous_count ?? 0} unresolved pair${(overview?.ambiguous_count ?? 0) === 1 ? '' : 's'} awaiting clarification`}
              empty="No ambiguous contradiction pairs yet."
            >
              {ambiguous.map((item) => (
                <div key={item.id} className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                  <div className="text-sm font-semibold text-slate-900">{item.ambiguity_reason.replaceAll('_', ' ')}</div>
                  <div className="mt-1 text-sm text-neutral-900">
                    {item.intervention_canonical || 'Unknown intervention'} · {item.outcome_canonical || 'Unknown outcome'}
                  </div>
                  <div className="mt-1 text-xs text-neutral-600">{item.direction_a} vs {item.direction_b}</div>
                </div>
              ))}
            </ListCard>
          </div>
        </div>
      )}

      {showConfirmedModal && (
        <ContradictionListModal
          title={`Confirmed contradiction pairs (${confirmed.length})`}
          subtitle={`${topicCount} contradiction topic${topicCount === 1 ? '' : 's'} are represented in this audit list.`}
          items={confirmed}
          onClose={() => setShowConfirmedModal(false)}
        />
      )}
    </div>
  );
};

const StatCard: React.FC<{
  label: string;
  value: number;
  tone: 'red' | 'orange' | 'green' | 'slate';
  icon: React.ComponentType<{ className?: string }>;
  interactive?: boolean;
}> = ({ label, value, tone, icon: Icon, interactive = false }) => {
  const toneClasses = {
    red: 'border-red-200 bg-red-50 text-red-900',
    orange: 'border-amber-200 bg-amber-50 text-amber-900',
    green: 'border-emerald-200 bg-emerald-50 text-emerald-900',
    slate: 'border-slate-200 bg-slate-50 text-slate-900',
  } as const;

  return (
    <div className={`rounded-xl border p-4 ${toneClasses[tone]} ${interactive ? 'transition hover:-translate-y-[1px] hover:shadow-sm' : ''}`}>
      <div className="mb-2 flex items-center gap-2 text-xs font-medium opacity-80">
        <Icon className="h-4 w-4" />
        <span>{label}</span>
      </div>
      <div className="text-2xl font-semibold">{value}</div>
    </div>
  );
};

const ListCard: React.FC<{
  title: string;
  empty: string;
  children: React.ReactNode;
  action?: React.ReactNode;
  subtitle?: string;
}> = ({ title, empty, children, action, subtitle }) => {
  const items = React.Children.toArray(children);
  return (
    <section className="rounded-xl border border-neutral-200 p-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div>
          <h4 className="text-sm font-semibold text-neutral-900">{title}</h4>
          {subtitle && <p className="mt-1 text-xs text-neutral-500">{subtitle}</p>}
        </div>
        {action}
      </div>
      <ScrollFadePanel heightClassName="h-[18rem]" className="border border-neutral-200/80 bg-neutral-50/40">
        <div className="space-y-3 p-3 pb-8">
          {items.length > 0 ? items : <div className="text-sm text-neutral-500">{empty}</div>}
        </div>
      </ScrollFadePanel>
    </section>
  );
};

const ConfirmedPairCard: React.FC<{ item: ConfirmedContradiction }> = ({ item }) => (
  <div className="rounded-xl border border-red-100 bg-red-50 p-3">
    <div className="flex items-center justify-between gap-3">
      <span className="text-xs font-semibold text-red-900">{item.severity}</span>
      <span className="text-xs text-red-700">
        {item.edge_weight != null ? `${Math.round(item.edge_weight * 100)}% weight` : 'Pending weight'}
      </span>
    </div>
    <div className="mt-2 text-sm font-semibold text-neutral-900">
      {item.intervention_canonical || 'Unknown intervention'} · {item.outcome_canonical || 'Unknown outcome'}
    </div>
    <div className="mt-1 text-xs text-neutral-600">
      {item.direction_a} vs {item.direction_b} · population {item.population_overlap}
    </div>
    <div className="mt-2 text-xs text-neutral-500">
      quality delta {item.quality_parity_delta.toFixed(2)} · confidence product {item.confidence_product.toFixed(2)}
    </div>
    {item.justification && (
      <div className="mt-2 text-xs text-red-800">{item.justification}</div>
    )}
  </div>
);

const ContradictionListModal: React.FC<{
  title: string;
  subtitle: string;
  items: ConfirmedContradiction[];
  onClose: () => void;
}> = ({ title, subtitle, items, onClose }) => (
  <>
    <div className="fixed inset-0 z-40 bg-black/50" onClick={onClose} />
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="max-h-[88vh] w-full max-w-4xl overflow-hidden rounded-2xl border border-neutral-200 bg-white shadow-[0_24px_80px_rgba(15,23,42,0.22)]">
        <div className="flex items-center justify-between border-b border-neutral-200 px-5 py-4">
          <div>
            <h3 className="text-lg font-semibold text-neutral-950">{title}</h3>
            <p className="text-sm text-neutral-500">{subtitle}</p>
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
            {items.map((item) => (
              <ConfirmedPairCard key={item.id} item={item} />
            ))}
          </div>
        </ScrollFadePanel>
      </div>
    </div>
  </>
);
