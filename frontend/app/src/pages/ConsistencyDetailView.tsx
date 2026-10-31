import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "@/components/useAuth";
import { Button } from "@/components/Button";
import { fetchConsistencyFinding, updateConsistencyFinding, type ConsistencyFinding } from "@/lib/api";

/** Standalone authenticated finding detail retained for callers outside the workbench. */
export function ConsistencyDetailView({ findingId }: { findingId: number }) {
  const { session } = useAuth();
  const token = session?.access_token;
  const [finding, setFinding] = useState<ConsistencyFinding | null>(null);
  const [description, setDescription] = useState("");
  const [resolved, setResolved] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    if (!token || !Number.isInteger(findingId) || findingId <= 0) {
      setLoading(false);
      setError(token ? "Finding not found." : "Sign in to view this finding.");
      return;
    }
    setLoading(true);
    void fetchConsistencyFinding(findingId, token).then((result) => {
      if (!active) return;
      if (result.ok) {
        setFinding(result.data);
        setDescription(result.data.description);
        setResolved(result.data.resolved);
        setError("");
      } else {
        setFinding(null);
        setError(Object.values(result.errors)[0] || "Unable to load finding.");
      }
      setLoading(false);
    });
    return () => { active = false; };
  }, [findingId, token]);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !finding) return;
    setSaving(true);
    setError("");
    const result = await updateConsistencyFinding(finding.id, { description: description.trim(), resolved }, token);
    setSaving(false);
    if (!result.ok) {
      setError(Object.values(result.errors)[0] || "Unable to save finding.");
      return;
    }
    setFinding(result.data);
  }

  if (loading) return <p className="py-12 text-center" role="status">Loading finding…</p>;
  return (
    <main className="mx-auto max-w-3xl space-y-5 p-6">
      <Link className="text-sm underline" to={finding ? `/consistency/${finding.consistency_check_id}` : "/consistency"}>Back to consistency check</Link>
      {error && <p role="alert" className="rounded border border-red-300 bg-red-50 p-3 text-red-800">{error}</p>}
      {!finding ? <p>Finding is unavailable or access is denied.</p> : <>
        <header><p className="text-sm text-text-secondary">Finding #{finding.id} · check #{finding.consistency_check_id}</p><h1 className="text-2xl font-bold">{finding.field_name}</h1><p className="text-sm">Severity: {finding.severity} · {finding.resolved ? "Resolved" : "Open"}</p></header>
        <section className="grid gap-3 sm:grid-cols-2"><div className="rounded border border-border p-3"><h2 className="text-sm font-semibold">Compared value 1</h2><p className="break-words">{finding.value_1 || "(empty)"}</p></div><div className="rounded border border-border p-3"><h2 className="text-sm font-semibold">Compared value 2</h2><p className="break-words">{finding.value_2 || "(empty)"}</p></div></section>
        <pre className="whitespace-pre-wrap break-words rounded border border-border p-3 text-sm">{finding.evidence ? JSON.stringify(finding.evidence, null, 2) : "No evidence was attached."}</pre>
        <form className="grid gap-3" onSubmit={(event) => void save(event)}><label className="grid gap-1">Reviewer description<textarea className="rounded border border-border bg-bg-1 p-3" value={description} onChange={(event) => setDescription(event.target.value)} required maxLength={4000} /></label><label className="flex items-center gap-2"><input type="checkbox" checked={resolved} onChange={(event) => setResolved(event.target.checked)} />Mark resolved</label><Button type="submit" loading={saving}>Save finding</Button></form>
      </>}
    </main>
  );
}

export default ConsistencyDetailView;
