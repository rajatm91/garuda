import json
from unittest.mock import patch

import pytest

from garuda.cli import main
from garuda.report.suppress import MARKER


def _sarif(tmp_path, *levels, suppressed=()):
    results = [{"level": lvl} for lvl in levels]
    results += [{"level": lvl, "suppressions": [{"properties": {"source": MARKER}}]}
                for lvl in suppressed]
    p = tmp_path / "scan_results.sarif"
    p.write_text(json.dumps({"runs": [{"results": results}]}))
    return p


def _run(tmp_path, sarif, *flags):
    with patch("garuda.runner.run_report", return_value=(sarif, tmp_path / "r.html")):
        return main(["report", str(tmp_path), *flags])


@pytest.mark.parametrize("levels,suppressed,flag,rc", [
    (("error",), (), None, 0),               # default unchanged
    (("error",), (), "error", 1),
    (("warning",), (), "error", 0),
    (("warning",), (), "warning", 1),
    (("note",), (), "warning", 0),
    ((), ("error",), "error", 0),            # suppressed findings don't count
])
def test_fail_on(tmp_path, levels, suppressed, flag, rc):
    sarif = _sarif(tmp_path, *levels, suppressed=suppressed)
    assert _run(tmp_path, sarif, *(["--fail-on", flag] if flag else [])) == rc
