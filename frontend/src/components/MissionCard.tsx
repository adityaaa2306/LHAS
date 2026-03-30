import React from 'react';
import { useNavigate } from 'react-router-dom';
import { MoreVertical, Activity, AlertCircle, Trash2 } from 'lucide-react';
import type { Mission } from '@/types';
import { StatusPill } from './StatusPill';
import { ConfidenceSparkline } from './ConfidenceSparkline';

interface MissionCardProps {
  mission: Mission;
  onClick?: () => void;
  onMenuOpen?: (missionId: string) => void;
  onDeleted?: (missionId: string) => void;
}

export const MissionCard: React.FC<MissionCardProps> = ({ mission, onClick, onMenuOpen, onDeleted }) => {
  const navigate = useNavigate();
  const [showMenu, setShowMenu] = React.useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = React.useState(false);
  const [deleting, setDeleting] = React.useState(false);

  const getStatusIndicator = () => {
    switch (mission.status) {
      case 'active':
        return { indicator: '●', color: 'text-green-500', label: 'Active' };
      case 'paused':
        return { indicator: '◌', color: 'text-amber-500', label: 'Paused' };
      case 'idle':
        return { indicator: '–', color: 'text-neutral-400', label: 'Idle' };
      case 'archived':
        return { indicator: '✕', color: 'text-neutral-400', label: 'Archived' };
      default:
        return { indicator: '–', color: 'text-neutral-400', label: 'Unknown' };
    }
  };

  const statusInfo = getStatusIndicator();

  const handleCardClick = () => {
    navigate(`/missions/${mission.id}`);
    onClick?.();
  };

  const handleDelete = async () => {
    setDeleting(true);
    try {
      const response = await fetch(`http://localhost:8000/api/dashboard/missions/${mission.id}`, {
        method: 'DELETE',
      });

      if (!response.ok) {
        throw new Error('Failed to delete mission');
      }

      onDeleted?.(mission.id);
      setShowDeleteConfirm(false);
    } catch (err) {
      console.error('Delete error:', err);
      alert('Failed to delete mission. Please try again.');
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div
      onClick={handleCardClick}
      className="bg-white border border-neutral-200 rounded-lg overflow-hidden hover:shadow-md hover:border-primary-200 transition-all cursor-pointer group"
    >
      {/* Header row: Mission name + Health pill + Menu */}
      <div className="px-4 py-3 border-b border-neutral-200 flex items-start justify-between bg-neutral-50">
        <div className="flex-1 min-w-0">
          <h3 className="font-semibold text-neutral-900 truncate">{mission.name}</h3>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <StatusPill status={mission.health} />
          <div className="relative">
            <button
              onClick={(e) => {
                e.stopPropagation();
                setShowMenu(!showMenu);
                onMenuOpen?.(mission.id);
              }}
              className="p-1 text-neutral-400 hover:text-neutral-600 rounded hover:bg-white transition-colors opacity-0 group-hover:opacity-100"
            >
              <MoreVertical size={16} />
            </button>
            {showMenu && (
              <div className="absolute right-0 top-full mt-1 bg-white border border-neutral-200 rounded-lg shadow-lg z-10">
                <button className="block w-full text-left px-3 py-2 text-sm text-neutral-700 hover:bg-neutral-50">Rename</button>
                <button className="block w-full text-left px-3 py-2 text-sm text-neutral-700 hover:bg-neutral-50">Pause</button>
                <button className="block w-full text-left px-3 py-2 text-sm text-neutral-700 hover:bg-neutral-50">View Sessions</button>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    setShowMenu(false);
                    setShowDeleteConfirm(true);
                  }}
                  className="block w-full text-left px-3 py-2 text-sm text-red-700 hover:bg-red-50"
                >
                  Delete
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Query line */}
      <div className="px-4 py-2 bg-white border-b border-neutral-200">
        <p className="text-xs text-neutral-500 line-clamp-2">{mission.normalized_query}</p>
      </div>

      {/* Intent badge + Status indicator */}
      <div className="px-4 py-3 flex items-center justify-between border-b border-neutral-200">
        <div className="flex items-center gap-2">
          <span className="inline-block px-2 py-1 bg-secondary-50 text-secondary-700 rounded text-xs font-medium">
            {mission.intent_type}
          </span>
          <span className={`text-lg ${statusInfo.color} font-bold`}>{statusInfo.indicator}</span>
        </div>
        <p className="text-xs text-neutral-500">{mission.session_count} sessions</p>
      </div>

      {/* Last session stats */}
      <div className="px-4 py-3 border-b border-neutral-200">
        <p className="text-xs text-neutral-500 mb-2">
          Last run · {mission.last_run ? new Date(mission.last_run).toLocaleString() : 'Never'}
        </p>
        <div className="grid grid-cols-3 gap-2">
          <div className="bg-neutral-50 p-2 rounded">
            <p className="text-xs text-neutral-500">Papers</p>
            <p className="text-sm font-semibold text-neutral-900">{mission.total_papers}</p>
          </div>
          <div className="bg-neutral-50 p-2 rounded">
            <p className="text-xs text-neutral-500">Claims</p>
            <p className="text-sm font-semibold text-neutral-900">{mission.total_claims}</p>
          </div>
          <div className="bg-neutral-50 p-2 rounded">
            <p className="text-xs text-neutral-500">Confidence</p>
            <p className="text-sm font-semibold text-neutral-900">{Math.round(mission.confidence_score)}%</p>
          </div>
        </div>
      </div>

      {/* Confidence velocity sparkline + Alert count */}
      <div className="px-4 py-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <p className="text-xs text-neutral-500">Trend:</p>
          <ConfidenceSparkline data={mission.confidence_velocity} />
        </div>
        {mission.active_alerts > 0 && (
          <div className="flex items-center gap-1 bg-red-50 px-2 py-1 rounded text-xs font-semibold text-red-700">
            <Activity size={12} />
            {mission.active_alerts} alert{mission.active_alerts !== 1 ? 's' : ''}
          </div>
        )}
      </div>

      {/* Delete Confirmation Dialog */}
      {showDeleteConfirm && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-lg shadow-xl max-w-sm w-full">
            <div className="p-6">
              <div className="flex items-center gap-3 mb-4">
                <div className="flex-shrink-0 flex items-center justify-center h-12 w-12 rounded-full bg-red-100">
                  <AlertCircle size={24} className="text-red-600" />
                </div>
                <div>
                  <h3 className="text-lg font-medium text-neutral-900">Delete Mission</h3>
                  <p className="text-sm text-neutral-500 mt-1">Are you sure you want to delete this mission?</p>
                </div>
              </div>

              <div className="bg-red-50 border border-red-200 rounded-lg p-3 mb-6">
                <p className="text-sm text-red-800">
                  <strong>"{mission.name}"</strong> will be permanently deleted along with all its associated data, sessions, and alerts.
                </p>
              </div>

              <div className="flex gap-3">
                <button
                  onClick={() => setShowDeleteConfirm(false)}
                  disabled={deleting}
                  className="flex-1 px-4 py-2 rounded-lg border border-neutral-300 text-neutral-900 font-medium hover:bg-neutral-50 transition-colors disabled:opacity-50"
                >
                  Cancel
                </button>
                <button
                  onClick={handleDelete}
                  disabled={deleting}
                  className="flex-1 px-4 py-2 rounded-lg bg-red-600 text-white font-medium hover:bg-red-700 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
                >
                  {deleting ? (
                    <>
                      <Activity size={16} className="animate-spin" />
                      Deleting...
                    </>
                  ) : (
                    <>
                      <Trash2 size={16} />
                      Delete
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
