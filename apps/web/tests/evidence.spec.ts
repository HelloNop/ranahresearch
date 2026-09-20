import { expect, test } from "@playwright/test";

test("full-text queue, source provenance, correction, and appraisal remain usable on mobile", async ({ page }) => {
  let corrected = false;
  const project = { id: "project-1", title: "Trial review", status: "EXTRACTION", ideas: [], literature_count: 1, plan_status: "APPROVED", operation: null };
  const study = { id: "study-1", study_label: "S01", title: "AI tutoring trial", study_type: "RCT", status: "CONFIRMED", works: [{ work_id: "work-1", title: "AI tutoring trial", relationship_type: "PRIMARY_REPORT", publication_year: 2025 }] };
  const item = () => ({ id: corrected ? "evidence-2" : "evidence-1", field_name: "sample_size", value: corrected ? 216 : 214, unit: "participants", value_type: corrected ? "USER_ENTERED" : "REPORTED", verification_status: "VERIFIED", notes: null, provenance: [{ work_id: "work-1", page: 2, section: "Methods > Participants", evidence_text: "We recruited 214 undergraduate students" }], verifications: [{ method: "EVIDENCE_REVIEWER_AGENT", status: "VERIFIED", notes: "Source checked", findings: [] }], history: corrected ? [{ id: "evidence-2", value: 216, value_type: "USER_ENTERED", status: "CURRENT" }, { id: "evidence-1", value: 214, value_type: "REPORTED", status: "SUPERSEDED" }] : [{ id: "evidence-1", value: 214, value_type: "REPORTED", status: "CURRENT" }] });
  await page.addInitScript(() => localStorage.setItem("ranahresearch-token", "fixture-token"));
  await page.route("http://127.0.0.1:8000/**", async route => {
    const path = new URL(route.request().url()).pathname;
    let body: unknown = null;
    if (path === "/projects") body = [project];
    else if (path === "/projects/project-1") body = project;
    else if (path.endsWith("/plan") || path.endsWith("/framework") || path.endsWith("/search-strategy")) body = null;
    else if (path.endsWith("/literature")) body = [{ id: "work-1", title: "AI tutoring trial", authors: [], publication_year: 2025, doi: null, discovered_via: [], verification_status: "VERIFIED", duplicate_status: "NO_DUPLICATE_DETECTED" }];
    else if (path.endsWith("/studies")) body = [study];
    else if (path.endsWith("/screening/full-text")) body = [{ work_id: "work-1", full_text_status: "AVAILABLE", effective: { decision: "INCLUDE", reason_code: null, rationale: "Eligible" } }];
    else if (path.endsWith("/screening/full-text/progress")) body = { total: 1, screened: 1, final_included: 1, unavailable: 0 };
    else if (path.endsWith("/screening-history")) body = [{ stage: "FULL_TEXT", decision: "INCLUDE", reason_code: null, rationale: "Eligible" }];
    else if (path.endsWith("/evidence/matrix")) body = { columns: [{ name: "sample_size", label: "Sample size", kind: "INTEGER" }], rows: [{ study_id: "study-1", study_label: "S01", title: "AI tutoring trial", study_type: "RCT", extraction_status: "EXTRACTED", needs_review: false, missing_count: 0, cells: { sample_size: { evidence_id: corrected ? "evidence-2" : "evidence-1", value: corrected ? 216 : 214, unit: "participants", value_type: corrected ? "USER_ENTERED" : "REPORTED", verification_status: "VERIFIED", has_provenance: true } } }] };
    else if (path.endsWith("/evidence/progress")) body = { included_studies: 1, extraction_complete: 1, needs_review: 0, awaiting_extraction: 0, missing_values: 0 };
    else if (path.endsWith("/risk-of-bias")) body = [{ id: "risk-1", study_id: "study-1", version: 1, tool: "ROB_2", tool_version: "foundation-1", overall_judgement: "NOT_ASSESSED", status: "NEEDS_REVIEW", domains: [{ domain_code: "randomization", judgement: "UNASSESSED", rationale: "Allocation method not reported", supporting_evidence: "", page: null }] }];
    else if (path.endsWith("/evidence/evidence-1/correct")) { corrected = true; body = item(); }
    else if (path.endsWith("/evidence/evidence-1") || path.endsWith("/evidence/evidence-2")) body = item();
    await route.fulfill({ json: body });
  });

  await page.goto("/");
  await page.getByLabel("Open project").selectOption("project-1");
  await page.getByRole("button", { name: "Full text & evidence" }).click();
  await expect(page.getByRole("heading", { name: "Full-text screening" })).toBeVisible();
  await expect(page.getByText("1 final includes")).toBeVisible();
  await page.getByRole("button", { name: "214 participants" }).click();
  await expect(page.getByText("We recruited 214 undergraduate students")).toBeVisible();
  await expect(page.getByText("Page 2 · Methods > Participants")).toBeVisible();
  await page.getByLabel("Reason", { exact: true }).fill("Checked against the original report");
  await page.getByLabel("Value", { exact: true }).fill("216");
  await page.getByRole("button", { name: "Save correction as a new version" }).click();
  await page.getByText("Verification and correction history").click();
  await expect(page.getByText("superseded · reported · 214", { exact: false })).toBeVisible();
  await page.getByRole("button", { name: "S01 · AI tutoring trial" }).first().click();
  await expect(page.getByText("ROB_2 · not assessed · needs review")).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
});
