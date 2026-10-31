/**
 * Backwards-compatible Consistency API module.
 *
 * The typed authenticated client is centralized in `api.ts` so all app
 * features share the same URL, timeout, bearer token, and error handling.
 */
export {
  createConsistencyCheck,
  createConsistencyFinding,
  fetchApplicationRecord,
  fetchApplications,
  fetchConsistencyCheck,
  fetchConsistencyChecks,
  fetchConsistencyFindings,
  updateConsistencyFinding,
} from "./api";
export type {
  ApplicationRecord as ApplicationSummary,
  ApplicationRecordPage as ApplicationPage,
  ConsistencyCheck,
  ConsistencyCheckCreate,
  ConsistencyFinding,
  ConsistencyFindingCreate,
  ConsistencyFindingUpdate,
  ConsistencyStatus,
} from "./api";
