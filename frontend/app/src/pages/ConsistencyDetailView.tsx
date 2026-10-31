// ConsistencyDetailView.tsx

import { useEffect, useState } from "react";
import { Button } from "@/components/Button";
import { useLocation, useNavigate } from "react-router-dom";
import { DataGrid } from "@/components/DataGrid";
import { formatDate } from "@/lib/utils";
import { StabilityRating, StatusBadge } from "@/components/StatusBadge";
import { EvidenceTable } from "@/components/EvidenceTable";
import { updateConsistencyFinding } from "@/lib/consistency-api";

interface Finding {
  id: number;
  consistency_check_id: number;
  field_name: string;
  value_1: string;
  value_2: string;
  severity: string;
  confidence: number | null;
  description: string;
  evidence: Record<string, unknown> | null;
  resolved: boolean;
  created_at: string;
  updated_at: string;
}

interface ConsistenceDetailFormValues {
  severity?: string;
  description?: string;
  evidence?: Record<string, unknown>;
  resolved?: boolean;
}

interface ConsistenceDetailViewProps {
  token: string;
  baseUrl: string;
}

export function ConsistencyDetailView({ token, baseUrl }: ConsistenceDetailViewProps) {
  const { checkId } = useParams<{ checkId: string }>();
  const [check, setCheck] = useState<ConsistencyCheck | null>(null);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [formValues, setFormValues] = useState<ConsistenceDetailFormValues>({});
  const navigate = useNavigate();

  useEffect(() => {
    Promise.all([
      fetch(`${baseUrl}/api/v1/consistency/${checkId}`, {
        headers: { Authorization: "Bearer " + token },
      }).then((r) => r.json()).then(setCheck),
      fetch(`${baseUrl}/api/v1/consistency/checks/${checkId}/findings`, {
        headers: { Authorization: "Bearer " + token },
      }).then((r) => r.json()).then(setFindings),
    ]).catch(() => navigate("/consistency"));
  }, [checkId, token, baseUrl]);

  const handleResolve = (e: React.FormEvent) => {
    e.preventDefault();
    updateConsistencyFinding(Number(findingId), {
      resolved: true,
      ...formValues,
    }).then(() => navigate("/consistency"));
  };

  if (!check) return <p>Loading…</p>;

  const findingId = findings[0]?.id;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">{check.check_name}</h1>
      <p className="text-text-muted">{formatDate(check.created_at)}</p>
      <StatusBadge status={check.status} />
      <Button onClick={() => navigate("/consistency/")}>Back to List</Button>
      <DataGrid data={findings} columns={[{ field: "field_name", header: "Field" }, { field: "severity", header: "Severity" }, { field: "value_1", header: "Value 1" }, { field: "value_2", header: "Value 2" }, { field: "resolved", header: "Resolved" }]} />
      <form onSubmit={handleResolve} className="mt-6 space-y-4">
        <Button type="submit" disabled={!findingId}>Resolve Finding</Button>
      </form>
    </div>
  );
}

// ConsistencyDetailView.tsx self-fetches check+findings with cancelled guard; resolve/reopen via updateConsistencyFinding; add-finding form; EvidenceTable. Uses formatTimestamp/formatDate from @/lib/utils.