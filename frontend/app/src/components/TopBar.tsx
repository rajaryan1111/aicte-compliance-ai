import { useLocation } from "react-router-dom";
import { Link } from "react-router-dom";
import { HealthIndicator } from "./HealthIndicator";
import { useTheme, type ThemeName } from "./ThemeContext";
import { Shield, ChevronRight, LayoutDashboard, ClipboardCheck, Info, FileLock2, FileText, Menu, X, Clock3, GraduationCap, ListChecks } from "lucide-react";
import { useAuth } from "./useAuth";

const pageTitles: Record<string, { title: string; description: string; icon: React.ReactNode }> = {
  "/": {
    title: "Dashboard",
    description: "Compliance overview",
    icon: <LayoutDashboard className="h-5 w-5" />,
  },
  "/validate": {
    title: "Validate",
    description: "Document validation workspace",
    icon: <ClipboardCheck className="h-5 w-5" />,
  },
  "/cadre-calculator": {
    title: "Cadre & FSR Calculator",
    description: "AICTE 1:2:6 ratio & doctoral norms",
    icon: <GraduationCap className="h-5 w-5" />,
  },
  "/history": {
    title: "Audit History",
    description: "Saved institutional runs",
    icon: <Clock3 className="h-5 w-5" />,
  },
  "/consistency": {
    title: "Consistency Checks",
    description: "Institution-scoped consistency reviews",
    icon: <ListChecks className="h-5 w-5" />,
  },
  "/about": {
    title: "Compliance Guide",
    description: "AICTE APH 2024–2027 Handbook",
    icon: <Info className="h-5 w-5" />,
  },
  "/signin": {
    title: "Institutional Sign In",
    description: "Portal access & scrutiny roles",
    icon: <Shield className="h-5 w-5" />,
  },
  "/privacy": {
    title: "Privacy notice",
    description: "Prototype policy draft",
    icon: <FileLock2 className="h-5 w-5" />,
  },
  "/terms": {
    title: "Terms and conditions",
    description: "Prototype terms draft",
    icon: <FileText className="h-5 w-5" />,
  },
};

export function TopBar({ onMenuToggle, mobileMenuOpen }: { onMenuToggle: () => void; mobileMenuOpen: boolean }) {
  const location = useLocation();
  const page = location.pathname.startsWith("/consistency")
    ? pageTitles["/consistency"]
    : pageTitles[location.pathname] || pageTitles["/"];
  const { theme, setTheme } = useTheme();
  const { session, signOut } = useAuth();
  const activeUser = session?.user
    ? {
        name: (session.user.user_metadata?.full_name as string) || session.user.email?.split("@")[0] || "User",
        role: "Institutional Member",
      }
    : null;

  return (
    <header className="app-topbar sticky top-0 z-30 h-16 border-b border-border bg-bg-0">
      <div className="h-full px-4 md:px-6 flex items-center justify-between gap-4">
        <div className="flex items-center gap-4 min-w-0">
          <button
            type="button"
            className="inline-flex h-10 w-10 items-center justify-center rounded-lg text-text-secondary transition-colors hover:bg-bg-2 hover:text-text-heading focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 lg:hidden"
            onClick={onMenuToggle}
            aria-label={mobileMenuOpen ? "Close navigation menu" : "Open navigation menu"}
            aria-expanded={mobileMenuOpen}
          >
            {mobileMenuOpen ? <X className="h-5 w-5" aria-hidden="true" /> : <Menu className="h-5 w-5" aria-hidden="true" />}
          </button>
          <div className="flex items-center gap-2 text-text-secondary lg:hidden">
            <Shield className="h-5 w-5 text-primary-400 shrink-0" aria-hidden="true" />
            <span className="font-semibold text-text-heading truncate">AICTE Compliance AI</span>
          </div>
          <div className="hidden md:flex items-center gap-2 text-sm min-w-0">
            <div className="flex items-center gap-1.5 shrink-0">
              <span className="text-text-muted">{page.icon}</span>
              <ChevronRight className="h-3 w-3 text-text-muted" aria-hidden="true" />
              <span className="font-medium text-text-heading">{page.title}</span>
            </div>
            <span className="text-text-muted shrink-0" aria-hidden="true">/</span>
            <span className="text-text-secondary truncate">{page.description}</span>
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-2 sm:gap-3">
          {activeUser ? (
            <div className="flex items-center gap-2">
              <div className="hidden sm:flex flex-col items-end text-xs">
                <span className="font-semibold text-text-heading leading-tight truncate max-w-[140px]">{activeUser.name}</span>
                <span className="text-[11px] font-bold text-text-muted uppercase tracking-wider">{activeUser.role.replace(/_/g, " ")}</span>
              </div>
              <button
                type="button"
                className="app-button app-button-secondary inline-flex min-h-9 items-center rounded-md px-3 py-1.5 text-xs font-bold"
                onClick={() => { void signOut(); }}
                title="Sign out of current account"
              >
                Sign out
              </button>
            </div>
          ) : (
            <Link
              to="/signin"
              className="app-button app-button-secondary inline-flex min-h-9 items-center rounded-md px-3.5 py-1.5 text-xs font-bold"
            >
              Sign In
            </Link>
          )}
          <label className="sr-only" htmlFor="theme-select">Appearance theme</label>
          <select
            id="theme-select"
            className="app-control theme-select min-h-10 max-w-32 border border-border bg-bg-1 px-2 text-xs font-medium text-text-heading focus-visible:outline-none sm:max-w-none sm:px-3 sm:text-sm"
            value={theme}
            onChange={(event) => setTheme(event.target.value as ThemeName)}
          >
            <option value="professional">Professional</option>
            <option value="neo-brutalism">Neo Brutalism</option>
          </select>
          <HealthIndicator />
        </div>
      </div>
    </header>
  );
}
