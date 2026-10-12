"""Exercise the emitted bundle and the workflow's actual artifact guard."""
import json
import os
from pathlib import Path
import subprocess

import pytest
import yaml

from broca.__main__ import main
from broca.publication import apply, prepare
from broca.state import shared_contract, UNKNOWN_TIME

BRAIN = Path(__file__).resolve().parents[2] / "PyAutoBrain"


@pytest.fixture
def instance(tmp_path):
    root = tmp_path / 'data'
    repos = tmp_path / 'repos.yaml'
    repos.write_text('repos:\n  guides:\n    github: Research/IndependentGuides\n')
    assert main(['--root', str(root), 'setup', '--repos', str(repos), '--repo', 'guides',
                 '--pages-url', 'https://research.example/guides/', '--brain', str(BRAIN), '--apply']) == 0
    (root / 'private.txt').write_text('PRIVATE-MARKER')
    return root, repos, tmp_path / 'publication'


def command(instance):
    root, repos, output = instance
    return ['--root', str(root), 'publication', '--repos', str(repos), '--repo', 'guides',
            '--pages-url', 'https://research.example/guides/', '--brain', str(BRAIN),
            '--output', str(output), '--branch', 'trunk']


def snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}


def run_guard(output, repository='Research/IndependentGuides'):
    workflow = yaml.safe_load((output / '.github/workflows/pages.yml').read_text())
    step = next(s for s in workflow['jobs']['build']['steps'] if 'run' in s)
    return subprocess.run(['bash', '-c', step['run']], cwd=output,
                          env={**os.environ, 'GITHUB_REPOSITORY': repository}, capture_output=True, text=True)


def test_bundle_preserves_source_and_uses_independent_identity(instance):
    root, _, output = instance
    before = snapshot(root)
    assert main(command(instance)) == 0
    assert not output.exists()
    assert main(command(instance) + ['--apply']) == 0
    assert snapshot(root) == before
    files = snapshot(output)
    assert set(files) == {'site/index.html', 'site/state.json', '.github/workflows/pages.yml'}
    assert all(b'PRIVATE-MARKER' not in b and str(root).encode() not in b for b in files.values())
    page = files['site/index.html'].decode()
    assert 'https://github.com/Research/IndependentGuides' in page
    assert 'https://github.com/PyAutoLabs/PyAutoBroca' not in page
    state = json.loads(files['site/state.json'])
    assert shared_contract(BRAIN).validate_state(state) == []
    assert state['repo'] == 'IndependentGuides'
    assert state['updated'] == UNKNOWN_TIME and state['status'] == 'grey'
    assert run_guard(output).returncode == 0
    assert run_guard(output, 'Research/Wrong').returncode != 0
    assert main(command(instance) + ['--apply']) == 2
    assert snapshot(output) == files


def test_workflow_has_narrow_upload_and_deployment_guard(instance):
    assert main(command(instance) + ['--apply']) == 0
    output = instance[2]
    wf = yaml.safe_load((output / '.github/workflows/pages.yml').read_text())
    assert wf['on']['push']['branches'] == ['trunk']
    assert set(wf['on']) == {'push', 'pull_request', 'workflow_dispatch'}
    assert wf['permissions'] == {'contents': 'read'}
    build = wf['jobs']['build']
    assert build['steps'][-1]['with']['path'] == 'site'
    assert build['steps'][0] == {'uses': 'actions/checkout@v4'}
    deploy = wf['jobs']['deploy']
    assert deploy['needs'] == 'build'
    assert deploy['if'] == "github.ref == 'refs/heads/trunk' && github.event_name != 'pull_request'"
    assert deploy['permissions'] == {'pages': 'write', 'id-token': 'write'}


@pytest.mark.parametrize('tamper', ['extra', 'symlink', 'directory', 'identity', 'missing'])
def test_generated_guard_rejects_bad_artifacts(instance, tamper):
    assert main(command(instance) + ['--apply']) == 0
    output = instance[2]; site = output / 'site'
    if tamper == 'extra':
        (site / 'private.txt').write_text('private')
    elif tamper in ('symlink', 'directory', 'missing'):
        (site / 'index.html').unlink()
        if tamper == 'symlink':
            (site / 'index.html').symlink_to(instance[0] / 'private.txt')
        elif tamper == 'directory':
            (site / 'index.html').mkdir()
    else:
        state = json.loads((site / 'state.json').read_text()); state['repo'] = 'Wrong'
        (site / 'state.json').write_text(json.dumps(state))
    assert run_guard(output).returncode != 0


@pytest.mark.parametrize('bad', ['repo', 'url', 'branch', 'evidence', 'symlink', 'inside', 'map'])
def test_invalid_inputs_write_nothing(instance, bad, tmp_path):
    root, repos, output = instance; argv = command(instance)
    if bad in ('repo', 'url', 'branch'):
        flag, value = {'repo': ('--repo', 'missing'), 'url': ('--pages-url', 'http://bad'),
                       'branch': ('--branch', "main' || true")}[bad]
        argv[argv.index(flag)+1] = value
    elif bad == 'evidence':
        (root / 'latest.json').write_text('{"receipt":"invalid"}')
    elif bad == 'symlink':
        output.symlink_to(tmp_path / 'missing')
    elif bad == 'inside':
        argv[argv.index('--output')+1] = str(root / 'publication')
    else:
        repos.write_text('repos: []')
    before = snapshot(root)
    assert main(argv + ['--apply']) == 2
    assert snapshot(root) == before
    assert not output.exists()


def test_racing_destination_is_preserved(instance):
    root, repos, output = instance
    prepared = prepare(root, repos, 'guides', 'https://research.example/guides/', BRAIN, output)
    output.mkdir(); (output / 'keep').write_text('existing')
    with pytest.raises(FileExistsError):
        apply(prepared)
    assert snapshot(output) == {'keep': b'existing'}
