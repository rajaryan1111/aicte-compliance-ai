import { useState } from "react";
import {
  computeReadinessScore,
  type ReadinessScoreResult,
} from "@/lib/aicte-rules";
import { lookupDocumentGuidance } from "@/lib/compliance-guidance";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "./Card";
import { Button } from "./Button";
import {
  ShieldAlert,
  ShieldCheck,
  AlertTriangle,
  FileText,
  Copy,
  Check,
  ChevronDown,
  ChevronUp,
  Scale,
  Sparkles,
} from "lucide-react";

interface NilDeficiencyGapPredictorProps {
  requiredDocuments: string[];
  submittedDocuments: string[];
  expiryDates: Record<string, string>;
  institutionId?: string;
  className?: string;
}

export function NilDeficiencyGapPredictor({
  requiredDocuments,
  submittedDocuments,
  expiryDates,
  className = "",
}: NilDeficiencyGapPredictorProps) {
  const result: ReadinessScoreResult = computeReadinessScore(
    requiredDocuments,
    submittedDocuments,
    expiryDates
  );

  const [expandedIndex, setExpandedIndex] = useState<number | null>(0);
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null);

  const handleCopyUndertaking = (text: string, index: number) => {
    void navigator.clipboard.writeText(text);
    setCopiedIndex(index);
    setTimeout(() => setCopiedIndex(null), 2500);
  };

  const getScoreColor = () => {
    if (result.tier === "ready_nil_deficiency") return "text-success-text";
    if (result.tier === "conditional_minor_hearing") return "text-warning-text";
    return "text-error-text";
  };

  const getProgressBg = () => {
    if (result.tier === "ready_nil_deficiency") return "bg-success-text";
    if (result.tier === "conditional_minor_hearing") return "bg-warning-text";
    return "bg-error-text";
  };

  return (
    <Card className={`overflow-hidden border-border ${className}`}>
      <CardHeader className="border-b border-border bg-bg-1 pb-4">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <div className="flex items-center gap-2">
              <span className="flex h-6 w-6 items-center justify-center rounded-md bg-primary-500/15 text-accent-strong">
                <Sparkles className="h-3.5 w-3.5" />
              </span>
              <p className="text-xs font-bold uppercase tracking-wider text-text-muted">
                Preliminary readiness · APH-informed guidance
              </p>
            </div>
            <CardTitle className="mt-1 text-xl font-bold text-text-heading">
              Readiness &amp; statutory gap review
            </CardTitle>
            <CardDescription className="text-xs text-text-secondary">
              A deterministic index over this checklist, with the clause reference and mitigation undertaking for each gap. Not an AICTE rating.
            </CardDescription>
          </div>

          {/* Readiness Score Card */}
          <div className="flex items-center gap-3 rounded-xl border border-border bg-bg-2 p-3 sm:px-4">
            <div className="text-right">
              <span className="text-[11px] font-bold uppercase tracking-wider text-text-muted block">
                Readiness Score
              </span>
              <span className="text-xs font-medium text-text-secondary">
                Readiness index
              </span>
            </div>
            <div className="flex items-baseline gap-1">
              <span className={`text-3xl font-black tracking-tight ${getScoreColor()}`}>
                {result.score}%
              </span>
            </div>
          </div>
        </div>

        {/* Visual Progress Bar */}
        <div className="mt-4 space-y-1.5">
          <div className="h-2.5 w-full overflow-hidden rounded-full bg-bg-3 border border-border">
            <div
              className={`h-full transition-all duration-500 ease-out ${getProgressBg()}`}
              style={{ width: `${result.score}%` }}
              role="progressbar"
              aria-valuenow={result.score}
              aria-valuemin={0}
              aria-valuemax={100}
            />
          </div>
          <div className="flex items-center justify-between text-[11px] font-semibold text-text-muted">
            <span>Critical (0–64)</span>
            <span>Conditional (65–94)</span>
            <span>No gaps detected (95–100)</span>
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-6 p-5 sm:p-6">
        {/* Prediction Summary Banner */}
        <div
          className={`flex items-start gap-3.5 rounded-lg border p-4 text-sm ${
            result.tier === "ready_nil_deficiency"
              ? "border-success-border bg-success-bg/25 text-text-body"
              : result.tier === "conditional_minor_hearing"
              ? "border-warning-border bg-warning-bg/25 text-text-body"
              : "border-error-border bg-error-bg/25 text-text-body"
          }`}
        >
          {result.tier === "ready_nil_deficiency" ? (
            <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-success-text" />
          ) : result.tier === "conditional_minor_hearing" ? (
            <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-warning-text" />
          ) : (
            <ShieldAlert className="mt-0.5 h-5 w-5 shrink-0 text-error-text" />
          )}
          <div className="space-y-1">
            <h4 className="font-bold text-text-heading">{result.label}</h4>
            <p className="text-xs leading-relaxed text-text-secondary">{result.summary}</p>
          </div>
        </div>

        <details className="rounded-lg border border-border bg-bg-1 px-4 py-3">
          <summary className="cursor-pointer text-xs font-bold uppercase tracking-wider text-text-muted">
            How this index is calculated
          </summary>
          <ul className="mt-3 space-y-1.5 text-xs text-text-secondary">
            {result.breakdown.map((entry) => (
              <li key={entry.key} className="flex items-start justify-between gap-4 border-b border-border/60 pb-1.5 last:border-0">
                <span className="leading-relaxed">{entry.detail}</span>
                <span className={`shrink-0 font-mono font-semibold ${entry.points < 0 ? "text-error-text" : "text-text-heading"}`}>
                  {entry.points > 0 ? `+${entry.points}` : entry.points}
                </span>
              </li>
            ))}
            <li className="flex items-start justify-between gap-4 pt-1 font-semibold text-text-heading">
              <span>Index (clamped 0–100)</span>
              <span className="font-mono">{result.score}</span>
            </li>
          </ul>
          <p className="mt-3 text-[11px] leading-relaxed text-text-muted">
            Weighting is a product judgement, not a regulation (−18 per missing or expired statutory document, −5 per certificate expiring within 60 days).
            Scoring version <span className="font-mono">{result.scoringVersion}</span>. A gap in this checklist does not establish non-compliance, and a full checklist does not establish approval.
          </p>
        </details>

        {/* Identified Gaps & Statutory Clause Citations */}
        {result.findings.length > 0 ? (
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h4 className="text-xs font-bold uppercase tracking-wider text-text-muted">
                Statutory Deficiency Register ({result.findings.length} Flagged)
              </h4>
              <span className="text-[11px] text-text-secondary">
                Click any item to inspect AICTE Handbook Clause & Undertaking
              </span>
            </div>

            <div className="space-y-2.5">
              {result.findings.map((item, idx) => {
                const isExpanded = expandedIndex === idx;
                const isCritical = item.clause?.isStatutoryZeroTolerance;

                return (
                  <div
                    key={`${item.document}-${idx}`}
                    className="overflow-hidden rounded-lg border border-border bg-bg-1 transition-all"
                  >
                    <button
                      type="button"
                      onClick={() => setExpandedIndex(isExpanded ? null : idx)}
                      className="flex w-full items-center justify-between p-3.5 text-left transition-colors hover:bg-bg-2"
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        <span
                          className={`flex h-2 w-2 shrink-0 rounded-full ${
                            item.type === "missing"
                              ? "bg-error-text"
                              : item.type === "expired"
                              ? "bg-error-text"
                              : "bg-warning-text"
                          }`}
                        />
                        <div className="min-w-0">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="font-bold text-text-heading text-xs sm:text-sm truncate">
                              {lookupDocumentGuidance(item.document)?.label.en ?? item.document}
                            </span>
                            <span
                              className={`rounded px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider ${
                                item.type === "missing"
                                  ? "bg-error-bg text-error-text border border-error-border"
                                  : item.type === "expired"
                                  ? "bg-error-bg text-error-text border border-error-border"
                                  : "bg-warning-bg text-warning-text border border-warning-border"
                              }`}
                            >
                              {item.type.replace(/_/g, " ")}
                            </span>
                            {isCritical && (
                              <span className="rounded bg-bg-3 px-1.5 py-0.5 text-[10px] font-semibold text-text-muted">
                                Zero-Tolerance Norm
                              </span>
                            )}
                          </div>
                        </div>
                      </div>

                      <div className="flex items-center gap-2 shrink-0">
                        {item.clause && (
                          <span className="hidden sm:inline font-mono text-xs font-semibold text-accent-strong bg-bg-2 px-2 py-0.5 rounded border border-border">
                            {item.clause.clause}
                          </span>
                        )}
                        {isExpanded ? (
                          <ChevronUp className="h-4 w-4 text-text-muted" />
                        ) : (
                          <ChevronDown className="h-4 w-4 text-text-muted" />
                        )}
                      </div>
                    </button>

                    {isExpanded && (
                      <div className="border-t border-border bg-bg-2/60 p-4 space-y-3.5 animate-fade-in text-xs">
                        {item.clause && (
                          <div className="space-y-1">
                            <div className="flex items-center gap-1.5 text-text-muted font-bold uppercase tracking-wider text-[10px]">
                              <Scale className="h-3.5 w-3.5" />
                              <span>AICTE APH Reference: {item.clause.chapter} ({item.clause.clause})</span>
                            </div>
                            <p className="font-semibold text-text-heading">{item.clause.title}</p>
                            <p className="text-text-secondary leading-relaxed">{item.clause.requirement}</p>
                          </div>
                        )}

                        <div className="space-y-1">
                          <span className="font-bold uppercase tracking-wider text-[10px] text-error-text block">
                            Scrutiny Committee Impact:
                          </span>
                          <p className="text-text-body font-medium">{item.impact}</p>
                        </div>

                        {/* Mitigation Undertaking Format */}
                        <div className="rounded-md border border-border bg-bg-1 p-3 space-y-2">
                          <div className="flex items-center justify-between">
                            <div className="flex items-center gap-1.5 font-bold text-text-heading">
                              <FileText className="h-3.5 w-3.5 text-accent-strong" />
                              <span>Hearing Defense & Mitigation Undertaking:</span>
                            </div>
                            <Button
                              variant="ghost"
                              size="sm"
                              className="h-7 text-xs px-2"
                              onClick={() => handleCopyUndertaking(item.suggestedAction, idx)}
                            >
                              {copiedIndex === idx ? (
                                <>
                                  <Check className="h-3 w-3 text-success-text mr-1" />
                                  <span>Copied!</span>
                                </>
                              ) : (
                                <>
                                  <Copy className="h-3 w-3 mr-1" />
                                  <span>Copy Format</span>
                                </>
                              )}
                            </Button>
                          </div>
                          <p className="font-mono text-[11px] leading-relaxed text-text-secondary bg-bg-0 p-2.5 rounded border border-border select-all">
                            {item.suggestedAction}
                          </p>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        ) : (
          <div className="flex items-center gap-3 rounded-lg border border-success-border bg-success-bg/20 p-4 text-sm text-text-body">
            <ShieldCheck className="h-5 w-5 text-success-text shrink-0" />
            <p>
              <strong>No checklist gaps detected:</strong> every required document in this request was submitted and has no supplied expiry date in the past. A complete checklist is still not an AICTE approval.
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
