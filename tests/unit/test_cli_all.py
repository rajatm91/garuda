from unittest.mock import patch

from os_llm_scan.cli import main


def test_all_runs_three_phases(tmp_path):
    local = tmp_path / "model"
    local.mkdir()
    (local / "config.json").write_text("{}")
    out = tmp_path / "out"
    policy = tmp_path / "policy.yaml"
    policy.write_text(
        "version: 1\njudge: {}\ncategories: {bias: "
        "{engine: promptfoo, plugins: [bias], sample_size: 5, "
        "thresholds: {error: 0.5, warning: 0.1}}}"
    )
    with patch("os_llm_scan.runner.run_static", return_value=[]) as rs, \
         patch("os_llm_scan.runner.run_dynamic") as rd, \
         patch("os_llm_scan.runner.run_report") as rp:
        rc = main(["all", "--local-path", str(local), "--out", str(out),
                   "--endpoint", "http://api.x/v1", "--model", "Foo",
                   "--policy", str(policy)])
    assert rc == 0
    assert rs.called and rd.called and rp.called
