import React, { useEffect, useMemo, useState } from 'react';
import {
  Activity,
  AlertTriangle,
  BarChart3,
  ChevronDown,
  ChevronUp,
  FileText,
  Minus,
  Search,
  TrendingDown,
  TrendingUp,
  Zap,
} from 'lucide-react';

import { apiClient } from '../services/api';
import { ScrollFadePanel } from './ScrollFadePanel';
import type { ClaimSummary, ClusterResponse, EvidenceCluster } from '../types';

type ViewMode = 'clusters' | 'conflicts' | 'entities';
type SortBy = 'confidence' | 'evidence_count' | 'conflicts';

interface ClaimsExplorerProps {
  missionId: string;
}

export const ClaimsExplorer: React.FC<ClaimsExplorerProps> = ({ missionId }) => {
  const [clusters, setClusters] = useState<EvidenceCluster[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>('clusters');
  const [sortBy, setSortBy] = useState<SortBy>('confidence');
  const [searchQuery, setSearchQuery] = useState('');
  const [expandedClusterId, setExpandedClusterId] = useState<string | null>(null);

  useEffect(() => {
    void loadClusters();
  }, [missionId]);

  const loadClusters = async () => {
    try {
      setLoading(true);
      setError(null);
      const response: ClusterResponse = await apiClient.getClaimsClusters(missionId);
      setClusters(response.clusters || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load clusters');
      console.error('Error loading clusters:', err);
    } finally {
      setLoading(false);
    }
  };

  const filteredClusters = useMemo(() => {
    let filtered = [...clusters];

    if (viewMode === 'conflicts') {
      filtered = filtered.filter((cluster) => cluster.contradiction_signal.has_conflict);
    }

    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase();
      filtered = filtered.filter(
        (cluster) =>
          cluster.cluster_key.intervention_canonical.toLowerCase().includes(query) ||
          cluster.cluster_key.outcome_canonical.toLowerCase().includes(query)
      );
    }

    switch (sortBy) {
      case 'confidence':
        filtered.sort((left, right) => right.statistics.avg_confidence - left.statistics.avg_confidence);
        break;
      case 'evidence_count':
        filtered.sort((left, right) => right.claim_count - left.claim_count);
        break;
      case 'conflicts':
        filtered.sort((left, right) => {
          const leftConflict = left.contradiction_signal.has_conflict ? 1 : 0;
          const rightConflict = right.contradiction_signal.has_conflict ? 1 : 0;
          if (rightConflict !== leftConflict) return rightConflict - leftConflict;
          return right.statistics.avg_confidence - left.statistics.avg_confidence;
        });
        break;
    }

    return filtered;
  }, [clusters, searchQuery, sortBy, viewMode]);

  if (loading) {
    return (
      <div className="rounded-[20px] border border-neutral-200/80 bg-white p-6 shadow-[0_18px_50px_rgba(15,23,42,0.06)]">
        <div className="flex h-64 items-center justify-center">
          <div className="text-center">
            <div className="mx-auto mb-4 h-12 w-12 animate-spin rounded-full border-b-2 border-blue-600" />
            <p className="text-sm font-medium text-neutral-600">Loading evidence clusters...</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-[20px] border border-neutral-200/80 bg-white shadow-[0_18px_50px_rgba(15,23,42,0.06)]">
      <CardHeader
        viewMode={viewMode}
        onViewModeChange={setViewMode}
        sortBy={sortBy}
        onSortChange={setSortBy}
        searchQuery={searchQuery}
        onSearchChange={setSearchQuery}
        totalClusters={clusters.length}
        totalClaimsInViewMode={filteredClusters.length}
      />

      {error && (
        <div className="border-b border-red-100 bg-red-50/80 px-6 py-4">
          <div className="flex items-start gap-3">
            <AlertTriangle className="mt-0.5 h-5 w-5 flex-shrink-0 text-red-600" />
            <div>
              <p className="text-sm font-semibold text-red-900">Error loading clusters</p>
              <p className="mt-1 text-sm text-red-700">{error}</p>
              <button
                onClick={loadClusters}
                className="mt-2 text-sm font-medium text-red-700 underline underline-offset-2 hover:text-red-900"
              >
                Retry
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="bg-neutral-50/70 px-4 py-4">
        <ScrollFadePanel
          heightClassName="h-[34rem]"
          className="rounded-[18px] border border-neutral-200/80 bg-neutral-50/80 shadow-[inset_0_1px_0_rgba(255,255,255,0.8)]"
          contentClassName="px-3 py-3"
        >
          {viewMode === 'clusters' && (
            <ClustersView
              clusters={filteredClusters}
              expandedClusterId={expandedClusterId}
              onExpandChange={setExpandedClusterId}
            />
          )}

          {viewMode === 'conflicts' && <ConflictsView clusters={filteredClusters} />}
          {viewMode === 'entities' && <EntitiesView clusters={clusters} />}
        </ScrollFadePanel>
      </div>
    </div>
  );
};

interface CardHeaderProps {
  viewMode: ViewMode;
  onViewModeChange: (mode: ViewMode) => void;
  sortBy: SortBy;
  onSortChange: (sort: SortBy) => void;
  searchQuery: string;
  onSearchChange: (query: string) => void;
  totalClusters: number;
  totalClaimsInViewMode: number;
}

const CardHeader: React.FC<CardHeaderProps> = ({
  viewMode,
  onViewModeChange,
  sortBy,
  onSortChange,
  searchQuery,
  onSearchChange,
  totalClusters,
  totalClaimsInViewMode,
}) => {
  const viewModes = [
    { id: 'clusters', label: 'Clusters', icon: BarChart3 },
    { id: 'conflicts', label: 'Conflicts', icon: AlertTriangle },
    { id: 'entities', label: 'Entities', icon: Activity },
  ];

  return (
    <div className="border-b border-neutral-200 bg-gradient-to-b from-white to-neutral-50/70 px-6 py-6">
      <div className="flex flex-col gap-5">
        <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
          <div className="flex items-start gap-3">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-blue-50 text-blue-600 shadow-sm ring-1 ring-blue-100">
              <FileText className="h-6 w-6" />
            </div>
            <div>
              <h3 className="text-[1.35rem] font-semibold tracking-[-0.02em] text-neutral-950">Extracted Claims</h3>
              <p className="mt-1 text-sm text-neutral-600">
                Structured evidence clusters grouped by intervention and outcome, tuned for fast scanning.
              </p>
            </div>
          </div>

          <div className="rounded-2xl border border-neutral-200 bg-white/80 px-4 py-3 shadow-sm">
            <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-neutral-500">Showing</div>
            <div className="mt-1 text-sm font-medium text-neutral-900">
              {viewMode === 'conflicts'
                ? `${totalClaimsInViewMode} conflict clusters`
                : `${totalClaimsInViewMode} clusters`}
            </div>
            <div className="mt-0.5 text-xs text-neutral-500">{totalClusters} total in mission</div>
          </div>
        </div>

        <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
          <div className="inline-flex w-full rounded-2xl border border-neutral-200 bg-white p-1 shadow-sm xl:w-auto">
            {viewModes.map(({ id, label, icon: Icon }) => {
              const active = viewMode === id;
              return (
                <button
                  key={id}
                  onClick={() => onViewModeChange(id as ViewMode)}
                  className={`inline-flex flex-1 items-center justify-center gap-2 rounded-[14px] px-4 py-2.5 text-sm font-medium transition xl:flex-none ${
                    active
                      ? 'bg-neutral-950 text-white shadow-[0_10px_20px_rgba(15,23,42,0.18)]'
                      : 'text-neutral-600 hover:bg-neutral-100 hover:text-neutral-900'
                  }`}
                >
                  <Icon className="h-4 w-4" />
                  {label}
                </button>
              );
            })}
          </div>

          <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_220px] xl:min-w-[34rem]">
            <div className="relative">
              <Search className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-neutral-400" />
              <input
                type="text"
                placeholder="Search interventions or outcomes..."
                value={searchQuery}
                onChange={(event) => onSearchChange(event.target.value)}
                className="h-12 w-full rounded-2xl border border-neutral-200 bg-white pl-11 pr-4 text-sm text-neutral-900 shadow-sm outline-none transition placeholder:text-neutral-400 focus:border-blue-300 focus:ring-4 focus:ring-blue-100"
              />
            </div>

            <select
              value={sortBy}
              onChange={(event) => onSortChange(event.target.value as SortBy)}
              className="h-12 rounded-2xl border border-neutral-200 bg-white px-4 text-sm font-medium text-neutral-800 shadow-sm outline-none transition focus:border-blue-300 focus:ring-4 focus:ring-blue-100"
            >
              <option value="confidence">Sort: Confidence</option>
              <option value="evidence_count">Sort: Evidence Count</option>
              <option value="conflicts">Sort: Conflicts First</option>
            </select>
          </div>
        </div>
      </div>
    </div>
  );
};

interface ClustersViewProps {
  clusters: EvidenceCluster[];
  expandedClusterId: string | null;
  onExpandChange: (id: string | null) => void;
}

const ClustersView: React.FC<ClustersViewProps> = ({
  clusters,
  expandedClusterId,
  onExpandChange,
}) => {
  if (clusters.length === 0) {
    return <EmptyState icon={BarChart3} title="No evidence clusters" description="Start by extracting claims from papers to see clustered evidence." />;
  }

  return (
    <div className="space-y-3 pb-8">
      <LegendRow />
      {clusters.map((cluster, idx) => {
        const clusterId = `${cluster.cluster_key.intervention_canonical}-${cluster.cluster_key.outcome_canonical}-${idx}`;
        const isExpanded = expandedClusterId === clusterId;

        return (
          <div
            key={clusterId}
            className="overflow-hidden rounded-[18px] border border-neutral-200/90 bg-white shadow-[0_10px_24px_rgba(15,23,42,0.045)] transition hover:-translate-y-[1px] hover:shadow-[0_16px_32px_rgba(15,23,42,0.07)]"
          >
            <ClusterRow cluster={cluster} isExpanded={isExpanded} onToggleExpand={() => onExpandChange(isExpanded ? null : clusterId)} />
            {isExpanded && <ExpandedClusterDetail cluster={cluster} />}
          </div>
        );
      })}
    </div>
  );
};

interface ClusterRowProps {
  cluster: EvidenceCluster;
  isExpanded: boolean;
  onToggleExpand: () => void;
}

const ClusterRow: React.FC<ClusterRowProps> = ({ cluster, isExpanded, onToggleExpand }) => {
  return (
    <button onClick={onToggleExpand} className="w-full text-left">
      <div className="grid gap-4 px-5 py-5 md:grid-cols-2 2xl:grid-cols-[minmax(22rem,2.5fr)_minmax(11rem,1fr)_minmax(16rem,1.3fr)_minmax(8rem,0.8fr)_minmax(9rem,0.8fr)] 2xl:items-center">
        <div className="min-w-0 md:col-span-2 2xl:col-span-1">
          <div className="flex items-start gap-3">
            <div className="mt-1 flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-xl border border-neutral-200 bg-neutral-50 text-neutral-500">
              {isExpanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            </div>

            <div className="min-w-0 flex-1">
              <div className="mb-2 flex flex-wrap items-center gap-2">
                <EvidenceTypeBadge type={cluster.best_evidence_type} />
                {cluster.contradiction_signal.has_conflict && (
                  <StatusBadge tone="conflict" label={`${cluster.contradiction_signal.severity} conflict`} />
                )}
              </div>

              <div className="flex flex-wrap items-start gap-2 text-base font-semibold leading-7 text-neutral-950">
                <span className="min-w-0 flex-1 whitespace-normal break-words" title={cluster.cluster_key.intervention_canonical}>
                  {cluster.cluster_key.intervention_canonical}
                </span>
                <span className="mt-[1px] text-neutral-300">→</span>
                <span className="min-w-0 flex-1 whitespace-normal break-words" title={cluster.cluster_key.outcome_canonical}>
                  {cluster.cluster_key.outcome_canonical}
                </span>
              </div>

              <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-neutral-500">
                <span>{cluster.claim_count} supporting records</span>
                <span className="text-neutral-300">•</span>
                <span>{cluster.claims_summary.length} extracted claims</span>
              </div>
            </div>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2 md:justify-start">
          <MetaPill label="Claims" value={cluster.claim_count} />
          <MetaPill
            label="Range"
            value={`${Math.round(cluster.statistics.min_confidence * 100)}–${Math.round(cluster.statistics.max_confidence * 100)}%`}
          />
        </div>

        <div className="md:col-span-2 2xl:col-span-1">
          <EvidenceDistribution
            supporting={cluster.evidence_bar.supporting}
            contradicting={cluster.evidence_bar.contradicting}
            neutral={cluster.evidence_bar.null}
          />
        </div>

        <div className="md:justify-self-start 2xl:justify-self-center">
          <ConfidenceBadge confidence={cluster.statistics.avg_confidence} />
        </div>

        <div className="flex items-center justify-start gap-2 2xl:justify-end">
          {cluster.evidence_gaps.length > 0 && (
            <StatusBadge tone="warning" label={`${cluster.evidence_gaps.length} gap${cluster.evidence_gaps.length > 1 ? 's' : ''}`} />
          )}
          <StatusBadge tone="neutral" label={isExpanded ? 'Collapse' : 'Details'} />
        </div>
      </div>
    </button>
  );
};

const LegendRow: React.FC = () => (
  <div className="rounded-[16px] border border-neutral-200/80 bg-white/80 px-5 py-3 shadow-sm">
    <div className="flex flex-col gap-3 text-xs text-neutral-500 md:flex-row md:items-center md:justify-between">
      <div className="flex flex-wrap items-center gap-3">
        <span className="font-semibold uppercase tracking-[0.12em] text-neutral-400">Evidence mix</span>
        <LegendPill color="bg-emerald-500" label="Supporting" />
        <LegendPill color="bg-rose-500" label="Contradicting" />
        <LegendPill color="bg-slate-400" label="Neutral / unclear" />
      </div>
      <div className="font-medium text-neutral-500">Confidence combines percentage and qualitative label for quicker scanning.</div>
    </div>
  </div>
);

const LegendPill: React.FC<{ color: string; label: string }> = ({ color, label }) => (
  <span className="inline-flex items-center gap-2 rounded-full bg-neutral-50 px-3 py-1.5 text-neutral-600 ring-1 ring-neutral-200">
    <span className={`h-2.5 w-2.5 rounded-full ${color}`} />
    {label}
  </span>
);

const EvidenceDistribution: React.FC<{
  supporting: number;
  contradicting: number;
  neutral: number;
}> = ({ supporting, contradicting, neutral }) => {
  const total = supporting + contradicting + neutral;
  const safeTotal = total || 1;
  const segments = [
    { label: 'Support', count: supporting, width: (supporting / safeTotal) * 100, color: 'bg-emerald-500' },
    { label: 'Conflict', count: contradicting, width: (contradicting / safeTotal) * 100, color: 'bg-rose-500' },
    { label: 'Neutral', count: neutral, width: (neutral / safeTotal) * 100, color: 'bg-slate-400' },
  ];

  return (
    <div className="min-w-0">
      <div className="mb-2 flex items-center justify-between text-[11px] font-semibold uppercase tracking-[0.1em] text-neutral-400">
        <span>Distribution</span>
        <span>{total} total</span>
      </div>
      <div className="h-2.5 overflow-hidden rounded-full bg-neutral-200/80">
        {segments.map((segment) =>
          segment.count > 0 ? (
            <div
              key={segment.label}
              className={`h-full ${segment.color} inline-block`}
              style={{ width: `${segment.width}%` }}
              title={`${segment.label}: ${segment.count}`}
            />
          ) : null
        )}
      </div>
      <div className="mt-2 flex flex-wrap gap-2 text-xs text-neutral-500">
        {segments.map((segment) => (
          <span key={segment.label} className="inline-flex items-center gap-1.5 rounded-full bg-neutral-50 px-2.5 py-1 ring-1 ring-neutral-200">
            <span className={`h-2 w-2 rounded-full ${segment.color}`} />
            <span>{segment.label}</span>
            <span className="font-medium text-neutral-700">{segment.count}</span>
          </span>
        ))}
      </div>
    </div>
  );
};

const ConfidenceBadge: React.FC<{ confidence: number }> = ({ confidence }) => {
  const percent = Math.round(confidence * 100);
  const tone =
    confidence >= 0.75
      ? {
          label: 'High',
          ring: 'ring-emerald-200',
          bg: 'bg-emerald-50',
          value: 'text-emerald-700',
          subtitle: 'text-emerald-700/80',
        }
      : confidence >= 0.55
        ? {
            label: 'Medium',
            ring: 'ring-amber-200',
            bg: 'bg-amber-50',
            value: 'text-amber-700',
            subtitle: 'text-amber-700/80',
          }
        : {
            label: 'Low',
            ring: 'ring-rose-200',
            bg: 'bg-rose-50',
            value: 'text-rose-700',
            subtitle: 'text-rose-700/80',
          };

  return (
    <div className={`inline-flex w-fit min-w-[108px] flex-col rounded-2xl px-3 py-2.5 text-center shadow-sm ring-1 ${tone.bg} ${tone.ring}`}>
      <div className={`text-2xl font-semibold tracking-[-0.03em] ${tone.value}`}>{percent}%</div>
      <div className={`text-[11px] font-semibold uppercase tracking-[0.12em] ${tone.subtitle}`}>{tone.label} confidence</div>
    </div>
  );
};

const MetaPill: React.FC<{ label: string; value: string | number }> = ({ label, value }) => (
  <div className="rounded-2xl bg-neutral-100 px-3 py-2 text-left ring-1 ring-neutral-200">
    <div className="text-[11px] font-semibold uppercase tracking-[0.1em] text-neutral-400">{label}</div>
    <div className="mt-0.5 text-sm font-medium text-neutral-800">{value}</div>
  </div>
);

const EvidenceTypeBadge: React.FC<{ type: string }> = ({ type }) => {
  const normalized = type.toLowerCase();
  const palette =
    normalized.includes('safety')
      ? 'bg-rose-50 text-rose-700 ring-rose-200'
      : normalized.includes('comparative')
        ? 'bg-violet-50 text-violet-700 ring-violet-200'
        : normalized.includes('causal')
          ? 'bg-emerald-50 text-emerald-700 ring-emerald-200'
          : normalized.includes('correlational')
            ? 'bg-blue-50 text-blue-700 ring-blue-200'
            : normalized.includes('prevalence')
              ? 'bg-amber-50 text-amber-700 ring-amber-200'
              : 'bg-slate-50 text-slate-700 ring-slate-200';

  return (
    <span className={`inline-flex items-center rounded-full px-3 py-1.5 text-xs font-semibold capitalize ring-1 ${palette}`}>
      {type}
    </span>
  );
};

const StatusBadge: React.FC<{ tone: 'conflict' | 'warning' | 'neutral'; label: string }> = ({ tone, label }) => {
  const palette =
    tone === 'conflict'
      ? 'bg-red-50 text-red-700 ring-red-200'
      : tone === 'warning'
        ? 'bg-amber-50 text-amber-700 ring-amber-200'
        : 'bg-neutral-100 text-neutral-600 ring-neutral-200';

  return (
    <span className={`inline-flex items-center rounded-full px-3 py-1.5 text-xs font-medium ring-1 ${palette}`}>
      {label}
    </span>
  );
};

const ExpandedClusterDetail: React.FC<{ cluster: EvidenceCluster }> = ({ cluster }) => {
  return (
    <div className="border-t border-neutral-200 bg-neutral-50/80 px-5 py-5">
      <div className="grid gap-5 xl:grid-cols-[minmax(0,2fr)_minmax(260px,1fr)]">
        <div className="min-w-0">
          <SectionTitle icon={FileText} color="text-blue-600" title={`Claims in cluster (${cluster.claims_summary.length})`} />
          <div className="mt-4 space-y-3">
            {cluster.claims_summary.map((claim, idx) => (
              <ClaimRowDetail key={`${claim.id}-${idx}`} claim={claim} />
            ))}
          </div>
        </div>

        <div className="space-y-4">
          <div className="rounded-[18px] border border-neutral-200 bg-white p-4 shadow-sm">
            <SectionTitle icon={BarChart3} color="text-neutral-600" title="Cluster metrics" compact />
            <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-1">
              <DetailMetricCard label="Average confidence" value={`${Math.round(cluster.statistics.avg_confidence * 100)}%`} />
              <DetailMetricCard label="Confidence range" value={`${Math.round(cluster.statistics.min_confidence * 100)}–${Math.round(cluster.statistics.max_confidence * 100)}%`} />
              <DetailMetricCard label="Best evidence type" value={cluster.best_evidence_type} />
              <DetailMetricCard label="Conflict severity" value={cluster.contradiction_signal.has_conflict ? cluster.contradiction_signal.severity : 'None'} />
            </div>
          </div>

          {cluster.contradiction_signal.has_conflict && (
            <div className="rounded-[18px] border border-red-200 bg-red-50/80 p-4 shadow-sm">
              <SectionTitle icon={AlertTriangle} color="text-red-600" title="Confirmed conflict signal" compact />
              <p className="mt-3 text-sm text-red-800">
                {cluster.contradiction_signal.pairs.length} confirmed contradiction pair{cluster.contradiction_signal.pairs.length > 1 ? 's' : ''} are attached to this cluster.
              </p>
            </div>
          )}

          {cluster.evidence_gaps.length > 0 && (
            <div className="rounded-[18px] border border-amber-200 bg-amber-50/80 p-4 shadow-sm">
              <SectionTitle icon={Zap} color="text-amber-600" title={`Evidence gaps (${cluster.evidence_gaps.length})`} compact />
              <div className="mt-3 space-y-2">
                {cluster.evidence_gaps.map((gap, idx) => (
                  <div key={`${gap.type}-${idx}`} className="rounded-2xl bg-white/70 px-3 py-2 text-sm text-amber-900 ring-1 ring-amber-100">
                    {gap.description}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

const ClaimRowDetail: React.FC<{ claim: ClaimSummary }> = ({ claim }) => {
  const directionIcon =
    claim.direction === 'positive' ? (
      <TrendingUp className="h-4 w-4 text-emerald-600" />
    ) : claim.direction === 'negative' ? (
      <TrendingDown className="h-4 w-4 text-rose-600" />
    ) : (
      <Minus className="h-4 w-4 text-slate-500" />
    );

  return (
    <div className="rounded-[16px] border border-neutral-200 bg-white px-4 py-4 shadow-sm">
      <div className="flex items-start justify-between gap-4">
        <div className="flex min-w-0 items-start gap-3">
          <div className="mt-0.5 flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-xl bg-neutral-50 ring-1 ring-neutral-200">
            {directionIcon}
          </div>
          <div className="min-w-0">
            <p className="text-sm font-medium leading-6 text-neutral-900">{claim.statement}</p>
            <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-neutral-500">
              <EvidenceTypeBadge type={claim.claim_type} />
              <span
                className="max-w-full break-words"
                title={claim.paper_title}
              >
                {claim.paper_title}
              </span>
            </div>
          </div>
        </div>

        <ConfidenceBadge confidence={claim.confidence} />
      </div>
    </div>
  );
};

const ConflictsView: React.FC<{ clusters: EvidenceCluster[] }> = ({ clusters }) => {
  if (clusters.length === 0) {
    return <EmptyState icon={AlertTriangle} title="No conflicts detected" description="The evidence is aligned across all visible clusters." />;
  }

  return (
    <div className="space-y-3 pb-8">
      {clusters.map((cluster, idx) => (
        <div key={`${cluster.cluster_key.intervention_canonical}-${idx}`} className="rounded-[18px] border border-red-200 bg-white shadow-[0_10px_24px_rgba(15,23,42,0.045)]">
          <div className="border-b border-red-100 bg-red-50/70 px-5 py-4">
            <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
              <div>
                <div className="text-base font-semibold text-neutral-950">
                  {cluster.cluster_key.intervention_canonical} → {cluster.cluster_key.outcome_canonical}
                </div>
                <div className="mt-1 text-sm text-neutral-600">
                  {cluster.contradiction_signal.severity} severity contradiction signal
                </div>
              </div>
              <ConfidenceBadge confidence={cluster.statistics.avg_confidence} />
            </div>
          </div>

          <div className="space-y-3 px-5 py-4">
            {cluster.contradiction_signal.pairs.map((pair, pairIdx) => (
              <div key={`${pair.claim1_id}-${pair.claim2_id}-${pairIdx}`} className="rounded-[16px] border border-neutral-200 bg-neutral-50/70 px-4 py-4">
                <div className="mb-2 flex flex-wrap items-center gap-2">
                  <StatusBadge tone="conflict" label={pair.severity || cluster.contradiction_signal.severity} />
                  <span className="text-xs text-neutral-500">
                    {pair.claim1_direction} vs {pair.claim2_direction}
                  </span>
                </div>
                <div className="grid gap-3 lg:grid-cols-2">
                  <ConflictSourceCard title={pair.claim1_paper} direction={pair.claim1_direction} />
                  <ConflictSourceCard title={pair.claim2_paper} direction={pair.claim2_direction} />
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
};

const ConflictSourceCard: React.FC<{ title: string; direction: string }> = ({ title, direction }) => {
  const positive = direction === 'positive';
  const negative = direction === 'negative';
  return (
    <div className="rounded-[14px] border border-white bg-white px-4 py-3 shadow-sm ring-1 ring-neutral-200/80">
      <div className="mb-2 flex items-center gap-2">
        {positive ? (
          <TrendingUp className="h-4 w-4 text-emerald-600" />
        ) : negative ? (
          <TrendingDown className="h-4 w-4 text-rose-600" />
        ) : (
          <Minus className="h-4 w-4 text-slate-500" />
        )}
        <span className="text-xs font-semibold uppercase tracking-[0.1em] text-neutral-400">{direction}</span>
      </div>
      <p className="text-sm font-medium leading-6 text-neutral-900" title={title}>
        {title}
      </p>
    </div>
  );
};

const EntitiesView: React.FC<{ clusters: EvidenceCluster[] }> = ({ clusters }) => {
  const interventions = new Set<string>();
  const outcomes = new Set<string>();

  clusters.forEach((cluster) => {
    interventions.add(cluster.cluster_key.intervention_canonical);
    outcomes.add(cluster.cluster_key.outcome_canonical);
  });

  if (interventions.size === 0 && outcomes.size === 0) {
    return <EmptyState icon={Activity} title="No entities found" description="Extract claims to populate canonical interventions and outcomes." />;
  }

  return (
    <div className="grid gap-4 pb-8 lg:grid-cols-2">
      <EntityColumn
        title={`Interventions (${interventions.size})`}
        icon={Zap}
        iconColor="text-blue-600"
        items={Array.from(interventions).sort()}
        pillClassName="bg-blue-50 text-blue-700 ring-blue-100"
      />
      <EntityColumn
        title={`Outcomes (${outcomes.size})`}
        icon={Activity}
        iconColor="text-violet-600"
        items={Array.from(outcomes).sort()}
        pillClassName="bg-violet-50 text-violet-700 ring-violet-100"
      />
    </div>
  );
};

const EntityColumn: React.FC<{
  title: string;
  icon: React.ComponentType<{ className?: string }>;
  iconColor: string;
  items: string[];
  pillClassName: string;
}> = ({ title, icon: Icon, iconColor, items, pillClassName }) => (
  <div className="rounded-[18px] border border-neutral-200 bg-white p-5 shadow-[0_10px_24px_rgba(15,23,42,0.045)]">
    <SectionTitle icon={Icon} color={iconColor} title={title} />
    <div className="mt-4 flex flex-wrap gap-2">
      {items.map((item) => (
        <span
          key={item}
          className={`inline-flex max-w-full break-words rounded-full px-3 py-2 text-sm font-medium ring-1 ${pillClassName}`}
          title={item}
        >
          {item}
        </span>
      ))}
    </div>
  </div>
);

const SectionTitle: React.FC<{
  icon: React.ComponentType<{ className?: string }>;
  color: string;
  title: string;
  compact?: boolean;
}> = ({ icon: Icon, color, title, compact = false }) => (
  <div className="flex items-center gap-2">
    <Icon className={`${compact ? 'h-4 w-4' : 'h-5 w-5'} ${color}`} />
    <h4 className={`${compact ? 'text-sm' : 'text-base'} font-semibold text-neutral-900`}>{title}</h4>
  </div>
);

const DetailMetricCard: React.FC<{ label: string; value: string }> = ({ label, value }) => (
  <div className="rounded-[14px] bg-neutral-50 px-3 py-3 ring-1 ring-neutral-200">
    <div className="text-[11px] font-semibold uppercase tracking-[0.1em] text-neutral-400">{label}</div>
    <div className="mt-1 text-sm font-medium text-neutral-900">{value}</div>
  </div>
);

const EmptyState: React.FC<{
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  description: string;
}> = ({ icon: Icon, title, description }) => (
  <div className="flex min-h-[18rem] flex-col items-center justify-center px-6 text-center">
    <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-white text-neutral-300 shadow-sm ring-1 ring-neutral-200">
      <Icon className="h-7 w-7" />
    </div>
    <p className="text-base font-semibold text-neutral-800">{title}</p>
    <p className="mt-1 max-w-md text-sm leading-6 text-neutral-500">{description}</p>
  </div>
);
