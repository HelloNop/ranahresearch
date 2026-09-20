"""Discovery artifacts, durable operation progress and scoped identifiers."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "c19a_discovery_slice"
down_revision = "b6ffd5d63bd9"
branch_labels = None
depends_on = None


def upgrade():
    for table in ("research_plans", "search_strategies"):
        op.add_column(table, sa.Column("content", postgresql.JSONB(), nullable=False, server_default="{}"))
    links = [
        ("research_plans", "research_idea_id", "research_ideas"),
        ("research_frameworks", "research_plan_id", "research_plans"),
        ("research_frameworks", "created_by_agent_run_id", "agent_runs"),
        ("search_strategies", "research_plan_id", "research_plans"),
        ("search_strategies", "research_framework_id", "research_frameworks"),
        ("search_strategies", "created_by_agent_run_id", "agent_runs"),
        ("search_runs", "operation_id", "workflow_runs"),
    ]
    for table, column, target in links:
        op.add_column(table, sa.Column(column, sa.Uuid(), sa.ForeignKey(f"{target}.id")))
    op.create_unique_constraint("uq_framework_plan", "research_frameworks", ["research_plan_id"])
    op.create_unique_constraint("uq_search_run_operation_query", "search_runs", ["operation_id", "search_query_id"])
    op.add_column("workflow_runs", sa.Column("stage", sa.String(100), nullable=False, server_default="PENDING"))
    op.add_column("workflow_runs", sa.Column("details", postgresql.JSONB(), nullable=False, server_default="{}"))
    inspector = sa.inspect(op.get_bind())
    for constraint in inspector.get_unique_constraints("work_identifiers"):
        if set(constraint["column_names"]) == {"provider", "identifier"}:
            op.drop_constraint(constraint["name"], "work_identifiers", type_="unique")
    op.create_unique_constraint("uq_work_provider_identifier", "work_identifiers", ["work_id", "provider", "identifier"])


def downgrade():
    op.drop_constraint("uq_work_provider_identifier", "work_identifiers", type_="unique")
    # Existing multi-project identifiers may require consolidation before downgrade.
    op.create_unique_constraint("work_identifiers_provider_identifier_key", "work_identifiers", ["provider", "identifier"])
    op.drop_column("workflow_runs", "details")
    op.drop_column("workflow_runs", "stage")
    op.drop_constraint("uq_search_run_operation_query", "search_runs", type_="unique")
    op.drop_column("search_runs", "operation_id")
    for table, columns in {
        "search_strategies": ["content", "research_plan_id", "research_framework_id", "created_by_agent_run_id"],
        "research_frameworks": ["research_plan_id", "created_by_agent_run_id"],
        "research_plans": ["content", "research_idea_id"],
    }.items():
        for column in columns:
            op.drop_column(table, column)
