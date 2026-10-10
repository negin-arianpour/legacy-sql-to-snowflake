"""Run the pytest suite and turn its results into an accuracy report.

    python -m reports.make_report

Writes reports/conversion_report.md and reports/conversion_report.html.
"""

import html
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from converter.common import CONVERTERS, REPORTS_DIR, load_queries  # noqa: E402
from harness.compare import CATEGORIES, INCONCLUSIVE  # noqa: E402
from harness.snowflake_runner import using_real_snowflake  # noqa: E402

CONVERTER_LABELS = {"llm": "LLM (Claude)", "baseline": "Rule based baseline (sqlglot)"}

# Source features known to change meaning or break when moved to Snowflake.
DIALECT_TRAPS = [
    ("tsql", r"\bTOP\s+\d+", "TOP n row limit"),
    ("tsql", r"\w\s*\+\s*'|'\s*\+\s*\w", "+ string concatenation"),
    ("tsql", r"\bISNULL\s*\(", "ISNULL"),
    ("tsql", r"\bCONVERT\s*\(\s*VARCHAR", "CONVERT with style code"),
    ("tsql", r"=\s*'[^']*'|<>\s*'[^']*'", "string comparison (case insensitive collation)"),
    ("tsql", r"SUM\([^)]*\)\s*/\s*COUNT", "integer division"),
    ("tsql", r"\bAVG\s*\(\s*\w+\.quantity", "AVG over an integer column"),
    ("tsql", r"CAST\s*\(.*AS\s+INT\s*\)", "CAST to INT (truncation)"),
    ("tsql", r"\bLEN\s*\(", "LEN ignores trailing spaces"),
    ("tsql", r"\bCROSS\s+APPLY\b", "CROSS APPLY"),
    ("oracle", r"\bROWNUM\b", "ROWNUM pagination"),
    ("oracle", r"\bCONNECT\s+BY\b", "CONNECT BY hierarchy"),
    ("oracle", r"ORDER\s+SIBLINGS\s+BY", "ORDER SIBLINGS BY"),
    ("oracle", r"\(\+\)", "(+) outer join"),
    ("oracle", r"\bDECODE\s*\(", "DECODE"),
    ("oracle", r"\bNVL2?\s*\(", "NVL / NVL2"),
    ("oracle", r"\bTO_CHAR\s*\(", "TO_CHAR date mask"),
]


def detect_traps(q):
    return [label for dialect, pattern, label in DIALECT_TRAPS
            if dialect == q.dialect and re.search(pattern, q.body, re.IGNORECASE)]


def run_pytest():
    junit = REPORTS_DIR / "junit.xml"
    proc = subprocess.run([sys.executable, "-m", "pytest", "-q", f"--junitxml={junit}"],
                          cwd=ROOT, capture_output=True, text=True)
    tree = ET.parse(junit)
    per_conv = defaultdict(Counter)
    mutation = Counter()
    for case in tree.iter("testcase"):
        name = case.get("name")
        outcome = ("failed" if case.find("failure") is not None or case.find("error") is not None
                   else "skipped" if case.find("skipped") is not None else "passed")
        m = re.search(r"\[(llm|baseline)-q\d+\]", name)
        if m:
            per_conv[m.group(1)][outcome] += 1
        elif name.startswith("test_mutation"):
            mutation[outcome] += 1
        elif name.startswith("test_llm_documentation"):
            per_conv["docs"][outcome] += 1
    return proc, per_conv, mutation


def summarise(results):
    summary = {}
    for conv in CONVERTERS:
        rs = [r for r in results if r["converter"] == conv]
        passed = sum(1 for r in rs if r["passed"] is True)
        inconclusive = sum(1 for r in rs if r["passed"] is None)
        verifiable = len(rs) - inconclusive
        summary[conv] = {
            "total": len(rs), "passed": passed, "failed": verifiable - passed,
            "inconclusive": inconclusive, "verifiable": verifiable,
            "accuracy": passed / verifiable if verifiable else 0.0,
            "categories": Counter(r["category"] for r in rs if r["passed"] is False),
        }
    return summary


def status_word(r):
    return "PASS" if r["passed"] is True else "NOT VERIFIABLE" if r["passed"] is None else "FAIL"


def build_markdown(queries, results, summary, per_conv, mutations, env, generated):
    by_key = {(r["converter"], r["qid"]): r for r in results}
    out = [f"# Legacy SQL to Snowflake: conversion accuracy report\n",
           f"Generated {generated} · Snowflake engine: {env}\n",
           "## Accuracy\n",
           "| Converter | Accurate | Failed | Not verifiable locally | Accuracy | pytest checks (pass / fail / skip) |",
           "|---|---|---|---|---|---|"]
    for conv in CONVERTERS:
        s, t = summary[conv], per_conv[conv]
        out.append(f"| {CONVERTER_LABELS[conv]} | {s['passed']} / {s['verifiable']} | {s['failed']} | "
                   f"{s['inconclusive']} | **{s['accuracy']:.0%}** | {t['passed']} / {t['failed']} / {t['skipped']} |")
    out.append("\nAccuracy = queries whose Snowflake output matches the legacy output exactly "
               "(columns, row count, values and row order) / queries that could be verified.\n")

    out += ["## Results by query\n", "| Query | Dialect | Dialect traps in source | LLM | Baseline |",
            "|---|---|---|---|---|"]
    for q in queries:
        cells = [f"{status_word(by_key[(c, q.qid)])}"
                 + (f" ({by_key[(c, q.qid)]['category']})" if by_key[(c, q.qid)]["category"] else "")
                 for c in CONVERTERS]
        out.append(f"| {q.qid.upper()} {q.title} | {q.dialect} | {', '.join(detect_traps(q))} | "
                   + " | ".join(cells) + " |")

    out.append("\n## Errors caught by the checks\n")
    failures = [r for r in results if r["passed"] is not True]
    if not failures:
        out.append("No conversion errors were found.\n")
    for r in failures:
        out.append(f"### {CONVERTER_LABELS[r['converter']]} · {r['qid'].upper()} {r['title']}\n")
        label = CATEGORIES.get(r["category"], "Not verifiable on the local emulator")
        out.append(f"* **{label}** (`{r['category']}`)\n* {r['message']}")
        for d in r["diffs"][:4]:
            if "missing_rows" in d:
                out.append(f"* missing rows: {d['missing_rows']}  \n  unexpected rows: {d['unexpected_rows']}")
            else:
                out.append(f"* row {d['row']}, `{d['column']}`: expected `{d['expected']}`, got `{d['actual']}`")
        out.append("")

    out += ["## Are the checks strong enough? (negative controls)\n",
            f"{sum(1 for m in mutations if m['detected_as'])} of {len(mutations)} deliberately injected "
            "migration bugs were detected.\n",
            "| Injected bug | Query | Detected as |", "|---|---|---|"]
    for m in mutations:
        out.append(f"| {m['simulates']} | {m['query'].upper()} | {m['detected_as'] or 'NOT DETECTED'} |")

    shims = sorted({(r["qid"], s) for r in results for s in r["emulator_shims"]})
    out += ["\n## Method and limitations\n",
            "* **Legacy side:** expected outputs in `expected/` come from `harness/legacy_reference.py`, "
            "a reimplementation of each query using the source engine's documented semantics. "
            "`harness/capture_legacy.py` replaces them with real SQL Server / Oracle output when a database is available.",
            f"* **Snowflake side:** converted SQL runs on {env}.",
            f"* **Documentation:** {per_conv['docs']['passed']} of "
            f"{sum(per_conv['docs'].values())} generated docs contain all required sections."]
    if shims:
        out.append("* **Emulator shims** (no op on real Snowflake, applied to both converters): "
                   + "; ".join(f"{q.upper()}: {s}" for q, s in shims) + ".")
    if any(r["passed"] is None for r in results):
        out.append("* **Not verifiable locally:** valid Snowflake syntax the emulator cannot run faithfully; "
                   "excluded from the accuracy denominator until checked on a real account.")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- HTML

def esc(v):
    return html.escape(str(v))


def build_html(queries, results, summary, per_conv, mutations, env, generated):
    by_key = {(r["converter"], r["qid"]): r for r in results}

    def pill(r):
        cls = "pass" if r["passed"] is True else "warn" if r["passed"] is None else "fail"
        text = "Pass" if r["passed"] is True else "Not verifiable" if r["passed"] is None \
            else r["category"].replace("_", " ")
        return f'<span class="pill {cls}">{esc(text)}</span>'

    tiles = []
    for conv in CONVERTERS:
        s, t = summary[conv], per_conv[conv]
        pct = round(s["accuracy"] * 100)
        segs = "".join(
            f'<span class="seg {"pass" if by_key[(conv, q.qid)]["passed"] is True else "warn" if by_key[(conv, q.qid)]["passed"] is None else "fail"}" '
            f'title="{esc(q.qid.upper())}: {esc(status_word(by_key[(conv, q.qid)]))}"></span>'
            for q in queries)
        extra = f' · {s["inconclusive"]} not verifiable locally' if s["inconclusive"] else ""
        tiles.append(f"""
        <section class="score">
          <h3>{esc(CONVERTER_LABELS[conv])}</h3>
          <p class="big"><span class="num">{pct}</span><span class="unit">%</span></p>
          <p class="sub">{s['passed']} of {s['verifiable']} verifiable queries identical{extra}</p>
          <div class="strip" aria-label="per query result">{segs}</div>
          <p class="meta">pytest: {t['passed']} passed · {t['failed']} failed · {t['skipped']} skipped</p>
        </section>""")

    rows = []
    for q in queries:
        traps = "".join(f"<li>{esc(t)}</li>" for t in detect_traps(q))
        rows.append(f"""<tr>
          <td><span class="qid">{esc(q.qid.upper())}</span> {esc(q.title)}</td>
          <td><span class="dialect">{esc(q.dialect)}</span></td>
          <td><ul class="traps">{traps}</ul></td>
          <td>{pill(by_key[('llm', q.qid)])}</td>
          <td>{pill(by_key[('baseline', q.qid)])}</td></tr>""")

    errs = []
    for r in [r for r in results if r["passed"] is not True]:
        diffs = []
        for d in r["diffs"][:4]:
            if "missing_rows" in d:
                if d["missing_rows"]:
                    diffs.append(f"<li>missing: <code>{esc(d['missing_rows'])}</code></li>")
                if d["unexpected_rows"]:
                    diffs.append(f"<li>unexpected: <code>{esc(d['unexpected_rows'])}</code></li>")
            else:
                diffs.append(f"<li>row {d['row']} · <code>{esc(d['column'])}</code> expected "
                             f"<code>{esc(d['expected'])}</code> got <code>{esc(d['actual'])}</code></li>")
        sev = "warn" if r["passed"] is None else "fail"
        errs.append(f"""<article class="err {sev}">
          <header><span class="qid">{esc(r['qid'].upper())}</span> {esc(r['title'])}
            <span class="who">{esc(CONVERTER_LABELS[r['converter']])}</span></header>
          <p class="cat">{esc(CATEGORIES.get(r['category'], 'Not verifiable on the local emulator'))}</p>
          <p class="msg">{esc(r['message'])}</p>
          {'<ul class="diffs">' + ''.join(diffs) + '</ul>' if diffs else ''}
        </article>""")

    caught_pill, missed_pill = '<span class="pill pass">caught</span> ', '<span class="pill fail">missed</span> '
    muts = "".join(
        f"<tr><td>{esc(m['simulates'])}</td><td><span class='qid'>{esc(m['query'].upper())}</span></td>"
        f"<td>{caught_pill if m['detected_as'] else missed_pill}"
        f"<code>{esc(m['detected_as'] or '')}</code></td></tr>" for m in mutations)
    caught = sum(1 for m in mutations if m["detected_as"])
    shims = sorted({(r["qid"], s) for r in results for s in r["emulator_shims"]})
    shim_text = ("; ".join(f"{q.upper()}: {s}" for q, s in shims)) if shims else "none"

    return TEMPLATE.format(
        generated=esc(generated), env=esc(env), n=len(queries),
        n_tsql=sum(q.dialect == "tsql" for q in queries), n_oracle=sum(q.dialect == "oracle" for q in queries),
        tiles="".join(tiles), rows="".join(rows), errs="".join(errs) or "<p>No conversion errors were found.</p>",
        muts=muts, caught=caught, n_mut=len(mutations), shims=esc(shim_text),
        docs=f"{per_conv['docs']['passed']} of {sum(per_conv['docs'].values())}")


TEMPLATE = """<title>SQL Migration Scorecard</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Condensed:wght@500;600&family=IBM+Plex+Sans:wght@400;500&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
/* Layout: test run scorecard. Summary tiles, then query matrix, then error log. */
:root {{
  --bg: #f5f7f8; --surface: #ffffff; --fg: #17232b; --muted: #5b6b75; --line: #d9e1e5;
  --accent: #0b6e8a; --pass: #1d7a4a; --pass-bg: #e3f3ea; --fail: #b3261e; --fail-bg: #fbe7e5;
  --warn: #8a5a00; --warn-bg: #fbf0d9; --code-bg: #eef2f4;
  --display: "IBM Plex Sans Condensed", "Arial Narrow", sans-serif;
  --body: "IBM Plex Sans", system-ui, sans-serif;
  --mono: "IBM Plex Mono", ui-monospace, Menlo, monospace;
}}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{
  --bg: #0f171c; --surface: #16222a; --fg: #e3eaee; --muted: #93a4ae; --line: #2a3a44;
  --accent: #5cc3df; --pass: #6fd39b; --pass-bg: #163327; --fail: #ff8a80; --fail-bg: #3a1d1b;
  --warn: #f2c063; --warn-bg: #3a2e14; --code-bg: #1d2c35; color-scheme: dark; }} }}
:root[data-theme="dark"] {{
  --bg: #0f171c; --surface: #16222a; --fg: #e3eaee; --muted: #93a4ae; --line: #2a3a44;
  --accent: #5cc3df; --pass: #6fd39b; --pass-bg: #163327; --fail: #ff8a80; --fail-bg: #3a1d1b;
  --warn: #f2c063; --warn-bg: #3a2e14; --code-bg: #1d2c35; color-scheme: dark; }}
* {{ box-sizing: border-box; }}
body {{ background: var(--bg); color: var(--fg); font: 15px/1.55 var(--body); }}
.wrap {{ max-width: 1080px; margin: 0 auto; padding: 40px 20px 64px; display: grid; gap: 40px; }}
h1, h2, h3 {{ font-family: var(--display); font-weight: 600; text-wrap: balance; margin: 0; }}
h1 {{ font-size: clamp(1.8rem, 4vw, 2.5rem); line-height: 1.1; }}
h2 {{ font-size: 1.35rem; margin-bottom: 14px; }}
h3 {{ font-size: 1rem; }}
.eyebrow {{ font: 500 .75rem var(--mono); letter-spacing: .08em; text-transform: uppercase; color: var(--accent); margin: 0 0 8px; }}
.lede {{ color: var(--muted); max-width: 68ch; margin: 10px 0 0; }}
code {{ font: .85em var(--mono); background: var(--code-bg); padding: 1px 5px; border-radius: 3px; overflow-wrap: anywhere; }}
.scores {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; }}
.score {{ background: var(--surface); border: 1px solid var(--line); border-radius: 6px; padding: 20px; display: grid; gap: 6px; min-width: 0; }}
.big {{ margin: 4px 0 0; font-family: var(--display); line-height: 1; }}
.big .num {{ font-size: 3.4rem; font-variant-numeric: tabular-nums; }}
.big .unit {{ font-size: 1.6rem; color: var(--muted); margin-left: 2px; }}
.sub, .meta {{ margin: 0; color: var(--muted); }}
.meta {{ font: .8rem var(--mono); }}
.strip {{ display: grid; grid-auto-flow: column; grid-auto-columns: 1fr; gap: 3px; margin: 8px 0 4px; }}
.seg {{ height: 10px; border-radius: 2px; }}
.seg.pass {{ background: var(--pass); }} .seg.fail {{ background: var(--fail); }} .seg.warn {{ background: var(--warn); }}
.tbl {{ overflow-x: auto; background: var(--surface); border: 1px solid var(--line); border-radius: 6px; }}
table {{ border-collapse: collapse; width: 100%; min-width: 720px; }}
th, td {{ text-align: left; padding: 10px 14px; border-bottom: 1px solid var(--line); vertical-align: top; }}
th {{ font: 500 .72rem var(--mono); letter-spacing: .06em; text-transform: uppercase; color: var(--muted); }}
tr:last-child td {{ border-bottom: 0; }}
.qid {{ font: 500 .8rem var(--mono); color: var(--accent); margin-right: 4px; }}
.dialect {{ font: .8rem var(--mono); color: var(--muted); }}
.traps {{ margin: 0; padding: 0; list-style: none; display: flex; flex-wrap: wrap; gap: 4px; }}
.traps li {{ font-size: .75rem; border: 1px solid var(--line); border-radius: 3px; padding: 0 6px; color: var(--muted); }}
.pill {{ display: inline-block; font: 500 .75rem var(--mono); padding: 2px 8px; border-radius: 3px; white-space: nowrap; }}
.pill.pass {{ background: var(--pass-bg); color: var(--pass); }}
.pill.fail {{ background: var(--fail-bg); color: var(--fail); }}
.pill.warn {{ background: var(--warn-bg); color: var(--warn); }}
.errs {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 12px; }}
.err {{ background: var(--surface); border: 1px solid var(--line); border-left: 4px solid var(--fail); border-radius: 4px; padding: 14px 16px; min-width: 0; }}
.err.warn {{ border-left-color: var(--warn); }}
.err header {{ font-weight: 500; display: flex; flex-wrap: wrap; gap: 4px 8px; align-items: baseline; }}
.err .who {{ font: .75rem var(--mono); color: var(--muted); margin-left: auto; }}
.err .cat {{ margin: 8px 0 2px; font: 600 .85rem var(--display); color: var(--fail); }}
.err.warn .cat {{ color: var(--warn); }}
.err .msg {{ margin: 0; font-size: .85rem; color: var(--muted); overflow-wrap: anywhere; }}
.diffs {{ margin: 8px 0 0; padding-left: 18px; font-size: .82rem; display: grid; gap: 3px; }}
.method {{ color: var(--muted); max-width: 75ch; margin: 0; padding-left: 18px; display: grid; gap: 6px; }}
.method strong {{ color: var(--fg); font-weight: 500; }}
</style>
<div class="wrap">
  <header>
    <p class="eyebrow">pytest run · {generated}</p>
    <h1>Legacy SQL to Snowflake conversion accuracy</h1>
    <p class="lede">{n} legacy queries ({n_tsql} T-SQL, {n_oracle} Oracle) were converted by an LLM and by a rule based
    transpiler, run on the same sample data, and compared cell by cell with the legacy output.</p>
  </header>

  <div class="scores">{tiles}</div>

  <section>
    <h2>Results by query</h2>
    <div class="tbl"><table>
      <thead><tr><th>Query</th><th>Source</th><th>Dialect traps in source</th><th>LLM</th><th>Baseline</th></tr></thead>
      <tbody>{rows}</tbody>
    </table></div>
  </section>

  <section>
    <h2>Errors caught by the checks</h2>
    <div class="errs">{errs}</div>
  </section>

  <section>
    <h2>Negative controls: {caught} of {n_mut} injected bugs caught</h2>
    <div class="tbl"><table>
      <thead><tr><th>Injected migration bug</th><th>Query</th><th>Result</th></tr></thead>
      <tbody>{muts}</tbody>
    </table></div>
  </section>

  <section>
    <h2>Method and limitations</h2>
    <ul class="method">
      <li><strong>Legacy side.</strong> Expected outputs are computed by a reimplementation of each query that follows the
      source engine's documented semantics (integer division, case insensitive collation, LEN, CAST truncation, CONNECT BY order).
      Real SQL Server or Oracle output can replace them via <code>harness/capture_legacy.py</code>.</li>
      <li><strong>Snowflake side.</strong> Converted SQL runs on {env}.</li>
      <li><strong>Accuracy.</strong> A query counts as accurate only when columns, row count, every value (numeric tolerance 1e-6)
      and row order all match.</li>
      <li><strong>Emulator shims</strong> (no op on real Snowflake, applied to both converters): {shims}.</li>
      <li><strong>Not verifiable locally</strong> means valid Snowflake syntax the emulator cannot execute faithfully; it is
      excluded from the accuracy denominator.</li>
      <li><strong>Documentation.</strong> {docs} generated documents contain every required section.</li>
    </ul>
  </section>
</div>
"""


def main():
    proc, per_conv, mutation_counts = run_pytest()
    results = json.loads((REPORTS_DIR / "results.json").read_text())
    mutations = json.loads((REPORTS_DIR / "mutations.json").read_text())
    queries = load_queries()
    summary = summarise(results)
    env = "a real Snowflake account" if using_real_snowflake() else "fakesnow (local Snowflake emulator on DuckDB)"
    generated = datetime.now().strftime("%d %b %Y %H:%M")

    (REPORTS_DIR / "conversion_report.md").write_text(
        build_markdown(queries, results, summary, per_conv, mutations, env, generated))
    (REPORTS_DIR / "conversion_report.html").write_text(
        build_html(queries, results, summary, per_conv, mutations, env, generated))

    print(proc.stdout.strip().splitlines()[-1])
    for conv in CONVERTERS:
        s = summary[conv]
        print(f"{CONVERTER_LABELS[conv]:<32} accuracy {s['accuracy']:.0%} "
              f"({s['passed']}/{s['verifiable']}, {s['inconclusive']} not verifiable)")
    print(f"negative controls caught: {sum(1 for m in mutations if m['detected_as'])}/{len(mutations)}")
    print("wrote reports/conversion_report.md and reports/conversion_report.html")


if __name__ == "__main__":
    main()
