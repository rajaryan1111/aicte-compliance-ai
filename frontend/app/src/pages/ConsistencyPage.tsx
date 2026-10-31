import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  Building2,
  ClipboardList,
  RotateCcw,
  Search,
} from "lucide-react";
import { Button } from "@/components/Button";
import { Card, CardContent } from "@/components/Card";
import { EmptyState } from "@/components/EmptyState";
import { FormField, Input, Select } from "@/components/FormField";
import { useAuth } from "@/components/useAuth";
import { formatTimestamp } from "@/lib/utils";
import {
  createConsistencyCheck,
  fetchApplications,
  listConsistencyChecks,
  type ApplicationPage,
  type ConsistencyCheck,
  type ConsistencyStatus,
} from "@/lib/consistency-api";
import { ConsistencyDetailView, StatusBadge } from "./ConsistencyDetailView";

const STATUS_OPTIONS = [
  { value: "", label: "All statuses" },
  { value: "pending", label: "Pending" },
  { value: "discrepancy_detected", label: "Discrepancy detected" },
  { value: "resolved", label: "Resolved" },
] as const;

function ConsistencyWorkflowPage() {
  const auth = useAuth();
  const { session } = auth;
  const token = session?.access_token ?? null;
  const { checkId } = useParams();

  const detailId = checkId && /^\d+$/.test(checkId) ? Number(checkId) : null;

  // ── Tenant-scoped application selector ──
  const [applications, setApplications] = useState<ApplicationPage | null>(null);
  const [applicationError, setApplicationError] = useState("");
  const [selectedApplication, setSelectedApplication] = useState("");

  // ── Saved checks list ──
  const [checks, setChecks] = useState<ConsistencyCheck[]>([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [checksLoading, setChecksLoading] = useState(true);
  const [checksError, setChecksError] = useState("");

  // ── Create-check form ──
  const [checkName, setCheckName] = useState("");
  const [relatedField, setRelatedField] = useState("");
  const [description, setDescription] = useState("");
  const [formErrors, setFormErrors] = useState<Record<string, string>>({});
  const [creating, setCreating] = useState(false);
  const [createdNotice, setCreatedNotice] = useState("");

  const applyChecksResult = (
    result: Awaited<ReturnType<typeof listConsistencyChecks>>,
  ) => {
    setChecksLoading(false);
    if (result.ok) {
      setChecks(result.data);
      setChecksError("");
    } else {
      setChecks([]);
      setChecksError(Object.values(result.errors)[0] || "Unable to load saved consistency checks.");
    }
  };

  // Data fetching runs as effects; state is committed only in the async
  // continuation so no synchronous render cascade starts inside the effect.
  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    void fetchApplications(token, { limit: 50 }).then((result) => {
      if (cancelled) return;
      if (result.ok) {
        setApplications(result.data);
        setApplicationError("");
        const first = result.data.items[0];
        if (first) setSelectedApplication((current) => current || String(first.id));
      } else {
        setApplicationError(Object.values(result.errors)[0] || "Unable to load your applications.");
      }
    });
    return () => {
      cancelled = true;
    };
  }, [token]);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    void listConsistencyChecks(
      token,
      {
        applicationId: selectedApplication ? Number(selectedApplication) : undefined,
        statusFilter: (statusFilter || undefined) as ConsistencyStatus | undefined,
      },
    ).then((result) => {
      if (!cancelled) applyChecksResult(result);
    });
    return () => {
      cancelled = true;
    };
  }, [statusFilter, selectedApplication, token]);

  async function refreshChecks() {
    if (!token) return;
    setChecksLoading(true);
    const result = await listConsistencyChecks(
      token,
      {
        applicationId: selectedApplication ? Number(selectedApplication) : undefined,
        statusFilter: (statusFilter || undefined) as ConsistencyStatus | undefined,
      },
    );
    applyChecksResult(result);
  }

  async function handleCreateCheck(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !selectedApplication) {
      setFormErrors({ application_id: "Select an application in your institutional scope first." });
      return;
    }
    setFormErrors({});
    setCreatedNotice("");
    setCreating(true);
    const result = await createConsistencyCheck(
      {
        application_id: Number(selectedApplication),
        check_name: checkName,
        description: description || null,
        related_field: relatedField || null,
      },
      token,
    );
    setCreating(false);
    if (result.ok) {
      setCheckName("");
      setRelatedField("");
      setDescription("");
      setCreatedNotice(`Saved consistency check “${result.data.check_name}”.`);
      await refreshChecks();
    } else {
      setFormErrors(Object.keys(result.errors).length > 0 ? result.errors : { _form: "The check could not be saved." });
    }
  }

  // ── Detail view (code-split module) ──
  if (detailId !== null) {
    return <ConsistencyDetailView token={token} detailId={detailId} />;
  }

  // ── List view ──
  const applicationItems = (applications?.items ?? []).map((item) => ({
    value: String(item.id),
    label: `#${item.id} · ${item.application_type} · ${item.academic_year}`,
  }));

  return (
    <div className="mx-auto max-w-5xl space-y-7">
      <header className="space-y-2">
        <p className="text-xs font-bold uppercase tracking-[0.16em] text-text-muted">Tenant-scoped review</p>
        <h1 className="text-3xl font-extrabold tracking-tight text-text-heading">Consistency Checks</h1>
        <p className="max-w-2xl text-sm leading-relaxed text-text-secondary">
          Record persistent cross-checks between submitted values and authorised records for applications in your
          institutional scope, and audit the supporting evidence.
        </p>
      </header>

      <Card padding="md">
        <CardContent className="grid gap-4 p-5 sm:grid-cols-2">
          <FormField label="Application" hint="Only applications your institutional membership can access are listed.">
            <Select
              value={selectedApplication}
              options={applicationItems}
              placeholder={applicationItems.length > 0 ? "Select an application" : "No authorised applications"}
              disabled={applicationItems.length === 0}
              onChange={(value) => setSelectedApplication(value)}
            />
          </FormField>
          <FormField label="Status filter">
            <Select
              value={statusFilter}
              options={[...STATUS_OPTIONS]}
              onChange={(value) => setStatusFilter(value)}
            />
          </FormField>
        </CardContent>
      </Card>

      {applicationError && <p className="text-sm text-error-text" role="alert">{applicationError}</p>}

      <Card>
        <CardContent className="space-y-4 p-5">
          <h2 className="text-lg font-semibold text-text-heading">Run a new consistency check</h2>
          {Object.keys(formErrors).length > 0 && (
            <ul className="list-inside list-disc rounded-md border border-error-border bg-error-bg/20 p-3 text-sm text-error-text" role="alert">
              {Object.entries(formErrors).map(([key, message]) => (
                <li key={key}>{message}</li>
              ))}
            </ul>
          )}
          {createdNotice && <p className="text-sm text-success-text" role="status">{createdNotice}</p>}
          <form className="grid gap-4" onSubmit={(event) => { void handleCreateCheck(event); }}>
            <div className="grid gap-4 sm:grid-cols-2">
              <FormField label="Check name" hint="Max 255 characters." required>
                <Input name="check_name" required value={checkName} onChange={(e) => setCheckName(e.target.value)} placeholder="e.g. Sanctioned intake vs approved record" />
              </FormField>
              <FormField label="Compared field" hint="Optional. Max 100 characters.">
                <Input name="related_field" value={relatedField} onChange={(e) => setRelatedField(e.target.value)} placeholder="e.g. approved_intake" />
              </FormField>
            </div>
            <FormField label="Description" hint="Optional. Max 4000 characters.">
              <textarea
                name="description"
                rows={3}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                className="app-control w-full rounded-lg border border-border bg-bg-3 p-3 text-sm text-text-body focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/30"
              />
            </div>
            <div>
              <Button type="submit" loading={creating} disabled={applicationItems.length === 0}>Save check</Button>
            </div>
          </form>
        </CardContent>
      </Card>

      {checksError && <p className="text-sm text-error-text" role="alert">{checksError}</p>}

      {checksLoading ? (
        <p className="py-8 text-center text-sm text-text-secondary" role="status">Loading saved checks…</p>
      ) : checks.length === 0 ? (
        <EmptyState
          icon={ClipboardList}
          title={checksError ? "Nothing to display" : "No saved consistency checks"}
          description={checksError
            ? undefined
            : "Save a check above for one of your authorised applications to start the audit trail. Pending checks show without discrepancies until findings are recorded."}
        />
      ) : (
        <ul className="space-y-3" aria-label="Saved consistency checks">
          {checks.map((item) => (
            <li key={item.id}>
              <Card padding="md">
                <CardContent className="grid gap-4 p-5 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center">
                  <div className="min-w-0 space-y-2">
                    <div className="flex flex-wrap items-center gap-2.5">
                      <h3 className="font-semibold text-text-heading truncate">{item.check_name}</h3>
                      <StatusBadge status={item.status} />
                    </div>
                    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-text-secondary">
                      <span>Application <strong className="text-text-heading">#{item.application_id}</strong></span>
                      {item.related_field && <span>Field: {item.related_field}</span>}
                      <span>Created {formatTimestamp(item.created_at)}</span>
                    </div>
                    {item.description && (
                      <p className="line-clamp-2 text-sm text-text-secondary">{item.description}</p>
                    )}
                  </div>
                  <div className="flex items-center gap-2.5 sm:self-center">
                    <Button
                      size="sm"
                      variant="secondary"
                      leftIcon={<RotateCcw className="h-3.5 w-3.5" />}
                      onClick={() => { void refreshChecks(); }}
                      title="Refresh saved checks"
                    >
                      Refresh
                    </Button>
                    <Link to={`/consistency/${item.id}`}>
                      <Button size="sm" leftIcon={<Search className="h-3.5 w-3.5" />}>View details</Button>
                    </Link>
                  </div>
                </CardContent>
              </Card>
            </li>
          ))}
        </ul>
      )}

      <Card variant="feature" padding="sm">
        <CardContent className="flex items-start gap-3 p-4 text-xs text-text-secondary">
          <Building2 className="mt-0.5 h-4 w-4 shrink-0 text-info-text" aria-hidden="true" />
          <p>
            Consistency checks are recorded server-side and scoped to the authenticated user's institution memberships;
            opening a check requires <code className="font-mono">application:update</code> permission on its tenant.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}

export default ConsistencyWorkflowPage;
