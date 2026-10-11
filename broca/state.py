"""Broca's shared feed: saved owner evidence, never a new collection or run."""
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

from .board import evidence_state, latest_benchmark
from .collect import config, load_snapshot
from .records import load_records

UNKNOWN_TIME = "1970-01-01T00:00:00Z"  # v1 requires a timestamp even when no receipt exists.


def shared_contract(brain):
    spec = importlib.util.spec_from_file_location("broca_shared_state", Path(brain) / "board/_state.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def pages_directory(value):
    if not isinstance(value, str):
        raise ValueError("configure pages_url or supply --pages-url")
    url = urlsplit(value)
    if (url.scheme != "https" or not url.hostname or url.username or url.password
            or url.query or url.fragment or "\\" in value or any(c.isspace() for c in value)):
        raise ValueError("pages_url must be an explicit public HTTPS directory")
    return value.rstrip("/") + "/"


def build(root, brain, repository, pages_url=None, *, now=None):
    """Repository comes from canonical publishing context, not the checkout name."""
    if not isinstance(repository, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("--repository must be the canonical owner/repository identity")
    cfg = config(root)
    pages = pages_directory(pages_url or cfg.get("pages_url"))
    max_age = cfg.get("collection_max_age_days", 30)
    if type(max_age) is not int or max_age < 1:
        raise ValueError("collection_max_age_days must be a positive integer")
    contract = shared_contract(brain)
    snapshot = load_snapshot(root)
    records = load_records(root, cfg["assistants"])
    now = now or datetime.now(timezone.utc)
    attempted = snapshot.get("attempted_at")
    updated = attempted or UNKNOWN_TIME
    if not contract._is_utc_iso(updated):
        raise ValueError("collection attempt must have a full UTC timestamp")
    expires = (datetime.fromisoformat(updated.replace("Z", "+00:00")) + timedelta(days=max_age)) if attempted else None
    valid_until = expires
    complete = snapshot.get("refreshed_at") is not None
    items = [{"severity": "info" if complete else "yellow", "text":
              ("Collection: " + snapshot["refreshed_at"]) if complete else
              ("Collection incomplete; attempt " + attempted if attempted else "Collection unavailable; timestamp unknown"),
              "url": pages + "#maintenance"}]
    catalogue_path = Path(root) / "resources.json"
    if catalogue_path.exists():
        catalogue = json.loads(catalogue_path.read_text())
        if not isinstance(catalogue, dict) or catalogue.get("schema_version") != 1 or not isinstance(catalogue.get("resources"), list):
            raise ValueError("invalid public resource catalogue")
        communication = {"workspaces", "tutorials", "documentation"}
        count = 0
        for resource in catalogue["resources"]:
            if not isinstance(resource, dict) or not isinstance(resource.get("relations"), list) or any(not isinstance(k, str) for k in resource["relations"]):
                raise ValueError("invalid public resource relations")
            if communication.intersection(resource["relations"]) and "assistants" not in resource["relations"]:
                count += 1
        text = f"Guides & Workspaces: {count} resources (inventory)"
    else:
        text = "Guides & Workspaces: inventory unavailable"
    items.append({"severity": "info", "text": text, "url": pages + "#communication"})
    rows = {row["assistant"]: row for row in snapshot["assistants"]}
    states = []
    for name in cfg["assistants"]:
        latest = latest_benchmark([r for r in records if r["assistant"] == name and r["kind"] == "benchmark"])
        state = evidence_state(latest, rows.get(name, {}), cfg["evidence_max_age_days"], today=now.date())
        states.append(state)
        if state == "Recorded pass":
            # evidence_state uses whole UTC calendar days: age == max is still
            # current; it becomes outdated at the next midnight. A newer
            # collection must not extend a passing benchmark's validity.
            deadline = (datetime.fromisoformat(latest["observed_at"][:10]).replace(tzinfo=timezone.utc)
                        + timedelta(days=cfg["evidence_max_age_days"] + 1))
            valid_until = min(valid_until, deadline) if valid_until else deadline
        severity = "red" if state == "Recorded failure" else "info" if state in {"Recorded pass", "Never evaluated"} else "yellow"
        observed = f" · observed {latest['observed_at']}" if latest else ""
        items.append({"severity": severity, "text": f"{name}: {state}{observed}", "url": pages + "#assistants"})
    stale = expires is not None and now > expires
    if stale:
        items.append({"severity": "yellow", "text": "Collection evidence outdated", "url": pages + "#maintenance"})
    status = ("red" if "Recorded failure" in states else "stale" if stale else
              "yellow" if attempted and (not complete or any(i["severity"] == "yellow" for i in items)) else
              "green" if complete and states and all(s == "Recorded pass" for s in states) else "grey")
    return contract.build_state("broca", repository.split("/")[1], status,
        "Guides & Workspaces · assistant evidence", updated, pages, items,
        valid_until=valid_until.isoformat() if valid_until else None)
