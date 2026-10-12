"""Offline, create-only initialization of a user-owned Broca data directory."""
import json
import os
from pathlib import Path
import re
import shlex
import tempfile

import yaml

from .state import pages_directory

MANIFEST = "setup.json"


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def plain_path(path):
    """Reject symlink destinations, including symlink parents, before resolving."""
    path = Path(os.path.abspath(path))
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError(f"setup path must not use symlinks: {path}")
    return path


def prepare(root, repos, repo, pages_url, brain):
    root = plain_path(root)
    if not root.parent.is_dir():
        raise ValueError("destination parent must already exist")
    if root.exists() and not root.is_dir():
        raise ValueError("destination must be a directory")
    repos, brain = Path(repos).resolve(), Path(brain).resolve()
    try:
        catalogue = yaml.safe_load(repos.read_text())
    except yaml.YAMLError as exc:
        raise ValueError("invalid canonical repository map") from exc
    entries = catalogue.get("repos") if isinstance(catalogue, dict) else None
    row = entries.get(repo) if isinstance(entries, dict) else None
    identity = row.get("github") if isinstance(row, dict) else None
    if not isinstance(identity, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", identity):
        raise ValueError("repo must identify a canonical owner/repository in the supplied map")
    pages = pages_directory(pages_url)
    if not all((brain / "board" / name).is_file() for name in ("_state.py", "_theme.py")):
        raise ValueError("Brain checkout needs the shared board and state contract")
    manifest = {"schema_version": 1, "repo": repo, "repository": identity,
                "pages_url": pages, "repos": str(repos), "brain": str(brain),
                "root": str(root), "framework": str(Path(__file__).resolve().parents[1])}
    cfg = {"schema_version": 1, "assistants": [], "evidence_max_age_days": 30,
           "collection_max_age_days": 30, "pages_url": pages}
    checkin = ("Review this instance's saved communication inventory and assistant evidence.\n"
               "Read the canonical Mind map and existing task before proposing changes.\n"
               "Missing collection or evaluation is unknown, never a pass. Preserve records.\n"
               "Do not collect, evaluate, schedule or publish without explicit authorization.\n")
    q = shlex.quote
    prefix = f"python -m broca --root {q(str(root))}"
    resume = (f"{prefix} setup --repos {q(str(repos))} --repo {q(repo)} "
              f"--pages-url {q(pages)} --brain {q(str(brain))}")
    render = (f"{prefix} render --brain {q(str(brain))} --repository {q(identity)} "
              f"--output {q(str(root / 'site/index.html'))} "
              f"--state-output {q(str(root / 'site/state.json'))}")
    handoff = f"""# Local Broca setup handoff

Keep this file and setup.json private: they contain local paths.
From the framework checkout, with Python and its dependencies available:

```sh
cd {q(manifest['framework'])}
{resume}
# After reviewing the preview, repeat with --apply to finish missing files.
{prefix} check
{render}
```

For a fresh conversation: read setup.json, this file, the canonical map and the
existing Mind task. Preview setup to identify missing or conflicting files. Resume
only this setup; never reinitialize or overwrite user edits. If configuration has
changed intentionally since setup, use check/render rather than restoring defaults.
The manifest records setup inputs, not task status or evidence of activation.

This prepares local data only. No collection or evaluation has occurred. An empty
feed is grey with an unknown collection timestamp. Projects, tasks and research
records remain in their existing homes. Add communication resources using Broca's
existing inventory procedure; do not copy a maintainer's records or receipts.

Publishing needs a separate approved task using the configured identity and public
board location. Publish only site/index.html and site/state.json after reviewing
visibility. Do not publish this directory wholesale. After the real HTTPS feed is
available, use Scientist's connect_organ.py preview/apply with organ broca, repo
{repo!r}, and pages URL {pages!r}. Until that validation succeeds, setup is not a
connected or active Scientist capability. Missing or stale evidence after connection
remains evidence trouble; it does not mean the organ is uninstalled.
"""
    files = {MANIFEST: encoded(manifest), "assistants.json": encoded(cfg),
             "CHECKIN.md": checkin.encode(), "SETUP.md": handoff.encode()}
    # Only a manifest from this exact setup grants permission to fill missing files
    # in an existing directory. Never adopt a pre-existing live data checkout.
    if root.exists() and any(root.iterdir()) and not (root / MANIFEST).exists():
        raise ValueError("nonempty destination has no setup manifest; refusing adoption")
    missing = inspect(root, files)
    return root, files, missing


def inspect(root, files):
    plain_path(root)
    missing = []
    for name, content in files.items():
        path = root / name
        if path.is_symlink() or (path.exists() and (not path.is_file() or path.read_bytes() != content)):
            raise ValueError(f"setup conflict: {name}; preserve it and review manually")
        if not path.exists():
            missing.append(name)
    return missing


def create_file(path, content):
    """Publish a complete file without replacing a concurrently created target."""
    fd, temporary = tempfile.mkstemp(prefix=".broca-setup-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)  # atomic create-only; an existing target wins
    finally:
        os.unlink(temporary)


def apply(prepared):
    root, files, _ = prepared
    root.mkdir(exist_ok=True)
    if any(root.iterdir()) and not (root / MANIFEST).exists():
        raise ValueError("destination changed before apply; no setup manifest")
    missing = inspect(root, files)  # preflight every conflict before writing
    for name in missing:  # manifest is published first; interruption is resumable
        inspect(root, files)
        create_file(root / name, files[name])
    inspect(root, files)
    from .collect import check_receipts, config, load_snapshot
    from .records import load_records
    from .state import build, shared_contract
    cfg = config(root)
    check_receipts(root)
    load_snapshot(root)
    load_records(root, cfg["assistants"])
    manifest = json.loads(files[MANIFEST])
    state = build(root, manifest["brain"], manifest["repository"])
    errors = shared_contract(manifest["brain"]).validate_state(state)
    if errors:
        raise ValueError(f"owner feed validation failed: {errors}")
    return missing
