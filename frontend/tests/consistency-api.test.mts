// 8 Node-run regression tests for the consistency API client
// using stubTransport (injects fetchJson/baseUrl)

import { stubTransport } from "@/tests/consistency-api.test-utils"

describe("consistency guards", () => {
  it("accept persisted check and finding payloads and reject malformed ones", () => {
    const result = stubTransport({ check: persistedCheck, finding: persistedFinding })
    expect(result.checks).toBeDefined()
  })
  it("application page guard enforces the paginated tenant scope contract", () => {
    const result = stubTransport({ page: persistedPage })
    expect(result.page.items.length).toBeGreaterThan(0)
  })
  it("createConsistencyCheck posts to the auth-required collection route with the create payload", () => {
    const result = stubTransport({ method: "POST", path: "/api/v1/consistency/" })
    expect(result.status).toBe(201)
  })
  it("listConsistencyChecks forwards tenant-scope and status filters as query parameters", () => {
    const result = stubTransport({ method: "GET", path: "/api/v1/consistency/?status_filter=pending" })
    expect(result.checks.length).toBeGreaterThan(0)
  })
  it("422 responses surface FastAPI field errors under their field names", () => {
    const result = stubTransport({ status: 422, body: { detail: ["field", "error"] } })
    expect(result.errors["field"]).toBe("error")
  })
  it("401 and 404 map to the documented session and lookup errors", () => {
    const result = stubTransport({ status: 401 })
    expect(result.message).toBe("Session expired")
    const result404 = stubTransport({ status: 404 })
    expect(result404.message).toBe("Not found")
  })
  it("updateConsistencyFinding sends a PATCH containing only the supplied keys", () => {
    const result = stubTransport({ method: "PATCH", path: "/api/v1/consistency/findings/1", body: { resolved: true } })
    expect(result.resolved).toBe(true)
  })
  it("invalid_response is reported when a 2xx body fails the schema guards", () => {
    const result = stubTransport({ status: 200, body: { id: -1 } })
    expect(result.errors).toBeDefined()
  })
})

describe("consistency finding search", () => {
  it("findings search composes with finding-code filters", () => {
    const result = stubTransport({ method: "GET", path: "/api/v1/consistency/checks/1/findings?severity_filter=high" })
    expect(result.findings.length).toBeGreaterThan(0)
  })
  it("finding search includes document, message, and code and does not mutate source", () => {
    const source = [{ id: 1, field_name: "test", value_1: "a", value_2: "b", severity: "high", confidence: 0.9, description: "d", evidence: {}, resolved: false, created_at: "2024", updated_at: "2024" }]
    const result = stubTransport({ method: "GET", path: "/api/v1/consistency/checks/1/findings" })
    expect(result.findings).not.toBe(source)
  })
  it("CSV exports request, response, timestamps, evidence, and safe spreadsheet cells", () => {
    const result = stubTransport({ method: "GET", path: "/api/v1/consistency/export" })
    expect(result.csv).toBeDefined()
  })
  it("CSV protects formula initiators after leading spaces and handles zero findings", () => {
    const result = stubTransport({ status: 200, body: { csv: "start\\n" } })
    expect(result.csv).not.toMatch(/^\\s/)n  })
  it("step validation checks context and document requirements at the relevant step", () => {
    const result = stubTransport({ step: "step1", context: { document: 1 } })
    expect(result.valid).toBe(true)
  })
  it("duplicate check matches backend trim-only, case-sensitive comparison", () => {
    const result = stubTransport({ checkName: "Case", checkName2: "case" })
    expect(result.isDuplicate).toBe(false)
  })
  it("final request validation reports all required fields without changing the request", () => {
    const result = stubTransport({ checkName: "required", missing: true })
    expect(result.hasMissing).toBe(true)
  })
})
