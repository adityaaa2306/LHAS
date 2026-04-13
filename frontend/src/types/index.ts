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
  severity?: 'LOW' | 'MEDIUM' | 'HIGH';
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

// ==================== MEMORY SYSTEM ====================

export interface MissionSnapshot {
  id: string;
  mission_id: string;
  cycle_number: number;
  timestamp: string | null;
  papers_ingested_count: number;
  claims_extracted_count: number;
  active_contradictions_count: number;
  current_belief_statement: string | null;
  current_confidence_score: number;
  dominant_evidence_direction: 'positive' | 'negative' | 'null' | 'mixed';
  synthesis_version_id: string | null;
}

export interface DriftMetric {
  id: string;
  mission_id: string;
  cycle_number: number;
  timestamp: string | null;
  confidence_delta: number;
  direction_stability: boolean;
  contradiction_rate: number;
}

export interface MemoryProvenanceEvent {
  id: string;
  event_type: string;
  claim_id: string | null;
  paper_id: string | null;
  mission_id: string;
  timestamp: string | null;
  actor: string;
  previous_value: any;
  new_value: any;
}

export interface MemoryContradiction {
  id: string;
  graph_edge_id?: string | null;
  claim_a_id: string;
  claim_b_id: string;
  edge_type: 'CONTRADICTS';
  severity?: 'LOW' | 'MEDIUM' | 'HIGH';
  edge_weight: number;
  study_design_delta: number;
  confidence_product: number;
  recency_weight: number;
  resolution_status: string;
  justification: string | null;
  created_at: string | null;
  intervention_canonical?: string | null;
  outcome_canonical?: string | null;
  population_overlap?: 'identical' | 'partial' | 'different';
  direction_a?: string | null;
  direction_b?: string | null;
  claim_a_statement?: string | null;
  claim_b_statement?: string | null;
  claim_a_paper_title?: string | null;
  claim_b_paper_title?: string | null;
}

export interface MemoryOverview {
  mission_id: string;
  latest_snapshot: MissionSnapshot | null;
  latest_drift: DriftMetric | null;
  belief_state?: {
    current_confidence_score: number | null;
    dominant_evidence_direction: string | null;
    current_revision_type: string | null;
    last_revised_at: string | null;
    drift_trend: string | null;
    operator_action_required: boolean;
    latest_revision_id: string | null;
    latest_revision_type: string | null;
    active_escalation_id: string | null;
    active_escalation_status: string | null;
  } | null;
  graph: {
    node_count: number;
    edge_count: number;
    contradictions: number;
  };
  audit: {
    provenance_events: number;
    checkpoints: number;
  };
}

export interface MemoryGraphNode {
  id: string;
  label: string;
  statement: string;
  intervention_canonical: string;
  outcome_canonical: string;
  direction: 'positive' | 'negative' | 'null' | 'unclear';
  claim_type: string;
  composite_confidence: number;
  study_design_score: number;
  publication_year: number | null;
  paper_title?: string | null;
  edge_count: number;
  contradiction_count: number;
  topic_key: string;
}

export interface MemoryGraphEdge {
  id: string;
  source: string;
  target: string;
  edge_type: 'SUPPORTS' | 'CONTRADICTS' | 'REPLICATES' | 'REFINES' | 'IS_SUBGROUP_OF' | string;
  edge_weight: number;
  study_design_delta: number;
  confidence_product: number;
  recency_weight: number;
  resolution_status: string;
  justification?: string | null;
}

export interface MemoryGraphResponse {
  mission_id: string;
  nodes: MemoryGraphNode[];
  edges: MemoryGraphEdge[];
  stats: {
    total_nodes: number;
    visible_nodes: number;
    total_edges: number;
    visible_edges: number;
    edge_type_breakdown: Record<string, number>;
  };
}

export interface ClaimMemoryDetail {
  claim_id: string;
  statement: string;
  mission_id: string;
  paper_id: string;
  versions: Array<{
    id: string;
    version_number: number;
    changed_field: string;
    old_value: any;
    new_value: any;
    changed_at: string | null;
    changed_by_module: string;
  }>;
  provenance: MemoryProvenanceEvent[];
  graph_edges: Array<{
    id: string;
    edge_type: string;
    other_claim_id: string;
    edge_weight: number;
    study_design_delta: number;
    confidence_product: number;
    recency_weight: number;
    justification: string | null;
    resolution_status: string;
    created_at: string | null;
  }>;
}

// ==================== BELIEF REVISION ====================

export interface BeliefStateView {
  id: string;
  mission_id: string;
  current_belief_statement: string | null;
  current_confidence_score: number;
  dominant_evidence_direction: 'positive' | 'negative' | 'null' | 'mixed';
  current_revision_type: string | null;
  last_revised_at: string | null;
  last_cycle_number: number;
  operator_action_required: boolean;
  drift_trend: 'stabilizing' | 'drifting' | 'reversing';
  active_escalation_id: string | null;
}

export interface BeliefRevisionRecord {
  id: string;
  mission_id: string;
  cycle_number: number;
  timestamp: string | null;
  revision_type: string;
  previous_confidence: number;
  new_confidence: number;
  confidence_delta: number;
  previous_direction: string;
  new_direction: string;
  evidence_summary: any;
  decision_rationale: string | null;
  claims_considered: string[];
  claims_filtered: Array<{ claim_id: string; reason: string; cycle_number: number; intake_filtered: boolean }>;
  triggered_synthesis_regen: boolean;
  operator_action_required: boolean;
  applied_automatically: boolean;
  condition_fired: string | null;
}

export interface BeliefEscalation {
  id: string;
  mission_id: string;
  source_revision_id: string | null;
  originating_cycle_number: number;
  target_direction: string;
  evidence_summary: any;
  status: string;
  operator_approved: boolean;
  operator_notes: string | null;
  approved_at: string | null;
  expires_after_cycle: number | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface BeliefOverview {
  mission_id: string;
  state: BeliefStateView | null;
  latest_revision: BeliefRevisionRecord | null;
  active_escalation: BeliefEscalation | null;
  revision_count: number;
}

// ==================== CONTRADICTION HANDLING ====================

export interface ContradictionOverview {
  mission_id: string;
  confirmed_count: number;
  topic_count?: number;
  context_resolved_count: number;
  ambiguous_count: number;
  high_severity_count: number;
  asymmetry_threshold: number;
}

export interface ConfirmedContradiction {
  id: string;
  mission_id: string;
  timestamp: string | null;
  claim_a_id: string;
  claim_b_id: string;
  graph_edge_id: string | null;
  severity: 'LOW' | 'MEDIUM' | 'HIGH';
  direction_a: string;
  direction_b: string;
  intervention_canonical: string | null;
  outcome_canonical: string | null;
  topic_key?: string;
  quality_parity_delta: number;
  confidence_product: number;
  population_overlap: 'identical' | 'partial' | 'different';
  context_resolution_attempted: boolean;
  context_resolution_result: string;
  semantic_verification_result: string;
  llm_verification_call_id: string | null;
  resolution_status: string;
  resolution_timestamp: string | null;
  resolved_by: string | null;
  edge_weight: number | null;
  study_design_delta: number;
  recency_weight: number | null;
  justification: string | null;
}

export interface ContextResolvedPair {
  id: string;
  mission_id: string;
  timestamp: string | null;
  claim_a_id: string;
  claim_b_id: string;
  direction_a: string;
  direction_b: string;
  intervention_canonical: string | null;
  outcome_canonical: string | null;
  resolution_reason: string;
  stronger_claim_id: string | null;
  llm_call_id: string | null;
  notes: string | null;
}

export interface AmbiguousContradictionPair {
  id: string;
  mission_id: string;
  timestamp: string | null;
  claim_a_id: string;
  claim_b_id: string;
  direction_a: string;
  direction_b: string;
  intervention_canonical: string | null;
  outcome_canonical: string | null;
  ambiguity_reason: string;
  llm_verification_call_id: string | null;
  review_status: string;
}

// ==================== SYNTHESIS GENERATION ====================

export type SynthesisTriggerType =
  | 'new_paper'
  | 'contradiction'
  | 'belief_material_update'
  | 'belief_reversed'
  | 'operator_request'
  | 'scheduled'
  | 'legacy';

export type SynthesisConfidenceTier = 'STRONG' | 'MODERATE' | 'MIXED' | 'WEAK';
export type SynthesisChangeMagnitude = 'MAJOR' | 'MODERATE' | 'MINOR';

export interface SynthesisVersion {
  id: string;
  mission_id: string;
  version_number: number;
  created_at: string | null;
  trigger_type: SynthesisTriggerType | string | null;
  synthesis_text: string;
  confidence_tier: SynthesisConfidenceTier | string;
  confidence_score: number;
  dominant_direction: 'positive' | 'negative' | 'null' | 'mixed' | string | null;
  claim_ids_tier1: string[];
  claim_ids_tier2: string[];
  claim_ids_tier3: string[];
  contradictions_included: string[];
  change_magnitude: SynthesisChangeMagnitude | string | null;
  confidence_delta: number;
  direction_changed: boolean;
  prior_synthesis_id: string | null;
  validation_passed: boolean;
  word_count: number;
  llm_fallback: boolean;
  change_summary: {
    confidence_delta: number;
    direction_changed: boolean;
    new_contradictions_surfaced: number;
    contradictions_resolved: number;
  };
  summary_metrics: {
    tier1_count: number;
    tier2_count: number;
    tier3_count: number;
    high_contradictions: number;
    medium_contradictions: number;
    high_contradiction_pairs?: number;
    medium_contradiction_pairs?: number;
  };
}

// ==================== ALIGNMENT MONITOR ====================

export interface MonitoringAlertRecordView {
  id: string;
  mission_id: string;
  alert_type: string;
  severity: 'LOW' | 'MEDIUM' | 'HIGH' | string;
  lifecycle_status: 'firing' | 'active' | 'resolved' | 'expired' | string;
  first_cycle_number: number;
  last_cycle_number: number;
  message: string | null;
  metric_values: Record<string, any>;
  resolution_record: any;
  created_at: string | null;
  updated_at: string | null;
  resolved_at: string | null;
}

export interface MonitoringSnapshotView {
  id: string;
  mission_id: string;
  cycle_number: number;
  timestamp: string | null;
  confidence_velocity: number | null;
  evidence_justified_velocity: number | null;
  trajectory_divergence: number | null;
  semantic_drift_score: number | null;
  active_contradiction_count: number;
  contradiction_acknowledgment_rate: number | null;
  support_ratio: number | null;
  directional_retrieval_balance: number | null;
  mean_paper_age: number | null;
  recent_ingestion_rate: number | null;
  reversal_rate: number | null;
  no_update_rate: number | null;
  active_alerts: string[];
  alert_history: string[];
  overall_health: HealthStatus | string;
  metrics_payload: Record<string, any>;
}

export interface MonitoringOverview {
  mission_id: string;
  current_cycle: number;
  overall_health: HealthStatus | string;
  active_alert_count: number;
  active_alerts: MonitoringAlertRecordView[];
  recent_alert_history: MonitoringAlertRecordView[];
  metrics: Record<string, any>;
  latest_snapshot: MonitoringSnapshotView | null;
  benchmark?: {
    classification: 'ALIGNED' | 'DIVERGING' | 'MISALIGNED';
    benchmark_similarity: number;
    benchmark_source?: string | null;
    disagreements: Array<{ tag: string; description: string }>;
  } | null;
}
