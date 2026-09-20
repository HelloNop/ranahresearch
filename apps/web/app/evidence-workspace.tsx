"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api, uploadApi } from "./api";

type Operation = { operation_id: string; status: string; error: string | null };
type Publication = { work_id: string; title: string; relationship_type: string; publication_year: number | null };
type Study = { id: string; study_label: string; title: string; study_type: string; status: string; works: Publication[] };
type Cell = { evidence_id: string; value: unknown; unit: string | null; value_type: string; verification_status: string; has_provenance: boolean };
type MatrixRow = { study_id: string; study_label: string; title: string; study_type: string; extraction_status: string; needs_review: boolean; missing_count: number; cells: Record<string, Cell> };
type Matrix = { columns: { name: string; label: string; kind: string }[]; rows: MatrixRow[] };
type Evidence = { id: string; field_name: string; value: unknown; unit: string | null; value_type: string; verification_status: string; notes: string | null; provenance: { work_id: string | null; page: number | null; section: string | null; evidence_text: string }[]; verifications: { method: string; status: string; notes: string | null; findings: { reason?: string; corrected_value?: unknown; message?: string }[] }[]; history: { id: string; value: unknown; value_type: string; status: string }[] };
type FullTextItem = { work_id: string; full_text_status: string; asset_status: string | null; effective: { decision: string; reason_code: string | null; rationale: string } | null };
type Risk = { id: string; study_id: string; version: number; tool: string; tool_version: string; overall_judgement: string; status: string; domains: { domain_code: string; judgement: string; rationale: string; supporting_evidence: string; page: number | null }[] };
type Counts = { included_studies: number; extraction_complete: number; needs_review: number; awaiting_extraction: number; missing_values: number };
type ScreeningCounts = { total: number; screened: number; final_included: number; unavailable: number } | null;
type Work = { id: string; title: string };

const human = (value: string) => value.replaceAll("_", " ").toLowerCase();
const display = (value: unknown) => value === null || value === undefined ? "Missing" : typeof value === "string" ? value : JSON.stringify(value);
const fullTextLabel = (item: FullTextItem) => item.asset_status === "PARSED" ? "Parsed" : item.asset_status === "PARSING" ? "Parsing" : item.asset_status === "FAILED" ? "Parsing failed" : item.asset_status === "AVAILABLE" || item.full_text_status === "AVAILABLE" ? "Full text available" : item.full_text_status === "NOT_REQUESTED" ? "Upload required or search open access" : human(item.full_text_status);

export default function EvidenceWorkspace({ projectId, token }: { projectId: string; token: string }) {
  const base = `/projects/${projectId}`;
  const [matrix, setMatrix] = useState<Matrix>({ columns: [], rows: [] });
  const [studies, setStudies] = useState<Study[]>([]);
  const [works, setWorks] = useState<Work[]>([]);
  const [queue, setQueue] = useState<FullTextItem[]>([]);
  const [risk, setRisk] = useState<Risk[]>([]);
  const [counts, setCounts] = useState<Counts | null>(null);
  const [screening, setScreening] = useState<ScreeningCounts>(null);
  const [selectedStudy, setSelectedStudy] = useState("");
  const [selectedWork, setSelectedWork] = useState("");
  const [selectedEvidence, setSelectedEvidence] = useState<Evidence | null>(null);
  const [screeningHistory, setScreeningHistory] = useState<{ stage: string; decision: string; reason_code: string | null; rationale: string }[]>([]);
  const [filter, setFilter] = useState({ design: "", verification: "", extraction: "", outcome: "" });
  const [correction, setCorrection] = useState({ value: "", reason: "", evidence_text: "", page: "", section: "" });
  const [designReason, setDesignReason] = useState("");
  const [linkTarget, setLinkTarget] = useState("");
  const [busy, setBusy] = useState("");
  const [operation, setOperation] = useState<Operation | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    const [nextMatrix, nextStudies, nextQueue, nextRisk, nextCounts, nextScreening, nextWorks, project] = await Promise.all([
      api<Matrix>(`${base}/evidence/matrix`, {}, token),
      api<Study[]>(`${base}/studies`, {}, token),
      api<FullTextItem[]>(`${base}/screening/full-text?limit=200`, {}, token),
      api<Risk[]>(`${base}/risk-of-bias`, {}, token),
      api<Counts>(`${base}/evidence/progress`, {}, token),
      api<ScreeningCounts>(`${base}/screening/full-text/progress`, {}, token),
      api<Work[]>(`${base}/literature?limit=200`, {}, token),
      api<{ operation: Operation | null }>(base, {}, token),
    ]);
    setMatrix(nextMatrix); setStudies(nextStudies); setQueue(nextQueue); setRisk(nextRisk);
    setCounts(nextCounts); setScreening(nextScreening); setWorks(nextWorks);
    setOperation(project.operation); setLoading(false);
  }, [base, token]);

  useEffect(() => {
    const timer = window.setTimeout(() => { void refresh().catch(caught => { setError(String(caught)); setLoading(false); }); }, 0);
    return () => window.clearTimeout(timer);
  }, [refresh]);
  useEffect(() => {
    if (!operation || !["RUNNING", "PENDING"].includes(operation.status)) return;
    const timer = window.setInterval(() => { void refresh().catch(caught => setError(String(caught))); }, 1500);
    return () => window.clearInterval(timer);
  }, [operation, refresh]);
  useEffect(() => {
    if (!selectedWork) return;
    void api<typeof screeningHistory>(`${base}/works/${selectedWork}/screening-history`, {}, token).then(setScreeningHistory).catch(caught => setError(String(caught)));
  }, [base, selectedWork, token]);

  async function command(label: string, path: string, body: object = {}) {
    setBusy(label); setError("");
    try {
      await api(`${base}${path}`, { method: "POST", body: JSON.stringify(body) }, token);
      await refresh();
    } catch (caught) { setError(String(caught)); }
    finally { setBusy(""); }
  }
  async function upload(workId: string, file?: File) {
    if (!file) return;
    setBusy(`upload-${workId}`); setError("");
    try { await uploadApi(`${base}/works/${workId}/full-text/upload`, file, token); await refresh(); }
    catch (caught) { setError(String(caught)); }
    finally { setBusy(""); }
  }
  async function openEvidence(id: string) {
    setSelectedEvidence(null); setError("");
    try {
      const item = await api<Evidence>(`${base}/evidence/${id}`, {}, token);
      setSelectedEvidence(item); setCorrection({ value: display(item.value), reason: "", evidence_text: "", page: "", section: "" });
    } catch (caught) { setError(String(caught)); }
  }
  async function saveCorrection() {
    if (!selectedEvidence) return;
    const raw = correction.value.trim();
    const value = raw === "" ? null : /^-?\d+(?:\.\d+)?$/.test(raw) ? Number(raw) : raw;
    setBusy("correction"); setError("");
    try {
      const item = await api<Evidence>(`${base}/evidence/${selectedEvidence.id}/correct`, {
        method: "POST", body: JSON.stringify({
          value, value_type: value === null ? "MISSING" : "USER_ENTERED",
          reason: correction.reason,
          evidence_text: correction.evidence_text || null,
          page: correction.page ? Number(correction.page) : null,
          section: correction.section || null,
        }),
      }, token);
      setSelectedEvidence(item); await refresh();
    } catch (caught) { setError(String(caught)); }
    finally { setBusy(""); }
  }

  const selected = studies.find(study => study.id === selectedStudy);
  const byWork = useMemo(() => new Map([
    ...works.map(work => [work.id, work.title] as const),
    ...studies.flatMap(study => study.works.map(work => [work.work_id, work.title] as const)),
  ]), [works, studies]);
  const filtered = matrix.rows.filter(row =>
    (!filter.design || row.study_type === filter.design) &&
    (!filter.extraction || row.extraction_status === filter.extraction) &&
    (!filter.verification || Object.values(row.cells).some(cell => cell.verification_status === filter.verification)) &&
    (!filter.outcome || display(row.cells.outcomes?.value).toLowerCase().includes(filter.outcome.toLowerCase()))
  );
  const currentRisk = risk.find(row => row.study_id === selectedStudy);
  const active = !!operation && ["PENDING", "RUNNING"].includes(operation.status);

  if (loading) return <p role="status">Loading full text and evidence…</p>;
  return <div className="review-workspace evidence-workspace">
    {error && <div className="notice error" role="alert">{error} <button onClick={() => void refresh()}>Refresh</button></div>}
    {active && <p role="status">{operation?.status}: {operation?.operation_id}. Results update automatically.</p>}

    <section className="panel">
      <div className="panel-head"><div><p className="eyebrow">01 / Source documents</p><h2>Full-text screening</h2></div><span className="tag">{screening?.final_included ?? 0} final includes</span></div>
      <p className="muted">Only a full-text INCLUDE enters the extraction corpus.</p>
      <div className="actions"><button disabled={!!busy || active} onClick={() => void command("acquire", "/full-text/acquire")}>Find open-access full text</button><button disabled={!!busy || active} onClick={() => void command("parse", "/full-text/parse")}>Parse stored PDFs</button><button disabled={!!busy || active} onClick={() => void command("screen", "/screening/full-text/start")}>Run full-text screening</button></div>
      {screening && <p role="status">{screening.screened} of {screening.total} screened · {screening.unavailable} unavailable</p>}
      {queue.length === 0 ? <p className="muted">Complete title and abstract screening to see the full-text queue.</p> : <div className="table-wrap"><table><thead><tr><th>Publication</th><th>Full text</th><th>Decision</th><th>Actions</th></tr></thead><tbody>{queue.map(item => <tr key={item.work_id}><td><button className="text-button" onClick={() => setSelectedWork(item.work_id)}>{byWork.get(item.work_id) ?? item.work_id}</button></td><td>{fullTextLabel(item)}</td><td>{item.effective ? <>{item.effective.decision}<small>{item.effective.reason_code && human(item.effective.reason_code)}</small></> : "Awaiting screening"}</td><td><label className="file-control">Upload PDF<input type="file" accept="application/pdf,.pdf" disabled={!!busy || active} onChange={event => { void upload(item.work_id, event.target.files?.[0]); event.target.value = ""; }} /></label></td></tr>)}</tbody></table></div>}
      {selectedWork && <details open><summary>Screening history for {byWork.get(selectedWork) ?? selectedWork}</summary>{screeningHistory.length ? screeningHistory.map((entry, index) => <p key={index}>{human(entry.stage)} · {entry.decision} · {entry.reason_code && human(entry.reason_code)} · {entry.rationale}</p>) : <p>No decision recorded.</p>}</details>}
    </section>

    <section className="panel">
      <div className="panel-head"><div><p className="eyebrow">02 / Publications and studies</p><h2>Study links</h2></div><span className="tag">{studies.length} studies</span></div>
      <button disabled={!!busy || active} onClick={() => void command("link", "/studies/build")}>Build or refresh study links</button>
      {studies.some(study => study.status === "NEEDS_REVIEW") && <p role="status">Ambiguous links need a human decision.</p>}
      <ul className="study-list">{studies.map(study => <li key={study.id}><button className="text-button" onClick={() => setSelectedStudy(study.id)}>{study.study_label} · {study.title}</button><span>{human(study.status)} · {study.works.length} publication{study.works.length === 1 ? "" : "s"}</span></li>)}</ul>
      {selected && <div className="study-detail"><h3>{selected.study_label}: {selected.title}</h3><ul>{selected.works.map(work => <li key={work.work_id}>{work.title} · {human(work.relationship_type)} · {work.publication_year ?? "year unknown"}</li>)}</ul>
        <label htmlFor="study-design">Study design</label><select id="study-design" value={selected.study_type} onChange={event => { if (!designReason.trim()) { setError("Enter a reason before changing study design."); return; } void command("design", `/studies/${selected.id}/design`, { study_type: event.target.value, reason: designReason }); }}><option value="OTHER">Other or unknown</option><option value="RCT">Randomized trial</option><option value="QUASI_EXPERIMENTAL">Non-randomized intervention</option><option value="COHORT">Cohort</option><option value="CASE_CONTROL">Case control</option><option value="CROSS_SECTIONAL">Cross sectional</option><option value="QUALITATIVE">Qualitative</option><option value="MIXED_METHODS">Mixed methods</option><option value="SYSTEMATIC_REVIEW">Systematic review</option></select><label htmlFor="design-reason">Reason for design classification</label><input id="design-reason" value={designReason} onChange={event => setDesignReason(event.target.value)} />
        {selected.status === "NEEDS_REVIEW" && <div className="link-review"><label htmlFor="link-target">Link this study’s first publication to</label><select id="link-target" value={linkTarget} onChange={event => setLinkTarget(event.target.value)}><option value="">Keep separate</option>{studies.filter(row => row.id !== selected.id).map(row => <option key={row.id} value={row.id}>{row.study_label} · {row.title}</option>)}</select><button disabled={!!busy || !selected.works.length} onClick={() => void command("review link", "/studies/link", { work_id: selected.works[0].work_id, decision: linkTarget ? "LINK" : "KEEP_SEPARATE", target_study_id: linkTarget || null, relationship_type: linkTarget ? "SECONDARY_REPORT" : null, rationale: "Reviewed publication relationship" })}>Save link decision</button></div>}
      </div>}
    </section>

    <section className="panel">
      <div className="panel-head"><div><p className="eyebrow">03 / Traceable findings</p><h2>Evidence matrix</h2></div><span className="tag">{counts?.extraction_complete ?? 0} extracted</span></div>
      <p className="muted">{counts?.included_studies ?? 0} included studies · {counts?.needs_review ?? 0} need review · {counts?.awaiting_extraction ?? 0} awaiting extraction · {counts?.missing_values ?? 0} missing values</p>
      <div className="actions"><button disabled={!!busy || active} onClick={() => void command("extract", "/extraction/start")}>Extract evidence</button></div>
      <div className="filters evidence-filters"><label>Design<select value={filter.design} onChange={event => setFilter({ ...filter, design: event.target.value })}><option value="">Any</option>{[...new Set(matrix.rows.map(row => row.study_type))].map(value => <option key={value}>{value}</option>)}</select></label><label>Verification<select value={filter.verification} onChange={event => setFilter({ ...filter, verification: event.target.value })}><option value="">Any</option>{["VERIFIED", "PARTIAL", "CONFLICT", "UNVERIFIED"].map(value => <option key={value}>{value}</option>)}</select></label><label>Extraction<select value={filter.extraction} onChange={event => setFilter({ ...filter, extraction: event.target.value })}><option value="">Any</option><option>EXTRACTED</option><option>NOT_EXTRACTED</option></select></label><label>Outcome<input value={filter.outcome} onChange={event => setFilter({ ...filter, outcome: event.target.value })} placeholder="Search outcome" /></label></div>
      {filtered.length === 0 ? <p className="muted">No studies match these filters.</p> : <div className="table-wrap"><table className="matrix-table"><thead><tr><th>Study</th><th>Extraction</th>{matrix.columns.map(column => <th key={column.name}>{column.label}</th>)}</tr></thead><tbody>{filtered.map(row => <tr key={row.study_id}><th scope="row"><button className="text-button" onClick={() => setSelectedStudy(row.study_id)}>{row.study_label}</button><small>{row.title}</small></th><td>{human(row.extraction_status)}{row.needs_review && <small>Needs review</small>}</td>{matrix.columns.map(column => <td key={column.name}>{row.cells[column.name] ? <button className="text-button cell-value" onClick={() => { setSelectedStudy(row.study_id); void openEvidence(row.cells[column.name].evidence_id); }}>{display(row.cells[column.name].value)}{row.cells[column.name].unit && ` ${row.cells[column.name].unit}`}<small>{human(row.cells[column.name].verification_status)}</small></button> : "—"}</td>)}</tr>)}</tbody></table></div>}
      {selectedEvidence && <div className="evidence-inspector"><div className="panel-head"><h3>{human(selectedEvidence.field_name)}: {display(selectedEvidence.value)}</h3><button className="text-button" onClick={() => setSelectedEvidence(null)}>Close</button></div><p>{human(selectedEvidence.value_type)} · {human(selectedEvidence.verification_status)}</p>{selectedEvidence.notes && <p>{selectedEvidence.notes}</p>}
        <h4>Source passages</h4>{selectedEvidence.provenance.length ? selectedEvidence.provenance.map((source, index) => <blockquote key={index}><p>{source.evidence_text}</p><cite>Page {source.page ?? "unknown"} · {source.section ?? "section unknown"} · {byWork.get(source.work_id ?? "") ?? "publication"}</cite></blockquote>) : <p>No source passage recorded for this field.</p>}
        <details><summary>Verification and correction history</summary>{selectedEvidence.verifications.map((entry, index) => <p key={index}>{human(entry.method)} · {human(entry.status)} · {entry.notes}{entry.findings.map(finding => ` ${finding.message ?? finding.reason ?? ""}`).join(" ")}</p>)}{selectedEvidence.history.map(entry => <p key={entry.id}>{human(entry.status)} · {human(entry.value_type)} · {display(entry.value)}</p>)}</details>
        <div className="correction-form"><h4>Correct this field</h4><label>Value<input value={correction.value} onChange={event => setCorrection({ ...correction, value: event.target.value })} /></label><label>Reason<input required value={correction.reason} onChange={event => setCorrection({ ...correction, reason: event.target.value })} /></label><label>Source quote, if available<textarea value={correction.evidence_text} onChange={event => setCorrection({ ...correction, evidence_text: event.target.value })} /></label><div className="filters"><label>Page<input type="number" min="1" value={correction.page} onChange={event => setCorrection({ ...correction, page: event.target.value })} /></label><label>Section<input value={correction.section} onChange={event => setCorrection({ ...correction, section: event.target.value })} /></label></div><button disabled={!!busy || !correction.reason.trim()} onClick={() => void saveCorrection()}>Save correction as a new version</button></div>
      </div>}
    </section>

    <section className="panel"><div className="panel-head"><div><p className="eyebrow">04 / Appraisal</p><h2>Risk of bias</h2></div><span className="tag">Foundation</span></div><p className="muted">Tool selection follows the recorded study design. Domain judgements are provisional until reviewed.</p><div className="actions"><button disabled={!!busy || active} onClick={() => void command("risk", "/risk-of-bias/start")}>Propose assessments</button></div>{selected && !currentRisk && <p>{selected.study_label}: {selected.study_type === "RCT" ? "RoB 2" : selected.study_type === "QUASI_EXPERIMENTAL" ? "ROBINS-I" : "No supported tool for this design"}</p>}{currentRisk && <div className="risk-detail"><h3>{currentRisk.tool} · {human(currentRisk.overall_judgement)} · {human(currentRisk.status)}</h3><p>Version {currentRisk.version} · {currentRisk.tool_version}</p><dl>{currentRisk.domains.map(domain => <div key={domain.domain_code}><dt>{human(domain.domain_code)} · {human(domain.judgement)}</dt><dd>{domain.rationale}{domain.supporting_evidence && <blockquote>{domain.supporting_evidence}<cite>Page {domain.page ?? "unknown"}</cite></blockquote>}</dd></div>)}</dl></div>}</section>
  </div>;
}
