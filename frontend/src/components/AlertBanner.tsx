import React from 'react';
import { AlertCircle, X } from 'lucide-react';

export interface AlertBannerItem {
  mission_name: string;
  alert_type: string;
  mission_id: string;
}

interface AlertBannerProps {
  alerts: AlertBannerItem[];
  onDismiss?: () => void;
  onNavigate?: (missionId: string) => void;
}

export const AlertBanner: React.FC<AlertBannerProps> = ({ alerts, onDismiss, onNavigate }) => {
  if (!alerts || alerts.length === 0) {
    return null;
  }

  return (
    <div className="bg-red-50 border-b border-red-200 px-6 py-3">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-start gap-3 flex-1">
          <AlertCircle className="text-red-600 flex-shrink-0 mt-0.5" size={18} />
          <div className="flex-1 min-w-0">
            <h3 className="text-sm font-semibold text-red-900">Critical Alerts</h3>
            <div className="mt-2 space-y-1">
              {alerts.map((alert, index) => (
                <div key={index} className="text-sm text-red-800">
                  <button
                    onClick={() => onNavigate?.(alert.mission_id)}
                    className="font-medium text-red-700 hover:underline"
                  >
                    {alert.mission_name}
                  </button>
                  {' — '}
                  <span>{alert.alert_type.replace(/_/g, ' ')}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
        <button
          onClick={onDismiss}
          className="text-red-600 hover:text-red-700 flex-shrink-0"
        >
          <X size={18} />
        </button>
      </div>
    </div>
  );
};
