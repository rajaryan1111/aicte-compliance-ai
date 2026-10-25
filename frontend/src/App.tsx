import { useEffect, useMemo, useState } from 'react';

type AppType = 'eoa' | 'new_program' | 'intake_change';
type Finding = { code: string; document_type: string; message: string; evidence?: Record<string, string> };
type ValidationResult = {
  institution_id: string;
  application_type: AppType;
  status: 'attention_required' | 'preliminary_checks_passed';
  validation_scope: string;
  missing_documents: string[];
  expired_documents: string[];
  findings: Finding[];
  checked_at: string;
  source: string;
  notice: string;
};
type Health = { ok: boolean; label: string; detail: string };

const DOCUMENTS = [
  { name: 'AICTE approval letter', note: 'Latest approval / EoA record', code: 'approval' },
  { name: 'Affiliation letter', note: 'University or affiliating body', code: 'affiliation' },
  { name: 'Faculty list', note: 'Current faculty roster', code: 'faculty' },
  { name: 'Infrastructure details', note: 'Facilities and equipment', code: 'infrastructure' },
  { name: 'Financial statements', note: 'Financial supporting records', code: 'finance' },
  { name: 'Land / building documents', note: 'Premises supporting records', code: 'land' },
];

const APP_TYPES: { value: AppType; label: string }[] = [
  { value: 'eoa', label: 'Extension of Approval (EoA)' },
  { value: 'new_program', label: 'New programme' },
  { value: 'intake_change', label: 'Intake change' },
];

function prettyDate(value?: string) {
  if (!value) return '—';
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

export default function App() {
  const [institutionId, setInstitutionId] = useState('DEMO-INSTITUTE-001');
  const [applicationType, setApplicationType] = useState<AppType>('eoa');
  const [required, setRequired] = useState<string[]>(DOCUMENTS.slice(0, 4).map((d) => d.name));
  const [submitted, setSubmitted] = useState<string[]>([DOCUMENTS[0].name, DOCUMENTS[1].name]);
  const [expiryDates, setExpiryDates] = useState<Record<string, string>>({});
  const [result, setResult] = useState<ValidationResult | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [health, setHealth] = useState<Health>({ ok: false, label: 'Checking service', detail: 'Connecting to the API…' });

  const apiBase = useMemo(() => (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, ''), []);

  useEffect(() => {
    let active = true;
    const check = async () => {
      try {
        const response = await fetch(`${apiBase}/health`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const body = await response.json();
        if (active) setHealth({ ok: true, label: 'API connected', detail: body.service || 'Backend is responding' });
      } catch (e) {
        if (active) setHealth({ ok: false, label: 'API unavailable', detail: e instanceof Error ? e.message : 'Could not reach the backend' });
      }
    };
    void check();
    return () => { active = false; };
  }, [apiBase]);

  const toggle = (list: string[], setList: (value: string[]) => void, name: string) => {
    setList(list.includes(name) ? list.filter((item) => item !== name) : [...list, name]);
  };

  async function runValidation(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError('');
    setResult(null);
    if (!institutionId.trim()) { setError('Enter an institution ID to continue.'); return; }
    if (required.length === 0) { setError('Choose at least one required document.'); return; }
    setBusy(true);
    try {
      const payload = {
        institution_id: institutionId.trim(),
        application_type: applicationType,
        required_documents: required,
        submitted_documents: submitted.filter((name) => required.includes(name)),
        expiry_dates: Object.fromEntries(
          Object.entries(expiryDates).filter(([name, date]) => required.includes(name) && submitted.includes(name) && Boolean(date)),
        ),
      };
      const response = await fetch(`${apiBase}/api/v1/validate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) {
        const detail = Array.isArray(body.detail)
          ? body.detail.map((item: { msg?: string; loc?: unknown[] }) => `${Array.isArray(item.loc) ? item.loc.slice(1).join('.') + ': ' : ''}${item.msg || 'Invalid input'}`).join(' · ')
          : body.detail || `Request failed (HTTP ${response.status})`;
        throw new Error(String(detail));
      }
      setResult(body as ValidationResult);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Validation could not be completed.');
    } finally {
      setBusy(false);
    }
  }

  const passed = result?.status === 'preliminary_checks_passed';
  const appLabel = APP_TYPES.find((item) => item.value === applicationType)?.label ?? applicationType;

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark"><span>AI</span></div>
          <div><strong>AICTE</strong><small>COMPLIANCE ASSISTANT</small></div>
        </div>
        <div className="side-section-label">WORKSPACE</div>
        <div className="nav-item active"><span className="nav-icon">▦</span> Preliminary validation <span className="nav-dot" /></div>
        <div className="nav-item muted"><span className="nav-icon">▤</span> Document register <span className="soon">NEXT</span></div>
        <div className="nav-item muted"><span className="nav-icon">◎</span> Review history <span className="soon">NEXT</span></div>
        <div className="sidebar-bottom">
          <div className="secure-icon">✓</div>
          <div><strong>Human-led decisions</strong><p>Automated checks support scrutiny. They never grant approval.</p></div>
        </div>
        <div className="sidebar-footer">PROTOTYPE · SYNTHETIC DATA ONLY</div>
      </aside>

      <main className="main-content">
        <header className="topbar">
          <div className="breadcrumb">Workspace <span>/</span> Preliminary validation</div>
          <div className={`connection ${health.ok ? 'online' : 'offline'}`} title={health.detail}><span className="status-dot" />{health.label}</div>
        </header>

        <section className="page-heading">
          <div>
            <div className="eyebrow"><span className="eyebrow-line" /> APPLICATION SCRUTINY</div>
            <h1>Preliminary validation</h1>
            <p className="subtitle">Check submitted documents against a checklist before human review.</p>
          </div>
          <div className="advisory-tag"><span>i</span> Advisory checks only</div>
        </section>

        <div className="notice-bar">
          <div className="notice-icon">i</div>
          <div><strong>What this check does</strong><p>Compares the document list you provide and checks any expiry dates. It does not verify authenticity, apply official AICTE rules, or make an approval decision.</p></div>
        </div>

        <div className="workspace-grid">
          <section className="panel form-panel">
            <div className="panel-heading">
              <div><span className="step-label">STEP 01</span><h2>Application details</h2></div>
              <span className="required-note"><span>*</span> Required fields</span>
            </div>
            <form onSubmit={runValidation}>
              <label className="field-label" htmlFor="institution-id">Institution ID <span>*</span></label>
              <input id="institution-id" value={institutionId} onChange={(e) => setInstitutionId(e.target.value)} placeholder="e.g. DEMO-INSTITUTE-001" required />
              <label className="field-label" htmlFor="application-type">Application type <span>*</span></label>
              <select id="application-type" value={applicationType} onChange={(e) => setApplicationType(e.target.value as AppType)}>
                {APP_TYPES.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
              </select>

              <div className="section-divider" />
              <div className="list-heading"><div><span className="step-label">STEP 02</span><h2>Required documents</h2></div><span className="count-pill">{required.length} selected</span></div>
              <p className="helper-text">Choose which documents this checklist expects.</p>
              <div className="document-list">
                {DOCUMENTS.map((doc) => (
                  <label className={`document-row ${required.includes(doc.name) ? 'checked' : ''}`} key={doc.name}>
                    <input type="checkbox" checked={required.includes(doc.name)} onChange={() => toggle(required, setRequired, doc.name)} />
                    <span className="custom-check">{required.includes(doc.name) ? '✓' : ''}</span>
                    <span className="document-copy"><strong>{doc.name}</strong><small>{doc.note}</small></span>
                  </label>
                ))}
              </div>

              <div className="section-divider" />
              <div className="list-heading"><div><span className="step-label">STEP 03</span><h2>Submitted documents</h2></div><span className="count-pill">{submitted.filter((name) => required.includes(name)).length} of {required.length}</span></div>
              <p className="helper-text">Mark the documents already submitted. Dates are optional and checked only when supplied.</p>
              <div className="submitted-list">
                {required.map((name) => (
                  <div className="submitted-row" key={name}>
                    <label className="submitted-check">
                      <input type="checkbox" checked={submitted.includes(name)} onChange={() => toggle(submitted, setSubmitted, name)} />
                      <span className="custom-check">{submitted.includes(name) ? '✓' : ''}</span>
                      <span>{name}</span>
                    </label>
                    {submitted.includes(name) && <input aria-label={`Expiry date for ${name}`} className="date-input" type="date" value={expiryDates[name] || ''} onChange={(e) => setExpiryDates({ ...expiryDates, [name]: e.target.value })} />}
                  </div>
                ))}
              </div>

              {error && <div className="error-box" role="alert"><strong>Could not validate</strong><span>{error}</span></div>}
              <button className="primary-button" type="submit" disabled={busy}>
                {busy ? <><span className="spinner" /> Checking documents…</> : <>Run preliminary check <span>→</span></>}
              </button>
              <p className="form-footnote"><span>⌁</span> Sent to the connected API. No simulated success response.</p>
            </form>
          </section>

          <section className="results-column">
            <div className="panel results-panel">
              <div className="panel-heading result-heading"><div><span className="step-label">VALIDATION OUTPUT</span><h2>Review summary</h2></div><span className="result-icon">↗</span></div>
              {!result ? (
                <div className="empty-state">
                  <div className="empty-illustration"><div className="paper paper-back" /><div className="paper paper-front"><span /><span /><span /><b>✓</b></div></div>
                  <h3>Results will appear here</h3>
                  <p>Complete the checklist and run a preliminary check to see missing documents and expiry findings returned by the API.</p>
                  <div className="empty-meta"><span className="status-dot" /> Awaiting validation request</div>
                </div>
              ) : (
                <div className="result-body">
                  <div className={`result-status ${passed ? 'pass' : 'attention'}`}>
                    <span className="result-status-icon">{passed ? '✓' : '!'}</span>
                    <div><small>{passed ? 'CHECKLIST MATCH' : 'ACTION REQUIRED'}</small><h3>{passed ? 'Preliminary checks passed' : 'Attention required'}</h3><p>{passed ? 'The supplied lists agree. This is not an approval.' : 'Some required documents are missing or expired.'}</p></div>
                  </div>
                  <div className="metrics-row">
                    <div className="metric"><span>Required</span><strong>{result.missing_documents.length + result.findings.filter((f) => f.code !== 'MISSING_DOCUMENT').length + submitted.filter((n) => required.includes(n)).length}</strong></div>
                    <div className="metric"><span>Missing</span><strong className={result.missing_documents.length ? 'red' : ''}>{result.missing_documents.length}</strong></div>
                    <div className="metric"><span>Expired</span><strong className={result.expired_documents.length ? 'red' : ''}>{result.expired_documents.length}</strong></div>
                  </div>
                  <div className="result-section"><h4>Findings <span>{result.findings.length}</span></h4>
                    {result.findings.length === 0 ? <div className="no-findings"><span>✓</span> No missing or expired items in the supplied checklist.</div> : result.findings.map((finding, i) => <div className="finding-row" key={`${finding.code}-${finding.document_type}-${i}`}><span className="finding-marker">{finding.code === 'MISSING_DOCUMENT' ? '−' : '!'}</span><div><strong>{finding.document_type}</strong><p>{finding.message}</p><small>{finding.code.replaceAll('_', ' ')}</small></div></div>)}
                  </div>
                  <div className="result-section detail-section"><h4>Request details</h4><div className="detail-line"><span>Institution</span><strong>{result.institution_id}</strong></div><div className="detail-line"><span>Application</span><strong>{appLabel}</strong></div><div className="detail-line"><span>Checked at</span><strong>{prettyDate(result.checked_at)}</strong></div></div>
                  <div className="scope-note"><span>i</span><p>{result.notice || 'Advisory output only. A human reviewer must make all decisions.'}</p></div>
                </div>
              )}
            </div>
            <div className="panel api-panel">
              <div className="api-panel-top"><div className="api-symbol">⌘</div><div><h3>Live service connection</h3><p>{health.detail}</p></div><span className={`mini-state ${health.ok ? 'good' : 'bad'}`}>{health.ok ? 'CONNECTED' : 'CHECK'}</span></div>
              <div className="api-endpoint"><span className="method">POST</span><code>/api/v1/validate</code><span className="endpoint-label">Checklist API</span></div>
              <div className="api-endpoint"><span className="method get">GET</span><code>/health</code><span className="endpoint-label">Liveness</span></div>
            </div>
            <div className="footnote-card"><span className="footnote-icon">⌁</span><p><strong>Designed for accountable scrutiny.</strong><br />Automated findings are evidence for a reviewer, not a regulatory decision. Official rules and authenticity checks are outside this prototype's current scope.</p></div>
          </section>
        </div>
        <footer className="page-footer"><span>AICTE COMPLIANCE ASSISTANT</span><span>Prototype build · Synthetic inputs only</span></footer>
      </main>
    </div>
  );
}
