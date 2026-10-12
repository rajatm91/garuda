"""scan — open-source LLM evidence-pack toolkit."""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from .context import ScanContext
from .manifest import Manifest, save_manifest


def _add_static_args(p: argparse.ArgumentParser) -> None:
    src_g = p.add_mutually_exclusive_group(required=True)
    src_g.add_argument("repo", nargs="?", help="HF repo id, e.g. meta-llama/Foo")
    src_g.add_argument("--local-path", type=Path, help="Path to on-disk model")
    p.add_argument("--revision", default="main")
    p.add_argument("--repo-id", help="Canonical name when using --local-path")
    p.add_argument("--out", type=Path, default=None, help="Output scan dir")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="scan", description="OS LLM scan toolkit")
    sub = parser.add_subparsers(dest="cmd", required=True)
    static_p = sub.add_parser("static", help="Static evidence-pack stage")
    _add_static_args(static_p)
    all_p = sub.add_parser("all", help="static + report")
    _add_static_args(all_p)
    report_p = sub.add_parser("report", help="Regenerate SARIF + HTML from an existing scan dir")
    report_p.add_argument("scan_dir", type=Path, help="Path to an existing scan directory")
    return parser


def _run_static(args: argparse.Namespace) -> Path | None:
    from .runner import run_static

    repo, local = args.repo, args.local_path
    if local is not None:
        repo = args.repo_id or f"local:{local.name}"
    if not repo:
        print(f"{args.cmd}: must pass repo OR --local-path", file=sys.stderr)
        return None
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe = repo.replace("/", "_")
    scan_dir = args.out or Path.cwd() / f"scan_{safe}_{ts}"
    ctx = ScanContext(
        scan_dir=scan_dir,
        repo=repo,
        revision=args.revision,
        local_path=local,
    )
    m = Manifest.create(
        scan_dir=scan_dir,
        repo=repo,
        revision=args.revision,
        source_mode="local_path" if local else "hf",
        source_abs_path=str(local.resolve()) if local else None,
    )
    scan_dir.mkdir(parents=True, exist_ok=True)
    save_manifest(m)
    t0 = time.monotonic()
    skipped = run_static(ctx)
    m.mark_static_done(duration_s=time.monotonic() - t0, skipped_steps=skipped)
    save_manifest(m)
    print(f"Scan dir: {scan_dir}")
    return scan_dir


def _cmd_static(args: argparse.Namespace) -> int:
    return 0 if _run_static(args) else 2


def _cmd_all(args: argparse.Namespace) -> int:
    from .runner import run_report

    scan_dir = _run_static(args)
    if scan_dir is None:
        return 2
    run_report(scan_dir)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "static":
        return _cmd_static(args)
    if args.cmd == "all":
        return _cmd_all(args)
    if args.cmd == "report":
        from .runner import run_report
        run_report(args.scan_dir)
        return 0
    print(f"cmd={args.cmd}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
