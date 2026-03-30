import React from 'react';
import type { HealthStatus, AlertSeverity } from '@/types';

interface StatusPillProps {
  status: HealthStatus | AlertSeverity;
  text?: string;
}

export const StatusPill: React.FC<StatusPillProps> = ({ status, text }) => {
  const statusColors: Record<string, string> = {
    HEALTHY: 'bg-green-100 text-green-700',
    WATCH: 'bg-amber-100 text-amber-700',
    DEGRADED: 'bg-red-100 text-red-700',
    CRITICAL: 'bg-red-900 text-red-50',
    'critical': 'bg-red-900 text-red-50',
    'degraded': 'bg-red-100 text-red-700',
    'watch': 'bg-amber-100 text-amber-700',
    'info': 'bg-blue-100 text-blue-700',
  };

  return (
    <span className={`inline-flex items-center rounded-pill px-2.5 py-0.5 text-xs font-semibold ${statusColors[status] || 'bg-gray-100 text-gray-700'}`}>
      {text || status}
    </span>
  );
};
