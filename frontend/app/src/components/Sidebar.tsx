import { Link, useLocation, NavLink } from "react-router-dom";
import { cn } from "@/lib/utils";
import {
  LayoutDashboard,
  ClipboardCheck,
  Clock3,
  Info,
  ChevronLeft,
  ChevronRight,
  Shield,
  X,
  GraduationCap,
  GitCompareArrows,
  ScanSearch,
} from "lucide-react";
import { Button } from "./Button";

const navItems = [
  { path: "/", label: "Dashboard", icon: LayoutDashboard },
  { path: "/validate", label: "Validate", icon: ClipboardCheck },
  { path: "/gap-analyzer", label: "Gap Analyzer", icon: ScanSearch },
  { path: "/consistency", label: "Consistency Checks", icon: GitCompareArrows },
  { path: "/cadre-calculator", label: "Cadre & FSR Norms", icon: GraduationCap },
  { path: "/history", label: "Audit History", icon: Clock3 },
  { path: "/about", label: "Compliance Guide", icon: Info },
] as const;

export function Sidebar({
  collapsed,
  onToggle,
  open,
  onClose,
}: {
  collapsed: boolean;
  onToggle: () => void;
  open: boolean;
  onClose: () => void;
}) {
  const location = useLocation();
  const items = navItems;

  return (
    <aside
      className={cn(
        "app-sidebar fixed inset-y-0 left-0 z-50 bg-bg-1 border-r border-border transition-transform duration-200 ease-out",
        "flex flex-col",
        "w-[min(260px,calc(100vw-3rem))] lg:w-[260px]",
        collapsed && "lg:w-[72px]",
        open ? "translate-x-0 visible" : "-translate-x-full invisible lg:visible lg:translate-x-0"
      )}
      aria-label="Main navigation"
    >
      <div className="flex h-16 items-center justify-between px-4 border-b border-border">
        <Link to="/" className="flex items-center gap-2 min-w-0" aria-label="AICTE Compliance AI Home" onClick={onClose}>
          <div className="p-2 bg-primary-700 rounded-md shrink-0">
            <Shield className="h-5 w-5 text-white" aria-hidden="true" />
          </div>
          <span className={cn("font-bold text-text-heading truncate", collapsed && "lg:hidden")}>AICTE Compliance</span>
        </Link>
        {collapsed && (
          <span className="hidden lg:block" />
        )}
        <Button
          variant="ghost"
          size="sm"
          onClick={onToggle}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          className="hidden lg:inline-flex text-text-muted hover:text-text-body"
        >
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
        <div className={cn("space-y-3", collapsed && "lg:hidden")}>
          <div className="space-y-3">
            <p className="text-xs font-medium text-text-secondary">Review scope</p>
            <p className="text-xs text-text-muted">EoA 2026–27 rule review is pending. Current checks use only the lists supplied.</p>
          </div>
        </div>
      </div>
    </aside>
  );
}
