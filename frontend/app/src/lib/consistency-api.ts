// Consistency findings

export function listConsistencyFindings(
  checkId: number,
  token: string,
  filters?: ConsistencyFindingListFilters,
  options?: ConsistencyRequestOptions,
): Promise<ApiResult<ConsistencyFinding[]>> {
  const query = buildQuery({
    severity_filter: filters?.severityFilter,
    resolved: filters?.resolved,
  });
  return consistencyRequest<ConsistencyFinding[]>(
    `/api/v1/consistency/checks/${checkId}/findings${query}`,
    token,
    {},
    isConsistencyFindingList,
    "Findings service returned an invalid response.",
    options,
  );
}

export function createConsistencyFinding(
  payload: ConsistencyFindingCreate,
  token: string,
  options?: ConsistencyRequestOptions,
): Promise<ApiResult<ConsistencyFinding>> {
  return consistencyRequest<ConsistencyFinding>(
    "/api/v1/consistency/findings",
    token,
    { method: "POST", body: JSON.stringify(payload) },
    isConsistencyFinding,
    "Findings service returned an invalid response.",
    options,
  );
}

export function updateConsistencyFinding(
  findingId: number,
  payload: ConsistencyFindingUpdate,
  token: string,
  options?: ConsistencyRequestOptions,
): Promise<ApiResult<ConsistencyFinding>> {
  return consistencyRequest<ConsistencyFinding>(
    `/api/v1/consistency/findings/${findingId}`,
    token,
    { method: "PATCH", body: JSON.stringify(payload) },
    isConsistencyFinding,
    "Findings service returned an invalid response.",
    options,
  );
}
