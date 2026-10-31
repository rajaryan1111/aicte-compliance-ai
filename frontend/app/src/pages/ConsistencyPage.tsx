import { useEffect, useState } from "react";
import { Button } from "@/components/Button";
import { cn } from "@/lib/utils";
import { useParams } from "react-router-dom";
import { fetchApplications } from "@/lib/consistency-api";
import { useLocation, useNavigate } from "react-router-dom";
import { DataGrid } from "@/components/DataGrid";
import { formatTimestamp } from "@/lib/utils";
import { StatusBadge } from "@/components/StatusBadge";
import { EvidenceTable } from "@/components/EvidenceTable";
import { formatDate } from "@/lib/utils";
import { createConsistencyCheck } from "@/lib/consistency-api";
import { listConsistencyChecks } from "@/lib/consistency-api";

interface ApplicationSummary {
  id: number;
  institution_id: number;
  application_type: string;
  academic_year: string;
  status: string;
}

interface CheckSummary {
  id: number;
  application_id: number;
  check_name: string;
  description: string | null;
  related_field: string | null;
  status: string;
  created_at: string;
  updated_at: string;
}

interface CheckFilters {
  applicationId?: number;
  statusFilter?: string;
}

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
    onSuccess: () => void,
    onError: (error: string) => void,
  ) => {
    setCreating(false);
    setChecksLoading(false);
    if (onError) onError("Failed to load checks");
    else onSuccess();
  };

  if (creating) return <p>Creating…</p>;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Consistency Checks</h1>
      <p className="text-text-muted">{formatTimestamp(new Date())}</p>
      <select
        onChange={(e) => setSelectedApplication({ id: Number(e.target.value), ...selectedApplication } as any)}
        className="border rounded p-2"
      >
        <option value="">-- Select Application --</option>
        {applications.map((app) => (
          <option key={app.id} value={app.id}>
            {app.application_type} — {app.institution_id}
          </option>
        ))}
      </select>
      <Button onClick={handleCreate} disabled={creating}>
        {creating ? "Creating…" : "Add Consistency Check"}
      </Button>
      <hr className="my-4" />
      <DataGrid data={checks} columns={[{ field: "check_name", header: "Check Name" }, { field: "status", header: "Status" }, { field: "created_at", header: "Created" }]} />
      <Button onClick={() => navigate("/consistency/")}>Back</Button>
    </div>
  );
}

export default ConsistencyWorkflowPage;
