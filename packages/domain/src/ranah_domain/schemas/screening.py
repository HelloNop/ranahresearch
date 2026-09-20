from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, from_attributes=True)


class Dimension(StrEnum):
    POPULATION = "POPULATION"
    INTERVENTION = "INTERVENTION"
    EXPOSURE = "EXPOSURE"
    COMPARATOR = "COMPARATOR"
    OUTCOME = "OUTCOME"
    STUDY_DESIGN = "STUDY_DESIGN"
    SETTING = "SETTING"
    PUBLICATION_TYPE = "PUBLICATION_TYPE"
    YEAR = "YEAR"
    LANGUAGE = "LANGUAGE"
    COUNTRY = "COUNTRY"
    PEER_REVIEW = "PEER_REVIEW"
    OTHER = "OTHER"


class ScreeningStage(StrEnum):
    TITLE_ABSTRACT = "TITLE_ABSTRACT"
    FULL_TEXT = "FULL_TEXT"


class ReasonCode(StrEnum):
    """Standardized exclusion reasons. FULL_TEXT_UNAVAILABLE and
    INSUFFICIENT_DATA_FOR_ELIGIBILITY apply only at the full-text stage, and
    FULL_TEXT_UNAVAILABLE is recorded by the system from a real retrieval
    outcome, never chosen by an agent."""

    WRONG_POPULATION = "WRONG_POPULATION"
    WRONG_INTERVENTION = "WRONG_INTERVENTION"
    WRONG_EXPOSURE = "WRONG_EXPOSURE"
    WRONG_COMPARATOR = "WRONG_COMPARATOR"
    WRONG_OUTCOME = "WRONG_OUTCOME"
    WRONG_STUDY_DESIGN = "WRONG_STUDY_DESIGN"
    WRONG_SETTING = "WRONG_SETTING"
    WRONG_PUBLICATION_TYPE = "WRONG_PUBLICATION_TYPE"
    OUTSIDE_DATE_RANGE = "OUTSIDE_DATE_RANGE"
    WRONG_LANGUAGE = "WRONG_LANGUAGE"
    NOT_PRIMARY_RESEARCH = "NOT_PRIMARY_RESEARCH"
    FULL_TEXT_UNAVAILABLE = "FULL_TEXT_UNAVAILABLE"
    INSUFFICIENT_DATA_FOR_ELIGIBILITY = "INSUFFICIENT_DATA_FOR_ELIGIBILITY"
    OTHER = "OTHER"


STAGE_ONLY_REASONS = {
    ReasonCode.FULL_TEXT_UNAVAILABLE,
    ReasonCode.INSUFFICIENT_DATA_FOR_ELIGIBILITY,
}
AGENT_FORBIDDEN_REASONS = {ReasonCode.FULL_TEXT_UNAVAILABLE}


Text = Annotated[str, Field(min_length=1, max_length=12000)]


class Description(StrictModel):
    description: Text


class Criterion(StrictModel):
    dimension: Dimension
    operator: Literal["MATCHES", "GTE", "LTE", "EQ", "IN", "NOT_IN"]
    value: StrictInt | StrictBool | list[str] | Description
    decision: Literal["INCLUDE", "EXCLUDE"]
    reason: Text
    priority: int = Field(default=0, ge=0, le=1000)

    @model_validator(mode="after")
    def typed_value(self) -> "Criterion":
        if self.dimension == Dimension.YEAR:
            valid = self.operator in ("GTE", "LTE", "EQ") and type(self.value) is int
            valid = valid and 1500 <= self.value <= 2100  # type: ignore[operator]
        elif self.dimension in (Dimension.LANGUAGE, Dimension.PUBLICATION_TYPE, Dimension.COUNTRY):
            valid = self.operator in ("IN", "NOT_IN") and isinstance(self.value, list)
            valid = valid and bool(self.value) and all(str(v).strip() for v in self.value)  # type: ignore[union-attr]
        elif self.dimension == Dimension.PEER_REVIEW:
            valid = self.operator == "EQ" and type(self.value) is bool
        else:
            valid = self.operator == "MATCHES" and isinstance(self.value, Description)
        if not valid:
            raise ValueError("Invalid operator/value for criterion dimension")
        return self


class BoundCriterion(Criterion):
    id: UUID


class Assessment(StrictModel):
    criterion_id: UUID
    result: Literal["PASS", "FAIL", "UNKNOWN", "NOT_APPLICABLE"]
    reason: Text
    evidence: str | None = None


REASON_DIMENSIONS = {
    ReasonCode.OUTSIDE_DATE_RANGE: Dimension.YEAR,
    ReasonCode.WRONG_LANGUAGE: Dimension.LANGUAGE,
    ReasonCode.NOT_PRIMARY_RESEARCH: Dimension.STUDY_DESIGN,
    **{ReasonCode(f"WRONG_{d}"): d for d in Dimension if f"WRONG_{d}" in ReasonCode},
}


def evaluate(
    criterion: BoundCriterion, metadata: dict[str, object], trusted: set[str]
) -> Assessment:
    field = {
        Dimension.YEAR: "publication_year",
        Dimension.LANGUAGE: "language",
        Dimension.PUBLICATION_TYPE: "publication_type",
    }.get(criterion.dimension)
    value = metadata.get(field) if field else None
    result = "UNKNOWN"
    if field in trusted and value is not None:
        if (
            criterion.operator in ("GTE", "LTE", "EQ")
            and type(value) is int
            and type(criterion.value) is int
        ):
            matched = {
                "GTE": value >= criterion.value,
                "LTE": value <= criterion.value,
                "EQ": value == criterion.value,
            }[criterion.operator]
        elif isinstance(value, str) and isinstance(criterion.value, list):
            matched = value.casefold() in [item.casefold() for item in criterion.value]
            if criterion.operator == "NOT_IN":
                matched = not matched
        else:
            return Assessment(
                criterion_id=criterion.id, result="UNKNOWN", reason="Metadata type is uncertain"
            )
        passed = matched if criterion.decision == "INCLUDE" else not matched
        result = "PASS" if passed else "FAIL"
    return Assessment(
        criterion_id=criterion.id,
        result=result,  # type: ignore[arg-type]
        reason="Trusted metadata evaluated"
        if result != "UNKNOWN"
        else "Missing, untrusted, or semantic metadata",
        evidence=str(value) if result != "UNKNOWN" else None,
    )
