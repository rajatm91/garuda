"""scan — open-source LLM evidence-pack toolkit."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="scan", description="OS LLM scan toolkit")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("static", help="Static evidence-pack stage")
    sub.add_parser("dynamic", help="Behavioural-eval stage")
    sub.add_parser("all", help="static + dynamic + report")
    p_report = sub.add_parser("report", help="Regenerate SARIF + HTML from an existing scan dir")
    p_report.add_argument("scan_dir", type=Path, help="Path to an existing scan directory")
    sub.add_parser("serve", help="Internal: host a model for local-serve mode")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "report":
        from .runner import run_report
        run_report(args.scan_dir)
        return 0
    print(f"cmd={args.cmd}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
