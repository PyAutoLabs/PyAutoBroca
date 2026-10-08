"""Broca data rendered with Brain's shared presentation implementation."""
from datetime import date, datetime, timezone
import html
import importlib.util
from pathlib import Path
import re

from .collect import config, load_snapshot
from .records import comparable, load_records


def theme_from(brain):
    path = Path(brain) / "board" / "_theme.py"
    spec = importlib.util.spec_from_file_location("broca_shared_theme", path)
    theme = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(theme)
    if "broca" not in theme.ORGANS:
        raise ValueError("Brain checkout needs the Broca theme registration")
    return theme


def evidence_state(record, row, max_age, today=None):
    if record is None:
        return "Never evaluated"
    if record["status"] == "failed":
        return "Recorded failure"
    if not record["assistant_sha"] or not row.get("revision"):
        return "Revision unknown"
    if record["assistant_sha"] != row["revision"]:
        return "Changed since evaluation"
    observed = date.fromisoformat(record["observed_at"][:10])
    if ((today or datetime.now(timezone.utc).date()) - observed).days > max_age:
        return "Evidence outdated"
    return "Recorded pass" if record["status"] == "passed" else "Needs interpretation"


def render(root, brain):
    theme = theme_from(brain)
    cfg = config(root)
    snapshot = load_snapshot(root)
    records = load_records(root, cfg["assistants"])
    rows = {r["assistant"]: r for r in snapshot["assistants"]}
    esc = lambda value: html.escape(str(value), quote=True)
    panels, attention, history, maintenance = [], [], [], []
    for name in cfg["assistants"]:
        row = rows.get(name, {})
        runs = sorted((r for r in records if r["assistant"] == name and r["kind"] == "benchmark"),
                      key=lambda r: (r["observed_at"], r["run_id"]))
        # Date-only imports cannot establish an order within a day. Show the
        # most conservative outcome from the latest day, not a random run ID.
        latest_day = max((r["observed_at"][:10] for r in runs), default=None)
        latest = max((r for r in runs if r["observed_at"][:10] == latest_day),
                     key=lambda r: {"passed": 0, "unscored": 1, "failed": 2}[r["status"]], default=None)
        state = evidence_state(latest, row, cfg["evidence_max_age_days"])
        collected = row.get("status", "unavailable")
        errors = row.get("errors", [])
        repo = row.get("github", "")
        link = (f'<a href="https://github.com/{esc(repo)}">{esc(name)}</a>'
                if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo) else esc(name))
        when = latest["observed_at"] if latest else "No run recorded"
        revision = (row.get("revision") or "Unknown")[:12]
        definitions = len(row.get("benchmarks", [])) if collected != "unavailable" else "Unknown"
        panels.append(f'<article class="assistant-card"><h3>{link}</h3><p><strong>{esc(state)}</strong></p>'
                      f'<dl><dt>Latest evidence day</dt><dd>{esc(when)}</dd><dt>Runs recorded</dt><dd>{len(runs)}</dd>'
                      f'<dt>Current commit</dt><dd><code>{esc(revision)}</code></dd>'
                      f'<dt>Evaluated commit</dt><dd><code>{esc((latest["assistant_sha"] or "Unknown")[:12] if latest else "None")}</code></dd>'
                      f'<dt>Benchmark definitions</dt><dd>{definitions}</dd>'
                      f'<dt>Collection</dt><dd>{esc(collected)}</dd></dl>'
                      + ('<p>Local uncommitted changes are excluded from evidence.</p>' if row.get("dirty") else '') + '</article>')
        if collected != "collected":
            action = "Restore complete collection before judging this assistant."
        elif not latest:
            action = ("Add a small benchmark definition, then capture the first response-quality baseline."
                      if not row.get("benchmarks") else "Select a small benchmark and capture the first response-quality baseline.")
        elif state == "Recorded failure":
            action = "Inspect the failed gates, then choose a bounded rerun or route a fix through Mind."
        elif state in {"Changed since evaluation", "Evidence outdated", "Revision unknown"}:
            action = "Run a small benchmark against the current revision with complete provenance."
        else:
            action = "Review uncovered capabilities and select the next useful evaluation."
        attention.append(f'<li><strong>{esc(name)}</strong>: {esc(action)}</li>')
        for error in errors:
            attention.append(f'<li>{esc(name)} — {esc(error["path"])}: {esc(error["error"])}</li>')
        checks = row.get("checks", {})
        maintenance.append(f'<li><strong>{esc(name)}</strong>: ' +
                           (', '.join(f'{esc(k.replace("_", " "))}: {"present" if v else "missing"}' for k, v in checks.items())
                            if checks else 'Inventory unavailable') + '</li>')
        for index, record in enumerate(runs):
            prior = next((r for r in reversed(runs[:index])
                          if r["observed_at"][:10] < record["observed_at"][:10] and comparable(r, record)), None)
            delta = "No comparable baseline"
            score = record["metrics"].get("score")
            if prior is not None and score is not None and prior["metrics"].get("score") is not None:
                delta = f'{score - prior["metrics"]["score"]:+g} score points vs {prior["run_id"]}'
            history.append((record["observed_at"], f'<tr><th scope="row">{esc(name)}<br>{esc(record["benchmark"]["id"])}</th>'
                            f'<td>{esc(record["observed_at"])}<br>{esc(record["model"] or "Unknown model")}</td>'
                            f'<td>{esc(record["status"])}<br>{esc(score if score is not None else "Unscored")}</td>'
                            f'<td>{esc(record["reason"] or "—")}<br>{esc(delta)}</td>'
                            f'<td><code>{esc(record["run_id"])}</code><br>{esc(record["source"]["path"])}</td></tr>'))
    prompt = (Path(root) / "CHECKIN.md").read_text()
    navigation = [{"href": "#assistants", "label": "Assistants", "count": len(cfg["assistants"])},
                  {"href": "#attention", "label": "Next actions"},
                  {"href": "#history", "label": "Evaluations", "count": len(history)},
                  {"href": "#maintenance", "label": "Maintenance"}]
    panel = theme.orchestration_panel("broca-checkin", "Check in with Broca", "", prompt,
                                     organ="broca", work_links=[{"label": "PyAutoBroca", "href": "https://github.com/PyAutoLabs/PyAutoBroca"}],
                                     refreshed_at=snapshot.get("refreshed_at"), refresh_url=None)
    table = ('<div class="table-scroll" role="region" aria-label="Evaluation history; scroll for more columns" tabindex="0">'
             '<table><thead><tr><th>Assistant / benchmark</th><th>Date / model</th><th>Outcome / score</th><th>Evidence / comparison</th><th>Record</th></tr></thead><tbody>'
             + ''.join(row for _, row in sorted(history, key=lambda item: item[0], reverse=True)) + '</tbody></table></div>') if history else '<p>No benchmark runs recorded.</p>'
    page = ('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>PyAutoBroca · Assistants</title><style>' + theme.css("broca") + '''
.assistant-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,260px),1fr));gap:1rem}
.assistant-card{border:1px solid var(--line,#888);border-radius:12px;padding:1rem;min-width:0}
.assistant-card h3{margin-top:0}dl{display:grid;grid-template-columns:1fr 1fr;gap:.4rem}dd{margin:0}
.table-scroll{overflow-x:auto;max-width:100%}.table-scroll table{min-width:760px;width:100%}
th,td{text-align:left;vertical-align:top;padding:.6rem}td code{overflow-wrap:anywhere}
</style></head><body><main>''' + theme.hero("broca", "Assistants", navigation=navigation) + panel +
            '<section id="assistants"><h2>Assistants</h2><div class="assistant-grid">' + ''.join(panels) + '</div></section>' +
            '<section id="attention"><h2>Next actions</h2><ul>' + ''.join(attention) + '</ul></section>' +
            '<section id="history"><h2>Evaluation history</h2>' + table + '</section>' +
            '<section id="maintenance"><h2>Maintenance</h2><p>Committed-file inventory; these checks do not establish response quality or scientific correctness.</p><ul>' + ''.join(maintenance) + '</ul></section>' +
            '<footer>Private operational evidence · collection age and evaluation age are separate.</footer></main><script>' + theme.JS + '</script></body></html>')
    return theme.section_layout(page)
