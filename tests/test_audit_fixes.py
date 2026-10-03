"""Regression cases from the October project audit; never use real providers."""
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest

from nexa.core.safety import Cancelled, CancelToken
from nexa.three_d.generation.base import ProviderError
from nexa.three_d.generation.http import HttpClient, retry_delay
from nexa.three_d.generation.parametric import compile_dsl_parts
from nexa.three_d.spec import ModelSpec


def client(handler):
    return HttpClient('https://audit.invalid', 'fake', factory=lambda **kw:
                      httpx.Client(transport=httpx.MockTransport(handler), **kw))


@pytest.mark.parametrize('method', ['POST', 'PATCH', 'PUT', 'DELETE'])
def test_mutation_not_replayed_after_lost_response(method):
    calls = []
    def handler(req):
        calls.append(req)
        raise httpx.ReadTimeout('response lost', request=req)
    c = client(handler)
    try:
        with pytest.raises(ProviderError) as err:
            c.request(method, '/task', json_body={'prompt': 'box'})
        assert err.value.kind == 'submission_unknown'
        assert not err.value.retryable and len(calls) == 1
    finally:
        c.close()


def test_post_server_error_not_replayed():
    requests = []
    c = client(lambda req: (requests.append(req), httpx.Response(503))[1])
    try:
        assert c.request('POST', '/task').status_code == 503
        assert len(requests) == 1
    finally:
        c.close()


def test_status_read_retries_http_date(monkeypatch):
    responses = iter([httpx.Response(429, headers={'Retry-After': 'Wed, 21 Oct 2026 07:28:00 GMT'}),
                      httpx.Response(200, json={'done': True})])
    waits = []
    monkeypatch.setattr('nexa.three_d.generation.http.time.sleep', waits.append)
    c = client(lambda req: next(responses))
    try:
        assert c.request('GET', '/task').json()['done']
        assert len(waits) == 1 and 0 <= waits[0] <= 8
    finally:
        c.close()


@pytest.mark.parametrize('header', ['', 'not-a-date', 'nan', 'inf'])
def test_invalid_retry_header_falls_back(header):
    assert retry_delay(header, 0) == 1.5


def test_collision_of_generated_dsl_id_terminates():
    base = 'a' * 36
    ids = [base, base + '_2', base, base]
    parts = [{'id': pid, 'name_vi': 'box', 'shape': {'op': 'box', 'size': [5, 5, 5]}} for pid in ids]
    result = compile_dsl_parts(ModelSpec(category='generic'), parts)
    assert len(set(result.compiled)) == 4 and not result.errors
    assert all(len(pid) <= 40 for pid in result.compiled)


def test_cancellation_inside_dsl_tree_not_swallowed():
    n = 0
    def check():
        nonlocal n
        n += 1
        if n >= 4:
            raise Cancelled('stop')
    parts = [{'id': 'a', 'name_vi': 'box', 'shape': {'op': 'union', 'children': [
        {'op': 'box', 'size': [5, 5, 5]}, {'op': 'box', 'size': [6, 6, 6]}]}}]
    with pytest.raises(Cancelled):
        compile_dsl_parts(ModelSpec(category='generic'), parts, tolerant=True, check=check)


def test_parametric_ui_preserves_structured_options():
    from nexa.ui.three_d_bridge import ThreeDBridge
    svc = SimpleNamespace(submit=Mock())
    fake = SimpleNamespace(svc=svc, toast=SimpleNamespace(emit=Mock()))
    ThreeDBridge.generate(fake, '  con mèo  ', 'parametric', 'high')
    svc.submit.assert_called_once_with('con mèo', mode='parametric', quality='high', source='keyboard')


def test_ui_displays_service_rejection():
    from nexa.ui.three_d_bridge import ThreeDBridge
    fake = SimpleNamespace(svc=SimpleNamespace(submit=Mock(side_effect=RuntimeError('locked'))),
                           toast=SimpleNamespace(emit=Mock()))
    ThreeDBridge.generate(fake, 'box', 'parametric', 'high')
    fake.toast.emit.assert_called_once_with('locked', True)


def test_parametric_unknown_category_never_uses_ai(config, tmp_path):
    from nexa.three_d.asset_store import AssetStore
    from nexa.three_d.pipeline import GenerationPipeline
    from nexa.three_d.planner import Planner
    from nexa.three_d.job_manager import Job, JobContext, JobFailed
    ai = Mock()
    provider = Mock()
    p = GenerationPipeline(config, AssetStore(tmp_path / 'cache'), Planner(ai), ai, provider_factory=provider)
    j = Job(id='audit-local', prompt='Tạo mô hình 3D con mèo', mode='parametric', token=CancelToken(None, 0))
    manager = SimpleNamespace(_update=lambda *args, **kwargs: None)
    with pytest.raises(JobFailed) as e:
        p.run(j, JobContext(manager, j))
    assert e.value.code == 'unsupported'
    assert not ai.mock_calls and not provider.mock_calls


def test_parametric_followup_preserves_mode():
    from nexa.three_d.intents import route_3d
    from nexa.utils.text import fold
    prompt = 'Tạo bu lông M8 bằng CAD tham số chất lượng cao, dài 30 mm'
    routed = route_3d(prompt, fold(prompt), False)
    assert routed[1][0][1]['mode'] == 'parametric'
    assert routed[1][0][1]['quality'] == 'high'


def test_all_registered_dynamic_templates_in_build():
    import importlib
    from scripts.build_exe import THREE_D_MODULES
    from nexa.three_d.generation.templates import TECH_TEMPLATES
    for module in set(TECH_TEMPLATES.values()):
        name = f'nexa.three_d.generation.templates.{module}'
        assert name in THREE_D_MODULES
        assert callable(importlib.import_module(name).build)


def test_build_does_not_collect_dlls_from_unrelated_tools(monkeypatch):
    from scripts.build_exe import build_environment
    monkeypatch.setenv('PATH', r'C:\foreign\poppler\bin')
    monkeypatch.setenv('QT_PLUGIN_PATH', r'C:\foreign\qt')
    monkeypatch.setenv('PYTHONPATH', r'C:\foreign\python')
    env = build_environment()
    assert 'foreign' not in env['PATH']
    assert 'QT_PLUGIN_PATH' not in env and 'PYTHONPATH' not in env
    assert 'System32' in env['PATH'] and env['PYTHONUTF8'] == '1'
