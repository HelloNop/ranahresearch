"""Deterministic evidence validation.

These are arithmetic and range facts, not judgements: a negative SD or an event
count above its total is wrong whatever a model says about it. Semantic
correctness is the reviewer agent's job, not this module's.
"""

import re
from dataclasses import dataclass
from typing import Any

SEVERITY_ERROR = "ERROR"
SEVERITY_WARNING = "WARNING"

_CI_PATTERN = re.compile(
    r"(-?\d+(?:\.\d+)?)\s*(?:to|,|-|–)\s*(-?\d+(?:\.\d+)?)",
)
_ESTIMATE_PATTERN = re.compile(r"(-?\d+(?:\.\d+)?)")
_CONFIDENCE_LEVEL = re.compile(r"\d+(?:\.\d+)?\s*%?\s*(?:CI|confidence\s+interval)", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class Finding:
    code: str
    severity: str
    field_name: str
    message: str


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def check_field(field_name: str, value: Any, unit: str | None = None) -> list[Finding]:
    """Range checks for one value, independent of the other fields."""
    findings: list[Finding] = []
    number = _number(value)
    if number is None:
        return findings

    if field_name in ("sample_size", "intervention_n", "comparator_n", "events", "total"):
        if number < 0:
            findings.append(
                Finding("NEGATIVE_COUNT", SEVERITY_ERROR, field_name, "A count cannot be negative")
            )
        elif number != int(number):
            findings.append(
                Finding(
                    "NON_INTEGER_COUNT",
                    SEVERITY_ERROR,
                    field_name,
                    "A count must be a whole number",
                )
            )
        elif number == 0:
            findings.append(
                Finding("ZERO_COUNT", SEVERITY_WARNING, field_name, "A count of zero is unusual")
            )
    if field_name.endswith(("_sd", "_se")) and number < 0:
        findings.append(
            Finding(
                "NEGATIVE_DISPERSION",
                SEVERITY_ERROR,
                field_name,
                "A standard deviation or error cannot be negative",
            )
        )
    if (unit or "").strip() == "%" and not 0 <= number <= 100:
        findings.append(
            Finding(
                "PERCENTAGE_OUT_OF_RANGE",
                SEVERITY_ERROR,
                field_name,
                "A percentage must fall between 0 and 100",
            )
        )
    return findings


def check_confidence_interval(field_name: str, text: str) -> list[Finding]:
    """Interval bounds must be ordered, and contain the estimate when one is stated."""
    match = _CI_PATTERN.search(text)
    if not match:
        return []
    lower, upper = float(match.group(1)), float(match.group(2))
    findings: list[Finding] = []
    if lower > upper:
        findings.append(
            Finding(
                "CI_BOUNDS_REVERSED",
                SEVERITY_ERROR,
                field_name,
                f"Confidence interval lower bound {lower} exceeds upper bound {upper}",
            )
        )
    # "95% CI" states the confidence level, not the estimate, so it must not be
    # mistaken for the point estimate sitting before the interval.
    before = _CONFIDENCE_LEVEL.sub(" ", text[: match.start()])
    estimates = _ESTIMATE_PATTERN.findall(before)
    if estimates:
        estimate = float(estimates[-1])
        if not min(lower, upper) <= estimate <= max(lower, upper):
            findings.append(
                Finding(
                    "ESTIMATE_OUTSIDE_CI",
                    SEVERITY_ERROR,
                    field_name,
                    f"Estimate {estimate} lies outside its interval {lower} to {upper}",
                )
            )
    return findings


def check_arm_consistency(values: dict[str, Any]) -> list[Finding]:
    """Cross-field arithmetic: arm totals, events within totals."""
    findings: list[Finding] = []
    total = _number(values.get("sample_size"))
    arms = [_number(values.get(name)) for name in ("intervention_n", "comparator_n")]
    if total is not None and all(arm is not None for arm in arms):
        summed = sum(arm for arm in arms if arm is not None)
        if summed != total:
            findings.append(
                Finding(
                    "ARM_TOTAL_MISMATCH",
                    SEVERITY_ERROR,
                    "sample_size",
                    f"Arm sizes sum to {summed:g} but the total sample size is {total:g}",
                )
            )
    events, denominator = _number(values.get("events")), _number(values.get("total"))
    if events is not None and denominator is not None and events > denominator:
        findings.append(
            Finding(
                "EVENTS_EXCEED_TOTAL",
                SEVERITY_ERROR,
                "events",
                f"Event count {events:g} exceeds the total {denominator:g}",
            )
        )
    return findings


def validate_study_values(values: dict[str, Any], units: dict[str, str | None]) -> list[Finding]:
    """Every deterministic check for one study's extracted values."""
    findings: list[Finding] = []
    for field_name, value in values.items():
        findings.extend(check_field(field_name, value, units.get(field_name)))
        if isinstance(value, str) and (
            "ci" in field_name.lower() or "effect" in field_name.lower()
        ):
            findings.extend(check_confidence_interval(field_name, value))
    findings.extend(check_arm_consistency(values))
    return findings
