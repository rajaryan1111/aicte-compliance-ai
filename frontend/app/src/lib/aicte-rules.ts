/**
 * AICTE Approval Process Handbook (APH 2024–2027) Regulatory Knowledge & Clause Reference.
 *
 * Provides clause citations, statutory document metadata, mitigation undertakings,
 * and Cadre/FSR calculation formulas based on the Council's published norms.
 *
 * The citations here are carried from the project catalog and remain unverified against the
 * official handbook; the UI must say so wherever they are shown.
 */

import { lookupDocumentGuidance } from "./compliance-guidance.ts";

export interface APHClauseReference {
  clause: string;
  chapter: string;
  title: string;
  requirement: string;
  deficiencyImpact: string;
  mitigationUndertaking: string;
  isStatutoryZeroTolerance: boolean;
}

export const APH_CLAUSE_CATALOG: Record<string, APHClauseReference> = {
  "Fire Safety Certificate": {
    clause: "Clause 2.4",
    chapter: "Chapter II: Extension of Approval",
    title: "Fire and Life Safety Clearance",
    requirement: "Valid Fire Safety NOC issued by the Competent State Fire Authority for all instructional and administrative blocks.",
    deficiencyImpact: "Zero-tolerance deficiency. Mandates withholding of EoA and summons before the Standing Hearing Committee (SHC).",
    mitigationUndertaking: "AICTE Format 3 Undertaking on Rs. 100 non-judicial stamp paper accompanied by the official renewal application receipt challan from the District Fire Officer.",
    isStatutoryZeroTolerance: true,
  },
  "Building Structural Stability Certificate": {
    clause: "Clause 2.6",
    chapter: "Chapter II: Infrastructure Verification",
    title: "Structural Soundness Certification",
    requirement: "Certificate issued by a Government-registered Structural Engineer confirming the building's earthquake and structural resistance.",
    deficiencyImpact: "Severe deficiency. Results in immediate halt of intake increase and mandatory physical inspection by an Expert Visit Committee (EVC).",
    mitigationUndertaking: "Provisional structural inspection affidavit by an empaneled engineer stating inspection is complete and official report submission is pending municipal seal.",
    isStatutoryZeroTolerance: true,
  },
  "Occupancy Certificate": {
    clause: "Clause 2.5",
    chapter: "Chapter II: Land & Building Norms",
    title: "Building Occupancy & Completion Certificate",
    requirement: "Final or provisional Occupancy Certificate from the Municipal Corporation / Competent Town Planning Authority.",
    deficiencyImpact: "Rejection of new programs or campus expansion. May lead to reduction in approved seat matrix.",
    mitigationUndertaking: "Submission of Building Blueprint certified by an architect along with local body application registration number.",
    isStatutoryZeroTolerance: true,
  },
  "Land Ownership Deed / 30-Year Registered Lease": {
    clause: "Clause 1.7",
    chapter: "Chapter I: Establishment of New Technical Institutions",
    title: "Contiguous Land Title & NA Conversion",
    requirement: "Clear, unencumbered land ownership or minimum 30-year registered lease deed with official Non-Agricultural (NA) educational conversion order.",
    deficiencyImpact: "Total disqualification of establishment/continuation. Division of campus across non-permitted separation distance.",
    mitigationUndertaking: "Certified copy of registered sub-registrar entry plus mutation extract confirming lawful title and physical possession.",
    isStatutoryZeroTolerance: true,
  },
  "State Pollution Control Board NOC": {
    clause: "Clause 1.8",
    chapter: "Chapter I & II: Environmental Clearances",
    title: "Consent to Operate / Water & Air NOC",
    requirement: "Consent to Operate / Certificate of Sewage and Effluent Treatment from the State Pollution Control Board.",
    deficiencyImpact: "Deficiency notice with 15-day rectification window before Regional Committee review.",
    mitigationUndertaking: "Formal copy of renewal application with verification fee challan submitted to the regional SPCB officer.",
    isStatutoryZeroTolerance: false,
  },
  "NBA Accreditation Certificate": {
    clause: "Clause 4.2",
    chapter: "Chapter IV: Intake Expansion & New Courses",
    title: "Programmatic Accreditation Norms",
    requirement: "Minimum valid NBA accreditation for at least 50% eligible courses for existing institutions seeking intake expansion.",
    deficiencyImpact: "Automatic denial of additional division or new specialization. Reversion to base intake.",
    mitigationUndertaking: "Pre-qualifier acceptance letter or NBA peer-visit scheduling acknowledgment receipt.",
    isStatutoryZeroTolerance: false,
  },
  "Affidavit 1 & Affidavit 2 (AICTE Portal Format)": {
    clause: "Clause 2.1",
    chapter: "Chapter II: Annual Self-Disclosure",
    title: "Mandatory Statutory Self-Disclosure Affidavits",
    requirement: "Duly notarized Affidavits 1 and 2 confirming accurate disclosure of faculty roster, fees, anti-ragging, and infrastructure.",
    deficiencyImpact: "Incomplete application. Rejection at online scrutinizer gate prior to committee review.",
    mitigationUndertaking: "Immediate digital re-upload with valid notary seal and stamp.",
    isStatutoryZeroTolerance: true,
  },
  "Fixed Deposit (Corpus Fund) Receipt": {
    clause: "Clause 1.9",
    chapter: "Chapter I: Financial Solvency",
    title: "Joint Corpus Security Deposit",
    requirement: "FDR in the joint name of Sponsoring Trust / Society and Regional Officer, AICTE for the prescribed lock-in period.",
    deficiencyImpact: "Withholding of Letter of Approval (LoA) or Letter of Extension (LoE).",
    mitigationUndertaking: "Banker's solvency certificate along with letter of lien creation submitted to AICTE Regional Office.",
    isStatutoryZeroTolerance: true,
  },
};

export interface CadreNorms {
  program: string;
  standardFSR: number; // e.g. 15 or 20
  professorRatio: number; // 1
  assocProfRatio: number; // 2
  asstProfRatio: number; // 6
  phdRequirement: {
    professor: number; // 100%
    assocProf: number; // 100%
    asstProf: number; // Optional/encouraged
  };
}

export const CADRE_PROGRAM_NORMS: Record<string, CadreNorms> = {
  "engineering_ug": {
    program: "Engineering & Technology (UG - B.Tech / B.E.)",
    standardFSR: 20, // AICTE Tier 2 default, Tier 1 is 15
    professorRatio: 1,
    assocProfRatio: 2,
    asstProfRatio: 6,
    phdRequirement: { professor: 1.0, assocProf: 1.0, asstProf: 0.2 },
  },
  "management_pg": {
    program: "Management (MBA / PGDM)",
    standardFSR: 20,
    professorRatio: 1,
    assocProfRatio: 2,
    asstProfRatio: 6,
    phdRequirement: { professor: 1.0, assocProf: 1.0, asstProf: 0.1 },
  },
  "mca_pg": {
    program: "Computer Applications (MCA)",
    standardFSR: 20,
    professorRatio: 1,
    assocProfRatio: 2,
    asstProfRatio: 6,
    phdRequirement: { professor: 1.0, assocProf: 1.0, asstProf: 0.1 },
  },
  "polytechnic_diploma": {
    program: "Diploma in Engineering & Technology",
    standardFSR: 25,
    professorRatio: 1,
    assocProfRatio: 2,
    asstProfRatio: 6,
    phdRequirement: { professor: 0.5, assocProf: 0.2, asstProf: 0.0 },
  },
};

/**
 * Document identifiers used by the API and presets, mapped to the catalog entries above.
 *
 * Only mappings that are genuinely the same document are listed. Anything absent resolves to
 * `undefined`, so the UI can say "no clause mapped" instead of showing a wrong citation.
 */
export const DOCUMENT_ID_TO_CATALOG_KEY: Record<string, string> = {
  fire_safety_certificate: "Fire Safety Certificate",
  building_occupancy_certificate: "Occupancy Certificate",
  land_use_certificate: "Land Ownership Deed / 30-Year Registered Lease",
  mandatory_disclosure: "Affidavit 1 & Affidavit 2 (AICTE Portal Format)",
  fd_corpus_fund_receipt: "Fixed Deposit (Corpus Fund) Receipt",
  nba_accreditation: "NBA Accreditation Certificate",
  state_pollution_noc: "State Pollution Control Board NOC",
  building_stability_certificate: "Building Structural Stability Certificate",
};

function normalizeDocumentKey(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]/g, "");
}

const NORMALIZED_CATALOG: Map<string, APHClauseReference> = (() => {
  const index = new Map<string, APHClauseReference>();
  for (const [key, reference] of Object.entries(APH_CLAUSE_CATALOG)) {
    index.set(normalizeDocumentKey(key), reference);
  }
  return index;
})();

/**
 * Resolve a clause reference for any spelling a caller might send: catalog label, snake_case
 * identifier, or a humanised display name.
 */
export function resolveClauseForDocument(documentId: string): APHClauseReference | undefined {
  if (!documentId) return undefined;
  const direct = APH_CLAUSE_CATALOG[documentId];
  if (direct) return direct;

  const mappedKey = DOCUMENT_ID_TO_CATALOG_KEY[documentId];
  if (mappedKey) {
    const mapped = APH_CLAUSE_CATALOG[mappedKey];
    if (mapped) return mapped;
  }

  const normalized = normalizeDocumentKey(documentId);
  const byNormalized = NORMALIZED_CATALOG.get(normalized);
  if (byNormalized) return byNormalized;

  // "fire_safety_certificate" -> "Fire Safety Certificate"
  const humanized = documentId.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  return APH_CLAUSE_CATALOG[humanized];
}

/** One line of the scoring derivation, surfaced to the user so the number is auditable. */
export interface ReadinessAdjustment {
  key: string;
  points: number;
  detail: string;
}

export interface ReadinessScoreResult {
  score: number; // 0 to 100
  baseScore: number;
  tier: "ready_nil_deficiency" | "conditional_minor_hearing" | "critical_deficiency_risk";
  label: string;
  summary: string;
  scoringVersion: string;
  breakdown: ReadinessAdjustment[];
  totalRequired: number;
  submittedCount: number;
  missingCount: number;
  expiredCount: number;
  expiringSoonCount: number;
  criticalZeroToleranceCount: number;
  findings: Array<{
    document: string;
    type: "missing" | "expired" | "expiring_soon";
    clause?: APHClauseReference;
    impact: string;
    suggestedAction: string;
  }>;
}

/** Weights are a product judgement, not a regulation. They are published in the UI. */
export const READINESS_WEIGHTS = {
  statutoryGap: -18,
  expiringSoon: -5,
  expiringSoonDays: 60,
} as const;

export const READINESS_SCORING_VERSION = "readiness-2026-10-30.1";

export function computeReadinessScore(
  required: string[],
  submitted: string[],
  expiryDates: Record<string, string>,
  today: Date = new Date()
): ReadinessScoreResult {
  const reqSet = new Set(required);
  const subSet = new Set(submitted);

  const missing = required.filter((doc) => !subSet.has(doc));
  const findings: ReadinessScoreResult["findings"] = [];

  let expiredCount = 0;
  let expiringSoonCount = 0;
  const statutoryGapDocuments: string[] = [];

  // Required documents that were not submitted.
  for (const doc of missing) {
    const clause = resolveClauseForDocument(doc);
    const isZeroTol =
      clause?.isStatutoryZeroTolerance ?? lookupDocumentGuidance(doc)?.isStatutoryZeroTolerance ?? false;
    if (isZeroTol) statutoryGapDocuments.push(doc);

    findings.push({
      document: doc,
      type: "missing",
      clause,
      impact: clause ? clause.deficiencyImpact : "Application checklist deficiency noted.",
      suggestedAction: clause ? clause.mitigationUndertaking : "Upload document before Scrutiny Committee cutoff.",
    });
  }

  // Submitted documents evaluated for expiry.
  for (const doc of submitted) {
    const expStr = expiryDates[doc];
    if (!expStr) continue;

    const expDate = new Date(expStr);
    if (Number.isNaN(expDate.getTime())) continue;
    const diffDays = Math.ceil((expDate.getTime() - today.getTime()) / (1000 * 60 * 60 * 24));
    const clause = resolveClauseForDocument(doc);
    const isZeroTol =
      clause?.isStatutoryZeroTolerance ?? lookupDocumentGuidance(doc)?.isStatutoryZeroTolerance ?? false;

    if (diffDays < 0) {
      expiredCount++;
      if (isZeroTol) statutoryGapDocuments.push(doc);
      findings.push({
        document: doc,
        type: "expired",
        clause,
        impact: clause ? clause.deficiencyImpact : `Document expired ${Math.abs(diffDays)} days ago.`,
        suggestedAction: clause ? clause.mitigationUndertaking : "Obtain immediate official renewal acknowledgment.",
      });
    } else if (diffDays <= READINESS_WEIGHTS.expiringSoonDays) {
      expiringSoonCount++;
      findings.push({
        document: doc,
        type: "expiring_soon",
        clause,
        impact: `Document expires in ${diffDays} days (during the active scrutiny window).`,
        suggestedAction: clause
          ? clause.mitigationUndertaking
          : "Request the renewal acknowledgement before the current certificate lapses.",
      });
    }
  }

  const total = required.length;
  const submittedRequired = submitted.filter((doc) => reqSet.has(doc)).length;
  const validRequiredSubmitted = Math.max(0, Math.min(total, submittedRequired) - expiredCount);
  const baseScore = total === 0 ? 0 : Math.round((validRequiredSubmitted / total) * 100);

  const breakdown: ReadinessAdjustment[] = [
    {
      key: "base",
      points: baseScore,
      detail: `${Math.min(validRequiredSubmitted, total)} of ${total} required documents valid and unexpired.`,
    },
    ...statutoryGapDocuments.map((doc) => ({
      key: `statutory:${doc}`,
      points: READINESS_WEIGHTS.statutoryGap,
      detail: `${doc}: statutory document missing or expired.`,
    })),
    ...(expiringSoonCount > 0
      ? [
          {
            key: "expiring-soon",
            points: expiringSoonCount * READINESS_WEIGHTS.expiringSoon,
            detail: `${expiringSoonCount} certificate(s) lapse within ${READINESS_WEIGHTS.expiringSoonDays} days.`,
          },
        ]
      : []),
  ];

  const rawScore = Math.max(
    0,
    Math.min(100, breakdown.reduce((sum, adjustment) => sum + adjustment.points, 0)),
  );

  const criticalCount = statutoryGapDocuments.length;

  let tier: ReadinessScoreResult["tier"] = "critical_deficiency_risk";
  let label = "Critical gaps — rectify before submission";
  let summary =
    "Statutory documents are missing or expired. Rectify these before the file goes to scrutiny.";

  if (rawScore >= 95 && criticalCount === 0 && expiredCount === 0 && expiringSoonCount === 0) {
    tier = "ready_nil_deficiency";
    label = "Checklist complete — no gaps detected";
    summary =
      "Every required document in this request is present with a valid supplied expiry date. This is a preliminary comparison, not an approval.";
  } else if (rawScore >= 65) {
    tier = "conditional_minor_hearing";
    label = "Conditional — rectify before scrutiny";
    summary =
      "The checklist is largely complete but needs affidavits, renewals or undertakings before the scrutiny window closes.";
  }

  return {
    score: rawScore,
    baseScore,
    tier,
    label,
    summary,
    scoringVersion: READINESS_SCORING_VERSION,
    breakdown,
    totalRequired: required.length,
    submittedCount: submitted.length,
    missingCount: missing.length,
    expiredCount,
    expiringSoonCount,
    criticalZeroToleranceCount: criticalCount,
    findings,
  };
}
