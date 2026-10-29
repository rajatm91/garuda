"""HTML report renderer — self-contained (inline CSS + SVG, no external assets)."""
from __future__ import annotations

import html
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..util.io import load_json
from .model_card import model_summary
from .review_notes import load_notes
from .suppress import is_suppressed
from .translators.review import sbom_summary

# ---------------------------------------------------------------------------
# CSS — embedded, no external deps. Light theme only (+ print).
# ---------------------------------------------------------------------------
CSS = """
:root {
  --bg: #f4f6fb; --surface: #ffffff; --surface-2: #f8fafc; --fg: #0f172a; --muted: #5b6577;
  --border: #e3e8f0; --primary: #1e40af; --primary-2: #3b82f6; --hero: #0b1736; --hero-2: #1e3a8a;
  --err: #b91c1c; --err-bg: #fef2f2; --err-bd: #fecaca;
  --warn: #b45309; --warn-bg: #fffbeb; --warn-bd: #fde68a;
  --note: #1d4ed8; --note-bg: #eff6ff; --note-bd: #bfdbfe;
  --ok: #15803d; --ok-bg: #f0fdf4; --ok-bd: #bbf7d0;
  --shadow: 0 1px 2px rgba(15,23,42,.06), 0 4px 12px rgba(15,23,42,.05);
  --mono: ui-monospace, "SF Mono", SFMono-Regular, Menlo, Consolas, monospace;
  color-scheme: light;
}
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
@media (prefers-reduced-motion: reduce) { html { scroll-behavior: auto; } }
body { margin: 0; background: var(--bg); color: var(--fg);
  font: 15px/1.6 -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, Roboto, "Helvetica Neue",
        Arial, sans-serif; font-variant-numeric: tabular-nums; }
a { color: var(--primary); }
code { font-family: var(--mono); font-size: 12.5px; background: var(--surface-2);
  border: 1px solid var(--border); padding: 1px 6px; border-radius: 5px; word-break: break-all; }
.icon { width: 16px; height: 16px; flex: none; vertical-align: -3px; }

/* hero */
.hero { background: linear-gradient(135deg, var(--hero) 0%, var(--hero-2) 100%); color: #fff;
  padding: 36px 24px 28px; }
.hero .inner, .nav .inner, main { max-width: 1160px; margin: 0 auto; }
.eyebrow { text-transform: uppercase; letter-spacing: .12em; font-size: 12px; opacity: .75;
  display: flex; align-items: center; gap: 8px; }
.hero h1 { margin: 8px 0 6px; font-size: 30px; line-height: 1.2; font-weight: 700;
  word-break: break-word; }
.hero .meta { opacity: .85; font-size: 14px; display: flex; flex-wrap: wrap; gap: 6px 18px; }
.hero .meta code { background: rgba(255,255,255,.12); border-color: rgba(255,255,255,.18);
  color: #fff; }
.hero .top { display: flex; justify-content: space-between; align-items: flex-start; gap: 24px;
  flex-wrap: wrap; }
.chips { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 18px; }
.chip { background: rgba(255,255,255,.1); border: 1px solid rgba(255,255,255,.2);
  border-radius: 999px; padding: 4px 12px; font-size: 13px; }
.chip b { font-weight: 600; opacity: .7; margin-right: 6px; }
.verdict { display: inline-flex; align-items: center; gap: 10px; border-radius: 12px;
  padding: 12px 18px; font-weight: 700; letter-spacing: .04em; font-size: 15px;
  border: 1px solid; background: #fff; }
.verdict small { display: block; font-weight: 500; letter-spacing: 0; font-size: 12px; opacity: .8; }
.verdict.fail { color: #991b1b; border-color: #fecaca; }
.verdict.review { color: #92400e; border-color: #fde68a; }
.verdict.pass { color: #166534; border-color: #bbf7d0; }

/* nav */
.nav { position: sticky; top: 0; z-index: 10; background: var(--surface);
  border-bottom: 1px solid var(--border); box-shadow: var(--shadow); }
.nav .inner { display: flex; gap: 4px; overflow-x: auto; padding: 0 16px; }
.nav a { color: var(--muted); text-decoration: none; padding: 12px 12px; font-size: 14px;
  font-weight: 500; white-space: nowrap; border-bottom: 2px solid transparent;
  transition: color .15s, border-color .15s; }
.nav a:hover, .nav a:focus-visible { color: var(--primary); border-bottom-color: var(--primary); }
a:focus-visible, summary:focus-visible { outline: 2px solid var(--primary-2); outline-offset: 2px;
  border-radius: 4px; }

main { padding: 8px 24px 48px; }
section { scroll-margin-top: 64px; }
h2 { font-size: 20px; margin: 36px 0 14px; display: flex; align-items: center; gap: 10px; }
h2 .num { display: inline-grid; place-items: center; width: 28px; height: 28px; border-radius: 8px;
  background: var(--primary); color: var(--surface); font-size: 14px; }
h3 { font-size: 15px; margin: 0 0 10px; }
.panel { background: var(--surface); border: 1px solid var(--border); border-radius: 14px;
  padding: 20px; box-shadow: var(--shadow); margin-bottom: 16px; }
.sub { color: var(--muted); font-size: 13px; margin: -6px 0 14px; }

/* kpis */
.kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; }
.kpi { background: var(--surface); border: 1px solid var(--border); border-radius: 14px;
  padding: 16px; box-shadow: var(--shadow); border-top: 4px solid var(--border); }
.kpi .n { font-size: 30px; font-weight: 700; line-height: 1.1; }
.kpi .l { color: var(--muted); font-size: 13px; margin-top: 6px; display: flex; gap: 6px;
  align-items: center; }
.kpi.err { border-top-color: var(--err); } .kpi.err .n { color: var(--err); }
.kpi.warn { border-top-color: var(--warn); } .kpi.warn .n { color: var(--warn); }
.kpi.note { border-top-color: var(--note); } .kpi.note .n { color: var(--note); }
.kpi.ok { border-top-color: var(--ok); } .kpi.ok .n { color: var(--ok); }
.kpi.neutral { border-top-color: var(--primary); }

.dist { display: flex; height: 12px; border-radius: 999px; overflow: hidden;
  background: var(--surface-2); border: 1px solid var(--border); margin: 6px 0 10px; }
.dist span { display: block; height: 100%; }
.dist .e { background: var(--err); } .dist .w { background: var(--warn); }
.dist .i { background: var(--note); opacity: .55; }
.legend { display: flex; flex-wrap: wrap; gap: 16px; font-size: 13px; color: var(--muted); }
.legend i { display: inline-block; width: 10px; height: 10px; border-radius: 3px;
  margin-right: 6px; vertical-align: -1px; }

/* facts */
.facts { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 12px; }
.fact { background: var(--surface-2); border: 1px solid var(--border); border-radius: 12px;
  padding: 14px 16px; min-width: 0; }
.fact .k { text-transform: uppercase; letter-spacing: .08em; font-size: 11px; color: var(--muted);
  font-weight: 600; display: flex; align-items: center; gap: 6px; }
.fact .v { font-size: 17px; font-weight: 600; margin-top: 4px; word-break: break-word; }
.fact .v code { font-size: 14.5px; background: none; border: 0; padding: 0; word-break: break-all; }
.fact .d { font-size: 13px; color: var(--muted); margin-top: 2px; word-break: break-word; }
.fact.wide { grid-column: 1 / -1; }

.kv { display: grid; grid-template-columns: 190px 1fr; gap: 8px 18px; margin: 0; font-size: 14px; }
.kv dt { color: var(--muted); }
.kv dd { margin: 0; word-break: break-word; }

/* tables */
.scrollx { overflow-x: auto; border: 1px solid var(--border); border-radius: 10px; }
table { width: 100%; border-collapse: collapse; font-size: 13.5px; }
th, td { text-align: left; padding: 10px 12px; border-bottom: 1px solid var(--border);
  vertical-align: top; }
th { background: var(--surface-2); font-weight: 600; color: var(--muted); font-size: 12px;
  text-transform: uppercase; letter-spacing: .06em; position: sticky; top: 0; }
tbody tr:last-child td { border-bottom: 0; }
tbody tr:hover td { background: var(--surface-2); }
td.num, th.num { text-align: right; }
.props { color: var(--muted); font-size: 12px; margin-top: 4px; }
td.rule code { white-space: nowrap; word-break: normal; }
td.loc { color: var(--muted); font-size: 13px; }
td.loc code { word-break: break-word; }
td.loc .ln { display: block; font-size: 12px; margin-top: 2px; }
.rnote { display: flex; gap: 6px; align-items: flex-start; margin-top: 6px; padding: 6px 8px;
  border-radius: 8px; background: var(--note-bg); border: 1px solid var(--note-bd);
  color: var(--note); font-size: 12.5px; }
.panel.notes { border-left: 4px solid var(--primary); }
.panel.notes h3 { display: flex; gap: 6px; align-items: center; }
.panel.notes ul { margin: 0; padding-left: 18px; } .panel.notes li { margin: 6px 0; }
.panel.notes li div { color: var(--muted); font-size: 13.5px; margin-top: 2px; }
ul.locs { columns: 2 260px; margin: 8px 0 0; padding-left: 18px; font-size: 12.5px; }

/* badges */
.badge { display: inline-flex; align-items: center; gap: 5px; padding: 2px 9px 2px 7px;
  border-radius: 999px; font-size: 11.5px; font-weight: 700; text-transform: uppercase;
  letter-spacing: .04em; border: 1px solid; white-space: nowrap; }
.badge .icon { width: 13px; height: 13px; vertical-align: 0; }
.badge.err { background: var(--err-bg); color: var(--err); border-color: var(--err-bd); }
.badge.warn { background: var(--warn-bg); color: var(--warn); border-color: var(--warn-bd); }
.badge.note { background: var(--note-bg); color: var(--note); border-color: var(--note-bd); }
.badge.ok { background: var(--ok-bg); color: var(--ok); border-color: var(--ok-bd); }
.badge.zero { opacity: .45; }

/* tool cards */
.tool { background: var(--surface); border: 1px solid var(--border); border-radius: 14px;
  box-shadow: var(--shadow); margin-bottom: 14px; overflow: hidden; }
.tool > header { display: flex; justify-content: space-between; align-items: center; gap: 12px;
  flex-wrap: wrap; padding: 14px 18px; border-bottom: 1px solid var(--border);
  background: var(--surface-2); }
.tool > header h3 { margin: 0; font-size: 16px; display: flex; align-items: center; gap: 8px; }
.tool > header .ver { color: var(--muted); font-weight: 400; font-size: 13px; }
.tool .counts { display: flex; gap: 6px; flex-wrap: wrap; align-items: center; }
.tool .body { padding: 14px 18px; }
.tool .body .scrollx { margin-top: 0; }

details { margin-top: 10px; }
summary { cursor: pointer; color: var(--primary); font-weight: 600; font-size: 14px;
  list-style: none; display: inline-flex; align-items: center; gap: 6px; padding: 4px 0; }
summary::-webkit-details-marker { display: none; }
summary::before { content: "▸"; transition: transform .15s; display: inline-block; }
details[open] > summary::before { transform: rotate(90deg); }
.empty { color: var(--muted); padding: 10px 0; display: flex; align-items: center; gap: 8px; }
.callout { display: flex; gap: 10px; align-items: flex-start; border-radius: 10px; padding: 12px 14px;
  border: 1px solid; margin: 12px 0 0; font-size: 14px; }
.callout.warn { background: var(--warn-bg); border-color: var(--warn-bd); color: var(--warn); }
.callout.ok { background: var(--ok-bg); border-color: var(--ok-bd); color: var(--ok); }
.tags code { display: inline-block; margin: 0 4px 4px 0; }

@media (max-width: 640px) {
  .hero h1 { font-size: 24px; } .kv { grid-template-columns: 1fr; } .kv dt { margin-top: 8px; }
  main { padding: 8px 16px 40px; }
}
@media print {
  body { background: #fff; } .nav { display: none; } .hero { padding: 20px; }
  .tool, .panel, .kpi { box-shadow: none; break-inside: avoid; }
  details > *:not(summary) { display: block; }
}
"""

# Inline SVG icons (Lucide-style, stroke = currentColor) — no icon fonts/CDN.
_ICON_PATHS = {
    "shield": '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
    "alert": '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/>'
             '<path d="M12 9v4"/><path d="M12 17h.01"/>',
    "x": '<circle cx="12" cy="12" r="10"/><path d="m15 9-6 6"/><path d="m9 9 6 6"/>',
    "info": '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>',
    "check": '<circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/>',
    "tool": '<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.8-3.8a6 6 0 0 1-7.9 7.9l-6.9'
            ' 6.9a2.1 2.1 0 0 1-3-3l6.9-6.9a6 6 0 0 1 7.9-7.9z"/>',
    "file": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>'
            '<path d="M14 2v6h6"/>',
    "cpu": '<rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/>'
           '<path d="M9 1v3M15 1v3M9 20v3M15 20v3M20 9h3M20 14h3M1 9h3M1 14h3"/>',
    "layers": '<path d="m12 2 10 5-10 5L2 7z"/><path d="m2 17 10 5 10-5"/><path d="m2 12 10 5 10-5"/>',
    "scale": '<path d="m16 16 3-8 3 8c-.9.7-1.9 1-3 1s-2.1-.3-3-1z"/><path d="m2 16 3-8 3 8c-.9.7-1.9'
             ' 1-3 1s-2.1-.3-3-1z"/><path d="M7 21h10"/><path d="M12 3v18"/><path d="M3 7h18"/>',
    "hash": '<path d="M4 9h16M4 15h16M10 3 8 21M16 3l-2 18"/>',
    "eye": '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
}


def _icon(name: str) -> str:
    return ('<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
            f'{_ICON_PATHS[name]}</svg>')


_LEVEL = {  # level → (css class, icon, label)
    "error": ("err", "x", "error"),
    "warning": ("warn", "alert", "warning"),
    "note": ("note", "info", "info"),
    "none": ("ok", "check", "pass"),
}
_ORDER = {"error": 0, "warning": 1, "note": 2, "none": 3}


def _badge(level: str, count: int | None = None) -> str:
    cls, icon, label = _LEVEL.get(level, _LEVEL["note"])
    text = f"{count} {label}" if count is not None else label
    zero = " zero" if count == 0 else ""
    return f'<span class="badge {cls}{zero}">{_icon(icon)}{html.escape(text)}</span>'


def _esc(x: Any) -> str:
    if x is None:
        return ""
    return html.escape(str(x))


def _uri(r: dict) -> str:
    locs = r.get("locations") or []
    return locs[0].get("physicalLocation", {}).get("artifactLocation", {}).get("uri", "") \
        if locs else ""


def _found_in(r: dict) -> str:
    """'path : line N' — where in the model the finding was detected."""
    uri = _uri(r)
    if not uri:
        return ""
    locs = r.get("locations") or []
    line = locs[0].get("physicalLocation", {}).get("region", {}).get("startLine")
    path = uri if not uri.startswith("/") else Path(uri).name
    return f"<code>{_esc(path)}</code>" + (f" <span class=ln>line {line}</span>" if line else "")


GROUP_MIN = 4  # this many same-rule/same-level findings collapse into one row


def _rows(results: list[dict]) -> str:
    groups: dict[tuple[str, str], list[dict]] = {}
    for r in results:
        groups.setdefault((r.get("level", "note"), r.get("ruleId", "")), []).append(r)
    rows = []
    for (level, rule), items in groups.items():
        batch = [items] if len(items) >= GROUP_MIN else [[r] for r in items]
        for grp in batch:
            r = grp[0]
            msg = _esc(r.get("message", {}).get("text", ""))
            props = "; ".join(
                f"{_esc(k)}={_esc(v)}" for k, v in (r.get("properties") or {}).items()
                if not isinstance(v, (list, dict)) and v is not None and k != "reviewerNote"
            )
            note = (r.get("properties") or {}).get("reviewerNote")
            if note:
                msg += f'<div class="rnote">{_icon("info")}<span>{_esc(note)}</span></div>' 
            loc = _found_in(r)
            if len(grp) > 1:
                files = "".join(f"<li>{_found_in(x)}</li>" for x in grp if _uri(x))
                msg = (f"<strong>{len(grp)} similar findings.</strong> e.g. {msg}"
                       f"<details><summary>Show {len(grp)} locations</summary>"
                       f"<ul class=locs>{files}</ul></details>")
                loc = f"{len(grp)} files"
            rows.append(
                f"<tr><td>{_badge(level)}</td><td class=rule><code>{_esc(rule)}</code></td>"
                f"<td>{msg}{f'<div class=props>{props}</div>' if props and len(grp) == 1 else ''}"
                f"</td><td class=loc>{loc}</td></tr>"
            )
    return (
        '<div class="scrollx"><table><thead><tr><th>Level</th><th>Rule</th><th>Finding</th>'
        '<th>Found in</th></tr></thead><tbody>' + "".join(rows) + "</tbody></table></div>"
    )


# Tools whose warnings are mostly coverage/noise: fold warnings too, keep only errors open.
COLLAPSE_WARNINGS = {"modelaudit"}


def _render_results(results: list[dict], *, collapse_warnings: bool = False) -> str:
    """Errors always shown; informational (and optionally warning) results folded away."""
    ignored = sum(1 for r in results if is_suppressed(r))
    results = [r for r in results if not is_suppressed(r)]
    note = (f'<p class="sub" style="margin:0 0 8px">{ignored} finding(s) in ignored files '
            "(e.g. README.md) excluded by scan policy.</p>") if ignored else ""
    if not results:
        return note + f'<div class="empty">{_icon("check")} No findings recorded.</div>'
    by_level: dict[str, list[dict]] = {"error": [], "warning": [], "note": []}
    for r in results:
        by_level.get(r.get("level", "note"), by_level["note"]).append(r)
    errors, warns, notes = by_level["error"], by_level["warning"], by_level["note"]

    shown = errors + ([] if collapse_warnings else warns)
    out_prefix = note
    folded = [("warning", warns)] if collapse_warnings else []
    folded.append(("informational", notes))
    out = _rows(shown) if shown else ""
    for label, items in folded:
        if not items:
            continue
        if not out and len(folded) == 1:  # nothing above it: no point hiding the only table
            out = _rows(items)
            continue
        out += (f"<details><summary>Show {len(items)} {label}"
                f"{'s' if label == 'warning' and len(items) != 1 else ''}</summary>"
                f"{_rows(items)}</details>")
    return out_prefix + out


def _scanned_files(run: dict) -> str:
    """Which model files a code scanner evaluated (semgrep step 12)."""
    files = (run.get("properties") or {}).get("scannedFiles") or []
    if not files:
        return ""
    items = "".join(f"<li><code>{_esc(f)}</code></li>" for f in files)
    return (f'<p class="sub" style="margin:0 0 8px">Scanned {len(files)} model code file(s) '
            f"shipped in the repo (not the scanner's own code).</p>"
            f"<details><summary>Show scanned files</summary><ul class=locs>{items}</ul></details>")


def _notes_panel(notes: list[dict]) -> str:
    if not notes:
        return ""
    items = "".join(
        f'<li><strong>{_esc(n["title"])}</strong>'
        f'{f" <code>{_esc(n["applies_to"])}</code>" if n["applies_to"] else ""}'
        f'<div>{_esc(n["note"])}</div></li>' for n in notes
    )
    return (f'<div class="panel notes" style="margin-top:16px"><h3>{_icon("info")} Reviewer notes'
            f'</h3><ul>{items}</ul></div>')


def _dependency_gap(scan_dir: Path) -> str:
    """Explain an empty SBOM / skipped pip-audit, so '0 findings' doesn't read as 'not run'."""
    sbom = load_json(scan_dir / "raw" / "08_sbom.cdx.json")
    pa = load_json(scan_dir / "raw" / "06_pip_audit.json")
    if not isinstance(sbom, dict) or "bomFormat" not in sbom or sbom.get("components"):
        return ""
    imports = (pa.get("undeclared_imports") if isinstance(pa, dict) else None) or {}
    extra = (f" Its code imports {len(imports)} third-party package(s) without declaring them: "
             f"{', '.join(f'<code>{_esc(m)}</code>' for m in imports)} — see pip-audit below."
             if imports else "")
    return (f'<div class="callout warn">{_icon("alert")}<div><strong>No dependency manifest '
            "shipped.</strong> The repo has no requirements.txt / pyproject.toml / setup.py / "
            "lockfile, so syft catalogued 0 packages and grype and pip-audit had nothing to "
            f"check for CVEs.{extra}</div></div>")


def _sbom_kpi(scan_dir: Path) -> str:
    sbom = sbom_summary(scan_dir)
    if sbom is None:
        return ""
    top = ", ".join(f"{_esc(k)} {v}" for k, v in list(sbom["ecosystems"].items())[:3])
    return (f'<div class="kpi {"neutral" if sbom["components"] else "warn"}"><div class="n">'
            f'{sbom["components"]}</div><div class="l">{_icon("tool")}SBOM packages'
            f'{f" ({top})" if top else ""}</div></div>\n')


def _fact(icon: str, key: str, value: str, detail: str = "", wide: bool = False) -> str:
    return (f'<div class="fact{" wide" if wide else ""}"><div class="k">{_icon(icon)}{key}</div>'
            f'<div class="v">{value}</div>{f"<div class=d>{detail}</div>" if detail else ""}</div>')


def build_html(scan_dir: Path, sarif: dict) -> str:
    meta = load_json(scan_dir / "raw" / "01_metadata.json") or {}
    sha_inv = load_json(scan_dir / "raw" / "02_sha256.json") or {"files": []}
    fmt = load_json(scan_dir / "raw" / "03_format_inventory.json") or {}
    licenses = load_json(scan_dir / "raw" / "07_licenses.json") or {}
    licenses = licenses if isinstance(licenses, dict) else {}

    level_counts: Counter = Counter()
    tool_counts: dict[str, Counter] = {}
    suppressed: Counter = Counter()  # per tool, policy-ignored (e.g. README.md)
    for run in sarif.get("runs", []):
        name = run.get("tool", {}).get("driver", {}).get("name", "unknown")
        tool_counts.setdefault(name, Counter())
        for res in run.get("results", []):
            if is_suppressed(res):
                suppressed[name] += 1
                continue
            lvl = res.get("level", "note")
            level_counts[lvl] += 1
            tool_counts[name][lvl] += 1
    errors, warnings = level_counts.get("error", 0), level_counts.get("warning", 0)
    notes = level_counts.get("note", 0)

    ms = model_summary(meta, licenses or None)
    model_id = ms["name"] or "UNKNOWN"
    sha = ms["version"]["commit_sha"] or "unknown"
    generated = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    arch, moe, ctxw, lic = (ms["architecture"], ms["architecture"]["moe"], ms["context_window"],
                            ms["license"])
    inputs = ", ".join(ms["modality"]["inputs"]) or "—"
    outputs = ", ".join(ms["modality"]["outputs"] or []) or "—"
    ctx_txt = f"{ctxw['tokens']:,}" if ctxw["tokens"] else "—"

    if errors:
        verdict = ("fail", "x", "FAIL", f"{errors} error-level finding(s)")
    elif warnings:
        verdict = ("review", "alert", "REVIEW", f"{warnings} warning(s) need a look")
    else:
        verdict = ("pass", "check", "PASS", "no errors or warnings")

    parts: list[str] = [f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light">
<title>Model Scan Report — {_esc(model_id)}</title>
<style>{CSS}</style></head><body>
<div class="hero"><div class="inner">
  <div class="top">
    <div>
      <div class="eyebrow">{_icon("shield")} Open-Source LLM Security Scan</div>
      <h1>{_esc(model_id)}</h1>
      <div class="meta">
        <span>Provider <strong>{_esc(ms["provider"] or "—")}</strong></span>
        <span>Commit <code>{_esc(sha[:12])}</code></span>
        <span>Revision <code>{_esc(ms["version"]["revision"] or "—")}</code></span>
        <span>Scanned {_esc(generated)}</span>
      </div>
    </div>
    <div class="verdict {verdict[0]}" role="status">{_icon(verdict[1])}
      <div>{verdict[2]}<small>{_esc(verdict[3])}</small></div></div>
  </div>
  <div class="chips">
    <span class="chip"><b>Params</b>{_esc(ms["parameters"]["human"] or "—")}</span>
    <span class="chip"><b>Context</b>{ctx_txt} tokens</span>
    <span class="chip"><b>Modality</b>{_esc(inputs)} → {_esc(outputs)}</span>
    <span class="chip"><b>License</b>{_esc(lic["declared"] or "not declared")}</span>
  </div>
</div></div>
<nav class="nav" aria-label="Report sections"><div class="inner">
  <a href="#summary">Summary</a><a href="#model">Model</a><a href="#integrity">Integrity</a>
  <a href="#findings">Findings</a><a href="#licenses">Licenses</a>
</div></nav>
<main>
"""]

    # 1. Executive summary
    total = errors + warnings + notes
    pct = (lambda n: f"{100 * n / total:.2f}%") if total else (lambda n: "0%")
    tool_rows = "".join(
        f"<tr><td><strong>{_esc(name)}</strong></td>"
        f"<td class=num>{_badge('error', c.get('error', 0))}</td>"
        f"<td class=num>{_badge('warning', c.get('warning', 0))}</td>"
        f"<td class=num>{_badge('note', c.get('note', 0))}</td></tr>"
        for name, c in tool_counts.items()
    )
    unsafe = fmt.get("counts", {}).get("unsafe_format", 0)
    parts.append(f"""
<section id="summary"><h2><span class="num">1</span>Executive Summary</h2>
<div class="kpis">
  <div class="kpi err"><div class="n">{errors}</div><div class="l">{_icon("x")}Errors</div></div>
  <div class="kpi warn"><div class="n">{warnings}</div><div class="l">{_icon("alert")}Warnings</div></div>
  <div class="kpi note"><div class="n">{notes}</div><div class="l">{_icon("info")}Informational</div></div>
  <div class="kpi neutral"><div class="n">{len(sarif.get("runs", []))}</div><div class="l">{_icon("tool")}Scan tools run</div></div>
  <div class="kpi neutral"><div class="n">{len(sha_inv.get("files", []))}</div><div class="l">{_icon("hash")}Weight files hashed</div></div>
  <div class="kpi {"err" if unsafe else "ok"}"><div class="n">{unsafe}</div><div class="l">{_icon("file")}Unsafe-format files</div></div>
{_sbom_kpi(scan_dir)}</div>
{_notes_panel(load_notes(scan_dir))}<div class="panel" style="margin-top:16px">
  <h3>Finding distribution</h3>
  <div class="dist" role="img" aria-label="{errors} errors, {warnings} warnings, {notes} informational">
    <span class="e" style="width:{pct(errors)}"></span><span class="w" style="width:{pct(warnings)}"></span><span class="i" style="width:{pct(notes)}"></span>
  </div>
  <div class="legend"><span><i style="background:var(--err)"></i>{errors} errors</span>
    <span><i style="background:var(--warn)"></i>{warnings} warnings</span>
    <span><i style="background:var(--note);opacity:.55"></i>{notes} informational</span>
    {f"<span>{sum(suppressed.values())} ignored by policy (README.md)</span>" if suppressed else ""}</div>
  {f'''<div class="scrollx" style="margin-top:16px"><table><thead><tr><th>Tool</th>
  <th class=num>Errors</th><th class=num>Warnings</th><th class=num>Info</th></tr></thead>
  <tbody>{tool_rows}</tbody></table></div>''' if tool_rows else ""}
</div></section>
""")

    # 2. Model identity
    moe_txt = f"MoE · {moe['experts']} experts, {moe['active_per_token']} active/token" if moe else ""
    dtypes = ", ".join(f"{k} {v:,}" for k, v in (ms["parameters"]["by_dtype"] or {}).items())
    total_params = ms["parameters"]["total"]
    parts.append(f"""
<section id="model"><h2><span class="num">2</span>Model Identity &amp; Provenance</h2>
<div class="facts">
  {_fact("cpu", "Architecture", f"<code>{_esc(arch['class'] or '—')}</code>",
         f"{_esc(arch['model_type'] or '')}{' · ' + _esc(moe_txt) if moe_txt else ''}")}
  {_fact("layers", "Parameters", _esc(ms["parameters"]["human"] or "—"),
         _esc(f"{total_params:,} · {dtypes}" if total_params else dtypes))}
  {_fact("file", "Context window", f"{ctx_txt} tokens" if ctxw["tokens"] else "—",
         f"sliding window {ctxw['sliding_window']:,}" if ctxw["sliding_window"] else "")}
  {_fact("eye", "Modality", f"{_esc(inputs)} → {_esc(outputs)}",
         f"<code>{_esc(ms['modality']['pipeline_tag'] or '—')}</code>")}
  {_fact("scale", "License", _esc(lic["declared"] or "not declared"),
         f"shipped: {_esc(', '.join(lic['files']) or 'none')}")}
  {_fact("shield", "Provider", _esc(ms["provider"] or "—"),
         f"base model: {_esc(ms['base_model'])}" if ms["base_model"] else "")}
  {_fact("hash", "Version", f"<code>{_esc(sha)}</code>",
         f"revision {_esc(ms['version']['revision'] or '—')} · updated "
         f"{_esc(ms['version']['last_modified'] or '—')}", wide=True)}
</div>
<div class="panel" style="margin-top:16px"><h3>Source</h3>
<dl class="kv">
  <dt>Repository</dt><dd><code>{_esc(model_id)}</code></dd>
  <dt>License link</dt><dd>{_esc(lic["link"] or "—")}</dd>
  <dt>Library</dt><dd>{_esc(meta.get("library_name") or "—")}</dd>
  <dt>Downloads</dt><dd>{_esc(f"{meta['downloads']:,}" if meta.get("downloads") else "—")}</dd>
  <dt>Repo file count</dt><dd>{len(meta.get("siblings", []))}</dd>
  <dt>Gated</dt><dd>{_esc(meta.get("gated") if meta.get("gated") is not None else "—")}</dd>
</dl>
<details><summary>Show tags ({len(meta.get("tags", []))})</summary>
<p class="tags">{"".join(f"<code>{_esc(t)}</code>" for t in meta.get("tags", [])[:80])}</p>
</details></div></section>
""")

    # 3. Integrity
    fmt_counts = fmt.get("counts", {})
    sha_files = sha_inv.get("files", [])
    sha_rows = "".join(
        f"<tr><td><code>{_esc(f['path'])}</code></td><td class=num>{f['size']:,}</td>"
        f"<td><code style='font-size:11px'>{_esc(f['sha256'])}</code></td></tr>"
        for f in sha_files[:50]
    )
    more = (f"<p class='empty'>… and {len(sha_files) - 50} more (see <code>02_sha256.json</code>)."
            "</p>") if len(sha_files) > 50 else ""
    callout = (
        f'<div class="callout warn">{_icon("alert")}<div><strong>Unsafe-format weight files '
        "detected.</strong> These formats permit arbitrary code execution at load time — check "
        "the modelaudit and picklescan results in Findings before approving.</div></div>"
        if unsafe else
        f'<div class="callout ok">{_icon("check")}<div>All weight files use non-executable formats.'
        "</div></div>"
    )
    parts.append(f"""
<section id="integrity"><h2><span class="num">3</span>Integrity &amp; Format Inventory</h2>
<div class="kpis">
  <div class="kpi ok"><div class="n">{fmt_counts.get("safetensors", 0)}</div><div class="l">{_icon("check")}safetensors (preferred)</div></div>
  <div class="kpi {"err" if unsafe else "ok"}"><div class="n">{unsafe}</div><div class="l">{_icon("alert")}Unsafe-format files</div></div>
  <div class="kpi neutral"><div class="n">{fmt_counts.get("other", 0)}</div><div class="l">{_icon("file")}Other formats</div></div>
</div>
{callout}
<div class="panel" style="margin-top:16px"><details><summary>SHA-256 inventory ({len(sha_files)} files)</summary>
<div class="scrollx" style="margin-top:10px"><table>
<thead><tr><th>Path</th><th class=num>Size (bytes)</th><th>SHA-256</th></tr></thead>
<tbody>{sha_rows or "<tr><td colspan=3 class=empty>No files hashed.</td></tr>"}</tbody></table></div>
{more}</details></div></section>
""")

    # 4. Findings by tool
    parts.append(
        '<section id="findings"><h2><span class="num">4</span>Findings by Tool</h2>'
        '<p class="sub">os-llm-review, modelaudit, picklescan, pip-audit, os-llm-model-provenance, '
        "grype, gitleaks — errors and warnings first; informational results are collapsed.</p>"
        + _dependency_gap(scan_dir)
    )
    for run in sarif.get("runs", []):
        driver = run.get("tool", {}).get("driver", {})
        name = driver.get("name", "unknown")
        version = driver.get("version", "")
        info_uri = driver.get("informationUri", "")
        c = tool_counts.get(name, Counter())
        docs = (f' <a href="{_esc(info_uri)}" target="_blank" rel="noopener">docs</a>'
                if info_uri.startswith("http") and "internal" not in info_uri else "")
        parts.append(f"""
<article class="tool">
  <header><h3>{_icon("tool")}{_esc(name)}<span class="ver">{f"v{_esc(version)}" if version and version != "unknown" else ""}{docs}</span></h3>
    <div class="counts">{_badge("error", c.get("error", 0))}{_badge("warning", c.get("warning", 0))}{_badge("note", c.get("note", 0))}</div>
  </header>
  <div class="body">{_scanned_files(run)}{_render_results(run.get("results", []), collapse_warnings=name in COLLAPSE_WARNINGS)}</div>
</article>
""")
    parts.append("</section>")

    # 5. License inventory
    declared = licenses.get("declared") or {}
    lic_files = licenses.get("files") or []
    if lic_files:
        lic_rows = "".join(
            f"<tr><td><code>{_esc(f.get('path'))}</code></td><td>{_esc(f.get('first_line'))}</td>"
            f"<td><code>{_esc((f.get('sha256') or '')[:12])}…</code></td></tr>"
            for f in lic_files
        )
        lic_body = (
            '<div class="scrollx" style="margin-top:14px"><table><thead><tr><th>File</th>'
            f"<th>First line</th><th>SHA-256</th></tr></thead><tbody>{lic_rows}</tbody></table></div>"
            '<p class="sub" style="margin:10px 0 0">Attach these files to the Legal review request; '
            "do not rely on the summary line.</p>"
        )
    else:
        lic_body = (f'<div class="callout warn">{_icon("alert")}<div>Model ships no LICENSE / '
                    "NOTICE / COPYING file — only the model-card declaration above is available."
                    "</div></div>")
    parts.append(f"""
<section id="licenses"><h2><span class="num">5</span>Model License Inventory</h2>
<div class="panel">
<dl class="kv">
  <dt>Declared (model card)</dt><dd><strong>{_esc(declared.get("license") or "not declared")}</strong></dd>
  <dt>License name</dt><dd>{_esc(declared.get("license_name") or "—")}</dd>
  <dt>License link</dt><dd>{_esc(declared.get("license_link") or "—")}</dd>
</dl>
{lic_body}
</div></section>
</main></body></html>""")

    return "".join(parts)
