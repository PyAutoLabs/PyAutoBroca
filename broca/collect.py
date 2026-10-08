"""Read committed assistant evidence without importing or executing assistants."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
import os

import yaml

from .records import InvalidRecord, digest, ingest, write_once, timestamp


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True,
                          capture_output=True, text=True, timeout=30).stdout.strip()


def config(root):
    data = json.loads((Path(root) / "assistants.json").read_text())
    names = data.get("assistants", [])
    if data.get("schema_version") != 1 or not names or len(names) != len(set(names)):
        raise ValueError("invalid assistant configuration")
    if any(not isinstance(n, str) or not re.fullmatch(r"[A-Za-z0-9_]+", n) for n in names):
        raise ValueError("invalid assistant name")
    if type(data.get("evidence_max_age_days")) is not int or data["evidence_max_age_days"] < 1:
        raise ValueError("invalid evidence age policy")
    return data


def identities(mind, names):
    repos = yaml.safe_load((Path(mind) / "repos.yaml").read_text())["repos"]
    result = {}
    for name in names:
        row = repos[name]
        path = Path(row["path"])
        if row["category"] != "assistant" or path.is_absolute() or ".." in path.parts:
            raise ValueError(f"invalid body-map assistant: {name}")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", row["github"]):
            raise ValueError("invalid GitHub identity")
        result[name] = row
    return result


def import_runs(root, repo, name, revision, paths, names):
    imported, errors = 0, []
    for path in sorted(paths):
        if not (path.startswith("benchmarks/runs/") and path.endswith("/meta.yaml")):
            continue
        try:
            meta_text = git(repo, "show", f"{revision}:{path}")
            meta = yaml.safe_load(meta_text)
            score_path = path.rsplit("/", 1)[0] + "/score.json"
            score_text = git(repo, "show", f"{revision}:{score_path}") if score_path in paths else "{}"
            score = json.loads(score_text)
            if not isinstance(meta, dict) or not isinstance(score, dict):
                raise ValueError("invalid benchmark metadata")
            short_sha = meta.get("assistant_sha")
            sha = None
            if isinstance(short_sha, str) and re.fullmatch(r"[0-9a-f]{7,40}", short_sha):
                try:
                    sha = git(repo, "rev-parse", "--verify", f"{short_sha}^{{commit}}")
                except subprocess.CalledProcessError:
                    pass
            value = score.get("score", meta.get("score"))
            if isinstance(value, dict):
                value = value.get("total")
            gates = score.get("gates", [])
            passed = bool(gates) and all(g.get("passed") is True for g in gates)
            failed = any(g.get("passed") is False for g in gates)
            # A numeric rubric alone does not establish a pass threshold.
            status = "failed" if failed else "passed" if passed else "unscored"
            run = meta.get("run") or {}
            record = {
                "schema_version": 1,
                "run_id": name + "-" + hashlib.sha256(path.encode()).hexdigest()[:24],
                "assistant": name, "kind": "benchmark",
                "observed_at": str(meta["date"]), "date_precision": "day",
                "assistant_sha": sha,
                "benchmark": {"id": str(meta["benchmark"]),
                              "version": str(meta["prompt_version"]) if meta.get("prompt_version") is not None else None,
                              "sha256": meta.get("prompt_sha256")},
                "model": meta.get("model"), "harness": meta.get("harness"),
                "environment": {"stack": meta.get("stack", {}), "hardware": meta.get("hardware", {}),
                                "harness_version": meta.get("harness_version"), "scorer_revision": meta.get("scorer_revision")},
                "status": status, "metrics": {"score": value, "wall_seconds": run.get("wall_seconds"),
                                                "cost_usd": run.get("cost_usd"), "interventions": None},
                "reason": score.get("reason") or ("Historical rubric; no explicit pass gates" if not gates else None),
                "source": {"revision": revision, "path": path,
                           "sha256": hashlib.sha256((meta_text + "\n" + score_text).encode()).hexdigest()},
            }
            # Source commit is the first import's immutable provenance. An unrelated
            # HEAD change must not manufacture another run or conflict on retry.
            existing = Path(root) / "records" / f'{record["run_id"]}.json'
            if existing.exists():
                prior = json.loads(existing.read_text())
                if prior["source"]["sha256"] == record["source"]["sha256"]:
                    record = prior
            imported += int(ingest(root, record, names))
        except (ValueError, KeyError, TypeError, AttributeError, subprocess.SubprocessError) as exc:
            errors.append({"path": path, "error": str(exc)[:300]})
    return imported, errors


def refresh(root, workspace, mind, *, import_history=False, pilot=False):
    cfg = config(root)
    names = cfg["assistants"]
    registry = identities(mind, names)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    snapshot = {"schema_version": 1, "attempted_at": now, "refreshed_at": None, "assistants": []}
    for name in names:
        identity = registry[name]
        row = {"assistant": name, "github": identity["github"], "status": "unavailable",
               "revision": None, "dirty": None, "benchmarks": [], "errors": []}
        repo = Path(workspace) / identity["path"]
        # Flat task bundles use the same identities, with canonical repo names.
        if not repo.exists() and (Path(workspace) / name).exists():
            repo = Path(workspace) / name
        try:
            revision = git(repo, "rev-parse", "HEAD")
            paths = set(git(repo, "ls-tree", "-r", "--name-only", "HEAD").splitlines())
            row.update(status="collected", revision=revision,
                       dirty=bool(git(repo, "status", "--porcelain")))
            row["benchmarks"] = sorted(p for p in paths if p.startswith("benchmarks/prompts/") and p.endswith(".md"))
            checks = {"instructions": "AGENTS.md" in paths,
                      "benchmark_runner": "autoassistant/benchmark.py" in paths,
                      "benchmark_definitions": bool(row["benchmarks"]),
                      "skills": any(p.startswith("skills/") and p.endswith(".md") for p in paths)}
            row["checks"] = checks
            if import_history:
                row["imported"], row["errors"] = import_runs(root, repo, name, revision, paths, names)
                if row["errors"]:
                    row["status"] = "partial"
            if pilot:
                payload = {"checks": checks, "assistant_sha": revision, "observed_at": now}
                record = {
                    "schema_version": 1, "run_id": name + "-inventory-" + digest(payload)[:24],
                    "assistant": name, "kind": "maintenance", "observed_at": now, "date_precision": "second",
                    "assistant_sha": revision,
                    "benchmark": {"id": "assistant-inventory", "version": "1", "sha256": digest({"checks": sorted(checks)})},
                    "model": None, "harness": "broca-inventory-v1", "environment": {},
                    "status": "passed" if all(checks.values()) else "failed",
                    "metrics": {k: int(v) for k, v in checks.items()},
                    "reason": "Committed-file inventory only; does not evaluate assistant responses or scientific correctness.",
                    "source": {"revision": revision, "path": "AGENTS.md", "sha256": digest(payload)},
                }
                ingest(root, record, names)
        except (ValueError, OSError, subprocess.SubprocessError) as exc:
            row["status"] = "unavailable"
            row["errors"].append({"path": "collection", "error": str(exc)[:300]})
        snapshot["assistants"].append(row)
    if all(r["status"] == "collected" for r in snapshot["assistants"]):
        snapshot["refreshed_at"] = now
    receipt = digest(snapshot)
    write_once(Path(root) / "receipts" / f"{receipt}.json", snapshot)
    # Pointer changes, append-only receipts do not. Replace atomically.
    fd, temporary = tempfile.mkstemp(dir=root, prefix=".latest-")
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(json.dumps({"receipt": receipt}) + "\n")
        os.replace(temporary, Path(root) / "latest.json")
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return snapshot


def validate_snapshot(snapshot, names):
    if snapshot.get("schema_version") != 1:
        raise InvalidRecord("unsupported collection schema")
    timestamp(snapshot["attempted_at"])
    rows = snapshot["assistants"]
    if len(rows) != len(names) or {r["assistant"] for r in rows} != set(names):
        raise InvalidRecord("collection coverage does not match configured assistants")
    for row in rows:
        if row["status"] not in {"collected", "partial", "unavailable"}:
            raise InvalidRecord("invalid collection status")
    if snapshot["refreshed_at"] is not None:
        timestamp(snapshot["refreshed_at"])
        if snapshot["refreshed_at"] != snapshot["attempted_at"] or any(r["status"] != "collected" for r in rows):
            raise InvalidRecord("incomplete collection cannot claim successful refresh")
    return snapshot


def check_receipts(root):
    names = config(root)["assistants"]
    for path in (Path(root) / "receipts").glob("*.json"):
        snapshot = json.loads(path.read_text())
        if digest(snapshot) != path.stem:
            raise InvalidRecord("collection receipt digest mismatch")
        validate_snapshot(snapshot, names)


def load_snapshot(root):
    pointer = Path(root) / "latest.json"
    if not pointer.exists():
        return {"schema_version": 1, "refreshed_at": None, "assistants": []}
    receipt = json.loads(pointer.read_text())["receipt"]
    if not re.fullmatch(r"[0-9a-f]{64}", receipt):
        raise InvalidRecord("invalid receipt pointer")
    snapshot = json.loads((Path(root) / "receipts" / f"{receipt}.json").read_text())
    if digest(snapshot) != receipt:
        raise InvalidRecord("collection receipt digest mismatch")
    return validate_snapshot(snapshot, config(root)["assistants"])
