export interface TelemetrySnapshot {
  timestamp: string;
  voltage_a: number;
  voltage_b: number;
  voltage_c: number;
  current_a: number;
  current_b: number;
  current_c: number;
  temperature: number;
}

export interface ScenarioSummary {
  case_id: string;
  panel_id: string;
  initial_snapshot: TelemetrySnapshot;
  image_available: boolean;
}

export type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };

export interface TraceStep {
  step_number: number;
  kind: 'MODEL_RESPONSE' | 'TOOL_CALL' | 'TOOL_RESULT' | 'MAX_STEP_TERMINATION';
  phase: 'INVESTIGATION' | 'FINALIZATION';
  summary: string;
  tool_name: string | null;
  tool_call_id: string | null;
  tool_arguments: Record<string, JsonValue> | null;
  tool_result: Record<string, JsonValue> | null;
  evidence_ids_added: string[];
}

export interface EvidenceRecord {
  id: string;
  source: 'TELEMETRY' | 'HISTORY' | 'DETERMINISTIC_ANALYSIS' | 'MAINTENANCE_CONTEXT' | 'VISION';
  type: string;
  timestamp: string;
  summary: string;
  value: number | string | boolean | null;
  unit: string | null;
  tool_name: string | null;
  reliability: number;
  metadata: Record<string, JsonValue>;
}

export interface Diagnosis {
  status: 'DIAGNOSIS_READY' | 'NEEDS_MORE_EVIDENCE' | 'NO_ACTIONABLE_DIAGNOSIS';
  likely_fault: 'overload' | 'phase_imbalance' | 'connection_related_overheating' | 'unknown';
  risk_level: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL' | 'UNKNOWN';
  confidence: number;
  evidence_ids: string[];
  reasoning_summary: string;
  recommended_inspection: string;
  missing_evidence: string[];
}

export interface ModelUsage {
  request_count: number;
  requests_with_usage: number;
  input_tokens: number | null;
  output_tokens: number | null;
  total_tokens: number | null;
  reasoning_tokens: number | null;
}

export interface InvestigationResponse {
  case: ScenarioSummary & { history: TelemetrySnapshot[] };
  trace: TraceStep[];
  evidence: EvidenceRecord[];
  diagnosis: Diagnosis;
  usage: ModelUsage;
  estimated_cost_usd: number | null;
  cost_is_partial: boolean;
  model: string;
  termination_reason: 'NATURAL_STOP' | 'MAX_AGENT_STEPS';
}
