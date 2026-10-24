import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError, api, getToken, setToken } from './api';
import {
  ApplicationCard,
  DocumentRow,
  EmptyState,
  Notice,
  ReportView,
  Spinner,
  fmtDate,
  humanize,
} from './components';
import type {
  ApplicationRead,
  DocumentRead,
  ProcessingJobStatusResponse,
  ReviewSummaryResponse,
  ScrutinyReportResponse,
  UserRead,
} from './types';

const DOC_TYPES = [
  'approval_letter',
  'land_documents',
  'faculty_list',
  'affidavit',
  'financial_statement',
];

export default function App() {
  const [user, setUser] = useState<UserRead | null>(null);
  const [booting, setBooting] = useState(true);
  const [bootError, setBootError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function restore() {
      if (!getToken()) {
        setBooting(false);
        return;
      }
      try {
        const me = await api.me();
        if (!cancelled) setUser(me);
      } catch (err) {
        if (!cancelled) setBootError(asMessage(err));
        setToken(null);
      } finally {
        if (!cancelled) setBooting(false);
      }
    }
    void restore();
    return () => {
      cancelled = true;
    };
  }, []);

  if (booting) {
    return (
      <div className="shell center">
        <Spinner label="Restoring session…" />
      </div>
    );
  }

  if (!user) {
    return (
      <LoginScreen
        bootError={bootError}
        onSignedIn={(u) => {
          setBootError(null);
          setUser(u);
        }}
      />
    );
  }

  return (
    <Workspace
      user={user}
      onSignOut={() => {
        setToken(null);
        setUser(null);
      }}
    />
  );
}

/* ------------------------------------------------------------------ login */

function LoginScreen({
  bootError,
  onSignedIn,
}: {
  bootError: string | null;
  onSignedIn: (u: UserRead) => void;
}) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const token = await api.login(username.trim(), password);
      setToken(token.access_token);
      const me = await api.me();
      onSignedIn(me);
    } catch (err) {
      setToken(null);
      setError(asMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="shell center">
      <main className="card login-card">
        <h1>AICTE Compliance Assistant</h1>
        <p className="muted">
          Preliminary pre-scrutiny of an EOA-style application checklist. Advisory only — this
          tool does not grant approval, verify authenticity or decide regulatory compliance.
        </p>

        {bootError ? <Notice tone="warn" title="Previous session ended">{bootError}</Notice> : null}

        <form onSubmit={submit} className="stack">
          <label>
            Username
            <input
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
              required
            />
          </label>
          <label>
            Password
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
            />
          </label>
          {error ? <Notice tone="error">{error}</Notice> : null}
          <button type="submit" className="btn btn-primary" disabled={busy}>
            {busy ? 'Signing in…' : 'Sign in'}
          </button>
        </form>

        <Notice tone="info" title="Demo accounts are provisioned by an operator">
          There is no self-registration. Run <code>tools/demo/seed_demo.py</code> against a
          migrated database to create the demo operator, then sign in with those credentials.
        </Notice>
      </main>
    </div>
  );
}

/* -------------------------------------------------------------- workspace */

function Workspace({ user, onSignOut }: { user: UserRead; onSignOut: () => void }) {
  const [apps, setApps] = useState<ApplicationRead[]>([]);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [creating, setCreating] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setListError(null);
    try {
      const res = await api.listApplications();
      setApps(res.items);
      setSelectedId((current) =>
        current && res.items.some((a) => a.id === current) ? current : res.items[0]?.id ?? null,
      );
    } catch (err) {
      setListError(asMessage(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function createApp(type: string, year: string) {
    setCreating(true);
    setListError(null);
    try {
      const created = await api.createApplication(type, year);
      await load();
      setSelectedId(created.id);
    } catch (err) {
      setListError(asMessage(err));
    } finally {
      setCreating(false);
    }
  }

  const selected = apps.find((a) => a.id === selectedId) ?? null;

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true" />
          <div>
            <strong>AICTE Compliance Assistant</strong>
            <span className="muted small">pre-scrutiny · advisory only</span>
          </div>
        </div>
        <div className="topbar-right">
          <span className="muted small">
            {user.display_name ?? user.username}
          </span>
          <button type="button" className="btn btn-ghost" onClick={onSignOut}>
            Sign out
          </button>
        </div>
      </header>

      <div className="layout">
        <aside className="sidebar">
          <h2>Applications</h2>
          <NewApplicationForm disabled={creating} onCreate={createApp} />

          {loading ? (
            <Spinner label="Loading applications…" />
          ) : listError ? (
            <Notice tone="error" title="Could not load applications">
              {listError}
              <button type="button" className="btn btn-tiny" onClick={() => void load()}>
                Retry
              </button>
            </Notice>
          ) : apps.length === 0 ? (
            <EmptyState title="No applications yet">
              Create a synthetic demo application to begin.
            </EmptyState>
          ) : (
            <nav className="app-list">
              {apps.map((app) => (
                <ApplicationCard
                  key={app.id}
                  app={app}
                  active={app.id === selectedId}
                  onSelect={() => setSelectedId(app.id)}
                />
              ))}
            </nav>
          )}
        </aside>

        <main className="content">
          {selected ? (
            <ApplicationPanel key={selected.id} app={selected} />
          ) : (
            <EmptyState title="Nothing selected">
              Choose an application, or create one to start the pre-scrutiny flow.
            </EmptyState>
          )}
        </main>
      </div>
    </div>
  );
}

function NewApplicationForm({
  disabled,
  onCreate,
}: {
  disabled: boolean;
  onCreate: (type: string, year: string) => Promise<void>;
}) {
  const [type, setType] = useState('eoa');
  const [year, setYear] = useState('2026-2027');

  return (
    <form
      className="new-app"
      onSubmit={(e) => {
        e.preventDefault();
        void onCreate(type, year);
      }}
    >
      <label>
        Type
        <select value={type} onChange={(e) => setType(e.target.value)}>
          <option value="eoa">eoa</option>
          <option value="new_program">new_program</option>
          <option value="intake_change">intake_change</option>
        </select>
      </label>
      <label>
        Academic year
        <input
          value={year}
          onChange={(e) => setYear(e.target.value)}
          pattern="\d{4}-\d{4}"
          title="YYYY-YYYY"
          required
        />
      </label>
      <button type="submit" className="btn btn-primary" disabled={disabled}>
        {disabled ? 'Creating…' : 'New application'}
      </button>
    </form>
  );
}

/* ------------------------------------------------------ application panel */

function ApplicationPanel({ app }: { app: ApplicationRead }) {
  const [docs, setDocs] = useState<DocumentRead[]>([]);
  const [processing, setProcessing] = useState<Record<number, ProcessingJobStatusResponse>>({});
  const [loadingDocs, setLoadingDocs] = useState(true);
  const [docsError, setDocsError] = useState<string | null>(null);

  const [docType, setDocType] = useState(DOC_TYPES[0]);
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadNotice, setUploadNotice] = useState<string | null>(null);

  const [report, setReport] = useState<ScrutinyReportResponse | null>(null);
  const [review, setReview] = useState<ReviewSummaryResponse | null>(null);
  const [validating, setValidating] = useState(false);
  const [validateError, setValidateError] = useState<string | null>(null);

  const timers = useRef<number[]>([]);

  const loadDocs = useCallback(async () => {
    setDocsError(null);
    try {
      const res = await api.listDocuments(app.id);
      setDocs(res.items);
      // Fetch current processing state for every stored version.
      await Promise.all(
        res.items.map(async (doc) => {
          const v = doc.current_version;
          if (!v) return;
          try {
            const st = await api.processing(app.id, doc.id, v.id);
            setProcessing((prev) => ({ ...prev, [doc.id]: st }));
          } catch {
            /* status is advisory; a failure here must not blank the list */
          }
        }),
      );
    } catch (err) {
      setDocsError(asMessage(err));
    } finally {
      setLoadingDocs(false);
    }
  }, [app.id]);

  useEffect(() => {
    setLoadingDocs(true);
    setReport(null);
    setReview(null);
    setProcessing({});
    void loadDocs();
    return () => {
      timers.current.forEach((t) => window.clearTimeout(t));
      timers.current = [];
    };
  }, [loadDocs]);

  const poll = useCallback(
    async (documentId: number, versionId: number, attempt = 0) => {
      try {
        const st = await api.processing(app.id, documentId, versionId);
        setProcessing((prev) => ({ ...prev, [documentId]: st }));
        if (!st.is_terminal && attempt < 20) {
          const t = window.setTimeout(() => {
            void poll(documentId, versionId, attempt + 1);
          }, 1500);
          timers.current.push(t);
        }
      } catch {
        /* transient; the Refresh button remains available */
      }
    },
    [app.id],
  );

  async function upload(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    setUploading(true);
    setUploadError(null);
    setUploadNotice(null);
    try {
      const res = await api.uploadDocument(app.id, docType, file);
      setUploadNotice(
        `Accepted: ${res.document.document_type} v${res.version.version_number}. ` +
          `Scan status "${res.version.scan_status ?? 'pending'}", processing "${res.version.processing_status}".`,
      );
      setFile(null);
      await loadDocs();
      if (res.job) {
        void poll(res.document.id, res.version.id);
      }
    } catch (err) {
      setUploadError(asMessage(err));
    } finally {
      setUploading(false);
    }
  }

  async function runValidation() {
    setValidating(true);
    setValidateError(null);
    try {
      const res = await api.validate(app.id);
      setReport(res);
      try {
        setReview(await api.reviewSummary(app.id));
      } catch {
        setReview(null);
      }
    } catch (err) {
      setValidateError(asMessage(err));
    } finally {
      setValidating(false);
    }
  }

  return (
    <div className="panel">
      <header className="panel-head">
        <div>
          <h2>
            Application #{app.id} <span className="muted">· {humanize(app.application_type)}</span>
          </h2>
          <p className="muted small">
            AY {app.academic_year} · institution #{app.institution_id} · status{' '}
            {humanize(app.status)} · created {fmtDate(app.created_at)}
          </p>
        </div>
        <button
          type="button"
          className="btn btn-primary"
          onClick={() => void runValidation()}
          disabled={validating}
        >
          {validating ? 'Running…' : 'Run pre-scrutiny'}
        </button>
      </header>

      <Notice tone="info" title="What this does">
        Compares the documents you upload against deterministic checks. It never contacts AICTE,
        never verifies authenticity, and its result is not an approval.
      </Notice>

      <section className="block">
        <h3>Upload a document</h3>
        <form className="upload-form" onSubmit={upload}>
          <label>
            Document slot
            <select value={docType} onChange={(e) => setDocType(e.target.value)}>
              {DOC_TYPES.map((t) => (
                <option key={t} value={t}>
                  {humanize(t)}
                </option>
              ))}
            </select>
          </label>
          <label>
            File (PDF, PNG, JPEG, TIFF, WEBP)
            <input
              type="file"
              accept=".pdf,.png,.jpg,.jpeg,.tif,.tiff,.webp"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </label>
          <button type="submit" className="btn" disabled={!file || uploading}>
            {uploading ? 'Uploading…' : 'Upload'}
          </button>
        </form>
        {uploadError ? <Notice tone="error" title="Upload rejected">{uploadError}</Notice> : null}
        {uploadNotice ? <Notice tone="ok">{uploadNotice}</Notice> : null}
      </section>

      <section className="block">
        <h3>Documents</h3>
        {loadingDocs ? (
          <Spinner label="Loading documents…" />
        ) : docsError ? (
          <Notice tone="error" title="Could not load documents">
            {docsError}
            <button type="button" className="btn btn-tiny" onClick={() => void loadDocs()}>
              Retry
            </button>
          </Notice>
        ) : docs.length === 0 ? (
          <EmptyState title="No documents uploaded">
            Upload a synthetic test document to see scan, processing and extraction states.
          </EmptyState>
        ) : (
          <ul className="doc-list">
            {docs.map((d) => (
              <DocumentRow
                key={d.id}
                doc={d}
                processing={processing[d.id]}
                onCheck={() => {
                  const v = d.current_version;
                  if (v) void poll(d.id, v.id);
                }}
              />
            ))}
          </ul>
        )}
      </section>

      {validateError ? (
        <Notice tone="error" title="Validation failed">{validateError}</Notice>
      ) : null}

      {report ? <ReportView report={report} review={review} /> : null}
    </div>
  );
}

/* ------------------------------------------------------------------ utils */

function asMessage(err: unknown): string {
  if (err instanceof ApiError) return err.detail;
  if (err instanceof Error) return err.message;
  return 'Unexpected error.';
}
