"""scan — open-source LLM evidence-pack toolkit."""
from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from . import __version__
from .context import ScanContext
from .manifest import Manifest, save_manifest
from .util.io import load_json

log = logging.getLogger("garuda")
FAIL_LEVELS = {"error": ("error",), "warning": ("error", "warning")}


def _add_fail_on(p: argparse.ArgumentParser) -> None:
    p.add_argument("--fail-on", choices=sorted(FAIL_LEVELS),
                   help="Exit 1 if unsuppressed findings at or above this level exist")


def _add_static_args(p: argparse.ArgumentParser) -> None:
    src_g = p.add_mutually_exclusive_group(required=True)
    src_g.add_argument("repo", nargs="?", help="HF repo id, e.g. meta-llama/Foo")
    src_g.add_argument("--local-path", type=Path, help="Path to on-disk model")
    p.add_argument("--revision", default="main")
    p.add_argument("--repo-id", help="Canonical name when using --local-path")
    p.add_argument("--out", type=Path, default=None, help="Output scan dir")
    p.add_argument("--signer-identity",
                   help="Expected Sigstore signer of model.sig (email or workload URI)")
    p.add_argument("--signer-issuer",
                   help="Expected OIDC issuer for --signer-identity")
    p.add_argument("--expect-publisher", help="Expected HF org/user that owns the repo")


BANNER = r"""
   ____    _    ____  _   _ ____    _
  / ___|  / \  |  _ \| | | |  _ \  / \
 | |  _  / _ \ | |_) | | | | | | |/ _ \
 | |_| |/ ___ \|  _ <| |_| | |_| / ___ \
  \____/_/   \_\_| \_\\___/|____/_/   \_\
"""


def _banner(rows: list[tuple[str, str]]) -> None:
    lines = [BANNER.rstrip("\n"), f"  garuda {__version__} - static security scan for open-source LLMs", ""]
    lines += [f"  {k:<10} {v}" for k, v in rows]
    print("\n".join(lines) + "\n", file=sys.stderr)


def _setup_logging(verbosity: int) -> None:
    level = {-1: logging.WARNING, 0: logging.INFO}.get(verbosity, logging.DEBUG)
    fmt = "%(asctime)s %(levelname)-7s " + ("%(name)s: " if level == logging.DEBUG else "")
    logging.basicConfig(level=level, stream=sys.stderr, force=True,
                        format=fmt + "%(message)s",
                        datefmt="%H:%M:%S")
    # third-party chatter (HTTP requests, download progress internals)
    for noisy in ("httpx", "urllib3", "huggingface_hub", "filelock"):
        logging.getLogger(noisy).setLevel(max(level, logging.WARNING))


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    vg = common.add_mutually_exclusive_group()
    vg.add_argument("-v", "--verbose", action="store_const", const=1, dest="verbosity",
                    default=0, help="Debug logging (tool command lines)")
    vg.add_argument("-q", "--quiet", action="store_const", const=-1, dest="verbosity",
                    help="Warnings and errors only; no banner")
    parser = argparse.ArgumentParser(prog="scan", description="OS LLM scan toolkit")
    parser.add_argument("--version", action="version", version=f"garuda {__version__}")
    sub = parser.add_subparsers(dest="cmd", required=True)
    static_p = sub.add_parser("static", help="Static evidence-pack stage", parents=[common])
    _add_static_args(static_p)
    all_p = sub.add_parser("all", help="static + report", parents=[common])
    _add_static_args(all_p)
    _add_fail_on(all_p)
    report_p = sub.add_parser("report", help="Regenerate SARIF + HTML from an existing scan dir",
                              parents=[common])
    report_p.add_argument("scan_dir", type=Path, help="Path to an existing scan directory")
    _add_fail_on(report_p)
    return parser


def _run_static(args: argparse.Namespace) -> Path | None:
    from .runner import run_static

    # absolute paths: tool subprocesses run with cwd=scan_dir, and weights/ is a symlink
    repo = args.repo
    local = args.local_path.resolve() if args.local_path else None
    if local is not None:
        repo = args.repo_id or f"local:{local.name}"
    if not repo:
        print(f"{args.cmd}: must pass repo OR --local-path", file=sys.stderr)
        return None
    if bool(args.signer_identity) != bool(args.signer_issuer):
        print(f"{args.cmd}: --signer-identity and --signer-issuer go together", file=sys.stderr)
        return None
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    safe = repo.replace("/", "_")
    scan_dir = (args.out or Path(f"scan_{safe}_{ts}")).resolve()
    ctx = ScanContext(
        scan_dir=scan_dir,
        repo=repo,
        revision=args.revision,
        local_path=local,
        signer_identity=args.signer_identity,
        signer_issuer=args.signer_issuer,
        expect_publisher=args.expect_publisher,
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
    if args.verbosity >= 0:
        _banner([("Command", args.cmd),
                 ("Target", str(local) if local else repo),
                 ("Revision", "(local)" if local else args.revision),
                 ("Scan dir", str(scan_dir)),
                 ("Started", datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC"))])
    t0 = time.monotonic()
    skipped = run_static(ctx)
    m.resolved_sha = (load_json(ctx.raw_dir / "01_metadata.json") or {}).get("sha")
    m.mark_static_done(duration_s=time.monotonic() - t0, skipped_steps=skipped)
    save_manifest(m)
    print(f"Scan dir: {scan_dir}")
    return scan_dir


def _report(scan_dir: Path, fail_on: str | None) -> int:
    from .report.suppress import is_suppressed
    from .runner import run_report

    sarif_path, html_path = run_report(scan_dir)
    log.info("SARIF: %s", sarif_path)
    log.info("HTML:  %s", html_path)
    if not fail_on:
        return 0
    # level default "note" matches the HTML verdict in report/html.py
    hits = sum(1 for run in (load_json(sarif_path) or {}).get("runs", [])
               for res in run.get("results", [])
               if not is_suppressed(res) and res.get("level", "note") in FAIL_LEVELS[fail_on])
    if hits:
        print(f"--fail-on {fail_on}: {hits} finding(s) at or above threshold", file=sys.stderr)
    return 1 if hits else 0


def _cmd_static(args: argparse.Namespace) -> int:
    return 0 if _run_static(args) else 2


def _cmd_all(args: argparse.Namespace) -> int:
    scan_dir = _run_static(args)
    if scan_dir is None:
        return 2
    return _report(scan_dir, args.fail_on)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _setup_logging(args.verbosity)
    if args.cmd == "static":
        return _cmd_static(args)
    if args.cmd == "all":
        return _cmd_all(args)
    if args.cmd == "report":
        return _report(args.scan_dir, args.fail_on)
    print(f"cmd={args.cmd}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
