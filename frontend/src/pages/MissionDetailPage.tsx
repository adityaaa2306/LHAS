import React from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ArrowLeft,
  FileText,
  Activity,
  Clock,
  Loader,
  Pause,
  Play,
  Edit2,
  Zap,
  AlertCircle,
  ChevronRight,
  RotateCw,
  BookOpen,
  Lightbulb,
  CheckCircle2,
  AlertTriangle,
  BarChart3,
  X,
} from 'lucide-react';
import { apiClient } from '@/services/api';
import { PaperLevelGraph, ComparisonGraph, MissionLevelGraph } from '@/components/CEGCGraphs';
import { ClaimsExplorer } from '@/components/ClaimsExplorer';
import { AlignmentMonitorPanel } from '@/components/AlignmentMonitorPanel';
import { ContradictionHandlingPanel } from '@/components/ContradictionHandlingPanel';
import { MemorySystemPanel } from '@/components/MemorySystemPanel';
import { ScrollFadePanel } from '@/components/ScrollFadePanel';
import type { ConfirmedContradiction, MemoryOverview, MissionSnapshot, MonitoringOverview, SynthesisVersion } from '@/types';

interface MissionDetailData {
  id: string;
  name: string;
  query: string;
  intent_type: string;
  status: string;
  health: string;
  papers: number;
  claims: number;
  confidence: number;
  sessions: number;
  active_alerts: number;
  created_at: string;
  updated_at: string;
  last_run?: string;
  pico?: { population: string; intervention: string; comparator: string; outcome: string };
  confidence_initial?: number;
  key_concepts?: string[];
  ambiguity_flags?: string[];
}

type MissionSectionId =
  | 'dashboard'
  | 'synthesis'
  | 'papers'
  | 'claims'
  | 'memory'
  | 'contradictions'
  | 'alignment'
  | 'reasoning'
  | 'timeline';

export const MissionDetailPage: React.FC = () => {
  const { missionId } = useParams<{ missionId: string }>();
  const navigate = useNavigate();
  const [mission, setMission] = React.useState<MissionDetailData | null>(null);
  const [papers, setPapers] = React.useState<any[]>([]);
  const [synthesis, setSynthesis] = React.useState<SynthesisVersion | null>(null);
  const [synthesisHistory, setSynthesisHistory] = React.useState<SynthesisVersion[]>([]);
  const [claims, setClaims] = React.useState<any[]>([]);
  const [confirmedContradictions, setConfirmedContradictions] = React.useState<ConfirmedContradiction[]>([]);
  const [memorySnapshots, setMemorySnapshots] = React.useState<MissionSnapshot[]>([]);
  const [reasoning, setReasoning] = React.useState<any[]>([]);
  const [timeline, setTimeline] = React.useState<any[]>([]);
  const [memoryOverview, setMemoryOverview] = React.useState<MemoryOverview | null>(null);
  const [monitoringOverview, setMonitoringOverview] = React.useState<MonitoringOverview | null>(null);
  const [activeSection, setActiveSection] = React.useState<MissionSectionId>('dashboard');
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [expandedTimelineId, setExpandedTimelineId] = React.useState<string | null>(null);
  
  // Graph data
  const [graphStats, setGraphStats] = React.useState<any>(null);
  const [graphLoading, _setGraphLoading] = React.useState(false);
  
  // Comparison feature
  const [comparisonMode, setComparisonMode] = React.useState(false);
  const [selectedPapers, setSelectedPapers] = React.useState<string[]>([]);
  
  // Paper-level graph
  const [expandedPaperGraph, setExpandedPaperGraph] = React.useState<string | null>(null);
  
  // Ingestion state
  const [isIngesting, setIsIngesting] = React.useState(false);
  const [isGeneratingSynthesis, setIsGeneratingSynthesis] = React.useState(false);
  const [ingestionError, setIngestionError] = React.useState<string | null>(null);
  const pollingInterval = React.useRef<ReturnType<typeof setInterval> | null>(null);

  React.useEffect(() => {
    if (!missionId) return;

    const fetchMissionData = async () => {
      try {
        setLoading(true);
        setError(null);

        // PHASE 1: Load critical data in parallel — including ingestion status from DB
        console.log('📊 Loading mission detail, papers, and ingestion status...');
        const [missionData, papersData, ingestionStatusData] = await Promise.all([
          apiClient.getMissionDetail(missionId).catch(() => null),
          apiClient.getMissionPapers(missionId).catch(() => null),
          apiClient.getIngestionStatus(missionId).catch(() => null),
        ]);

        setMission(missionData as MissionDetailData);
        const loadedPapers = (papersData as any)?.papers || [];
        setPapers(loadedPapers);
        setLoading(false);

        // PHASE 2: Load optional data (non-blocking)
        console.log('Loading synthesis...');
        Promise.all([
          apiClient.getMissionSynthesis(missionId),
          apiClient.getSynthesisHistory(missionId, 6),
        ])
          .then(([latest, history]) => {
            setSynthesis(latest.synthesis ?? null);
            setSynthesisHistory(history.history || []);
          })
          .catch(err => console.warn('Synthesis load failed:', err));

        setTimeout(() => {
          console.log('🎯 Loading claims...');
          apiClient.getMissionClaims(missionId)
            .then(data => setClaims((data as any)?.claims || []))
            .catch(err => console.warn('Claims load failed:', err));
        }, 200);

        setTimeout(() => {
          console.log('⚡ Loading confirmed contradictions...');
          apiClient.getConfirmedContradictions(missionId)
            .then(data => setConfirmedContradictions((data as any)?.contradictions || []))
            .catch(err => console.warn('Confirmed contradictions load failed:', err));
        }, 300);

        if (loadedPapers.length > 0) {
          apiClient.getMissionGraphStats(missionId)
            .then(data => setGraphStats(data))
            .catch(err => console.warn('Graph stats load failed:', err));
        }

        setTimeout(() => {
          console.log('🧠 Loading reasoning...');
          apiClient.getMissionReasoning(missionId)
            .then(data => setReasoning((data as any)?.reasoning_steps || []))
            .catch(err => console.warn('Reasoning load failed:', err));
        }, 400);

        setTimeout(() => {
          console.log('⏰ Loading timeline...');
          apiClient.getMissionTimeline(missionId)
            .then(data => setTimeline((data as any)?.timeline || []))
            .catch(err => console.warn('Timeline load failed:', err));
        }, 600);

        setTimeout(() => {
          console.log('🧠 Loading memory overview...');
          apiClient.getMemoryOverview(missionId)
            .then(data => setMemoryOverview(data as MemoryOverview))
            .catch(err => console.warn('Memory overview load failed:', err));
        }, 150);

        setTimeout(() => {
          console.log('📈 Loading memory snapshots...');
          apiClient.getMemorySnapshots(missionId)
            .then(data => setMemorySnapshots((data as any)?.snapshots || []))
            .catch(err => console.warn('Memory snapshots load failed:', err));
        }, 180);

        setTimeout(() => {
          console.log('🛡️ Loading monitoring overview...');
          apiClient.getMonitoringOverview(missionId)
            .then(data => setMonitoringOverview(data as MonitoringOverview))
            .catch(err => console.warn('Monitoring overview load failed:', err));
        }, 250);

        // Decide ingestion state based on the DB's ingestion_status — never use local flag
        const ingStatus = ingestionStatusData?.status || 'idle';
        console.log('🔍 Ingestion status from DB:', ingStatus);

        if (ingStatus === 'processing' || ingStatus === 'pending') {
          // Already running in background — just resume polling
          console.log('▶️ Resuming poll for in-progress ingestion...');
          setIsIngesting(true);
        } else if (ingStatus === 'idle' && loadedPapers.length === 0) {
          // Fresh mission with no papers — auto-trigger
          console.log('🚀 Auto-triggering ingestion for mission:', missionId);
          apiClient.triggerIngestion(missionId)
            .then((res) => {
              console.log('✅ Ingestion started:', res.status);
              if (res.status === 'started' || res.status === 'already_running') {
                setIsIngesting(true);
              }
            })
            .catch(err => console.error('❌ Ingestion trigger failed:', err));
        } else if (ingStatus === 'failed') {
          // Show the stored error so user can retry
          setIngestionError(ingestionStatusData?.error || 'Previous ingestion failed. Click Retry to try again.');
        }
        // 'completed' — do nothing, papers already loaded above
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load mission');
        console.error('Mission detail fetch error:', err);
        setLoading(false);
      }
    };

    fetchMissionData();
  }, [missionId]); // Only depends on missionId — not on local ingestion state

  // Poll the dedicated ingestion status endpoint every 3 seconds while ingesting.
  // When the job reaches "completed" or "failed" we stop polling and refresh papers.
  React.useEffect(() => {
    if (!missionId || !isIngesting) return;

    // Hard timeout: if still "processing" after 10 minutes, treat as failed
    const hardTimeout = setTimeout(() => {
      console.warn('⏰ Ingestion hard timeout (10 min) — stopping poll.');
      setIsIngesting(false);
    }, 10 * 60 * 1000);

    const pollStatus = async () => {
      try {
        const statusData = await apiClient.getIngestionStatus(missionId);
        console.log('📊 Ingestion status:', statusData.status, `${statusData.progress}%`);

        if (statusData.status === 'completed' || statusData.status === 'failed') {
          setIsIngesting(false);
          clearTimeout(hardTimeout);
          if (pollingInterval.current) {
            clearInterval(pollingInterval.current);
          }
          if (statusData.status === 'completed') {
            setIngestionError(null);
            // Refresh papers now that ingestion is done
            apiClient.getMissionPapers(missionId)
              .then(data => setPapers((data as any)?.papers || []))
              .catch(err => console.warn('Paper refresh failed:', err));
          } else {
            console.error('❌ Ingestion failed:', statusData.error);
            setIngestionError(statusData.error || 'Ingestion failed. Try again.');
          }
        }
      } catch (err) {
        console.error('Error polling ingestion status:', err);
      }
    };

    pollingInterval.current = setInterval(pollStatus, 3000);

    return () => {
      clearTimeout(hardTimeout);
      if (pollingInterval.current) {
        clearInterval(pollingInterval.current);
      }
    };
  }, [missionId, isIngesting]);

  const handleRegenerateSynthesis = React.useCallback(async () => {
    if (!missionId) return;
    try {
      setIsGeneratingSynthesis(true);
      const generated = await apiClient.generateSynthesis(missionId, 'operator_request');
      setSynthesis(generated.synthesis);

      const [historyData, timelineData, memoryData] = await Promise.all([
        apiClient.getSynthesisHistory(missionId, 6).catch(() => null),
        apiClient.getMissionTimeline(missionId).catch(() => null),
        apiClient.getMemoryOverview(missionId).catch(() => null),
      ]);

      if (historyData) setSynthesisHistory(historyData.history || []);
      if (timelineData) setTimeline((timelineData as any)?.timeline || []);
      if (memoryData) setMemoryOverview(memoryData as MemoryOverview);
      apiClient.getMonitoringOverview(missionId)
        .then(data => setMonitoringOverview(data as MonitoringOverview))
        .catch(() => null);
    } catch (err) {
      console.error('Synthesis regeneration failed:', err);
    } finally {
      setIsGeneratingSynthesis(false);
    }
  }, [missionId]);

  const positiveClaims = claims.filter((c) => c.direction === 'positive').length;
  const negativeClaims = claims.filter((c) => c.direction === 'negative').length;
  const neutralClaims = claims.filter((c) => c.direction === 'null' || c.direction === 'unclear' || !c.direction).length;
  const evidenceTotal = positiveClaims + negativeClaims + neutralClaims;
  const positivePct = evidenceTotal > 0 ? (positiveClaims / evidenceTotal) * 100 : 0;
  const negativePct = evidenceTotal > 0 ? (negativeClaims / evidenceTotal) * 100 : 0;
  const activeCycleNumber = memoryOverview?.latest_snapshot?.cycle_number ?? mission?.sessions ?? 0;
  const displayedHealth = monitoringOverview?.overall_health ?? mission?.health ?? 'UNKNOWN';
  const displayedAlertCount = monitoringOverview?.active_alert_count ?? mission?.active_alerts ?? 0;
  const sectionItems: Array<{
    id: MissionSectionId;
    label: string;
    description: string;
    icon: React.ComponentType<{ size?: number; className?: string }>;
    badge?: string;
  }> = [
    {
      id: 'dashboard',
      label: 'Dashboard',
      description: 'Mission status, synthesis, alerts, and trajectory at a glance.',
      icon: BarChart3,
    },
    {
      id: 'synthesis',
      label: 'Central Synthesis',
      description: 'Current mission conclusion and synthesis history.',
      icon: Lightbulb,
      badge: synthesis ? `v${synthesis.version_number}` : undefined,
    },
    {
      id: 'papers',
      label: 'Evidence Papers',
      description: 'Browse the ingested literature for this mission.',
      icon: FileText,
      badge: papers.length ? String(papers.length) : undefined,
    },
    {
      id: 'claims',
      label: 'Extracted Claims',
      description: 'Clustered evidence claims and entities.',
      icon: Activity,
      badge: claims.length ? String(claims.length) : undefined,
    },
    {
      id: 'memory',
      label: 'Memory System',
      description: 'Graph state, provenance, drift, and checkpoints.',
      icon: BookOpen,
      badge: memoryOverview?.graph?.node_count ? String(memoryOverview.graph.node_count) : undefined,
    },
    {
      id: 'contradictions',
      label: 'Contradiction Handling',
      description: 'Confirmed conflicts and context-resolved pairs.',
      icon: AlertTriangle,
      badge: memoryOverview?.graph?.contradictions ? String(memoryOverview.graph.contradictions) : undefined,
    },
    {
      id: 'alignment',
      label: 'Alignment Monitor',
      description: 'Oversight signals, alerts, and mission health.',
      icon: Zap,
      badge: displayedAlertCount ? String(displayedAlertCount) : undefined,
    },
    {
      id: 'reasoning',
      label: 'Reasoning',
      description: 'Belief-revision audit trail for this mission.',
      icon: RotateCw,
      badge: reasoning.length ? String(reasoning.length) : undefined,
    },
    {
      id: 'timeline',
      label: 'Mission Timeline',
      description: 'Cycle-by-cycle mission activity and events.',
      icon: Clock,
      badge: timeline.length ? String(timeline.length) : undefined,
    },
  ];

  const activeSectionMeta = sectionItems.find((section) => section.id === activeSection) ?? sectionItems[0];

  const currentConfidenceScore = memoryOverview?.belief_state?.current_confidence_score
    ?? memoryOverview?.latest_snapshot?.current_confidence_score
    ?? mission?.confidence
    ?? 0;
  const currentDominantDirection = memoryOverview?.belief_state?.dominant_evidence_direction
    ?? memoryOverview?.latest_snapshot?.dominant_evidence_direction
    ?? 'mixed';
  const contradictionTopicKey = (item: Pick<ConfirmedContradiction, 'intervention_canonical' | 'outcome_canonical'>) =>
    `${String(item.intervention_canonical || 'unknown intervention').toLowerCase()}::${String(item.outcome_canonical || 'unknown outcome').toLowerCase()}`;
  const contradictionTopics = React.useMemo(() => {
    const grouped = new Map<string, ConfirmedContradiction[]>();
    for (const item of confirmedContradictions) {
      const key = contradictionTopicKey(item);
      const current = grouped.get(key) || [];
      current.push(item);
      grouped.set(key, current);
    }
    return grouped;
  }, [confirmedContradictions]);
  const highSeverityContradictions = React.useMemo(
    () => Array.from(contradictionTopics.values()).filter((items) => items.some((item) => item.severity === 'HIGH')).length,
    [contradictionTopics],
  );
  const confidenceSeries = [...memorySnapshots]
    .sort((left, right) => left.cycle_number - right.cycle_number)
    .slice(-12)
    .map((snapshot) => ({
      cycle: snapshot.cycle_number,
      confidence: snapshot.current_confidence_score ?? 0,
    }));
  const latestSnapshot = memorySnapshots[0] ?? memoryOverview?.latest_snapshot ?? null;
  const previousSnapshot = memorySnapshots[1] ?? null;
  const latestRevisionType = memoryOverview?.belief_state?.latest_revision_type
    || memoryOverview?.belief_state?.current_revision_type
    || 'NO_UPDATE';
  const contradictionSeverityRank: Record<string, number> = { LOW: 1, MEDIUM: 2, HIGH: 3 };
  const contradictionSeverityLabel = (items: ConfirmedContradiction[]) => {
    const top = items.reduce<string | null>((current, item) => {
      if (!current) return item.severity;
      return contradictionSeverityRank[item.severity] > contradictionSeverityRank[current] ? item.severity : current;
    }, null);
    return top;
  };
  const latestCycleContradictions = React.useMemo(() => {
    if (!latestSnapshot?.timestamp) return [];
    const latestTime = new Date(latestSnapshot.timestamp).getTime();
    const previousTime = previousSnapshot?.timestamp ? new Date(previousSnapshot.timestamp).getTime() : Number.NEGATIVE_INFINITY;
    return confirmedContradictions.filter((item) => {
      if (!item.timestamp) return false;
      const itemTime = new Date(item.timestamp).getTime();
      return itemTime <= latestTime && itemTime > previousTime;
    });
  }, [confirmedContradictions, latestSnapshot, previousSnapshot]);
  const latestCycleContradictionTopics = React.useMemo(() => {
    const grouped = new Map<string, ConfirmedContradiction[]>();
    for (const item of latestCycleContradictions) {
      const key = contradictionTopicKey(item);
      const current = grouped.get(key) || [];
      current.push(item);
      grouped.set(key, current);
    }
    return Array.from(grouped.values());
  }, [latestCycleContradictions]);
  const newClaimsLastCycle = Math.max(
    0,
    (latestSnapshot?.claims_extracted_count ?? 0) - (previousSnapshot?.claims_extracted_count ?? 0),
  );
  const latestCycleContradictionSeverity = contradictionSeverityLabel(latestCycleContradictionTopics.flat());
  const latestCycleSummary = [
    `Cycle ${latestSnapshot?.cycle_number ?? activeCycleNumber}`,
    `${newClaimsLastCycle} new claim${newClaimsLastCycle === 1 ? '' : 's'}`,
    formatRevisionTypeLabel(latestRevisionType),
    latestCycleContradictionTopics.length > 0
      ? `${latestCycleContradictionTopics.length} new contradiction topic${latestCycleContradictionTopics.length === 1 ? '' : 's'}${latestCycleContradictionSeverity ? ` (${latestCycleContradictionSeverity})` : ''}`
      : '0 new contradictions',
  ].join(' · ');

  if (loading) {
    return (
      <div className="min-h-screen bg-neutral-50 flex items-center justify-center">
        <div className="text-center">
          <Loader size={48} className="animate-spin text-red-600 mx-auto mb-4" />
          <p className="text-neutral-600 font-medium">Loading mission console...</p>
        </div>
      </div>
    );
  }

  if (error || !mission) {
    return (
      <div className="min-h-screen bg-white flex items-center justify-center">
        <div className="text-center">
          <AlertCircle size={48} className="text-red-500 mx-auto mb-4" />
          <p className="text-neutral-900 font-semibold mb-2">Failed to load mission</p>
          <p className="text-neutral-600 mb-6 max-w-md">{error || 'Mission not found'}</p>
          <button
            onClick={() => navigate('/')}
            className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors font-medium"
          >
            Back to Dashboard
          </button>
        </div>
      </div>
    );
  }

  const renderActiveSection = () => {
    switch (activeSection) {
      case 'dashboard':
        return (
          <MissionDashboardSection
            currentConfidenceScore={currentConfidenceScore}
            dominantDirection={currentDominantDirection}
            overallHealth={displayedHealth}
            synthesis={synthesis}
            positiveClaims={positiveClaims}
            negativeClaims={negativeClaims}
            neutralClaims={neutralClaims}
            activeAlerts={monitoringOverview?.active_alerts || []}
            confidenceSeries={confidenceSeries}
            latestCycleSummary={latestCycleSummary}
            unresolvedContradictionCount={memoryOverview?.graph?.contradictions ?? 0}
            highSeverityContradictionCount={highSeverityContradictions}
            onOpenContradictions={() => setActiveSection('contradictions')}
            onOpenSynthesis={() => setActiveSection('synthesis')}
          />
        );
      case 'synthesis':
        return (
          <ModernSynthesisCard
            synthesis={synthesis}
            history={synthesisHistory}
            isGenerating={isGeneratingSynthesis}
            onGenerate={handleRegenerateSynthesis}
            missionClaims={claims}
            confirmedContradictions={confirmedContradictions}
            onOpenClaimsSection={() => setActiveSection('claims')}
            onOpenContradictionsSection={() => setActiveSection('contradictions')}
          />
        );
      case 'papers':
        return (
          <div className="space-y-6">
            <EvidencePapersCard
              papers={papers}
              isIngesting={isIngesting}
              ingestionError={ingestionError}
              mission={mission}
              onRetry={() => {
                setIngestionError(null);
                if (missionId) {
                  apiClient.triggerIngestion(missionId)
                    .then((res) => {
                      if (res.status === 'started' || res.status === 'already_running') setIsIngesting(true);
                    })
                    .catch(err => setIngestionError(String(err)));
                }
              }}
              onCompareClick={(paperId) => {
                setComparisonMode(true);
                setSelectedPapers([paperId]);
              }}
              onGraphClick={(paperId) => setExpandedPaperGraph(paperId)}
            />
            {graphStats && !graphLoading && <MissionGraphDashboardCard stats={graphStats} />}
          </div>
        );
      case 'claims':
        return <ClaimsExplorer missionId={missionId || ''} />;
      case 'memory':
        return <MemorySystemPanel missionId={missionId || ''} />;
      case 'contradictions':
        return <ContradictionHandlingPanel missionId={missionId || ''} />;
      case 'alignment':
        return <AlignmentMonitorPanel missionId={missionId || ''} />;
      case 'reasoning':
        return <ReasoningCard reasoning={reasoning} memoryOverview={memoryOverview} />;
      case 'timeline':
        return (
          <TimelineCard
            timeline={timeline}
            expandedId={expandedTimelineId}
            onExpandId={setExpandedTimelineId}
          />
        );
      default:
        return null;
    }
  };

  return (
    <div className="min-h-screen bg-white text-neutral-900">
      {/* Top Bar - Header Navigation */}
      <div className="sticky top-0 z-50 bg-white border-b border-neutral-200 px-4 py-3">
        <button
          onClick={() => navigate('/')}
          className="inline-flex items-center gap-2 text-neutral-600 hover:text-neutral-900 transition-colors font-medium"
        >
          <ArrowLeft size={18} />
          Back
        </button>
      </div>

      {/* Main Layout: Sidebar + Content */}
      <div className="flex h-[calc(100vh-57px)]">
        {/* LEFT SIDEBAR */}
        <div className="hidden lg:flex w-64 flex-col border-r border-neutral-200 bg-white p-6 overflow-y-auto">
          {/* Mission Identity Block */}
          <div className="mb-6">
            <h1 className="text-xl font-serif font-bold text-neutral-900 mb-2 leading-tight">
              {mission.name}
            </h1>
            <p className="text-sm italic text-neutral-600 line-clamp-3">{mission.query}</p>
            <div className="flex gap-2 mt-3">
              <span
                className={`text-xs font-semibold px-2.5 py-1 rounded-full flex items-center gap-1.5 ${
                  mission.status === 'active'
                    ? 'bg-red-50 text-red-700'
                    : mission.status === 'paused'
                      ? 'bg-amber-100 text-amber-700'
                      : mission.status === 'archived'
                        ? 'bg-green-100 text-green-700'
                        : 'bg-neutral-100 text-neutral-700'
                }`}
              >
                {mission.status === 'active' && (
                  <span className="w-1.5 h-1.5 bg-red-600 rounded-full animate-pulse" />
                )}
                {mission.status?.toUpperCase() || 'IDLE'}
              </span>
              <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-neutral-100 text-neutral-700">
                {mission.intent_type}
              </span>
            </div>
          </div>

          {/* Confidence Gauge */}
          <div className="mb-6 p-4 bg-white rounded-lg border border-neutral-200">
            <div className="text-center">
              <div className="relative w-24 h-24 mx-auto mb-2">
                <ConfidenceGauge value={mission.confidence} />
                <div className="absolute inset-0 flex flex-col items-center justify-center">
                  <span className="text-2xl font-bold text-neutral-900">
                    {Math.round(mission.confidence * 100)}%
                  </span>
                  <span className="text-xs text-neutral-600">Confidence</span>
                </div>
              </div>
            </div>
          </div>

          {/* Vitals Block */}
          <div className="mb-6 space-y-2 text-sm space-y-0">
            <VitalRow icon={FileText} label="Papers" value={papers.length} />
            <VitalRow icon={Activity} label="Claims" value={claims.length} />
            <VitalRow icon={RotateCw} label="Cycles" value={activeCycleNumber} />
            <VitalRow
              icon={AlertTriangle}
              label="Alerts"
              value={displayedAlertCount}
              highlight={displayedAlertCount > 0}
            />
            {mission.last_run && (
              <div className="flex items-center gap-2 px-2 py-1.5 text-neutral-600">
                <span className="text-xs">Last active: {formatRelativeTime(mission.last_run)}</span>
              </div>
            )}
          </div>

          {/* Evidence Balance Bar */}
          <div className="mb-6">
            <div className="text-xs font-semibold text-neutral-700 mb-2">Evidence Direction</div>
            <div className="flex gap-1 h-2 bg-neutral-200 rounded-full overflow-hidden">
              {evidenceTotal === 0 ? (
                <div className="flex-1 bg-neutral-300" />
              ) : (
                <>
                  {positivePct > 0 && (
                    <div
                      className="bg-green-500 transition-all"
                      style={{ width: `${positivePct}%` }}
                    />
                  )}
                  {negativePct > 0 && (
                    <div
                      className="bg-red-500 transition-all"
                      style={{ width: `${negativePct}%` }}
                    />
                  )}
                  {neutralClaims > 0 && (
                    <div
                      className="bg-neutral-300 transition-all"
                      style={{ width: `${((neutralClaims / evidenceTotal) * 100)}%` }}
                    />
                  )}
                </>
              )}
            </div>
            {evidenceTotal === 0 ? (
              <div className="text-xs text-neutral-600 mt-1">Awaiting evidence</div>
            ) : (
              <div className="flex justify-between text-xs text-neutral-600 mt-1">
                <span>{positivePct.toFixed(0)}% Positive</span>
                <span>{negativePct.toFixed(0)}% Negative</span>
              </div>
            )}
          </div>

          {/* System Health */}
          <div className="mb-6 p-3 rounded-lg border border-neutral-200 bg-white">
            <div className="text-xs font-semibold text-neutral-700 mb-1">System Health</div>
            <div
              className={`text-sm font-semibold flex items-center gap-2 ${
                displayedHealth === 'HEALTHY'
                  ? 'text-green-700'
                  : displayedHealth === 'DEGRADED'
                    ? 'text-amber-700'
                    : displayedHealth === 'CRITICAL'
                      ? 'text-red-700'
                      : 'text-neutral-700'
              }`}
            >
              {displayedHealth === 'HEALTHY' ? (
                <CheckCircle2 size={16} />
              ) : displayedHealth === 'DEGRADED' ? (
                <AlertTriangle size={16} />
              ) : displayedHealth === 'CRITICAL' ? (
                <AlertCircle size={16} />
              ) : (
                <span className="w-4 h-4 rounded-full bg-neutral-300" />
              )}
              {displayedHealth || 'UNKNOWN'}
            </div>
          </div>

          {/* Action Buttons */}
          <div className="space-y-2">
            <button className="w-full px-3 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg font-medium text-sm transition-colors flex items-center justify-center gap-2">
              {mission.status === 'active' ? <Pause size={16} /> : <Play size={16} />}
              {mission.status === 'active' ? 'Pause' : 'Resume'}
            </button>
            <button className="w-full px-3 py-2 bg-neutral-200 hover:bg-neutral-300 text-neutral-900 rounded-lg font-medium text-sm transition-colors flex items-center justify-center gap-2">
              <Edit2 size={16} />
              Edit Mission
            </button>
          </div>

          <div className="mt-8 border-t border-neutral-200 pt-6">
            <div className="mb-3 text-xs font-semibold uppercase tracking-[0.14em] text-neutral-500">
              Mission Sections
            </div>
            <nav className="space-y-2">
              {sectionItems.map((section) => {
                const Icon = section.icon;
                const isActive = activeSection === section.id;
                return (
                  <button
                    key={section.id}
                    onClick={() => setActiveSection(section.id)}
                    className={`w-full rounded-2xl border px-3 py-3 text-left transition-all ${
                      isActive
                        ? 'border-neutral-900 bg-neutral-950 text-white shadow-sm'
                        : 'border-neutral-200 bg-white text-neutral-800 hover:border-neutral-300 hover:bg-neutral-50'
                    }`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex min-w-0 items-start gap-3">
                        <div className={`mt-0.5 ${isActive ? 'text-white' : 'text-neutral-500'}`}>
                          <Icon size={16} />
                        </div>
                        <div className="min-w-0">
                          <div className={`text-sm font-semibold ${isActive ? 'text-white' : 'text-neutral-900'}`}>
                            {section.label}
                          </div>
                          <div className={`mt-1 text-xs leading-5 ${isActive ? 'text-neutral-300' : 'text-neutral-500'}`}>
                            {section.description}
                          </div>
                        </div>
                      </div>
                      {section.badge && (
                        <span className={`rounded-full px-2 py-1 text-[11px] font-semibold ${
                          isActive ? 'bg-white/10 text-white' : 'bg-neutral-100 text-neutral-600'
                        }`}>
                          {section.badge}
                        </span>
                      )}
                    </div>
                  </button>
                );
              })}
            </nav>
          </div>
        </div>

        {/* Mobile Sidebar - as compact top strip */}
        <div className="lg:hidden w-full bg-white border-b border-neutral-200 px-4 py-3">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h1 className="text-sm font-bold text-neutral-900">{mission.name}</h1>
              <p className="text-xs text-neutral-600">{(mission.confidence * 100).toFixed(0)}% confidence</p>
            </div>
            <div className="flex gap-2">
              <button className="p-1.5 hover:bg-neutral-100 rounded text-neutral-600 hover:text-neutral-900 transition-colors">
                <Play size={16} />
              </button>
              <button className="p-1.5 hover:bg-neutral-100 rounded text-neutral-600 hover:text-neutral-900 transition-colors">
                <Zap size={16} />
              </button>
            </div>
          </div>
        </div>

        {/* MAIN CONTENT AREA */}
        <div className="flex-1 overflow-y-auto bg-white">
          <div className="p-6 space-y-6">
            <div className="rounded-2xl border border-neutral-200/80 bg-gradient-to-r from-white via-neutral-50 to-white px-5 py-4 shadow-[0_10px_30px_rgba(15,23,42,0.04)]">
              <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.14em] text-neutral-500">
                    Mission Workspace
                  </p>
                  <h2 className="mt-1 text-2xl font-semibold tracking-[-0.03em] text-neutral-950">
                    {activeSectionMeta.label}
                  </h2>
                  <p className="mt-1 text-sm text-neutral-600">{activeSectionMeta.description}</p>
                </div>
                <div className="lg:hidden">
                  <div className="flex gap-2 overflow-x-auto pb-1">
                    {sectionItems.map((section) => {
                      const isActive = activeSection === section.id;
                      return (
                        <button
                          key={section.id}
                          onClick={() => setActiveSection(section.id)}
                          className={`shrink-0 rounded-full px-4 py-2 text-sm font-medium transition-colors ${
                            isActive
                              ? 'bg-neutral-950 text-white'
                              : 'bg-white text-neutral-700 ring-1 ring-neutral-200 hover:bg-neutral-50'
                          }`}
                        >
                          {section.label}
                        </button>
                      );
                    })}
                  </div>
                </div>
              </div>
            </div>

            <div className="space-y-6" id="mission-section-content">
              {renderActiveSection()}
            </div>
          </div>
        </div>
      </div>

      {/* Paper-Level Graph Modal */}
      {expandedPaperGraph && papers.find(p => p.id === expandedPaperGraph) && (
        <PaperGraphModal
          paper={papers.find(p => p.id === expandedPaperGraph)}
          onClose={() => setExpandedPaperGraph(null)}
        />
      )}

      {/* Comparison Modal */}
      {comparisonMode && selectedPapers.length > 0 && (
        <ComparisonModal
          missionId={missionId || ''}
          selectedPaperIds={selectedPapers}
          allPapers={papers}
          onClose={() => {
            setComparisonMode(false);
            setSelectedPapers([]);
          }}
        />
      )}
    </div>
  );
};

// ============ CONFIDENCE GAUGE ============

const ConfidenceGauge: React.FC<{ value: number }> = ({ value }) => {
  const getColor = () => {
    if (value >= 0.7) return '#22c55e';
    if (value >= 0.4) return '#f59e0b';
    return '#ef4444';
  };

  const angle = value * 180;
  const radians = (angle - 90) * (Math.PI / 180);
  const x = 50 + 35 * Math.cos(radians);
  const y = 50 + 35 * Math.sin(radians);

  return (
    <svg viewBox="0 0 100 100" className="w-full h-full">
      <circle cx="50" cy="50" r="40" fill="none" stroke="#d1d5db" strokeWidth="2" opacity="0.3" />
      <path
        d={`M 15 50 A 35 35 0 0 1 85 50`}
        fill="none"
        stroke="#e5e7eb"
        strokeWidth="3"
      />
      <path
        d={`M 15 50 A 35 35 0 0 1 ${x} ${y}`}
        fill="none"
        stroke={getColor()}
        strokeWidth="3"
        style={{
          animation: 'strokeDraw 1s ease-out',
        }}
      />
      <style>{`
        @keyframes strokeDraw {
          from { stroke-dasharray: 100; stroke-dashoffset: 100; }
          to { stroke-dasharray: 100; stroke-dashoffset: 0; }
        }
      `}</style>
    </svg>
  );
};

// ============ VITAL ROW ============

const VitalRow: React.FC<{
  icon: React.ComponentType<{ size: number }>;
  label: string;
  value: number | string;
  highlight?: boolean;
}> = ({ icon: Icon, label, value, highlight }) => (
  <div className={`flex items-center justify-between px-3 py-2.5 rounded border ${highlight ? 'bg-red-50 border-red-200' : 'bg-white border-neutral-200'}`}>
    <div className="flex items-center gap-2">
      <div className={highlight ? 'text-red-600' : 'text-neutral-600'}>
        <Icon size={16} />
      </div>
      <span className="text-neutral-700">{label}</span>
    </div>
    <span className={`font-semibold ${highlight ? 'text-red-600' : 'text-neutral-900'}`}>{value}</span>
  </div>
);

// ============ SYNTHESIS CARD ============

export const LegacySynthesisCard: React.FC<{ synthesis: any }> = ({ synthesis }) => (
  <div className="bg-white border-l-4 border-red-600 rounded-lg p-6 border border-neutral-200">
    <div className="flex items-start justify-between mb-4">
      <h2 className="text-lg font-semibold text-neutral-900 flex items-center gap-2">
        <Lightbulb size={20} className="text-red-600" />
        Central Synthesis
      </h2>
      <div className="flex items-center gap-2">
        {synthesis?.answer_confidence && (
          <span
            className={`text-xs font-semibold px-2 py-1 rounded ${
              synthesis.answer_confidence >= 0.7
                ? 'bg-green-100 text-green-700'
                : synthesis.answer_confidence >= 0.4
                  ? 'bg-amber-100 text-amber-700'
                  : 'bg-red-100 text-red-700'
            }`}
          >
            {synthesis.answer_confidence >= 0.7 ? 'STRONG' : synthesis.answer_confidence >= 0.4 ? 'MODERATE' : 'MIXED'}
          </span>
        )}
        <button className="text-neutral-600 hover:text-neutral-900 text-sm font-medium transition-colors">
          Regenerate
        </button>
      </div>
    </div>

    {!synthesis ? (
      <div className="py-12 text-center border border-dashed border-neutral-300 rounded-lg">
        <Lightbulb size={32} className="mx-auto mb-3 text-neutral-400" />
        <p className="text-neutral-700 font-medium mb-1">No synthesis generated yet</p>
        <p className="text-neutral-600 text-sm mb-4">Run an ingestion cycle to populate this section</p>
        <button className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg font-medium text-sm transition-colors">
          Run First Analysis
        </button>
      </div>
    ) : (
      <div className="space-y-4">
        <p className="text-neutral-800 leading-relaxed font-serif text-base">{synthesis.answer_text}</p>

        {synthesis.key_findings && synthesis.key_findings.length > 0 && (
          <div>
            <h3 className="text-sm font-semibold text-neutral-900 mb-2">Key Findings</h3>
            <ul className="space-y-1">
              {synthesis.key_findings.slice(0, 3).map((finding: string, idx: number) => (
                <li key={idx} className="text-sm text-neutral-700 flex items-start gap-2">
                  <span className="text-red-600 mt-0.5">→</span>
                  <span>{finding}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {synthesis.uncertainty_statement && (
          <div className="text-sm text-neutral-700 italic border-l-2 border-amber-600 pl-3 py-1">
            <span className="text-amber-700 font-semibold">Uncertainty: </span>
            {synthesis.uncertainty_statement}
          </div>
        )}
      </div>
    )}
  </div>
);

const ModernSynthesisCard: React.FC<{
  synthesis: SynthesisVersion | null;
  history: SynthesisVersion[];
  isGenerating: boolean;
  onGenerate: () => void;
  missionClaims: any[];
  confirmedContradictions: ConfirmedContradiction[];
  onOpenClaimsSection: () => void;
  onOpenContradictionsSection: () => void;
}> = ({
  synthesis,
  history,
  isGenerating,
  onGenerate,
  missionClaims,
  confirmedContradictions,
  onOpenClaimsSection,
  onOpenContradictionsSection,
}) => {
  const [detailView, setDetailView] = React.useState<'tier1' | 'contradictions' | null>(null);

  const tier1Claims = React.useMemo(() => {
    if (!synthesis) return [];
    const claimMap = new Map(missionClaims.map((claim) => [String(claim.id), claim]));
    return synthesis.claim_ids_tier1
      .map((claimId) => claimMap.get(String(claimId)))
      .filter(Boolean);
  }, [missionClaims, synthesis]);

  const includedContradictions = React.useMemo(() => {
    if (!synthesis) return [];
    const contradictionMap = new Map(confirmedContradictions.map((item) => [String(item.id), item]));
    return synthesis.contradictions_included
      .map((contradictionId) => contradictionMap.get(String(contradictionId)))
      .filter(Boolean) as ConfirmedContradiction[];
  }, [confirmedContradictions, synthesis]);
  const includedContradictionTopics = React.useMemo(() => {
    const grouped = new Map<string, ConfirmedContradiction[]>();
    for (const item of includedContradictions) {
      const key = `${String(item.intervention_canonical || 'unknown intervention').toLowerCase()}::${String(item.outcome_canonical || 'unknown outcome').toLowerCase()}`;
      const current = grouped.get(key) || [];
      current.push(item);
      grouped.set(key, current);
    }
    return Array.from(grouped.values());
  }, [includedContradictions]);

  return (
  <div className="overflow-hidden rounded-2xl border border-neutral-200/80 bg-white shadow-[0_18px_50px_rgba(15,23,42,0.06)]">
    <div className="border-b border-neutral-200 bg-gradient-to-r from-white via-neutral-50 to-white px-6 py-5">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="flex items-start gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-amber-50 text-amber-600 shadow-sm ring-1 ring-amber-100">
            <Lightbulb size={22} />
          </div>
          <div>
            <h2 className="text-[1.35rem] font-semibold tracking-[-0.02em] text-neutral-950">Central Synthesis</h2>
            <p className="mt-1 text-sm text-neutral-600">
              Versioned narrative generated from belief state, contradiction handling, and ranked evidence tiers.
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {synthesis && (
            <>
              <SynthesisPill className={tierPillClass(String(synthesis.confidence_tier))} label={String(synthesis.confidence_tier)} />
              <SynthesisPill className="bg-neutral-100 text-neutral-700 ring-neutral-200" label={`v${synthesis.version_number}`} />
              {synthesis.change_magnitude && (
                <SynthesisPill className={changePillClass(String(synthesis.change_magnitude))} label={String(synthesis.change_magnitude)} />
              )}
            </>
          )}
          <button
            onClick={onGenerate}
            disabled={isGenerating}
            className="inline-flex items-center gap-2 rounded-xl bg-neutral-950 px-4 py-2.5 text-sm font-medium text-white shadow-sm transition hover:bg-neutral-800 disabled:cursor-not-allowed disabled:opacity-60"
          >
            <RotateCw size={16} className={isGenerating ? 'animate-spin' : ''} />
            {isGenerating ? 'Generating…' : 'Regenerate'}
          </button>
        </div>
      </div>
    </div>

    {!synthesis ? (
      <div className="px-6 py-12">
        <div className="rounded-2xl border border-dashed border-neutral-300 bg-neutral-50/70 px-6 py-12 text-center">
          <Lightbulb size={32} className="mx-auto mb-3 text-neutral-400" />
          <p className="text-neutral-800 font-medium mb-1">No synthesis generated yet</p>
          <p className="text-neutral-600 text-sm mb-4">Generate the first versioned synthesis to capture this mission’s current evidence state.</p>
          <button
            onClick={onGenerate}
            disabled={isGenerating}
            className="inline-flex items-center gap-2 rounded-xl bg-red-600 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            <RotateCw size={16} className={isGenerating ? 'animate-spin' : ''} />
            {isGenerating ? 'Generating…' : 'Generate Synthesis'}
          </button>
        </div>
      </div>
    ) : (
      <div className="grid gap-0 xl:grid-cols-[minmax(0,1.7fr)_360px]">
        <div className="px-6 py-6">
          <div className="mb-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <SynthesisStatCard label="Confidence" value={`${Math.round(synthesis.confidence_score * 100)}%`} detail={String(synthesis.confidence_tier)} />
            <SynthesisStatCard label="Direction" value={formatTitleCase(String(synthesis.dominant_direction || 'mixed'))} detail={synthesis.direction_changed ? 'Changed vs prior' : 'Stable vs prior'} />
            <SynthesisStatCard
              label="Core Claims"
              value={`${synthesis.summary_metrics.tier1_count}`}
              detail={`${synthesis.summary_metrics.tier2_count} supporting`}
              actionLabel="View claims"
              onAction={() => setDetailView(detailView === 'tier1' ? null : 'tier1')}
            />
            <SynthesisStatCard
              label="Contradictions"
              value={`${includedContradictionTopics.length}`}
              detail={`${synthesis.contradictions_included.length} pair records · ${synthesis.summary_metrics.high_contradictions} high-severity topics`}
              actionLabel="View conflicts"
              onAction={() => setDetailView(detailView === 'contradictions' ? null : 'contradictions')}
            />
          </div>

          {detailView === 'tier1' && (
            <div className="mb-5 rounded-2xl border border-blue-200 bg-blue-50/70 px-5 py-5">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <h3 className="text-sm font-semibold text-blue-900">Tier 1 Core Claims</h3>
                  <p className="text-xs text-blue-700">These are the exact high-priority claims anchoring the synthesis.</p>
                </div>
                <button
                  type="button"
                  onClick={onOpenClaimsSection}
                  className="rounded-full border border-blue-200 bg-white px-3 py-1.5 text-xs font-semibold text-blue-700 transition hover:bg-blue-50"
                >
                  Open Extracted Claims
                </button>
              </div>
              <div className="mt-4 space-y-3">
                {tier1Claims.length > 0 ? (
                  tier1Claims.map((claim) => (
                    <div key={String(claim.id)} className="rounded-xl border border-white/80 bg-white/80 px-4 py-3 shadow-sm">
                      <div className="flex flex-wrap items-center gap-2 text-xs text-neutral-500">
                        <span className="rounded-full bg-neutral-100 px-2 py-1 font-semibold text-neutral-700">
                          {String(claim.claim_type || 'claim')}
                        </span>
                        <span>{Math.round((claim.composite_confidence || 0) * 100)}% confidence</span>
                        <span>·</span>
                        <span>{String(claim.direction || 'unclear')}</span>
                      </div>
                      <p className="mt-2 text-sm leading-6 text-neutral-900">
                        {String(claim.statement_normalized || claim.statement_raw || claim.statement || 'No claim text')}
                      </p>
                      {claim.paper_title && (
                        <p className="mt-2 text-xs text-neutral-500">{String(claim.paper_title)}</p>
                      )}
                    </div>
                  ))
                ) : (
                  <div className="rounded-xl border border-dashed border-blue-200 bg-white/70 px-4 py-3 text-sm text-blue-800">
                    The current synthesis references Tier 1 claim IDs, but the matching claim records are not loaded yet.
                  </div>
                )}
              </div>
            </div>
          )}

          {detailView === 'contradictions' && (
            <div className="mb-5 rounded-2xl border border-red-200 bg-red-50/70 px-5 py-5">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <h3 className="text-sm font-semibold text-red-900">Contradictions Surfaced In This Synthesis</h3>
                  <p className="text-xs text-red-700">These are the exact contradiction records the synthesis is expected to acknowledge.</p>
                </div>
                <button
                  type="button"
                  onClick={onOpenContradictionsSection}
                  className="rounded-full border border-red-200 bg-white px-3 py-1.5 text-xs font-semibold text-red-700 transition hover:bg-red-50"
                >
                  Open Contradiction Handling
                </button>
              </div>
              <div className="mt-4 space-y-3">
                {includedContradictions.length > 0 ? (
                  includedContradictions.map((item) => (
                    <div key={item.id} className="rounded-xl border border-white/80 bg-white/80 px-4 py-3 shadow-sm">
                      <div className="flex flex-wrap items-center gap-2 text-xs text-neutral-500">
                        <span className="rounded-full bg-red-100 px-2 py-1 font-semibold text-red-700">{item.severity}</span>
                        {item.edge_weight != null && <span>{Math.round(item.edge_weight * 100)}% weight</span>}
                        <span>·</span>
                        <span>{item.population_overlap} population overlap</span>
                      </div>
                      <p className="mt-2 text-sm font-semibold text-neutral-900">
                        {item.intervention_canonical || 'Unknown intervention'} · {item.outcome_canonical || 'Unknown outcome'}
                      </p>
                      <p className="mt-1 text-sm text-neutral-700">
                        {item.direction_a} vs {item.direction_b}
                      </p>
                      {item.justification && (
                        <p className="mt-2 text-xs text-neutral-500">{item.justification}</p>
                      )}
                    </div>
                  ))
                ) : (
                  <div className="rounded-xl border border-dashed border-red-200 bg-white/70 px-4 py-3 text-sm text-red-800">
                    No detailed contradiction records are linked to this synthesis yet.
                  </div>
                )}
              </div>
            </div>
          )}

          <div className="rounded-2xl border border-neutral-200 bg-neutral-50/70 px-5 py-5">
            <div className="mb-3 flex flex-wrap items-center gap-2 text-xs font-medium text-neutral-500">
              <span>Trigger: {formatTriggerLabel(synthesis.trigger_type)}</span>
              <span className="text-neutral-300">•</span>
              <span>{synthesis.word_count} words</span>
              <span className="text-neutral-300">•</span>
              <span>{synthesis.validation_passed ? 'Validated output' : 'Fallback output'}</span>
            </div>
            <div className="space-y-4 text-[15px] leading-8 text-neutral-800">
              {synthesis.synthesis_text.split(/\n\s*\n/).filter(Boolean).map((paragraph, idx) => (
                <p key={idx}>{paragraph}</p>
              ))}
            </div>
          </div>

          <div className="mt-4 rounded-2xl border border-neutral-200 bg-white px-5 py-4 shadow-sm">
            <div className="flex flex-wrap items-center gap-2 text-sm text-neutral-600">
              <span className="font-semibold text-neutral-900">Change summary</span>
              <span className="text-neutral-300">•</span>
              <span>{formatSignedPercent(synthesis.change_summary.confidence_delta)} confidence delta</span>
              <span className="text-neutral-300">•</span>
              <span>{synthesis.change_summary.new_contradictions_surfaced} contradictions surfaced</span>
              <span className="text-neutral-300">•</span>
              <span>{synthesis.direction_changed ? 'Direction changed' : 'Direction unchanged'}</span>
            </div>
          </div>
        </div>

        <div className="border-t border-neutral-200 bg-neutral-50/70 px-6 py-6 xl:border-l xl:border-t-0">
          <div className="space-y-5">
            <div>
              <h3 className="text-sm font-semibold uppercase tracking-[0.12em] text-neutral-500">Version History</h3>
              <div className="mt-3 space-y-3">
                {history.slice(0, 4).map((version) => (
                  <div key={version.id} className="rounded-2xl border border-neutral-200 bg-white px-4 py-4 shadow-sm">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-sm font-semibold text-neutral-900">Version {version.version_number}</p>
                        <p className="mt-1 text-xs text-neutral-500">
                          {formatTriggerLabel(version.trigger_type)} · {formatRelativeTime(version.created_at || '')}
                        </p>
                      </div>
                      <SynthesisPill className={tierPillClass(String(version.confidence_tier))} label={String(version.confidence_tier)} />
                    </div>
                    <p className="mt-3 text-sm leading-6 text-neutral-700 line-clamp-3">{version.synthesis_text}</p>
                  </div>
                ))}
              </div>
            </div>

            <div className="rounded-2xl border border-neutral-200 bg-white px-4 py-4 shadow-sm">
              <h3 className="text-sm font-semibold text-neutral-900">Audit snapshot</h3>
              <div className="mt-3 space-y-2 text-sm text-neutral-600">
                <p>Tier 1 claim IDs: {synthesis.claim_ids_tier1.length}</p>
                <p>Tier 2 claim IDs: {synthesis.claim_ids_tier2.length}</p>
                <p>Tier 3 claim IDs: {synthesis.claim_ids_tier3.length}</p>
                <p>Contradictions included: {synthesis.contradictions_included.length}</p>
                <p>{synthesis.llm_fallback ? 'Template fallback was used for this version.' : 'Narrative was produced by the synthesis writer.'}</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    )}
  </div>
  );
};

const SynthesisPill: React.FC<{ className: string; label: string }> = ({ className, label }) => (
  <span className={`inline-flex items-center rounded-full px-3 py-1.5 text-xs font-semibold ring-1 ${className}`}>
    {label}
  </span>
);

const SynthesisStatCard: React.FC<{
  label: string;
  value: string;
  detail: string;
  actionLabel?: string;
  onAction?: () => void;
}> = ({ label, value, detail, actionLabel, onAction }) => (
  <div className="rounded-2xl border border-neutral-200 bg-white px-4 py-4 shadow-sm">
    <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-neutral-500">{label}</p>
    <p className="mt-1 text-2xl font-semibold tracking-[-0.03em] text-neutral-950">{value}</p>
    <div className="mt-1 flex items-center justify-between gap-3">
      <p className="text-xs text-neutral-500">{detail}</p>
      {actionLabel && onAction && (
        <button
          type="button"
          onClick={onAction}
          className="shrink-0 rounded-full border border-neutral-200 bg-neutral-50 px-2.5 py-1 text-[11px] font-semibold text-neutral-700 transition hover:bg-neutral-100"
        >
          {actionLabel}
        </button>
      )}
    </div>
  </div>
);

const tierPillClass = (tier: string) =>
  tier === 'STRONG'
    ? 'bg-emerald-50 text-emerald-700 ring-emerald-200'
    : tier === 'MODERATE'
      ? 'bg-amber-50 text-amber-700 ring-amber-200'
      : tier === 'MIXED'
        ? 'bg-blue-50 text-blue-700 ring-blue-200'
        : 'bg-rose-50 text-rose-700 ring-rose-200';

const changePillClass = (magnitude: string) =>
  magnitude === 'MAJOR'
    ? 'bg-red-50 text-red-700 ring-red-200'
    : magnitude === 'MODERATE'
      ? 'bg-amber-50 text-amber-700 ring-amber-200'
      : 'bg-neutral-100 text-neutral-700 ring-neutral-200';

const formatTriggerLabel = (trigger: string | null | undefined) =>
  String(trigger || 'operator_request')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (letter) => letter.toUpperCase());

const formatTitleCase = (value: string) =>
  value.replace(/\b\w/g, (letter) => letter.toUpperCase());

const formatSignedPercent = (value: number) => `${value >= 0 ? '+' : ''}${(value * 100).toFixed(0)}%`;
const formatRevisionTypeLabel = (value: string) =>
  String(value || 'NO_UPDATE')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (letter) => letter.toUpperCase());

const formatAlertTitle = (value: string) =>
  String(value || '')
    .toLowerCase()
    .split('_')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');

const MissionDashboardSection: React.FC<{
  currentConfidenceScore: number;
  dominantDirection: string;
  overallHealth: string;
  synthesis: SynthesisVersion | null;
  positiveClaims: number;
  negativeClaims: number;
  neutralClaims: number;
  activeAlerts: MonitoringOverview['active_alerts'];
  confidenceSeries: Array<{ cycle: number; confidence: number }>;
  latestCycleSummary: string;
  unresolvedContradictionCount: number;
  highSeverityContradictionCount: number;
  onOpenContradictions: () => void;
  onOpenSynthesis: () => void;
}> = ({
  currentConfidenceScore,
  dominantDirection,
  overallHealth,
  synthesis,
  positiveClaims,
  negativeClaims,
  neutralClaims,
  activeAlerts,
  confidenceSeries,
  latestCycleSummary,
  unresolvedContradictionCount,
  highSeverityContradictionCount,
  onOpenContradictions,
  onOpenSynthesis,
}) => (
  <div className="space-y-6">
    <section className="grid gap-4 xl:grid-cols-3">
      <DashboardHeadlineCard
        label="Current Confidence"
        value={`${Math.round((currentConfidenceScore || 0) * 100)}%`}
        tone="blue"
      />
      <DashboardHeadlineCard
        label="Dominant Direction"
        value={formatTitleCase(String(dominantDirection || 'mixed'))}
        tone="neutral"
      />
      <DashboardHeadlineCard
        label="Mission Health"
        value={String(overallHealth || 'UNKNOWN')}
        tone={overallHealth === 'CRITICAL' ? 'red' : overallHealth === 'DEGRADED' || overallHealth === 'WATCH' ? 'amber' : 'green'}
      />
    </section>

    <section className="overflow-hidden rounded-2xl border border-neutral-200/80 bg-white shadow-[0_18px_50px_rgba(15,23,42,0.06)]">
      <div className="border-b border-neutral-200 bg-gradient-to-r from-white via-neutral-50 to-white px-6 py-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <h3 className="text-[1.35rem] font-semibold tracking-[-0.02em] text-neutral-950">Latest Synthesis</h3>
            <p className="mt-1 text-sm text-neutral-600">The most recent human-readable conclusion generated by the system.</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {synthesis && (
              <>
                <SynthesisPill className={tierPillClass(String(synthesis.confidence_tier))} label={String(synthesis.confidence_tier)} />
                <SynthesisPill className="bg-neutral-100 text-neutral-700 ring-neutral-200" label={`v${synthesis.version_number}`} />
              </>
            )}
            <button
              type="button"
              onClick={onOpenSynthesis}
              className="rounded-full border border-neutral-200 bg-white px-3 py-1.5 text-xs font-semibold text-neutral-700 transition hover:bg-neutral-50"
            >
              Open synthesis
            </button>
          </div>
        </div>
      </div>
      <div className="px-6 py-6">
        {synthesis ? (
          <div className="space-y-4">
            <p className="text-[15px] leading-8 text-neutral-800">
              {synthesis.synthesis_text}
            </p>
          </div>
        ) : (
          <div className="rounded-2xl border border-dashed border-neutral-300 bg-neutral-50/70 px-6 py-10 text-center text-sm text-neutral-600">
            No synthesis is available yet for this mission.
          </div>
        )}
      </div>
    </section>

    <section className="grid gap-6 xl:grid-cols-[minmax(0,1.35fr)_minmax(320px,0.85fr)]">
      <div className="space-y-6">
        <DashboardEvidenceBar
          positiveClaims={positiveClaims}
          negativeClaims={negativeClaims}
          neutralClaims={neutralClaims}
        />
        <DashboardSparklineCard points={confidenceSeries} />
        <DashboardCycleSummaryCard summary={latestCycleSummary} />
      </div>

      <div className="space-y-6">
        <DashboardAlertsCard alerts={activeAlerts} />
        <DashboardContradictionsCard
          unresolvedCount={unresolvedContradictionCount}
          highSeverityCount={highSeverityContradictionCount}
          onOpenContradictions={onOpenContradictions}
        />
      </div>
    </section>
  </div>
);

const DashboardHeadlineCard: React.FC<{
  label: string;
  value: string;
  tone: 'blue' | 'neutral' | 'green' | 'amber' | 'red';
}> = ({ label, value, tone }) => {
  const toneClasses = {
    blue: 'border-blue-200 bg-blue-50/70 text-blue-950',
    neutral: 'border-neutral-200 bg-white text-neutral-950',
    green: 'border-emerald-200 bg-emerald-50/70 text-emerald-950',
    amber: 'border-amber-200 bg-amber-50/70 text-amber-950',
    red: 'border-red-200 bg-red-50/70 text-red-950',
  } as const;

  return (
    <div className={`rounded-2xl border px-5 py-5 shadow-sm ${toneClasses[tone]}`}>
      <p className="text-[11px] font-semibold uppercase tracking-[0.14em] opacity-70">{label}</p>
      <p className="mt-2 text-3xl font-semibold tracking-[-0.04em]">{value}</p>
    </div>
  );
};

const DashboardEvidenceBar: React.FC<{
  positiveClaims: number;
  negativeClaims: number;
  neutralClaims: number;
}> = ({ positiveClaims, negativeClaims, neutralClaims }) => {
  const total = positiveClaims + negativeClaims + neutralClaims;
  const safeTotal = total || 1;
  const positiveWidth = (positiveClaims / safeTotal) * 100;
  const negativeWidth = (negativeClaims / safeTotal) * 100;
  const neutralWidth = (neutralClaims / safeTotal) * 100;

  return (
    <section className="rounded-2xl border border-neutral-200 bg-white p-5 shadow-sm">
      <h3 className="text-sm font-semibold text-neutral-900">Evidence Balance</h3>
      <p className="mt-1 text-sm text-neutral-600">
        {positiveClaims} supporting · {negativeClaims} contradicting · {neutralClaims} mixed
      </p>
      <div className="mt-4 h-3 overflow-hidden rounded-full bg-neutral-200">
        {positiveClaims > 0 && <div className="inline-block h-full bg-emerald-500" style={{ width: `${positiveWidth}%` }} />}
        {negativeClaims > 0 && <div className="inline-block h-full bg-rose-500" style={{ width: `${negativeWidth}%` }} />}
        {neutralClaims > 0 && <div className="inline-block h-full bg-slate-400" style={{ width: `${neutralWidth}%` }} />}
      </div>
    </section>
  );
};

const DashboardAlertsCard: React.FC<{
  alerts: MonitoringOverview['active_alerts'];
}> = ({ alerts }) => (
  <section className="rounded-2xl border border-neutral-200 bg-white p-5 shadow-sm">
    <h3 className="text-sm font-semibold text-neutral-900">Active Alerts</h3>
    <div className="mt-4 space-y-3">
      {alerts.length === 0 ? (
        <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
          No active alignment alerts right now.
        </div>
      ) : (
        alerts.map((alert) => (
          <div
            key={alert.id}
            className={`rounded-xl border px-4 py-3 ${
              alert.severity === 'HIGH'
                ? 'border-red-200 bg-red-50'
                : alert.severity === 'MEDIUM'
                  ? 'border-amber-200 bg-amber-50'
                  : 'border-neutral-200 bg-neutral-50'
            }`}
          >
            <div className="flex items-center justify-between gap-3">
              <span className="text-xs font-semibold uppercase tracking-[0.12em] text-neutral-600">{alert.severity}</span>
              <span className="text-xs text-neutral-500">Cycle {alert.last_cycle_number}</span>
            </div>
            <p className="mt-2 text-sm font-medium text-neutral-900">{formatAlertTitle(alert.alert_type)}</p>
            {alert.message && <p className="mt-1 text-sm text-neutral-700">{alert.message}</p>}
          </div>
        ))
      )}
    </div>
  </section>
);

const DashboardSparklineCard: React.FC<{
  points: Array<{ cycle: number; confidence: number }>;
}> = ({ points }) => {
  const width = 520;
  const height = 120;
  const padding = 12;
  const validPoints = points.length > 1 ? points : [
    { cycle: 0, confidence: points[0]?.confidence ?? 0 },
    { cycle: 1, confidence: points[0]?.confidence ?? 0 },
  ];
  const values = validPoints.map((point) => point.confidence);
  const min = Math.min(...values, 0.05);
  const max = Math.max(...values, 0.95);
  const range = max - min || 1;
  const path = validPoints
    .map((point, index) => {
      const x = padding + (index / (validPoints.length - 1)) * (width - padding * 2);
      const y = height - padding - ((point.confidence - min) / range) * (height - padding * 2);
      return `${index === 0 ? 'M' : 'L'} ${x} ${y}`;
    })
    .join(' ');

  return (
    <section className="rounded-2xl border border-neutral-200 bg-white p-5 shadow-sm">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-neutral-900">Confidence Over Time</h3>
          <p className="mt-1 text-sm text-neutral-600">Last {Math.min(points.length, 12)} cycles of confidence movement.</p>
        </div>
      </div>
      <div className="mt-4 rounded-2xl border border-neutral-200 bg-neutral-50 px-3 py-4">
        <svg viewBox={`0 0 ${width} ${height}`} className="h-28 w-full">
          <path
            d={`M ${padding} ${height - padding} L ${width - padding} ${height - padding}`}
            stroke="#d4d4d8"
            strokeWidth="1"
            fill="none"
          />
          <path d={path} stroke="#2563eb" strokeWidth="3" fill="none" strokeLinecap="round" strokeLinejoin="round" />
          {validPoints.map((point, index) => {
            const x = padding + (index / (validPoints.length - 1)) * (width - padding * 2);
            const y = height - padding - ((point.confidence - min) / range) * (height - padding * 2);
            return <circle key={`${point.cycle}-${index}`} cx={x} cy={y} r="3.5" fill="#2563eb" />;
          })}
        </svg>
      </div>
    </section>
  );
};

const DashboardCycleSummaryCard: React.FC<{ summary: string }> = ({ summary }) => (
  <section className="rounded-2xl border border-neutral-200 bg-white p-5 shadow-sm">
    <h3 className="text-sm font-semibold text-neutral-900">Last Cycle Summary</h3>
    <p className="mt-3 text-sm leading-7 text-neutral-700">{summary}</p>
  </section>
);

const DashboardContradictionsCard: React.FC<{
  unresolvedCount: number;
  highSeverityCount: number;
  onOpenContradictions: () => void;
}> = ({ unresolvedCount, highSeverityCount, onOpenContradictions }) => (
  <section className="rounded-2xl border border-neutral-200 bg-white p-5 shadow-sm">
    <h3 className="text-sm font-semibold text-neutral-900">Unresolved Contradictions</h3>
    <div className="mt-4 flex items-end justify-between gap-4">
      <div>
        <p className="text-3xl font-semibold tracking-[-0.04em] text-neutral-950">{unresolvedCount}</p>
        <p className="mt-1 text-sm text-neutral-600">
          {highSeverityCount} high severity
        </p>
      </div>
      <button
        type="button"
        onClick={onOpenContradictions}
        className="rounded-full border border-neutral-200 bg-neutral-50 px-3 py-1.5 text-xs font-semibold text-neutral-700 transition hover:bg-neutral-100"
      >
        Open contradiction handling
      </button>
    </div>
  </section>
);

// ============ EVIDENCE PAPERS CARD ============

const EvidencePapersCard: React.FC<{
  papers: any[];
  isIngesting: boolean;
  ingestionError?: string | null;
  mission: MissionDetailData | null;
  onRetry?: () => void;
  onCompareClick?: (paperId: string) => void;
  onGraphClick?: (paperId: string) => void;
}> = ({ papers, isIngesting, ingestionError, mission, onRetry, onCompareClick, onGraphClick }) => {
  const [expandedPaperId, setExpandedPaperId] = React.useState<string | null>(null);

  return (
    <div className="flex flex-col overflow-hidden rounded-2xl border border-neutral-200/80 bg-white shadow-[0_12px_40px_rgba(15,23,42,0.06)]">
      <div className="flex flex-shrink-0 items-center justify-between border-b border-neutral-200 bg-gradient-to-r from-white via-neutral-50 to-white px-6 py-4">
        <h2 className="font-semibold text-neutral-900 flex items-center gap-2">
          <FileText size={18} className="text-red-600" />
          Evidence Papers
          {!isIngesting && papers.length > 0 && (
            <span className="text-xs font-medium px-2 py-1 bg-neutral-100 text-neutral-700 rounded-full">
              {papers.length}
            </span>
          )}
        </h2>
      </div>

      <div className="flex flex-1 flex-col overflow-y-auto">
        {isIngesting || papers.length > 0 ? (
          <div className="p-6 space-y-4 flex-1 flex flex-col">
            {/* Ingestion Progress Task */}
            {isIngesting && (
              <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg">
                <div className="flex items-center gap-3 mb-3">
                  <Loader size={18} className="animate-spin text-blue-600" />
                  <div>
                    <p className="font-semibold text-blue-900">Ingesting papers for "{mission?.name}"</p>
                    <p className="text-sm text-blue-700 mt-1">
                      {papers.length} {papers.length === 1 ? 'paper' : 'papers'} ingested so far...
                    </p>
                  </div>
                </div>
              </div>
            )}

            {/* Completion Banner */}
            {!isIngesting && papers.length > 0 && (
              <div className="p-4 bg-green-50 border border-green-200 rounded-lg flex items-center gap-3">
                <CheckCircle2 size={18} className="text-green-600" />
                <div>
                  <p className="font-semibold text-green-900">
                    Initial ingestion: {papers.length} {papers.length === 1 ? 'paper' : 'papers'} ingested
                  </p>
                </div>
              </div>
            )}

            {/* Research Papers List */}
            <ScrollFadePanel
              heightClassName="h-[32rem]"
              className="border border-neutral-200/80 bg-neutral-50/40"
              contentClassName="px-1"
            >
              <div className="space-y-2 pb-8">
                {papers.map((paper) => (
                  <CollapsibleResearchPaper
                    key={paper.id}
                    paper={paper}
                    isExpanded={expandedPaperId === paper.id}
                    onToggle={() => setExpandedPaperId(expandedPaperId === paper.id ? null : paper.id)}
                    onCompareClick={onCompareClick}
                    onGraphClick={onGraphClick}
                  />
                ))}
              </div>
            </ScrollFadePanel>
          </div>
        ) : ingestionError ? (
          <div className="flex-1 flex flex-col items-center justify-center p-8 text-center">
            <AlertTriangle size={28} className="text-amber-500 mb-3" />
            <p className="text-neutral-800 font-semibold text-sm mb-1">Ingestion failed</p>
            <p className="text-neutral-500 text-xs mb-4 max-w-xs">{ingestionError}</p>
            {onRetry && (
              <button
                onClick={onRetry}
                className="flex items-center gap-2 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors text-sm font-medium"
              >
                <RotateCw size={14} />
                Retry Ingestion
              </button>
            )}
          </div>
        ) : (
          <div className="flex-1 flex flex-col items-center justify-center p-8 text-center">
            <BookOpen size={28} className="text-neutral-300 mb-2" />
            <p className="text-neutral-700 font-medium text-sm mb-1">No papers ingested yet</p>
            <p className="text-neutral-600 text-xs">Starting ingestion automatically...</p>
          </div>
        )}
      </div>
    </div>
  );
};

// ============ COLLAPSIBLE RESEARCH PAPER ============

const CollapsibleResearchPaper: React.FC<{
  paper: any;
  isExpanded: boolean;
  onToggle: () => void;
  onCompareClick?: (paperId: string) => void;
  onGraphClick?: (paperId: string) => void;
}> = ({ paper, isExpanded, onToggle, onCompareClick, onGraphClick }) => {
  const getAuthorString = (authors: string | string[]) => {
    if (typeof authors === 'string') return authors;
    if (Array.isArray(authors)) return authors.join(', ');
    return 'Unknown';
  };

  const pdfLink = paper.pdf_url || paper.arxiv_url || paper.doi_link;
  
  // CEGC score breakdown
  const cegcScore = paper.score_breakdown;
  const mechanismDesc = paper.mechanism_description;

  return (
    <div
      onClick={onToggle}
      className="w-full text-left p-4 rounded-lg border border-neutral-200 hover:border-neutral-300 hover:bg-neutral-50 transition-all group cursor-pointer"
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onToggle();
        }
      }}
    >
      {/* Collapsed View */}
      <div className="flex items-start gap-3">
        <ChevronRight
          size={18}
          className={`text-neutral-400 group-hover:text-neutral-600 flex-shrink-0 transition-transform mt-0.5 ${
            isExpanded ? 'rotate-90' : ''
          }`}
        />
        <div className="flex-1 min-w-0">
          <h3 className="text-sm font-semibold text-neutral-900 line-clamp-2 group-hover:text-red-600 transition-colors">
            {paper.title}
          </h3>
          <p className="text-xs text-neutral-600 mt-1">
            {getAuthorString(paper.authors || paper.author || 'Unknown')}
          </p>
          <p className="text-xs text-neutral-500 mt-1">
            {paper.year || '—'} • {(paper.source || paper.venue || '').replace(/_/g, ' ')}
          </p>
          {mechanismDesc && (
            <p className="text-xs text-neutral-600 mt-2 italic">
              📊 {mechanismDesc}
            </p>
          )}
        </div>
        {paper.final_score && (
          <div className="flex-shrink-0 text-right">
            <div className="text-xs font-semibold text-red-600">
              {(paper.final_score * 100).toFixed(0)}%
            </div>
            <div className="text-xs text-neutral-500">CEGC Score</div>
          </div>
        )}
      </div>

      {/* Expanded View */}
      {isExpanded && (
        <div className="mt-4 pt-4 border-t border-neutral-200 space-y-3">
          {/* CEGC Score Breakdown */}
          {cegcScore && (
            <div className="bg-neutral-50 p-3 rounded-lg space-y-2">
              <p className="text-xs font-semibold text-neutral-700 mb-3">CEGC Score Breakdown</p>
              
              {/* Layer 1: PICO */}
              {cegcScore.pico !== undefined && (
                <div className="space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-neutral-600">Layer 1: PICO Matching (25%)</span>
                    <span className="text-xs font-semibold text-neutral-900">{(cegcScore.pico * 100).toFixed(0)}%</span>
                  </div>
                  <div className="w-full h-1.5 bg-neutral-200 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-blue-500 transition-all"
                      style={{ width: `${Math.min(cegcScore.pico * 100, 100)}%` }}
                    />
                  </div>
                </div>
              )}

              {/* Layer 2: Evidence */}
              {cegcScore.evidence !== undefined && (
                <div className="space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-neutral-600">Layer 2: Evidence Strength (30%)</span>
                    <span className="text-xs font-semibold text-neutral-900">{(cegcScore.evidence * 100).toFixed(0)}%</span>
                  </div>
                  <div className="w-full h-1.5 bg-neutral-200 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-green-500 transition-all"
                      style={{ width: `${Math.min(cegcScore.evidence * 100, 100)}%` }}
                    />
                  </div>
                </div>
              )}

              {/* Layer 3: Mechanism */}
              {cegcScore.mechanism !== undefined && (
                <div className="space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-neutral-600">Layer 3: Mechanism Match (20%)</span>
                    <span className="text-xs font-semibold text-neutral-900">{(cegcScore.mechanism * 100).toFixed(0)}%</span>
                  </div>
                  <div className="w-full h-1.5 bg-neutral-200 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-amber-500 transition-all"
                      style={{ width: `${Math.min(cegcScore.mechanism * 100, 100)}%` }}
                    />
                  </div>
                </div>
              )}

              {/* Layer 4: Assumption */}
              {cegcScore.assumption !== undefined && (
                <div className="space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-neutral-600">Layer 4: Assumption Alignment (15%)</span>
                    <span className="text-xs font-semibold text-neutral-900">{(cegcScore.assumption * 100).toFixed(0)}%</span>
                  </div>
                  <div className="w-full h-1.5 bg-neutral-200 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-purple-500 transition-all"
                      style={{ width: `${Math.min(cegcScore.assumption * 100, 100)}%` }}
                    />
                  </div>
                </div>
              )}

              {/* Layer 5: LLM Verification (if applied) */}
              {cegcScore.llm_adjustment !== undefined && cegcScore.llm_adjustment !== null && (
                <div className="space-y-1 pt-1 border-t border-neutral-200">
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-neutral-600">Layer 5: LLM Verification (10%)</span>
                    <span className={`text-xs font-semibold ${cegcScore.llm_adjustment > 0 ? 'text-green-600' : cegcScore.llm_adjustment < 0 ? 'text-red-600' : 'text-neutral-500'}`}>
                      {cegcScore.llm_adjustment > 0 ? '+' : ''}{(cegcScore.llm_adjustment * 100).toFixed(0)}%
                    </span>
                  </div>
                </div>
              )}

              {/* Final Score */}
              {cegcScore.final !== undefined && (
                <div className="space-y-1 pt-2 border-t border-neutral-300">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-neutral-900">FINAL CEGC SCORE</span>
                    <span className="text-sm font-bold text-red-600">{(cegcScore.final * 100).toFixed(1)}%</span>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Abstract */}
          {paper.abstract && (
            <div>
              <p className="text-xs font-semibold text-neutral-700 mb-2">Abstract</p>
              <p className="text-sm text-neutral-700 leading-relaxed max-h-32 overflow-y-auto">
                {paper.abstract}
              </p>
            </div>
          )}

          {/* Action Buttons */}
          <div className="flex gap-2 pt-2 border-t border-neutral-200">
            {onGraphClick && (
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onGraphClick(paper.id);
                }}
                className="flex-1 px-3 py-2 bg-blue-50 hover:bg-blue-100 text-blue-600 hover:text-blue-700 rounded-lg font-medium text-xs transition-colors"
              >
                📊 View Analysis
              </button>
            )}
            {onCompareClick && (
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onCompareClick(paper.id);
                }}
                className="flex-1 px-3 py-2 bg-green-50 hover:bg-green-100 text-green-600 hover:text-green-700 rounded-lg font-medium text-xs transition-colors"
              >
                ⚖️ Compare
              </button>
            )}
            {pdfLink && (
              <a
                href={pdfLink}
                target="_blank"
                rel="noopener noreferrer"
                onClick={(e) => e.stopPropagation()}
                className="flex-1 px-3 py-2 bg-neutral-100 hover:bg-neutral-200 text-neutral-700 hover:text-neutral-900 rounded-lg font-medium text-xs transition-colors flex items-center justify-center gap-1"
              >
                <FileText size={14} />
                PDF
              </a>
            )}
          </div>
        </div>
      )}
    </div>
  );
};



// ============ REASONING CARD ============

const ReasoningCard: React.FC<{ reasoning: any[]; memoryOverview: MemoryOverview | null }> = ({ reasoning, memoryOverview }) => {
  const currentBelief = memoryOverview?.latest_snapshot?.current_belief_statement
    || 'No belief statement has been formed yet.';
  const currentConfidence = memoryOverview?.belief_state?.current_confidence_score
    ?? memoryOverview?.latest_snapshot?.current_confidence_score
    ?? null;
  const currentDirection = memoryOverview?.belief_state?.dominant_evidence_direction
    ?? memoryOverview?.latest_snapshot?.dominant_evidence_direction
    ?? 'mixed';

  const formatRevisionTitle = (step: any) => {
    const conclusion = String(step?.conclusion || '').toUpperCase();
    if (conclusion.includes('NO_UPDATE')) return 'No change this cycle';
    if (conclusion.includes('REINFORCE')) return 'Belief reinforced';
    if (conclusion.includes('WEAK_REINFORCE')) return 'Belief slightly reinforced';
    if (conclusion.includes('WEAKEN')) return 'Belief weakened';
    if (conclusion.includes('MATERIAL_UPDATE')) return 'Material belief update';
    if (conclusion.includes('REVERSAL')) return 'Belief reversed';
    if (conclusion.includes('ESCALATE')) return 'Needs operator review';
    return 'Belief update';
  };

  const formatRevisionExplanation = (step: any) => {
    if (step?.logic) return step.logic;
    return 'The system reviewed the latest evidence and updated the belief state accordingly.';
  };

  return (
    <div className="bg-white border border-neutral-200 rounded-lg overflow-hidden flex flex-col h-96">
      <div className="px-6 py-4 border-b border-neutral-200 flex items-center justify-between flex-shrink-0">
        <h2 className="font-semibold text-neutral-900 flex items-center gap-2">
          <Activity size={18} className="text-red-600" />
          Reasoning
          <span className="text-xs font-medium px-2 py-1 bg-neutral-100 text-neutral-700 rounded-full">
            {reasoning.length}
          </span>
        </h2>
      </div>

      <div className="overflow-y-auto flex-1">
        <div className="space-y-4 p-6">
          <div className="rounded-lg border border-blue-200 bg-blue-50 p-4">
            <p className="text-xs font-semibold uppercase tracking-wide text-blue-700 mb-2">Current Belief</p>
            <p className="text-sm text-neutral-900 leading-relaxed">{currentBelief}</p>
            <div className="mt-3 flex flex-wrap gap-3 text-xs text-neutral-600">
              <span>Direction: {currentDirection}</span>
              {currentConfidence !== null && <span>Confidence: {(currentConfidence * 100).toFixed(0)}%</span>}
            </div>
          </div>

          {reasoning.length === 0 ? (
            <div className="flex flex-col items-center justify-center p-8 text-center">
              <BookOpen size={28} className="text-neutral-300 mb-2" />
              <p className="text-neutral-700 font-medium text-sm mb-1">No reasoning steps yet</p>
              <p className="text-neutral-600 text-xs">Belief updates will appear here once a revision cycle runs.</p>
            </div>
          ) : (
            reasoning.slice(0, 5).map((step, idx) => (
              <div key={idx} className="rounded-lg border border-neutral-200 p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-wide text-neutral-500 mb-1">
                      Cycle {step.step_number}
                    </p>
                    <p className="text-sm font-semibold text-neutral-900">{formatRevisionTitle(step)}</p>
                  </div>
                  <div className="text-xs font-medium px-2.5 py-1 rounded-full bg-neutral-100 text-neutral-700">
                    {(step.confidence_score * 100).toFixed(0)}% confidence
                  </div>
                </div>
                <p className="text-sm text-neutral-700 mt-3 leading-relaxed">
                  {formatRevisionExplanation(step)}
                </p>
                {step.conclusion && (
                  <div className="mt-3 rounded-md bg-neutral-50 border border-neutral-200 px-3 py-2">
                    <p className="text-xs font-medium text-neutral-500 mb-1">System outcome</p>
                    <p className="text-sm text-neutral-800">{step.conclusion}</p>
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
};

// ============ TIMELINE CARD ============

const TimelineCard: React.FC<{ timeline: any[]; expandedId: string | null; onExpandId: (id: string | null) => void }> = ({
  timeline,
  expandedId,
  onExpandId,
}) => {
  const getEventColor = (type: string) => {
    if (type?.includes('ingestion')) return 'bg-blue-500';
    if (type?.includes('synthesis') || type?.includes('analysis')) return 'bg-green-500';
    if (type?.includes('contradiction')) return 'bg-red-500';
    if (type?.includes('escalation') || type?.includes('reversal')) return 'bg-red-500';
    return 'bg-neutral-400';
  };

  return (
    <div className="bg-white border border-neutral-200 rounded-lg overflow-hidden flex flex-col flex-1">
      <div className="px-6 py-4 border-b border-neutral-200 flex-shrink-0">
        <h2 className="font-semibold text-neutral-900 flex items-center gap-2">
        <Clock size={18} className="text-red-600" />
          Mission Timeline
          <span className="text-xs font-medium px-2 py-1 bg-neutral-100 text-neutral-700 rounded-full">
            {timeline.length}
          </span>
        </h2>
      </div>

      {timeline.length === 0 ? (
        <div className="flex-1 flex flex-col items-center justify-center p-8 text-center">
          <Clock size={28} className="text-neutral-300 mb-2" />
          <p className="text-neutral-700 font-medium text-sm mb-1">No events yet</p>
          <p className="text-neutral-600 text-xs">Activity will be tracked here</p>
        </div>
      ) : (
        <div className="overflow-y-auto flex-1">
          <div className="space-y-2 p-6">
            {timeline.slice(0, 6).map((event) => (
              <button
                key={event.id}
                onClick={() => onExpandId(expandedId === event.id ? null : event.id)}
                className="w-full text-left p-3 rounded-lg border border-neutral-200 hover:border-neutral-300 hover:bg-neutral-50 transition-all group"
              >
                <div className="flex items-start gap-3">
                  <div className={`w-2.5 h-2.5 rounded-full flex-shrink-0 mt-1 ${getEventColor(event.event_type || '')}`} />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-semibold text-neutral-900 line-clamp-1">{event.event_title}</p>
                    <p className="text-xs text-neutral-600 mt-0.5">Cycle #{event.cycle_number || 0}</p>
                    {expandedId === event.id && event.event_description && (
                      <p className="text-xs text-neutral-700 mt-2 pt-2 border-t border-neutral-200">
                        {event.event_description}
                      </p>
                    )}
                  </div>
                  <ChevronRight
                    size={16}
                    className={`text-neutral-400 group-hover:text-neutral-600 flex-shrink-0 transition-transform ${
                      expandedId === event.id ? 'rotate-90' : ''
                    }`}
                  />
                </div>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

// ============ PAPER GRAPH MODAL ============

const PaperGraphModal: React.FC<{ paper: any; onClose: () => void }> = ({ paper, onClose }) => {
  return (
    <>
      <div
        className="fixed inset-0 bg-black/50 z-40"
        onClick={onClose}
      />
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div className="bg-white rounded-lg shadow-xl max-w-4xl w-full max-h-[90vh] overflow-y-auto">
          {/* Header */}
          <div className="sticky top-0 flex items-center justify-between border-b border-neutral-200 bg-white px-6 py-4">
            <h2 className="text-lg font-semibold text-neutral-900">
              Paper Analysis: {paper.title}
            </h2>
            <button
              onClick={onClose}
              className="p-1 text-neutral-600 hover:text-neutral-900 hover:bg-neutral-100 rounded transition-colors"
            >
              <X size={20} />
            </button>
          </div>

          {/* Content */}
          <div className="p-6">
            {/* Paper Metadata */}
            <div className="mb-6 p-4 bg-neutral-50 rounded-lg border border-neutral-200">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
                <div>
                  <p className="text-neutral-600">Authors</p>
                  <p className="font-semibold text-neutral-900">
                    {typeof paper.authors === 'string'
                      ? paper.authors
                      : Array.isArray(paper.authors)
                        ? paper.authors.join(', ')
                        : 'Unknown'}
                  </p>
                </div>
                <div>
                  <p className="text-neutral-600">Year</p>
                  <p className="font-semibold text-neutral-900">{paper.year || 'Unknown'}</p>
                </div>
                <div>
                  <p className="text-neutral-600">Source</p>
                  <p className="font-semibold text-neutral-900">
                    {(paper.source || paper.venue || 'Unknown').replace(/_/g, ' ')}
                  </p>
                </div>
                <div>
                  <p className="text-neutral-600">CEGC Score</p>
                  <p className="font-semibold text-red-600 text-lg">
                    {(paper.final_score * 100).toFixed(1)}%
                  </p>
                </div>
              </div>
            </div>

            {/* Graph */}
            <div className="mb-6">
              <h3 className="text-md font-semibold text-neutral-900 mb-4">CEGC Score Analysis</h3>
              <div className="bg-white border border-neutral-200 rounded-lg p-4">
                <PaperLevelGraph paper={paper} />
              </div>
            </div>

            {/* Mechanism Description */}
            {paper.mechanism_description && (
              <div className="mb-6 p-4 bg-blue-50 rounded-lg border border-blue-200">
                <h3 className="text-sm font-semibold text-blue-900 mb-2">Mechanism Analysis</h3>
                <p className="text-sm text-blue-800">{paper.mechanism_description}</p>
              </div>
            )}

            {/* Abstract */}
            {paper.abstract && (
              <div className="mb-6">
                <h3 className="text-sm font-semibold text-neutral-900 mb-2">Abstract</h3>
                <p className="text-sm text-neutral-700 leading-relaxed">{paper.abstract}</p>
              </div>
            )}

            {/* Close Button */}
            <div className="flex justify-end gap-3">
              <button
                onClick={onClose}
                className="px-4 py-2 bg-neutral-200 hover:bg-neutral-300 text-neutral-900 rounded-lg font-medium transition-colors"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      </div>
    </>
  );
};

// ============ COMPARISON MODAL ============

const ComparisonModal: React.FC<{
  missionId: string;
  selectedPaperIds: string[];
  allPapers: any[];
  onClose: () => void;
}> = ({ selectedPaperIds, allPapers, onClose }) => {
  const [comparisonData, setComparisonData] = React.useState<any>(null);
  const [selectedSecondPaperId, setSelectedSecondPaperId] = React.useState<string>('');
  const [loading, setLoading] = React.useState(false);

  const firstPaperId = selectedPaperIds[0];
  const firstPaper = allPapers.find(p => p.id === firstPaperId);

  React.useEffect(() => {
    if (selectedSecondPaperId && firstPaperId && selectedSecondPaperId !== firstPaperId) {
      const fetchComparison = async () => {
        try {
          setLoading(true);
          const data = await apiClient.comparePapers(firstPaperId, selectedSecondPaperId);
          setComparisonData(data);
        } catch (err) {
          console.error('Error fetching comparison:', err);
        } finally {
          setLoading(false);
        }
      };
      fetchComparison();
    }
  }, [selectedSecondPaperId, firstPaperId]);

  const secondPaper = selectedSecondPaperId ? allPapers.find(p => p.id === selectedSecondPaperId) : null;
  const otherPapers = allPapers.filter(p => p.id !== firstPaperId);

  return (
    <>
      <div
        className="fixed inset-0 bg-black/50 z-40"
        onClick={onClose}
      />
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div className="bg-white rounded-lg shadow-xl max-w-4xl w-full max-h-[90vh] overflow-y-auto">
          {/* Header */}
          <div className="sticky top-0 flex items-center justify-between border-b border-neutral-200 bg-white px-6 py-4">
            <h2 className="text-lg font-semibold text-neutral-900">
              Compare Papers
            </h2>
            <button
              onClick={onClose}
              className="p-1 text-neutral-600 hover:text-neutral-900 hover:bg-neutral-100 rounded transition-colors"
            >
              <X size={20} />
            </button>
          </div>

          {/* Content */}
          <div className="p-6 space-y-6">
            {/* First Paper Selected */}
            {firstPaper && (
              <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg">
                <p className="text-xs text-blue-600 font-semibold mb-1">PAPER 1 (Selected)</p>
                <p className="font-semibold text-blue-900">{firstPaper.title}</p>
                <p className="text-xs text-blue-700 mt-1">
                  CEGC Score: {(firstPaper.final_score * 100).toFixed(1)}%
                </p>
              </div>
            )}

            {/* Select Second Paper */}
            <div>
              <label className="block text-sm font-semibold text-neutral-900 mb-2">
                Select Paper to Compare With
              </label>
              <select
                value={selectedSecondPaperId}
                onChange={(e) => setSelectedSecondPaperId(e.target.value)}
                className="w-full px-4 py-2 border border-neutral-300 rounded-lg focus:border-red-600 focus:ring-1 focus:ring-red-600 outline-none"
              >
                <option value="">Choose a paper...</option>
                {otherPapers.map(paper => (
                  <option key={paper.id} value={paper.id}>
                    {paper.title} ({(paper.final_score * 100).toFixed(1)}%)
                  </option>
                ))}
              </select>
            </div>

            {/* Comparison Graph */}
            {selectedSecondPaperId && secondPaper && (
              <>
                {loading ? (
                  <div className="flex items-center justify-center py-12">
                    <Loader size={32} className="animate-spin text-red-600" />
                  </div>
                ) : (
                  <>
                    <div className="border border-neutral-200 rounded-lg p-6 bg-white">
                      <ComparisonGraph paperA={firstPaper} paperB={secondPaper} />
                    </div>

                    {/* Second Paper Selected */}
                    <div className="p-4 bg-green-50 border border-green-200 rounded-lg">
                      <p className="text-xs text-green-600 font-semibold mb-1">PAPER 2 (Selected)</p>
                      <p className="font-semibold text-green-900">{secondPaper.title}</p>
                      <p className="text-xs text-green-700 mt-1">
                        CEGC Score: {(secondPaper.final_score * 100).toFixed(1)}%
                      </p>
                    </div>

                    {/* Comparison Metadata */}
                    {comparisonData && (
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        {/* Paper 1 Stats */}
                        <div className="p-4 border border-neutral-200 rounded-lg">
                          <p className="text-sm font-semibold text-neutral-900 mb-3">{firstPaper.title}</p>
                          <div className="space-y-2 text-sm">
                            <div className="flex justify-between">
                              <span className="text-neutral-600">PICO Matching</span>
                              <span className="font-semibold text-neutral-900">
                                {(comparisonData.paper_a.score_breakdown?.pico * 100 || 0).toFixed(0)}%
                              </span>
                            </div>
                            <div className="flex justify-between">
                              <span className="text-neutral-600">Evidence Strength</span>
                              <span className="font-semibold text-neutral-900">
                                {(comparisonData.paper_a.score_breakdown?.evidence * 100 || 0).toFixed(0)}%
                              </span>
                            </div>
                            <div className="flex justify-between">
                              <span className="text-neutral-600">Mechanism Match</span>
                              <span className="font-semibold text-neutral-900">
                                {(comparisonData.paper_a.score_breakdown?.mechanism * 100 || 0).toFixed(0)}%
                              </span>
                            </div>
                          </div>
                        </div>

                        {/* Paper 2 Stats */}
                        <div className="p-4 border border-neutral-200 rounded-lg">
                          <p className="text-sm font-semibold text-neutral-900 mb-3">{secondPaper.title}</p>
                          <div className="space-y-2 text-sm">
                            <div className="flex justify-between">
                              <span className="text-neutral-600">PICO Matching</span>
                              <span className="font-semibold text-neutral-900">
                                {(comparisonData.paper_b.score_breakdown?.pico * 100 || 0).toFixed(0)}%
                              </span>
                            </div>
                            <div className="flex justify-between">
                              <span className="text-neutral-600">Evidence Strength</span>
                              <span className="font-semibold text-neutral-900">
                                {(comparisonData.paper_b.score_breakdown?.evidence * 100 || 0).toFixed(0)}%
                              </span>
                            </div>
                            <div className="flex justify-between">
                              <span className="text-neutral-600">Mechanism Match</span>
                              <span className="font-semibold text-neutral-900">
                                {(comparisonData.paper_b.score_breakdown?.mechanism * 100 || 0).toFixed(0)}%
                              </span>
                            </div>
                          </div>
                        </div>
                      </div>
                    )}
                  </>
                )}
              </>
            )}

            {/* Close Button */}
            <div className="flex justify-end gap-3 pt-4 border-t border-neutral-200">
              <button
                onClick={onClose}
                className="px-4 py-2 bg-neutral-200 hover:bg-neutral-300 text-neutral-900 rounded-lg font-medium transition-colors"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      </div>
    </>
  );
};

// ============ MISSION GRAPH DASHBOARD CARD ============

const MissionGraphDashboardCard: React.FC<{
  stats: any;
}> = ({ stats }) => {
  return (
    <div className="bg-white border border-neutral-200 rounded-lg overflow-hidden flex flex-col">
      <div className="px-6 py-4 border-b border-neutral-200 flex items-center justify-between flex-shrink-0">
        <h2 className="font-semibold text-neutral-900 flex items-center gap-2">
          <BarChart3 size={18} className="text-red-600" />
          Mission-Level Graph
        </h2>
      </div>

      <div className="p-6 overflow-y-auto">
        {stats ? (
          <div className="space-y-8">
            {/* Overview Stats */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="p-4 bg-neutral-50 rounded-lg border border-neutral-200">
                <p className="text-xs text-neutral-600 font-semibold mb-1">Total Papers</p>
                <p className="text-2xl font-bold text-red-600">{stats.total_papers || 0}</p>
              </div>
              <div className="p-4 bg-neutral-50 rounded-lg border border-neutral-200">
                <p className="text-xs text-neutral-600 font-semibold mb-1">Average Score</p>
                <p className="text-2xl font-bold text-blue-600">
                  {(stats.avg_score * 100 || 0).toFixed(1)}%
                </p>
              </div>
              <div className="p-4 bg-neutral-50 rounded-lg border border-neutral-200">
                <p className="text-xs text-neutral-600 font-semibold mb-1">Median Score</p>
                <p className="text-2xl font-bold text-green-600">
                  {(stats.median_score * 100 || 0).toFixed(1)}%
                </p>
              </div>
            </div>

            {/* Mission Level Graph */}
            <div className="border border-neutral-200 rounded-lg p-4 bg-white">
              <MissionLevelGraph stats={stats} />
            </div>
          </div>
        ) : (
          <div className="flex items-center justify-center py-12 text-center">
            <div>
              <BarChart3 size={32} className="text-neutral-300 mx-auto mb-2" />
              <p className="text-neutral-700 font-medium text-sm">Loading graph data...</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

// ============ UTILITY FUNCTIONS ============

const formatRelativeTime = (dateString: string) => {
  if (!dateString) return 'unknown';
  const date = new Date(dateString);
  if (Number.isNaN(date.getTime())) return 'unknown';
  const now = new Date();
  const seconds = Math.floor((now.getTime() - date.getTime()) / 1000);

  if (seconds < 60) return 'just now';
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
};
