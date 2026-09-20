"""risk_of_bias_foundation

Revision ID: 926c9833b614
Revises: 5baf40062978
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "926c9833b614"
down_revision: str | None = "5baf40062978"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "risk_of_bias_assessments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "project_id",
            sa.Uuid(),
            sa.ForeignKey("research_projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "study_id", sa.Uuid(), sa.ForeignKey("studies.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("tool", sa.String(30), nullable=False),
        sa.Column("tool_version", sa.String(30), nullable=False),
        sa.Column("overall_judgement", sa.String(30), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("reviewer_id", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("agent_run_id", sa.Uuid(), sa.ForeignKey("agent_runs.id")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.UniqueConstraint("study_id", "version"),
    )
    op.create_index(
        "ix_risk_of_bias_assessments_project_id", "risk_of_bias_assessments", ["project_id"]
    )
    op.create_index(
        "ix_risk_of_bias_assessments_study_id", "risk_of_bias_assessments", ["study_id"]
    )
    op.create_table(
        "risk_of_bias_domains",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "assessment_id",
            sa.Uuid(),
            sa.ForeignKey("risk_of_bias_assessments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("domain_code", sa.String(50), nullable=False),
        sa.Column("judgement", sa.String(30), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("supporting_evidence", sa.Text(), nullable=False),
        sa.Column("work_id", sa.Uuid(), sa.ForeignKey("work_records.id")),
        sa.Column("page", sa.Integer()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.UniqueConstraint("assessment_id", "domain_code"),
    )
    op.create_index(
        "ix_risk_of_bias_domains_assessment_id", "risk_of_bias_domains", ["assessment_id"]
    )
    op.execute("""
    CREATE TRIGGER risk_assessment_immutable BEFORE UPDATE OR DELETE ON risk_of_bias_assessments
    FOR EACH ROW EXECUTE FUNCTION protect_evidence_history();
    CREATE TRIGGER risk_domain_immutable BEFORE UPDATE OR DELETE ON risk_of_bias_domains
    FOR EACH ROW EXECUTE FUNCTION protect_evidence_history();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER risk_domain_immutable ON risk_of_bias_domains")
    op.execute("DROP TRIGGER risk_assessment_immutable ON risk_of_bias_assessments")
    op.drop_index("ix_risk_of_bias_domains_assessment_id", table_name="risk_of_bias_domains")
    op.drop_table("risk_of_bias_domains")
    op.drop_index("ix_risk_of_bias_assessments_study_id", table_name="risk_of_bias_assessments")
    op.drop_index("ix_risk_of_bias_assessments_project_id", table_name="risk_of_bias_assessments")
    op.drop_table("risk_of_bias_assessments")
