import React from 'react';
import { TrendingUp, TrendingDown } from 'lucide-react';

export interface StatsTile {
  label: string;
  value: number | string;
  trend?: 'up' | 'down';
  trendValue?: number;
  icon?: React.ReactNode;
  color?: 'primary' | 'secondary' | 'accent' | 'alert';
}

interface StatsRowProps {
  stats: StatsTile[];
}

export const StatsRow: React.FC<StatsRowProps> = ({ stats }) => {
  const colorClasses: Record<string, string> = {
    primary: 'bg-primary-50 border-primary-200',
    secondary: 'bg-blue-50 border-blue-200',
    accent: 'bg-purple-50 border-purple-200',
    alert: 'bg-red-50 border-red-200',
  };

  const textColorClasses: Record<string, string> = {
    primary: 'text-primary-900',
    secondary: 'text-blue-900',
    accent: 'text-purple-900',
    alert: 'text-red-900',
  };

  return (
    <div className="grid grid-cols-4 gap-4 px-6 py-4">
      {stats.map((stat, index) => (
        <div
          key={index}
          className={`border rounded-lg p-4 ${colorClasses[stat.color || 'primary']}`}
        >
          <div className="flex items-start justify-between">
            <div className="flex-1">
              <p className={`text-xs font-semibold uppercase tracking-wide ${textColorClasses[stat.color || 'primary']}`}>
                {stat.label}
              </p>
              <div className="flex items-baseline gap-2 mt-2">
                <p className={`text-2xl font-bold ${textColorClasses[stat.color || 'primary']}`}>
                  {stat.value}
                </p>
                {stat.trend && stat.trendValue !== undefined && (
                  <div className={`flex items-center gap-1 text-xs font-semibold ${stat.trend === 'up' ? 'text-green-600' : 'text-red-600'}`}>
                    {stat.trend === 'up' ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
                    <span>{stat.trendValue}%</span>
                  </div>
                )}
              </div>
            </div>
            {stat.icon && (
              <div className={`flex-shrink-0 ${textColorClasses[stat.color || 'primary']}`}>
                {stat.icon}
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
};
