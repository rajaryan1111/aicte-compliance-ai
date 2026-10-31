import { useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  CalendarDays,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  ClipboardList,
  CloudOff,
  Download,
  Info,
  Languages,
  Loader2,
  RefreshCw,
  RotateCcw,
  Scale,
  User,
} from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./Card";
import { Button } from "./Button";
import { Badge } from "./Badge";
import { cn } from "@/lib/utils";
import { useAuth } from "./useAuth";
import {
  ACTION_PLAN_STORAGE_KEY,
  DEFAULT_DEADLINE_POLICY,
  applyDeadlinePolicy,
  buildActionPlan,
  createActionPlanCsv,
  daysBetween,
  formatIsoDate,
  mergePlanProgress,
  normalizeDeadlinePolicy,
  parseStoredPlans,
  resetPlanProgress,
  serializeStoredPlans,
  setItemNote,
  setItemStatus,
  summarizePlan,
  upsertPlan,
  type ActionPlan,
  type DeadlinePolicy,
  type PlanStatus,
} from "@/lib/action-plan";
import {
  isRetryableSyncFailure,
  mergeRemotePlan,
  pushTaskUpdate,
  readStoredDeadlinePolicy,
  storeDeadlinePolicy,
  syncPlan,
  updateDeadlinePolicy,
  type RemotePlanSnapshot,
} from "@/lib/plan-sync";
import {
  PLAN_UI,
  lookupDocumentGuidance,
  pickLocalized,
  type GuidanceLanguage,
  type LocalizedText,
} from "@/lib/compliance-guidance";
import type { ValidationRequest, ValidationResponse } from "@/lib/api";

const LANGUAGE_STORAGE_KEY = "aicte.guidance.lang";
const STATUS_OPTIONS: PlanStatus[] = ["open", "in_progress", "blocked", "done"];

function readStoredPlans(): ActionPlan[] {
  try {
    return parseStoredPlans(localStorage.getItem(ACTION_PLAN_STORAGE_KEY));
  } catch {
    return [];
  }
}

function writeStoredPlans(plans: ActionPlan[]): void {
  try {
    localStorage.setItem(ACTION_PLAN_STORAGE_KEY, serializeStoredPlans(plans));
  } catch {
    // Storage can be unavailable (private mode, quota). Progress then lasts for this view only.
  }
}

function readLanguage(): GuidanceLanguage {
  try {
    return localStorage.getItem(LANGUAGE_STORAGE_KEY) === "hi" ? "hi" : "en";
  } catch {
    return "en";
  }
}

function writeLanguage(language: GuidanceLanguage): void {
  try {
    localStorage.setItem(LANGUAGE_STORAGE_KEY, language);
  } catch {
    // Preference is best-effort.
  }
}

function localized(text: LocalizedText | undefined, language: GuidanceLanguage): string {
  return text ? pickLocalized(text, language) : "";
}

function priorityVariant(priority: "P1" | "P2" | "P3") {
  return priority === "P1" ? "error" : priority === "P2" ? "warning" : "info";
}

/** "Clause 2.4" is stored in English; render the label in the active language. */
function clauseText(clause: string, language: GuidanceLanguage): string {
  const number = clause.replace(/^Clause\s+/i, "");
  return language === "hi" ? `धारा ${number}` : `Clause ${number}`;
}

type SyncState = "idle" | "syncing" | "synced" | "local" | "error";

interface RemediationActionPlanProps {
  request: ValidationRequest;
  response: ValidationResponse;
}

export function RemediationActionPlan({ request, response }: RemediationActionPlanProps) {
  const { session, authMode } = useAuth();
  // The plan API authenticates with this backend's own JWT. A Supabase session carries a differently
  // signed token, so it is not sent here: the panel stays in local mode rather than showing a
  // misleading "session expired" error for a token this API was never able to accept.
  const token = authMode === "backend" ? (session?.access_token ?? null) : null;

  const [policyBusy, setPolicyBusy] = useState(false);
  const [policy, setPolicy] = useState<DeadlinePolicy>(
    () => readStoredDeadlinePolicy() ?? DEFAULT_DEADLINE_POLICY,
  );
  const [draft, setDraft] = useState<DeadlinePolicy>(policy);
  const [plan, setPlan] = useState<ActionPlan>(() => {
    const built = applyDeadlinePolicy(buildActionPlan(request, response), policy);
    const stored = readStoredPlans().find((entry) => entry.planId === built.planId);
    // Re-running the same checklist reopens the same plan with its recorded progress.
    return stored ? mergePlanProgress(built, stored) : built;
  });
  const [language, setLanguage] = useState<GuidanceLanguage>(readLanguage);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [remote, setRemote] = useState<RemotePlanSnapshot | null>(null);
  const [sync, setSync] = useState<{ state: SyncState; message?: string; retryable?: boolean }>({
    state: "idle",
  });
  // Captured once per mount so the render stays pure; a plan is a snapshot of one run anyway.
  const [now] = useState(() => new Date());
  const today = formatIsoDate(now);

  const planRef = useRef(plan);
  planRef.current = plan;
  const policyRef = useRef(policy);
  policyRef.current = policy;
  const syncInFlight = useRef(false);

  useEffect(() => {
    // Always upsert: the stored plan must carry this run's provenance and its latest progress.
    writeStoredPlans(upsertPlan(readStoredPlans(), plan));
  }, [plan]);

  /**
   * Create-or-get the shared plan, then push any progress this browser already holds.
   *
   * Only runs once per mount: re-running the same checklist is idempotent on the server, and
   * pushing local progress first keeps pre-sign-in work when a plan is first saved.
   */
  useEffect(() => {
    if (!token) {
      setSync({ state: "local" });
      return;
    }
    const institutionRef = request.institution_id;
    if (!institutionRef) {
      setSync({ state: "local" });
      return;
    }

    let cancelled = false;
    void (async () => {
      setSync({ state: "syncing" });
      const created = await syncPlan(institutionRef, planRef.current, policyRef.current, token);
      if (cancelled) return;
      if (!created.ok) {
        setSync({
          state: "error",
          message: created.message,
          retryable: isRetryableSyncFailure(created.kind),
        });
        return;
      }

      let latest = created.plan;
      const localItems = planRef.current.items;
      for (const item of localItems) {
        const stored = latest.tasks.find((entry) => entry.taskKey === item.id);
        if (!stored) continue;
        if (stored.status === item.status && stored.note === item.note) continue;
        const pushed = await pushTaskUpdate(
          institutionRef,
          latest.id,
          item.id,
          { status: item.status, note: item.note },
          token,
        );
        if (cancelled) return;
        if (pushed.ok) latest = pushed.plan;
      }

      setRemote(latest);
      setPlan((prev) => mergeRemotePlan(prev, latest));
      setSync({ state: "synced" });
    })();

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, request.institution_id]);

  if (plan.items.length === 0) return null;

  const summary = summarizePlan(plan, now);
  const overdueLabel = PLAN_UI.overdue[language];

  const update = (next: ActionPlan) => {
    setPlan(next);
  };

  const pushChange = async (taskKey: string, change: { status?: PlanStatus; note?: string }) => {
    if (!token || !remote || syncInFlight.current) return;
    syncInFlight.current = true;
    setSync({ state: "syncing" });
    const result = await pushTaskUpdate(request.institution_id, remote.id, taskKey, change, token);
    syncInFlight.current = false;
    if (result.ok) {
      setRemote(result.plan);
      setSync({ state: "synced" });
    } else {
      // The local copy stays authoritative for this browser so no work is lost.
      setSync({
        state: "error",
        message: result.message,
        retryable: isRetryableSyncFailure(result.kind),
      });
    }
  };

  const changeStatus = (itemId: string, status: PlanStatus) => {
    const item = plan.items.find((entry) => entry.id === itemId);
    if (!item) return;
    update(setItemStatus(plan, item.id, status));
    void pushChange(item.id, { status });
  };

  const resetProgress = async () => {
    const reset = resetPlanProgress(plan);
    update(reset);
    if (!token || !remote) return;
    for (const item of reset.items) {
      await pushChange(item.id, { status: "open", note: item.note });
    }
  };

  const applyRemoteSchedule = async () => {
    if (!token || !remote) return;
    const next = normalizeDeadlinePolicy(draft);
    setPolicyBusy(true);
    const result = await updateDeadlinePolicy(request.institution_id, remote.id, next, token);
    setPolicyBusy(false);
    if (!result.ok) {
      // Nothing is applied locally: the shared schedule is unchanged, so the panel must not show a
      // date the server never accepted.
      setDraft(policy);
      setSync({
        state: "error",
        message:
          result.kind === "forbidden"
            ? PLAN_UI.scheduleAdminOnly[language]
            : result.message,
        retryable: isRetryableSyncFailure(result.kind),
      });
      return;
    }
    setPolicy(result.plan.deadlinePolicy);
    setDraft(result.plan.deadlinePolicy);
    setRemote(result.plan);
    setPlan((prev) => mergeRemotePlan(prev, result.plan));
    setSync({ state: "synced" });
  };

  const applySchedule = () => {
    if (remote) {
      void applyRemoteSchedule();
      return;
    }
    const next = normalizeDeadlinePolicy(draft);
    setPolicy(next);
    setDraft(next);
    storeDeadlinePolicy(next);
    update(applyDeadlinePolicy(plan, next));
  };

  const retrySync = () => {
    window.location.reload();
  };

  const chooseLanguage = (next: GuidanceLanguage) => {
    setLanguage(next);
    writeLanguage(next);
  };

  const downloadCsv = () => {
    const blob = new Blob([createActionPlanCsv(plan)], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `remediation-plan-${plan.checkedAt.slice(0, 10)}.csv`;
    anchor.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 0);
  };

  return (
    <Card lang={language === "hi" ? "hi" : "en"}>
      <CardHeader className="border-b border-border pb-4">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="flex h-6 w-6 items-center justify-center rounded-md bg-primary-500/15 text-accent-strong">
                <ClipboardList className="h-3.5 w-3.5" aria-hidden="true" />
              </span>
              <p className="text-xs font-bold uppercase tracking-wider text-text-muted">
                {PLAN_UI.progress[language]} · {summary.completionPct}%
              </p>
            </div>
            <CardTitle className="mt-1 text-xl font-bold text-text-heading">
              {PLAN_UI.title[language]}
            </CardTitle>
            <CardDescription className="max-w-2xl text-sm text-text-secondary">
              {PLAN_UI.subtitle[language]}
            </CardDescription>

            <p
              className={cn(
                "mt-2 inline-flex items-start gap-1.5 text-[11px] font-medium",
                sync.state === "synced" && "text-success-text",
                sync.state === "error" && "text-warning-text",
                (sync.state === "local" || sync.state === "syncing" || sync.state === "idle") &&
                  "text-text-muted",
              )}
              role="status"
              aria-live="polite"
            >
              {sync.state === "synced" && <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />}
              {sync.state === "syncing" && <Loader2 className="mt-0.5 h-3.5 w-3.5 shrink-0 animate-spin" aria-hidden="true" />}
              {(sync.state === "local" || sync.state === "error") && (
                <CloudOff className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
              )}
              <span>
                {sync.state === "synced" && PLAN_UI.syncedToWorkspace[language]}
                {sync.state === "syncing" && PLAN_UI.syncing[language]}
                {sync.state === "local" && PLAN_UI.storedLocally[language]}
                {sync.state === "error" && (
                  <>
                    {sync.message} {PLAN_UI.syncUnavailable[language]}
                    {sync.retryable && (
                      <button
                        type="button"
                        onClick={retrySync}
                        className="ml-2 inline-flex items-center gap-1 font-semibold text-accent-strong underline-offset-2 hover:underline"
                      >
                        <RefreshCw className="h-3 w-3" aria-hidden="true" />
                        {language === "hi" ? "पुनः प्रयास" : "Reload"}
                      </button>
                    )}
                  </>
                )}
              </span>
            </p>
          </div>

          <div
            className="flex shrink-0 items-center gap-1 rounded-lg border border-border bg-bg-2 p-1"
            role="group"
            aria-label={PLAN_UI.language[language]}
          >
            <Languages className="ml-2 mr-1 h-3.5 w-3.5 text-text-muted" aria-hidden="true" />
            {(["en", "hi"] as const).map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => chooseLanguage(option)}
                aria-pressed={language === option}
                className={cn(
                  "rounded px-2.5 py-1 text-xs font-semibold transition-colors",
                  language === option
                    ? "bg-bg-1 text-text-heading shadow-sm ring-1 ring-border"
                    : "text-text-secondary hover:text-text-heading",
                )}
              >
                {option === "en" ? "English" : "हिन्दी"}
              </button>
            ))}
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-5 p-5 sm:p-6">
        <div className="space-y-2">
          <div className="h-2 w-full overflow-hidden rounded-full border border-border bg-bg-3">
            <div
              className={cn(
                "h-full transition-all duration-300",
                summary.overdue > 0 ? "bg-warning-text" : "bg-success-text",
              )}
              style={{ width: `${summary.completionPct}%` }}
              role="progressbar"
              aria-valuenow={summary.completionPct}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-label={PLAN_UI.progress[language]}
            />
          </div>
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <Badge variant="success" size="sm">
              {summary.done}/{summary.total} {PLAN_UI.done[language].toLowerCase()}
            </Badge>
            {summary.overdue > 0 && (
              <Badge variant="error" size="sm">
                {summary.overdue} {overdueLabel.toLowerCase()}
              </Badge>
            )}
            {summary.nextDueDate && summary.done < summary.total && (
              <span className="inline-flex items-center gap-1 text-text-muted">
                <CalendarDays className="h-3.5 w-3.5" aria-hidden="true" />
                {PLAN_UI.due[language]}: <time dateTime={summary.nextDueDate}>{summary.nextDueDate}</time>
              </span>
            )}
          </div>
        </div>

        <section className="rounded-lg border border-border bg-bg-2/60 p-3.5">
          <h4 className="text-[10px] font-bold uppercase tracking-wider text-text-muted">
            {PLAN_UI.scheduleTitle[language]}
          </h4>
          <div className="mt-2 flex flex-wrap items-end gap-2">
            {(
              [
                ["p1Days", PLAN_UI.p1Days],
                ["p2Days", PLAN_UI.p2Days],
                ["p3BufferDays", PLAN_UI.expiryBuffer],
              ] as const
            ).map(([key, label]) => (
              <label key={key} className="flex flex-col gap-1 text-[10px] font-semibold uppercase tracking-wider text-text-muted">
                {label[language]}
                <input
                  type="number"
                  min={key === "p3BufferDays" ? 0 : 1}
                  max={365}
                  value={draft[key]}
                  disabled={policyBusy}
                  onChange={(event) =>
                    setDraft({ ...draft, [key]: Number(event.target.value) })
                  }
                  className="w-20 rounded-md border border-border bg-bg-1 px-2 py-1 text-xs font-medium text-text-heading disabled:opacity-60"
                />
              </label>
            ))}
            <Button variant="secondary" size="sm" onClick={applySchedule} disabled={policyBusy}>
              {policyBusy && <Loader2 className="mr-1.5 h-3 w-3 animate-spin" aria-hidden="true" />}
              {remote ? PLAN_UI.scheduleApplyShared[language] : PLAN_UI.scheduleApply[language]}
            </Button>
          </div>
          <p className="mt-2 flex items-start gap-1.5 text-[11px] leading-relaxed text-text-muted">
            <Info className="mt-0.5 h-3 w-3 shrink-0" aria-hidden="true" />
            {remote ? PLAN_UI.scheduleSharedNote[language] : PLAN_UI.scheduleNote[language]}
          </p>
          {remote?.deadlineHistory[0] && (
            <p className="mt-1 text-[11px] text-text-muted">
              {PLAN_UI.scheduleHistory[language]}:{" "}
              <span className="font-semibold text-text-secondary">
                {remote.deadlineHistory[0].changedBy}
              </span>{" "}
              · <time dateTime={remote.deadlineHistory[0].changedAt}>
                {remote.deadlineHistory[0].changedAt.slice(0, 10)}
              </time>
              {remote.deadlineHistory[0].rescheduledTasks > 0 && (
                <> · {remote.deadlineHistory[0].rescheduledTasks}</>
              )}
            </p>
          )}
        </section>

        <ul className="space-y-2.5">
          {plan.items.map((item) => {
            const guidance = lookupDocumentGuidance(item.documentId);
            const expanded = expandedId === item.id;
            const isOverdue = item.status !== "done" && daysBetween(today, item.dueDate) < 0;

            return (
              <li
                key={item.id}
                className={cn(
                  "overflow-hidden rounded-lg border bg-bg-1",
                  item.status === "done" ? "border-success-border/60" : "border-border",
                )}
              >
                <div className="flex flex-col gap-3 p-3.5 sm:flex-row sm:items-start sm:justify-between">
                  <button
                    type="button"
                    onClick={() => setExpandedId(expanded ? null : item.id)}
                    aria-expanded={expanded}
                    className="flex min-w-0 flex-1 items-start gap-3 text-left"
                  >
                    <span
                      className={cn(
                        "mt-0.5 flex h-2 w-2 shrink-0 rounded-full",
                        item.status === "done"
                          ? "bg-success-text"
                          : item.priority === "P1"
                            ? "bg-error-text"
                            : item.priority === "P2"
                              ? "bg-warning-text"
                              : "bg-info-text",
                      )}
                      aria-hidden="true"
                    />
                    <span className="min-w-0">
                      <span className="flex flex-wrap items-center gap-2">
                        <span
                          className={cn(
                            "truncate text-sm font-bold",
                            item.status === "done"
                              ? "text-text-muted line-through"
                              : "text-text-heading",
                          )}
                        >
                          {localized(guidance?.label, language) || item.documentLabel}
                        </span>
                        <Badge variant={priorityVariant(item.priority)} size="sm">
                          {PLAN_UI.priorities[item.priority][language]}
                        </Badge>
                        {guidance?.clause && (
                          <span className="rounded border border-border bg-bg-2 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-accent-strong">
                            {clauseText(guidance.clause, language)}
                          </span>
                        )}
                        {isOverdue && (
                          <Badge variant="error" size="sm">
                            {overdueLabel}
                          </Badge>
                        )}
                      </span>
                      <span className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-text-muted">
                        <span className="inline-flex items-center gap-1">
                          <User className="h-3 w-3" aria-hidden="true" />
                          {localized(guidance?.ownerRole, language) || item.ownerRole}
                        </span>
                        <span className="inline-flex items-center gap-1">
                          <CalendarDays className="h-3 w-3" aria-hidden="true" />
                          {PLAN_UI.due[language]}:{" "}
                          <time dateTime={item.dueDate}>{item.dueDate}</time>
                        </span>
                      </span>
                    </span>
                    {expanded ? (
                      <ChevronUp className="mt-1 h-4 w-4 shrink-0 text-text-muted" aria-hidden="true" />
                    ) : (
                      <ChevronDown className="mt-1 h-4 w-4 shrink-0 text-text-muted" aria-hidden="true" />
                    )}
                  </button>

                  <label className="flex shrink-0 items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-text-muted">
                    <span className="sr-only sm:not-sr-only">{PLAN_UI.statusLabel[language]}</span>
                    <select
                      value={item.status}
                      onChange={(event) => changeStatus(item.id, event.target.value as PlanStatus)}
                      className="rounded-md border border-border bg-bg-2 px-2 py-1 text-xs font-medium text-text-heading"
                      aria-label={`${PLAN_UI.statusLabel[language]}: ${item.documentLabel}`}
                    >
                      {STATUS_OPTIONS.map((status) => (
                        <option key={status} value={status}>
                          {PLAN_UI[status][language]}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>

                {expanded && (
                  <div className="space-y-3.5 border-t border-border bg-bg-2/60 p-4 text-xs">
                    <section className="space-y-1">
                      <h4 className="font-bold uppercase tracking-wider text-[10px] text-text-muted">
                        {PLAN_UI.evidence[language]}
                      </h4>
                      <p className="leading-relaxed text-text-body">{item.evidenceRequired}</p>
                    </section>

                    {guidance ? (
                      <>
                        <section className="space-y-1">
                          <h4 className="font-bold uppercase tracking-wider text-[10px] text-error-text">
                            {PLAN_UI.why[language]}
                          </h4>
                          <p className="leading-relaxed text-text-body">
                            {localized(guidance.impact, language)}
                          </p>
                        </section>
                        <section className="space-y-1">
                          <h4 className="font-bold uppercase tracking-wider text-[10px] text-text-muted">
                            {PLAN_UI.fix[language]}
                          </h4>
                          <p className="leading-relaxed text-text-body">
                            {localized(guidance.mitigation, language)}
                          </p>
                        </section>
                        <section className="space-y-1">
                          <h4 className="flex items-center gap-1.5 font-bold uppercase tracking-wider text-[10px] text-text-muted">
                            <Scale className="h-3.5 w-3.5" aria-hidden="true" />
                            {PLAN_UI.requirement[language]}
                            {guidance.clause ? ` · ${clauseText(guidance.clause, language)}` : ""}
                          </h4>
                          <p className="leading-relaxed text-text-secondary">
                            {localized(guidance.requirement, language)}
                          </p>
                          {!guidance.clause && (
                            <p className="text-[11px] italic text-text-muted">{PLAN_UI.noClause[language]}</p>
                          )}
                        </section>
                      </>
                    ) : (
                      <p className="leading-relaxed text-text-muted">{PLAN_UI.unknownDocument[language]}</p>
                    )}

                    <label className="block space-y-1">
                      <span className="font-bold uppercase tracking-wider text-[10px] text-text-muted">
                        {PLAN_UI.note[language]}
                      </span>
                      <input
                        type="text"
                        maxLength={280}
                        value={item.note}
                        onChange={(event) => update(setItemNote(plan, item.id, event.target.value))}
                        onBlur={() => {
                          const current = plan.items.find((entry) => entry.id === item.id);
                          if (current) void pushChange(current.id, { note: current.note });
                        }}
                        className="w-full rounded-md border border-border bg-bg-1 px-2.5 py-1.5 text-xs text-text-heading"
                        placeholder={language === "hi" ? "उदाहरण: नवीनीकरण आवेदन जमा" : "e.g. renewal filed with the fire office"}
                      />
                    </label>
                  </div>
                )}
              </li>
            );
          })}
        </ul>

        <div className="flex flex-col gap-3 border-t border-border pt-4 sm:flex-row sm:items-center sm:justify-between">
          <p className="flex items-start gap-2 text-[11px] leading-relaxed text-text-muted">
            <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
            <span>
              {sync.state === "synced"
                ? PLAN_UI.syncedToWorkspace[language]
                : PLAN_UI.storedLocally[language]}
              {language === "hi" && (
                <span className="mt-1 block italic">{PLAN_UI.unofficial.hi}</span>
              )}
            </span>
          </p>
          <div className="flex shrink-0 flex-wrap gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => void resetProgress()}
              leftIcon={<RotateCcw className="h-3.5 w-3.5" />}
            >
              {PLAN_UI.reset[language]}
            </Button>
            <Button variant="secondary" size="sm" onClick={downloadCsv} leftIcon={<Download className="h-3.5 w-3.5" />}>
              {PLAN_UI.exportCsv[language]}
            </Button>
          </div>
        </div>

        <p className="flex items-start gap-2 text-[11px] leading-relaxed text-text-muted">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          {language === "hi"
            ? "यह योजना प्रारंभिक तुलना से बनी है, आधिकारिक एआईसीटीई निर्धारण नहीं।"
            : "This plan is derived from a preliminary comparison, not an AICTE determination."}
          {summary.blocked > 0 && (
            <span className="font-semibold text-warning-text">
              {" "}
              {summary.blocked} {PLAN_UI.blocked[language].toLowerCase()}
            </span>
          )}
        </p>
      </CardContent>
    </Card>
  );
}
