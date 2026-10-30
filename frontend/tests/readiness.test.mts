import test from "node:test";
import assert from "node:assert/strict";
import {
  READINESS_SCORING_VERSION,
  READINESS_WEIGHTS,
  computeReadinessScore,
  resolveClauseForDocument,
} from "../app/src/lib/aicte-rules.ts";

const TODAY = new Date("2026-10-30T00:00:00Z");

test("clause lookup resolves identifiers, display labels and humanised spellings", () => {
  const byId = resolveClauseForDocument("fire_safety_certificate");
  const byLabel = resolveClauseForDocument("Fire Safety Certificate");
  const byMixedCase = resolveClauseForDocument("FIRE SAFETY certificate");
  assert.equal(byId?.clause, "Clause 2.4");
  assert.equal(byLabel?.clause, "Clause 2.4");
  assert.equal(byMixedCase?.clause, "Clause 2.4");
  assert.equal(resolveClauseForDocument("building_occupancy_certificate")?.clause, "Clause 2.5");
  assert.equal(resolveClauseForDocument("mandatory_disclosure")?.clause, "Clause 2.1");
});

test("clause lookup returns undefined instead of inventing a citation", () => {
  assert.equal(resolveClauseForDocument("trust_deed"), undefined);
  assert.equal(resolveClauseForDocument("some_unknown_document"), undefined);
  assert.equal(resolveClauseForDocument(""), undefined);
});

test("statutory identifier lookup now applies the zero-tolerance penalty", () => {
  const result = computeReadinessScore(
    ["fire_safety_certificate", "trust_deed"],
    ["trust_deed"],
    {},
    TODAY,
  );
  assert.equal(result.totalRequired, 2);
  assert.equal(result.missingCount, 1);
  assert.equal(result.criticalZeroToleranceCount, 1);
  // base 50 (1 of 2) - 18 (statutory gap) = 32
  assert.equal(result.baseScore, 50);
  assert.equal(result.score, 32);
  assert.equal(result.tier, "critical_deficiency_risk");
  assert.ok(result.findings[0].clause, "missing statutory document carries its clause");
});

test("a complete, unexpired checklist scores 100 and says it is only a checklist", () => {
  const result = computeReadinessScore(
    ["trust_deed", "nba_accreditation"],
    ["trust_deed", "nba_accreditation"],
    { trust_deed: "2030-01-01", nba_accreditation: "2029-06-30" },
    TODAY,
  );
  assert.equal(result.score, 100);
  assert.equal(result.breakdown.reduce((sum, entry) => sum + entry.points, 0), 100);
  assert.equal(result.tier, "ready_nil_deficiency");
  assert.match(result.summary, /not an approval/i);
});

test("expired statutory documents are penalised once, not twice", () => {
  const result = computeReadinessScore(
    ["fire_safety_certificate"],
    ["fire_safety_certificate"],
    { fire_safety_certificate: "2026-01-31" },
    TODAY,
  );
  assert.equal(result.expiredCount, 1);
  assert.equal(result.criticalZeroToleranceCount, 1);
  // base 0 (the only required document is expired) - 18, clamped at 0
  assert.equal(result.baseScore, 0);
  assert.equal(result.score, 0);
});

test("score is clamped at zero and the breakdown still explains the raw total", () => {
  const result = computeReadinessScore(
    ["fire_safety_certificate", "building_occupancy_certificate", "fd_corpus_fund_receipt"],
    [],
    {},
    TODAY,
  );
  const rawTotal = result.breakdown.reduce((sum, entry) => sum + entry.points, 0);
  assert.equal(result.score, 0);
  assert.equal(rawTotal, -54);
  assert.equal(result.breakdown.length, 4); // base + three statutory gaps
});

test("certificates expiring inside the window are surfaced and deducted", () => {
  const result = computeReadinessScore(
    ["fire_safety_certificate", "trust_deed"],
    ["fire_safety_certificate", "trust_deed"],
    { fire_safety_certificate: "2026-11-15" },
    TODAY,
  );
  assert.equal(result.expiringSoonCount, 1);
  assert.equal(result.baseScore, 100);
  assert.equal(result.score, 100 + READINESS_WEIGHTS.expiringSoon);
  assert.equal(result.findings[0].type, "expiring_soon");
});

test("invalid and missing expiry dates cannot crash or create findings", () => {
  const result = computeReadinessScore(
    ["trust_deed"],
    ["trust_deed"],
    { trust_deed: "not-a-date" },
    TODAY,
  );
  assert.equal(result.expiredCount, 0);
  assert.equal(result.expiringSoonCount, 0);
  assert.equal(result.score, 100);
});

test("empty checklist scores zero rather than dividing by zero", () => {
  const result = computeReadinessScore([], [], {}, TODAY);
  assert.equal(result.totalRequired, 0);
  assert.equal(result.score, 0);
  assert.ok(Number.isFinite(result.score));
});

test("scoring is deterministic and carries a version", () => {
  const args: Parameters<typeof computeReadinessScore> = [
    ["fire_safety_certificate", "trust_deed"],
    ["trust_deed"],
    {},
    TODAY,
  ];
  const first = computeReadinessScore(...args);
  const second = computeReadinessScore(...args);
  assert.deepEqual(first, second);
  assert.equal(first.scoringVersion, READINESS_SCORING_VERSION);
});
