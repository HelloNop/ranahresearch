"""Extraction schema: what this project extracts, and what shape each value takes.

The default form covers fields common to most reviews, but it is a starting
point that the protocol tailors, never a universal form imposed on every project
(docs/IMPLEMENTATION_ROADMAP.md EPIC-025).
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

FieldKind = Literal["TEXT", "NUMBER", "INTEGER", "CATEGORICAL", "LIST"]
EVIDENCE_TYPES = ("CHARACTERISTIC", "OUTCOME", "QUANTITATIVE", "NARRATIVE")


class SchemaField(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=100)
    label: str
    kind: FieldKind
    evidence_type: str = "CHARACTERISTIC"
    unit: str | None = None
    description: str = ""
    allowed_values: list[str] = Field(default_factory=list)
    required: bool = False
    retrieval_queries: list[str] = Field(default_factory=list)

    def queries(self) -> list[str]:
        return self.retrieval_queries or [f"{self.label} {self.description}".strip()]


class ExtractionSchemaDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fields: list[SchemaField]

    def by_name(self) -> dict[str, SchemaField]:
        return {field.name: field for field in self.fields}


def _field(
    name: str,
    label: str,
    kind: FieldKind,
    *,
    evidence_type: str = "CHARACTERISTIC",
    unit: str | None = None,
    description: str = "",
    queries: list[str] | None = None,
) -> SchemaField:
    return SchemaField(
        name=name,
        label=label,
        kind=kind,
        evidence_type=evidence_type,
        unit=unit,
        description=description,
        retrieval_queries=queries or [],
    )


def default_schema(
    research_question: str = "", framework_type: str = "PICO"
) -> ExtractionSchemaDefinition:
    """General review fields plus the quantitative slots meta-analysis will need.

    Quantitative fields are extracted and provenance-linked here; no pooling or
    effect-size computation happens anywhere in this layer.
    """
    context = f" {research_question}".rstrip()
    definition = ExtractionSchemaDefinition(
        fields=[
            _field(
                "study_design",
                "Study design",
                "CATEGORICAL",
                description="The design as described by the authors",
                queries=["study design randomised controlled trial cohort cross-sectional"],
            ),
            _field(
                "country",
                "Country",
                "TEXT",
                description="Where the study was conducted",
                queries=["country setting conducted recruited site"],
            ),
            _field(
                "setting",
                "Setting",
                "TEXT",
                description="The institutional or clinical setting",
                queries=["setting university hospital school clinic community"],
            ),
            _field(
                "population_description",
                "Population",
                "TEXT",
                description="Who the participants were",
                queries=[f"participants population inclusion eligibility{context}"],
            ),
            _field(
                "sample_size",
                "Sample size",
                "INTEGER",
                evidence_type="QUANTITATIVE",
                unit="participants",
                description="Total analysed participants across arms",
                queries=["total participants enrolled randomised sample size n"],
            ),
            _field(
                "intervention",
                "Intervention",
                "TEXT",
                description="What the intervention or exposure was",
                queries=[f"intervention exposure treatment programme{context}"],
            ),
            _field(
                "comparator",
                "Comparator",
                "TEXT",
                description="What the intervention was compared against",
                queries=["comparator control group usual care placebo"],
            ),
            _field(
                "outcomes",
                "Outcomes",
                "LIST",
                evidence_type="OUTCOME",
                description="Outcomes measured, with measurement tool where stated",
                queries=["primary outcome secondary outcome measured instrument scale"],
            ),
            _field(
                "duration",
                "Duration",
                "TEXT",
                description="Follow-up or study duration",
                queries=["duration follow-up weeks months timepoint"],
            ),
            _field(
                "key_findings",
                "Key findings",
                "TEXT",
                evidence_type="NARRATIVE",
                description="The authors' reported primary result",
                queries=["results findings significant difference effect"],
            ),
            _field(
                "limitations",
                "Limitations",
                "TEXT",
                evidence_type="NARRATIVE",
                description="Limitations the authors acknowledge",
                queries=["limitations weakness caution generalisability"],
            ),
            _field(
                "intervention_mean",
                "Intervention group mean",
                "NUMBER",
                evidence_type="QUANTITATIVE",
                description="Mean outcome value in the intervention arm",
                queries=["mean intervention group score"],
            ),
            _field(
                "intervention_sd",
                "Intervention group SD",
                "NUMBER",
                evidence_type="QUANTITATIVE",
                description="Standard deviation in the intervention arm",
                queries=["standard deviation SD intervention group"],
            ),
            _field(
                "comparator_mean",
                "Comparator group mean",
                "NUMBER",
                evidence_type="QUANTITATIVE",
                description="Mean outcome value in the comparator arm",
                queries=["mean control comparator group score"],
            ),
            _field(
                "comparator_sd",
                "Comparator group SD",
                "NUMBER",
                evidence_type="QUANTITATIVE",
                description="Standard deviation in the comparator arm",
                queries=["standard deviation SD control comparator group"],
            ),
            _field(
                "effect_estimate",
                "Effect estimate",
                "TEXT",
                evidence_type="QUANTITATIVE",
                description="Reported effect estimate with its confidence interval",
                queries=["difference effect estimate 95% CI confidence interval"],
            ),
        ]
    )
    if framework_type not in {"PICO", "PICOS"}:
        intervention_only = {
            "comparator",
            "intervention_mean",
            "intervention_sd",
            "comparator_mean",
            "comparator_sd",
            "effect_estimate",
        }
        definition.fields = [
            field for field in definition.fields if field.name not in intervention_only
        ]
    return definition


def schema_payload(research_question: str = "", framework_type: str = "PICO") -> dict[str, Any]:
    return default_schema(research_question, framework_type).model_dump(mode="json")
