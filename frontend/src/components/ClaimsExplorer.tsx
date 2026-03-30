/**
 * Extracted Claims Card - MODULE 3 CLAIM EXTRACTION
 * REDESIGNED: Evidence Clusters Network View
 * 
 * Primary unit: Evidence clusters (not individual claims)
 * A cluster = group of claims from multiple papers with same intervention/outcome pair
 */

import React, { useState, useEffect } from 'react';
import {
  ChevronDown,
  ChevronUp,
  AlertTriangle,
  Activity,
  BarChart3,
  FileText,
  Zap,
  TrendingUp,
  TrendingDown,
  Minus,
  Search,
} from 'lucide-react';
import { apiClient } from '../services/api';
import type {
  EvidenceCluster,
  ClusterResponse,
  ClaimSummary,
} from '../types';

type ViewMode = 'clusters' | 'conflicts' | 'entities';
type SortBy = 'confidence' | 'evidence_count' | 'conflicts';

interface ClaimsExplorerProps {
  missionId: string;
}

/**
 * MAIN COMPONENT: Extracted Claims Card
 * Container structure remains unchanged (per user requirement)
 */
export const ClaimsExplorer: React.FC<ClaimsExplorerProps> = ({ missionId }) => {
  const [clusters, setClusters] = useState<EvidenceCluster[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [viewMode, setViewMode] = useState<ViewMode>('clusters');
  const [sortBy, setSortBy] = useState<SortBy>('confidence');
  const [searchQuery, setSearchQuery] = useState('');
  const [expandedClusterId, setExpandedClusterId] = useState<string | null>(null);

  useEffect(() => {
    loadClusters();
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

  const getFilteredClusters = (): EvidenceCluster[] => {
    let filtered = clusters;

    // Filter by view mode
    if (viewMode === 'conflicts') {
      filtered = filtered.filter((c) => c.contradiction_signal.has_conflict);
    }

    // Filter by search query
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase();
      filtered = filtered.filter(
        (c) =>
          c.cluster_key.intervention_canonical.toLowerCase().includes(query) ||
          c.cluster_key.outcome_canonical.toLowerCase().includes(query)
      );
    }

    // Sort
    switch (sortBy) {
      case 'confidence':
        filtered.sort((a, b) => b.statistics.avg_confidence - a.statistics.avg_confidence);
        break;
      case 'evidence_count':
        filtered.sort((a, b) => b.claim_count - a.claim_count);
        break;
      case 'conflicts':
        filtered.sort((a, b) => {
          const aHasConflict = a.contradiction_signal.has_conflict ? 1 : 0;
          const bHasConflict = b.contradiction_signal.has_conflict ? 1 : 0;
          return bHasConflict - aHasConflict;
        });
        break;
    }

    return filtered;
  };

  const filteredClusters = getFilteredClusters();

  if (loading) {
    return (
      <div className="bg-white rounded-lg shadow p-6">
        <div className="flex items-center justify-center h-64">
          <div className="text-center">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
            <p className="text-gray-600">Loading evidence clusters...</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-lg shadow">
      {/* HEADER with View Toggles */}
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

      {/* ERROR STATE */}
      {error && (
        <div className="border-b border-gray-200 bg-red-50 p-4">
          <div className="flex items-start gap-3">
            <AlertTriangle className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
            <div>
              <p className="text-sm font-medium text-red-900">Error loading clusters</p>
              <p className="text-sm text-red-700 mt-1">{error}</p>
              <button
                onClick={loadClusters}
                className="mt-2 text-sm font-medium text-red-600 hover:text-red-800 underline"
              >
                Retry
              </button>
            </div>
          </div>
        </div>
      )}

      {/* CONTENT BASED ON VIEW MODE */}
      <div className="border-b border-gray-200">
        {viewMode === 'clusters' && (
          <ClustersView
            clusters={filteredClusters}
            expandedClusterId={expandedClusterId}
            onExpandChange={setExpandedClusterId}
          />
        )}

        {viewMode === 'conflicts' && (
          <ConflictsView
            clusters={filteredClusters}
            expandedClusterId={expandedClusterId}
            onExpandChange={setExpandedClusterId}
          />
        )}

        {viewMode === 'entities' && (
          <EntitiesView clusters={clusters} />
        )}
      </div>
    </div>
  );
};

/**
 * CARD HEADER: View toggles, sort, search
 */
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
    <div className="border-b border-gray-200 p-6">
      {/* Title Row */}
      <div className="flex items-center gap-3 mb-4">
        <FileText className="w-6 h-6 text-blue-600" />
        <h3 className="text-xl font-semibold text-gray-900">Extracted Claims</h3>
        <span className="text-sm text-gray-500 ml-auto">
          {viewMode === 'conflicts'
            ? `${totalClaimsInViewMode} clusters with conflicts`
            : `${totalClaimsInViewMode} clusters (${totalClusters} total)`}
        </span>
      </div>

      {/* View Mode Toggles */}
      <div className="flex gap-2 mb-4">
        {viewModes.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => onViewModeChange(id as ViewMode)}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg font-medium text-sm transition ${
              viewMode === id
                ? 'bg-blue-600 text-white shadow-lg'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
          >
            <Icon className="w-4 h-4" />
            {label}
          </button>
        ))}
      </div>

      {/* Search and Sort Row */}
      <div className="flex gap-4">
        {/* Search */}
        <div className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            type="text"
            placeholder="Search interventions or outcomes..."
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            className="w-full px-10 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
          />
        </div>

        {/* Sort Dropdown */}
        <select
          value={sortBy}
          onChange={(e) => onSortChange(e.target.value as SortBy)}
          className="px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm font-medium"
        >
          <option value="confidence">Sort: Confidence ↓</option>
          <option value="evidence_count">Sort: Evidence Count ↓</option>
          <option value="conflicts">Sort: Conflicts First</option>
        </select>
      </div>
    </div>
  );
};

/**
 * CLUSTERS VIEW: Main evidence clusters display
 */
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
    return (
      <div className="p-12 text-center">
        <BarChart3 className="w-12 h-12 text-gray-300 mx-auto mb-4" />
        <p className="text-gray-600 font-medium mb-1">No evidence clusters</p>
        <p className="text-gray-500 text-sm">
          Start by extracting claims from papers to see evidence clusters
        </p>
      </div>
    );
  }

  return (
    <div>
      {clusters.map((cluster, idx) => {
        const clusterId = `${cluster.cluster_key.intervention_canonical}-${cluster.cluster_key.outcome_canonical}-${idx}`;
        const isExpanded = expandedClusterId === clusterId;

        return (
          <div key={clusterId} className="border-b border-gray-100 last:border-0">
            {/* Cluster Row */}
            <ClusterRow
              cluster={cluster}
              isExpanded={isExpanded}
              onToggleExpand={() =>
                onExpandChange(isExpanded ? null : clusterId)
              }
            />

            {/* Expanded Details */}
            {isExpanded && (
              <ExpandedClusterDetail cluster={cluster} />
            )}
          </div>
        );
      })}
    </div>
  );
};

/**
 * CLUSTER ROW: Individual cluster summary row
 */
interface ClusterRowProps {
  cluster: EvidenceCluster;
  isExpanded: boolean;
  onToggleExpand: () => void;
}

const ClusterRow: React.FC<ClusterRowProps> = ({
  cluster,
  isExpanded,
  onToggleExpand,
}) => {
  const confidenceColor =
    cluster.statistics.avg_confidence >= 0.7
      ? 'text-green-600'
      : cluster.statistics.avg_confidence >= 0.5
      ? 'text-blue-600'
      : cluster.statistics.avg_confidence >= 0.3
      ? 'text-yellow-600'
      : 'text-red-600';

  const confidencePercent = (cluster.statistics.avg_confidence * 100).toFixed(0);

  return (
    <button
      onClick={onToggleExpand}
      className="w-full text-left hover:bg-gray-50 transition p-4"
    >
      <div className="flex items-center gap-4">
        {/* Expand Icon */}
        <div className="w-6 h-6 flex-shrink-0">
          {isExpanded ? (
            <ChevronUp className="w-6 h-6 text-gray-400" />
          ) : (
            <ChevronDown className="w-6 h-6 text-gray-400" />
          )}
        </div>

        {/* Intervention → Outcome */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 text-sm font-medium text-gray-900 truncate">
            <span className="truncate">{cluster.cluster_key.intervention_canonical}</span>
            <TrendingUp className="w-4 h-4 text-gray-400 flex-shrink-0" />
            <span className="truncate">{cluster.cluster_key.outcome_canonical}</span>
          </div>
        </div>

        {/* Claim Count */}
        <div className="px-3 py-1 bg-gray-100 rounded text-xs font-medium text-gray-700 flex-shrink-0">
          {cluster.claim_count} claims
        </div>

        {/* Evidence Bar */}
        <EvidenceBar
          supporting={cluster.evidence_bar.supporting}
          contradicting={cluster.evidence_bar.contradicting}
          null={cluster.evidence_bar.null}
        />

        {/* Confidence Gauge */}
        <div className="flex-shrink-0 w-20 text-right">
          <div className={`text-lg font-bold ${confidenceColor}`}>
            {confidencePercent}%
          </div>
          <div className="text-xs text-gray-500">confidence</div>
        </div>

        {/* Best Evidence Type */}
        <div className="px-2 py-1 bg-blue-50 rounded text-xs font-medium text-blue-700 flex-shrink-0">
          {cluster.best_evidence_type}
        </div>

        {/* Contradiction Signal */}
        {cluster.contradiction_signal.has_conflict && (
          <div className="flex-shrink-0">
            <AlertTriangle className={`w-5 h-5 ${
              cluster.contradiction_signal.severity === 'HIGH'
                ? 'text-red-500'
                : cluster.contradiction_signal.severity === 'MEDIUM'
                ? 'text-orange-500'
                : 'text-yellow-500'
            }`} />
          </div>
        )}
      </div>
    </button>
  );
};

/**
 * EVIDENCE BAR: Stacked bar showing supporting/contradicting/null claims
 */
interface EvidenceBarProps {
  supporting: number;
  contradicting: number;
  null: number;
}

const EvidenceBar: React.FC<EvidenceBarProps> = ({
  supporting,
  contradicting,
  null: nullCount,
}) => {
  const total = supporting + contradicting + nullCount;
  if (total === 0) return null;

  const supportingPct = (supporting / total) * 100;
  const contradictingPct = (contradicting / total) * 100;
  const nullPct = (nullCount / total) * 100;

  return (
    <div className="flex items-center gap-2 flex-shrink-0">
      <div className="flex h-2 w-24 rounded-full overflow-hidden bg-gray-200">
        {supporting > 0 && (
          <div
            className="bg-green-500"
            style={{ width: `${supportingPct}%` }}
            title={`${supporting} supporting`}
          />
        )}
        {contradicting > 0 && (
          <div
            className="bg-red-500"
            style={{ width: `${contradictingPct}%` }}
            title={`${contradicting} contradicting`}
          />
        )}
        {nullCount > 0 && (
          <div
            className="bg-gray-400"
            style={{ width: `${nullPct}%` }}
            title={`${nullCount} null results`}
          />
        )}
      </div>
      <div className="text-xs text-gray-600 w-12 text-right">
        {supporting}/{contradicting}/{nullCount}
      </div>
    </div>
  );
};

/**
 * EXPANDED CLUSTER DETAIL: Two-column layout
 */
interface ExpandedClusterDetailProps {
  cluster: EvidenceCluster;
}

const ExpandedClusterDetail: React.FC<ExpandedClusterDetailProps> = ({
  cluster,
}) => {
  return (
    <div className="bg-gray-50 border-t border-gray-100 p-6 grid grid-cols-1 lg:grid-cols-3 gap-6">
      {/* Left: Claims List */}
      <div className="lg:col-span-2">
        <h4 className="text-sm font-semibold text-gray-900 mb-4 flex items-center gap-2">
          <FileText className="w-4 h-4 text-blue-600" />
          Claims in Cluster ({cluster.claims_summary.length})
        </h4>
        <div className="space-y-3 max-h-96 overflow-y-auto">
          {cluster.claims_summary.map((claim, idx) => (
            <ClaimRowDetail key={idx} claim={claim} />
          ))}
        </div>
      </div>

      {/* Right: Metadata Panel */}
      <div className="space-y-4">
        {/* Statistics */}
        <div className="bg-white rounded-lg p-4 border border-gray-200">
          <h5 className="text-xs font-semibold text-gray-700 mb-3 uppercase">
            Statistics
          </h5>
          <div className="space-y-2 text-xs">
            <div className="flex justify-between">
              <span className="text-gray-600">Average Confidence</span>
              <span className="font-medium text-gray-900">
                {(cluster.statistics.avg_confidence * 100).toFixed(0)}%
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-600">Confidence Range</span>
              <span className="font-medium text-gray-900">
                {(cluster.statistics.min_confidence * 100).toFixed(0)}%–
                {(cluster.statistics.max_confidence * 100).toFixed(0)}%
              </span>
            </div>
          </div>
        </div>

        {/* Contradiction Info */}
        {cluster.contradiction_signal.has_conflict && (
          <div className="bg-red-50 rounded-lg p-4 border border-red-200">
            <h5 className="text-xs font-semibold text-red-900 mb-2 flex items-center gap-1">
              <AlertTriangle className="w-3 h-3" />
              Conflict Detected
            </h5>
            <p className="text-xs text-red-700">
              {cluster.contradiction_signal.pairs.length} contradicting claim pair(s)
            </p>
          </div>
        )}

        {/* Evidence Gaps */}
        {cluster.evidence_gaps.length > 0 && (
          <div className="bg-yellow-50 rounded-lg p-4 border border-yellow-200">
            <h5 className="text-xs font-semibold text-yellow-900 mb-2 flex items-center gap-1">
              <Zap className="w-3 h-3" />
              Evidence Gaps ({cluster.evidence_gaps.length})
            </h5>
            <ul className="text-xs text-yellow-700 space-y-1">
              {cluster.evidence_gaps.map((gap, idx) => (
                <li key={idx} className="flex gap-2">
                  <span className="flex-shrink-0 font-bold">•</span>
                  <span>{gap.description}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
};

/**
 * CLAIM ROW DETAIL: Individual claim within cluster
 */
interface ClaimRowDetailProps {
  claim: ClaimSummary;
}

const ClaimRowDetail: React.FC<ClaimRowDetailProps> = ({ claim }) => {
  const directionIcon =
    claim.direction === 'positive' ? (
      <TrendingUp className="w-3 h-3 text-green-600" />
    ) : claim.direction === 'negative' ? (
      <TrendingDown className="w-3 h-3 text-red-600" />
    ) : (
      <Minus className="w-3 h-3 text-gray-600" />
    );

  const confidenceColor =
    claim.confidence >= 0.7
      ? 'text-green-600'
      : claim.confidence >= 0.5
      ? 'text-blue-600'
      : 'text-yellow-600';

  return (
    <div className="bg-white rounded p-3 border border-gray-200 text-xs space-y-2">
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-start gap-2 flex-1 min-w-0">
          {directionIcon}
          <p className="text-gray-900 whitespace-normal">{claim.statement}</p>
        </div>
        <span className={`font-bold flex-shrink-0 ${confidenceColor}`}>
          {(claim.confidence * 100).toFixed(0)}%
        </span>
      </div>
      <div className="flex items-center justify-between text-gray-600">
        <span>{claim.claim_type}</span>
        <span className="truncate">{claim.paper_title}</span>
      </div>
    </div>
  );
};

/**
 * CONFLICTS VIEW: Show only clusters with contradictions
 */
interface ConflictsViewProps {
  clusters: EvidenceCluster[];
  expandedClusterId: string | null;
  onExpandChange: (id: string | null) => void;
}

const ConflictsView: React.FC<ConflictsViewProps> = ({
  clusters,
  expandedClusterId,
  onExpandChange,
}) => {
  if (clusters.length === 0) {
    return (
      <div className="p-12 text-center">
        <AlertTriangle className="w-12 h-12 text-gray-300 mx-auto mb-4" />
        <p className="text-gray-600 font-medium mb-1">No conflicts detected</p>
        <p className="text-gray-500 text-sm">
          The evidence is aligned across all clusters
        </p>
      </div>
    );
  }

  return (
    <div>
      {clusters.map((cluster, idx) => (
        <div key={idx} className="border-b border-gray-100 last:border-0 p-4">
          <div className="bg-red-50 rounded-lg p-4 border border-red-200">
            <div className="flex items-start gap-4">
              <AlertTriangle className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
              <div className="flex-1 min-w-0">
                <h4 className="text-sm font-semibold text-red-900 mb-2">
                  {cluster.cluster_key.intervention_canonical} →{' '}
                  {cluster.cluster_key.outcome_canonical}
                </h4>
                <div className="space-y-3">
                  {cluster.contradiction_signal.pairs.map((pair, pIdx) => (
                    <div
                      key={pIdx}
                      className="text-xs bg-white rounded p-3 border border-red-100"
                    >
                      <div className="flex items-center gap-2 mb-1">
                        <TrendingUp className="w-3 h-3 text-green-600" />
                        <span className="font-medium">{pair.claim1_paper}</span>
                      </div>
                      <p className="text-gray-700 mb-3">
                        Positive evidence: [claim 1]
                      </p>

                      <div className="flex items-center gap-2 mb-1">
                        <TrendingDown className="w-3 h-3 text-red-600" />
                        <span className="font-medium">{pair.claim2_paper}</span>
                      </div>
                      <p className="text-gray-700">
                        Contradictory evidence: [claim 2]
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
};

/**
 * ENTITIES VIEW: Canonical entities vocabulary
 */
interface EntitiesViewProps {
  clusters: EvidenceCluster[];
}

const EntitiesView: React.FC<EntitiesViewProps> = ({ clusters }) => {
  // Extract unique canonical entities
  const interventions = new Set<string>();
  const outcomes = new Set<string>();

  clusters.forEach((cluster) => {
    interventions.add(cluster.cluster_key.intervention_canonical);
    outcomes.add(cluster.cluster_key.outcome_canonical);
  });

  if (interventions.size === 0 && outcomes.size === 0) {
    return (
      <div className="p-12 text-center">
        <Activity className="w-12 h-12 text-gray-300 mx-auto mb-4" />
        <p className="text-gray-600 font-medium mb-1">No entities found</p>
        <p className="text-gray-500 text-sm">
          Extract claims to see canonical entities
        </p>
      </div>
    );
  }

  return (
    <div className="p-6 grid grid-cols-1 lg:grid-cols-2 gap-6">
      {/* Interventions */}
      <div>
        <h4 className="text-sm font-semibold text-gray-900 mb-4 flex items-center gap-2">
          <Zap className="w-4 h-4 text-blue-600" />
          Interventions ({interventions.size})
        </h4>
        <div className="space-y-2">
          {Array.from(interventions)
            .sort()
            .map((entity, idx) => (
              <div
                key={idx}
                className="px-4 py-2 bg-blue-50 rounded-lg border border-blue-100 text-sm text-gray-900"
              >
                {entity}
              </div>
            ))}
        </div>
      </div>

      {/* Outcomes */}
      <div>
        <h4 className="text-sm font-semibold text-gray-900 mb-4 flex items-center gap-2">
          <Activity className="w-4 h-4 text-purple-600" />
          Outcomes ({outcomes.size})
        </h4>
        <div className="space-y-2">
          {Array.from(outcomes)
            .sort()
            .map((entity, idx) => (
              <div
                key={idx}
                className="px-4 py-2 bg-purple-50 rounded-lg border border-purple-100 text-sm text-gray-900"
              >
                {entity}
              </div>
            ))}
        </div>
      </div>
    </div>
  );
};
