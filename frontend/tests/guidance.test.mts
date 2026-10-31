import test from "node:test";
import assert from "node:assert/strict";
import {
  DOCUMENT_GUIDANCE,
  GUIDANCE_SOURCE_NOTE,
  PLAN_UI,
  lookupDocumentGuidance,
  normalizeDocumentKey,
  pickLocalized,
} from "../app/src/lib/compliance-guidance.ts";

test("every guidance entry is complete in both languages", () => {
  for (const entry of DOCUMENT_GUIDANCE) {
    for (const [field, value] of Object.entries({
      label: entry.label,
      requirement: entry.requirement,
      impact: entry.impact,
      mitigation: entry.mitigation,
      ownerRole: entry.ownerRole,
      evidenceRequired: entry.evidenceRequired,
    })) {
      assert.ok(value.en.trim().length > 10, `${entry.id}.${field}.en is substantive`);
      assert.ok(value.hi.trim().length > 5, `${entry.id}.${field}.hi exists`);
    }
    if (entry.clause) {
      assert.ok(entry.chapter?.en, `${entry.id} has a chapter when it cites a clause`);
      assert.ok(entry.title?.en, `${entry.id} has a title when it cites a clause`);
    }
  }
});

test("identifiers are unique and aliases resolve to their own entry", () => {
  const ids = new Set<string>();
  for (const entry of DOCUMENT_GUIDANCE) {
    assert.equal(ids.has(entry.id), false, `duplicate id ${entry.id}`);
    ids.add(entry.id);
    for (const alias of entry.aliases) {
      assert.equal(lookupDocumentGuidance(alias)?.id, entry.id);
    }
    assert.equal(lookupDocumentGuidance(entry.id)?.id, entry.id);
    assert.equal(lookupDocumentGuidance(entry.label.en)?.id, entry.id);
  }
});

test("lookup is punctuation and case insensitive and never guesses", () => {
  assert.equal(lookupDocumentGuidance("fire_safety_certificate")?.id, "fire_safety_certificate");
  assert.equal(lookupDocumentGuidance("FIRE SAFETY CERTIFICATE")?.id, "fire_safety_certificate");
  assert.equal(lookupDocumentGuidance("  fire safety certificate ")?.id, "fire_safety_certificate");
  assert.equal(lookupDocumentGuidance("not_a_real_document"), undefined);
  assert.equal(lookupDocumentGuidance(""), undefined);
});

test("normalisation strips separators but keeps letters and digits", () => {
  assert.equal(normalizeDocumentKey("Fire-Safety / NOC"), "firesafetynoc");
  assert.equal(normalizeDocumentKey("Land Use Certificate"), "landusecertificate");
});

test("clause citations exist only where the catalog has one", () => {
  assert.equal(lookupDocumentGuidance("fire_safety_certificate")?.clause, "Clause 2.4");
  assert.equal(lookupDocumentGuidance("aicte_approval")?.clause, null);
  assert.equal(lookupDocumentGuidance("trust_deed")?.clause, null);
});

test("Hindi guidance is a translation, not a copy of the English", () => {
  const fire = lookupDocumentGuidance("fire_safety_certificate");
  assert.ok(fire);
  assert.notEqual(fire.requirement.hi, fire.requirement.en);
  assert.notEqual(fire.mitigation.hi, fire.mitigation.en);
  assert.equal(pickLocalized(fire.impact, "hi"), fire.impact.hi);
  assert.equal(pickLocalized(fire.impact, "en"), fire.impact.en);
});

test("the unofficial-translation and unverified-clause notices exist in both languages", () => {
  for (const notice of [GUIDANCE_SOURCE_NOTE, PLAN_UI.unofficial]) {
    assert.ok(notice.en.length > 20);
    assert.ok(notice.hi.length > 10);
  }
  assert.match(PLAN_UI.unofficial.en, /unofficial/i);
});

test("plan UI strings cover every status, priority and action in both languages", () => {
  for (const status of ["open", "in_progress", "blocked", "done"] as const) {
    assert.ok(PLAN_UI[status].en);
    assert.ok(PLAN_UI[status].hi);
  }
  for (const priority of ["P1", "P2", "P3"] as const) {
    assert.ok(PLAN_UI.priorities[priority].en.includes(priority));
    assert.ok(PLAN_UI.priorities[priority].hi.includes(priority));
  }
  const required = [
    "title",
    "subtitle",
    "storedLocally",
    "exportCsv",
    "reset",
    "evidence",
    "why",
    "fix",
    "requirement",
    "due",
    "overdue",
    "owner",
    "noClause",
    "unknownDocument",
  ] as const;
  for (const key of required) {
    assert.ok(PLAN_UI[key].en.length > 0, `${key}.en`);
    assert.ok(PLAN_UI[key].hi.length > 0, `${key}.hi`);
  }
});
