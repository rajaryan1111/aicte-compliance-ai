/** Types mirror the backend OpenAPI schemas exactly (verified against the live
 *  /openapi.json of main @ e88a5bf on 2026-10-24). Do not invent fields. */

export interface Token {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export interface UserRead {
  id: number;
  username: string;
  display_name: string | null;
  is_active: boolean;
  created_at: string;
}

export interface ApplicationRead {
  id: number;
  institution_id: number;
  application_type: string;
  academic_year: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface ApplicationListResponse {
  items: ApplicationRead[];
  total: number;
  skip: number;
  limit: number;
}

export interface DocumentVersionRead {
  id: number;
  document_id: number;
  version_number: number;
  storage_key: string;
  sha256: string;
  media_type: string;
  byte_size: number;
  page_count: number | null;
  file_name: string | null;
  scan_status: string | null;
  processing_status: string;
  uploaded_at: string;
}

export interface DocumentRead {
  id: number;
  application_id: number;
  document_type: string;
  current_version_id: number | null;
  created_at: string;
  current_version: DocumentVersionRead | null;
}

export interface DocumentListResponse {
  items: DocumentRead[];
  total: number;
}

export interface ProcessingJobRead {
  id: string;
  document_version_id: number;
  job_type: string;
  state: string;
  attempt_count: number;
  max_attempts: number;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  last_error_code: string | null;
}

export interface DocumentUploadResponse {
  document: DocumentRead;
  version: DocumentVersionRead;
  job: ProcessingJobRead | null;
  polling_url: string | null;
  extracted_fields_count: number;
  notice: string;
}

export interface ProcessingJobStatusResponse {
  job_id: string;
  document_id: number;
  version_id: number;
  application_id: number;
  state: string;
  scan_status: string | null;
  processing_status: string;
  attempt_count: number;
  max_attempts: number;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  last_error_code: string | null;
  extracted_fields_count: number;
  findings_count: number;
  is_terminal: boolean;
  notice: string;
}

export type CheckStatus =
  | 'passed'
  | 'failed'
  | 'inconclusive'
  | 'not_applicable'
  | 'not_run';

export interface ValidationCheckResultRead {
  id: number;
  validation_run_id: number;
  check_id: string;
  check_name: string;
  category: string;
  status: CheckStatus;
  document_version_id: number | null;
  message: string;
  evidence: string | null;
  limitations: string | null;
  created_at: string;
}

export interface FindingRead {
  id: number;
  validation_run_id: number;
  document_version_id: number | null;
  code: string;
  status: string;
  severity: string;
  summary: string;
  evidence: string | null;
  created_at: string;
}

export interface ValidationRunSummaryCounts {
  passed: number;
  failed: number;
  inconclusive: number;
  not_applicable: number;
  not_run: number;
}

export type ValidationOutcome =
  | 'preliminary_checks_passed'
  | 'attention_required'
  | 'inconclusive'
  | 'processing_incomplete';

export interface ValidationRunRead {
  id: number;
  application_id: number;
  status: 'queued' | 'running' | 'succeeded' | 'partial' | 'failed';
  outcome: ValidationOutcome | null;
  evaluation_date: string;
  ruleset_version: string;
  started_at: string;
  completed_at: string | null;
  triggered_by: string | null;
  consumed_version_ids: number[];
  summary_counts: ValidationRunSummaryCounts;
  limitations: string[];
}

export interface ScrutinyReportResponse {
  application_id: number;
  application_type: string;
  academic_year: string;
  institution_id: string;
  institution_name: string;
  validation_run: ValidationRunRead;
  check_results: ValidationCheckResultRead[];
  findings: FindingRead[];
  disclaimer: string;
  polling_url: string | null;
}

export interface ReviewSummaryResponse {
  application_id: number;
  total_findings: number;
  open_count: number;
  acknowledged_count: number;
  under_review_count: number;
  resolved_count: number;
  escalated_count: number;
  waived_count: number;
  pending_action_count: number;
}

export interface HealthResponse {
  status: string;
  service: string;
}
