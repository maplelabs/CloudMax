export interface Alert {
  id: string;
  name: string;
  severity: "P1" | "P2" | "P3" | "P4";
  alert_status: "firing" | "resolved" | "pending";
  description: string;
  started_at: string;
  last_updated_at: string;
  resolved_at?: string;
  labels: Record<string, string>;
  annotations: Record<string, string>;
  triage_status: "success" | "processing" | "pending" | "error" | "not-started" | "in-progress" | "failed" | "queued";
  evaluation_status: "success" | "processing" | "pending" | "error" | "not-started" | "in-progress" | "failed" | "queued";
  evaluation_score?: number;
  generator_url?: string;
  fingerprint: string;
  alert_source?: string;
  payload?:any
  
}

export interface AlertsResponse {
  alerts: Alert[];
  pagination: Pagination;
}

export interface Pagination {
  current_page: number;
  page_size: number;
  total_items: number;
}

export interface AlertsQueryParams {
  page?: number;
  page_size?: number;
  severity?: string | null;
  triage_status?: string | null;
  evaluation_status?: string | null;
  name_contains?: string | null;
  time_range?: string | null;
  start_time?: string | null;
  end_time?: string | null;
  evaluation_score_operator?: string | null;
  evaluation_score_value?: number | null;
  search?: string;
  semantic_search?: boolean;
}


export interface RootCauseAnalysis {
  id: string;
  alert_id: string;
  analysis: string;
  confidence_score: number;
  created_at: string;
  updated_at: string;
  content?: string;
}

export interface ScoreCriteria {
  title: string;
  score_percent: number;
  description:string;
}

export interface AlertEvaluation {
  average_score_percent: number;
  reason: string;
  score_criteria_cards: ScoreCriteria[];
  status?: string; // pending, queued, processing, success, error
}

export interface TriageMessage {
  timestamp: string;
  agent_name: string;
  content?: string;
  tool_name?: string;
  tool_args?: string;
  tool_response?: string;
  response_type?: string;
}

export interface TriageResponse {
  alert_id: string;
  messages: TriageMessage[];
}