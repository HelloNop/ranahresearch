import { expect, test } from "@playwright/test";

test("synthesis, claim trace, manuscript editing, review, and mobile layout", async ({ page }) => {
  let edited = false;
  const project = { id: "project-1", title: "Evidence review", status: "AUTHOR_REVIEW", ideas: [], literature_count: 2, plan_status: "APPROVED", operation: null };
  const section = () => ({ id: "section-1", section_type: "RESULTS", heading: "Results", content: edited ? "Several reviewed studies reported mixed outcomes." : "Several studies reported mixed outcomes.", word_count: edited ? 6 : 5, status: edited ? "NEEDS_REVIEW" : "COMPLETE" });
  const claim = { id: "claim-1", claim_type: "SYNTHESIS", text: "Several included studies reported improved outcomes.", status: "VERIFIED", confidence: "MODERATE", verification: "SUPPORTED", recommended_qualification: null, evidence: [{ evidence_id: "evidence-1", relationship: "SUPPORTS" }] };
  const issue = { id: "issue-1", section_id: "section-1", reviewer_type: "SCIENTIFIC", severity: "MAJOR", category: "Overstatement", description: "The conclusion is stronger than the evidence.", recommended_action: "Qualify the conclusion.", status: "OPEN" };
  await page.addInitScript(() => localStorage.setItem("ranahresearch-token", "fixture-token"));
  await page.route("http://127.0.0.1:8000/**", async route => {
    const path = new URL(route.request().url()).pathname;
    let body: unknown = null;
    if (path === "/projects") body = [project];
    else if (path === "/projects/project-1") body = project;
    else if (path.endsWith("/plan") || path.endsWith("/framework") || path.endsWith("/search-strategy")) body = null;
    else if (path.endsWith("/literature")) body = [];
    else if (path.endsWith("/synthesis")) body = { id: "synthesis-1", version: 1, status: "REVIEWED", method: "NARRATIVE_SYNTHESIS", limitations: ["One study had high risk of bias."], confidence_notes: [], themes: [{ id: "theme-1", label: "Mixed short-term outcomes", description: "Effects varied between included studies.", confidence: "MODERATE", evidence: [{ evidence_id: "evidence-1", relationship: "SUPPORTS" }] }], findings: [{ id: "finding-1", text: "The reviewed evidence was inconsistent.", confidence: "MODERATE", evidence: [] }], contradictions: [{ id: "contradiction-1", description: "One study improved while another did not.", interpretation: "Design differences may explain variation.", confidence: "MODERATE", evidence: [] }], research_gaps: [{ id: "gap-1", gap_type: "LONGITUDINAL_GAP", description: "Long-term outcomes were rarely reported.", scope: "Within the reviewed corpus", supporting_observation: "One follow-up study", confidence: "LOW" }] };
    else if (path.endsWith("/claims/claim-1")) body = { ...claim, evidence: [{ id: "evidence-1", field_name: "outcome", value: "improved", relationship: "SUPPORTS", work_id: "work-1" }], studies: [{ id: "study-1", title: "AI tutoring trial" }], works: [{ id: "work-1", title: "AI tutoring trial", doi: "10.1/example" }] };
    else if (path.endsWith("/claims")) body = [claim];
    else if (path.endsWith("/manuscript")) body = { id: "manuscript-1", title: "AI tutoring outcomes", status: edited ? "REVISION_REQUIRED" : "READY_FOR_AUTHOR_REVIEW", citation_style: "APA_7", version: edited ? 2 : 1, sections: [section()], issues: [issue] };
    else if (path.endsWith("/exports")) body = [];
    else if (path.endsWith("/manuscript/sections/section-1/edit")) { edited = true; body = { version: 2, section_id: "section-2" }; }
    else if (path.endsWith("/review-issues/issue-1/revise")) body = { operation_id: "op-1", status: "PENDING" };
    await route.fulfill({ json: body });
  });

  await page.goto("/");
  await page.getByLabel("Open project").selectOption("project-1");
  await page.getByRole("button", { name: "Synthesis & manuscript" }).click();
  await expect(page.getByRole("heading", { name: "AI tutoring outcomes" })).toBeVisible();
  await page.getByRole("button", { name: "Synthesis", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Contradictions" })).toBeVisible();
  await expect(page.getByText("Within the reviewed corpus")).toBeVisible();
  await page.getByRole("button", { name: "Claim graph" }).click();
  await page.getByRole("button", { name: /Several included studies/ }).click();
  await page.getByRole("button", { name: "Manuscript", exact: true }).click();
  await page.getByRole("textbox", { name: "Edit Results" }).fill("Several reviewed studies reported mixed outcomes.");
  await page.getByRole("button", { name: "Save as new version" }).click();
  await page.getByRole("button", { name: "Review", exact: true }).click();
  await expect(page.getByText("The conclusion is stronger than the evidence.")).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  await page.screenshot({ path: "test-results/manuscript-mobile.png", fullPage: true });
});
