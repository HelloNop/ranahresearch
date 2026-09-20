"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";

type Criterion = { id?: string; dimension: string; operator: string; value: number | boolean | string[] | { description: string }; decision: string; reason: string; priority: number };
type Protocol = { id: string; version: number; status: string; research_question: string; framework_id: string; framework?: { framework_type: string; elements: { name: string; values: string[] }[] }; background: string; objective: string; review_type: string; eligibility_criteria: Criterion[]; information_sources: string[]; screening_strategy: string; extraction_strategy: string; synthesis_strategy: string; risk_of_bias_plan: string; meta_analysis_plan: string; meta_analysis_planned: boolean; assumptions: string[]; uncertainties: string[] };
type Decision = { id: string; decision: string; reason_code: string | null; rationale: string; confidence: number | null; reviewer_type: string; protocol_version: number; criterion_assessments: { criterion_id: string; result: string; reason: string; evidence: string | null }[]; created_at: string };
type QueueItem = { work_id: string; effective: Decision | null };
type Progress = { round_id: string; protocol_id: string; protocol_version: number; status: string; error: string | null; total: number; screened: number; include: number; exclude: number; uncertain: number; remaining: number };
type Work = { title: string; abstract: string | null; authors: string[]; publication_year: number | null; venue: string | null; doi: string | null; discovered_via: string[]; verification_status: string; duplicate_status: string };
const reasons = ["WRONG_POPULATION", "WRONG_INTERVENTION", "WRONG_EXPOSURE", "WRONG_COMPARATOR", "WRONG_OUTCOME", "WRONG_STUDY_DESIGN", "WRONG_SETTING", "WRONG_PUBLICATION_TYPE", "OUTSIDE_DATE_RANGE", "WRONG_LANGUAGE", "NOT_PRIMARY_RESEARCH", "OTHER"];
const label = (value: string) => value.replaceAll("_", " ").toLowerCase();
const criterionValue = (criterion: Criterion) => typeof criterion.value === "object" ? Array.isArray(criterion.value) ? criterion.value.join(", ") : criterion.value.description : String(criterion.value);
const sections = ["background", "objective", "screening_strategy", "extraction_strategy", "synthesis_strategy", "risk_of_bias_plan", "meta_analysis_plan"] as const;

export default function ScreeningWorkspace({ projectId, token }: { projectId: string; token: string }) {
  const base = `/projects/${projectId}`;
  const [protocol, setProtocol] = useState<Protocol | null>(null);
  const [versions, setVersions] = useState<Protocol[]>([]);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [queue, setQueue] = useState<QueueItem[]>([]);
  const [filter, setFilter] = useState("ALL");
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState("");
  const [work, setWork] = useState<Work | null>(null);
  const [history, setHistory] = useState<Decision[]>([]);
  const workRequest = useRef(0);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [operation, setOperation] = useState<{ operation_id: string; status: string; error?: string | null } | null>(null);
  const [acknowledged, setAcknowledged] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<Protocol | null>(null);
  const [amendmentReason, setAmendmentReason] = useState("");
  const [reason, setReason] = useState("");
  const [note, setNote] = useState("");
  const [constraints, setConstraints] = useState("");
  const active = operation && ["RUNNING", "PENDING"].includes(operation.status);
  const refresh = useCallback(async () => {
    const [next, all, counts, rows, project] = await Promise.all([
      api<Protocol | null>(`${base}/protocol`, {}, token), api<Protocol[]>(`${base}/protocol/versions`, {}, token),
      api<Progress | null>(`${base}/screening/title-abstract/progress`, {}, token),
      api<QueueItem[]>(`${base}/screening/title-abstract?filter=${filter}&offset=${offset}`, {}, token),
      api<{ operation: { operation_id: string; status: string } | null }>(base, {}, token),
    ]);
    setProtocol(next); setVersions(all); setProgress(counts); setQueue(rows); setOperation(project.operation); setLoading(false);
  }, [base, filter, offset, token]);
  useEffect(() => { let alive = true; const timer = setTimeout(() => { if (alive) void refresh().catch(caught => { setError(String(caught)); setLoading(false); }); }, 0); return () => { alive = false; clearTimeout(timer); }; }, [refresh]);
  useEffect(() => { if (!active || !operation) return; const timer = setInterval(() => { void api<{ status: string; error: string | null }>(`${base}/operations/${operation.operation_id}`, {}, token).then(async next => { await refresh(); if (next.error) setError(next.error); }).catch(caught => setError(String(caught))); }, 1500); return () => clearInterval(timer); }, [active, operation, base, token, refresh]);
  const loadWork = useCallback(async (id: string) => {
    const request = ++workRequest.current;
    const [works, decisions] = await Promise.all([api<Work[]>(`${base}/literature?work_id=${id}`, {}, token), api<Decision[]>(`${base}/works/${id}/screening-history`, {}, token)]);
    if (request === workRequest.current) { setWork(works[0] ?? null); setHistory(decisions); }
  }, [base, token]);
  useEffect(() => { if (!selected) return; const timer = setTimeout(() => { void loadWork(selected).catch(caught => setError(String(caught))); }, 0); return () => clearTimeout(timer); }, [selected, loadWork, queue]);
  async function command(path: string, body: object = {}) {
    setBusy(true); setError("");
    try { await api(`${base}${path}`, { method: "POST", body: JSON.stringify(body) }, token); await refresh(); if (selected) await loadWork(selected); return true; }
    catch (caught) { setError(String(caught)); return false; }
    finally { setBusy(false); }
  }
  async function saveRevision() {
    if (!draft || !protocol) return;
    const payload = Object.fromEntries([...sections, "review_type", "information_sources", "meta_analysis_planned", "assumptions", "uncertainties"].map(key => [key, draft[key as keyof Protocol]]));
    payload.eligibility_criteria = draft.eligibility_criteria.map(({ id: _id, ...criterion }) => { void _id; return criterion; });
    if (await command(`/protocol/${protocol.id}/revise`, { protocol: payload, reason: amendmentReason })) { setEditing(false); setAcknowledged(false); }
  }
  const roundProtocol = versions.find(v => v.id === progress?.protocol_id);
  const recommendation = history.find(d => d.reviewer_type === "AI" && d.protocol_version === progress?.protocol_version);
  const effective = history.find(d => d.protocol_version === progress?.protocol_version && d.reviewer_type === "HUMAN") ?? queue.find(item => item.work_id === selected)?.effective;

  if (loading) return <p role="status">Loading protocol and screening…</p>;
  return <div className="review-workspace">
    {error && <div className="notice error" role="alert">{error}<button onClick={() => void refresh().catch(caught => setError(String(caught)))}>Refresh workspace</button></div>}
    {operation && <p role="status">Operation: {operation.status}{active ? ". Results update automatically." : ""}</p>}
    <section className="panel"><h2>Review protocol{protocol ? ` · v${protocol.version} · ${protocol.status}` : ""}</h2>
      {!protocol ? <><label htmlFor="protocol-constraints">Optional protocol constraints</label><textarea id="protocol-constraints" value={constraints} onChange={e => setConstraints(e.target.value)} /><button disabled={busy || !!active} onClick={() => void command("/protocol/generate", { user_constraints: constraints || null })}>Generate review protocol</button></> : <>
        <p>{label(protocol.review_type)}</p><h3>Research question</h3><p>{protocol.research_question}</p>
        {protocol.framework && <><h3>Framework: {protocol.framework.framework_type}</h3><dl>{protocol.framework.elements.map(element => <div key={element.name}><dt>{element.name}</dt><dd>{element.values.join("; ")}</dd></div>)}</dl></>}
        {sections.map(key => <div key={key}><h3>{label(key)}</h3>{editing && draft ? <textarea aria-label={label(key)} value={draft[key]} onChange={e => setDraft({ ...draft, [key]: e.target.value })} /> : <p>{protocol[key]}</p>}</div>)}
        <h3>Information sources used for discovery</h3><p>{protocol.information_sources.join(", ") || "No discovery sources recorded"}</p>
        <h3>Eligibility criteria</h3><ul className="criteria">{(editing && draft ? draft : protocol).eligibility_criteria.map((criterion, index) => <li key={criterion.id ?? index}><strong>{label(criterion.dimension)}</strong><p>{label(criterion.decision)}: {label(criterion.operator)} {criterionValue(criterion)}</p><p className="muted">{criterion.reason}</p>{editing && draft && <input aria-label={`Criterion ${index + 1} value`} value={criterionValue(criterion)} onChange={e => { const value = typeof criterion.value === "number" ? Number(e.target.value) : typeof criterion.value === "boolean" ? e.target.value === "true" : Array.isArray(criterion.value) ? e.target.value.split(",").map(v => v.trim()) : { description: e.target.value }; setDraft({ ...draft, eligibility_criteria: draft.eligibility_criteria.map((c, i) => i === index ? { ...c, value } : c) }); }} />}</li>)}</ul>
        {protocol.assumptions.length > 0 && <><h3>Assumptions</h3><ul>{protocol.assumptions.map(s => <li key={s}>{s}</li>)}</ul></>}
        {protocol.uncertainties.length > 0 && <><h3>Uncertainties requiring human review</h3><ul>{protocol.uncertainties.map(s => <li key={s}>{s}</li>)}</ul><label><input type="checkbox" checked={acknowledged} onChange={e => setAcknowledged(e.target.checked)} /> I reviewed these uncertainties</label></>}
        <div className="actions">{protocol.status === "PROPOSED" && <button disabled={busy || !!active || (protocol.uncertainties.length > 0 && !acknowledged)} onClick={() => void command(`/protocol/${protocol.id}/approve`, { acknowledge_uncertainties: acknowledged })}>Approve protocol</button>}<button disabled={busy || !!active} onClick={() => { setDraft(structuredClone(protocol)); setEditing(!editing); }}> {editing ? "Cancel revision" : "Revise protocol"}</button></div>
        {editing && <><label htmlFor="amendment-reason">Reason for amendment</label><input id="amendment-reason" value={amendmentReason} onChange={e => setAmendmentReason(e.target.value)} /><button disabled={busy || !amendmentReason.trim()} onClick={() => void saveRevision()}>Save as new proposed version</button></>}
        <details><summary>Protocol version history</summary>{versions.map(v => <div key={v.id}><h3>v{v.version} · {v.status}</h3><ul>{v.eligibility_criteria.map((c, i) => <li key={i}>{label(c.dimension)}: {label(c.decision)} {label(c.operator)} {criterionValue(c)}</li>)}</ul></div>)}</details>
      </>}
    </section>
    <section className="panel"><h2>Title/Abstract Screening</h2><p>Included records pass to Full-text Review. They are not final included studies.</p>
      <button disabled={busy || !!active || protocol?.status !== "APPROVED"} onClick={() => void command("/screening/title-abstract/start")}>{progress?.status === "PARTIAL" ? "Retry remaining records" : "Run AI Screening"}</button>
      {protocol?.status !== "APPROVED" && <p>Approve the current protocol before starting screening.</p>}
      {progress && <><p>Protocol v{progress.protocol_version} · {progress.status}</p>{progress.protocol_id !== protocol?.id && <div className="notice">These decisions use protocol v{progress.protocol_version}. Approve the new version and start a new round to re-screen.</div>}<dl className="screening-counts" aria-live="polite">{(["total", "screened", "include", "exclude", "uncertain", "remaining"] as const).map(key => <div key={key}><dt>{key === "include" ? "Passed to full-text review" : key}</dt><dd>{progress[key]}</dd></div>)}</dl>{progress.status === "PARTIAL" && <div role="alert" className="notice error">PARTIAL: {progress.error}. Completed decisions are preserved. Retry processes only remaining records.</div>}</>}
      <label htmlFor="screen-filter">Screening filter</label><select id="screen-filter" value={filter} onChange={e => { setFilter(e.target.value); setOffset(0); }}>{["ALL", "UNSCREENED", "INCLUDE", "EXCLUDE", "UNCERTAIN", "HUMAN_OVERRIDDEN"].map(f => <option key={f}>{f}</option>)}</select>
      <div className="screening-columns"><aside aria-label="Screening queue">{queue.length === 0 && <p>No records in this view.</p>}{queue.map((item, index) => <button key={item.work_id} aria-pressed={selected === item.work_id} onClick={() => { ++workRequest.current; setSelected(item.work_id); setWork(null); setHistory([]); setReason(""); setNote(""); }}>Record {offset + index + 1} · {item.effective?.decision ?? "UNSCREENED"}</button>)}<div className="actions"><button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 50))}>Previous</button><button disabled={queue.length < 50} onClick={() => setOffset(offset + 50)}>Next</button></div></aside>
      <article>{!selected ? <p>Select a record to inspect its title, abstract, and decisions.</p> : !work ? <p>Loading record…</p> : <><h3>{work.title}</h3><p>{work.authors.join(", ") || "Authors unavailable"}</p><p>{work.publication_year ?? "Year unavailable"} · {work.venue ?? "Journal unavailable"}</p><p>DOI: {work.doi ?? "Unavailable"}</p><h3>Abstract</h3><p>{work.abstract ?? "No abstract available. Missing information must not be treated as exclusion evidence."}</p><details><summary>Discovery provenance and screening history</summary><p>Discovered via: {work.discovered_via.join(", ")}</p><p>Metadata verification: {work.verification_status}</p><p>Duplicate status: {work.duplicate_status}</p>{history.map(d => <div key={d.id}><h4>{d.reviewer_type} · {d.decision} · protocol v{d.protocol_version}</h4><p>{d.reason_code} {d.rationale}</p><time>{d.created_at}</time></div>)}</details></>}</article>
      <aside><h3>Round eligibility criteria</h3><ul>{roundProtocol?.eligibility_criteria.map((c, i) => <li key={i}>{label(c.dimension)}: {label(c.decision)} {label(c.operator)} {criterionValue(c)}</li>)}</ul>{recommendation && <><h3>AI recommendation: {recommendation.decision}</h3><p>Confidence: {recommendation.confidence === null ? "Unavailable" : `${Math.round(recommendation.confidence * 100)}%`}</p><p>{recommendation.reason_code} {recommendation.rationale}</p><ul>{recommendation.criterion_assessments.map(a => <li key={a.criterion_id}><strong>{label(roundProtocol?.eligibility_criteria.find(c => c.id === a.criterion_id)?.dimension ?? "Criterion")} · {a.result}</strong><p>{a.reason}</p>{a.evidence && <blockquote>{a.evidence}</blockquote>}</li>)}</ul></>}{effective && <p>Effective decision: {effective.decision} ({effective.reviewer_type})</p>}
      {selected && progress && <><label htmlFor="exclude-reason">Exclusion reason</label><select id="exclude-reason" value={reason} onChange={e => setReason(e.target.value)}><option value="">Select reason to exclude</option>{reasons.map(r => <option key={r} value={r}>{label(r)}</option>)}</select><label htmlFor="override-note">Optional review note</label><textarea id="override-note" value={note} onChange={e => setNote(e.target.value)} /><div className="actions">{["INCLUDE", "EXCLUDE", "UNCERTAIN"].map(d => <button key={d} disabled={busy || (d === "EXCLUDE" && !reason)} onClick={() => void command(`/works/${selected}/screening-decisions`, { round_id: progress.round_id, decision: d, reason_code: d === "EXCLUDE" ? reason : null, note })}>{d === "INCLUDE" ? "Include" : d === "EXCLUDE" ? "Exclude" : "Uncertain"}</button>)}</div></>}
      </aside></div>
    </section>
  </div>;
}
