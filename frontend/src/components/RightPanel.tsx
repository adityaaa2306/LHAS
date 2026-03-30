import React from 'react';
import { X, Tag, AlertCircle, CheckCircle } from 'lucide-react';
import type { Mission, Session, Alert } from '@/types';
import { StatusPill } from './StatusPill';

interface RightPanelProps {
  mission: Mission | null;
  sessions: Session[];
  alerts: Alert[];
  isOpen: boolean;
  onClose: () => void;
}

export const RightPanel: React.FC<RightPanelProps> = ({
  mission,
  sessions,
  alerts,
  isOpen,
  onClose,
}) => {
  const [activeTab, setActiveTab] = React.useState<'overview' | 'sessions' | 'alerts'>('overview');

  if (!isOpen || !mission) {
    return null;
  }

  return (
    <div className="fixed inset-y-0 right-0 w-96 bg-white border-l border-neutral-200 shadow-xl z-40 overflow-hidden flex flex-col">
      {/* Header */}
      <div className="border-b border-neutral-200 px-6 py-4 flex items-center justify-between bg-neutral-50">
        <h2 className="font-semibold text-neutral-900 truncate">{mission.name}</h2>
        <button
          onClick={onClose}
          className="text-neutral-400 hover:text-neutral-600 p-1"
        >
          <X size={20} />
        </button>
      </div>

      {/* Tab buttons */}
      <div className="border-b border-neutral-200 px-6 flex gap-8 bg-white">
        {['overview', 'sessions', 'alerts'].map(tab => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab as any)}
            className={`py-3 text-sm font-medium border-b-2 transition-colors ${
              activeTab === tab
                ? 'border-primary-500 text-primary-600'
                : 'border-transparent text-neutral-600 hover:text-neutral-900'
            }`}
          >
            {tab.charAt(0).toUpperCase() + tab.slice(1)}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-6 py-4">
        {activeTab === 'overview' && (
          <div className="space-y-4">
            {/* Full query */}
            <div>
              <h3 className="text-xs font-semibold text-neutral-600 uppercase tracking-wide mb-2">Research Question</h3>
              <p className="text-sm text-neutral-700 leading-relaxed">{mission.normalized_query}</p>
            </div>

            {/* PICO breakdown */}
            {mission.pico && (
              <div>
                <h3 className="text-xs font-semibold text-neutral-600 uppercase tracking-wide mb-2">PICO Breakdown</h3>
                <div className="space-y-2">
                  <div>
                    <p className="text-xs text-neutral-500">Population</p>
                    <p className="text-sm text-neutral-700">{mission.pico.population}</p>
                  </div>
                  <div>
                    <p className="text-xs text-neutral-500">Intervention</p>
                    <p className="text-sm text-neutral-700">{mission.pico.intervention}</p>
                  </div>
                  <div>
                    <p className="text-xs text-neutral-500">Comparator</p>
                    <p className="text-sm text-neutral-700">{mission.pico.comparator}</p>
                  </div>
                  <div>
                    <p className="text-xs text-neutral-500">Outcome</p>
                    <p className="text-sm text-neutral-700">{mission.pico.outcome}</p>
                  </div>
                </div>
              </div>
            )}

            {/* Decision + Confidence */}
            <div>
              <h3 className="text-xs font-semibold text-neutral-600 uppercase tracking-wide mb-2">Query Status</h3>
              <div className="space-y-2">
                {mission.decision && (
                  <div>
                    <p className="text-xs text-neutral-500">Decision</p>
                    <StatusPill status={mission.decision === 'PROCEED' ? 'HEALTHY' : 'WATCH'} text={mission.decision} />
                  </div>
                )}
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <p className="text-xs text-neutral-500">Initial Confidence</p>
                    <p className="text-sm font-semibold text-neutral-900">{Math.round(mission.confidence_from_module1 || 0)}%</p>
                  </div>
                  <div>
                    <p className="text-xs text-neutral-500">Current Confidence</p>
                    <p className="text-sm font-semibold text-neutral-900">{Math.round(mission.confidence_score)}%</p>
                  </div>
                </div>
              </div>
            </div>

            {/* Key concepts */}
            {mission.key_concepts.length > 0 && (
              <div>
                <h3 className="text-xs font-semibold text-neutral-600 uppercase tracking-wide mb-2">Key Concepts</h3>
                <div className="flex flex-wrap gap-2">
                  {mission.key_concepts.map(concept => (
                    <span
                      key={concept}
                      className="inline-flex items-center gap-1 bg-accent-50 text-accent-700 px-2 py-1 rounded text-xs font-medium"
                    >
                      <Tag size={12} />
                      {concept}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Ambiguity flags */}
            {mission.ambiguity_flags && mission.ambiguity_flags.length > 0 && (
              <div>
                <h3 className="text-xs font-semibold text-neutral-600 uppercase tracking-wide mb-2">Ambiguity Flags</h3>
                <div className="space-y-1">
                  {mission.ambiguity_flags.map((flag, index) => (
                    <p key={index} className="text-xs text-neutral-600 flex items-start gap-2">
                      <AlertCircle size={12} className="mt-0.5 text-amber-500 flex-shrink-0" />
                      {flag}
                    </p>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {activeTab === 'sessions' && (
          <div className="space-y-2">
            {sessions.length === 0 ? (
              <p className="text-sm text-neutral-500 text-center py-8">No sessions yet</p>
            ) : (
              sessions.map((session) => (
                <div
                  key={session.id}
                  className="border border-neutral-200 rounded-lg p-3 hover:bg-neutral-50 cursor-pointer transition-colors"
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-semibold text-neutral-600">Session {session.session_number}</span>
                        <StatusPill status={session.status === 'Completed' ? 'HEALTHY' : session.status === 'Failed' ? 'DEGRADED' : 'WATCH'} text={session.status} />
                      </div>
                      <p className="text-xs text-neutral-500 mt-1">
                        {new Date(session.timestamp).toLocaleString()}
                      </p>
                      <div className="flex gap-4 mt-2 text-xs text-neutral-600">
                        <span>Papers: {session.papers_ingested}</span>
                        <span>Claims: {session.claims_extracted}</span>
                      </div>
                    </div>
                    <StatusPill status={session.health} />
                  </div>
                </div>
              ))
            )}
          </div>
        )}

        {activeTab === 'alerts' && (
          <div className="space-y-2">
            {alerts.length === 0 ? (
              <p className="text-sm text-neutral-500 text-center py-8">No alerts</p>
            ) : (
              alerts.map(alert => (
                <div
                  key={alert.id}
                  className="border border-neutral-200 rounded-lg p-3"
                >
                  <div className="flex items-start justify-between mb-2">
                    <span className="text-xs font-semibold text-neutral-900">{alert.alert_type}</span>
                    <StatusPill status={alert.severity} />
                  </div>
                  <p className="text-xs text-neutral-600 mb-2">
                    Cycle {alert.cycle_number} · {alert.lifecycle_status}
                  </p>
                  {alert.resolved_at && (
                    <div className="flex items-start gap-2 text-xs text-green-700 bg-green-50 p-2 rounded">
                      <CheckCircle size={12} className="mt-0.5 flex-shrink-0" />
                      <div>
                        <p className="font-medium">Resolved</p>
                        <p className="text-green-600">{alert.resolution_record}</p>
                      </div>
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        )}
      </div>
    </div>
  );
};
