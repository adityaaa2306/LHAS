import React from 'react';
import {
  CheckCircle2,
  Circle,
  Loader2,
  XCircle,
  Activity,
  Brain,
  Zap,
  Target,
  Clock,
  Shield,
  GitBranch,
} from 'lucide-react';
import type { IngestionStatusResponse, IngestionStage, BackgroundTaskStatus } from '@/types/ingestion';
import { RetrievalTransparencyPanel } from '@/components/RetrievalTransparencyPanel';

const TASK_META: Record<string, { label: string; icon: React.ComponentType<{ size?: number; className?: string }> }> = {
  claims: { label: 'Extracting claims', icon: Target },
  contradictions: { label: 'Detecting contradictions', icon: Zap },
  synthesis: { label: 'Building synthesis', icon: Brain },
  memory: { label: 'Building memory', icon: Activity },
  monitoring: { label: 'Alignment monitoring', icon: Shield },
  timeline: { label: 'Building timeline', icon: Clock },
  reasoning: { label: 'Reasoning graph', icon: GitBranch },
};

function StageIcon({ stage }: { stage: IngestionStage }) {
  if (stage.status === 'completed') {
    return <CheckCircle2 size={16} className="text-emerald-500 shrink-0" />;
  }
  if (stage.status === 'failed') {
    return <XCircle size={16} className="text-red-500 shrink-0" />;
  }
  if (stage.status === 'running') {
    return <Loader2 size={16} className="text-blue-500 animate-spin shrink-0" />;
  }
  return <Circle size={16} className="text-neutral-300 shrink-0" />;
}

function StatChip({ label, value, highlight }: { label: string; value: number; highlight?: boolean }) {
  return (
    <div
      className={`rounded-lg border px-3 py-2 text-center ${
        highlight ? 'border-red-200 bg-red-50' : 'border-neutral-100 bg-neutral-50'
      }`}
    >
      <p className="text-lg font-semibold tabular-nums text-neutral-900">{value}</p>
      <p className="text-[10px] font-medium uppercase tracking-wide text-neutral-500">{label}</p>
    </div>
  );
}

function ProgressBar({ progress, label }: { progress: number; label?: string }) {
  const clamped = Math.max(0, Math.min(100, progress));
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between text-xs text-neutral-600">
        <span>{label || `${clamped}%`}</span>
        <span className="font-semibold tabular-nums text-neutral-900">{clamped}%</span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-neutral-100">
        <div
          className="h-full rounded-full bg-gradient-to-r from-red-500 to-red-600 transition-all duration-500 ease-out"
          style={{ width: `${clamped}%` }}
        />
      </div>
    </div>
  );
}

function BackgroundTaskRow({ taskId, task }: { taskId: string; task: BackgroundTaskStatus }) {
  const meta = TASK_META[taskId] || { label: taskId, icon: Circle };
  const Icon = meta.icon;
  const isActive = task.status === 'running';
  const isDone = task.status === 'completed';
  const isFailed = task.status === 'failed';

  return (
    <div className="rounded-lg border border-neutral-100 bg-neutral-50/80 px-3 py-2.5">
      <div className="mb-1.5 flex items-center gap-2 text-sm">
        {isActive ? (
          <Loader2 size={14} className="animate-spin text-blue-500" />
        ) : isDone ? (
          <CheckCircle2 size={14} className="text-emerald-500" />
        ) : isFailed ? (
          <XCircle size={14} className="text-red-500" />
        ) : (
          <Icon size={14} className="text-neutral-400" />
        )}
        <span className="font-medium text-neutral-800">{meta.label}</span>
        {task.detail && (
          <span className="ml-auto truncate text-xs text-neutral-500">{task.detail}</span>
        )}
      </div>
      {(isActive || isDone) && (
        <div className="h-1.5 overflow-hidden rounded-full bg-neutral-200">
          <div
            className={`h-full rounded-full transition-all duration-300 ${
              isFailed ? 'bg-red-500' : isDone ? 'bg-emerald-500' : 'bg-blue-500'
            }`}
            style={{ width: `${task.progress}%` }}
          />
        </div>
      )}
      {task.status === 'waiting' && (
        <p className="text-xs text-neutral-400">Waiting...</p>
      )}
    </div>
  );
}

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  } catch {
    return iso;
  }
}

interface MissionProgressPanelProps {
  status: IngestionStatusResponse | null;
  isActive: boolean;
  missionName?: string;
  error?: string | null;
  onRetry?: () => void;
}

export const MissionProgressPanel: React.FC<MissionProgressPanelProps> = ({
  status,
  isActive,
  missionName,
  error,
  onRetry,
}) => {
  const feedRef = React.useRef<HTMLDivElement>(null);
  const progress = status?.progress ?? 0;
  const currentStage = status?.stages?.find((s) => s.status === 'running')
    || status?.stages?.find((s) => s.id === status?.current_stage);
  const stageLabel = currentStage?.label || 'Processing';
  const stageDetail = status?.stage_detail;
  const activities = status?.activities ?? [];
  const backgroundTasks = status?.background_tasks ?? {};
  const showPanel = isActive || status?.status === 'failed' || (status?.status === 'completed' && progress === 100);

  React.useEffect(() => {
    if (feedRef.current) {
      feedRef.current.scrollTop = feedRef.current.scrollHeight;
    }
  }, [activities.length]);

  if (!showPanel && !error) return null;

  const isFailed = status?.status === 'failed' || Boolean(error);
  const isComplete = status?.status === 'completed';

  return (
    <section className="overflow-hidden rounded-2xl border border-neutral-200 bg-white shadow-sm">
      <div className="border-b border-neutral-100 bg-gradient-to-r from-neutral-50 to-white px-5 py-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-neutral-500">
              Mission execution
            </p>
            <h2 className="mt-0.5 text-lg font-semibold text-neutral-900">
              {isComplete ? 'Mission complete' : isFailed ? 'Execution failed' : stageLabel}
            </h2>
            {missionName && (
              <p className="mt-0.5 text-sm text-neutral-500">{missionName}</p>
            )}
            {stageDetail && !isComplete && !isFailed && (
              <p className="mt-1 text-sm text-blue-700">{stageDetail}</p>
            )}
          </div>
          {isActive && !isFailed && (
            <Loader2 size={22} className="mt-1 animate-spin text-red-500" />
          )}
          {isComplete && <CheckCircle2 size={22} className="mt-1 text-emerald-500" />}
          {isFailed && <XCircle size={22} className="mt-1 text-red-500" />}
        </div>

        <div className="mt-4">
          <ProgressBar progress={progress} label={isComplete ? 'Complete' : `${stageLabel}...`} />
        </div>

        {status?.stats && (
          <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
            <StatChip label="Candidates" value={status.stats.candidates_retrieved} />
            <StatChip label="After dedup" value={status.stats.after_dedup} />
            <StatChip label="Prefiltered" value={status.stats.after_prefilter} />
            <StatChip label="Finalized" value={status.stats.stored || status.stats.selected} highlight />
          </div>
        )}
      </div>

        {status?.stats && Object.keys(status.stats.source_counts || {}).length > 0 && (
          <div className="mt-2 flex flex-wrap gap-2 px-5 pb-2">
            {Object.entries(status.stats.source_counts).map(([src, count]) => (
              <span key={src} className="rounded-full bg-neutral-100 px-2 py-0.5 text-[10px] font-medium text-neutral-600">
                {src}: {count}
              </span>
            ))}
          </div>
        )}

        <RetrievalTransparencyPanel plan={status?.stats?.retrieval_plan} />

      {(status?.stats?.finalized_papers?.length ?? 0) > 0 && (
        <div className="border-b border-neutral-100 px-5 py-4">
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-neutral-500">
            Finalized papers ({status?.stats?.finalized_papers.length})
          </h3>
          <ul className="max-h-36 space-y-1.5 overflow-y-auto rounded-lg border border-neutral-100 bg-neutral-50/80 p-2">
            {status!.stats!.finalized_papers.map((paper) => (
              <li key={paper.id} className="flex items-start gap-2 text-xs">
                <CheckCircle2 size={12} className="mt-0.5 shrink-0 text-emerald-500" />
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium text-neutral-800">{paper.title}</p>
                  <p className="text-neutral-500">
                    {paper.source} · score {(paper.score * 100).toFixed(0)}%
                  </p>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="grid gap-0 lg:grid-cols-2">
        {/* Stage checklist */}
        <div className="border-b border-neutral-100 p-5 lg:border-b-0 lg:border-r">
          <h3 className="mb-3 text-xs font-semibold uppercase tracking-wide text-neutral-500">
            Pipeline stages
          </h3>
          <ul className="max-h-64 space-y-2 overflow-y-auto pr-1">
            {(status?.stages ?? []).map((stage) => (
              <li
                key={stage.id}
                className={`flex items-start gap-2.5 rounded-lg px-2 py-1.5 text-sm ${
                  stage.status === 'running' ? 'bg-blue-50 text-blue-900' : 'text-neutral-700'
                }`}
              >
                <StageIcon stage={stage} />
                <span className={stage.status === 'completed' ? 'text-neutral-500' : ''}>
                  {stage.label}
                </span>
              </li>
            ))}
          </ul>
        </div>

        {/* Activity feed */}
        <div className="p-5">
          <h3 className="mb-3 text-xs font-semibold uppercase tracking-wide text-neutral-500">
            Live activity
          </h3>
          <div
            ref={feedRef}
            className="max-h-48 space-y-2 overflow-y-auto rounded-lg border border-neutral-100 bg-neutral-50/50 p-3"
          >
            {activities.length === 0 ? (
              <p className="text-sm text-neutral-400">Waiting for activity...</p>
            ) : (
              activities.map((entry, i) => (
                <div key={`${entry.timestamp}-${i}`} className="text-sm">
                  <span className="font-mono text-[11px] text-neutral-400">
                    {formatTime(entry.timestamp)}
                  </span>
                  <p
                    className={
                      entry.level === 'error'
                        ? 'text-red-700'
                        : entry.level === 'warning'
                          ? 'text-amber-700'
                          : 'text-neutral-700'
                    }
                  >
                    {entry.message}
                  </p>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* Background tasks */}
      {Object.keys(backgroundTasks).length > 0 && isActive && (
        <div className="border-t border-neutral-100 px-5 py-4">
          <h3 className="mb-3 text-xs font-semibold uppercase tracking-wide text-neutral-500">
            Background tasks
          </h3>
          <div className="grid gap-2 sm:grid-cols-2">
            {Object.entries(backgroundTasks).map(([taskId, task]) => (
              <BackgroundTaskRow key={taskId} taskId={taskId} task={task} />
            ))}
          </div>
        </div>
      )}

      {(isFailed || error) && (
        <div className="border-t border-red-100 bg-red-50 px-5 py-4">
          <p className="text-sm font-medium text-red-800">
            {error || status?.error || 'Ingestion failed'}
          </p>
          {onRetry && (
            <button
              type="button"
              onClick={onRetry}
              className="mt-3 rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700"
            >
              Retry ingestion
            </button>
          )}
        </div>
      )}
    </section>
  );
};
