"""Subprocess wrapper. Streams stdout/stderr to files. Returns exit code + duration."""
from __future__ import annotations

import logging
import subprocess
import time
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class RunResult:
    exit_code: int
    duration_s: float


def run_tool(
    name: str,
    argv: list[str],
    *,
    stdout_path: Path | None = None,
    stderr_path: Path | None = None,
    timeout: int | None = None,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> RunResult:
    log.debug("run %s: %s", name, " ".join(argv))
    t0 = time.monotonic()

    with ExitStack() as stack:
        stdout_f = stack.enter_context(open(stdout_path, "wb")) if stdout_path else subprocess.DEVNULL
        stderr_f = stack.enter_context(open(stderr_path, "wb")) if stderr_path else subprocess.DEVNULL
        try:
            proc = subprocess.Popen(argv, stdout=stdout_f, stderr=stderr_f, cwd=cwd, env=env)
            try:
                exit_code = proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
                exit_code = 124
        except FileNotFoundError:
            exit_code = 127

    dur = time.monotonic() - t0
    log.log(logging.WARNING if exit_code in (124, 127) else logging.DEBUG,
            "%s: exit=%d (%.1fs)%s", name, exit_code, dur,
            {124: " timed out", 127: " not found"}.get(exit_code, ""))
    return RunResult(exit_code=exit_code, duration_s=dur)
