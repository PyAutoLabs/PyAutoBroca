"""Recovery and preservation at the independent-instance setup boundary."""
import json
from pathlib import Path

import pytest

from broca.__main__ import main
from broca import setup
from broca.state import UNKNOWN_TIME, shared_contract
from broca.records import digest

BRAIN = Path(__file__).resolve().parents[2] / "PyAutoBrain"


@pytest.fixture
def inputs(tmp_path):
    repos = tmp_path / "repos.yaml"
    repos.write_text("repos:\n  guides:\n    github: Research/IndependentGuides\n")
    root = tmp_path / "data"
    return root, repos


def args(inputs):
    root, repos = inputs
    return ["--root", str(root), "setup", "--repos", str(repos), "--repo", "guides",
            "--pages-url", "https://research.example/guides/", "--brain", str(BRAIN)]


def prepare(inputs):
    root, repos = inputs
    return setup.prepare(root, repos, "guides", "https://research.example/guides/", BRAIN)


def contents(root):
    return {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_preview_apply_retry_and_render(inputs, tmp_path):
    root, _ = inputs
    assert main(args(inputs)) == 0
    assert not root.exists()
    assert main(args(inputs) + ["--apply"]) == 0
    assert set(p.name for p in root.iterdir()) == {"setup.json", "assistants.json", "SETUP.md", "CHECKIN.md"}
    before = contents(root)
    assert main(args(inputs) + ["--apply"]) == 0
    assert contents(root) == before
    assert main(["--root", str(root), "check"]) == 0
    site = tmp_path / "preview"
    assert main(["--root", str(root), "render", "--brain", str(BRAIN),
                 "--repository", "Research/IndependentGuides", "--output", str(site / "index.html"),
                 "--state-output", str(site / "state.json")]) == 0
    feed = json.loads((site / "state.json").read_text())
    assert shared_contract(BRAIN).validate_state(feed) == []
    assert feed["repo"] == "IndependentGuides"
    assert feed["status"] == "grey" and feed["updated"] == UNKNOWN_TIME
    assert "Collection unavailable" in feed["items"][0]["text"]
    assert "inventory unavailable" in feed["items"][1]["text"]
    assert contents(root) == before


@pytest.mark.parametrize("after", [1, 2, 3])
def test_interruption_resumes_without_rewriting_completed_files(inputs, monkeypatch, after):
    root, _ = inputs
    original = setup.create_file
    count = 0

    def interrupt(path, content):
        nonlocal count
        if count == after:
            raise OSError("interrupted")
        original(path, content)
        count += 1

    monkeypatch.setattr(setup, "create_file", interrupt)
    assert main(args(inputs) + ["--apply"]) == 2
    before = {p: (data, (root / p).stat().st_mtime_ns) for p, data in contents(root).items()}
    monkeypatch.setattr(setup, "create_file", original)
    assert main(args(inputs) + ["--apply"]) == 0
    for p, (data, mtime) in before.items():
        assert (root / p).read_bytes() == data
        assert (root / p).stat().st_mtime_ns == mtime


def test_conflict_is_preflighted_and_user_records_preserved(inputs):
    root, _ = inputs
    assert main(args(inputs) + ["--apply"]) == 0
    (root / "research.txt").write_text("baseline-A: preserve this research")
    (root / "records").mkdir()
    (root / "records" / "note.txt").write_text("existing user record")
    before = contents(root)
    assert main(args(inputs) + ["--apply"]) == 0
    assert contents(root) == before
    (root / "CHECKIN.md").unlink()
    (root / "assistants.json").write_text('{"user": "customized"}')
    before = contents(root)
    assert main(args(inputs) + ["--apply"]) == 2
    assert contents(root) == before
    assert not (root / "CHECKIN.md").exists()


@pytest.mark.parametrize("kind", ["identity", "url", "map", "brain", "nonempty", "symlink"])
def test_invalid_inputs_do_not_initialize(inputs, tmp_path, kind):
    root, repos = inputs
    argv = args(inputs)
    if kind == "identity":
        argv[argv.index("--repo") + 1] = "missing"
    elif kind == "url":
        argv[argv.index("--pages-url") + 1] = "http://research.example/"
    elif kind == "map":
        repos.write_text("repos: []")
    elif kind == "brain":
        argv[argv.index("--brain") + 1] = str(tmp_path)
    elif kind == "nonempty":
        root.mkdir()
        (root / "research.txt").write_text("preserve")
    else:
        other = tmp_path / "other"
        other.mkdir()
        root.symlink_to(other, target_is_directory=True)
    before = contents(root)
    assert main(argv + ["--apply"]) == 2
    assert contents(root) == before


def test_changed_identity_and_symlink_file_refused(inputs, tmp_path):
    root, repos = inputs
    assert main(args(inputs) + ["--apply"]) == 0
    before = contents(root)
    repos.write_text("repos:\n  guides:\n    github: Research/OtherGuides\n")
    assert main(args(inputs) + ["--apply"]) == 2
    assert contents(root) == before
    repos.write_text("repos:\n  guides:\n    github: Research/IndependentGuides\n")
    (root / "CHECKIN.md").unlink()
    target = tmp_path / "external"
    target.write_text("untouched")
    (root / "CHECKIN.md").symlink_to(target)
    assert main(args(inputs) + ["--apply"]) == 2
    assert target.read_text() == "untouched"


def test_change_between_preview_and_apply_is_not_overwritten(inputs):
    root, _ = inputs
    prepared = prepare(inputs)
    root.mkdir()
    (root / "research.txt").write_text("new data")
    with pytest.raises(ValueError, match="changed before apply"):
        setup.apply(prepared)
    assert list(root.iterdir()) == [root / "research.txt"]


def test_atomic_create_does_not_replace_existing_file(tmp_path):
    path = tmp_path / "file"
    path.write_bytes(b"existing")
    with pytest.raises(FileExistsError):
        setup.create_file(path, b"replacement")
    assert path.read_bytes() == b"existing"
    assert list(tmp_path.iterdir()) == [path]


def test_saved_receipt_and_records_survive_failed_owner_validation(inputs):
    root, _ = inputs
    assert main(args(inputs) + ["--apply"]) == 0
    snapshot = {"schema_version": 1, "attempted_at": "2026-10-11T00:00:00Z",
                "refreshed_at": "2026-10-11T00:00:00Z", "assistants": []}
    key = digest(snapshot)
    (root / "receipts").mkdir()
    (root / "receipts" / (key + ".json")).write_text(json.dumps(snapshot))
    (root / "latest.json").write_text(json.dumps({"receipt": key}))
    before = contents(root)
    assert main(args(inputs) + ["--apply"]) == 0
    assert contents(root) == before
    (root / "records").mkdir()
    (root / "records" / "invalid.json").write_text('{"existing": "do not delete"}')
    before = contents(root)
    assert main(args(inputs) + ["--apply"]) == 2
    assert contents(root) == before
