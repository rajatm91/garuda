"""SARIF 2.1.0 schema validation."""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema

_SCHEMA_PATH = (
    Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "sarif-schema-2.1.0.json"
)


def validate_sarif(log: dict) -> None:
    """Validate a SARIF log dict against the bundled schema.

    Raises ``jsonschema.ValidationError`` on failure.
    """
    jsonschema.validate(log, json.loads(_SCHEMA_PATH.read_text()))
