import { useState } from "react";
import { useAuth } from "@/components/useAuth";
import { fetchGapAnalysis, fetchGapDocuments, fetchGapMappings, fetchGapRequirements, reviewGapMapping, runGapAssessment, submitGapMapping, type GapAnalysis, type GapDocument, type GapMapping, type GapRequirement } from "@/lib/api";

export function GapAnalyzerPage() {
  const { session } = useAuth();
  const token = session?.access_token ?? "";
  const [applicationId, setApplicationId] = useState("");
  const [requirements, setRequirements] = useState<GapRequirement[]>([]);
  const [analysis, setAnalysis] = useState<GapAnalysis | null>(null);
  const [documents, setDocuments] = useState<GapDocument[]>([]);
  const [mappings, setMappings] = useState<GapMapping[]>([]);
  const [ruleId, setRuleId] = useState("");
  const [versionId, setVersionId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const load = async (run = false) => {
    const id = Number(applicationId);
    if (!Number.isInteger(id) || id < 1 || !token) { setError("Enter an application ID and sign in to continue."); return; }
    setBusy(true); setError("");
    try {
      if (run) {
        const result = await runGapAssessment(id, token);
        if (!result.ok) throw new Error(result.errors._server ?? "Unable to run assessment.");
      }
      const [req, gap, docs, links] = await Promise.all([fetchGapRequirements(id, token), fetchGapAnalysis(id, token), fetchGapDocuments(id, token), fetchGapMappings(id, token)]);
      if (!req.ok) throw new Error(req.errors._server ?? "Unable to load approved requirements.");
      setRequirements(req.data);
      setDocuments(docs.ok ? docs.data.items : []);
      setMappings(links.ok ? links.data : []);
      if (gap.ok) setAnalysis(gap.data); else setAnalysis(null);
    } catch (e) { setError(e instanceof Error ? e.message : "Request failed."); }
    finally { setBusy(false); }
  };
  const createMapping = async () => {
    const id = Number(applicationId);
    if (!ruleId || !versionId) { setError("Select a requirement and a processed document version."); return; }
    setBusy(true); setError("");
    const result = await submitGapMapping(id, token, { rule_approval_id: Number(ruleId), document_version_id: Number(versionId), rationale: "Institutional evidence manually mapped for reviewer assessment." });
    setBusy(false);
    if (!result.ok) { setError(result.errors._server ?? "Could not save the evidence mapping."); return; }
    setMappings((items) => [result.data, ...items]);
  };
  const reviewMapping = async (mappingId: number, status: "confirmed" | "rejected") => {
    const result = await reviewGapMapping(Number(applicationId), mappingId, token, status);
    if (!result.ok) { setError(result.errors._server ?? "Could not review the evidence mapping."); return; }
    setMappings((items) => items.map((item) => item.id === mappingId ? result.data : item));
  };
  return <main className="mx-auto max-w-6xl space-y-6 p-6">
    <header><p className="text-sm font-medium text-primary-600">Compliance workspace</p><h1 className="mt-1 text-3xl font-bold">Gap Analyzer</h1><p className="mt-2 text-text-secondary">Requirement level results use only active, verified, approved rule versions and saved assessment data.</p></header>
    <section className="flex flex-wrap items-end gap-3 rounded-xl border border-border bg-bg-1 p-4">
      <label className="grid gap-1 text-sm">Application ID<input className="rounded-md border border-border bg-bg-1 px-3 py-2" type="number" min="1" value={applicationId} onChange={(e) => setApplicationId(e.target.value)} /></label>
      <button className="rounded-md bg-primary-600 px-4 py-2 text-white disabled:opacity-50" disabled={busy} onClick={() => void load(false)}>Load gap analysis</button>
      <button className="rounded-md border border-border px-4 py-2 disabled:opacity-50" disabled={busy} onClick={() => void load(true)}>Run assessment</button>
      {busy && <span role="status">Loading…</span>}
    </section>
    {error && <p role="alert" className="rounded-md border border-red-300 bg-red-50 p-3 text-red-800">{error}</p>}
    {!analysis && requirements.length === 0 && !busy && !error && <p className="rounded-xl border border-dashed border-border p-8 text-text-secondary">Choose an application to view approved requirements. No requirements are fabricated; if the verified registry is empty, this page will say so.</p>}
    {analysis && <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4" aria-label="Assessment metrics">
      {[["Coverage", analysis.metrics.coverage_percent == null ? "—" : `${analysis.metrics.coverage_percent}%`], ["Requirements", analysis.metrics.total_requirements], ["Compliant", analysis.metrics.compliant], ["Potential gaps", analysis.metrics.potential_gaps], ["Missing evidence", analysis.metrics.missing_evidence], ["Manual review", analysis.metrics.manual_verification_required], ["Not applicable", analysis.metrics.not_applicable], ["Pending review", analysis.metrics.pending_review]].map(([label, value]) => <article key={String(label)} className="rounded-xl border border-border bg-bg-1 p-4"><p className="text-sm text-text-secondary">{label}</p><p className="mt-1 text-2xl font-semibold">{value}</p></article>)}
    </section>}
    <section className="space-y-3"><h2 className="text-xl font-semibold">Approved requirements</h2>{requirements.length === 0 ? <p className="rounded-xl border border-border p-5 text-text-secondary">No active requirements match this application, or no requirement versions have completed source verification and approval.</p> : requirements.map((r) => {
      const assessment = analysis?.requirements.find((x) => x.rule_id === r.rule_id);
      return <article key={`${r.id}-${r.version}`} className="rounded-xl border border-border bg-bg-1 p-5"><div className="flex flex-wrap items-start justify-between gap-2"><div><p className="text-xs text-text-secondary">{r.rule_id} · v{r.version}</p><h3 className="mt-1 font-semibold">{r.title}</h3></div><span className="rounded-full bg-bg-2 px-3 py-1 text-sm">{assessment?.outcome_status ?? (r.applicable ? "Not assessed" : "Not applicable")}</span></div><p className="mt-3 text-sm text-text-secondary">{r.description}</p><p className="mt-3 text-sm">Applicability: {r.applicability_reason}</p>{assessment && <p className="mt-2 text-sm">Evidence: {assessment.evidence_sufficiency} · {assessment.result_message}</p>}<p className="mt-3 text-sm"><strong>{r.source_title} §{r.source_clause}, p. {r.source_page}</strong></p></article>;
    })}</section>
    {requirements.length > 0 && <section className="space-y-3 rounded-xl border border-border bg-bg-1 p-5"><h2 className="text-xl font-semibold">Map evidence from the Document Vault</h2><p className="text-sm text-text-secondary">Only clean, successfully processed versions from this application are selectable. New mappings need reviewer confirmation before they can support a compliant result.</p><div className="flex flex-wrap items-end gap-3"><label className="grid gap-1 text-sm">Requirement<select className="rounded-md border border-border bg-bg-1 px-3 py-2" value={ruleId} onChange={(e) => setRuleId(e.target.value)}><option value="">Choose requirement</option>{requirements.map((r) => <option key={r.id} value={r.id}>{r.rule_id} · {r.title}</option>)}</select></label><label className="grid gap-1 text-sm">Document version<select className="rounded-md border border-border bg-bg-1 px-3 py-2" value={versionId} onChange={(e) => setVersionId(e.target.value)}><option value="">Choose processed version</option>{documents.filter((d) => d.current_version?.scan_status === "clean" && ["succeeded", "partial"].includes(d.current_version.processing_status)).map((d) => <option key={d.current_version!.id} value={d.current_version!.id}>{d.document_type} · v{d.current_version!.version_number} · {d.current_version!.file_name ?? "document"}</option>)}</select></label><button disabled={busy} onClick={() => void createMapping()} className="rounded-md bg-primary-600 px-4 py-2 text-white disabled:opacity-50">Save mapping</button></div><div className="space-y-2">{mappings.map((m) => <div key={m.id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border p-3 text-sm"><span>{m.rule_id} ← {m.document_type} v{m.version_number} · {m.status}</span>{m.status === "suggested" && <span className="flex gap-2"><button className="underline" onClick={() => void reviewMapping(m.id, "confirmed")}>Confirm</button><button className="underline" onClick={() => void reviewMapping(m.id, "rejected")}>Reject</button></span>}</div>)}{mappings.length === 0 && <p className="text-sm text-text-secondary">No evidence mappings yet.</p>}</div></section>}
  </main>;
}
