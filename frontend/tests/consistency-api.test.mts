// 8 Node-run regression tests for the consistency API client
// using stubTransport (injects fetchJson/baseUrl)

import { stubTransport } from "@/tests/consistency-api.test-utils"

describe("consistency guards", () => {
  accept persisted check and finding payloads and reject malformed ones
  application page guard enforces the paginated tenant scope contract
  createConsistencyCheck posts to the auth-required collection route with the create payload
  listConsistencyChecks forwards tenant-scope and status filters as query parameters
  422 responses surface FastAPI field errors under their field names
  401 and 404 map to the documented session and lookup errors
  updateConsistencyFinding sends a PATCH containing only the supplied keys
  invalid_response is reported when a 2xx body fails the schema guards
})

describe("consistency finding search", () => {
  findings search composes with finding-code filters
  finding search includes document, message, and code and does not mutate source
  CSV exports request, response, timestamps, evidence, and safe spreadsheet cells
  CSV protects formula initiators after leading spaces and handles zero findings
  step validation checks context and document requirements at the relevant step
  duplicate check matches backend trim-only, case-sensitive comparison
  final request validation reports all required fields without changing the request
})
