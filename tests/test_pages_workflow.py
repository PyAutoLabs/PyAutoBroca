"""Publication must not expose the checkout or mutate evaluation evidence."""
from pathlib import Path
import yaml


def test_pages_publishes_only_rendered_snapshot_with_guarded_deployment():
    root = Path(__file__).resolve().parents[1]
    workflow = yaml.safe_load((root / '.github/workflows/pages.yml').read_text())
    triggers = workflow.get('on', workflow.get(True))
    assert set(triggers) == {'push', 'pull_request', 'workflow_dispatch'}
    assert triggers['push']['branches'] == ['main']
    build = workflow['jobs']['build']
    commands = '\n'.join(step.get('run', '') for step in build['steps'])
    assert 'broca --root PyAutoBroca check' in commands
    assert 'render --brain PyAutoBrain --output site/index.html' in commands
    assert 'refresh' not in commands and '--pilot' not in commands
    upload = next(step for step in build['steps'] if step.get('uses', '').startswith('actions/upload-pages-artifact@'))
    assert upload['with']['path'] == 'site'
    deploy = workflow['jobs']['deploy']
    assert deploy['needs'] == 'build'
    assert "github.ref == 'refs/heads/main'" in deploy['if']
    assert "github.event_name != 'pull_request'" in deploy['if']
    assert deploy['permissions'] == {'pages': 'write', 'id-token': 'write'}
    assert workflow['permissions'] == {'contents': 'read'}
    assert deploy['environment']['name'] == 'github-pages'
