import httpx
import pytest
from ranah_agents.risk_of_bias import TOOLS, select_tool
from ranah_domain.enums import StudyType
from sqlalchemy.ext.asyncio import AsyncEngine
from test_extraction_slice import api_client as api_client
from test_extraction_slice import run_pipeline


def test_tool_selection_follows_study_design() -> None:
    assert select_tool(StudyType.RCT) == "ROB_2"
    assert select_tool(StudyType.QUASI_EXPERIMENTAL) == "ROBINS_I"
    assert select_tool(StudyType.COHORT) is None


async def test_risk_assessment_requires_design_and_keeps_domain_history(
    api_client: httpx.AsyncClient, db_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_id, _ = await run_pipeline(api_client, db_engine, monkeypatch, risk_study_type="RCT")
    base = f"/projects/{project_id}"
    study = (await api_client.get(f"{base}/studies")).json()[0]

    assessments = (await api_client.get(f"{base}/risk-of-bias")).json()
    assert len(assessments) == 1
    row = assessments[0]
    assert row["study_id"] == study["id"]
    assert row["tool"] == "ROB_2" and row["tool_version"] == "foundation-1"
    assert row["status"] == "NEEDS_REVIEW"
    assert row["overall_judgement"] == "NOT_ASSESSED"
    assert {domain["domain_code"] for domain in row["domains"]} == set(TOOLS["ROB_2"])
    assert row["agent_run_id"]

    assert len((await api_client.get(f"{base}/risk-of-bias")).json()) == 1
