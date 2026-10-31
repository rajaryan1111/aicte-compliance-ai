// ConsistencyPage.tsx

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

interface ConsistencePageProps {
  token: string;
  baseUrl: string;
}

export default function ConsistencyPage({ token, baseUrl }: ConsistencePageProps) {
  const [applications, setApplications] = useState<ApplicationSummary[]>([]);
  const [checks, setChecks] = useState<CheckSummary[]>([]);
  const [selectedApplication, setSelectedApplication] = useState<ApplicationSummary | null>(null);
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [creating, setCreating] = useState<boolean>(false);
  const [newCheck, setNewCheck] = useState<{ check_name: string; description?: string; related_field?: string }>({ check_name: "", description: "", related_field: "" });
  const navigate = useNavigate();
  const location = useLocation();

  // Auto-select first application on mount
  useEffect(() => {
    if (applications.length === 0) {
      fetchApplications(token, { limit: 50 })
        .then((r) => setApplications(r.data?.items ?? []))
        .then(() => setSelectedApplication(applications[0] ?? null));
    }
  }, [applications.length, token]);

  // Load checks for selected application
  useEffect(() => {
    if (selectedApplication) {
      listConsistencyChecks(token, { applicationId: selectedApplication.id, statusFilter }, { skip: 0, limit: 50 })
        .then((r) => setChecks(r.data?.items ?? []));
    }
  }, [selectedApplication?.id, statusFilter]);

  const handleCreate = () => {
    setCreating(true);
    createConsistencyCheck({
      application_id: selectedApplication!.id,
      check_name: newCheck.check_name,
      description: newCheck.description,
      related_field: newCheck.related_field,
    }, token)
      .then((r) => {
        setNewCheck({ check_name: "", description: "", related_field: "" });
        setCreating(false);
        listConsistencyChecks(token, { applicationId: selectedApplication!.id, statusFilter }, { skip: 0, limit: 50 })
          .then((r) => setChecks(r.data?.items ?? []));
      })
      .catch(() => setCreating(false));
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

// ConsistencyPage.tsx default-export workbench; tenant selector via fetchApplications auto-selects first app; status filter; create form; list view; routes /consistency and /consistency/:checkId behind RequireAuth + Suspense.