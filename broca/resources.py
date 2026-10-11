"""Communication inventory projected from Scientist; never a quality verdict."""
import html
import json
from pathlib import Path
from urllib.parse import urlsplit

TYPES = {'workspaces': 'Workspaces', 'tutorials': 'How To', 'documentation': 'Documentation'}
PURPOSE = {'documentation': 'Reference and explanations for using the software.',
           'tutorials': 'Guided learning: start with the tutorial introduction.',
           'workspaces': 'Runnable user examples: start with its README and setup guidance.',
           'assistants': 'A project-owned assistant: read its scope and setup instructions.'}


def link(url, label):
    parsed = urlsplit(str(url))
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        return html.escape(str(label))
    return f'<a href="{html.escape(str(url), quote=True)}">{html.escape(str(label))}</a>'


def render(root, assistant_evidence):
    path = Path(root) / 'resources.json'
    if not path.is_file():
        return '<section id="communication"><h2>Guides &amp; Workspaces</h2><p>Public resource inventory unavailable.</p></section>'
    catalogue = json.loads(path.read_text())
    if catalogue.get('schema_version') != 1 or not isinstance(catalogue.get('resources'), list):
        raise ValueError('invalid public resource catalogue')
    esc = lambda value: html.escape(str(value), quote=True)
    cards = {kind: [] for kind in TYPES}
    for resource in catalogue['resources']:
        kinds = [k for k in TYPES if k in resource.get('relations', [])]
        if not kinds or 'assistants' in resource.get('relations', []):
            continue
        state = 'Inventory only — quality not evaluated'
        projects = ', '.join(p['name'] for p in resource['projects'])
        links = ' · '.join(link(l['url'], l['label']) for l in resource['links'])
        details = '<p>Revision, collection time and upkeep evidence: unavailable for this resource.</p>'
        cards[kinds[0]].append(f'''<details id="resource-{esc(resource['id'])}"><summary>{esc(resource['name'])} · {esc(' / '.join(TYPES[k] for k in kinds))} · {esc(projects)} · {esc(state)}</summary>
<p>{esc(' '.join(PURPOSE[k] for k in kinds))}</p><p>{links}</p>
<p>Used by: {esc(projects)}. Shared resources retain one identity; no assistant is required.</p>{details}
<p>Technical validation belongs to Heart. A successful build or runnable example does not establish explanatory quality or scientific correctness.</p>
<p>Next: inspect this resource's introduction, intended audience and known gaps with Broca before proposing a bounded documentation or evaluation task.</p></details>''')
    return ('<section id="communication"><h2>Guides &amp; Workspaces</h2>'
            + ''.join(f'<details id="communication-{kind}"><summary>{TYPES[kind]}</summary><div class="communication-resource-list">' + ''.join(rows) + '</div></details>' for kind, rows in cards.items() if rows) + ('' if any(cards.values()) else '<p>No public communication resources configured.</p>') + '</section>')


def assistant_anchors(root, name, github):
    path = Path(root) / 'resources.json'
    if not path.is_file():
        return ''
    resources = json.loads(path.read_text())['resources']
    return ''.join('<span id="resource-' + html.escape(r['id'], quote=True) + '"></span>'
                   for r in resources if 'assistants' in r.get('relations', [])
                   and r.get('repo') == name and r.get('github') == github)
