"""Prepare a static, reviewable Pages bundle without publishing anything."""
import json
from pathlib import Path
import re

import yaml

from .board import render
from .collect import check_receipts, config, load_snapshot
from .records import load_records
from .setup import plain_path
from .state import build, pages_directory, shared_contract


def workflow(repository, pages, branch):
    # The shared contract was checked during rendering. At publication, check
    # artifact membership and identity again without installing the framework.
    check = f'''python - <<'PYTHON'
import json, os
from pathlib import Path
site = Path("site")
if site.is_symlink() or not site.is_dir():
    raise SystemExit("site must be a real directory")
if sorted(p.name for p in site.iterdir()) != ["index.html", "state.json"]:
    raise SystemExit("site must contain only index.html and state.json")
if any(p.is_symlink() or not p.is_file() for p in site.iterdir()):
    raise SystemExit("site entries must be regular files")
state = json.loads((site / "state.json").read_text())
if os.environ["GITHUB_REPOSITORY"] != {repository!r}:
    raise SystemExit("publishing repository differs from configured identity")
if (state.get("organ"), state.get("repo"), state.get("pages_url")) != (
        "broca", {repository.split('/')[-1]!r}, {pages!r}):
    raise SystemExit("feed identity differs from configured publication")
PYTHON'''
    return yaml.safe_dump({
        "name": "Publish Broca snapshot",
        "on": {"push": {"branches": [branch]}, "pull_request": None, "workflow_dispatch": None},
        "permissions": {"contents": "read"},
        "concurrency": {"group": "pages-${{ github.event_name == 'pull_request' && github.ref || 'production' }}",
                        "cancel-in-progress": False},
        "jobs": {
            "build": {"runs-on": "ubuntu-latest", "steps": [
                {"uses": "actions/checkout@v4"},
                {"uses": "actions/setup-python@v5", "with": {"python-version": "3.12"}},
                {"name": "Validate publication files and identity", "run": check},
                {"uses": "actions/upload-pages-artifact@v3", "with": {"path": "site"}}]},
            "deploy": {
                "if": f"github.ref == 'refs/heads/{branch}' && github.event_name != 'pull_request'",
                "needs": "build", "runs-on": "ubuntu-latest",
                "permissions": {"pages": "write", "id-token": "write"},
                "environment": {"name": "github-pages", "url": "${{ steps.deployment.outputs.page_url }}"},
                "steps": [{"name": "Deploy reviewed snapshot", "id": "deployment",
                           "uses": "actions/deploy-pages@v4"}]}}}, sort_keys=False)


def prepare(root, repos, repo, pages_url, brain, output, branch="main"):
    root = Path(root).resolve()
    output = plain_path(output)
    if output.exists() or not output.parent.is_dir():
        raise ValueError("publication destination must be new, with an existing parent")
    if output == root or root in output.parents:
        raise ValueError("publication destination must be outside the private data directory")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", branch):
        raise ValueError("publication branch must contain only letters, digits, hyphens or underscores")
    try:
        catalogue = yaml.safe_load(Path(repos).read_text())
    except yaml.YAMLError as exc:
        raise ValueError("invalid canonical repository map") from exc
    entries = catalogue.get("repos") if isinstance(catalogue, dict) else None
    row = entries.get(repo) if isinstance(entries, dict) else None
    repository = row.get("github") if isinstance(row, dict) else None
    if not isinstance(repository, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("repo must identify a canonical owner/repository in the supplied map")
    pages = pages_directory(pages_url)
    cfg = config(root)
    check_receipts(root)
    load_snapshot(root)
    load_records(root, cfg["assistants"])
    state = build(root, brain, repository, pages)
    errors = shared_contract(brain).validate_state(state)
    if errors:
        raise ValueError(f"invalid publication feed: {errors}")
    page = render(root, brain, repository=repository)
    return output, {
        "site/index.html": page,
        "site/state.json": json.dumps(state, indent=2) + "\n",
        ".github/workflows/pages.yml": workflow(repository, pages, branch),
    }


def apply(prepared):
    output, files = prepared
    plain_path(output)
    output.mkdir()  # exclusive: never overwrite an existing publication checkout
    for name, content in files.items():
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x") as stream:
            stream.write(content)
    return output
