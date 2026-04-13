import React from 'react';
import { Activity, Gauge, ShieldAlert, ShieldCheck, Siren } from 'lucide-react';

import { apiClient } from '@/services/api';
import { ScrollFadePanel } from '@/components/ScrollFadePanel';
import type { MonitoringOverview } from '@/types';

interface AlignmentMonitorPanelProps {
  missionId: string;
}

export const AlignmentMonitorPanel: React.FC<AlignmentMonitorPanelProps> = ({ missionId }) => {
  const [overview, setOverview] = React.useState<MonitoringOverview | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        setLoading(true);
        setError(null);
        const response = await apiClient.getMonitoringOverview(missionId);
        if (!cancelled) setOverview(response);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load monitoring state');
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    void load();
    return () => {
      cancelled = true;
    };
  }, [missionId]);

  const metrics = overview?.metrics || {};
  const confidenceMetrics = metrics.confidence || {};
  const contradictionMetrics = metrics.contradictions || {};
  const evidenceMetrics = metrics.evidence_balance || {};
  const freshnessMetrics = metrics.freshness || {};
  const contradictionLoadLabel =
    contradictionMetrics.active_contradiction_topic_count != null
      ? `${contradictionMetrics.active_contradiction_topic_count} topics`
      : String(contradictionMetrics.active_contradiction_count || 0);

  return (
    <div className="rounded-2xl border border-neutral-200 bg-white shadow-[0_12px_32px_-20px_rgba(15,23,42,0.3)]">
      <div className="border-b border-neutral-200 px-5 py-4">
        <div className="flex items-center gap-3">
          <ShieldAlert className="h-5 w-5 text-amber-600" />
          <div>
            <h3 className="text-lg font-semibold tracking-[-0.02em] text-neutral-950">Alignment Monitor</h3>
            <p className="text-sm text-neutral-600">Mission-level oversight for drift, bias, contradictions, and responsiveness.</p>
          </div>
        </div>
      </div>

      {loading ? (
        <div className="p-5 text-sm text-neutral-600">Loading alignment signals...</div>
      ) : error ? (
        <div className="m-5 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>
      ) : !overview ? (
        <div className="p-5 text-sm text-neutral-600">No monitoring state available yet.</div>
      ) : (
        <div className="space-y-5 p-5">
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <MetricCard
              icon={overview.overall_health === 'HEALTHY' ? ShieldCheck : ShieldAlert}
              label="Overall Health"
              value={overview.overall_health}
              tone={healthTone(overview.overall_health)}
            />
            <MetricCard
              icon={Siren}
              label="Active Alerts"
              value={String(overview.active_alert_count)}
              tone={overview.active_alert_count > 0 ? 'amber' : 'neutral'}
            />
            <MetricCard
              icon={Gauge}
              label="Confidence Velocity"
              value={formatSigned(confidenceMetrics.confidence_velocity)}
              tone={Math.abs(confidenceMetrics.confidence_velocity || 0) > 0.05 ? 'amber' : 'neutral'}
            />
            <MetricCard
              icon={Activity}
              label="Contradiction Load"
              value={contradictionLoadLabel}
              tone={(contradictionMetrics.active_contradiction_count || 0) > 5 ? 'red' : 'neutral'}
            />
          </div>

          <div className="grid gap-4 xl:grid-cols-[1.4fr_1fr]">
            <section className="rounded-2xl border border-neutral-200 bg-neutral-50/70 p-4">
              <div className="mb-4 flex items-center justify-between gap-3">
                <div>
                  <h4 className="text-sm font-semibold text-neutral-900">Active Monitoring Alerts</h4>
                  <p className="text-xs text-neutral-500">Only the alerts that are currently shaping mission health.</p>
                </div>
                <span className="rounded-full bg-white px-2.5 py-1 text-xs font-medium text-neutral-600 shadow-sm">
                  Cycle {overview.current_cycle}
                </span>
              </div>

              {overview.active_alerts.length === 0 ? (
                <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
                  No active alignment alerts. The mission currently looks healthy from the oversight layer.
                </div>
              ) : (
                <ScrollFadePanel heightClassName="h-[18rem]">
                  <div className="space-y-3 pb-8">
                    {overview.active_alerts.map((alert) => (
                      <div
                        key={alert.id}
                        className={`rounded-2xl border px-4 py-3 shadow-sm ${alertCardTone(alert.severity)}`}
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <div className="flex items-center gap-2">
                              <span className="rounded-full bg-white/80 px-2 py-0.5 text-[11px] font-semibold tracking-[0.12em] text-neutral-700">
                                {alert.severity}
                              </span>
                              <span className="text-sm font-semibold text-neutral-900">
                                {formatAlertTitle(alert.alert_type)}
                              </span>
                            </div>
                            <p className="mt-2 text-sm leading-6 text-neutral-700">{alert.message}</p>
                          </div>
                          <span className="text-xs text-neutral-500">Cycle {alert.last_cycle_number}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </ScrollFadePanel>
              )}
            </section>

            <section className="rounded-2xl border border-neutral-200 bg-white p-4">
              <h4 className="text-sm font-semibold text-neutral-900">Oversight Metrics</h4>
              <div className="mt-4 space-y-3">
                <SignalRow
                  label="Trajectory divergence"
                  value={formatMetric(confidenceMetrics.trajectory_divergence)}
                  hint="How far confidence movement is drifting from the evidence-justified path."
                />
                <SignalRow
                  label="Contradiction acknowledgment"
                  value={formatPercent(contradictionMetrics.contradiction_acknowledgment_rate)}
                  hint="Share of active high/medium contradictions already surfaced in synthesis."
                />
                <SignalRow
                  label="Support ratio"
                  value={formatPercent(evidenceMetrics.support_ratio)}
                  hint="How much of the primary evidence cluster still aligns with the current dominant direction."
                  reliability={evidenceMetrics.support_ratio_reliability}
                />
                <SignalRow
                  label="Retrieval balance"
                  value={formatPercent(evidenceMetrics.directional_retrieval_balance)}
                  hint="Whether recent retrieval is disproportionately aligned with the current belief."
                  reliability={evidenceMetrics.directional_retrieval_balance_reliability}
                />
                <SignalRow
                  label="Mean paper age"
                  value={formatYears(freshnessMetrics.mean_paper_age)}
                  hint="Average age of the currently weighted evidence base."
                  reliability={freshnessMetrics.mean_paper_age_reliability}
                />
                <SignalRow
                  label="Recent ingestion rate"
                  value={formatPercent(freshnessMetrics.recent_ingestion_rate)}
                  hint="Fraction of newly ingested papers that are from the last three years."
                  reliability={freshnessMetrics.recent_ingestion_rate_reliability}
                />
              </div>
            </section>
          </div>

          {overview.benchmark && (
            <div className="rounded-2xl border border-neutral-200 bg-neutral-50 p-4">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <h4 className="text-sm font-semibold text-neutral-900">Benchmark Comparison</h4>
                  <p className="text-xs text-neutral-500">
                    External benchmark: {overview.benchmark.benchmark_source || 'configured reference'}
                  </p>
                </div>
                <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${benchmarkTone(overview.benchmark.classification)}`}>
                  {overview.benchmark.classification}
                </span>
              </div>
              <p className="mt-3 text-sm text-neutral-700">
                Similarity {Math.round((overview.benchmark.benchmark_similarity || 0) * 100)}%
              </p>
              {overview.benchmark.disagreements?.length > 0 && (
                <div className="mt-3 space-y-2">
                  {overview.benchmark.disagreements.map((item, index) => (
                    <div key={`${item.tag}-${index}`} className="rounded-xl border border-neutral-200 bg-white px-3 py-2 text-sm text-neutral-700">
                      <span className="mr-2 rounded-full bg-neutral-100 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-neutral-600">
                        {item.tag}
                      </span>
                      {item.description}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

const MetricCard: React.FC<{
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string;
  tone: 'neutral' | 'green' | 'amber' | 'red';
}> = ({ icon: Icon, label, value, tone }) => (
  <div className={`rounded-2xl border px-4 py-3 shadow-sm ${metricTone(tone)}`}>
    <div className="flex items-center gap-2 text-xs font-medium text-neutral-600">
      <Icon className="h-4 w-4" />
      {label}
    </div>
    <div className="mt-2 text-xl font-semibold tracking-[-0.02em] text-neutral-950">{value}</div>
  </div>
);

const SignalRow: React.FC<{
  label: string;
  value: string;
  hint: string;
  reliability?: { level?: string; reason?: string; sample_size?: number } | null;
}> = ({ label, value, hint, reliability }) => (
  <div className="rounded-xl border border-neutral-200 bg-neutral-50 px-3 py-3">
    <div className="flex items-center justify-between gap-3">
      <div className="flex items-center gap-2">
        <span className="text-sm font-medium text-neutral-800">{label}</span>
        {reliability && (
          <span
            className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.12em] ${reliabilityTone(
              reliability.level,
            )}`}
            title={reliability.reason || undefined}
          >
            {reliability.level || 'unknown'}
          </span>
        )}
      </div>
      <span className="text-sm font-semibold text-neutral-950">{value}</span>
    </div>
    <p className="mt-1 text-xs leading-5 text-neutral-500">{hint}</p>
    {reliability?.reason && reliability.level !== 'high' && (
      <p className="mt-1 text-[11px] leading-5 text-neutral-400">{reliability.reason}</p>
    )}
  </div>
);

const formatPercent = (value?: number | null) => (value == null ? '—' : `${Math.round(value * 100)}%`);
const formatMetric = (value?: number | null) => (value == null ? '—' : value.toFixed(2));
const formatSigned = (value?: number | null) => (value == null ? '+0.00' : `${value >= 0 ? '+' : ''}${value.toFixed(2)}`);
const formatYears = (value?: number | null) => (value == null ? '—' : `${value.toFixed(1)}y`);
const formatAlertTitle = (value: string) => value.toLowerCase().split('_').map(part => part.charAt(0).toUpperCase() + part.slice(1)).join(' ');

const healthTone = (value: string): 'neutral' | 'green' | 'amber' | 'red' => {
  if (value === 'HEALTHY') return 'green';
  if (value === 'WATCH') return 'amber';
  if (value === 'DEGRADED' || value === 'CRITICAL') return 'red';
  return 'neutral';
};

const metricTone = (tone: 'neutral' | 'green' | 'amber' | 'red') => {
  if (tone === 'green') return 'border-emerald-200 bg-emerald-50/70';
  if (tone === 'amber') return 'border-amber-200 bg-amber-50/70';
  if (tone === 'red') return 'border-red-200 bg-red-50/70';
  return 'border-neutral-200 bg-neutral-50/80';
};

const alertCardTone = (severity: string) => {
  if (severity === 'HIGH') return 'border-red-200 bg-red-50/80';
  if (severity === 'MEDIUM') return 'border-amber-200 bg-amber-50/80';
  return 'border-neutral-200 bg-neutral-50';
};

const benchmarkTone = (classification: string) => {
  if (classification === 'ALIGNED') return 'bg-emerald-100 text-emerald-700';
  if (classification === 'MISALIGNED') return 'bg-red-100 text-red-700';
  return 'bg-amber-100 text-amber-700';
};

const reliabilityTone = (level?: string) => {
  if (level === 'high') return 'bg-emerald-100 text-emerald-700';
  if (level === 'medium') return 'bg-sky-100 text-sky-700';
  if (level === 'low') return 'bg-amber-100 text-amber-700';
  return 'bg-neutral-200 text-neutral-600';
};
