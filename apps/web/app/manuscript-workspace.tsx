"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api, downloadApi } from "./api";

type Operation = { operation_id: string; status: string; stage: string; error: string | null };
type SynthesisItem = { id: string; label?: string; text?: string; description?: string; interpretation?: string; gap_type?: string; supporting_observation?: string; scope?: string; confidence: string; evidence?: { evidence_id: string; relationship: string }[] };
type Synthesis = { id: string; version: number; status: string; method: string; themes: SynthesisItem[]; findings: SynthesisItem[]; contradictions: SynthesisItem[]; research_gaps: SynthesisItem[]; limitations: string[]; confidence_notes: string[] };
type Claim = { id: string; claim_type: string; text: string; status: string; confidence: string; verification: string | null; recommended_qualification: string | null; evidence: { evidence_id: string; relationship: string }[] };
type ClaimDetail = Omit<Claim, "evidence"> & { evidence: { id: string; field_name: string; value: unknown; relationship: string; work_id: string | null }[]; studies: { id: string; title: string }[]; works: { id: string; title: string; doi: string | null }[] };
type Section = { id: string; section_type: string; heading: string; content: string; word_count: number; status: string };
type Issue = { id: string; section_id: string | null; reviewer_type: string; severity: string; category: string; description: string; recommended_action: string; status: string };
type Manuscript = { id: string; title: string; status: string; citation_style: string; version: number; sections: Section[]; issues: Issue[] };
type ExportRow = { id: string; status: string; format: string; citation_style: string };

const human = (value: string) => value.replaceAll("_", " ").toLowerCase();

export default function ManuscriptWorkspace({ projectId, token }: { projectId: string; token: string }) {
  const base = `/projects/${projectId}`;
  const [view, setView] = useState<"synthesis" | "claims" | "manuscript">("manuscript");
  const [synthesis, setSynthesis] = useState<Synthesis | null>(null);
  const [claims, setClaims] = useState<Claim[]>([]);
  const [manuscript, setManuscript] = useState<Manuscript | null>(null);
  const [exports, setExports] = useState<ExportRow[]>([]);
  const [operation, setOperation] = useState<Operation | null>(null);
  const [selectedSection, setSelectedSection] = useState("");
  const [selectedClaim, setSelectedClaim] = useState<ClaimDetail | null>(null);
  const [inspector, setInspector] = useState<"evidence" | "citations" | "review">("evidence");
  const [issueFilter, setIssueFilter] = useState("OPEN");
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [citationStyle, setCitationStyle] = useState("APA_7");
  const [synthesisMethod, setSynthesisMethod] = useState("NARRATIVE_SYNTHESIS");
  const [format, setFormat] = useState("DOCX");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    const [nextSynthesis, nextClaims, nextManuscript, nextExports, project] = await Promise.all([
      api<Synthesis | null>(`${base}/synthesis`, {}, token),
      api<Claim[]>(`${base}/claims`, {}, token),
      api<Manuscript | null>(`${base}/manuscript`, {}, token),
      api<ExportRow[]>(`${base}/exports`, {}, token),
      api<{ operation: Operation | null }>(base, {}, token),
    ]);
    setSynthesis(nextSynthesis); setClaims(nextClaims); setManuscript(nextManuscript); setExports(nextExports); setOperation(project.operation); setLoading(false);
    if (nextManuscript?.sections.length && !nextManuscript.sections.some(row => row.id === selectedSection)) setSelectedSection(nextManuscript.sections[0].id);
  }, [base, selectedSection, token]);

  useEffect(() => { const timer = window.setTimeout(() => { void refresh().catch(caught => { setError(String(caught)); setLoading(false); }); }, 0); return () => window.clearTimeout(timer); }, [refresh]);
  useEffect(() => { if (!operation || !["PENDING", "RUNNING"].includes(operation.status)) return; const timer = window.setInterval(() => { void refresh().catch(caught => setError(String(caught))); }, 1500); return () => window.clearInterval(timer); }, [operation, refresh]);

  const section = manuscript?.sections.find(row => row.id === selectedSection) ?? null;
  const draft = section ? edits[section.id] ?? section.content : "";
  const active = !!operation && ["PENDING", "RUNNING"].includes(operation.status);
  const issues = useMemo(() => manuscript?.issues.filter(issue => issueFilter === "ALL" || issue.status === issueFilter || issue.severity === issueFilter) ?? [], [issueFilter, manuscript]);

  async function command(label: string, path: string, body: object = {}) {
    setBusy(label); setError("");
    try { await api(`${base}${path}`, { method: "POST", body: JSON.stringify(body) }, token); await refresh(); }
    catch (caught) { setError(String(caught)); }
    finally { setBusy(""); }
  }
  async function inspectClaim(id: string) {
    setError(""); setInspector("evidence");
    try { setSelectedClaim(await api<ClaimDetail>(`${base}/claims/${id}`, {}, token)); }
    catch (caught) { setError(String(caught)); }
  }
  async function saveSection() {
    if (!section || draft === section.content) return;
    await command("save", `/manuscript/sections/${section.id}/edit`, { content: draft, reason: "Manual author edit" });
    setEdits(current => { const next = { ...current }; delete next[section.id]; return next; });
  }
  async function dismiss(issue: Issue) {
    const reason = window.prompt("Why should this issue be dismissed?");
    if (reason?.trim()) await command("dismiss", `/review-issues/${issue.id}/dismiss`, { reason });
  }
  async function exportManuscript() {
    setBusy("export"); setError("");
    try {
      const row = await api<ExportRow>(`${base}/exports`, { method: "POST", body: JSON.stringify({ format, citation_style: citationStyle }) }, token);
      const blob = await downloadApi(`${base}/exports/${row.id}/download`, token);
      const url = URL.createObjectURL(blob); const link = document.createElement("a"); link.href = url; link.download = `manuscript.${format === "MARKDOWN" ? "md" : format === "LATEX" ? "tex" : format.toLowerCase()}`; link.click(); URL.revokeObjectURL(url); await refresh();
    } catch (caught) { setError(String(caught)); }
    finally { setBusy(""); }
  }

  if (loading) return <p role="status">Loading synthesis and manuscript…</p>;
  return <div className="manuscript-area">
    {error && <div className="notice error" role="alert">{error} <button onClick={() => void refresh()}>Refresh</button></div>}
    <section className="manuscript-commandbar">
      <div><p className="eyebrow">Evidence to manuscript</p><h2>{manuscript?.title ?? "Build an auditable manuscript"}</h2><p className="muted">Synthesis, claims, prose, citations, and review remain separately inspectable.</p></div>
      <div className="command-actions"><span className="tag">{manuscript?.status ?? synthesis?.status ?? "NOT STARTED"}</span><button disabled={active || !!busy} onClick={() => void command("generate", "/manuscript/generate")}>{active ? `${human(operation?.stage ?? "working")}…` : manuscript ? "Generate new manuscript" : "Generate manuscript"}</button></div>
    </section>
    <nav className="manuscript-tabs" aria-label="Evidence synthesis and manuscript views">
      <button aria-pressed={view === "synthesis"} onClick={() => setView("synthesis")}>Synthesis</button>
      <button aria-pressed={view === "claims"} onClick={() => setView("claims")}>Claim graph</button>
      <button aria-pressed={view === "manuscript"} onClick={() => setView("manuscript")}>Manuscript</button>
    </nav>

    {view === "synthesis" && <SynthesisView synthesis={synthesis} active={active || !!busy} method={synthesisMethod} setMethod={setSynthesisMethod} generate={() => void command("synthesis", "/synthesis/generate", { method: synthesisMethod })} approve={() => synthesis && void command("approve", "/synthesis/approve", { synthesis_id: synthesis.id })} />}
    {view === "claims" && <section className="panel claim-ledger"><div className="panel-head"><div><p className="eyebrow">Verified propositions</p><h2>Claim ledger</h2></div><div className="command-actions"><span className="tag">{claims.length} claims</span><button disabled={active || !!busy || !synthesis} onClick={() => void command("claims", "/claims/generate")}>Build claim graph</button></div></div>{claims.length === 0 ? <p className="muted">Generate a synthesis, then build evidence-linked claims.</p> : claims.map(claim => <button className="claim-row" key={claim.id} onClick={() => void inspectClaim(claim.id)}><span>{claim.claim_type}</span><strong>{claim.text}</strong><small>{claim.verification ? human(claim.verification) : human(claim.status)} · {human(claim.confidence)}</small></button>)}</section>}
    {view === "manuscript" && (!manuscript ? <section className="panel empty"><p>No manuscript exists yet. Generation starts only when validated evidence is available.</p></section> : <div className="manuscript-grid">
      <aside className="manuscript-outline"><p className="eyebrow">Version {manuscript.version}</p><nav aria-label="Manuscript sections">{manuscript.sections.map(item => <button key={item.id} aria-current={item.id === selectedSection ? "page" : undefined} onClick={() => setSelectedSection(item.id)}><span>{item.heading}</span><small>{item.word_count} words · {human(item.status)}</small></button>)}</nav></aside>
      <article className="manuscript-editor">{section ? <><div className="editor-heading"><div><p className="eyebrow">{human(section.section_type)}</p><h2>{section.heading}</h2></div><span>{section.word_count} words</span></div><label className="sr-only" htmlFor="section-editor">Edit {section.heading}</label><textarea id="section-editor" value={draft} onChange={event => setEdits(current => ({ ...current, [section.id]: event.target.value }))} rows={24} /><div className="editor-actions"><button disabled={!!busy || draft === section.content} onClick={() => void saveSection()}>{busy === "save" ? "Saving…" : "Save as new version"}</button><span className="muted">Saving preserves the prior manuscript version.</span></div></> : <p>Select a section.</p>}</article>
      <aside className="manuscript-inspector"><nav aria-label="Manuscript inspector"><button aria-pressed={inspector === "evidence"} onClick={() => setInspector("evidence")}>Claims</button><button aria-pressed={inspector === "citations"} onClick={() => setInspector("citations")}>Citations</button><button aria-pressed={inspector === "review"} onClick={() => setInspector("review")}>Review</button></nav>
        {inspector === "evidence" && <div className="inspector-body"><h3>Claim evidence</h3>{selectedClaim ? <ClaimInspector claim={selectedClaim} /> : <><p className="muted">Select a verified claim to inspect its evidence trail.</p>{claims.filter(claim => claim.status === "VERIFIED").map(claim => <button className="text-button" key={claim.id} onClick={() => void inspectClaim(claim.id)}>{claim.text}</button>)}</>}</div>}
        {inspector === "citations" && <div className="inspector-body"><h3>Canonical works</h3>{selectedClaim?.works.length ? selectedClaim.works.map(work => <dl key={work.id}><dt>{work.title}</dt><dd>DOI: {work.doi ?? "Metadata incomplete"}</dd><dd>Work ID: {work.id}</dd></dl>) : <p className="muted">Choose a claim to see the works used for citation.</p>}</div>}
        {inspector === "review" && <div className="inspector-body"><div className="issue-tools"><label>Issue filter<select value={issueFilter} onChange={event => setIssueFilter(event.target.value)}><option value="OPEN">Open</option><option value="BLOCKING">Blocking</option><option value="MAJOR">Major</option><option value="RESOLVED">Resolved</option><option value="ALL">All</option></select></label><button disabled={active || !!busy} onClick={() => void command("review", "/manuscript/re-review")}>Re-review</button></div>{issues.length === 0 ? <p className="muted">No issues match this filter.</p> : issues.map(issue => <article className="issue" key={issue.id}><p><strong>{issue.severity}</strong> · {human(issue.reviewer_type)}</p><h4>{issue.category}</h4><p>{issue.description}</p><p className="muted">{issue.recommended_action}</p>{issue.status === "OPEN" && <div className="issue-actions"><button onClick={() => void command("revise", `/review-issues/${issue.id}/revise`)}>Apply revision</button><button className="secondary" onClick={() => void dismiss(issue)}>Dismiss</button></div>}</article>)}</div>}
      </aside>
      <section className="export-bar"><div><p className="eyebrow">Versioned output</p><h3>Export this manuscript</h3><p className="muted">References include only canonical works cited in the manuscript.</p></div><label>Citation style<select value={citationStyle} onChange={event => setCitationStyle(event.target.value)}><option value="APA_7">APA 7</option><option value="VANCOUVER">Vancouver</option></select></label><label>Format<select value={format} onChange={event => setFormat(event.target.value)}><option>DOCX</option><option>PDF</option><option>MARKDOWN</option><option>LATEX</option></select></label><button disabled={!!busy} onClick={() => void exportManuscript()}>{busy === "export" ? "Rendering…" : "Export"}</button>{exports.length > 0 && <span className="muted">{exports.length} export{exports.length === 1 ? "" : "s"} recorded</span>}</section>
    </div>)}
  </div>;
}

function SynthesisView({ synthesis, active, method, setMethod, generate, approve }: { synthesis: Synthesis | null; active: boolean; method: string; setMethod: (method: string) => void; generate: () => void; approve: () => void }) {
  const controls = <div className="command-actions"><label>Synthesis method<select value={method} onChange={event => setMethod(event.target.value)}><option value="NARRATIVE_SYNTHESIS">Narrative</option><option value="THEMATIC_SYNTHESIS">Thematic</option><option value="DESCRIPTIVE_SYNTHESIS">Descriptive</option></select></label><button disabled={active} onClick={generate}>{synthesis ? "New version" : "Generate synthesis"}</button></div>;
  if (!synthesis) return <section className="panel empty"><p>No synthesis exists yet. Build one from validated evidence before drafting claims.</p>{controls}</section>;
  return <div className="synthesis-grid"><section className="panel"><div className="panel-head"><div><p className="eyebrow">Themes and findings</p><h2>{human(synthesis.method)}</h2></div><div><span className="tag">v{synthesis.version} · {synthesis.status}</span>{controls}</div></div>{["GENERATED", "REVIEWED"].includes(synthesis.status) && <button onClick={approve}>Approve synthesis</button>}{synthesis.themes.map(theme => <article className="synthesis-item" key={theme.id}><h3>{theme.label}</h3><p>{theme.description}</p><small>{human(theme.confidence)} confidence · {theme.evidence?.length ?? 0} evidence links</small></article>)}{synthesis.findings.map(finding => <article className="synthesis-item" key={finding.id}><h3>Finding</h3><p>{finding.text}</p><small>{human(finding.confidence)} confidence</small></article>)}</section><aside><section className="panel contradictions"><p className="eyebrow">Conflicting findings</p><h2>Contradictions</h2>{synthesis.contradictions.length ? synthesis.contradictions.map(item => <article key={item.id}><p>{item.description}</p><small>{item.interpretation}</small></article>) : <p className="muted">No contradiction was identified in the reviewed evidence.</p>}</section><section className="panel gaps"><p className="eyebrow">Corpus limits</p><h2>Research gaps</h2>{synthesis.research_gaps.map(item => <article key={item.id}><strong>{item.gap_type && human(item.gap_type)}</strong><p>{item.description}</p><small>{item.scope}</small></article>)}</section></aside></div>;
}

function ClaimInspector({ claim }: { claim: ClaimDetail }) {
  return <div><p className="claim-text">{claim.text}</p><p>{human(claim.status)} · {human(claim.confidence)}</p>{claim.recommended_qualification && <p className="notice">Qualification: {claim.recommended_qualification}</p>}<h4>Evidence</h4>{claim.evidence.map(row => <dl key={`${row.id}-${row.relationship}`}><dt>{human(row.relationship)} · {human(row.field_name)}</dt><dd>{typeof row.value === "string" ? row.value : JSON.stringify(row.value)}</dd></dl>)}<h4>Studies</h4>{claim.studies.map(row => <p key={row.id}>{row.title}</p>)}</div>;
}
