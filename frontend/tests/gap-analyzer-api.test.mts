import test from "node:test";
import assert from "node:assert/strict";
import {
  fetchGapAnalysis,
  fetchGapValidationRuns,
  reviewGapMapping,
} from "../app/src/lib/api.ts";

const originalWindow = globalThis.window;
test.before(() => {
  Object.defineProperty(globalThis, "window", { configurable: true, value: { setTimeout, clearTimeout } });
});
test.after(() => {
  Object.defineProperty(globalThis, "window", { configurable: true, value: originalWindow });
});

function response(status: number, body: unknown) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

test("saved Gap Analyzer assessment history uses an authenticated, application-scoped route", async (t) => {
  const page = { items: [{ id: 7, application_id: 12, status: "succeeded", outcome: "attention_required", evaluation_date: "2026-10-31", ruleset_version: "1", started_at: "2026-10-31T00:00:00Z", completed_at: null, triggered_by: "reviewer" }], total: 1, skip: 0, limit: 100 };
  t.mock.method(globalThis, "fetch", async (input, init) => {
    assert.match(String(input), /\/api\/v1\/applications\/12\/validation-runs\?skip=0&limit=100$/);
    assert.equal(new Headers(init?.headers).get("Authorization"), "Bearer gap-token");
    return response(200, page);
  });
  assert.deepEqual(await fetchGapValidationRuns(12, "gap-token"), { ok: true, data: page });
});

test("assessment selection sends the persisted run ID to the scoped analysis endpoint", async (t) => {
  const analysis = { metrics: { validation_run_id: 7 }, requirements: [] };
  t.mock.method(globalThis, "fetch", async (input, init) => {
    assert.match(String(input), /\/api\/v1\/applications\/12\/gap-analysis\?run_id=7$/);
    assert.equal(new Headers(init?.headers).get("Authorization"), "Bearer gap-token");
    return response(200, analysis);
  });
  assert.deepEqual(await fetchGapAnalysis(12, "gap-token", 7), { ok: true, data: analysis });
});

test("evidence review persists decision, sufficiency and rationale with authentication", async (t) => {
  const mapping = { id: 8, rule_id: "APH_TEST", document_version_id: 22 };
  t.mock.method(globalThis, "fetch", async (input, init) => {
    assert.match(String(input), /\/api\/v1\/applications\/12\/requirement-evidence-mappings\/8$/);
    assert.equal(init?.method, "PATCH");
    assert.equal(new Headers(init?.headers).get("Authorization"), "Bearer gap-token");
    assert.deepEqual(JSON.parse(String(init?.body)), { status: "confirmed", sufficiency_status: "insufficient", rationale: "More evidence is still required." });
    return response(200, mapping);
  });
  assert.deepEqual(await reviewGapMapping(12, 8, "gap-token", "confirmed", "insufficient", "More evidence is still required."), { ok: true, data: mapping });
});
