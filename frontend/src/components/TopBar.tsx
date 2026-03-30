import React from 'react';
import { Search, Moon, Plus } from 'lucide-react';

interface TopBarProps {
  onNewMission?: () => void;
  onSearchChange?: (query: string) => void;
}

export const TopBar: React.FC<TopBarProps> = ({ onNewMission, onSearchChange }) => {
  const [searchQuery, setSearchQuery] = React.useState('');

  const handleSearchChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const query = e.target.value;
    setSearchQuery(query);
    onSearchChange?.(query);
  };

  return (
    <div className="bg-white border-b border-neutral-200 px-6 py-4">
      <div className="flex items-center justify-between">
        {/* Breadcrumb */}
        <div className="flex items-center gap-2">
          <h1 className="text-lg font-semibold text-neutral-900">Missions</h1>
        </div>

        {/* Right side: Search + Actions */}
        <div className="flex items-center gap-3">
          {/* Search Bar */}
          <div className="relative w-72">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-400" size={18} />
            <input
              type="text"
              placeholder="Search by mission name or query..."
              value={searchQuery}
              onChange={handleSearchChange}
              className="w-full pl-10 pr-4 py-2 bg-neutral-50 border border-neutral-200 rounded-lg text-sm placeholder-neutral-500 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:bg-white"
            />
          </div>

          {/* Dark mode toggle */}
          <button className="p-2 text-neutral-600 hover:bg-neutral-100 rounded-lg transition-colors">
            <Moon size={18} />
          </button>

          {/* New Mission Button */}
          <button
            onClick={onNewMission}
            className="flex items-center gap-2 bg-primary-500 text-white px-4 py-2 rounded-lg hover:bg-primary-600 transition-colors font-medium text-sm"
          >
            <Plus size={18} />
            New Mission
          </button>
        </div>
      </div>
    </div>
  );
};
