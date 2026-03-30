/**
 * API Service for LHAS Frontend
 * Handles all backend communication
 */

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

  async getMissionSynthesis(missionId: string): Promise<{ mission_id: string; synthesis: any; message?: string }> {
    return this.request<{ mission_id: string; synthesis: any; message?: string }>(`/api/dashboard/missions/${missionId}/synthesis`);
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
}

// Export singleton instance
export const apiClient = new APIClient();

// Export types
export type { DashboardOverview, Mission, Alert, MissionDetail };
