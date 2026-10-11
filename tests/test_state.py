"""Shared feed and site artifact preserve the meaning and age of owner evidence."""
from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from broca.__main__ import main
from broca.records import digest, ingest
from broca.state import build, shared_contract, UNKNOWN_TIME

BRAIN = Path(__file__).resolve().parents[2] / "PyAutoBrain"
NOW = datetime(2026, 10, 11, tzinfo=timezone.utc)


@pytest.fixture
def root(tmp_path):
    (tmp_path / "assistants.json").write_text(json.dumps({"schema_version": 1,
        "assistants": ["sample_assistant"], "evidence_max_age_days": 30,
        "collection_max_age_days": 5, "pages_url": "https://research.example/guides/"}))
    (tmp_path / "CHECKIN.md").write_text("Review existing evidence.")
    (tmp_path / "resources.json").write_text(json.dumps({"schema_version": 1,
        "resources": [{"id": "guide", "name": "Guide", "relations": ["documentation"],
                       "links": [], "projects": []}]}))
    return tmp_path


def receipt(root, when="2026-10-10T00:00:00Z", complete=True):
    snapshot = {"schema_version": 1, "attempted_at": when,
                "refreshed_at": when if complete else None,
                "assistants": [{"assistant": "sample_assistant", "status": "collected" if complete else "unavailable",
                                "revision": "a" * 40, "errors": []}]}
    folder = root / "receipts"; folder.mkdir(exist_ok=True)
    key = digest(snapshot)
    (folder / (key + ".json")).write_text(json.dumps(snapshot))
    (root / "latest.json").write_text(json.dumps({"receipt": key}))
    return folder / (key + ".json")


def benchmark(root, status="passed", day="2026-10-10", run_id="sample"):
    record = {"schema_version": 1, "run_id": run_id, "assistant": "sample_assistant",
        "kind": "benchmark", "observed_at": day, "date_precision": "day",
        "assistant_sha": "a" * 40, "benchmark": {"id": "quality", "version": "1", "sha256": "b" * 64},
        "model": "fixture", "harness": "fixture", "environment": {}, "status": status,
        "metrics": {}, "reason": "Saved outcome", "source": {"revision": "a" * 40,
        "path": "benchmarks/sample.json", "sha256": "c" * 64}}
    ingest(root, record, ["sample_assistant"])


def feed(root):
    return build(root, BRAIN, "Research/Communication", now=NOW)


def test_missing_collection_is_unknown_not_newly_measured(root):
    state = feed(root)
    assert shared_contract(BRAIN).validate_state(state) == []
    assert state["repo"] == "Communication" and state["organ"] == "broca"
    assert state["updated"] == UNKNOWN_TIME and state["status"] == "grey"
    assert "valid_until" not in state
    assert any("timestamp unknown" in row["text"] for row in state["items"])
    assert any("1 resources (inventory)" in row["text"] for row in state["items"])


def test_inventory_without_assistants_is_supported(root):
    path = root / "assistants.json"; cfg = json.loads(path.read_text()); cfg["assistants"] = []
    path.write_text(json.dumps(cfg))
    state = feed(root)
    assert state["status"] == "grey"
    assert all("Recorded pass" not in i["text"] for i in state["items"])
    assert main(["--root", str(root), "check"]) == 0


def test_collection_and_evaluation_clocks_stay_separate(root):
    receipt(root)
    benchmark(root, day="2026-01-01")
    state = feed(root)
    assert state["updated"] == "2026-10-10T00:00:00Z"
    assert state["valid_until"] == "2026-10-15T00:00:00+00:00"
    assert state["status"] == "yellow"
    assert any("Evidence outdated" in row["text"] and "2026-01-01" in row["text"] for row in state["items"])
    assert feed(root) == state


def test_old_collection_and_missing_sources_are_not_healthy(root):
    receipt(root, when="2026-09-01T00:00:00Z")
    assert feed(root)["status"] == "stale"
    receipt(root, complete=False)
    state = feed(root)
    assert state["status"] == "yellow"
    assert state["updated"] == "2026-10-10T00:00:00Z"
    assert "Collection incomplete" in state["items"][0]["text"]


def test_new_collection_cannot_extend_a_passing_benchmark_deadline(root):
    receipt(root)
    benchmark(root, day="2026-09-12")
    state = feed(root)
    assert state["status"] == "green"
    assert state["updated"] == "2026-10-10T00:00:00Z"
    assert state["valid_until"] == "2026-10-13T00:00:00+00:00"
    later = build(root, BRAIN, "Research/Communication",
                  now=datetime(2026, 10, 13, tzinfo=timezone.utc))
    assert later["status"] == "yellow"
    assert any("Evidence outdated" in row["text"] for row in later["items"])


def test_recorded_failures_survive_same_day_pass_ties(root):
    receipt(root)
    benchmark(root, status="passed", run_id="pass")
    assert feed(root)["status"] == "green"
    benchmark(root, status="failed", run_id="fail")
    assert feed(root)["status"] == "red"


def test_tampered_receipt_and_bad_catalogue_fail_closed(root):
    path = receipt(root); path.write_text(path.read_text() + " ")  # formatting is immaterial
    data = json.loads(path.read_text()); data["assistants"][0]["revision"] = "b" * 40
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="digest mismatch"):
        feed(root)
    receipt(root)
    (root / "resources.json").write_text('{"schema_version": 1, "resources": [42]}')
    with pytest.raises(ValueError, match="resource relations"):
        feed(root)


@pytest.mark.parametrize("identity,url", [("invalid", "https://research.example/"),
    ("Research/Communication", "http://research.example/"),
    ("Research/Communication", "https://user:password@research.example/")])
def test_identity_and_location_are_explicit(root, identity, url):
    with pytest.raises(ValueError):
        build(root, BRAIN, identity, url, now=NOW)


def test_cli_site_artifact_contains_only_html_and_feed(root, tmp_path):
    receipt(root)
    before = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}
    site = tmp_path / "site"
    args = ["--root", str(root), "render", "--brain", str(BRAIN), "--output", str(site / "index.html"),
            "--state-output", str(site / "state.json"), "--repository", "Research/RenamedGuides",
            "--pages-url", "https://research.example/custom/"]
    assert main(args) == 0
    assert sorted(p.name for p in site.iterdir()) == ["index.html", "state.json"]
    state = json.loads((site / "state.json").read_text())
    assert state["repo"] == "RenamedGuides" and state["pages_url"] == "https://research.example/custom/"
    assert shared_contract(BRAIN).validate_state(state) == []
    assert all((root / p).read_bytes() == contents for p, contents in before.items())
    assert "Guides &amp; Workspaces" in (site / "index.html").read_text()


def test_invalid_feed_configuration_writes_no_artifact(root, tmp_path):
    site = tmp_path / "site"
    assert main(["--root", str(root), "render", "--brain", str(BRAIN),
        "--output", str(site / "index.html"), "--state-output", str(site / "state.json")]) == 2
    assert not site.exists()
