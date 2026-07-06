export type IngestionStatusValue = 'idle' | 'pending' | 'processing' | 'completed' | 'failed';

export type StageStatus = 'completed' | 'running' | 'waiting' | 'failed';

export interface IngestionStage {
  id: string;
  label: string;
  progress_min: number;
  progress_max: number;
  status: StageStatus;
}

export interface IngestionActivity {
  timestamp: string;
  message: string;
  level: 'info' | 'warning' | 'error';
}

export interface BackgroundTaskStatus {
  status: 'waiting' | 'running' | 'completed' | 'failed';
  progress: number;
  detail: string | null;
}

export interface FinalizedPaper {
  id: string;
  title: string;
  source: string;
  score: number;
  timestamp: string;
}

export interface RetrievalEntity {
  name: string;
  entity_type: string;
  canonical_names?: string[];
  synonyms?: string[];
  drug_class?: string;
  mesh_terms?: string[];
}

export interface RetrievalPlanInner {
  entities: RetrievalEntity[];
  intent?: {
    domain?: string;
    primary_question?: string;
    research_goals?: string[];
    coverage_dimensions?: string[];
    study_types_wanted?: string[];
    is_medical?: boolean;
  };
  searches?: Array<{
    source: string;
    query: string;
    strategy: string;
    rationale?: string;
  }>;
  complexity?: string;
  planner_notes?: string;
  total_planned_searches?: number;
}

export interface RetrievalPlanStats {
  plan?: RetrievalPlanInner;
  executions?: Array<{
    source: string;
    query: string;
    strategy: string;
    papers_found: number;
    error?: string;
  }>;
  rejected_papers?: Array<{ paper_id: string; title: string; reason: string }>;
  rejected_count?: number;
  coverage?: {
    dimensions_covered?: Record<string, number>;
    dimensions_missing?: string[];
    coverage_score?: number;
    gap_fill_searches?: number;
  };
  confidence_score?: number;
  total_candidates?: number;
  after_dedup?: number;
  after_qc?: number;
  source_counts?: Record<string, number>;
  queries_executed?: number;
}

export interface IngestionStats {
  candidates_retrieved: number;
  after_dedup: number;
  after_prefilter: number;
  selected: number;
  stored: number;
  source_counts: Record<string, number>;
  finalized_papers: FinalizedPaper[];
  retrieval_plan?: RetrievalPlanStats | null;
}

export interface IngestionStatusResponse {
  mission_id: string;
  status: IngestionStatusValue;
  progress: number;
  error: string | null;
  current_stage: string;
  stage_detail: string | null;
  stages: IngestionStage[];
  activities: IngestionActivity[];
  background_tasks: Record<string, BackgroundTaskStatus>;
  stats: IngestionStats;
  started_at: string | null;
  completed_at: string | null;
  _timing_ms?: number;
  _source?: 'cache' | 'db';
}
