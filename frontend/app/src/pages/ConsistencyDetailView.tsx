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
}

interface ConsistenceDetailFormValues {
  severity?: string;
  description?: string;
  evidence?: Record<string, unknown>;
}

const navItems = [
  { path: "/", label: "Dashboard", icon: LayoutDashboard },
  { path: "/validate", label: "Validate", icon: ClipboardCheck },
  { path: "/consistency", label: "Consistency Checks", icon: GitCompareArrows },
  { path: "/cadre-calculator", label: "Cadre & FSR Norms", icon: GraduationCap },
  { path: "/history", label: "Audit History", icon: Clock3 },
  { path: "/about", label: "Compliance Guide", icon: Info },
] as const;

export function Sidebar({ collapsed, onToggle, open, onClose }: { collapsed: boolean; onToggle: () => void; open: boolean; onClose: () => void }) {
  const location = useLocation();
  const items = navItems;
  return (
    <aside className={cn(
      "app-sidebar fixed inset-y-0 left-0 z-50 bg-bg-1 border-r border-border transition-transform duration-200 ease-out",
      "flex flex-col",
      "w-[min(260px,calc(100vw-3rem))] lg:w-[260px]",
      collapsed && "lg:w-[72px]",
      open ? "translate-x-0 visible" : "-translate-x-full invisible lg:visible lg:translate-x-0"
    )}
      aria-label="Main navigation"
    >
      <div className="flex h-16 items-center justify-between px-4 border-b border-border">
        <Link to="/" className="flex items-center gap-2 min-w-0" aria-label="AICTE Compliance Home" onClick={onClose}>
          <div className="p-2 bg-primary-700 rounded-md shrink-0">
            <Shield className="h-5 w-5 text-white" aria-hidden="true" />
          </div>
          <span className={cn("font-bold text-text-heading truncate", collapsed && "lg:hidden")}>AICTE Compliance</span>
        </Link>
        {collapsed && (
          <span className="hidden lg:block" />
        )}
        <Button variant="ghost" size="sm" onClick={onToggle} aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"} className="hidden lg:inline-flex text-text-muted hover:text-text-body">
          {collapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
        </Button>
        <Button variant="ghost" size="sm" onClick={onClose} aria-label="Close navigation" className="lg:hidden text-text-muted">
          <X className="h-4 w-4" />
        </Button>
      </div>
      <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto" aria-label="Navigation">
        {items.map((item) => {
          const Icon = item.icon;
          const isActive = location.pathname === item.path;
          return (
            <NavLink
              key={item.path}
              to={item.path}
              className={({ isActive: active }) => cn(
                "flex items-center gap-3 px-3 py-2.5 min-h-10 rounded-lg border-transparent transition-all duration-200",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500",
                active
                  ? "bg-primary-500/10 text-text-heading border-l-primary-500 pl-2"
                  : "text-text-secondary hover:bg-bg-2 hover:text-text-body",
                collapsed && "lg:justify-center lg:px-2"
              )}
              aria-current={isActive ? "page" : undefined}
              title={collapsed ? item.label : undefined}
              onClick={onClose}
            >
              <Icon className="h-5 w-5 flex-shrink-0" aria-hidden="true" />
              <span className={cn("font-medium", collapsed && "lg:hidden")}>{item.label}</span>
            </NavLink>
          );
        })}
      </nav>
      <div className="p-4 border-t border-border">
        <div className={cn("space-y-3", collapsed && "lg:hidden")}>\n          <div className="space-y-3">
            <p className="text-xs font-medium text-text-secondary">Review scope</p>
            <p className="text-xs text-text-muted">EoA 2026M-bM-^@M-^S27 rule review is pending. Current checks use only the lists supplied.</p>
          </div>
        </div>
      </div>
    </aside>
  );
}

import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
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
}

export function ConsistencyDetailView({ findingId }: { findingId: number }) {
  const [findings, setFindings] = useState<Finding[]>([]);
  const [token, setToken] = useState<string>("");
  const [finding, setFinding] = useState<Finding | null>(null);
  const [resolvedBusy, setResolvedBusy] = useState<boolean>(false);
  const [actionError, setFindingActionError] = useState<string>("");

  useEffect(() => {
    fetch("/api/v1/consistency/findings", { headers: { Authorization: "Bearer " + token } })
      .then((r) => r.json()).then(setFindings)
  }, [checkId, token, baseUrl]);

  const handleResolve = (e: React.FormEvent) => {
    e.preventDefault();
    updateConsistencyFinding(Number(findingId), {
      resolved: true,
      ...formValues,
    }, token).then(() => navigate("/consistency"));
  };

  if (!check) return <p>Loading…</p>;

  const findingId = findings[0]?.id;

  return (
    <div>
      <form onSubmit={handleResolve} className="p-6 space-y-4 max-w-md">
        <div>
          <label className="block text-sm font-medium mb-2">Severity</label>
          <select
            value={finding?.severity || ''}
            onChange={(e) => setFinding({ ...finding, severity: e.target.value } as any)}
            className="border rounded p-2"
          >
            <option value="">-- Select --</option>
            <option value="resolved">Resolved</option>
            <option value="discrepancy_detected">Discrepancy detected</option>
            <option value="pending">Pending</option>
          </select>
        </div>
        <div>
          <label className="block text-sm font-medium mb-2">Description</label>
          <textarea
            value={finding?.description || ''}
            onChange={(e) => setFinding({ ...finding, description: e.target.value } as any)}
            className="border rounded p-2"
            rows={3}
          ></textarea>
        </div>
        <div>
          <label className="block text-sm font-medium mb-2">Evidence</label>
          <input
            type="text"
            value={finding?.evidence ? JSON.stringify(finding.evidence) : ''}
            onChange={(e) => setFinding({ ...finding, evidence: JSON.parse(e.target.value) } as any)}
            className="border rounded p-2"
          />
        </div>
        <button type="submit" disabled={!findingId} className="btn-primary">
          Resolve Finding
        </button>
      </form>
    </div>
  );
}

export default ConsistencyDetailView;

const navigate = useNavigate();