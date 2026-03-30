import React from 'react';
import { Inbox } from 'lucide-react';

interface EmptyStateProps {
  onNewMission?: () => void;
}

export const EmptyState: React.FC<EmptyStateProps> = ({ onNewMission }) => {
  return (
    <div className="flex flex-col items-center justify-center py-20 px-6">
      <div className="text-neutral-300 mb-4">
        <Inbox size={48} />
      </div>
      <h2 className="text-xl font-semibold text-neutral-900 mb-2">No missions yet</h2>
      <p className="text-neutral-600 text-center mb-6 max-w-sm">
        Start by creating your first research mission to begin tracking evidence, extracting claims, and monitoring hypothesis evolution.
      </p>
      <button
        onClick={onNewMission}
        className="flex items-center gap-2 bg-primary-500 text-white px-6 py-3 rounded-lg hover:bg-primary-600 transition-colors font-medium"
      >
        Create New Mission
      </button>
    </div>
  );
};
