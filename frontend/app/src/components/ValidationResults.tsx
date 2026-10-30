import { useState } from "react";
import { cn } from "@/lib/utils";
import { ArrowLeft, AlertTriangle, RefreshCw, Shield, FileX2, Clock, FileText, CheckCircle2, ListChecks, Printer, Download, Sparkles } from "lucide-react";
import { Card, CardContent } from "./Card";
import { DocumentChecklist } from "./DocumentChecklist";
import { FindingsTable } from "./FindingsTable";
import { Alert } from "./Alert";
import { Button } from "./Button";
import { formatTimestamp } from "@/lib/utils";
import { EmptyState } from "./EmptyState";
import { RequestComparison } from "./RequestComparison";
import { NilDeficiencyGapPredictor } from "./NilDeficiencyGapPredictor";
import { RemediationActionPlan } from "./RemediationActionPlan";
import { ExpiryWatchdogMatrix } from "./ExpiryWatchdogMatrix";
import { ScrutinyDossierModal } from "./ScrutinyDossierModal";
import { RegulatoryScrutinyWorkbench } from "./RegulatoryScrutinyWorkbench";
import type { ValidationRequest, ValidationResponse } from "@/lib/api";
import { downloadValidationCsv } from "@/lib/report";

interface ValidationResultsProps {
  data: ValidationResponse;
  request: ValidationRequest;
  onReset: () => void;
}

export function ValidationResults({ data, request, onReset }: ValidationResultsProps) {
  const [reportGeneratedAt, setReportGeneratedAt] = useState<string | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);
  const [isDossierOpen, setIsDossierOpen] = useState(false);
  const passed = data.status === "preliminary_checks_passed";

  const missingCount = data.missing_documents.length;
  const expiredCount = data.expired_documents.length;
  const totalFindings = data.findings.length;
  const reviewDocuments = Array.from(new Set([...data.missing_documents, ...data.expired_documents]));

  return (
    <div className="validation-results animate-fade-in space-y-6">
      <div className="print-only mb-6">
        <p className="text-sm font-semibold uppercase tracking-wide">AICTE Compliance AI</p>
        <h1 className="mt-1 text-2xl font-bold">Preliminary validation summary</h1>
        <p className="mt-2">Validation scope: {data.validation_scope}</p>
        <p>Checked at: <time dateTime={data.checked_at}>{data.checked_at}</time></p>
        {reportGeneratedAt && <p>Report generated at: <time dateTime={reportGeneratedAt}>{reportGeneratedAt}</time></p>}
      </div>

      <div className="no-print flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <Button variant="ghost" size="sm" leftIcon={<ArrowLeft className="h-4 w-4" />} onClick={onReset}>
          Back to Form
        </Button>
        <div className="flex flex-wrap items-center gap-3">
          <Button
            variant="primary"
            size="sm"
            onClick={() => setIsDossierOpen(true)}
            leftIcon={<Sparkles className="h-4 w-4" />}
          >
            Download Scrutiny Dossier
          </Button>
          <div className={cn(
            "flex items-center gap-3 border px-4 py-2 rounded-md",
            passed ? "border-success-border bg-success-bg/40 text-success-text" : "border-warning-border bg-warning-bg/40 text-warning-text"
          )} role="status" aria-live="polite">
            {passed ? <CheckCircle2 className="h-5 w-5 shrink-0" aria-hidden="true" /> : <AlertTriangle className="h-5 w-5 shrink-0" aria-hidden="true" />}
            <span className="font-bold text-xs">{passed ? "Checks Passed" : `${totalFindings} Finding(s)`}</span>
          </div>
        </div>
      </div>

      {/* Flagship Feature 1: AICTE Nil-Deficiency Smart Gap Predictor */}
      <NilDeficiencyGapPredictor
        requiredDocuments={request.required_documents}
        submittedDocuments={request.submitted_documents}
        expiryDates={request.expiry_dates}
        institutionId={data.institution_id}
      />

      {/* Feature 3: Expiry Watchdog & Timeline Matrix */}
      {Object.keys(request.expiry_dates).length > 0 && (
        <ExpiryWatchdogMatrix
          expiryDates={request.expiry_dates}
          submittedDocuments={request.submitted_documents}
          institutionId={data.institution_id}
        />
      )}

      
      {/* Flagship Feature: AICTE Regulatory Scrutiny Decision-Support Workbench */}
      <RegulatoryScrutinyWorkbench
        institutionId={data.institution_id}
        applicationType={data.application_type}
        submittedDocuments={request.submitted_documents}
        expiryDates={request.expiry_dates}
      />

      {/* Official Scrutiny Dossier Package Modal */}
      <ScrutinyDossierModal
        isOpen={isDossierOpen}
        onClose={() => setIsDossierOpen(false)}
        institutionId={data.institution_id}
        applicationType={data.application_type}
        requiredDocuments={request.required_documents}
        submittedDocuments={request.submitted_documents}
        expiryDates={request.expiry_dates}
        checkedAt={data.checked_at}
      />

      <Card variant="feature">
        <CardContent className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard
              label="Institution"
              value={data.institution_id}
              icon={<Shield className="h-5 w-5 text-primary-400" />}
            />
            <StatCard
              label="Application Type"
              value={data.application_type.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())}
              icon={<AlertTriangle className="h-5 w-5 text-accent-500" />}
            />
            <StatCard
              label="Checked At"
              value={formatTimestamp(data.checked_at)}
              icon={<Clock className="h-5 w-5 text-text-muted" />}
            />
            <StatCard
              label="Source"
              value={data.source}
              icon={<FileText className="h-5 w-5 text-text-muted" />}
              valueClassName="text-sm font-mono leading-5"
            />
          </div>

          <div className="grid gap-4 border-t border-border pt-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard
              label="Required Documents"
              value={request.required_documents.length}
              icon={<ListChecks className="h-5 w-5 text-primary-400" />}
            />
            <StatCard
              label="Submitted Documents"
              value={request.submitted_documents.length}
              icon={<FileText className="h-5 w-5 text-primary-400" />}
            />
            <StatCard
              label="Missing Documents"
              value={missingCount}
              icon={<FileX2 className="h-6 w-6 text-error-text" />}
              highlight={missingCount > 0}
              tone="error"
            />
            <StatCard
              label="Expired Documents"
              value={expiredCount}
              icon={<Clock className="h-6 w-6 text-warning-text" />}
              highlight={expiredCount > 0}
              tone="warning"
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          <RequestComparison
            request={request}
            missingDocuments={data.missing_documents}
            expiredDocumentCount={expiredCount}
          />
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          <div className="mb-4 flex items-center gap-2">
            <ListChecks className="h-5 w-5 text-primary-400" aria-hidden="true" />
            <h3 className="text-lg font-semibold text-text-heading">{reviewDocuments.length ? "Documents to Review" : "Document Checklist"}</h3>
          </div>
          {reviewDocuments.length > 0 && (
            <p className="mb-4 text-sm text-text-muted">
              This API response lists flagged documents, so the checklist below focuses on items that need review.
            </p>
          )}
          {reviewDocuments.length ? (
            <DocumentChecklist
              requiredDocs={reviewDocuments}
              submittedDocs={data.expired_documents}
              expiryDates={{}}
              missingDocs={data.missing_documents}
              expiredDocs={data.expired_documents}
            />
          ) : (
            <EmptyState
              icon={CheckCircle2}
              title="No document issues found"
              description="The preliminary checklist and expiry checks passed for this request."
              className="py-8"
            />
          )}
        </CardContent>
      </Card>

      <Card>
        <CardContent className="space-y-4">
          <div>
            <h3 className="text-lg font-semibold text-text-heading">Findings review</h3>
            <p className="mt-1 text-sm leading-relaxed text-text-secondary">
              A missing finding means a required name is absent from the submitted list. An expired finding means a supplied expiry date is before the server’s current UTC date.
            </p>
          </div>
          <dl className="grid gap-3 border-y border-border py-4 sm:grid-cols-2 lg:grid-cols-4">
            <div><dt className="text-xs font-semibold uppercase tracking-wide text-text-muted">API status</dt><dd className="mt-1 break-words text-sm text-text-heading">{data.status}</dd></div>
            <div><dt className="text-xs font-semibold uppercase tracking-wide text-text-muted">Validation scope</dt><dd className="mt-1 break-words text-sm text-text-heading">{data.validation_scope}</dd></div>
            <div><dt className="text-xs font-semibold uppercase tracking-wide text-text-muted">Checked at</dt><dd className="mt-1 break-words text-sm text-text-heading"><time dateTime={data.checked_at}>{data.checked_at}</time></dd></div>
            <div><dt className="text-xs font-semibold uppercase tracking-wide text-text-muted">Source</dt><dd className="mt-1 break-words font-mono text-xs text-text-heading">{data.source}</dd></div>
          </dl>
          {totalFindings > 0 ? (
            <FindingsTable findings={data.findings} />
          ) : (
            <div className="border-l-2 border-info-border bg-info-bg/40 p-4" role="status">
              <h4 className="font-semibold text-text-heading">No findings were returned</h4>
              <p className="mt-1 text-sm leading-relaxed text-text-secondary">This describes this caller-supplied comparison only. It is not an official compliance determination.</p>
            </div>
          )}
        </CardContent>
      </Card>

      <RemediationActionPlan request={request} response={data} />

      <Alert variant="info" title="Notice" icon={<Shield className="h-5 w-5" />}>
        {data.notice}
      </Alert>

      <div className="no-print flex flex-wrap justify-end gap-3 pt-4">
        <Button
          variant="primary"
          onClick={() => setIsDossierOpen(true)}
          leftIcon={<Sparkles className="h-4 w-4" />}
        >
          Download Scrutiny Dossier
        </Button>
        <Button variant="secondary" onClick={() => {
          setExportError(null);
          try {
            downloadValidationCsv(request, data);
          } catch {
            setExportError("The CSV could not be generated. The validation result is still available on this page.");
          }
        }} leftIcon={<Download className="h-4 w-4" />}>
          Download CSV
        </Button>
        <Button variant="secondary" onClick={() => {
          setReportGeneratedAt(new Date().toISOString());
          window.setTimeout(() => window.print(), 0);
        }} leftIcon={<Printer className="h-4 w-4" />}>
          Print Summary
        </Button>
        <Button onClick={onReset} leftIcon={<RefreshCw className="h-4 w-4" />}>
          Start New Validation
        </Button>
      </div>
      {exportError && <p className="no-print text-right text-sm text-error-text" role="alert">{exportError}</p>}
      <p className="no-print text-right text-xs text-text-muted">
        CSV cells are quoted and formula-leading values are prefixed with an apostrophe for spreadsheet safety.
      </p>
    </div>
  );
}

function StatCard({
  label,
  value,
  icon,
  highlight = false,
  tone = "error",
  valueClassName,
}: {
  label: string;
  value: string | number;
  icon: React.ReactNode;
  highlight?: boolean;
  tone?: "error" | "warning" | "info";
  valueClassName?: string;
}) {
  const toneStyles = {
    error: "border-error-border/50 text-error-text",
    warning: "border-warning-border/50 text-warning-text",
    info: "border-info-border text-info-text",
  };

  return (
    <div
      className={cn(
        "p-4 bg-bg-3/50 border border-border rounded-xl transition-all",
        highlight && toneStyles[tone]
      )}
    >
      <div className="flex items-center gap-3 mb-2">
        <div className="p-2 bg-bg-2 rounded-lg">{icon}</div>
        <span className="text-xs font-medium text-text-secondary uppercase tracking-wider">{label}</span>
      </div>
      <div className={cn("break-words text-3xl font-bold tracking-tight", highlight ? toneStyles[tone].split(" ")[1] : "text-text-heading", valueClassName)}>
        {value}
      </div>
    </div>
  );
}
