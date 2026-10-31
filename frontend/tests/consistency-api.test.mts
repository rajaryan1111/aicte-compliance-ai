// Regression tests for the consistency API client.
// These run under node --experimental-strip-types against the real client
// module with an injected transport, guarding the wire contract that the
// backend (docs/development/API_CONTRACT.md, /api/v1/consistency) expects.

import test from "node:test";
import assert from "node:assert/strict";
import {
  isConsistencyCheck,
  isConsistencyCheckList,
  isConsistencyFinding,
  isConsistencyFindingList,
  isApplicationPage,
  createConsistencyCheck,
  listConsistencyChecks,
  updateConsistencyFinding,
  type ConsistencyCheck,
  type ConsistencyFinding,
  type ApplicationPage,
} from "../app/src/lib/consistency-api.ts";

const checkFixture: ConsistencyCheck = {
  id: 12,
  application_id: 34,
  check_name: "Sanctioned intake vs approved record",
  description: "Cross-check submitted intake with authorised record.",
  related_field: "approved_intake",
  status: "discrepancy_detected",
  created_at: "2026-10-30T08:00:00Z",
  updated_at: "2026-10-30T09:00:00Z",
};

const findingFixture: ConsistencyFinding = {
  id: 7,
  consistency_check_id: 12,
  field_name: "approved_intake",
  value_1: "240",
  value_2: "180",
  severity: "high",
  confidence: 0.85,
  description: "Submitted intake exceeds the authorised record.",
  evidence: { authorised_value: 180, submitted_value: 240 },
  resolved: false,
  created_at: "2026-10-30T08:05:00Z",
  updated_at: "2026-10-30T08:05:00Z",
};

const applicationPageFixture: ApplicationPage = {
  items: [
    {
      id: 34,
      institution_id: 2,
      application_type: "eoa",
      academic_year: "2026-2027",
      status: "draft",
    },
  ],
  total: 1,
  skip: 0,
  limit: 50,
};

function stubTransport(result) {
  const calls = [];
  const fetchJson = async (input, init) => {
    const url = String(input);
    const body = typeof init?.body === "string" && init.body.length > 0
      ? JSON.parse(init.body)
      : undefined;
    calls.push({ url, init, body });
    return {
      response: { ok: result.status >= 200 && result.status < 300, status: result.status },
      body: result.body,
      parseError: result.parseError ?? false,
    };
  };
  return { calls, fetchJson, baseUrl: (path) => path };
}

test("consistency guards accept persisted check and finding payloads and reject malformed ones", () => {
  assert.equal(isConsistencyCheck(checkFixture), true);
  assert.equal(isConsistencyCheckList([checkFixture, checkFixture]), true);
  assert.equal(isConsistencyFinding(findingFixture), true);
  assert.equal(isConsistencyFindingList([findingFixture]), true);
  assert.equal(isConsistencyCheck({ ...checkFixture, status: "draft" }), false);
  assert.equal(isConsistencyCheck({ ...checkFixture, id: "12" }), false);
  assert.equal(isConsistencyFinding({ ...findingFixture, resolved: "no" }), false);
  assert.equal(isConsistencyFinding({ ...findingFixture, evidence: "logs" }), false);
  assert.equal(isConsistencyCheckList(["nope"]), false);
});
