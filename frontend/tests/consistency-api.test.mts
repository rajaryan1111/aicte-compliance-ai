import test, { after, before, mock } from "node:test";
import assert from "node:assert/strict";
import {
  createConsistencyCheck,
  createConsistencyFinding,
  fetchApplicationRecord,
  fetchApplications,
  fetchConsistencyChecks,
  fetchConsistencyFindings,
  updateConsistencyFinding,
} from "../app/src/lib/api.ts";

const originalWindow = globalThis.window;
before(() => {
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: { setTimeout, clearTimeout },
  });
});
after(() => {
  Object.defineProperty(globalThis, "window", { configurable: true, value: originalWindow });
});

const check = {
  id: 21,
  application_id: 8,
  check_name: "Compare institution identifiers",
  description: null,
  related_field: "institution_id",
  status: "pending",
  created_at: "2026-10-31T02:00:00Z",
  updated_at: "2026-10-31T02:00:00Z",
};

const finding = {
  id: 34,
  consistency_check_id: 21,
  field_name: "institution_id",
  value_1: "INST-A",
  value_2: "INST-B",
  severity: "high",
  confidence: 0.9,
  description: "The identifiers do not match.",
  evidence: { source: "two application records" },
  resolved: false,
  created_at: "2026-10-31T02:00:00Z",
  updated_at: "2026-10-31T02:00:00Z",
};

const application = {
  id: 8,
  institution_id: 4,
  application_type: "eoa",
  academic_year: "2026-2027",
  status: "submitted",
  created_at: "2026-10-30T02:00:00Z",
  updated_at: "2026-10-31T02:00:00Z",
};

function mockJsonResponse(status: number, body: unknown) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

test("consistency list uses the authenticated API and validates its response", async (t) => {
  const fetchMock = t.mock.method(globalThis, "fetch", async (input, init) => {
    assert.match(String(input), /\/consistency\/$/);
    assert.equal(new Headers(init?.headers).get("Authorization"), "Bearer test-token");
    return mockJsonResponse(200, [check]);
  });

  const result = await fetchConsistencyChecks("test-token");
  assert.equal(fetchMock.mock.callCount(), 1);
  assert.deepEqual(result, { ok: true, data: [check] });
});

test("application selection and details use tenant-scoped authenticated endpoints", async (t) => {
  let calls = 0;
  t.mock.method(globalThis, "fetch", async (input, init) => {
    calls += 1;
    assert.equal(new Headers(init?.headers).get("Authorization"), "Bearer test-token");
    if (calls === 1) {
      assert.match(String(input), /\/api\/v1\/applications\?skip=0&limit=100$/);
      return mockJsonResponse(200, { items: [application], total: 1, skip: 0, limit: 100 });
    }
    assert.match(String(input), /\/api\/v1\/applications\/8$/);
    return mockJsonResponse(200, application);
  });

  assert.deepEqual(await fetchApplications("test-token"), {
    ok: true,
    data: { items: [application], total: 1, skip: 0, limit: 100 },
  });
  assert.deepEqual(await fetchApplicationRecord(8, "test-token"), { ok: true, data: application });
});

test("creating a check sends only the backend create schema", async (t) => {
  const payload = {
    application_id: 8,
    check_name: "Compare institution identifiers",
    description: "Compare persisted application records.",
    related_field: "institution_id",
  };
  t.mock.method(globalThis, "fetch", async (_input, init) => {
    assert.equal(init?.method, "POST");
    assert.equal(new Headers(init?.headers).get("Authorization"), "Bearer test-token");
    assert.deepEqual(JSON.parse(String(init?.body)), payload);
    return mockJsonResponse(201, check);
  });

  assert.deepEqual(await createConsistencyCheck(payload, "test-token"), { ok: true, data: check });
});

test("finding create and update use the documented route and fields", async (t) => {
  let calls = 0;
  t.mock.method(globalThis, "fetch", async (input, init) => {
    calls += 1;
    assert.equal(new Headers(init?.headers).get("Authorization"), "Bearer test-token");
    if (calls === 1) {
      assert.match(String(input), /\/consistency\/checks\/21\/findings$/);
      return mockJsonResponse(200, [finding]);
    }
    if (calls === 2) {
      assert.match(String(input), /\/consistency\/findings$/);
      assert.equal(init?.method, "POST");
      assert.deepEqual(JSON.parse(String(init?.body)), {
        consistency_check_id: 21,
        field_name: "institution_id",
        value_1: "INST-A",
        value_2: "INST-B",
        severity: "high",
        confidence: 0.9,
        description: "The identifiers do not match.",
        evidence: { source: "two application records" },
      });
      return mockJsonResponse(201, finding);
    }
    assert.match(String(input), /\/consistency\/findings\/34$/);
    assert.equal(init?.method, "PATCH");
    assert.deepEqual(JSON.parse(String(init?.body)), { resolved: true });
    return mockJsonResponse(200, { ...finding, resolved: true });
  });

  assert.deepEqual(await fetchConsistencyFindings(21, "test-token"), { ok: true, data: [finding] });
  assert.deepEqual(await createConsistencyFinding({
    consistency_check_id: 21,
    field_name: "institution_id",
    value_1: "INST-A",
    value_2: "INST-B",
    severity: "high",
    confidence: 0.9,
    description: "The identifiers do not match.",
    evidence: { source: "two application records" },
  }, "test-token"), { ok: true, data: finding });
  assert.deepEqual(await updateConsistencyFinding(34, { resolved: true }, "test-token"), {
    ok: true,
    data: { ...finding, resolved: true },
  });
});

test("unauthorized and concealed cross-institution responses remain errors", async (t) => {
  let status = 401;
  t.mock.method(globalThis, "fetch", async () => mockJsonResponse(status, { detail: "Request rejected." }));

  const expired = await fetchConsistencyChecks("expired-token");
  assert.equal(expired.ok, false);
  if (!expired.ok) {
    assert.equal(expired.status, 401);
    assert.equal(expired.errors._server, "Your session expired. Sign in again.");
  }

  status = 404;
  const concealed = await fetchConsistencyFindings(21, "test-token");
  assert.equal(concealed.ok, false);
  if (!concealed.ok) {
    assert.equal(concealed.status, 404);
    assert.match(concealed.errors._server, /not found or access is denied/i);
  }

  status = 403;
  const forbidden = await fetchConsistencyChecks("test-token");
  assert.equal(forbidden.ok, false);
  if (!forbidden.ok) {
    assert.equal(forbidden.status, 403);
    assert.match(forbidden.errors._server, /does not have access/i);
  }
});
