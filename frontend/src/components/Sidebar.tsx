import React from 'react';
import {
  Home,
  AlertCircle,
  BarChart3,
  Settings,
  ChevronDown,
  Menu,
} from 'lucide-react';

interface SidebarProps {
  activeItem?: string;
  onNavigate?: (item: string) => void;
}

export const Sidebar: React.FC<SidebarProps> = ({ activeItem = 'missions', onNavigate }) => {
  const [isExpanded, setIsExpanded] = React.useState(true);

  const navigationItems = [
    { id: 'missions', label: 'Missions', icon: Home },
    { id: 'alerts', label: 'Alerts', icon: AlertCircle },
    { id: 'reports', label: 'Reports', icon: BarChart3 },
    { id: 'settings', label: 'Settings', icon: Settings },
  ];

  const modules = [
    'Query Understanding',
    'Paper Ingestion',
    'Claim Extraction',
    'Memory System',
    'Belief Revision',
    'Contradiction Handling',
    'Synthesis Generation',
    'Alignment Monitor',
  ];

  const [expandedSections, setExpandedSections] = React.useState<Record<string, boolean>>({
    overview: true,
    modules: false,
    memory: false,
  });

  const toggleSection = (section: string) => {
    setExpandedSections(prev => ({
      ...prev,
      [section]: !prev[section],
    }));
  };

  return (
    <aside className={`${isExpanded ? 'w-56' : 'w-20'} bg-white border-r border-neutral-200 transition-all duration-300 flex flex-col h-screen`}>
      {/* Header */}
      <div className="p-4 border-b border-neutral-200 flex items-center justify-between">
        {isExpanded && (
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 bg-primary-500 rounded-lg flex items-center justify-center">
              <span className="text-white font-bold text-sm">LH</span>
            </div>
            <span className="font-bold text-neutral-900">LHAS</span>
          </div>
        )}
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="p-1 hover:bg-neutral-100 rounded"
        >
          <Menu size={18} className="text-neutral-600" />
        </button>
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-4 px-2 space-y-1">
        {navigationItems.map(item => {
          const IconComponent = item.icon;
          return (
            <button
              key={item.id}
              onClick={() => onNavigate?.(item.id)}
              className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg transition-colors ${
                activeItem === item.id
                  ? 'bg-primary-50 text-primary-600'
                  : 'text-neutral-600 hover:bg-neutral-50'
              }`}
              title={!isExpanded ? item.label : undefined}
            >
              <IconComponent size={20} />
              {isExpanded && <span className="text-sm font-medium">{item.label}</span>}
            </button>
          );
        })}
      </nav>

      {/* Sections */}
      {isExpanded && (
        <div className="px-3 py-4 border-t border-neutral-200 space-y-3 flex-1 overflow-y-auto">
          {/* Overview */}
          <div>
            <button
              onClick={() => toggleSection('overview')}
              className="w-full flex items-center justify-between text-xs font-semibold text-neutral-600 uppercase tracking-wide px-2 py-1"
            >
              Overview
              <ChevronDown size={14} className={`transition-transform ${expandedSections.overview ? 'rotate-180' : ''}`} />
            </button>
            {expandedSections.overview && (
              <div className="mt-2 space-y-1 ml-2">
                <a href="#" className="block text-xs text-neutral-600 hover:text-primary-600 py-1">
                  Active Missions
                </a>
                <a href="#" className="block text-xs text-neutral-600 hover:text-primary-600 py-1">
                  All Missions
                </a>
              </div>
            )}
          </div>

          {/* Modules */}
          <div>
            <button
              onClick={() => toggleSection('modules')}
              className="w-full flex items-center justify-between text-xs font-semibold text-neutral-600 uppercase tracking-wide px-2 py-1"
            >
              Modules
              <ChevronDown size={14} className={`transition-transform ${expandedSections.modules ? 'rotate-180' : ''}`} />
            </button>
            {expandedSections.modules && (
              <div className="mt-2 space-y-1 ml-2">
                {modules.map(module => (
                  <a key={module} href="#" className="block text-xs text-neutral-600 hover:text-primary-600 py-1 truncate">
                    {module}
                  </a>
                ))}
              </div>
            )}
          </div>

          {/* Memory */}
          <div>
            <button
              onClick={() => toggleSection('memory')}
              className="w-full flex items-center justify-between text-xs font-semibold text-neutral-600 uppercase tracking-wide px-2 py-1"
            >
              Memory
              <ChevronDown size={14} className={`transition-transform ${expandedSections.memory ? 'rotate-180' : ''}`} />
            </button>
            {expandedSections.memory && (
              <div className="mt-2 space-y-1 ml-2">
                <a href="#" className="block text-xs text-neutral-600 hover:text-primary-600 py-1">
                  Claims Browser
                </a>
                <a href="#" className="block text-xs text-neutral-600 hover:text-primary-600 py-1">
                  Contradiction Log
                </a>
                <a href="#" className="block text-xs text-neutral-600 hover:text-primary-600 py-1">
                  Synthesis History
                </a>
              </div>
            )}
          </div>
        </div>
      )}

      {/* User Footer */}
      {isExpanded && (
        <div className="px-3 py-3 border-t border-neutral-200 flex items-center gap-2">
          <div className="w-8 h-8 bg-secondary-500 rounded-full"></div>
          <div className="flex-1 min-w-0">
            <p className="text-xs font-medium text-neutral-900 truncate">Research Ops</p>
            <p className="text-xs text-neutral-500 truncate">v1.0 alpha</p>
          </div>
        </div>
      )}
    </aside>
  );
};
