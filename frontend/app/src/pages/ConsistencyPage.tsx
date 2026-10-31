import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import {
  ArrowLeft,
  Clock3,
  FileSearch,
  ListChecks,
  Plus,
  Save,
  ShieldAlert,
} from "lucide-react";
import { Button } from "@/components/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/Card";
import { useAuth } from "@/components/useAuth";
import {
  createConsistencyCheck,
  createConsistencyFinding,
  fetchApplicationRecord,
  fetchApplications,
  fetchConsistencyCheck,
  fetchConsistencyChecks,
  fetchConsistencyFindings,
  updateConsistencyFinding,
  type ApiResult,
  type ApplicationRecord,
  type ConsistencyCheck,
  type ConsistencyFinding,
  type ConsistencyFindingUpdate,
} from "@/lib/api";

function formatDate(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.valueOf())
    ? "Date unavailable"
    : new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(date);
}

function statusLabel(status: ConsistencyCheck["status"]) {
  if (status === "discrepancy_detected") return "Discrepancy recorded";
  return status === "resolved" ? "Resolved" : "Pending review";
}

function statusClass(status: ConsistencyCheck["status"]) {
  if (status === "discrepancy_detected") return "border-warning-border bg-warning-bg/30 text-warning-text";
  return status === "resolved"
    ? "border-success-border bg-success-bg/30 text-success-text"
    : "border-border bg-bg-2 text-text-secondary";
}

function firstError<T>(result: ApiResult<T>, fallback: string) {
  return result.ok ? fallback : Object.values(result.errors)[0] || fallback;
}

function FindingCard({
  finding,
  onUpdate,
}: {
  finding: ConsistencyFinding;
  onUpdate: (findingId: number, payload: ConsistencyFindingUpdate) => Promise<void>;
}) {
  const [expanded, setExpanded] = useState(false);
  const [severity, setSeverity] = useState(finding.severity);
  const [description, setDescription] = useState(finding.description);
  const [evidenceText, setEvidenceText] = useState(
    finding.evidence ? JSON.stringify(finding.evidence, null, 2) : "",
  );
  const [resolved, setResolved] = useState(finding.resolved);
  const [evidenceError, setEvidenceError] = useState("");
  const [saving, setSaving] = useState(false);

  async function saveFinding(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setEvidenceError("");
    let evidence: Record<string, unknown> | null = null;
    if (evidenceText.trim()) {
      try {
        const parsed: unknown = JSON.parse(evidenceText);
        if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
          throw new Error("Evidence must be a JSON object.");
        }
        evidence = parsed as Record<string, unknown>;
      } catch {
        setEvidenceError("Enter valid JSON object evidence, or leave it blank.");
        return;
      }
    }
    if (!severity.trim() || !description.trim()) {
      setEvidenceError("Severity and description are required.");
      return;
    }
    setSaving(true);
    await onUpdate(finding.id, { severity: severity.trim(), description: description.trim(), evidence, resolved });
    setSaving(false);
  }

  return (
    <Card>
      <CardContent className="space-y-4 p-5">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0 space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="break-words text-base font-semibold text-text-heading">{finding.field_name}</h3>
              <span className="rounded border border-border bg-bg-2 px-2 py-0.5 text-xs text-text-secondary">
                {finding.severity}
              </span>
              <span className={finding.resolved
                ? "rounded border border-success-border bg-success-bg/30 px-2 py-0.5 text-xs text-success-text"
                : "rounded border border-warning-border bg-warning-bg/30 px-2 py-0.5 text-xs text-warning-text"}>
                {finding.resolved ? "Resolved" : "Open"}
              </span>
            </div>
            <p className="text-sm leading-relaxed text-text-body">{finding.description}</p>
            <p className="text-xs text-text-muted">Finding code is not supplied by this API.</p>
          </div>
          <Button type="button" variant="secondary" size="sm" onClick={() => setExpanded((value) => !value)}>
            {expanded ? "Close details" : "Finding details"}
          </Button>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <div className="rounded-md border border-border bg-bg-2 p-3">
            <p className="text-xs font-semibold text-text-secondary">Compared value 1</p>
            <p className="mt-1 break-words font-mono text-sm text-text-body">{finding.value_1 || "(empty)"}</p>
          </div>
          <div className="rounded-md border border-border bg-bg-2 p-3">
            <p className="text-xs font-semibold text-text-secondary">Compared value 2</p>
            <p className="mt-1 break-words font-mono text-sm text-text-body">{finding.value_2 || "(empty)"}</p>
          </div>
        </div>

        {expanded && (
          <div className="space-y-4 border-t border-border pt-4">
            <dl className="grid gap-3 text-sm sm:grid-cols-2">
              <div><dt className="text-xs font-semibold text-text-secondary">Related field</dt><dd className="mt-1 break-words text-text-body">{finding.field_name}</dd></div>
              <div><dt className="text-xs font-semibold text-text-secondary">Confidence</dt><dd className="mt-1 text-text-body">{finding.confidence === null ? "Not provided" : `${Math.round(finding.confidence * 100)}%`}</dd></div>
              <div><dt className="text-xs font-semibold text-text-secondary">Created</dt><dd className="mt-1 text-text-body">{formatDate(finding.created_at)}</dd></div>
              <div><dt className="text-xs font-semibold text-text-secondary">Updated</dt><dd className="mt-1 text-text-body">{formatDate(finding.updated_at)}</dd></div>
            </dl>
            <div>
              <h4 className="text-xs font-semibold text-text-secondary">Evidence</h4>
              <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-words rounded-md border border-border bg-bg-2 p-3 font-mono text-xs text-text-body">
                {finding.evidence ? JSON.stringify(finding.evidence, null, 2) : "No evidence supplied."}
              </pre>
            </div>
            <form className="grid gap-4 rounded-lg border border-border bg-bg-1 p-4" onSubmit={(event) => { void saveFinding(event); }}>
              <h4 className="text-sm font-semibold text-text-heading">Update finding</h4>
              <label className="grid gap-1.5 text-sm text-text-secondary">
                Severity
                <input className="app-control min-h-10 rounded-md border border-border bg-bg-1 px-3 text-text-body" value={severity} maxLength={30} onChange={(event) => setSeverity(event.target.value)} required />
              </label>
              <label className="grid gap-1.5 text-sm text-text-secondary">
                Description
                <textarea className="app-control min-h-20 rounded-md border border-border bg-bg-1 p-3 text-text-body" value={description} maxLength={4000} onChange={(event) => setDescription(event.target.value)} required />
              </label>
              <label className="grid gap-1.5 text-sm text-text-secondary">
                Evidence JSON (object)
                <textarea className="app-control min-h-28 rounded-md border border-border bg-bg-1 p-3 font-mono text-xs text-text-body" value={evidenceText} onChange={(event) => setEvidenceText(event.target.value)} />
              </label>
              <label className="flex items-center gap-2 text-sm text-text-body">
                <input type="checkbox" checked={resolved} onChange={(event) => setResolved(event.target.checked)} />
                Mark as resolved
              </label>
              {evidenceError && <p className="text-sm text-error-text" role="alert">{evidenceError}</p>}
              <Button type="submit" loading={saving} leftIcon={<Save className="h-4 w-4" />}>Save finding</Button>
            </form>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export function ConsistencyPage() {
  const { checkId: rawCheckId } = useParams();
  const checkId = rawCheckId ? Number(rawCheckId) : null;
  const { session, signOut } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const token = session?.access_token;
  const viewKey = checkId === null ? "list" : `check-${checkId}`;
  const [loadedView, setLoadedView] = useState("");

  const [applications, setApplications] = useState<ApplicationRecord[]>([]);
  const [checks, setChecks] = useState<ConsistencyCheck[]>([]);
  const [check, setCheck] = useState<ConsistencyCheck | null>(null);
  const [application, setApplication] = useState<ApplicationRecord | null>(null);
  const [findings, setFindings] = useState<ConsistencyFinding[]>([]);
  const loading = loadedView !== viewKey;
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState(
    (location.state as { notice?: string } | null)?.notice ?? "",
  );
  const [applicationId, setApplicationId] = useState("");
  const [checkName, setCheckName] = useState("");
  const [checkDescription, setCheckDescription] = useState("");
  const [relatedField, setRelatedField] = useState("");
  const [findingField, setFindingField] = useState("");
  const [valueOne, setValueOne] = useState("");
  const [valueTwo, setValueTwo] = useState("");
  const [severity, setSeverity] = useState("medium");
  const [confidence, setConfidence] = useState("");
  const [findingDescription, setFindingDescription] = useState("");
  const [findingEvidence, setFindingEvidence] = useState("");

  const handleUnauthorized = useCallback(async <T,>(result: ApiResult<T>) => {
    if (result.ok || result.status !== 401) return false;
    await signOut();
    navigate("/signin", { replace: true, state: { from: location.pathname } });
    return true;
  }, [location.pathname, navigate, signOut]);

  useEffect(() => {
    let active = true;
    async function load() {
      setError("");
      if (!token) {
        setLoadedView(viewKey);
        return;
      }

      if (checkId === null) {
        const [applicationsResult, checksResult] = await Promise.all([
          fetchApplications(token),
          fetchConsistencyChecks(token),
        ]);
        if (!active) return;
        if (!applicationsResult.ok && applicationsResult.status === 401) {
          await handleUnauthorized(applicationsResult);
          return;
        }
        if (!checksResult.ok && checksResult.status === 401) {
          await handleUnauthorized(checksResult);
          return;
        }
        if (!applicationsResult.ok || !checksResult.ok) {
          setError(!applicationsResult.ok
            ? firstError(applicationsResult, "Unable to load applications.")
            : firstError(checksResult, "Unable to load consistency checks."));
        } else {
          setApplications(applicationsResult.data.items);
          setChecks(checksResult.data);
        }
        setLoadedView(viewKey);
        return;
      }

      if (!Number.isInteger(checkId) || checkId <= 0) {
        setCheck(null);
        setError("This consistency record was not found or access is denied.");
        setLoadedView(viewKey);
        return;
      }

      const [checkResult, findingsResult] = await Promise.all([
        fetchConsistencyCheck(checkId, token),
        fetchConsistencyFindings(checkId, token),
      ]);
      if (!active) return;
      if (!checkResult.ok && checkResult.status === 401) {
        await handleUnauthorized(checkResult);
        return;
      }
      if (!findingsResult.ok && findingsResult.status === 401) {
        await handleUnauthorized(findingsResult);
        return;
      }
      if (!checkResult.ok || !findingsResult.ok) {
        setCheck(null);
        setError(!checkResult.ok
          ? firstError(checkResult, "Unable to load this consistency check.")
          : firstError(findingsResult, "Unable to load findings."));
        setLoadedView(viewKey);
        return;
      }
      setCheck(checkResult.data);
      setFindings(findingsResult.data);
      const applicationResult = await fetchApplicationRecord(checkResult.data.application_id, token);
      if (!active) return;
      if (!applicationResult.ok && applicationResult.status === 401) {
        await handleUnauthorized(applicationResult);
        return;
      }
      if (applicationResult.ok) setApplication(applicationResult.data);
      else setError(firstError(applicationResult, "Application details are unavailable."));
      setLoadedView(viewKey);
    }
    void load();
    return () => { active = false; };
  }, [checkId, handleUnauthorized, token, viewKey]);

  async function submitCheck(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token) return;
    setSaving(true);
    setError("");
    const result = await createConsistencyCheck({
      application_id: Number(applicationId),
      check_name: checkName.trim(),
      description: checkDescription.trim() || null,
      related_field: relatedField.trim() || null,
    }, token);
    setSaving(false);
    if (await handleUnauthorized(result)) return;
    if (!result.ok) {
      setError(firstError(result, "Unable to create this consistency check."));
      return;
    }
    navigate(`/consistency/${result.data.id}`, { state: { notice: "Consistency check created." } });
  }

  async function submitFinding(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !check) return;
    setSaving(true);
    setError("");
    let evidence: Record<string, unknown> | null = null;
    if (findingEvidence.trim()) {
      try {
        const parsed: unknown = JSON.parse(findingEvidence);
        if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) throw new Error();
        evidence = parsed as Record<string, unknown>;
      } catch {
        setError("Evidence must be a valid JSON object, or leave it blank.");
        setSaving(false);
        return;
      }
    }
    const confidenceValue = confidence.trim() ? Number(confidence) : null;
    if (confidenceValue !== null && (!Number.isFinite(confidenceValue) || confidenceValue < 0 || confidenceValue > 1)) {
      setError("Confidence must be a number from 0 to 1.");
      setSaving(false);
      return;
    }
    const result = await createConsistencyFinding({
      consistency_check_id: check.id,
      field_name: findingField.trim(),
      value_1: valueOne,
      value_2: valueTwo,
      severity: severity.trim(),
      confidence: confidenceValue,
      description: findingDescription.trim(),
      evidence,
    }, token);
    setSaving(false);
    if (await handleUnauthorized(result)) return;
    if (!result.ok) {
      setError(firstError(result, "Unable to save this finding."));
      return;
    }
    setFindings((current) => [result.data, ...current]);
    const checkResult = await fetchConsistencyCheck(check.id, token);
    if (await handleUnauthorized(checkResult)) return;
    if (checkResult.ok) setCheck(checkResult.data);
    setFindingField("");
    setValueOne("");
    setValueTwo("");
    setSeverity("medium");
    setConfidence("");
    setFindingDescription("");
    setFindingEvidence("");
    setNotice("Finding saved to this consistency check.");
  }

  async function saveFinding(findingId: number, payload: ConsistencyFindingUpdate) {
    if (!token) return;
    setError("");
    const result = await updateConsistencyFinding(findingId, payload, token);
    if (await handleUnauthorized(result)) return;
    if (!result.ok) {
      setError(firstError(result, "Unable to update this finding."));
      return;
    }
    setFindings((current) => current.map((finding) => finding.id === findingId ? result.data : finding));
    const checkResult = await fetchConsistencyCheck(result.data.consistency_check_id, token);
    if (await handleUnauthorized(checkResult)) return;
    if (checkResult.ok) setCheck(checkResult.data);
    setNotice("Finding updated.");
  }

  if (loading) {
    return <p className="py-12 text-center text-sm text-text-secondary" role="status">Loading consistency checks…</p>;
  }

  if (checkId !== null) {
    if (!check) {
      return (
        <section className="mx-auto max-w-4xl space-y-5" aria-labelledby="consistency-title">
          <Link to="/consistency" className="inline-flex items-center gap-2 text-sm text-text-secondary underline underline-offset-4">
            <ArrowLeft className="h-4 w-4" aria-hidden="true" /> Back to consistency checks
          </Link>
          <h1 id="consistency-title" className="text-3xl font-bold text-text-heading">Consistency Check</h1>
          <p className="rounded-md border border-error-border bg-error-bg/30 p-4 text-sm text-error-text" role="alert">
            {error || "This consistency record was not found or access is denied."}
          </p>
        </section>
      );
    }

    return (
      <div className="mx-auto max-w-5xl space-y-6 animate-fade-in">
        <Link to="/consistency" className="inline-flex items-center gap-2 text-sm text-text-secondary underline underline-offset-4">
          <ArrowLeft className="h-4 w-4" aria-hidden="true" /> Back to consistency checks
        </Link>
        <header className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="space-y-2">
            <p className="text-xs font-bold uppercase tracking-[0.16em] text-text-muted">Institution-scoped record</p>
            <h1 className="break-words text-3xl font-bold tracking-tight text-text-heading">{check.check_name}</h1>
            <p className="max-w-2xl text-sm leading-relaxed text-text-secondary">
              This API stores review records and findings. It does not run an automatic or AI comparison.
            </p>
          </div>
          <span className={`inline-flex w-fit items-center rounded-full border px-3 py-1.5 text-sm font-medium ${statusClass(check.status)}`}>
            {statusLabel(check.status)}
          </span>
        </header>

        {notice && <p className="rounded-md border border-success-border bg-success-bg/30 p-3 text-sm text-success-text" role="status">{notice}</p>}
        {error && <p className="rounded-md border border-error-border bg-error-bg/30 p-3 text-sm text-error-text" role="alert">{error}</p>}

        <Card>
          <CardHeader><CardTitle>Application details</CardTitle></CardHeader>
          <CardContent className="grid gap-4 p-5 pt-0 text-sm sm:grid-cols-2 lg:grid-cols-4">
            <div><p className="text-xs font-semibold text-text-secondary">Application</p><p className="mt-1 text-text-heading">#{check.application_id}</p></div>
            <div><p className="text-xs font-semibold text-text-secondary">Type / academic year</p><p className="mt-1 text-text-heading">{application ? `${application.application_type} · ${application.academic_year}` : "Not available"}</p></div>
            <div><p className="text-xs font-semibold text-text-secondary">Application status</p><p className="mt-1 text-text-heading">{application?.status ?? "Not available"}</p></div>
            <div><p className="text-xs font-semibold text-text-secondary">Related field</p><p className="mt-1 break-words text-text-heading">{check.related_field || "Not specified"}</p></div>
            <div><p className="text-xs font-semibold text-text-secondary">Created</p><p className="mt-1 text-text-heading">{formatDate(check.created_at)}</p></div>
            <div><p className="text-xs font-semibold text-text-secondary">Last updated</p><p className="mt-1 text-text-heading">{formatDate(check.updated_at)}</p></div>
          </CardContent>
        </Card>

        <section className="space-y-4" aria-labelledby="findings-heading">
          <div className="flex items-center gap-2">
            <FileSearch className="h-5 w-5 text-text-secondary" aria-hidden="true" />
            <h2 id="findings-heading" className="text-xl font-bold text-text-heading">Findings ({findings.length})</h2>
          </div>
          {findings.length === 0
            ? <p className="rounded-lg border border-dashed border-border p-6 text-sm text-text-secondary">No findings have been recorded for this check yet.</p>
            : <div className="space-y-4">{findings.map((finding) => <FindingCard key={`${finding.id}-${finding.updated_at}`} finding={finding} onUpdate={saveFinding} />)}</div>}
        </section>

        <Card>
          <CardHeader><CardTitle>Add finding</CardTitle></CardHeader>
          <CardContent className="p-5 pt-0">
            <form className="grid gap-4 md:grid-cols-2" onSubmit={(event) => { void submitFinding(event); }}>
              <label className="grid gap-1.5 text-sm text-text-secondary">Finding field/title
                <input className="app-control min-h-10 rounded-md border border-border bg-bg-1 px-3 text-text-body" value={findingField} onChange={(event) => setFindingField(event.target.value)} maxLength={100} required />
              </label>
              <label className="grid gap-1.5 text-sm text-text-secondary">Severity
                <input className="app-control min-h-10 rounded-md border border-border bg-bg-1 px-3 text-text-body" value={severity} onChange={(event) => setSeverity(event.target.value)} maxLength={30} required />
              </label>
              <label className="grid gap-1.5 text-sm text-text-secondary">Compared value 1
                <input className="app-control min-h-10 rounded-md border border-border bg-bg-1 px-3 text-text-body" value={valueOne} onChange={(event) => setValueOne(event.target.value)} maxLength={4000} required />
              </label>
              <label className="grid gap-1.5 text-sm text-text-secondary">Compared value 2
                <input className="app-control min-h-10 rounded-md border border-border bg-bg-1 px-3 text-text-body" value={valueTwo} onChange={(event) => setValueTwo(event.target.value)} maxLength={4000} required />
              </label>
              <label className="grid gap-1.5 text-sm text-text-secondary">Confidence (0–1, optional)
                <input className="app-control min-h-10 rounded-md border border-border bg-bg-1 px-3 text-text-body" type="number" min="0" max="1" step="0.01" value={confidence} onChange={(event) => setConfidence(event.target.value)} />
              </label>
              <label className="grid gap-1.5 text-sm text-text-secondary md:col-span-2">Description
                <textarea className="app-control min-h-20 rounded-md border border-border bg-bg-1 p-3 text-text-body" value={findingDescription} onChange={(event) => setFindingDescription(event.target.value)} maxLength={4000} required />
              </label>
              <label className="grid gap-1.5 text-sm text-text-secondary md:col-span-2">Evidence JSON object (optional)
                <textarea className="app-control min-h-24 rounded-md border border-border bg-bg-1 p-3 font-mono text-xs text-text-body" value={findingEvidence} onChange={(event) => setFindingEvidence(event.target.value)} placeholder={'{"source": "..."}'} />
              </label>
              <div className="md:col-span-2">
                <Button type="submit" loading={saving} leftIcon={<Plus className="h-4 w-4" />}>Save finding</Button>
              </div>
            </form>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl space-y-7 animate-fade-in">
      <header className="space-y-2">
        <p className="text-xs font-bold uppercase tracking-[0.16em] text-text-muted">Authenticated workspace</p>
        <h1 className="text-3xl font-extrabold tracking-tight text-text-heading">Consistency Check</h1>
        <p className="max-w-3xl text-sm leading-relaxed text-text-secondary">
          Start an institution-scoped consistency review for an application, inspect saved records and manage findings. Creating a check records the review; the API does not automatically compare documents.
        </p>
      </header>

      {notice && <p className="rounded-md border border-success-border bg-success-bg/30 p-3 text-sm text-success-text" role="status">{notice}</p>}
      {error && <p className="rounded-md border border-error-border bg-error-bg/30 p-3 text-sm text-error-text" role="alert">{error}</p>}

      <Card>
        <CardHeader><CardTitle>Start a consistency check</CardTitle></CardHeader>
        <CardContent className="p-5 pt-0">
          {applications.length === 0
            ? <p className="rounded-md border border-dashed border-border p-4 text-sm text-text-secondary">No applications are available in your authorized institution scope. Create or request access to an application before starting a check.</p>
            : (
              <form className="grid gap-4 md:grid-cols-2" onSubmit={(event) => { void submitCheck(event); }}>
                <label className="grid gap-1.5 text-sm text-text-secondary md:col-span-2">Application
                  <select className="app-control min-h-11 w-full rounded-md border border-border bg-bg-1 px-3 text-text-body" value={applicationId} onChange={(event) => setApplicationId(event.target.value)} required>
                    <option value="">Select an authorized application</option>
                    {applications.map((item) => <option key={item.id} value={item.id}>#{item.id} · {item.application_type} · {item.academic_year} · {item.status}</option>)}
                  </select>
                </label>
                <label className="grid gap-1.5 text-sm text-text-secondary md:col-span-2">Check name
                  <input className="app-control min-h-10 rounded-md border border-border bg-bg-1 px-3 text-text-body" value={checkName} onChange={(event) => setCheckName(event.target.value)} maxLength={255} required />
                </label>
                <label className="grid gap-1.5 text-sm text-text-secondary">Related field (optional)
                  <input className="app-control min-h-10 rounded-md border border-border bg-bg-1 px-3 text-text-body" value={relatedField} onChange={(event) => setRelatedField(event.target.value)} maxLength={100} />
                </label>
                <label className="grid gap-1.5 text-sm text-text-secondary md:col-span-2">Description (optional)
                  <textarea className="app-control min-h-20 rounded-md border border-border bg-bg-1 p-3 text-text-body" value={checkDescription} onChange={(event) => setCheckDescription(event.target.value)} maxLength={4000} />
                </label>
                <div className="md:col-span-2"><Button type="submit" loading={saving} leftIcon={<ListChecks className="h-4 w-4" />}>Create consistency check</Button></div>
              </form>
            )}
        </CardContent>
      </Card>

      <section className="space-y-4" aria-labelledby="saved-checks-heading">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 id="saved-checks-heading" className="text-xl font-bold text-text-heading">Previous consistency checks</h2>
          <span className="text-xs text-text-muted">{checks.length} record{checks.length === 1 ? "" : "s"}</span>
        </div>
        {checks.length === 0
          ? <p className="rounded-lg border border-dashed border-border p-6 text-sm text-text-secondary">No consistency checks have been saved for your authorized institutions.</p>
          : <div className="grid gap-4 sm:grid-cols-2">{checks.map((item) => (
            <Link key={item.id} to={`/consistency/${item.id}`} className="block rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500">
              <Card className="h-full transition-colors hover:border-border-hover">
                <CardContent className="space-y-4 p-5">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0"><h3 className="break-words font-semibold text-text-heading">{item.check_name}</h3><p className="mt-1 text-xs text-text-secondary">Application #{item.application_id}</p></div>
                    <span className={`shrink-0 rounded-full border px-2.5 py-1 text-xs ${statusClass(item.status)}`}>{statusLabel(item.status)}</span>
                  </div>
                  {item.description && <p className="line-clamp-2 text-sm text-text-secondary">{item.description}</p>}
                  <p className="flex items-center gap-1.5 text-xs text-text-muted"><Clock3 className="h-3.5 w-3.5" aria-hidden="true" />Updated {formatDate(item.updated_at)}</p>
                </CardContent>
              </Card>
            </Link>
          ))}</div>}
      </section>
      <p className="flex items-start gap-2 rounded-md border border-info-border bg-info-bg/30 p-3 text-xs leading-relaxed text-text-secondary">
        <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-info-text" aria-hidden="true" />
        All records are loaded from the authenticated backend, which limits results to your institution memberships. Finding codes and document links are not part of the current API response.
      </p>
    </div>
  );
}
