import test from "node:test";
import assert from "node:assert/strict";
import {
  DEFAULT_DEADLINE_POLICY,
  MAX_STORED_PLANS,
  addDays,
  applyDeadlinePolicy,
  formatIsoDate,
  normalizeDeadlinePolicy,
  buildActionPlan,
  createActionPlanCsv,
  daysBetween,
  mergePlanProgress,
  parseStoredPlans,
  planIdFor,
  resetPlanProgress,
  serializeStoredPlans,
  setItemNote,
  setItemStatus,
  summarizePlan,
  upsertPlan,
  type ActionPlan,
} from "../app/src/lib/action-plan.ts";
import type { ValidationRequest, ValidationResponse } from "../app/src/lib/api.ts";

const TODAY = new Date("2026-10-30T09:00:00Z");

const request: ValidationRequest = {
  institution_id: "SYNTH-DEMO-001",
  application_type: "eoa",
  required_documents: [
    "aicte_approval",
    "fire_safety_certificate",
    "trust_deed",
    "mandatory_disclosure",
  ],
  submitted_documents: ["aicte_approval", "trust_deed", "mandatory_disclosure"],
  expiry_dates: {
    aicte_approval: "2024-03-31",
    mandatory_disclosure: "2026-11-20",
  },
};

const response: ValidationResponse = {
  institution_id: "SYNTH-DEMO-001",
  application_type: "eoa",
  status: "attention_required",
  validation_scope: "caller_supplied_checklist_only",
  missing_documents: ["fire_safety_certificate"],
  expired_documents: ["aicte_approval"],
  findings: [
    {
      code: "MISSING_DOCUMENT",
      document_type: "fire_safety_certificate",
      message: "Required document was not submitted.",
      evidence: { source: "submitted_document_list", observed: "not_submitted" },
    },
    {
      code: "DOCUMENT_EXPIRED",
      document_type: "aicte_approval",
      message: "Expiry date is before the evaluation date.",
      evidence: { source: "synthetic_demo_input", expiry_date: "2024-03-31" },
    },
  ],
  checked_at: "2026-10-30T08:59:00+00:00",
  source: "synthetic_demo_input",
  notice: "Preliminary validation only.",
};

test("plan turns findings into prioritised, owned tasks with due dates", () => {
  const plan = buildActionPlan(request, response, TODAY);
  assert.equal(plan.items.length, 3);

  const [approval, fire, disclosure] = plan.items;
  assert.equal(approval.documentId, "aicte_approval");
  assert.equal(approval.priority, "P1");
  assert.equal(approval.dueDate, "2026-11-02");
  assert.equal(approval.ownerRole, "Registrar / Principal");
  assert.equal(approval.status, "open");

  assert.equal(fire.documentId, "fire_safety_certificate");
  assert.equal(fire.priority, "P1");
  assert.equal(fire.clause, "Clause 2.4");

  assert.equal(disclosure.findingCode, "EXPIRING_SOON");
  assert.equal(disclosure.priority, "P3");
  // 2026-11-20 minus 14 days, which is after today.
  assert.equal(disclosure.dueDate, "2026-11-06");
});

test("non-statutory gaps are P2 and overdue is derived from the due date", () => {
  const plan = buildActionPlan(
    { ...request, required_documents: ["trust_deed"], submitted_documents: [], expiry_dates: {} },
    { ...response, missing_documents: ["trust_deed"], expired_documents: [], findings: [
      { code: "MISSING_DOCUMENT", document_type: "trust_deed", message: "missing", evidence: {} },
    ] },
    TODAY,
  );
  assert.equal(plan.items[0].priority, "P2");
  assert.equal(plan.items[0].clause, null);

  const summaryNow = summarizePlan(plan, TODAY);
  assert.equal(summaryNow.overdue, 0);

  const later = new Date("2026-11-20T00:00:00Z");
  assert.equal(summarizePlan(plan, later).overdue, 1);
});

test("duplicate findings collapse into one task per document and code", () => {
  const duplicated: ValidationResponse = {
    ...response,
    findings: [...response.findings, response.findings[0]],
  };
  const plan = buildActionPlan(request, duplicated, TODAY);
  assert.equal(plan.items.length, 3);
});

test("typed lists still produce a plan when findings are omitted", () => {
  const plan = buildActionPlan(
    { ...request, expiry_dates: { aicte_approval: "2024-03-31" } },
    { ...response, findings: [] },
    TODAY,
  );
  assert.equal(plan.items.length, 2);
  assert.deepEqual(
    plan.items.map((item) => item.findingCode).sort(),
    ["DOCUMENT_EXPIRED", "MISSING_DOCUMENT"],
  );
});

test("an expired document is not also scheduled as expiring soon", () => {
  const plan = buildActionPlan(
    { ...request, expiry_dates: { aicte_approval: "2024-03-31" } },
    {
      ...response,
      missing_documents: [],
      expired_documents: ["aicte_approval"],
      findings: [],
    },
    TODAY,
  );
  assert.deepEqual(plan.items.map((item) => item.findingCode), ["DOCUMENT_EXPIRED"]);
});

test("status, note and reset mutations are immutable and bounded", () => {
  const plan = buildActionPlan(request, response, TODAY);
  const target = plan.items[0];

  const advanced = setItemStatus(plan, target.id, "done");
  assert.equal(advanced.items[0].status, "done");
  assert.equal(plan.items[0].status, "open", "source plan is not mutated");
  assert.equal(advanced.items.length, plan.items.length);

  const noted = setItemNote(advanced, target.id, "x".repeat(400));
  assert.equal(noted.items[0].note.length, 280);

  const reset = resetPlanProgress(noted);
  assert.equal(reset.items[0].status, "open");
  assert.equal(reset.items[0].note.length, 280, "reset only clears completion state");
});

test("summary counts completion and ignores completed items when finding the next due date", () => {
  const plan = buildActionPlan(request, response, TODAY);
  const done = setItemStatus(plan, plan.items[0].id, "done");
  const summary = summarizePlan(done, TODAY);
  assert.equal(summary.total, 3);
  assert.equal(summary.done, 1);
  assert.equal(summary.completionPct, 33);
  assert.equal(summary.nextDueDate, "2026-11-02");

  const allDone = plan.items.reduce(
    (current, item) => setItemStatus(current, item.id, "done"),
    plan,
  );
  assert.equal(summarizePlan(allDone, TODAY).completionPct, 100);
  assert.equal(summarizePlan(allDone, TODAY).nextDueDate, null);
});

test("date arithmetic crosses month and leap-year boundaries", () => {
  assert.equal(addDays("2026-10-31", 1), "2026-11-01");
  assert.equal(addDays("2026-12-31", 1), "2027-01-01");
  assert.equal(addDays("2028-02-28", 1), "2028-02-29");
  assert.equal(daysBetween("2026-10-30", "2026-11-02"), 3);
  assert.equal(daysBetween("2026-11-02", "2026-10-30"), -3);
});

test("storage codec round-trips, rejects foreign versions and corrupt JSON", () => {
  const plan = buildActionPlan(request, response, TODAY);
  const raw = serializeStoredPlans([plan]);
  const parsed = parseStoredPlans(raw);
  assert.equal(parsed.length, 1);
  assert.equal(parsed[0].planId, plan.planId);

  assert.deepEqual(parseStoredPlans(null), []);
  assert.deepEqual(parseStoredPlans("{not json"), []);
  assert.deepEqual(parseStoredPlans(JSON.stringify({ version: 99, plans: [plan] })), []);
  assert.deepEqual(parseStoredPlans(JSON.stringify({ version: 1, plans: [{ planId: 1 }] })), []);
});

test("a plan with one malformed item is discarded rather than half-restored", () => {
  const plan = buildActionPlan(request, response, TODAY);
  const broken = {
    version: 1,
    plans: [{ ...plan, items: [...plan.items, { id: "x" }] }],
  };
  assert.deepEqual(parseStoredPlans(JSON.stringify(broken)), []);
});

test("upsert replaces the same plan and caps the store", () => {
  const plan = buildActionPlan(request, response, TODAY);
  const other: ActionPlan = { ...plan, planId: "plan-other" };
  const replaced = upsertPlan([plan, other], { ...plan, createdAt: "2026-10-31T00:00:00Z" });
  assert.equal(replaced.length, 2);
  assert.equal(replaced[0].createdAt, "2026-10-31T00:00:00Z");

  const many = Array.from({ length: MAX_STORED_PLANS + 5 }, (_, index) => ({
    ...plan,
    planId: `plan-${index}`,
  }));
  assert.equal(upsertPlan(many, plan).length, MAX_STORED_PLANS);
});

test("plan id survives a re-run of the same checklist and changes with the deficiencies", () => {
  const first = buildActionPlan(request, response, TODAY);
  const rerun = buildActionPlan(
    request,
    { ...response, checked_at: "2026-10-31T10:00:00+00:00" },
    new Date("2026-10-31T09:00:00Z"),
  );
  assert.equal(first.planId, rerun.planId, "a re-run must reopen the same plan to keep progress");

  const resolved = buildActionPlan(
    { ...request, submitted_documents: [...request.submitted_documents, "fire_safety_certificate"] },
    {
      ...response,
      missing_documents: [],
      findings: response.findings.filter((finding) => finding.code !== "MISSING_DOCUMENT"),
    },
    TODAY,
  );
  assert.notEqual(first.planId, resolved.planId, "different deficiencies are a different plan");

  assert.equal(planIdFor("A", "eoa", "x"), planIdFor("A", "eoa", "x"));
  assert.notEqual(planIdFor("A", "eoa", "x"), planIdFor("B", "eoa", "x"));
});

test("merging a re-run keeps recorded progress and takes provenance from the new run", () => {
  const previous = buildActionPlan(request, response, TODAY);
  const noted = setItemNote(previous, previous.items[0].id, "renewal filed");
  const advanced = noted.items.reduce(
    (current, item) => setItemStatus(current, item.id, "done"),
    noted,
  );

  const rerun = buildActionPlan(
    request,
    { ...response, checked_at: "2026-11-01T07:30:00+00:00" },
    new Date("2026-11-01T07:00:00Z"),
  );
  const merged = mergePlanProgress(rerun, advanced);
  assert.equal(merged.planId, rerun.planId);
  assert.equal(merged.checkedAt, "2026-11-01T07:30:00+00:00", "the new run is the record of truth");
  assert.ok(merged.items.every((item) => item.status === "done"), "progress is carried over");
  assert.equal(summarizePlan(merged, TODAY).completionPct, 100);
  assert.equal(
    merged.items.find((item) => item.id === previous.items[0].id)?.note,
    "renewal filed",
  );

  // A task that is absent from the stored plan is never invented into a completed state.
  const partial = mergePlanProgress(rerun, { ...advanced, items: advanced.items.slice(1) });
  assert.equal(partial.items.length, rerun.items.length);
  assert.equal(partial.items[0].status, "open");
});

test("CSV export neutralises spreadsheet formulas and includes every task", () => {
  const plan = buildActionPlan({ ...request, institution_id: "=SYNTH" }, response, TODAY);
  const csv = createActionPlanCsv(plan);
  const lines = csv.trimEnd().split("\r\n");
  assert.equal(lines.length, plan.items.length + 1);
  assert.match(lines[0], /^"plan_id","institution_id"/);
  assert.ok(lines[1].startsWith("\"plan-"));
  assert.ok(csv.includes("'=SYNTH"), "leading formula character is prefixed");
  assert.ok(csv.includes("\"Clause 2.4\""), "clause is exported when known");
  assert.ok(csv.includes("P1"));
});

test("deadline policy is clamped and never inverts P1/P2", () => {
  const normalized = normalizeDeadlinePolicy({
    p1Days: 0,
    p2Days: 1,
    p3BufferDays: -5,
    p3MaxDays: 9999,
    expiringWindowDays: 0,
  });
  assert.equal(normalized.p1Days, 1);
  assert.equal(normalized.p2Days, 1, "P2 never falls before P1");
  assert.equal(normalized.p3BufferDays, 0);
  assert.equal(normalized.p3MaxDays, 365, "offsets are bounded");
  assert.equal(normalized.expiringWindowDays, 1);

  const defaults = normalizeDeadlinePolicy({});
  assert.deepEqual(defaults, DEFAULT_DEADLINE_POLICY);
});

test("applying a policy re-dates tasks without touching progress", () => {
  const plan = setItemStatus(buildActionPlan(request, response, TODAY), "fire_safety_certificate::MISSING_DOCUMENT", "done");
  const applied = applyDeadlinePolicy(
    plan,
    { p1Days: 5, p2Days: 10, p3BufferDays: 30, p3MaxDays: 14, expiringWindowDays: 90 },
    TODAY,
  );

  const p1 = applied.items.find((item) => item.priority === "P1");
  assert.equal(p1?.dueDate, addDays(formatIsoDate(TODAY), 5));

  const p2 = applied.items.find((item) => item.priority === "P2");
  if (p2) assert.equal(p2.dueDate, addDays(formatIsoDate(TODAY), 10));

  const done = applied.items.find((item) => item.id === "fire_safety_certificate::MISSING_DOCUMENT");
  assert.equal(done?.status, "done", "progress survives a re-date");

  // EXPIRING_SOON works backwards from expiry, capped so a far-off certificate cannot drift.
  const soon = applied.items.find((item) => item.findingCode === "EXPIRING_SOON");
  if (soon) {
    const capped = addDays(formatIsoDate(TODAY), 14);
    assert.ok(daysBetween(formatIsoDate(TODAY), soon.dueDate) <= daysBetween(formatIsoDate(TODAY), capped));
    assert.ok(daysBetween(formatIsoDate(TODAY), soon.dueDate) >= 1);
  }
});
