// Mission types
export type HealthStatus = 'HEALTHY' | 'WATCH' | 'DEGRADED' | 'CRITICAL';
export type MissionStatus = 'active' | 'paused' | 'idle' | 'archived';
export type IntentType = 'Causal' | 'Comparative' | 'Exploratory' | 'Descriptive';
export type AlertType = 'OSCILLATION_DETECTED' | 'EVIDENCE_DROUGHT' | 'CONFIDENCE_COLLAPSE' | string;
export type AlertSeverity = 'critical' | 'degraded' | 'watch' | 'info';
export type ClaimDirection = 'positive' | 'negative' | 'null' | 'unclear';
export type EvidenceGapType = 'limited_evidence' | 'study_design_homogeneity' | 'population_coverage' | 'conflicting_evidence';
export type GapSeverity = 'high' | 'medium' | 'low';

export interface Mission {
  id: string;
  name: string;
  normalized_query: string;
  pico?: {
    population: string;
    intervention: string;
    comparator: string;
    outcome: string;
  };
  intent_type: IntentType;
  decision?: 'PROCEED' | 'PROCEED_WITH_CAUTION' | 'NEED_CLARIFICATION';
  key_concepts: string[];
  ambiguity_flags?: string[];
  health: HealthStatus;
  status: MissionStatus;
  session_count: number;
  total_papers: number;
  total_claims: number;
  confidence_score: number;
  confidence_from_module1?: number;
  active_alerts: number;
  last_run?: Date;
  created_at: Date;
  updated_at: Date;
  confidence_velocity: number[]; // 8-dot sparkline
}

export interface Session {
  id: string;
  mission_id: string;
  session_number: number;
  timestamp: Date;
  status: 'Completed' | 'Failed' | 'Running';
  papers_ingested: number;
  claims_extracted: number;
  health: HealthStatus;
}

export interface Alert {
  id: string;
  mission_id: string;
  alert_type: AlertType;
  severity: AlertSeverity;
  cycle_number: number;
  lifecycle_status: 'firing' | 'active' | 'resolved';
  created_at: Date;
  resolved_at?: Date;
  resolution_record?: string;
}

export interface ContradictionAlert {
  id: string;
  claim1: string;
  source1: string;
  claim2: string;
  source2: string;
  severity: AlertSeverity;
}

export interface SystemStats {
  total_missions: number;
  active_right_now: number;
  needing_attention: number;
  total_active_alerts: number;
}

// ==================== EVIDENCE CLUSTERS ====================

export interface ClusterKey {
  intervention_canonical: string;
  outcome_canonical: string;
}

export interface ClusterStatistics {
  supporting_count: number;
  contradicting_count: number;
  null_count: number;
  unclear_count: number;
  avg_confidence: number;
  min_confidence: number;
  max_confidence: number;
}

export interface EvidenceBar {
  supporting: number;
  contradicting: number;
  null: number;
}

export interface ContradictionPair {
  claim1_id: string;
  claim1_direction: string;
  claim1_paper: string;
  claim2_id: string;
  claim2_direction: string;
  claim2_paper: string;
}

export interface ContradictionSignal {
  has_conflict: boolean;
  severity: 'NONE' | 'LOW' | 'MEDIUM' | 'HIGH';
  pairs: ContradictionPair[];
}

export interface EvidenceGap {
  type: EvidenceGapType;
  description: string;
  severity: GapSeverity;
}

export interface ClaimSummary {
  id: string;
  statement: string;
  direction: ClaimDirection;
  confidence: number;
  paper_title: string;
  claim_type: string;
}

export interface EvidenceCluster {
  cluster_key: ClusterKey;
  claim_count: number;
  statistics: ClusterStatistics;
  evidence_bar: EvidenceBar;
  contradiction_signal: ContradictionSignal;
  best_evidence_type: string;
  evidence_gaps: EvidenceGap[];
  claims_summary: ClaimSummary[];
}

export interface ClusterResponse {
  clusters: EvidenceCluster[];
  total_clusters: number;
  total_claims_clustered: number;
  cluster_statistics: {
    total_supporting: number;
    total_contradicting: number;
    total_null: number;
    average_cluster_confidence: number;
  };
}
