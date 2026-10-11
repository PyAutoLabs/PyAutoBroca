import json
from broca.resources import render


def catalogue(tmp_path):
    data = {'schema_version': 1, 'resources': [{'id': 'guide', 'name': 'HowToExample',
        'repo': 'guide', 'github': 'Example/Guide', 'relations': ['tutorials', 'documentation'],
        'projects': [{'id': 'one', 'name': 'One'}, {'id': 'two', 'name': 'Two'}],
        'links': [{'label': 'Source', 'url': 'https://github.com/Example/Guide'}]}]}
    (tmp_path / 'resources.json').write_text(json.dumps(data))
    return data


def test_tutorial_without_assistant_is_first_class_and_shared(tmp_path):
    catalogue(tmp_path)
    page = render(tmp_path, {})
    assert page.count('id="resource-guide"') == 1
    assert 'One, Two' in page and 'quality not evaluated' in page
    assert 'Tutorials' in page and 'Documentation' in page
    assert 'technical' in page.lower()


def test_assistant_evidence_requires_exact_canonical_remote(tmp_path):
    data = catalogue(tmp_path); data['resources'][0]['relations'] = ['assistants']
    (tmp_path / 'resources.json').write_text(json.dumps(data))
    evidence = {'github': 'Elsewhere/Guide', 'state': 'Recorded pass'}
    assert 'Recorded pass' not in render(tmp_path, {'guide': evidence})
    evidence.update(github='Example/Guide', collection='collected', collected_at='2026-01-01', revision='abc', observed_at='2026-01-01')
    assert 'Recorded pass' in render(tmp_path, {'guide': evidence})


def test_missing_and_unsafe_inventory(tmp_path):
    assert 'unavailable' in render(tmp_path, {})
    data = catalogue(tmp_path)
    data['resources'][0]['links'][0]['url'] = 'javascript:alert(1)'
    (tmp_path / 'resources.json').write_text(json.dumps(data))
    assert 'javascript:' not in render(tmp_path, {})
