import type {
  ApplicationRead,
  DocumentRead,
  ProcessingJobStatusResponse,
  ReviewSummaryResponse,
  ScrutinyReportResponse,
  ValidationCheckResultRead,
} from './types';

/* ---------- small formatting helpers ---------- */

export function fmtDate(value: string | null | undefined): string {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function fmtBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(2)} MB`;
}

export function shortHash(h: string): string {
  return h.length > 16 ? `${h.slice(0, 12)}…${h.slice(-4)}` : h;
}

export function humanize(value: string): string {
  return value
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

/* ---------- primitives ---------- */

export function Notice({
  tone = 'info',
  title,
  children,
}: {
  tone?: 'info' | 'warn' | 'error' | 'ok';
  title?: string;
  children: React.ReactNode;
}) {
  return (
    <div className={`notice notice-${tone}`} role={tone === 'error' ? 'alert' : undefined}>
      {title ? <strong className="notice-title">{title}</strong> : null}
      <div>{children}</div>
    </div>
  );
}

export function Spinner({ label }: { label: string }) {
  return (
    <span className="spinner-wrap" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      {label}
    </span>
  );
}

export function EmptyState({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="empty">
      <p className="empty-title">{title}</p>
      <div className="muted">{children}</div>
    </div>
  );
}

/* ---------- domain components ---------- */

export function ApplicationCard({
  app,
  active,
  onSelect,
}: {
  app: ApplicationRead;
  active: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      className={`app-card${active ? ' app-card-active' : ''}`}
      onClick={onSelect}
      aria-current={active ? 'true' : undefined}
    >
      <span className="app-card-id">#{app.id}</span>
      <span className="app-card-type">{humanize(app.application_type)}</span>
      <span className="app-card-year">{app.academic_year}</span>
      <span className={`pill pill-status-${app.status}`}>{humanize(app.status)}</span>
    </button>
  );
}

export function DocumentRow({
  doc,
  processing,
  onCheck,
}: {
  doc: DocumentRead;
  processing?: ProcessingJobStatusResponse;
  onCheck: () => void;
}) {
  const version = doc.current_version;
  const scan = processing?.scan_status ?? version?.scan_status ?? null;
  const state = processing?.state ?? 'unknown';

  return (
    <li className="doc-row">
      <div className="doc-main">
        <div className="doc-title">
          <strong>{humanize(doc.document_type)}</strong>
          {version ? <span className="muted"> v{version.version_number}</span> : null}
        </div>
        {version ? (
          <div className="doc-meta muted">
            {version.file_name ?? 'unnamed'} · {version.media_type} ·{' '}
            {fmtBytes(version.byte_size)}
            {version.page_count ? ` · ${version.page_count} page(s)` : ''}
            <br />
            sha256 <code title={version.sha256}>{shortHash(version.sha256)}</code>
          </div>
        ) : (
          <div className="muted">No version stored.</div>
        )}
      </div>

      <div className="doc-badges">
        <StatusBadge label="Scan" value={scan ?? 'pending'} />
        <StatusBadge label="Processing" value={processing?.processing_status ?? version?.processing_status ?? 'queued'} />
        <StatusBadge label="Job" value={state} />
        {processing && !processing.is_terminal ? (
          <button type="button" className="btn btn-tiny" onClick={onCheck}>
            Refresh
          </button>
        ) : null}
      </div>

      {processing?.last_error_code ? (
        <div className="doc-error" role="alert">
          <strong>{processing.last_error_code}</strong>
          {processing.last_error_code === 'SCANNER_UNAVAILABLE' ? (
            <span>
              {' '}
              — no malware scanner is configured, so the document is held in quarantine and is
              not processed. This is the fail-closed security behaviour, not a UI bug.
            </span>
          ) : null}
          <span className="muted">
            {' '}
            attempt {processing.attempt_count}/{processing.max_attempts}
          </span>
        </div>
      ) : null}
    </li>
  );
}

export function StatusBadge({ label, value }: { label: string; value: string }) {
  const tone = badgeTone(value);
  return (
    <span className={`badge badge-${tone}`} title={`${label}: ${value}`}>
      <span className="badge-label">{label}</span>
      {humanize(value)}
    </span>
  );
}

function badgeTone(value: string): string {
  switch (value) {
    case 'clean':
    case 'succeeded':
    case 'completed':
    case 'passed':
    case 'preliminary_checks_passed':
      return 'ok';
    case 'failed':
    case 'rejected':
    case 'attention_required':
      return 'bad';
    case 'scan_unavailable':
    case 'retry_wait':
    case 'inconclusive':
    case 'processing_incomplete':
      return 'warn';
    case 'queued':
    case 'running':
    case 'scanning':
      return 'info';
    default:
      return 'neutral';
  }
}

export function CheckRow({ check }: { check: ValidationCheckResultRead }) {
  const [open, setOpen] = useStateLocal(false);
  return (
    <li className={`check check-${check.status}`}>
      <div className="check-head">
        <span className={`dot dot-${badgeTone(check.status)}`} aria-hidden="true" />
        <span className="check-name">{check.check_name}</span>
        <span className={`pill pill-check-${check.status}`}>{humanize(check.status)}</span>
      </div>
      <p className="check-msg">{check.message}</p>
      {check.evidence || check.limitations ? (
        <>
          <button type="button" className="btn btn-link" onClick={() => setOpen(!open)}>
            {open ? 'Hide detail' : 'Show detail'}
          </button>
          {open ? (
            <div className="check-detail">
              {check.evidence ? (
                <div>
                  <span className="muted">Evidence</span>
                  <pre>{pretty(check.evidence)}</pre>
                </div>
              ) : null}
              {check.limitations ? (
                <div>
                  <span className="muted">Limitations</span>
                  <pre>{pretty(check.limitations)}</pre>
                </div>
              ) : null}
            </div>
          ) : null}
        </>
      ) : null}
    </li>
  );
}

export function ReportView({
  report,
  review,
}: {
  report: ScrutinyReportResponse;
  review: ReviewSummaryResponse | null;
}) {
  const run = report.validation_run;
  const counts = run.summary_counts;

  return (
    <section className="report" aria-labelledby="report-title">
      <header className="report-head">
        <h3 id="report-title">Pre-scrutiny result</h3>
        <span className={`pill outcome-${run.outcome ?? 'inconclusive'}`}>
          {humanize(run.outcome ?? 'inconclusive')}
        </span>
      </header>

      <dl className="meta-grid">
        <div>
          <dt>Run</dt>
          <dd>#{run.id}</dd>
        </div>
        <div>
          <dt>Evaluated</dt>
          <dd>{run.evaluation_date}</dd>
        </div>
        <div>
          <dt>Ruleset</dt>
          <dd>{run.ruleset_version}</dd>
        </div>
        <div>
          <dt>Triggered by</dt>
          <dd>{run.triggered_by ?? '—'}</dd>
        </div>
      </dl>

      <div className="counts">
        <span className="count count-ok">{counts.passed} passed</span>
        <span className="count count-bad">{counts.failed} failed</span>
        <span className="count count-warn">{counts.inconclusive} inconclusive</span>
        <span className="count count-neutral">{counts.not_applicable} n/a</span>
        <span className="count count-neutral">{counts.not_run} not run</span>
      </div>

      {run.limitations.length > 0 ? (
        <Notice tone="warn" title="What this run could not do">
          <ul className="tight">
            {run.limitations.map((l) => (
              <li key={l}>{l}</li>
            ))}
          </ul>
        </Notice>
      ) : null}

      <h4>Checks</h4>
      {report.check_results.length === 0 ? (
        <EmptyState title="No checks recorded">This run produced no check results.</EmptyState>
      ) : (
        <ul className="check-list">
          {report.check_results.map((c) => (
            <CheckRow key={c.id} check={c} />
          ))}
        </ul>
      )}

      <h4>Machine-generated observations</h4>
      {report.findings.length === 0 ? (
        <EmptyState title="No observations">
          No findings were raised by this run. That is not evidence of compliance or authenticity.
        </EmptyState>
      ) : (
        <ul className="finding-list">
          {report.findings.map((f) => (
            <li key={f.id} className={`finding finding-${f.severity}`}>
              <div className="finding-head">
                <code>{f.code}</code>
                <span className={`pill pill-sev-${f.severity}`}>{humanize(f.severity)}</span>
                <span className="pill pill-neutral">{humanize(f.status)}</span>
              </div>
              <p>{f.summary}</p>
              {f.evidence ? <pre className="evidence">{pretty(f.evidence)}</pre> : null}
            </li>
          ))}
        </ul>
      )}

      <div className="review-strip">
        <strong>Human review</strong>
        {review ? (
          <span className="muted">
            {review.open_count} open · {review.acknowledged_count} acknowledged ·{' '}
            {review.under_review_count} under review · {review.resolved_count} resolved ·{' '}
            {review.escalated_count} escalated · {review.waived_count} waived
          </span>
        ) : (
          <span className="muted">Review summary unavailable.</span>
        )}
        <span className="muted small">
          Findings above are machine-produced observations. They are not an approval decision
          until a reviewer records an action.
        </span>
      </div>

      <Notice tone="info">{report.disclaimer}</Notice>
    </section>
  );
}

/* tiny hook alias keeps this file dependency-free */
import { useState } from 'react';
function useStateLocal(initial: boolean) {
  return useState(initial);
}

function pretty(raw: string): string {
  try {
    const parsed = JSON.parse(raw);
    return JSON.stringify(parsed, null, 2);
  } catch {
    return raw;
  }
}
