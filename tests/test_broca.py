import copy
import json
from pathlib import Path
import subprocess

import pytest
import yaml

from broca.records import InvalidRecord, comparable, digest, ingest, load_records, validate
from broca.collect import refresh, load_snapshot
from broca.board import evidence_state, render


@pytest.fixture
def root(tmp_path):
    (tmp_path / 'assistants.json').write_text(json.dumps({'schema_version': 1, 'assistants': ['test_assistant'], 'evidence_max_age_days': 30}))
    (tmp_path / 'CHECKIN.md').write_text('Review evidence, not transcripts.')
    return tmp_path


@pytest.fixture
def record():
    return {'schema_version': 1, 'run_id': 'run-1', 'assistant': 'test_assistant',
            'kind': 'benchmark', 'observed_at': '2026-01-01', 'date_precision': 'day',
            'assistant_sha': 'a' * 40, 'benchmark': {'id': 'smoke', 'version': '1', 'sha256': 'b' * 64},
            'model': 'test-model', 'harness': 'test-harness',
            'environment': {'stack': {'test': '1'}, 'hardware': {'cpu': 'test'}, 'harness_version': '1', 'scorer_revision': 'c' * 40},
            'status': 'failed', 'metrics': {'score': 0, 'cost_usd': None}, 'reason': '<script>bad</script>',
            'source': {'revision': 'a' * 40, 'path': 'benchmarks/runs/test/meta.yaml', 'sha256': 'd' * 64}}


def test_immutable_idempotent_ingestion(root, record):
    assert ingest(root, record, ['test_assistant'])
    assert not ingest(root, record, ['test_assistant'])
    changed = copy.deepcopy(record); changed['metrics']['score'] = 99
    with pytest.raises(InvalidRecord, match='immutable'):
        ingest(root, changed, ['test_assistant'])
    assert load_records(root, ['test_assistant'])[0]['metrics']['score'] == 0


@pytest.mark.parametrize('key,value', [('run_id', '../escape'), ('assistant_sha', 'abcdef0'),
    ('observed_at', '2099-01-01'), ('metrics', {'score': float('nan')}),
    ('status', 'green'), ('assistant', 'private_assistant'), ('schema_version', True)])
def test_invalid_records(record, key, value):
    record[key] = value
    with pytest.raises((InvalidRecord, ValueError)):
        validate(record, ['test_assistant'])


def test_comparison_requires_full_matching_provenance(record):
    other = copy.deepcopy(record); other['assistant_sha'] = 'e' * 40
    assert comparable(record, other)
    other['environment']['harness_version'] = None
    assert not comparable(record, other)
    other = copy.deepcopy(record); other['benchmark']['version'] = '2'
    assert not comparable(record, other)


def test_unknown_and_current_evidence_are_distinct(record):
    assert evidence_state(None, {}, 30) == 'Never evaluated'
    assert evidence_state(record, {}, 30) == 'Recorded failure'
    record['status'] = 'passed'
    assert evidence_state(record, {}, 30) == 'Revision unknown'
    assert evidence_state(record, {'revision': 'b' * 40}, 30) == 'Changed since evaluation'
    assert evidence_state(record, {'revision': 'a' * 40}, 30) == 'Evidence outdated'


def setup_assistant(root):
    workspace = root / 'workspace'; repo = workspace / 'test_assistant'; repo.mkdir(parents=True)
    def git(*args):
        return subprocess.check_output(['git', '-C', str(repo), *args], text=True).strip()
    git('init', '-q'); git('config', 'user.email', 'test@example.invalid'); git('config', 'user.name', 'Test')
    for path in ['AGENTS.md', 'skills/test.md', 'autoassistant/benchmark.py', 'benchmarks/prompts/smoke.md']:
        target = repo / path; target.parent.mkdir(parents=True, exist_ok=True); target.write_text('fixture')
    git('add', '.'); git('commit', '-qm', 'fixture')
    mind = root / 'mind'; mind.mkdir()
    (mind / 'repos.yaml').write_text(yaml.safe_dump({'repos': {'test_assistant': {'path': 'test_assistant', 'category': 'assistant', 'github': 'example/test_assistant'}}}))
    return workspace, repo, mind, git


def test_refresh_missing_source_never_fresh(root):
    workspace, repo, mind, git = setup_assistant(root)
    result = refresh(root, workspace, mind, pilot=True)
    assert result['refreshed_at']
    assert load_snapshot(root) == result
    records = load_records(root, ['test_assistant'])
    assert len(records) == 1 and records[0]['kind'] == 'maintenance'
    repo.rename(repo.with_name('unavailable'))
    result = refresh(root, workspace, mind)
    assert result['refreshed_at'] is None
    assert result['assistants'][0]['status'] == 'unavailable'
    assert len(list((root / 'receipts').glob('*.json'))) == 2


def test_import_preserves_failures_and_retries_across_head_changes(root):
    workspace, repo, mind, git = setup_assistant(root)
    revision = git('rev-parse', 'HEAD')
    run = repo / 'benchmarks/runs/smoke/run1'; run.mkdir(parents=True)
    meta = {'benchmark': 'smoke', 'date': '2026-01-01', 'assistant_sha': revision[:7], 'prompt_version': 1,
            'prompt_sha256': 'b' * 64, 'model': 'model', 'harness': 'harness', 'score': 0}
    (run / 'meta.yaml').write_text(yaml.safe_dump(meta))
    (run / 'score.json').write_text(json.dumps({'score': 0, 'gates': [{'passed': False}], 'reason': 'budget exceeded'}))
    git('add', '.'); git('commit', '-qm', 'measurement')
    result = refresh(root, workspace, mind, import_history=True)
    assert result['assistants'][0]['imported'] == 1
    original = load_records(root, ['test_assistant'])[0]
    assert original['assistant_sha'] == revision and original['status'] == 'failed'
    (repo / 'unrelated').write_text('change'); git('add', '.'); git('commit', '-qm', 'unrelated')
    result = refresh(root, workspace, mind, import_history=True)
    assert result['assistants'][0]['imported'] == 0
    assert load_records(root, ['test_assistant'])[0] == original
    (run / 'score.json').write_text(json.dumps({'score': 100, 'gates': [{'passed': True}]}))
    git('add', '.'); git('commit', '-qm', 'conflicting rewrite')
    result = refresh(root, workspace, mind, import_history=True)
    assert result['refreshed_at'] is None
    assert result['assistants'][0]['status'] == 'partial'
    assert load_records(root, ['test_assistant'])[0] == original


def test_tampered_receipt_rejected(root):
    workspace, repo, mind, git = setup_assistant(root)
    refresh(root, workspace, mind)
    receipt = next((root / 'receipts').glob('*.json'))
    receipt.write_text('{}')
    with pytest.raises(InvalidRecord, match='digest'):
        load_snapshot(root)


def test_render_uses_shared_theme_and_escapes_evidence(root, record):
    brain = Path(__file__).resolve().parents[2] / 'PyAutoBrain'
    if not brain.exists():
        pytest.skip('Brain checkout required for renderer integration')
    ingest(root, record, ['test_assistant'])
    page = render(root, brain)
    assert 'PyAuto' in page and 'Broca' in page
    assert '<script>bad</script>' not in page
    assert '&lt;script&gt;bad&lt;/script&gt;' in page
    assert 'Copy check-in prompt' in page and 'Last updated unavailable' in page
    assert 'No comparable baseline' in page
    assert 'Update unavailable' in page
    assert page.index('class="orchestration') < page.index('class="board-nav"')


def test_legacy_rubric_total_keeps_unknown_pass_threshold(root):
    workspace, repo, mind, git = setup_assistant(root)
    run = repo / 'benchmarks/runs/rubric/one'; run.mkdir(parents=True)
    meta = {'benchmark': 'rubric', 'date': '2026-01-01', 'score': {'total': 13, 'machine': 3, 'judged': 10}}
    (run / 'meta.yaml').write_text(yaml.safe_dump(meta))
    git('add', '.'); git('commit', '-qm', 'legacy rubric')
    snapshot = refresh(root, workspace, mind, import_history=True)
    assert snapshot['refreshed_at']
    record = load_records(root, ['test_assistant'])[0]
    assert record['status'] == 'unscored' and record['metrics']['score'] == 13
    assert record['assistant_sha'] is None
    assert not comparable(record, record)


def test_precise_dates_and_paths_rejected(record):
    record['date_precision'] = 'second'
    for stamp in ['2026-01-01T12:00:00', '2026-01-01', '2026-99-01T12:00:00Z']:
        record['observed_at'] = stamp
        with pytest.raises(InvalidRecord):
            validate(record, ['test_assistant'])
    record['observed_at'] = '2026-01-01T12:00:00Z'
    validate(record, ['test_assistant'])
    record['source']['path'] = '../secret'
    with pytest.raises(InvalidRecord):
        validate(record, ['test_assistant'])


def test_same_day_history_does_not_invent_run_order(root, record):
    brain = Path(__file__).resolve().parents[2] / 'PyAutoBrain'
    if not brain.exists():
        pytest.skip('Brain checkout required for renderer integration')
    ingest(root, record, ['test_assistant'])
    other = copy.deepcopy(record)
    other.update(run_id='zzz-last-alphabetically', status='passed', reason=None)
    other['metrics']['score'] = 100
    ingest(root, other, ['test_assistant'])
    page = render(root, brain)
    assert 'Recorded failure' in page
    assert '+100 score points' not in page


def test_unknown_nested_environment_prevents_comparison(record):
    record['environment']['stack']['test'] = None
    assert not comparable(record, record)
