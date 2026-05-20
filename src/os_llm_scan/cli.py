"""scan — open-source LLM evidence-pack toolkit."""
from __future__ import annotations

import argparse
import sys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="scan", description="OS LLM scan toolkit")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("static", help="Static evidence-pack stage")
    sub.add_parser("dynamic", help="Behavioural-eval stage")
    sub.add_parser("all", help="static + dynamic + report")
    sub.add_parser("report", help="Regenerate SARIF + HTML from an existing scan dir")
    sub.add_parser("serve", help="Internal: host a model for local-serve mode")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    print(f"cmd={args.cmd}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
