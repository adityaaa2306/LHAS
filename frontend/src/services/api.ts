/**
 * API Service for LHAS Frontend
 * Handles all backend communication
 */

import type { MemoryGraphResponse, MonitoringOverview, MonitoringSnapshotView, MonitoringAlertRecordView, SynthesisVersion } from '@/types';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

interface DashboardOverview {
  stats: {
    total_missions: number;
    active_missions: number;
    missions_needing_attention: number;
    total_alerts: number;
  };
  alerts: Alert[];
  missions: Mission[];
}

interface Mission {
  id: string;
  name: string;
  query: string;
  intent_type: string;
  status: string;
  health: string;
  last_run: string | null;
  papers: number;
  claims: number;
  confidence: number;
  sessions: number;
  active_alerts: number;
  created_at: string;
  updated_at: string;
}

interface Alert {
  id: string;
  mission_id: string;
  mission_name: string;
  alert_type: string;
  severity: string;
  cycle_number: number;
  lifecycle_status: string;
  message: string | null;
  created_at: string;
}

interface MissionDetail extends Mission {
  pico: {
    population: string;
    intervention: string;
    comparator: string;
    outcome: string;
  } | null;
  decision: string;
  key_concepts: string[];
  ambiguity_flags: string[];
  confidence_initial: number | null;
}

class APIClient {
  private baseUrl: string;
  private requestTimeout: number = 60000; // 60 seconds timeout for long operations

  constructor(baseUrl: string = API_BASE_URL) {
    this.baseUrl = baseUrl;
  }

  /**
   * Core fetch method with timeout support
   * @param endpoint API endpoint
   * @param options Fetch options
   * @param timeout Request timeout in milliseconds (default 15s)
   */
  async request<T>(endpoint: string, options?: RequestInit, timeout: number = this.requestTimeout): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeout);

    try {
      const response = await fetch(url, {
        headers: {
          'Content-Type': 'application/json',
          ...options?.headers,
        },
        ...options,
        signal: controller.signal,
      });

      if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
        throw new Error(error.detail || `HTTP ${response.status}`);
      }

      return await response.json();
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') {
        const timeoutError = new Error(`Request timeout after ${timeout}ms: ${endpoint}`);
        console.error(`API Timeout [${endpoint}]:`, timeoutError);
        throw timeoutError;
      }
      console.error(`API Error [${endpoint}]:`, error);
      throw error;
    } finally {
      clearTimeout(timeoutId);
    }
  }

  // Dashboard endpoints
  async getDashboardOverview(): Promise<DashboardOverview> {
    return this.request<DashboardOverview>('/api/dashboard/overview');
  }

  async getMissionDetail(missionId: string): Promise<MissionDetail> {
    return this.request<MissionDetail>(`/api/dashboard/missions/${missionId}`);
  }

  async getMissionAlerts(missionId: string): Promise<{ mission_id: string; alerts: Alert[] }> {
    return this.request<{ mission_id: string; alerts: Alert[] }>(`/api/dashboard/missions/${missionId}/alerts`);
  }

  async getMissionPapers(missionId: string): Promise<{ mission_id: string; papers: any[]; count: number }> {
    return this.request<{ mission_id: string; papers: any[]; count: number }>(`/api/dashboard/missions/${missionId}/papers`);
  }

  async getMissionSynthesis(missionId: string): Promise<{ mission_id: string; synthesis: SynthesisVersion | null; message?: string }> {
    return this.request<{ mission_id: string; synthesis: SynthesisVersion | null; message?: string }>(`/api/synthesis/missions/${missionId}/latest`);
  }

  async getSynthesisHistory(missionId: string, limit: number = 10): Promise<{ mission_id: string; history: SynthesisVersion[]; count: number }> {
    return this.request<{ mission_id: string; history: SynthesisVersion[]; count: number }>(`/api/synthesis/missions/${missionId}/history?limit=${limit}`);
  }

  async generateSynthesis(
    missionId: string,
    triggerType: string = 'operator_request',
  ): Promise<{ mission_id: string; synthesis: SynthesisVersion }> {
    return this.request<{ mission_id: string; synthesis: SynthesisVersion }>(
      `/api/synthesis/missions/${missionId}/generate`,
      {
        method: 'POST',
        body: JSON.stringify({ trigger_type: triggerType }),
      },
    );
  }

  async getMissionClaims(missionId: string, claimType?: string): Promise<{ mission_id: string; claims: any[]; count: number; filter: string }> {
    const url = claimType ? `/api/dashboard/missions/${missionId}/claims?claim_type=${claimType}` : `/api/dashboard/missions/${missionId}/claims`;
    return this.request<{ mission_id: string; claims: any[]; count: number; filter: string }>(url);
  }

  async getMissionReasoning(missionId: string): Promise<{ mission_id: string; reasoning_steps: any[]; count: number }> {
    return this.request<{ mission_id: string; reasoning_steps: any[]; count: number }>(`/api/dashboard/missions/${missionId}/reasoning`);
  }

  async getMissionTimeline(missionId: string): Promise<{ mission_id: string; timeline: any[]; count: number }> {
    return this.request<{ mission_id: string; timeline: any[]; count: number }>(`/api/dashboard/missions/${missionId}/timeline`);
  }

  async getHealth(): Promise<{ status: string; version: string }> {
    return this.request<{ status: string; version: string }>('/health');
  }

  async createMission(payload: {
    name: string;
    query: string;
    intent_type: string;
    pico_population?: string;
    pico_intervention?: string;
    pico_comparator?: string;
    pico_outcome?: string;
    key_concepts?: string[];
  }): Promise<Mission> {
    return this.request<Mission>('/api/dashboard/missions', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  async triggerIngestion(missionId: string): Promise<{ status: string; mission_id?: string; message?: string; ingestion_id?: string }> {
    // Short timeout — endpoint now returns immediately (background job pattern)
    return this.request<{ status: string; mission_id?: string; message?: string; ingestion_id?: string }>(
      `/api/papers/ingest?mission_id=${missionId}`,
      { method: 'POST', body: JSON.stringify({}) },
      10000, // 10s is more than enough for a fire-and-forget endpoint
    );
  }

  async getIngestionStatus(missionId: string): Promise<{
    mission_id: string;
    status: 'idle' | 'pending' | 'processing' | 'completed' | 'failed';
    progress: number;
    error: string | null;
    started_at: string | null;
    completed_at: string | null;
  }> {
    return this.request(`/api/papers/ingest/status/${missionId}`, undefined, 10000);
  }

  // Graph endpoints
  async getMissionGraphStats(missionId: string): Promise<any> {
    return this.request<any>(`/api/papers/mission/${missionId}/graph-stats`);
  }

  async comparePapers(paperAId: string, paperBId: string): Promise<any> {
    return this.request<any>(`/api/papers/compare?paper_a_id=${paperAId}&paper_b_id=${paperBId}`);
  }

  // Claims and Evidence Clusters endpoints
  async getClaimsClusters(missionId: string): Promise<any> {
    return this.request<any>(`/api/claims/mission/${missionId}/clusters`);
  }

  async getClaims(
    missionId: string,
    options?: {
      skip?: number;
      limit?: number;
      claim_type?: string;
      direction?: string;
      min_confidence?: number;
      max_confidence?: number;
      validation_status?: string;
    }
  ): Promise<any> {
    const params = new URLSearchParams();
    if (options?.skip !== undefined) params.append('skip', options.skip.toString());
    if (options?.limit !== undefined) params.append('limit', options.limit.toString());
    if (options?.claim_type) params.append('claim_type', options.claim_type);
    if (options?.direction) params.append('direction', options.direction);
    if (options?.min_confidence !== undefined) params.append('min_confidence', options.min_confidence.toString());
    if (options?.max_confidence !== undefined) params.append('max_confidence', options.max_confidence.toString());
    if (options?.validation_status) params.append('validation_status', options.validation_status);

    const queryString = params.toString();
    const endpoint = `/api/claims/mission/${missionId}${queryString ? `?${queryString}` : ''}`;
    return this.request<any>(endpoint);
  }

  async getClaimsStats(missionId: string): Promise<any> {
    return this.request<any>(`/api/claims/mission/${missionId}/stats`);
  }

  async getMemoryOverview(missionId: string): Promise<any> {
    return this.request<any>(`/api/memory/missions/${missionId}/overview`);
  }

  async getMemorySnapshots(missionId: string): Promise<{ mission_id: string; snapshots: any[]; count: number }> {
    return this.request<{ mission_id: string; snapshots: any[]; count: number }>(`/api/memory/missions/${missionId}/snapshots`);
  }

  async getMemoryDrift(missionId: string): Promise<{ mission_id: string; drift: any[]; count: number }> {
    return this.request<{ mission_id: string; drift: any[]; count: number }>(`/api/memory/missions/${missionId}/drift`);
  }

  async getMemoryProvenance(
    missionId: string,
    options?: { claim_id?: string; paper_id?: string; limit?: number }
  ): Promise<{ mission_id: string; events: any[]; count: number }> {
    const params = new URLSearchParams();
    if (options?.claim_id) params.append('claim_id', options.claim_id);
    if (options?.paper_id) params.append('paper_id', options.paper_id);
    if (options?.limit !== undefined) params.append('limit', options.limit.toString());
    const queryString = params.toString();
    return this.request<{ mission_id: string; events: any[]; count: number }>(
      `/api/memory/missions/${missionId}/provenance${queryString ? `?${queryString}` : ''}`
    );
  }

  async getMemoryContradictions(missionId: string): Promise<{ mission_id: string; contradictions: any[]; count: number }> {
    return this.request<{ mission_id: string; contradictions: any[]; count: number }>(`/api/memory/missions/${missionId}/contradictions`);
  }

  async getMemoryGraph(
    missionId: string,
    options?: { max_nodes?: number; max_edges?: number },
  ): Promise<MemoryGraphResponse> {
    const params = new URLSearchParams();
    if (options?.max_nodes !== undefined) params.append('max_nodes', options.max_nodes.toString());
    if (options?.max_edges !== undefined) params.append('max_edges', options.max_edges.toString());
    const queryString = params.toString();
    return this.request<MemoryGraphResponse>(`/api/memory/missions/${missionId}/graph${queryString ? `?${queryString}` : ''}`);
  }

  async getContradictionOverview(missionId: string): Promise<any> {
    return this.request<any>(`/api/contradictions/missions/${missionId}/overview`);
  }

  async getConfirmedContradictions(missionId: string): Promise<{ mission_id: string; contradictions: any[]; count: number }> {
    return this.request<{ mission_id: string; contradictions: any[]; count: number }>(`/api/contradictions/missions/${missionId}/confirmed`);
  }

  async getResolvedContradictions(missionId: string): Promise<{ mission_id: string; resolved_pairs: any[]; count: number }> {
    return this.request<{ mission_id: string; resolved_pairs: any[]; count: number }>(`/api/contradictions/missions/${missionId}/resolved`);
  }

  async getAmbiguousContradictions(missionId: string): Promise<{ mission_id: string; ambiguous_pairs: any[]; count: number }> {
    return this.request<{ mission_id: string; ambiguous_pairs: any[]; count: number }>(`/api/contradictions/missions/${missionId}/ambiguous`);
  }

  async runContradictionCycle(missionId: string, evaluateAll: boolean = false): Promise<any> {
    return this.request<any>(`/api/contradictions/missions/${missionId}/run-cycle?evaluate_all=${evaluateAll ? 'true' : 'false'}`, { method: 'POST' });
  }

  async getClaimMemoryDetail(claimId: string): Promise<any> {
    return this.request<any>(`/api/memory/claims/${claimId}`);
  }

  async getMonitoringOverview(missionId: string): Promise<MonitoringOverview> {
    return this.request<MonitoringOverview>(`/api/monitoring/missions/${missionId}/overview`);
  }

  async getMonitoringSnapshots(
    missionId: string,
    limit: number = 20,
  ): Promise<{ mission_id: string; snapshots: MonitoringSnapshotView[]; count: number }> {
    return this.request<{ mission_id: string; snapshots: MonitoringSnapshotView[]; count: number }>(
      `/api/monitoring/missions/${missionId}/snapshots?limit=${limit}`,
    );
  }

  async getMonitoringAlerts(
    missionId: string,
    status: 'active' | 'history' | 'all' = 'active',
    limit: number = 100,
  ): Promise<{ mission_id: string; alerts: MonitoringAlertRecordView[]; count: number; status: string }> {
    return this.request<{ mission_id: string; alerts: MonitoringAlertRecordView[]; count: number; status: string }>(
      `/api/monitoring/missions/${missionId}/alerts?status=${status}&limit=${limit}`,
    );
  }

  async runMonitoringCycle(missionId: string): Promise<any> {
    return this.request<any>(`/api/monitoring/missions/${missionId}/run-cycle`, { method: 'POST' });
  }
}

// Export singleton instance
export const apiClient = new APIClient();

// Export types
export type { DashboardOverview, Mission, Alert, MissionDetail };
