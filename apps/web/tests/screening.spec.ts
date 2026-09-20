import { expect, test } from "@playwright/test";

test("discovery entry, protocol approval, screening decisions, filters and partial retry", async ({ page }) => {
  let protocolStatus = "PROPOSED";
  let decision = "EXCLUDE";
  let human = false;
  let runStatus = "PARTIAL";
  let operationPolls = 0;
  const criterion = { id: "criterion-1", dimension: "POPULATION", operator: "MATCHES", value: { description: "University students" }, decision: "INCLUDE", reason: "Question scope", priority: 0 };
  const protocol = () => ({ id: "protocol-1", version: 1, status: protocolStatus, research_question: "How do students use AI?", framework_id: "framework-1", background: "AI learning", objective: "Map learning", review_type: "SCOPING_REVIEW", eligibility_criteria: [criterion], information_sources: ["crossref"], screening_strategy: "Recall-oriented screening", extraction_strategy: "Extract after full-text review", synthesis_strategy: "Map themes", risk_of_bias_plan: "Assess if required", meta_analysis_plan: "No pooling planned", meta_analysis_planned: false, assumptions: [], uncertainties: [] });
  const ai = { id: "ai-1", decision: "EXCLUDE", reason_code: "WRONG_POPULATION", rationale: "Primary school population", confidence: .9, reviewer_type: "AI", protocol_version: 1, criterion_assessments: [{ criterion_id: criterion.id, result: "FAIL", reason: "Wrong population", evidence: "Primary school children" }], created_at: "2026-09-20" };
  const effective = () => human ? { ...ai, id: "human-1", reviewer_type: "HUMAN", decision, rationale: "Human review" } : ai;
  const project = () => ({ id: "project-1", title: "AI learning review", status: "SCREENING", ideas: [{ raw_text: "University AI learning" }], literature_count: 2, plan_status: "APPROVED", operation: runStatus === "RUNNING" ? { operation_id: "operation-1", status: "RUNNING", stage: "TITLE_ABSTRACT", error: null, provider_runs: [] } : null });
  await page.addInitScript(() => localStorage.setItem("ranahresearch-token", "fixture-token"));
  await page.route("http://127.0.0.1:8000/**", async route => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    let body: unknown = null;
    if (path === "/projects") body = [project()];
    else if (path.endsWith("/protocol/protocol-1/approve")) { protocolStatus = "APPROVED"; body = protocol(); }
    else if (path.endsWith("/protocol/versions")) body = [protocol()];
    else if (path.endsWith("/protocol")) body = protocol();
    else if (path.endsWith("/framework")) body = { structured_elements: { framework_type: "PCC", elements: [{ name: "population", values: ["University students"] }] } };
    else if (path.endsWith("/screening/title-abstract/start")) { runStatus = "RUNNING"; body = { operation_id: "operation-1", status: runStatus }; }
    else if (path.endsWith("/operations/operation-1")) { operationPolls++; runStatus = "COMPLETED"; body = { status: runStatus, error: null }; }
    else if (path.endsWith("/screening/title-abstract/progress")) body = { round_id: "round-1", protocol_id: "protocol-1", protocol_version: 1, status: runStatus, error: "Provider unavailable", total: 2, screened: runStatus === "COMPLETED" ? 2 : 1, include: decision === "INCLUDE" ? 1 : 0, exclude: decision === "EXCLUDE" ? 1 : 0, uncertain: runStatus === "COMPLETED" ? 1 : 0, remaining: runStatus === "COMPLETED" ? 0 : 1 };
    else if (path.endsWith("/screening/title-abstract")) { const filter = url.searchParams.get("filter"); body = filter === "UNSCREENED" || (filter === "INCLUDE" && decision !== "INCLUDE") ? [] : [{ work_id: "work-1", effective: effective() }]; }
    else if (path.endsWith("/screening-decisions")) { human = true; decision = route.request().postDataJSON().decision; body = effective(); }
    else if (path.endsWith("/screening-history")) body = human ? [effective(), ai] : [ai];
    else if (path.endsWith("/literature")) body = url.searchParams.has("year") ? [] : [{ id: "work-1", title: "AI in learning", abstract: "Primary school children used AI", authors: ["Fixture author"], publication_year: 2024, venue: "Fixture journal", doi: null, discovered_via: ["crossref"], verification_status: "VERIFIED", duplicate_status: "NO_DUPLICATE_DETECTED" }];
    else if (path === "/projects/project-1") body = project();
    await route.fulfill({ json: body });
  });
  await page.goto("/");
  await page.getByLabel("Open project").selectOption("project-1");
  await expect(page.getByText("AI in learning", { exact: true })).toBeVisible();
  await page.getByLabel("Year", { exact: true }).fill("2000");
  await expect(page.getByText("AI in learning", { exact: true })).not.toBeVisible();
  await page.getByRole("button", { name: "Protocol & screening" }).click();
  await expect(page.getByRole("heading", { name: "Review protocol · v1 · PROPOSED" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Eligibility criteria", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Approve protocol", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Review protocol · v1 · APPROVED" })).toBeVisible();
  await expect(page.getByRole("alert").filter({ hasText: "PARTIAL" })).toBeVisible();
  await page.getByRole("button", { name: "Record 1" }).click();
  await expect(page.getByRole("heading", { name: "AI recommendation: EXCLUDE" })).toBeVisible();
  await page.getByRole("button", { name: "Include", exact: true }).click();
  await expect(page.getByText("Effective decision: INCLUDE (HUMAN)")).toBeVisible();
  await page.getByLabel("Screening filter").selectOption("HUMAN_OVERRIDDEN");
  await expect(page.getByRole("button", { name: "Record 1 · INCLUDE" })).toBeVisible();
  await page.getByLabel("Exclusion reason").selectOption("WRONG_POPULATION");
  await page.getByRole("button", { name: "Exclude", exact: true }).click();
  await expect(page.getByText("Effective decision: EXCLUDE (HUMAN)")).toBeVisible();
  await page.getByRole("button", { name: "Uncertain", exact: true }).click();
  await expect(page.getByText("Effective decision: UNCERTAIN (HUMAN)")).toBeVisible();
  await page.getByText("Discovery provenance and screening history").click();
  await expect(page.getByText("Discovered via: crossref")).toBeVisible();
  await page.getByRole("button", { name: "Retry remaining records" }).click();
  await expect(page.getByText("Protocol v1 · COMPLETED", { exact: true })).toBeVisible();
  expect(operationPolls).toBeGreaterThan(0);
  await page.getByLabel("Screening filter").selectOption("UNSCREENED");
  await expect(page.getByText("No records in this view.")).toBeVisible();
  await page.screenshot({ path: "test-results/screening-desktop.png", fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  await page.screenshot({ path: "test-results/screening-mobile.png", fullPage: true });
});

test("generate protocol, acknowledge uncertainty, and revise criteria as a new version", async ({ page }) => {
  let current: Record<string, unknown> | null = null;
  const versions: Record<string, unknown>[] = [];
  let revision: { protocol: { eligibility_criteria: { value: { description: string } }[] }; reason: string } | null = null;
  const seed = { id: "p1", version: 1, status: "PROPOSED", research_question: "AI learning?", framework_id: "f1", framework: { framework_type: "PCC", elements: [{ name: "population", values: ["Students"] }] }, background: "AI", objective: "Map learning", review_type: "SCOPING_REVIEW", eligibility_criteria: [{ id: "c1", dimension: "POPULATION", operator: "MATCHES", value: { description: "Students" }, decision: "INCLUDE", reason: "Population", priority: 0 }], information_sources: [], screening_strategy: "Recall first", extraction_strategy: "Later full text", synthesis_strategy: "Map", risk_of_bias_plan: "Assess later", meta_analysis_plan: "No pooling", meta_analysis_planned: false, assumptions: [], uncertainties: ["Incomplete discovery"] };
  await page.addInitScript(() => localStorage.setItem("ranahresearch-token", "fixture-token"));
  await page.route("http://127.0.0.1:8000/**", async route => {
    const path = new URL(route.request().url()).pathname;
    const project = { id: "project-1", title: "Protocol fixture", status: "PROTOCOL", ideas: [], literature_count: 0, operation: null };
    let body: unknown = null;
    if (path === "/projects") body = [project];
    else if (path === "/projects/project-1") body = project;
    else if (path.endsWith("/protocol/generate")) { current = seed; versions.push(seed); body = { operation_id: "op1", status: "COMPLETED" }; }
    else if (path.endsWith("/protocol/p1/approve")) { current = { ...current, status: "APPROVED" }; body = current; }
    else if (path.endsWith("/protocol/p1/revise")) { revision = route.request().postDataJSON(); current = { ...seed, ...revision!.protocol, id: "p2", version: 2 }; versions.unshift(current); body = current; }
    else if (path.endsWith("/protocol/versions")) body = versions;
    else if (path.endsWith("/protocol")) body = current;
    else if (path.endsWith("/literature") || path.endsWith("/screening/title-abstract")) body = [];
    await route.fulfill({ json: body });
  });
  await page.goto("/");
  await page.getByLabel("Open project").selectOption("project-1");
  await page.getByRole("button", { name: "Protocol & screening" }).click();
  await page.getByLabel("Optional protocol constraints").fill("University students");
  await page.getByRole("button", { name: "Generate review protocol" }).click();
  await expect(page.getByRole("heading", { name: "Framework: PCC" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Approve protocol", exact: true })).toBeDisabled();
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Approve protocol", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Review protocol · v1 · APPROVED" })).toBeVisible();
  await page.getByRole("button", { name: "Revise protocol" }).click();
  await page.getByRole("textbox", { name: "Criterion 1 value" }).fill("University students");
  await page.getByLabel("Reason for amendment").fill("Clarify the population");
  await page.getByRole("button", { name: "Save as new proposed version" }).click();
  await expect(page.getByRole("heading", { name: "Review protocol · v2 · PROPOSED" })).toBeVisible();
  expect(revision).toMatchObject({ reason: "Clarify the population", protocol: { eligibility_criteria: [{ value: { description: "University students" } }] } });
  await expect(page.getByRole("button", { name: "Run AI Screening" })).toBeDisabled();
});
