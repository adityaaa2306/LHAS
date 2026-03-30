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

export const MissionDetailPage: React.FC = () => {
  const { missionId } = useParams<{ missionId: string }>();
  const navigate = useNavigate();
  const [mission, setMission] = React.useState<MissionDetailData | null>(null);
  const [papers, setPapers] = React.useState<any[]>([]);
  const [synthesis, setSynthesis] = React.useState<any>(null);
  const [claims, setClaims] = React.useState<any[]>([]);
  const [reasoning, setReasoning] = React.useState<any[]>([]);
  const [timeline, setTimeline] = React.useState<any[]>([]);
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
        console.log('📝 Loading synthesis...');
        apiClient.getMissionSynthesis(missionId)
          .then(data => setSynthesis((data as any)?.synthesis))
          .catch(err => console.warn('Synthesis load failed:', err));

        setTimeout(() => {
          console.log('🎯 Loading claims...');
          apiClient.getMissionClaims(missionId)
            .then(data => setClaims((data as any)?.claims || []))
            .catch(err => console.warn('Claims load failed:', err));
        }, 200);

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

  const supportingClaims = claims.filter((c) => c.claim_type === 'supporting').length;
  const contradictingClaims = claims.filter((c) => c.claim_type === 'contradicting').length;
  const neutralClaims = claims.length - supportingClaims - contradictingClaims;
  const evidenceTotal = supportingClaims + contradictingClaims + neutralClaims;
  const supportingPct = evidenceTotal > 0 ? (supportingClaims / evidenceTotal) * 100 : 0;
  const contradictingPct = evidenceTotal > 0 ? (contradictingClaims / evidenceTotal) * 100 : 0;

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
            <VitalRow icon={RotateCw} label="Cycles" value={mission.sessions} />
            <VitalRow
              icon={AlertTriangle}
              label="Contradictions"
              value={contradictingClaims}
              highlight={contradictingClaims > 0}
            />
            {mission.last_run && (
              <div className="flex items-center gap-2 px-2 py-1.5 text-neutral-600">
                <span className="text-xs">Last active: {formatRelativeTime(mission.last_run)}</span>
              </div>
            )}
          </div>

          {/* Evidence Balance Bar */}
          <div className="mb-6">
            <div className="text-xs font-semibold text-neutral-700 mb-2">Evidence Balance</div>
            <div className="flex gap-1 h-2 bg-neutral-200 rounded-full overflow-hidden">
              {evidenceTotal === 0 ? (
                <div className="flex-1 bg-neutral-300" />
              ) : (
                <>
                  {supportingPct > 0 && (
                    <div
                      className="bg-green-500 transition-all"
                      style={{ width: `${supportingPct}%` }}
                    />
                  )}
                  {contradictingPct > 0 && (
                    <div
                      className="bg-red-500 transition-all"
                      style={{ width: `${contradictingPct}%` }}
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
                <span>{supportingPct.toFixed(0)}% Supporting</span>
                <span>{contradictingPct.toFixed(0)}% Contradicting</span>
              </div>
            )}
          </div>

          {/* System Health */}
          <div className="mb-6 p-3 rounded-lg border border-neutral-200 bg-white">
            <div className="text-xs font-semibold text-neutral-700 mb-1">System Health</div>
            <div
              className={`text-sm font-semibold flex items-center gap-2 ${
                mission.health === 'HEALTHY'
                  ? 'text-green-700'
                  : mission.health === 'DEGRADED'
                    ? 'text-amber-700'
                    : mission.health === 'CRITICAL'
                      ? 'text-red-700'
                      : 'text-neutral-700'
              }`}
            >
              {mission.health === 'HEALTHY' ? (
                <CheckCircle2 size={16} />
              ) : mission.health === 'DEGRADED' ? (
                <AlertTriangle size={16} />
              ) : mission.health === 'CRITICAL' ? (
                <AlertCircle size={16} />
              ) : (
                <span className="w-4 h-4 rounded-full bg-neutral-300" />
              )}
              {mission.health || 'UNKNOWN'}
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
            {/* TOP BAND - Central Synthesis */}
            <SynthesisCard synthesis={synthesis} />

            {/* MISSION-LEVEL GRAPH CARD */}
            {graphStats && !graphLoading && (
              <MissionGraphDashboardCard stats={graphStats} />
            )}

            {/* BOTTOM GRID */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* LEFT COLUMN */}
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
                <ClaimsExplorer missionId={missionId || ''} />
              </div>

              {/* RIGHT COLUMN */}
              <div className="space-y-6">
                <ReasoningCard reasoning={reasoning} />
                <TimelineCard timeline={timeline} expandedId={expandedTimelineId} onExpandId={setExpandedTimelineId} />
              </div>
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

const SynthesisCard: React.FC<{ synthesis: any }> = ({ synthesis }) => (
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
    <div className="bg-white border border-neutral-200 rounded-lg overflow-hidden flex flex-col">
      <div className="px-6 py-4 border-b border-neutral-200 flex items-center justify-between flex-shrink-0">
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

      <div className="overflow-y-auto flex-1 flex flex-col">
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
            <div className="space-y-2">
              {papers.slice(0, isIngesting ? undefined : 10).map((paper) => (
                <CollapsibleResearchPaper
                  key={paper.id}
                  paper={paper}
                  isExpanded={expandedPaperId === paper.id}
                  onToggle={() => setExpandedPaperId(expandedPaperId === paper.id ? null : paper.id)}
                  onCompareClick={onCompareClick}
                  onGraphClick={onGraphClick}
                />
              ))}
              {papers.length > 10 && !isIngesting && (
                <button className="pt-2 text-sm text-red-600 hover:text-red-700 font-medium">
                  View all {papers.length} papers
                </button>
              )}
            </div>
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

const ReasoningCard: React.FC<{ reasoning: any[] }> = ({ reasoning }) => (
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

    {reasoning.length === 0 ? (
      <div className="flex-1 flex flex-col items-center justify-center p-8 text-center">
        <BookOpen size={28} className="text-neutral-300 mb-2" />
        <p className="text-neutral-700 font-medium text-sm mb-1">No reasoning steps yet</p>
        <p className="text-neutral-600 text-xs">Analysis will populate structured reasoning</p>
      </div>
    ) : (
      <div className="overflow-y-auto flex-1">
        <div className="space-y-3 p-6">
          {reasoning.slice(0, 5).map((step, idx) => (
            <div key={idx} className="flex gap-3 pb-3 border-b border-neutral-200 last:border-0 last:pb-0">
              <div className="flex flex-col items-center">
                <div className="w-6 h-6 rounded-full bg-red-100 border border-red-300 flex items-center justify-center flex-shrink-0">
                  <span className="text-xs font-semibold text-red-600">{step.step_number}</span>
                </div>
                {idx < reasoning.length - 1 && <div className="w-0.5 h-6 bg-red-100 mt-2" />}
              </div>
              <div className="flex-1 pt-0.5">
                <p className="text-xs font-semibold text-neutral-600 mb-1">{step.reasoning_type}</p>
                {step.conclusion && <p className="text-sm text-neutral-800">{step.conclusion}</p>}
                <p className="text-xs text-neutral-600 mt-1">{(step.confidence_score * 100).toFixed(0)}% confidence</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    )}
  </div>
);

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
  const date = new Date(dateString);
  const now = new Date();
  const seconds = Math.floor((now.getTime() - date.getTime()) / 1000);

  if (seconds < 60) return 'just now';
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
};
