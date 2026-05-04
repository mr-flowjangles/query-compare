"""Schema model + type categorization.

Columns are classified into a small number of categories that determine the
comparison rule applied in the generated SQL:

  TEXT          -> COALESCE(col, '') equality (NULL == '')
  TIMESTAMP_TZ  -> normalized to UTC before compare
  OTHER         -> NULL-safe equality (IS NOT DISTINCT FROM)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class TypeCategory(Enum):
    TEXT = "text"
    TIMESTAMP_TZ = "timestamp_tz"
    OTHER = "other"


_TEXT_TYPES = {
    "text",
    "varchar",
    "character varying",
    "char",
    "character",
    "bpchar",
    "citext",
    "name",
}

_TIMESTAMP_TZ_TYPES = {
    "timestamptz",
    "timestamp with time zone",
    "timetz",
    "time with time zone",
}


def categorize(pg_type: str) -> TypeCategory:
    """Classify a raw Postgres type string from `\\d` output."""
    base = _strip_type_modifiers(pg_type).lower().strip()
    if base in _TEXT_TYPES:
        return TypeCategory.TEXT
    if base in _TIMESTAMP_TZ_TYPES:
        return TypeCategory.TIMESTAMP_TZ
    return TypeCategory.OTHER


def _strip_type_modifiers(pg_type: str) -> str:
    """Strip parameterization and array brackets:

    'character varying(100)' -> 'character varying'
    'numeric(10,2)'          -> 'numeric'
    'integer[]'              -> 'integer'
    """
    s = pg_type.strip()
    if "(" in s:
        s = s[: s.index("(")].rstrip()
    if s.endswith("[]"):
        s = s[:-2].rstrip()
    return s


@dataclass(frozen=True)
class Column:
    name: str
    raw_type: str

    @property
    def category(self) -> TypeCategory:
        return categorize(self.raw_type)


@dataclass(frozen=True)
class Schema:
    """Parsed schema of a table or view."""

    qualified_name: str  # e.g. "public.patient"
    kind: str            # "table" or "view"
    columns: tuple[Column, ...]

    def column_names(self) -> list[str]:
        return [c.name for c in self.columns]

    def non_key_columns(self, key: list[str]) -> list[Column]:
        keyset = set(key)
        return [c for c in self.columns if c.name not in keyset]
