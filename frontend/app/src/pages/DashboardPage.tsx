import { useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowRight,
  BookOpen,
  CalendarDays,
  FileSearch,
  ListChecks,
  Shield,
  Clock3,
  CheckCircle2,
  FileCheck,
  Sparkles,
  ArrowUpRight,
  GraduationCap,
} from "lucide-react";
import { Card, CardContent, CardTitle, CardDescription } from "@/components/Card";
import { Button } from "@/components/Button";
import { ScopeNotice } from "@/components/ScopeNotice";
import { useAuth } from "@/components/useAuth";

const STATS = [
  { label: "AICTE Handbook Cycle", value: "2024–2027", detail: "Approval Process Guidelines" },
  { label: "Scrutiny Automation", value: "Instant", detail: "Checklist & Expiry Evaluation" },
  { label: "Deficiency Detection", value: "Real-time", detail: "Identifies Missing & Expired Items" },
  { label: "Privacy Architecture", value: "Zero-File Retention", detail: "Document Names Only" },
];

const WORKFLOW_STEPS = [
  {
    step: "01",
    title: "Application Context",
    desc: "Define Institution ID and select approval track (EoA, New Program, Intake Variation).",
    tag: "Context",
  },
  {
    step: "02",
    title: "Document Intake",
    desc: "Specify mandatory AICTE checklist items against actual submitted institute documents.",
    tag: "Comparison",
  },
  {
    step: "03",
    title: "Expiry & Validity Audit",
    desc: "Audit statutory approvals, structural stability, land titles, and fire clearances against current date.",
    tag: "Verification",
  },
  {
    step: "04",
    title: "Scrutiny Report Generation",
    desc: "Produce actionable deficiency reports with precise evidence citations and CSV/audit exports.",
    tag: "Deficiency Resolution",
  },
];

const REGULATORY_CHECKS = [
  {
    icon: FileSearch,
    title: "Mandatory Document Scrutiny",
    description:
      "Per AICTE APH Chapter 1 & 2, compares submitted certificates against required checklists to detect missing statutory filings before Scrutiny Committee review.",
  },
  {
    icon: CalendarDays,
    title: "Statutory Validity & Expiry Checks",
    description:
      "Flags expired fire safety NOCs, structural certificates, or past AICTE approvals against server evaluation dates, preventing sudden committee rejections.",
  },
  {
    icon: BookOpen,
    title: "Attributable Evidence Logging",
    description:
      "Outputs transparent, dispute-free evidence snapshots showing observed status and timestamps for internal quality audits and institutional records.",
  },
];

const GOVERNANCE_PILLARS = [
  {
    title: "No Real Document Retention",
    desc: "Only metadata and filenames are evaluated. Raw PDFs or sensitive institutional files are never held or shared.",
  },
  {
    title: "Attributable Audit Trail",
    desc: "Optional 365-day persistent history allows institutional coordinators and reviewers to track scrutiny resolutions.",
  },
  {
    title: "Self-Disclosure Alignment",
    desc: "Supports AICTE's self-disclosure model for Extension of Approval (EoA) to prepare colleges before physical EVC visits.",
  },
  {
    title: "Zero Regulatory Overclaim",
    desc: "Strictly labeled as preliminary scrutiny assistance. Does not declare compliance without AICTE official committee order.",
  },
];

export function DashboardPage() {
  const [activeTab, setActiveTab] = useState<"workflow" | "checks" | "governance">("workflow");
  const { session } = useAuth();

  return (
    <div className="mx-auto max-w-6xl space-y-12 animate-fade-in">
      {/* Hero Section */}
      <section className="relative overflow-hidden rounded-2xl border border-border bg-gradient-to-b from-bg-1 via-bg-1 to-bg-0 p-6 sm:p-10 shadow-sm">
        <div className="relative z-10 space-y-6 max-w-3xl">
          <div className="inline-flex items-center gap-2 rounded-full border border-border bg-bg-2 px-3.5 py-1 text-xs font-bold text-text-heading">
            <Sparkles className="h-3.5 w-3.5 text-accent-strong" aria-hidden="true" />
            <span>AICTE Approval Process Handbook (APH 2024–2027) Compliance Assistant</span>
          </div>

          <h1 className="text-3xl font-extrabold tracking-tight text-text-heading sm:text-4xl lg:text-5xl leading-tight">
            Intelligent Institutional Document Validation & Scrutiny Engine
          </h1>

          <p className="text-base sm:text-lg leading-relaxed text-text-body max-w-2xl">
            Pre-screen institutional approval checklists, detect document expiry gaps, and resolve deficiencies before formal AICTE Scrutiny Committee and EVC visits.
          </p>

          <div className="flex flex-wrap items-center gap-4 pt-2">
            <Link to="/validate">
              <Button size="lg" rightIcon={<ArrowRight className="h-4 w-4" />}>
                Launch Scrutiny Workspace
              </Button>
            </Link>
            <Link to="/history">
              <Button variant="secondary" size="lg" leftIcon={<Clock3 className="h-4 w-4" />}>
                Audit History
              </Button>
            </Link>
            <Link
              to="/about"
              className="text-sm font-semibold text-text-secondary hover:text-text-heading underline underline-offset-4 transition-colors"
            >
              Handbook Guidelines & API
            </Link>
            {session && (
              <Link to="/consistency" className="text-sm font-semibold text-text-secondary underline underline-offset-4 transition-colors hover:text-text-heading">
                Consistency Check
              </Link>
            )}
          </div>
        </div>

        {/* Stats Grid inside Hero */}
        <div className="mt-10 grid grid-cols-2 gap-4 border-t border-border pt-6 sm:grid-cols-4">
          {STATS.map((stat) => (
            <div key={stat.label} className="space-y-1">
              <p className="text-xl sm:text-2xl font-bold tracking-tight text-text-heading">{stat.value}</p>
              <p className="text-xs font-bold uppercase tracking-wider text-text-muted">{stat.label}</p>
              <p className="text-[11px] text-text-muted">{stat.detail}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Scope Disclaimer banner */}
      <section aria-label="Regulatory advisory">
        <ScopeNotice />
      </section>

      {/* Organized Tabbed Section: Workflow vs Regulatory Checks vs Governance */}
      <section className="space-y-6">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between border-b border-border pb-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-widest text-text-muted">Structured Architecture</p>
            <h2 className="text-2xl font-bold tracking-tight text-text-heading">Institutional Review Framework</h2>
          </div>

          {/* Clean Section Navigation Pills */}
          <div className="flex flex-wrap items-center gap-2 rounded-lg border border-border bg-bg-1 p-1.5">
            <button
              type="button"
              onClick={() => setActiveTab("workflow")}
              className={`app-tab-pill ${
                activeTab === "workflow" ? "app-tab-pill-active" : "app-tab-pill-inactive"
              }`}
            >
              <ListChecks className="h-4 w-4" />
              <span>Scrutiny Workflow</span>
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("checks")}
              className={`app-tab-pill ${
                activeTab === "checks" ? "app-tab-pill-active" : "app-tab-pill-inactive"
              }`}
            >
              <FileCheck className="h-4 w-4" />
              <span>Regulatory Coverage</span>
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("governance")}
              className={`app-tab-pill ${
                activeTab === "governance" ? "app-tab-pill-active" : "app-tab-pill-inactive"
              }`}
            >
              <Shield className="h-4 w-4" />
              <span>Governance & Safeguards</span>
            </button>
          </div>
        </div>

        {/* Tab 1: Workflow */}
        {activeTab === "workflow" && (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4 animate-fade-in">
            {WORKFLOW_STEPS.map((s) => (
              <Card key={s.step} className="group transition-all hover:border-border-hover">
                <CardContent className="space-y-4 p-5">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-mono text-xs font-bold text-text-heading bg-bg-2 border border-border rounded px-2.5 py-0.5 whitespace-nowrap shrink-0">
                      STEP {s.step}
                    </span>
                    <span className="text-[11px] font-semibold text-text-muted uppercase tracking-wider truncate">{s.tag}</span>
                  </div>
                  <div>
                    <h3 className="text-base font-semibold text-text-heading">{s.title}</h3>
                    <p className="mt-1.5 text-xs leading-relaxed text-text-secondary">{s.desc}</p>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}

        {/* Tab 2: Regulatory Coverage */}
        {activeTab === "checks" && (
          <div className="grid gap-5 md:grid-cols-3 animate-fade-in">
            {REGULATORY_CHECKS.map((item) => {
              const Icon = item.icon;
              return (
                <Card key={item.title} className="h-full transition-colors hover:border-border-hover">
                  <CardContent className="space-y-4 p-6">
                    <div className="flex h-10 w-10 items-center justify-center rounded-lg border border-border bg-bg-2 text-text-heading">
                      <Icon className="h-5 w-5" aria-hidden="true" />
                    </div>
                    <div>
                      <CardTitle className="text-base">{item.title}</CardTitle>
                      <CardDescription className="mt-2 text-xs leading-relaxed text-text-body">
                        {item.description}
                      </CardDescription>
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        )}

        {/* Tab 3: Governance */}
        {activeTab === "governance" && (
          <div className="grid gap-4 sm:grid-cols-2 animate-fade-in">
            {GOVERNANCE_PILLARS.map((p) => (
              <Card key={p.title}>
                <CardContent className="flex items-start gap-3.5 p-5">
                  <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-success-text" aria-hidden="true" />
                  <div className="space-y-1">
                    <h3 className="text-sm font-semibold text-text-heading">{p.title}</h3>
                    <p className="text-xs leading-relaxed text-text-secondary">{p.desc}</p>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </section>

      {/* Quick Launchpad Stations */}
      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-bold text-text-heading">Institutional Compliance Workstations</h2>
          <span className="text-xs font-semibold text-text-muted">4 Core Modules</span>
        </div>

        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
          <Link to="/validate" className="group block focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-400 rounded-lg">
            <Card className="h-full transition-all group-hover:border-primary-400 group-hover:bg-bg-2">
              <CardContent className="space-y-3 p-5">
                <div className="flex items-center justify-between">
                  <div className="flex h-9 w-9 items-center justify-center rounded-md bg-primary-500/10 text-accent-strong">
                    <ListChecks className="h-5 w-5" />
                  </div>
                  <ArrowUpRight className="h-4 w-4 text-text-muted transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5 group-hover:text-accent-strong" />
                </div>
                <div>
                  <h3 className="font-semibold text-text-heading group-hover:text-accent-strong transition-colors">Run Scrutiny Workspace</h3>
                  <p className="mt-1 text-xs text-text-secondary">AICTE Nil-Deficiency Gap Predictor, expiry watchdog, and OCR certificate extraction.</p>
                </div>
              </CardContent>
            </Card>
          </Link>

          <Link to="/cadre-calculator" className="group block focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-400 rounded-lg">
            <Card className="h-full transition-all group-hover:border-primary-400 group-hover:bg-bg-2">
              <CardContent className="space-y-3 p-5">
                <div className="flex items-center justify-between">
                  <div className="flex h-9 w-9 items-center justify-center rounded-md bg-success-bg/40 text-success-text">
                    <GraduationCap className="h-5 w-5" />
                  </div>
                  <ArrowUpRight className="h-4 w-4 text-text-muted transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5 group-hover:text-success-text" />
                </div>
                <div>
                  <h3 className="font-semibold text-text-heading group-hover:text-success-text transition-colors">Cadre & FSR Evaluator</h3>
                  <p className="mt-1 text-xs text-text-secondary">Evaluate 1:15 / 1:20 ratios, 1:2:6 cadre quota, and Ph.D. requirements to prevent intake reduction.</p>
                </div>
              </CardContent>
            </Card>
          </Link>

          <Link to="/history" className="group block focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-400 rounded-lg">
            <Card className="h-full transition-all group-hover:border-primary-400 group-hover:bg-bg-2">
              <CardContent className="space-y-3 p-5">
                <div className="flex items-center justify-between">
                  <div className="flex h-9 w-9 items-center justify-center rounded-md bg-info-bg/30 text-info-text">
                    <Clock3 className="h-5 w-5" />
                  </div>
                  <ArrowUpRight className="h-4 w-4 text-text-muted transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5 group-hover:text-info-text" />
                </div>
                <div>
                  <h3 className="font-semibold text-text-heading group-hover:text-info-text transition-colors">Saved Audits & Reports</h3>
                  <p className="mt-1 text-xs text-text-secondary">Inspect previously generated scrutiny reports, search by college, and export CSVs.</p>
                </div>
              </CardContent>
            </Card>
          </Link>

          <Link to="/about" className="group block focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-400 rounded-lg">
            <Card className="h-full transition-all group-hover:border-primary-400 group-hover:bg-bg-2">
              <CardContent className="space-y-3 p-5">
                <div className="flex items-center justify-between">
                  <div className="flex h-9 w-9 items-center justify-center rounded-md bg-warning-bg/30 text-warning-text">
                    <BookOpen className="h-5 w-5" />
                  </div>
                  <ArrowUpRight className="h-4 w-4 text-text-muted transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5 group-hover:text-warning-text" />
                </div>
                <div>
                  <h3 className="font-semibold text-text-heading group-hover:text-warning-text transition-colors">AICTE Handbook & Specs</h3>
                  <p className="mt-1 text-xs text-text-secondary">Read APH 2024–2027 statutory criteria, common deficiency pitfalls, and hearing FAQs.</p>
                </div>
              </CardContent>
            </Card>
          </Link>
        </div>
      </section>
    </div>
  );
}
