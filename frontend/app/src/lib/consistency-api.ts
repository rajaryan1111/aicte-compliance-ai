// Consistency finding list filters

function buildQuery(params: Record<string, string | number | boolean | undefined>): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) query.set(key, String(value));
  }
  const encoded = query.toString();
  return encoded ? `?${encoded}` : "";
}

// ── Applications (tenant-scoped selector source) ────────────────

const APPLICATIONS_INVALID_MESSAGE =
  "Application list returned an invalid response.";

export function fetchApplications(
  token: string,
  options?: ConsistencyRequestOptions & { limit?: number; skip?: number },
): Promise<ApiResult<ApplicationPage>> {
  const query = buildQuery({ skip: options?.skip, limit: options?.limit });
  return consistencyRequest<ApplicationPage>(
    `/api/v1/applications${query}`,
    token,
    {},
    isApplicationPage,
    APPLICATIONS_INVALID_MESSAGE,
    options,
  );
}

// ── Consistency checks ──────────────────────────────────────────

export function createConsistencyCheck(
  payload: ConsistencyCheckCreate,
  token: string,
  options?: ConsistencyRequestOptions,
): Promise<ApiResult<ConsistencyCheck>> {
  return consistencyRequest<ConsistencyCheck>(
    "/api/v1/consistency/",
    token,
    { method: "POST", body: JSON.stringify(payload) },
    isConsistencyCheck,
    "Consistency check service returned an invalid response.",
    options,
  );
}

export function listConsistencyChecks(
  token: string,
  filters?: ConsistencyListFilters,
  options?: ConsistencyRequestOptions,
): Promise<ApiResult<ConsistencyCheck[]>> {
  const query = buildQuery({
    application_id: filters?.applicationId,
    status_filter: filters?.statusFilter,
  });
  return consistencyRequest<ConsistencyCheck[]>(
    `/api/v1/consistency/${query}`,
    token,
    {},
    isConsistencyCheckList,
    "Saved consistency checks returned an invalid response.",
    options,
  );
}

export function getConsistencyCheck(
  checkId: number,
  token: string,
  options?: ConsistencyRequestOptions,
): Promise<ApiResult<ConsistencyCheck>> {
  return consistencyRequest<ConsistencyCheck>(
    `/api/v1/consistency/${checkId}`,
    token,
