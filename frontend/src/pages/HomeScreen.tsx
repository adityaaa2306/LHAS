import React from 'react';
import {
  Sidebar,
  TopBar,
  AlertBanner,
  MissionCard,
  RightPanel,
  Filters,
  EmptyState,
  StatsRow,
  MissionModal,
} from '@/components';
import type {
  AlertBannerItem,
  StatsTile,
  FilterState,
  MissionFormData,
} from '@/components';
import type {
  Mission,
  Alert,
} from '@/types';
import { apiClient } from '@/services/api';
import { AlertCircle, Loader } from 'lucide-react';

export const HomeScreen: React.FC = () => {
  const [selectedMissionId, setSelectedMissionId] = React.useState<string | null>(null);
  const [filters, setFilters] = React.useState<FilterState>({
    sortBy: 'last-run',
    status: [],
    health: [],
    intentType: [],
    hasAlerts: false,
    viewMode: 'grid',
  });
  const [searchQuery, setSearchQuery] = React.useState('');
  const [showAlertBanner, setShowAlertBanner] = React.useState(true);
  const [showMissionModal, setShowMissionModal] = React.useState(false);

  // Data fetching states
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [missions, setMissions] = React.useState<Mission[]>([]);
  const [alerts, setAlerts] = React.useState<Alert[]>([]);
  const [stats, setStats] = React.useState({
    total_missions: 0,
    active_missions: 0,
    missions_needing_attention: 0,
    total_alerts: 0,
  });

  const selectedMission = missions.find(m => m.id === selectedMissionId) || null;

  // Fetch dashboard data
  const fetchDashboardData = React.useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      const data = await apiClient.getDashboardOverview();

      // Transform API data to frontend format
      const transformedMissions: Mission[] = data.missions.map((m: any) => ({
        id: m.id,
        name: m.name,
        normalized_query: m.query,
        intent_type: m.intent_type as any,
        health: m.health as any,
        status: m.status as any,
        session_count: m.sessions,
        total_papers: m.papers,
        total_claims: m.claims,
        confidence_score: m.confidence,
        confidence_from_module1: undefined,
        active_alerts: m.active_alerts,
        last_run: m.last_run ? new Date(m.last_run) : undefined,
        created_at: new Date(m.created_at),
        updated_at: new Date(m.updated_at),
        key_concepts: [],
        confidence_velocity: [m.confidence], // Single value since not provided by API
      }));

      // Transform alert data
      const transformedAlerts: Alert[] = data.alerts.map((a: any) => ({
        id: a.id,
        mission_id: a.mission_id,
        alert_type: a.alert_type as any,
        severity: a.severity as any,
        cycle_number: a.cycle_number,
        lifecycle_status: a.lifecycle_status as any,
        created_at: new Date(a.created_at),
      }));

      setMissions(transformedMissions);
      setAlerts(transformedAlerts);
      setStats(data.stats);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load dashboard');
      console.error('Dashboard fetch error:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  // Load data on mount
  React.useEffect(() => {
    fetchDashboardData();
    // Optionally refresh every 30 seconds
    const interval = setInterval(fetchDashboardData, 30000);
    return () => clearInterval(interval);
  }, [fetchDashboardData]);

  const handleMissionDeleted = React.useCallback((deletedMissionId: string) => {
    // Remove deleted mission from local state
    setMissions(prev => prev.filter(m => m.id !== deletedMissionId));
    
    // Clear selection if deleted mission was selected
    if (selectedMissionId === deletedMissionId) {
      setSelectedMissionId(null);
    }
    
    // Refresh dashboard stats
    fetchDashboardData();
  }, [selectedMissionId, fetchDashboardData]);

  // Filter and sort missions
  const filteredMissions = React.useMemo(() => {
    let result = missions;

    // Search filter
    if (searchQuery) {
      result = result.filter(
        m =>
          m.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
          m.normalized_query.toLowerCase().includes(searchQuery.toLowerCase())
      );
    }

    // Status filter
    if (filters.status.length > 0) {
      result = result.filter(m => filters.status.includes(m.status));
    }

    // Health filter
    if (filters.health.length > 0) {
      result = result.filter(m => filters.health.includes(m.health));
    }

    // Intent filter
    if (filters.intentType.length > 0) {
      result = result.filter(m => filters.intentType.includes(m.intent_type));
    }

    // Has alerts filter
    if (filters.hasAlerts) {
      result = result.filter(m => m.active_alerts > 0);
    }

    // Sort
    result.sort((a, b) => {
      switch (filters.sortBy) {
        case 'health':
          const healthOrder = { CRITICAL: 0, DEGRADED: 1, WATCH: 2, HEALTHY: 3 };
          return healthOrder[a.health] - healthOrder[b.health];
        case 'confidence':
          return b.confidence_score - a.confidence_score;
        case 'sessions':
          return b.session_count - a.session_count;
        case 'created':
          return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
        case 'last-run':
        default:
          return (new Date(b.last_run || 0).getTime() - new Date(a.last_run || 0).getTime());
      }
    });

    return result;
  }, [filters, searchQuery, missions]);

  // Build stats tiles
  const statsTiles: StatsTile[] = [
    {
      label: 'Total Missions',
      value: stats.total_missions,
      color: 'primary',
    },
    {
      label: 'Active Right Now',
      value: stats.active_missions,
      color: 'secondary',
    },
    {
      label: 'Missions Needing Attention',
      value: stats.missions_needing_attention,
      color: 'accent',
    },
    {
      label: 'Total Active Alerts',
      value: stats.total_alerts,
      color: 'alert',
    },
  ];

  // Get critical alerts for banner
  const criticalAlerts: AlertBannerItem[] = [];
  const degradedMissions = missions.filter(m => m.health === 'DEGRADED' || m.health === 'CRITICAL');
  degradedMissions.forEach(mission => {
    const missionAlerts = alerts.filter(a => a.mission_id === mission.id && a.lifecycle_status === 'active');
    missionAlerts.forEach(alert => {
      criticalAlerts.push({
        mission_name: mission.name,
        alert_type: alert.alert_type,
        mission_id: mission.id,
      });
    });
  });

  // Handle mission creation
  const handleCreateMission = async (formData: MissionFormData) => {
    try {
      await apiClient.createMission({
        name: formData.name,
        query: formData.query,
        intent_type: formData.intent_type,
        pico_population: formData.pico_population,
        pico_intervention: formData.pico_intervention,
        pico_comparator: formData.pico_comparator,
        pico_outcome: formData.pico_outcome,
        key_concepts: formData.key_concepts,
      });

      // Refresh dashboard data
      await fetchDashboardData();
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to create mission';
      throw new Error(message);
    }
  };

  return (
    <div className="flex bg-white h-screen overflow-hidden">
      {/* Sidebar */}
      <Sidebar activeItem="missions" />

      {/* Main content */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Top Bar */}
        <TopBar
          onNewMission={() => setShowMissionModal(true)}
          onSearchChange={setSearchQuery}
        />

        {/* Error Banner */}
        {error && (
          <div className="bg-red-50 border-b border-red-200 px-6 py-4 flex items-center gap-3">
            <AlertCircle size={20} className="text-red-600 flex-shrink-0" />
            <div className="flex-1">
              <p className="text-sm font-medium text-red-900">{error}</p>
            </div>
            <button
              onClick={() => {
                setError(null);
                fetchDashboardData();
              }}
              className="text-sm font-medium text-red-700 hover:text-red-900"
            >
              Retry
            </button>
          </div>
        )}

        {/* Alert Banner */}
        {showAlertBanner && criticalAlerts.length > 0 && (
          <AlertBanner
            alerts={criticalAlerts}
            onDismiss={() => setShowAlertBanner(false)}
            onNavigate={(missionId) => setSelectedMissionId(missionId)}
          />
        )}

        {/* Loading state */}
        {loading ? (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center">
              <Loader size={48} className="animate-spin text-primary-500 mx-auto mb-4" />
              <p className="text-neutral-600">Loading dashboard...</p>
            </div>
          </div>
        ) : (
          <>
            {/* Stats Row */}
            <StatsRow stats={statsTiles} />

            {/* Main content area */}
            <div className="flex-1 overflow-hidden flex">
              <div className="flex-1 flex flex-col overflow-auto">
                {/* Filters */}
                {missions.length > 0 && <Filters filters={filters} onFilterChange={setFilters} />}

                {/* Missions grid/table or empty state */}
                {missions.length === 0 ? (
                  <EmptyState onNewMission={() => setShowMissionModal(true)} />
                ) : filteredMissions.length === 0 ? (
                  <div className="flex-1 flex items-center justify-center">
                    <div className="text-center">
                      <p className="text-neutral-600 mb-4">No missions match your filters</p>
                      <button
                        onClick={() => {
                          setFilters({
                            sortBy: 'last-run',
                            status: [],
                            health: [],
                            intentType: [],
                            hasAlerts: false,
                            viewMode: 'grid',
                          });
                          setSearchQuery('');
                        }}
                        className="text-primary-600 hover:text-primary-700 font-medium"
                      >
                        Clear filters
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="px-6 py-4 flex-1 overflow-auto">
                    {filters.viewMode === 'grid' ? (
                      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                        {filteredMissions.map(mission => (
                          <MissionCard
                            key={mission.id}
                            mission={mission}
                            onClick={() => setSelectedMissionId(mission.id)}
                            onDeleted={handleMissionDeleted}
                          />
                        ))}
                      </div>
                    ) : (
                      /* Table view */
                      <div className="bg-white border border-neutral-200 rounded-lg overflow-hidden">
                        <table className="w-full text-sm">
                          <thead className="bg-neutral-50 border-b border-neutral-200">
                            <tr>
                              <th className="px-6 py-3 text-left font-semibold text-neutral-900">Mission Name</th>
                              <th className="px-6 py-3 text-left font-semibold text-neutral-900">Query</th>
                              <th className="px-6 py-3 text-left font-semibold text-neutral-900">Status</th>
                              <th className="px-6 py-3 text-left font-semibold text-neutral-900">Health</th>
                              <th className="px-6 py-3 text-left font-semibold text-neutral-900">Confidence</th>
                              <th className="px-6 py-3 text-left font-semibold text-neutral-900">Sessions</th>
                            </tr>
                          </thead>
                          <tbody>
                            {filteredMissions.map(mission => (
                              <tr
                                key={mission.id}
                                onClick={() => setSelectedMissionId(mission.id)}
                                className="border-b border-neutral-200 hover:bg-neutral-50 cursor-pointer transition-colors"
                              >
                                <td className="px-6 py-4 font-medium text-neutral-900">{mission.name}</td>
                                <td className="px-6 py-4 text-neutral-600 truncate max-w-xs">{mission.normalized_query}</td>
                                <td className="px-6 py-4">
                                  <span className="px-2 py-1 bg-blue-100 text-blue-700 rounded text-xs font-medium">
                                    {mission.status}
                                  </span>
                                </td>
                                <td className="px-6 py-4">
                                  <span
                                    className={`px-2 py-1 rounded text-xs font-medium ${
                                      mission.health === 'HEALTHY'
                                        ? 'bg-green-100 text-green-700'
                                        : mission.health === 'WATCH'
                                        ? 'bg-amber-100 text-amber-700'
                                        : mission.health === 'DEGRADED'
                                        ? 'bg-red-100 text-red-700'
                                        : 'bg-red-900 text-red-50'
                                    }`}
                                  >
                                    {mission.health}
                                  </span>
                                </td>
                                <td className="px-6 py-4 font-semibold">{Math.round(mission.confidence_score)}%</td>
                                <td className="px-6 py-4 text-neutral-600">{mission.session_count}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          </>
        )}
      </div>

      {/* Right Panel - Only show sessions/alerts if we have them in future API calls */}
      <RightPanel
        mission={selectedMission}
        sessions={[]}
        alerts={alerts.filter(a => a.mission_id === selectedMissionId)}
        isOpen={!!selectedMissionId}
        onClose={() => setSelectedMissionId(null)}
      />

      {/* Mission Creation Modal */}
      <MissionModal
        isOpen={showMissionModal}
        onClose={() => setShowMissionModal(false)}
        onSubmit={handleCreateMission}
      />
    </div>
  );
};
