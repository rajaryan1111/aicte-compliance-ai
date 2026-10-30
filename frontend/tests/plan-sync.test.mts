/**
 * Contract tests between the browser plan client and the institution plan API.
 *
 * The sample payload below is a captured response from the real FastAPI route (synthetic
 * institution and user), so a future schema rename on either side fails here instead of in
 * production.
 */

import test from "node:test";
import assert from "node:assert/strict";
import {
  buildPlanPayload,
  isRetryableSyncFailure,
  mergeRemotePlan,
  parseRemotePlan,
  planMatchesRemote,
  updateDeadlinePolicy,
} from "../app/src/lib/plan-sync.ts";
import {
  DEFAULT_DEADLINE_POLICY,
  buildActionPlan,
  setItemStatus,
  type ActionPlan,
} from "../app/src/lib/action-plan.ts";
import type { ValidationRequest, ValidationResponse } from "../app/src/lib/api.ts";

const TODAY = new Date("2026-10-30T09:00:00Z");

const request: ValidationRequest = {
  institution_id: "SYNTH-DEMO-001",
  application_type: "eoa",
  required_documents: ["fire_safety_certificate", "aicte_approval", "mandatory_disclosure"],
  submitted_documents: ["aicte_approval", "mandatory_disclosure"],
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
    {
      code: "EXPIRING_SOON",
      document_type: "mandatory_disclosure",
      message: "Expires within 60 days.",
      evidence: { source: "synthetic_demo_input", expiry_date: "2026-11-20" },
    },
  ],
  checked_at: "2026-10-30T08:59:00+00:00",
  source: "synthetic_demo_input",
  notice: "Preliminary validation only.",
};

const plan: ActionPlan = buildActionPlan(request, response, TODAY);

/** Captured from POST /api/v1/institutions/{ref}/remediation-plans (synthetic data). */
const serverPlan = {
  id: 1,
  institution_id: 1,
  institution_ref: "SYNTH-DEMO-001",
  plan_key: plan.planId,
  application_type: "eoa",
  deadline_policy: {
    p1_days: 3,
    p2_days: 7,
    p3_buffer_days: 14,
    p3_max_days: 21,
    expiring_window_days: 60,
  },
  created_by: "contract_user",
  created_at: "2026-10-30T19:36:47.160414",
  updated_at: "2026-10-30T19:36:47.160416",
  tasks: [
    {
      id: 1,
      task_key: "fire_safety_certificate::MISSING_DOCUMENT",
      document_id: "fire_safety_certificate",
      document_label: "Fire Safety Certificate / NOC",
      finding_code: "MISSING_DOCUMENT",
      priority: "P1",
      owner_role: "Estate & Fire Safety Officer",
      due_date: "2026-11-03",
      evidence_required: "Valid fire NOC covering all blocks.",
      clause: "Clause 2.4",
      status: "open",
      note: "",
      version: 1,
      status_changed_by: null,
      status_changed_at: null,
      created_at: "2026-10-30T19:36:47.160848",
      updated_at: "2026-10-30T19:36:47.160849",
    },
  ],
  notice: "Stored institutional work plan.",
};

test("plan payload matches the backend schema", () => {
  const payload = buildPlanPayload(plan, DEFAULT_DEADLINE_POLICY, "SYNTH-DEMO-001");
  assert.equal(payload.institution_ref, "SYNTH-DEMO-001");
  assert.equal(payload.plan_key, plan.planId);
  assert.deepEqual(payload.deadline_policy, {
    p1_days: 3,
    p2_days: 7,
    p3_buffer_days: 14,
    p3_max_days: 21,
    expiring_window_days: 60,
  });
  assert.equal(payload.items.length, plan.items.length);
  for (const [index, item] of payload.items.entries()) {
    assert.equal(item.task_key, plan.items[index].id);
    assert.equal(item.due_date, plan.items[index].dueDate);
    assert.equal(item.finding_code, plan.items[index].findingCode);
    assert.ok(item.evidence_required.length > 0);
  }
});

test("stored plan payload is parsed and rejects unexpected shapes", () => {
  const parsed = parseRemotePlan(serverPlan);
  assert.ok(parsed);
  assert.equal(parsed.id, 1);
  assert.equal(parsed.planKey, plan.planId);
  assert.equal(parsed.tasks[0].taskKey, "fire_safety_certificate::MISSING_DOCUMENT");
  assert.equal(parsed.tasks[0].version, 1);
  assert.equal(parsed.deadlinePolicy.p1Days, 3);

  assert.equal(parseRemotePlan({ ...serverPlan, tasks: [{ task_key: "x" }] }), null, "task shape is checked");
  assert.equal(parseRemotePlan({ ...serverPlan, tasks: "nope" }), null);
  assert.equal(parseRemotePlan(null), null);
  const badStatus = {
    ...serverPlan,
    tasks: [{ ...serverPlan.tasks[0], status: "approved" }],
  };
  assert.equal(parseRemotePlan(badStatus), null, "only the four plan statuses are accepted");

  const missingVersion = {
    ...serverPlan,
    tasks: [{ ...serverPlan.tasks[0], version: 0 }],
  };
  assert.equal(parseRemotePlan(missingVersion), null);
});

test("server progress wins over local state, deficiency list stays local", () => {
  const local = setItemStatus(
    plan,
    "fire_safety_certificate::MISSING_DOCUMENT",
    "in_progress",
  );
  const remote = parseRemotePlan({
    ...serverPlan,
    deadline_policy: { ...serverPlan.deadline_policy, p1_days: 5, p2_days: 9 },
    tasks: [
      {
        ...serverPlan.tasks[0],
        status: "done",
        note: "NOC received",
        version: 2,
        due_date: "2026-11-06",
        status_changed_by: "officer7",
      },
    ],
  });
  assert.ok(remote);

  const merged = mergeRemotePlan(local, remote);
  const task = merged.items.find((item) => item.id === "fire_safety_certificate::MISSING_DOCUMENT");
  assert.equal(task?.status, "done");
  assert.equal(task?.note, "NOC received");
  assert.equal(task?.dueDate, "2026-11-06");
  assert.equal(merged.items.length, local.items.length, "the checklist still comes from the run");
  // A task the server knows nothing about keeps its local progress.
  const untouched = merged.items.find((item) => item.id !== task?.id);
  if (untouched) {
    assert.equal(untouched.status, "open");
  }

  // A different plan signature must never be merged.
  const foreign = { ...remote, planKey: "plan-someotherother" };
  assert.deepEqual(mergeRemotePlan(local, foreign), local);
});

test("planMatchesRemote detects unsynced progress", () => {
  const remote = parseRemotePlan(serverPlan);
  assert.ok(remote);

  const aligned = mergeRemotePlan(plan, remote);
  // Only the server's single task is compared; tasks absent remotely are ignored by design.
  const comparisonPlan: ActionPlan = {
    ...aligned,
    items: aligned.items.filter((item) => item.id === remote.tasks[0].taskKey),
  };
  assert.equal(planMatchesRemote(comparisonPlan, remote), true);
  assert.equal(
    planMatchesRemote(setItemStatus(comparisonPlan, remote.tasks[0].taskKey, "done"), remote),
    false,
  );
});

/**
 * Rescheduling is administrator-only on the server, so the client contract has to be exact: the
 * policy payload keys, the PATCH path, and the mapping of a 403 to a non-retryable message.
 */
test("updateDeadlinePolicy PATCHes the administrator route and reads back history", async () => {
  const captured: { url: string; method: string; body: unknown }[] = [];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    captured.push({
      url: String(input),
      method: init?.method ?? "GET",
      body: init?.body ? JSON.parse(String(init.body)) : null,
    });
    return new Response(
      JSON.stringify({
        ...serverPlan,
        deadline_policy: {
          p1_days: 5,
          p2_days: 10,
          p3_buffer_days: 14,
          p3_max_days: 21,
          expiring_window_days: 60,
        },
        deadline_history: [
          {
            id: 7,
            changed_by: "synthetic_admin",
            previous_policy: serverPlan.deadline_policy,
            new_policy: {
              p1_days: 5,
              p2_days: 10,
              p3_buffer_days: 14,
              p3_max_days: 21,
              expiring_window_days: 60,
            },
            rescheduled_tasks: 2,
            created_at: "2026-10-31T10:15:00+00:00",
          },
        ],
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    );
  }) as typeof fetch;

  try {
    const result = await updateDeadlinePolicy(
      "SYNTH-DEMO-001",
      1,
      { p1Days: 5, p2Days: 10, p3BufferDays: 14, p3MaxDays: 21, expiringWindowDays: 60 },
      "synthetic-token",
    );

    assert.equal(captured.length, 1);
    assert.equal(captured[0].method, "PATCH");
    assert.ok(
      captured[0].url.endsWith("/api/v1/institutions/SYNTH-DEMO-001/remediation-plans/1/deadline-policy"),
      captured[0].url,
    );
    assert.deepEqual(captured[0].body, {
      policy: { p1_days: 5, p2_days: 10, p3_buffer_days: 14, p3_max_days: 21, expiring_window_days: 60 },
    });

    assert.equal(result.ok, true);
    if (!result.ok) return;
    assert.equal(result.plan.deadlinePolicy.p1Days, 5);
    assert.equal(result.plan.deadlineHistory.length, 1);
    assert.equal(result.plan.deadlineHistory[0].changedBy, "synthetic_admin");
    assert.equal(result.plan.deadlineHistory[0].rescheduledTasks, 2);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("updateDeadlinePolicy reports a 403 as a non-retryable role refusal", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async () =>
    new Response(JSON.stringify({ detail: "Forbidden" }), {
      status: 403,
      headers: { "Content-Type": "application/json" },
    })) as typeof fetch;

  try {
    const result = await updateDeadlinePolicy(
      "SYNTH-DEMO-001",
      1,
      DEFAULT_DEADLINE_POLICY,
      "synthetic-token",
    );
    assert.equal(result.ok, false);
    if (result.ok) return;
    assert.equal(result.kind, "forbidden");
    assert.equal(isRetryableSyncFailure(result.kind), false);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
