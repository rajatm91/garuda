import json
from pathlib import Path

import jsonschema
import pytest

_SCHEMA = json.loads((Path(__file__).parents[1] / "fixtures" / "sarif-schema-2.1.0.json").read_text())


def validate_sarif(log: dict) -> None:
    jsonschema.validate(log, _SCHEMA)


def test_minimal_valid_log_passes():
    log = {
        "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
        "version": "2.1.0",
        "runs": [{"tool": {"driver": {"name": "x"}}, "results": []}],
    }
    validate_sarif(log)


def test_missing_version_raises():
    with pytest.raises(jsonschema.ValidationError):
        validate_sarif({"runs": []})
