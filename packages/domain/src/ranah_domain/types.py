"""Small column-type helpers shared across models."""

import enum

from sqlalchemy import Enum


def enum_column(enum_cls: type[enum.Enum], length: int = 40) -> Enum:
    """String-backed enum column: avoids ALTER TYPE churn on every added value."""
    return Enum(enum_cls, native_enum=False, length=length, validate_strings=True)
