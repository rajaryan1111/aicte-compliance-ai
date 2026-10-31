import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, Save } from "lucide-react";
import { Button } from "@/components/Button";
import { Card, CardContent } from "@/components/Card";
import { Badge } from "@/components/Badge";
import { FormField, Input } from "@/components/FormField";
import { formatTimestamp } from "@/lib/utils";
import {
  createConsistencyFinding,
  getConsistencyCheck,
  listConsistencyFindings,
  updateConsistencyFinding,
  type ConsistencyCheck,
  type ConsistencyFinding,
  type ConsistencyStatus,
} from "@/lib/consistency-api";

export function StatusBadge({ status }: { status: ConsistencyStatus }) {
  if (status === "resolved") {
    return <Badge variant="success" dot>Resolved</Badge>;
  }
  if (status === "discrepancy_detected") {
    return <Badge variant="warning" dot>Discrepancy detected</Badge>;
  }
  return <Badge variant="info" dot>Pending</Badge>;
}

function formatConfidence(value: number | null) {
  if (value === null) return "Not recorded";
  return `${Math.round(value * 100)}%`;
}

function EvidenceTable({ evidence }: { evidence: Record<string, unknown> }) {
  const entries = Object.entries(evidence);
  if (entries.length === 0) return null;
  return (
    <dl className="mt-2 overflow-hidden rounded-md border border-border bg-bg-3 text-xs">
      {entries.map(([key, value]) => (
        <div key={key} className="grid grid-cols-[minmax(0,32%)_minmax(0,68%)] border-b border-border last:border-b-0">
          <dt className="px-3 py-1.5 font-mono font-semibold break-words text-text-secondary">{key}</dt>
          <dd className="px-3 py-1.5 break-words text-text-body">
            {typeof value === "string" ? value : <code>{JSON.stringify(value)}</code>}
          </dd>
        </div>
      ))}
    </dl>
  );
}

// Detail view for one persisted consistency check: check summary, its findings
// with supporting evidence, the resolve/reopen actions and the add-finding
// form. All server interactions go through @/lib/consistency-api.
export function ConsistencyDetailView({
  token,
  detailId,
}: {
  token: string | null;
  detailId: number | null;
}) {
  const [check, setCheck] = useState<ConsistencyCheck | null>(null);
  const [findings, setFindings] = useState<ConsistencyFinding[]>([]);
  const [detailLoading, setDetailLoading] = useState(true);
  const [detailError, setDetailError] = useState("");
  const [findingActionError, setFindingActionError] = useState("");
  const [resolvedBusy, setResolvedBusy] = useState<number | null>(null);

  // ── Add-finding form ──
  const [fieldName, setFieldName] = useState("");
  const [value1, setValue1] = useState("");
  const [value2, setValue2] = useState("");
  const [severity, setSeverity] = useState("");
  const [confidence, setConfidence] = useState("");
  const [findingDescription, setFindingDescription] = useState("");
  const [findingErrors, setFindingErrors] = useState<Record<string, string>>({});
  const [addingFinding, setAddingFinding] = useState(false);

  const applyDetailResults = (
    checkResult: Awaited<ReturnType<typeof getConsistencyCheck>>,
    findingsResult: Awaited<ReturnType<typeof listConsistencyFindings>>,
  ) => {
    setDetailLoading(false);
    if (checkResult.ok) {
      setCheck(checkResult.data);
      setDetailError("");
    } else {
      setCheck(null);
      setDetailError(Object.values(checkResult.errors)[0] || "Unable to load this consistency check.");
    }
    if (findingsResult.ok) {
      setFindings(findingsResult.data);
    } else {
      setFindings([]);
      setDetailError(
        (prev) => prev || Object.values(findingsResult.errors)[0] || "Unable to load findings for this check.",
      );
    }
  };

  useEffect(() => {
    if (!token || detailId === null) return;
    let cancelled = false;
    void Promise.all([
      getConsistencyCheck(detailId, token),
      listConsistencyFindings(detailId, token),
    ]).then(([checkResult, findingsResult]) => {
      if (!cancelled) applyDetailResults(checkResult, findingsResult);
    });
    return () => {
      cancelled = true;
    };
  }, [detailId, token]);

  async function refreshDetail() {
    if (!token || detailId === null) return;
    const [checkResult, findingsResult] = await Promise.all([
      getConsistencyCheck(detailId, token),
      listConsistencyFindings(detailId, token),
    ]);
    applyDetailResults(checkResult, findingsResult);
  }

  async function handleAddFinding(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || detailId === null || check === null) return;
    setFindingErrors({});
    setFindingActionError("");
    const parsedConfidence = confidence.trim() === "" ? null : Number(confidence);
    if (parsedConfidence !== null && !(parsedConfidence >= 0 && parsedConfidence <= 1)) {
      setFindingErrors({ confidence: "Confidence must be between 0 and 1." });
      return;
    }
    setAddingFinding(true);
    const result = await createConsistencyFinding(
      {
        consistency_check_id: check.id,
        field_name: fieldName,
        value_1: value1,
        value_2: value2,
        severity: severity.trim() || "medium",
        confidence: parsedConfidence,
        description: findingDescription,
        evidence: null,
      },
      token,
    );
    setAddingFinding(false);
    if (result.ok) {
      setFieldName("");
      setValue1("");
      setValue2("");
      setSeverity("");
      setConfidence("");
      setFindingDescription("");
      await refreshDetail();
    } else {
      setFindingErrors(
        Object.keys(result.errors).length > 0 ? result.errors : { _form: "The finding could not be recorded." },
      );
    }
  }

  async function handleToggleResolved(finding: ConsistencyFinding) {
    if (!token) return;
    setFindingActionError("");
    setResolvedBusy(finding.id);
    const result = await updateConsistencyFinding(
      finding.id,
      { resolved: !finding.resolved },
      token,
    );
    setResolvedBusy(null);
    if (!result.ok) {
      setFindingActionError(Object.values(result.errors)[0] || "The update was not saved.");
      return;
    }
    await refreshDetail();
  }

  if (detailLoading) {
    return (
      <p className="py-12 text-center text-sm text-text-secondary" role="status">
        Loading consistency check…
      </p>
    );
  }
  if (!check) {
    return (
      <div className="mx-auto max-w-3xl space-y-5">
        <Link to="/consistency" className="inline-flex items-center gap-2 text-sm text-text-secondary underline underline-offset-4">
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          Back to consistency checks
        </Link>
        <p className="text-sm text-error-text" role="alert">{detailError || "This consistency check was not found."}</p>
      </div>
    );
  }
  const unresolved = findings.filter((finding) => !finding.resolved).length;
  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <Link to="/consistency" className="inline-flex items-center gap-2 text-sm text-text-secondary underline underline-offset-4">
        <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        Back to consistency checks
      </Link>
      <header className="space-y-2">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-bold tracking-tight text-text-heading">{check.check_name}</h1>
          <StatusBadge status={check.status} />
        </div>
        <p className="text-sm text-text-secondary">
          {check.description || "No description recorded."}
        </p>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-text-secondary">
          <span>Application <strong className="text-text-heading">#{check.application_id}</strong></span>
          {check.related_field && <span>Compared field: <strong className="text-text-heading">{check.related_field}</strong></span>}
          <span>Created {formatTimestamp(check.created_at)}</span>
          <span>·</span>
          <span>{unresolved === 0 ? "No unresolved discrepancies" : `${unresolved} unresolved finding${unresolved === 1 ? "" : "s"}`}</span>
        </div>
      </header>

      {detailError && <p className="text-sm text-error-text" role="alert">{detailError}</p>}
      {findingActionError && <p className="text-sm text-error-text" role="alert">{findingActionError}</p>}

      <section aria-label="Recorded findings" className="space-y-3">
        <h2 className="text-lg font-semibold text-text-heading">Findings and evidence</h2>
        {findings.length === 0 ? (
          <Card>
            <CardContent className="p-6 text-center text-sm text-text-secondary">
              No findings recorded yet. Add a comparison below once two authoritative values have been checked.
            </CardContent>
          </Card>
        ) : (
          findings.map((finding) => (
            <Card key={finding.id} padding="md">
              <CardContent className="space-y-3 p-5">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="flex flex-wrap items-center gap-2.5">
                    <h3 className="font-mono text-sm font-semibold text-text-heading">{finding.field_name}</h3>
                    <Badge variant="error" size="sm">{finding.severity}</Badge>
                    {finding.resolved ? <Badge variant="success" size="sm">Resolved</Badge> : <Badge variant="neutral" size="sm">Unresolved</Badge>}
                  </div>
                  <Button
                    variant={finding.resolved ? "secondary" : "success"}
                    size="sm"
                    disabled={resolvedBusy === finding.id}
                    onClick={() => handleToggleResolved(finding)}
                  >
                    {finding.resolved ? "Reopen finding" : "Mark resolved"}
                  </Button>
                </div>
                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="rounded-md border border-border bg-bg-2 p-3 text-sm">
                    <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">Value 1</p>
                    <p className="mt-1 break-words text-text-heading">{finding.value_1 || "—"}</p>
                  </div>
                  <div className="rounded-md border border-border bg-bg-2 p-3 text-sm">
                    <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">Value 2</p>
                    <p className="mt-1 break-words text-text-heading">{finding.value_2 || "—"}</p>
                  </div>
                </div>
                <p className="text-sm leading-relaxed text-text-body">{finding.description}</p>
                <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-text-secondary">
                  <span>Severity: <strong className="text-text-heading">{finding.severity}</strong></span>
                  <span>Confidence: {formatConfidence(finding.confidence)}</span>
                  <span>Recorded {formatTimestamp(finding.created_at)}</span>
                </div>
                {finding.evidence && <EvidenceTable evidence={finding.evidence} />}
              </CardContent>
            </Card>
          ))
        )}
      </section>

      <Card>
        <CardContent className="space-y-4 p-5">
          <h2 className="text-lg font-semibold text-text-heading">Record a comparison finding</h2>
          <p className="text-sm text-text-secondary">
            Persistently record two compared values with severity, confidence and supporting evidence for the audit trail.
          </p>
          {Object.keys(findingErrors).length > 0 && (
            <ul className="list-inside list-disc rounded-md border border-error-border bg-error-bg/20 p-3 text-sm text-error-text" role="alert">
              {Object.entries(findingErrors).map(([key, message]) => (
                <li key={key}>{message}</li>
              ))}
            </ul>
          )}
          <form className="grid gap-4" onSubmit={(event) => { void handleAddFinding(event); }}>
            <div className="grid gap-4 sm:grid-cols-2">
              <FormField label="Field compared" required>
                <Input name="field_name" required value={fieldName} onChange={(e) => setFieldName(e.target.value)} placeholder="e.g. approved_intake" />
              </FormField>
              <FormField label="Severity" hint="Small free-form tag, max 30 characters." required>
                <Input name="severity" required value={severity} onChange={(e) => setSeverity(e.target.value)} placeholder="e.g. high" />
              </FormField>
              <FormField label="Value 1" required>
                <Input name="value_1" value={value1} onChange={(e) => setValue1(e.target.value)} />
              </FormField>
              <FormField label="Value 2" required>
                <Input name="value_2" value={value2} onChange={(e) => setValue2(e.target.value)} />
              </FormField>
              <FormField label="Confidence (0–1)" hint="Optional. Example: 0.85">
                <Input name="confidence" inputMode="decimal" value={confidence} onChange={(e) => setConfidence(e.target.value)} />
              </FormField>
            </div>
            <FormField label="Description" required hint="Explain the discrepancy or confirmation.">
              <textarea
                name="description"
                required
                rows={3}
                value={findingDescription}
                onChange={(e) => setFindingDescription(e.target.value)}
                className="app-control w-full rounded-lg border border-border bg-bg-3 p-3 text-sm text-text-body focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/30"
              />
            </FormField>
            <div>
              <Button type="submit" loading={addingFinding} leftIcon={<Save className="h-4 w-4" />}>Save finding</Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}