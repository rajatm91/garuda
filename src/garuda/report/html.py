"""HTML report renderer — ports legacy to_html.py."""
from __future__ import annotations

import html
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..util.io import load_json

# ---------------------------------------------------------------------------
# CSS — embedded, no external deps
# ---------------------------------------------------------------------------
CSS = """
:root {
  --bg: #ffffff; --fg: #1a1a1a; --muted: #6b7280; --border: #e5e7eb;
  --card: #f9fafb; --accent: #1f3864;
  --err-bg: #fef2f2; --err-fg: #991b1b; --err-bd: #fecaca;
  --warn-bg: #fffbeb; --warn-fg: #92400e; --warn-bd: #fde68a;
  --note-bg: #eff6ff; --note-fg: #1e40af; --note-bd: #bfdbfe;
  --ok-bg: #f0fdf4;   --ok-fg: #166534;   --ok-bd: #bbf7d0;
}
* { box-sizing: border-box; }
body { font: 14px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
       color: var(--fg); background: var(--bg); margin: 0; padding: 0; }
.wrap { max-width: 1100px; margin: 0 auto; padding: 32px 24px; }
header { border-bottom: 1px solid var(--border); padding-bottom: 18px; margin-bottom: 24px; }
header h1 { margin: 0 0 6px; font-size: 24px; color: var(--accent); }
header .sub { color: var(--muted); font-size: 13px; }
h2 { font-size: 18px; margin: 32px 0 12px; color: var(--accent); border-bottom: 1px solid var(--border); padding-bottom: 6px; }
h3 { font-size: 15px; margin: 18px 0 8px; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin: 16px 0; }
.card { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 14px; }
.card .n { font-size: 26px; font-weight: 600; }
.card .l { font-size: 12px; color: var(--muted); margin-top: 4px; }
.kv { display: grid; grid-template-columns: 180px 1fr; gap: 4px 16px; margin: 8px 0; font-size: 13px; }
.kv dt { color: var(--muted); }
.kv dd { margin: 0; word-break: break-all; }
table { width: 100%; border-collapse: collapse; font-size: 13px; margin: 8px 0; }
th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--border); vertical-align: top; }
th { background: var(--card); font-weight: 600; }
tr:hover td { background: #fafafa; }
code { font-family: ui-monospace, SF Mono, Menlo, monospace; font-size: 12px;
       background: var(--card); padding: 1px 5px; border-radius: 3px; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 11px;
         font-weight: 600; text-transform: uppercase; letter-spacing: 0.3px; }
.badge.err  { background: var(--err-bg);  color: var(--err-fg);  border: 1px solid var(--err-bd); }
.badge.warn { background: var(--warn-bg); color: var(--warn-fg); border: 1px solid var(--warn-bd); }
.badge.note { background: var(--note-bg); color: var(--note-fg); border: 1px solid var(--note-bd); }
.badge.ok   { background: var(--ok-bg);   color: var(--ok-fg);   border: 1px solid var(--ok-bd); }
.tool { background: var(--card); border: 1px solid var(--border); border-radius: 8px;
        padding: 16px; margin: 12px 0; }
.tool h3 { margin-top: 0; display: flex; justify-content: space-between; align-items: center; }
.tool .meta { color: var(--muted); font-size: 12px; font-weight: normal; }
.empty { color: var(--muted); font-style: italic; padding: 8px 0; }
footer { margin-top: 40px; padding-top: 16px; border-top: 1px solid var(--border);
         color: var(--muted); font-size: 12px; }
.toc { background: var(--card); border: 1px solid var(--border); border-radius: 8px;
       padding: 12px 18px; margin-bottom: 24px; }
.toc ol { margin: 4px 0; padding-left: 20px; }
.toc a { color: var(--accent); text-decoration: none; }
.toc a:hover { text-decoration: underline; }
details { margin: 6px 0; }
summary { cursor: pointer; color: var(--accent); font-weight: 500; }
.scrollx { overflow-x: auto; }
@media print { .wrap { max-width: none; } .tool { break-inside: avoid; } }
"""


def _badge(level: str) -> str:
    cls = {"error": "err", "warning": "warn", "note": "note", "none": "ok"}.get(level, "note")
    return f'<span class="badge {cls}">{html.escape(level)}</span>'


def _esc(x: Any) -> str:
    if x is None:
        return ""
    return html.escape(str(x))


def _render_results_table(results: list[dict]) -> str:
    if not results:
        return '<div class="empty">No findings recorded.</div>'
    rows = []
    for r in results:
        lvl = r.get("level", "note")
        rule = _esc(r.get("ruleId", ""))
        msg = _esc(r.get("message", {}).get("text", ""))
        loc = ""
        locs = r.get("locations") or []
        if locs:
            uri = locs[0].get("physicalLocation", {}).get("artifactLocation", {}).get("uri", "")
            loc = f"<code>{_esc(uri)}</code>"
        props = r.get("properties") or {}
        prop_html = ""
        if props:
            inner = "; ".join(
                f"{_esc(k)}={_esc(v)}"
                for k, v in props.items()
                if not isinstance(v, (list, dict)) and v is not None
            )
            if inner:
                prop_html = (
                    f'<div style="color:var(--muted);font-size:12px;margin-top:4px;">{inner}</div>'
                )
        rows.append(
            f"<tr><td>{_badge(lvl)}</td><td><code>{rule}</code></td>"
            f"<td>{msg}{prop_html}</td><td>{loc}</td></tr>"
        )
    return (
        '<div class="scrollx"><table>'
        '<thead><tr><th>Level</th><th>Rule</th><th>Finding</th><th>Location</th></tr></thead>'
        '<tbody>' + "".join(rows) + '</tbody></table></div>'
    )


def build_html(scan_dir: Path, sarif: dict) -> str:
    meta = load_json(scan_dir / "raw" / "01_metadata.json") or {}
    sha_inv = load_json(scan_dir / "raw" / "02_sha256.json") or {"files": []}
    fmt = load_json(scan_dir / "raw" / "03_format_inventory.json") or {}
    licenses = load_json(scan_dir / "raw" / "07_pip_licenses.json") or []

    # Aggregate counts
    level_counts: Counter = Counter()
    tool_counts: dict[str, Counter] = {}
    for run in sarif.get("runs", []):
        name = run.get("tool", {}).get("driver", {}).get("name", "unknown")
        tool_counts.setdefault(name, Counter())
        for res in run.get("results", []):
            lvl = res.get("level", "note")
            level_counts[lvl] += 1
            tool_counts[name][lvl] += 1

    # Header info
    model_id = meta.get("id") or "UNKNOWN"
    sha = meta.get("sha") or "unknown"
    license_label = meta.get("license") or "not declared"
    generated = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

    # Sections
    parts: list[str] = []
    parts.append(f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>OS LLM Scan Report — {_esc(model_id)}</title>
<style>{CSS}</style></head><body><div class="wrap">
<header>
  <h1>Open-Source LLM Scan Report</h1>
  <div class="sub">Model: <strong>{_esc(model_id)}</strong> &middot; Commit SHA: <code>{_esc(sha[:12])}…</code> &middot; Generated {_esc(generated)}</div>
</header>

<div class="toc"><strong>Contents</strong>
  <ol>
    <li><a href="#summary">Executive summary</a></li>
    <li><a href="#model">Model identity &amp; provenance</a></li>
    <li><a href="#integrity">Integrity &amp; format inventory</a></li>
    <li><a href="#findings">Findings by tool</a></li>
    <li><a href="#licenses">License inventory</a></li>
    <li><a href="#attestation">Attestation</a></li>
  </ol>
</div>
""")

    # 1. Summary
    parts.append(f"""
<h2 id="summary">1. Executive Summary</h2>
<div class="grid">
  <div class="card"><div class="n" style="color:var(--err-fg)">{level_counts.get('error',0)}</div><div class="l">Error-level findings</div></div>
  <div class="card"><div class="n" style="color:var(--warn-fg)">{level_counts.get('warning',0)}</div><div class="l">Warning-level findings</div></div>
  <div class="card"><div class="n" style="color:var(--note-fg)">{level_counts.get('note',0)}</div><div class="l">Informational</div></div>
  <div class="card"><div class="n">{len(sarif.get('runs', []))}</div><div class="l">Scan tools run</div></div>
  <div class="card"><div class="n">{len(sha_inv.get('files', []))}</div><div class="l">Weight files hashed</div></div>
  <div class="card"><div class="n">{fmt.get('counts',{}).get('unsafe_format', 0)}</div><div class="l">Unsafe-format weight files</div></div>
</div>
<p>This report combines outputs from automated security tooling into a single human-readable
summary alongside a machine-readable SARIF 2.1.0 file (<code>scan_results.sarif</code>) suitable
for ingestion by GitHub Advanced Security, Azure DevOps, SonarQube, DefectDojo, or similar
platforms. <strong>Findings here do not constitute approval.</strong> They are evidence for
review by InfoSec and the Model Review &amp; Management Committee.</p>
""")

    # 2. Model identity
    sib_count = len(meta.get("siblings", []))
    parts.append(f"""
<h2 id="model">2. Model Identity &amp; Provenance</h2>
<dl class="kv">
  <dt>Repository</dt><dd><code>{_esc(model_id)}</code></dd>
  <dt>Resolved commit SHA</dt><dd><code>{_esc(sha)}</code></dd>
  <dt>Revision requested</dt><dd><code>{_esc(meta.get('revision_requested', 'main'))}</code></dd>
  <dt>License (declared)</dt><dd>{_esc(license_label)}</dd>
  <dt>License link</dt><dd>{_esc(meta.get('license_link') or '—')}</dd>
  <dt>Pipeline tag</dt><dd>{_esc(meta.get('pipeline_tag') or '—')}</dd>
  <dt>Library</dt><dd>{_esc(meta.get('library_name') or '—')}</dd>
  <dt>Last modified</dt><dd>{_esc(meta.get('last_modified') or '—')}</dd>
  <dt>Downloads</dt><dd>{_esc(meta.get('downloads') or '—')}</dd>
  <dt>File count</dt><dd>{sib_count}</dd>
</dl>
<details><summary>Show tags ({len(meta.get('tags', []))})</summary>
<p>{', '.join(f'<code>{_esc(t)}</code>' for t in meta.get('tags', [])[:60])}</p>
</details>
""")

    # 3. Integrity
    fmt_counts = fmt.get("counts", {})
    unsafe_count = fmt_counts.get("unsafe_format", 0)
    unsafe_warn = ""
    if unsafe_count > 0:
        unsafe_warn = (
            '<p><strong>Unsafe-format weight files detected.</strong> '
            'These formats permit arbitrary code execution at load time. '
            'Verify the modelaudit and second-opinion scan results in Section 4 before approving.</p>'
        )

    sha_rows = "".join(
        f"<tr><td><code>{_esc(f['path'])}</code></td><td>{f['size']:,}</td>"
        f"<td><code style='font-size:11px'>{_esc(f['sha256'])}</code></td></tr>"
        for f in sha_inv.get("files", [])[:50]
    )
    sha_more = ""
    if len(sha_inv.get("files", [])) > 50:
        sha_more = (
            f"<p class='empty'>… and {len(sha_inv['files']) - 50} more "
            "(see <code>02_sha256.json</code>).</p>"
        )

    parts.append(f"""
<h2 id="integrity">3. Integrity &amp; Format Inventory</h2>
<div class="grid">
  <div class="card"><div class="n" style="color:var(--ok-fg)">{fmt_counts.get('safetensors',0)}</div><div class="l">safetensors (preferred)</div></div>
  <div class="card"><div class="n" style="color:var(--warn-fg)">{unsafe_count}</div><div class="l">Unsafe-format weight files</div></div>
  <div class="card"><div class="n">{fmt_counts.get('other',0)}</div><div class="l">Other formats</div></div>
</div>
{unsafe_warn}
<details><summary>SHA-256 inventory (first 50 files)</summary>
<div class="scrollx"><table>
<thead><tr><th>Path</th><th>Size (bytes)</th><th>SHA-256</th></tr></thead>
<tbody>{sha_rows or '<tr><td colspan=3 class=empty>No files hashed.</td></tr>'}</tbody></table></div>
{sha_more}
</details>
""")

    # 4. Findings by tool
    parts.append(
        '<h2 id="findings">4. Findings by Tool</h2>'
        '<p class="empty">Per-tool findings below (os-llm-review, modelaudit, second-opinion scan, '
        'pip-audit, grype, gitleaks).</p>'
    )
    for run in sarif.get("runs", []):
        driver = run.get("tool", {}).get("driver", {})
        name = driver.get("name", "unknown")
        version = driver.get("version", "")
        info_uri = driver.get("informationUri", "")
        counts = tool_counts.get(name, Counter())
        summary_line = (
            f"{counts.get('error',0)} error &middot; "
            f"{counts.get('warning',0)} warning &middot; "
            f"{counts.get('note',0)} note"
        )
        link_html = (
            f' &middot; <a href="{_esc(info_uri)}" target="_blank" rel="noopener">docs</a>'
            if info_uri else ""
        )
        parts.append(f"""
<div class="tool">
  <h3>{_esc(name)} <span class="meta">v{_esc(version)} &middot; {summary_line}{link_html}</span></h3>
  {_render_results_table(run.get('results', []))}
</div>
""")

    # 5. License inventory (Python deps)
    parts.append('<h2 id="licenses">5. Python Dependency License Inventory</h2>')
    if isinstance(licenses, list) and licenses:
        risky = [
            l for l in licenses
            if str(l.get("License", "")).upper()
            in ("GPL", "AGPL", "GPLV2", "GPLV3", "GPL-2.0", "GPL-3.0", "AGPL-3.0", "UNKNOWN")
        ]
        if risky:
            parts.append(
                f'<p><strong>{len(risky)} package(s) with copyleft or unknown licenses</strong> '
                f"— review with Legal before redistribution.</p>"
            )
        lic_rows = "".join(
            f"<tr><td>{_esc(l.get('Name'))}</td><td>{_esc(l.get('Version'))}</td>"
            f"<td>{_esc(l.get('License'))}</td></tr>"
            for l in licenses[:200]
        )
        parts.append(f"""
<details><summary>Show {len(licenses)} packages</summary>
<div class="scrollx"><table>
<thead><tr><th>Package</th><th>Version</th><th>License</th></tr></thead>
<tbody>{lic_rows}</tbody></table></div>
</details>
""")
    else:
        parts.append('<div class="empty">No license inventory produced (pip-licenses unavailable).</div>')

    # 6. Attestation
    parts.append(f"""
<h2 id="attestation">6. Attestation</h2>
<p>I confirm that the scans documented in this report were executed against the model at the
pinned commit SHA shown in Section 2, and that the SARIF file <code>scan_results.sarif</code>
contains the complete machine-readable record of findings.</p>
<dl class="kv">
  <dt>Engineer (name)</dt><dd>__________________________</dd>
  <dt>Team / Cost-centre</dt><dd>__________________________</dd>
  <dt>Date</dt><dd>__________________________</dd>
  <dt>Signature</dt><dd>__________________________</dd>
</dl>

<footer>
  Generated by os-llm-review tooling. Raw outputs preserved in
  <code>{_esc(str(scan_dir / 'raw'))}</code>. SARIF log:
  <code>{_esc(str(scan_dir / 'reports' / 'scan_results.sarif'))}</code>.
</footer>
</div></body></html>""")

    return "".join(parts)
