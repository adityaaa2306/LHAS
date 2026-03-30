import React from 'react';
import { ChevronDown, Grid3X3, List } from 'lucide-react';
import type { HealthStatus, MissionStatus, IntentType } from '@/types';

export interface FilterState {
  sortBy: 'last-run' | 'health' | 'confidence' | 'sessions' | 'created';
  status: MissionStatus[];
  health: HealthStatus[];
  intentType: IntentType[];
  hasAlerts: boolean;
  viewMode: 'grid' | 'table';
}

interface FiltersProps {
  filters: FilterState;
  onFilterChange: (filters: FilterState) => void;
}

export const Filters: React.FC<FiltersProps> = ({ filters, onFilterChange }) => {
  const [showSortMenu, setShowSortMenu] = React.useState(false);

  const sortOptions = [
    { id: 'last-run', label: 'Last Run (default)' },
    { id: 'health', label: 'Health (worst first)' },
    { id: 'confidence', label: 'Confidence Score' },
    { id: 'sessions', label: 'Session Count' },
    { id: 'created', label: 'Date Created' },
  ];

  const statusOptions: { id: MissionStatus; label: string }[] = [
    { id: 'active', label: 'Active' },
    { id: 'paused', label: 'Paused' },
    { id: 'idle', label: 'Idle' },
    { id: 'archived', label: 'Archived' },
  ];

  const healthOptions: HealthStatus[] = ['HEALTHY', 'WATCH', 'DEGRADED', 'CRITICAL'];

  const intentOptions: IntentType[] = ['Causal', 'Comparative', 'Exploratory', 'Descriptive'];

  const toggleFilter = (type: 'status' | 'health' | 'intentType', value: any) => {
    const newFilters = { ...filters };
    const array = newFilters[type] as any[];
    const index = array.indexOf(value);

    if (index > -1) {
      array.splice(index, 1);
    } else {
      array.push(value);
    }

    onFilterChange(newFilters);
  };

  return (
    <div className="px-6 py-4 border-b border-neutral-200 bg-neutral-50">
      <div className="flex items-center gap-4 flex-wrap">
        {/* Sort Dropdown */}
        <div className="relative">
          <button
            onClick={() => setShowSortMenu(!showSortMenu)}
            className="flex items-center gap-2 px-3 py-2 bg-white border border-neutral-200 rounded-lg text-sm font-medium text-neutral-600 hover:bg-neutral-50"
          >
            Sort by: {sortOptions.find(o => o.id === filters.sortBy)?.label.split('(')[0]}
            <ChevronDown size={14} />
          </button>
          {showSortMenu && (
            <div className="absolute top-full mt-1 bg-white border border-neutral-200 rounded-lg shadow-lg z-10 min-w-48">
              {sortOptions.map(option => (
                <button
                  key={option.id}
                  onClick={() => {
                    onFilterChange({ ...filters, sortBy: option.id as any });
                    setShowSortMenu(false);
                  }}
                  className={`block w-full text-left px-4 py-2 text-sm ${
                    filters.sortBy === option.id
                      ? 'bg-primary-50 text-primary-600 font-semibold'
                      : 'text-neutral-700 hover:bg-neutral-50'
                  }`}
                >
                  {option.label}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Status Filter */}
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold text-neutral-600">Status:</span>
          <div className="flex gap-2">
            {statusOptions.map(option => (
              <button
                key={option.id}
                onClick={() => toggleFilter('status', option.id)}
                className={`px-3 py-1 rounded-pill text-xs font-medium transition-colors ${
                  filters.status.includes(option.id)
                    ? 'bg-primary-500 text-white'
                    : 'bg-white border border-neutral-200 text-neutral-600 hover:border-neutral-300'
                }`}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>

        {/* Health Filter */}
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold text-neutral-600">Health:</span>
          <div className="flex gap-2">
            {healthOptions.map(option => {
              const colorMap: Record<HealthStatus, string> = {
                HEALTHY: 'bg-green-100 text-green-700 border-green-200',
                WATCH: 'bg-amber-100 text-amber-700 border-amber-200',
                DEGRADED: 'bg-red-100 text-red-700 border-red-200',
                CRITICAL: 'bg-red-900 text-red-50 border-red-800',
              };
              return (
                <button
                  key={option}
                  onClick={() => toggleFilter('health', option)}
                  className={`px-3 py-1 rounded-pill text-xs font-medium border transition-colors ${
                    filters.health.includes(option) ? colorMap[option] : 'bg-white border-neutral-200 text-neutral-600 hover:border-neutral-300'
                  }`}
                >
                  {option}
                </button>
              );
            })}
          </div>
        </div>

        {/* Intent Type Filter */}
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold text-neutral-600">Intent:</span>
          <div className="flex gap-2">
            {intentOptions.map(option => (
              <button
                key={option}
                onClick={() => toggleFilter('intentType', option)}
                className={`px-3 py-1 rounded-pill text-xs font-medium transition-colors ${
                  filters.intentType.includes(option)
                    ? 'bg-secondary-500 text-white'
                    : 'bg-white border border-neutral-200 text-neutral-600 hover:border-neutral-300'
                }`}
              >
                {option}
              </button>
            ))}
          </div>
        </div>

        {/* Alerts Toggle */}
        <button
          onClick={() => onFilterChange({ ...filters, hasAlerts: !filters.hasAlerts })}
          className={`px-3 py-1 rounded-pill text-xs font-medium border transition-colors ${
            filters.hasAlerts
              ? 'bg-red-100 text-red-700 border-red-200'
              : 'bg-white border-neutral-200 text-neutral-600 hover:border-neutral-300'
          }`}
        >
          Has Active Alerts
        </button>

        {/* View Toggle */}
        <div className="ml-auto flex gap-1 bg-white border border-neutral-200 rounded-lg p-1">
          <button
            onClick={() => onFilterChange({ ...filters, viewMode: 'grid' })}
            className={`p-1.5 rounded transition-colors ${
              filters.viewMode === 'grid'
                ? 'bg-neutral-200 text-neutral-900'
                : 'text-neutral-600 hover:bg-neutral-100'
            }`}
          >
            <Grid3X3 size={16} />
          </button>
          <button
            onClick={() => onFilterChange({ ...filters, viewMode: 'table' })}
            className={`p-1.5 rounded transition-colors ${
              filters.viewMode === 'table'
                ? 'bg-neutral-200 text-neutral-900'
                : 'text-neutral-600 hover:bg-neutral-100'
            }`}
          >
            <List size={16} />
          </button>
        </div>
      </div>
    </div>
  );
};
