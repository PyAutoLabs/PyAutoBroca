"""Versioned evidence records; ingestion never edits an existing run."""
from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile


class InvalidRecord(ValueError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, indent=2) + "\n"


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def timestamp(value):
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)", value
    ):
        raise InvalidRecord("expected timezone-aware timestamp with seconds")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise InvalidRecord("invalid timestamp") from exc
    if result > datetime.now(timezone.utc):
        raise InvalidRecord("future timestamp")
    return result


def text(value, field, nullable=False):
    if nullable and value is None:
        return
    if not isinstance(value, str) or not value.strip() or len(value) > 4000:
        raise InvalidRecord(f"invalid {field}")


def validate(record, assistants):
    required = {"schema_version", "run_id", "assistant", "kind", "observed_at",
                "date_precision", "assistant_sha", "benchmark", "model", "harness",
                "environment", "status", "metrics", "reason", "source"}
    if not isinstance(record, dict) or set(record) != required:
        raise InvalidRecord("record fields do not match schema version 1")
    if type(record["schema_version"]) is not int or record["schema_version"] != 1:
        raise InvalidRecord("unsupported schema version")
    if record["assistant"] not in assistants:
        raise InvalidRecord("unregistered assistant")
    if not isinstance(record["run_id"], str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,160}", record["run_id"]):
        raise InvalidRecord("unsafe run_id")
    if record["kind"] not in {"benchmark", "maintenance"}:
        raise InvalidRecord("invalid kind")
    if record["date_precision"] == "second":
        timestamp(record["observed_at"])
    elif record["date_precision"] == "day":
        try:
            observed = date.fromisoformat(record["observed_at"])
            if observed.isoformat() != record["observed_at"] or observed > datetime.now(timezone.utc).date():
                raise ValueError()
        except (ValueError, TypeError) as exc:
            raise InvalidRecord("invalid observation date") from exc
    else:
        raise InvalidRecord("invalid date_precision")
    sha = record["assistant_sha"]
    if sha is not None and (not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha)):
        raise InvalidRecord("assistant_sha must be a full commit or null")
    benchmark = record["benchmark"]
    if not isinstance(benchmark, dict) or set(benchmark) != {"id", "version", "sha256"}:
        raise InvalidRecord("invalid benchmark")
    text(benchmark["id"], "benchmark id")
    text(benchmark["version"], "benchmark version", nullable=True)
    if benchmark["sha256"] is not None and not re.fullmatch(r"[0-9a-f]{64}", str(benchmark["sha256"])):
        raise InvalidRecord("invalid benchmark hash")
    for field in ("model", "harness", "reason"):
        text(record[field], field, nullable=True)
    if not isinstance(record["environment"], dict):
        raise InvalidRecord("environment must be an object")
    if record["status"] not in {"passed", "failed", "unscored"}:
        raise InvalidRecord("invalid status")
    if not isinstance(record["metrics"], dict):
        raise InvalidRecord("metrics must be an object")
    for key, value in record["metrics"].items():
        text(key, "metric name")
        if value is not None and (type(value) not in (int, float) or not math.isfinite(value) or value < 0):
            raise InvalidRecord("metrics must be finite nonnegative numbers or null")
    source = record["source"]
    if not isinstance(source, dict) or set(source) != {"revision", "path", "sha256"}:
        raise InvalidRecord("invalid source provenance")
    for key in source:
        text(source[key], f"source {key}")
    if not re.fullmatch(r"[0-9a-f]{64}", source["sha256"]):
        raise InvalidRecord("invalid source digest")
    if not re.fullmatch(r"[0-9a-f]{40}", source["revision"]):
        raise InvalidRecord("invalid source revision")
    path = Path(source["path"])
    if path.is_absolute() or ".." in path.parts or "\\" in source["path"]:
        raise InvalidRecord("unsafe source path")
    canonical(record)  # Reject non-JSON values and NaN inside environment too.
    return record


def write_once(path, value):
    """Atomic exclusive publish; identical retries are no-ops, conflicts fail."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical(value)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".ingest-")
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(payload)
        try:
            os.link(temporary, path)
            return True
        except FileExistsError:
            if path.is_symlink() or path.read_text() != payload:
                raise InvalidRecord(f"immutable record conflict: {path.name}")
            return False
    finally:
        os.unlink(temporary)


def ingest(root, record, assistants):
    validate(record, assistants)
    return write_once(Path(root) / "records" / f'{record["run_id"]}.json', record)


def load_records(root, assistants):
    result = []
    for path in sorted((Path(root) / "records").glob("*.json")):
        record = validate(json.loads(path.read_text()), assistants)
        if path.stem != record["run_id"]:
            raise InvalidRecord("filename does not match run_id")
        result.append(record)
    return result


def complete_provenance(value):
    if isinstance(value, dict):
        return bool(value) and all(complete_provenance(v) for v in value.values())
    if isinstance(value, list):
        return bool(value) and all(complete_provenance(v) for v in value)
    if isinstance(value, str):
        return bool(value.strip()) and value.lower() not in {"unknown", "unavailable", "n/a"}
    return value is not None


def comparable(a, b):
    """A change in assistant revision is allowed; unknown environments are not."""
    for record in (a, b):
        if not all((record["assistant_sha"], record["model"], record["harness"],
                    record["benchmark"]["version"], record["benchmark"]["sha256"])):
            return False
        env = record["environment"]
        if not all(complete_provenance(env.get(key)) for key in ("stack", "hardware", "harness_version", "scorer_revision")):
            return False
    return all(a[key] == b[key] for key in ("assistant", "kind", "benchmark", "model", "harness", "environment"))
