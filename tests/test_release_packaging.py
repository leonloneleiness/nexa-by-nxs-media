"""Release regressions: offline model completeness and active-provider configuration."""
from pathlib import Path
import importlib.util

import pytest

spec = importlib.util.spec_from_file_location('prepare_release',
    Path(__file__).parents[1] / 'scripts' / 'prepare_windows_release.py')
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


def test_openai_release_includes_active_provider_credentials_only_from_allowlist():
    result = release.shared_api_values({'NEXA_AI_PROVIDER': 'openai', 'OPENAI_API_KEY': 'test-key',
        'OPENAI_BASE_URL': 'https://example.com/v1', 'OPENAI_MODEL': 'test-model',
        'WINDOWS_PASSWORD': 'private', 'TRIPO_API_KEY': 'YOUR_TRIPO_API_KEY'})
    assert result['OPENAI_API_KEY'] == 'test-key'
    assert result['OPENAI_MODEL'] == 'test-model'
    assert 'WINDOWS_PASSWORD' not in result and 'TRIPO_API_KEY' not in result


def test_gemini_release_does_not_distribute_inactive_openai_credentials():
    result = release.shared_api_values({'NEXA_AI_PROVIDER': 'gemini', 'GEMINI_API_KEY': 'gemini-key',
        'OPENAI_API_KEY': 'openai-key', 'OPENAI_BASE_URL': 'https://example.com/v1',
        'OPENAI_MODEL': 'private-model'})
    assert result['GEMINI_API_KEY'] == 'gemini-key'
    assert 'OPENAI_API_KEY' not in result and 'OPENAI_BASE_URL' not in result and 'OPENAI_MODEL' not in result


def test_missing_active_provider_key_rejects_build_even_when_gemini_is_configured():
    with pytest.raises(ValueError, match='OPENAI_API_KEY'):
        release.shared_api_values({'NEXA_AI_PROVIDER': 'openai', 'GEMINI_API_KEY': 'test-key'})


def test_release_provider_override_does_not_change_developer_settings():
    values = {'NEXA_AI_PROVIDER': 'openai', 'GEMINI_API_KEY': 'test-key'}
    assert release.shared_api_values(values, 'gemini')['NEXA_AI_PROVIDER'] == 'gemini'
    assert values['NEXA_AI_PROVIDER'] == 'openai'


def test_partial_whisper_cache_rejects_release(tmp_path):
    model = tmp_path / 'models/whisper/models--Systran--faster-whisper-small'
    (model / 'refs').mkdir(parents=True)
    (model / 'refs/main').write_text('snapshot', encoding='utf-8')
    (model / 'snapshots/snapshot').mkdir(parents=True)
    (model / 'snapshots/snapshot/model.bin').write_bytes(b'present')
    result = release.validate_payload(tmp_path)
    assert not result['ok']
    assert any('tokenizer.json' in error for error in result['errors'])
    assert any('large-v3-turbo' in error for error in result['errors'])
    assert any('NexaBridge.exe' in error for error in result['errors'])


@pytest.mark.parametrize('kind', ['hand', 'face'])
def test_landmark_models_run_from_vietnamese_install_path(tmp_path, kind):
    import shutil
    import numpy as np
    from nexa.vision.hand_tracker import HandTracker
    from nexa.vision.face_tracker import FaceTracker

    source = Path(__file__).parents[1] / 'models' / f'{kind}_landmarker.task'
    if not source.is_file():
        pytest.skip('Release model not downloaded on this development machine')
    target = tmp_path / 'Người dùng thử nghiệm' / source.name
    target.parent.mkdir()
    shutil.copy2(source, target)
    tracker = (HandTracker if kind == 'hand' else FaceTracker)(target)
    try:
        assert tracker.detect(np.zeros((128, 128, 3), np.uint8), 1) == []
    finally:
        tracker.close()
