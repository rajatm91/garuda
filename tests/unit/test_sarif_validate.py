import pytest

from garuda.report._validate import validate_sarif


def test_minimal_valid_log_passes():
    log = {
        "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
        "version": "2.1.0",
        "runs": [{"tool": {"driver": {"name": "x"}}, "results": []}],
    }
    validate_sarif(log)


def test_missing_version_raises():
    with pytest.raises(Exception):
        validate_sarif({"runs": []})
