"""Local history tests: temporary files, fake Gemini responses, no real env files."""
import json

import pytest
from google.genai import types

from nexa.ai.conversation_history import ConversationHistory, MAX_BYTES, MAX_TEXT
from nexa.ai.gemini_provider import AIError, GeminiProvider
from nexa.core.safety import Cancelled, SafetyManager
from nexa.utils.config import Config
from nexa.utils.logging import REDACTED


@pytest.fixture(autouse=True)
def isolated_secrets(monkeypatch):
    for name in ("GEMINI_API_KEY", "TRIPO_API_KEY", "MESHY_API_KEY", "HF_TOKEN", "HUGGINGFACE_HUB_TOKEN"):
        monkeypatch.delenv(name, raising=False)


def response(text="reply", parts=None):
    return types.GenerateContentResponse(candidates=[types.Candidate(
        content=types.Content(role="model", parts=parts or [types.Part(text=text)]))])


def make_provider(config, tmp_path, monkeypatch, script=()):
    provider = GeminiProvider(config, history_path=tmp_path / "history.json")
    items = iter(script)

    def call(*args, **kwargs):
        item = next(items)
        if callable(item):
            item = item()
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(provider, "_call", call)
    return provider


def converse(provider, text="question", **kwargs):
    return provider.converse(text, [], lambda fc: {"ok": True, "message": "private tool output"},
                             SafetyManager().new_token(), **kwargs)


def test_disabled_never_reads_or_writes(config, tmp_path, monkeypatch):
    path = tmp_path / "history.json"
    path.write_text("private existing file", encoding="utf-8")
    monkeypatch.setattr(ConversationHistory, "load", lambda *a: pytest.fail("read while disabled"))
    monkeypatch.setattr(ConversationHistory, "save", lambda *a: pytest.fail("write while disabled"))
    p = make_provider(config, tmp_path, monkeypatch, [response()])
    converse(p)
    assert p.history_turns == 1
    assert path.read_text(encoding="utf-8") == "private existing file"
    p.clear_history()
    assert not path.exists()


def test_restart_restores_bounded_text_only(config, tmp_path, monkeypatch):
    config.update({"ai": {"persist_history": True, "max_history_turns": 2}})
    p = make_provider(config, tmp_path, monkeypatch, [response(str(i)) for i in range(3)])
    p.add_note("private internal note")
    for i in range(3):
        converse(p, "hello " + str(i), context="private window context\n")
        assert "private" not in (tmp_path / "history.json").read_text(encoding="utf-8")
    raw = (tmp_path / "history.json").read_text(encoding="utf-8")
    assert "private" not in raw
    q = make_provider(config, tmp_path, monkeypatch, [response("continued")])
    assert q.history_turns == 2
    assert [(c.role, c.parts[0].text) for c in q._history] == [
        ("user", "hello 1"), ("model", "1"), ("user", "hello 2"), ("model", "2")]
    converse(q)
    assert q.history_turns == 2
    q.clear_history()
    assert not (tmp_path / "history.json").exists()
    assert make_provider(config, tmp_path, monkeypatch).history_turns == 0


def test_tools_thoughts_and_secrets_not_saved(config, tmp_path, monkeypatch):
    config.set("ai.persist_history", True)
    key = "AIza" + "x" * 35
    monkeypatch.setenv("GEMINI_API_KEY", key)
    tool = response(parts=[types.Part(function_call=types.FunctionCall(name="tool", args={"secret": key}))])
    plain = response(parts=[types.Part(text="private reasoning", thought=True),
                            types.Part(text="answer " + key, thought_signature=b"private signature")])
    p = make_provider(config, tmp_path, monkeypatch, [tool, response("private tool answer"), plain])
    converse(p, "tool request")
    assert not (tmp_path / "history.json").exists()
    converse(p, "user " + key)
    raw = (tmp_path / "history.json").read_text(encoding="utf-8")
    assert key not in raw and "private" not in raw and "tool" not in raw
    assert REDACTED in raw


@pytest.mark.parametrize("result", [AIError("network", "failure"), Cancelled("cancel"),
                                   types.GenerateContentResponse()])
def test_failed_turn_not_saved(config, tmp_path, monkeypatch, result):
    config.set("ai.persist_history", True)
    p = make_provider(config, tmp_path, monkeypatch, [response(), result])
    converse(p)
    before = (tmp_path / "history.json").read_bytes()
    if isinstance(result, Exception):
        with pytest.raises(type(result)):
            converse(p, "failed")
    else:
        converse(p, "empty")
    assert (tmp_path / "history.json").read_bytes() == before
    assert p.history_turns == 1


def test_live_toggle_no_backfill_and_limit_reload(config, tmp_path, monkeypatch):
    p = make_provider(config, tmp_path, monkeypatch, [response() for _ in range(4)])
    converse(p, "private before opt in")
    config.update({"ai": {"persist_history": True}})
    converse(p, "saved one")
    converse(p, "saved two")
    config.update({"ai": {"max_history_turns": 1}})
    assert p._history_store.load(50) == [("saved two", "reply")]
    config.update({"ai": {"persist_history": False}})
    assert not p._history_store.path.exists()
    converse(p, "private after opt out")
    assert not p._history_store.path.exists()


@pytest.mark.parametrize("action", ["clear", "disable", "toggle"])
def test_inflight_cannot_recreate_deleted_history(config, tmp_path, monkeypatch, action):
    config.set("ai.persist_history", True)
    p = make_provider(config, tmp_path, monkeypatch)

    def during_call(*args):
        if action == "clear":
            p.clear_history()
        else:
            config.set("ai.persist_history", False)
            if action == "toggle":
                config.set("ai.persist_history", True)
        return response()

    monkeypatch.setattr(p, "_call", during_call)
    if action == "clear":
        with pytest.raises(Cancelled):
            converse(p)
        assert p.history_turns == 0
        assert not p._history
    else:
        converse(p)
    assert not p._history_store.path.exists()


@pytest.mark.parametrize("raw", [b"{", b"\xff", b"[]", b"null", b"{}", b"[" * 2000,
    b'{"version":true,"messages":[]}',
    b'{"version":1,"messages":[{"role":"model","text":"bad"}]}',
    b'{"version":1,"messages":[{"role":"user","text":"x","function_call":{}},{"role":"model","text":"y"}]}',
    b"x" * (MAX_BYTES + 1)], ids=["json", "encoding", "array", "null", "schema", "nesting",
                                "version", "odd", "tool-field", "oversized"])
def test_malformed_files_are_ignored(tmp_path, raw):
    path = tmp_path / "history.json"
    path.write_bytes(raw)
    assert ConversationHistory(path).load(12) == []


def test_byte_bounds_and_oversize_turns(tmp_path):
    store = ConversationHistory(tmp_path / "history.json")
    turns = [(str(i) + "界" * 8000, "reply") for i in range(50)]
    store.save(turns + [("x" * (MAX_TEXT + 1), "too large")], 50)
    assert store.path.stat().st_size <= MAX_BYTES
    restored = store.load(50)
    assert 0 < len(restored) < 50
    assert restored[-1] == turns[-1]


def test_atomic_failure_preserves_previous_file(config, tmp_path, monkeypatch, caplog):
    store = ConversationHistory(tmp_path / "history.json")
    store.save([("old", "reply")], 12)
    original = store.path.read_bytes()

    def fail(*args):
        raise PermissionError("do not log secret contents")

    monkeypatch.setattr("nexa.ai.conversation_history.os.replace", fail)
    store.save([("new", "reply")], 12)
    assert store.path.read_bytes() == original
    assert list(tmp_path.glob("*.tmp")) == []
    assert "secret contents" not in caplog.text


def test_unreadable_unwritable_and_delete_error(tmp_path, monkeypatch, caplog):
    path = tmp_path / "directory"
    path.mkdir()
    store = ConversationHistory(path)
    assert store.load(12) == []
    store.save([("user", "model")], 12)
    store.delete()
    assert path.is_dir()
    assert caplog.records


@pytest.mark.parametrize("value", ["false", "true", 1, None, [], {}])
def test_opt_in_requires_boolean_on_load_and_update(config, tmp_path, value):
    config.update({"ai": {"persist_history": value, "max_history_turns": "bad"}})
    assert config.get("ai.persist_history") is False
    assert config.get("ai.max_history_turns") == 12
    path = tmp_path / "invalid.json.yaml"
    path.write_text(json.dumps({"ai": {"persist_history": value}}), encoding="utf-8")
    loaded = Config(path, tmp_path / "gestures-empty.yaml", load_env=False)
    assert loaded.get("ai.persist_history") is False
    assert loaded.config_warnings


def test_setting_survives_config_save_reload(config, tmp_path):
    config.set("ai.persist_history", True)
    config.save()
    loaded = Config(config.settings_path, config.gestures_path, load_env=False)
    assert loaded.get("ai.persist_history") is True


def test_validation_preserves_other_section_warnings(config):
    config.update({"three_d": {"refinement_rounds": 7}})
    warnings = list(config.config_warnings)
    config.set("ai.persist_history", "false")
    assert all(w in config.config_warnings for w in warnings)
    config.update({"ai": {"persist_history": True}})
    assert config.config_warnings == warnings
    config.update({"ai": {"persist_history": "bad"}, "three_d": {"refinement_rounds": 7}})
    assert any(w.startswith("ai.") for w in config.config_warnings)
    assert any(w.startswith("three_d.") for w in config.config_warnings)


def test_production_and_explicit_paths(config, tmp_path, monkeypatch):
    from nexa.utils import config as config_module
    monkeypatch.setattr(config_module, "LOCAL_DATA_DIR", tmp_path / "local-data")
    assert GeminiProvider(config)._history_store.path == tmp_path / "conversation_history.json"
    config.settings_path = config_module.CONFIG_DIR / "settings.yaml"
    assert GeminiProvider(config)._history_store.path == tmp_path / "local-data" / "conversation_history.json"
    assert GeminiProvider(config, state_path=tmp_path / "state" / "model.json")._history_store.path == (
        tmp_path / "state" / "conversation_history.json")
    explicit = tmp_path / "explicit.json"
    assert GeminiProvider(config, history_path=explicit)._history_store.path == explicit


def test_non_text_model_parts_not_saved(config, tmp_path, monkeypatch):
    config.set("ai.persist_history", True)
    reply = response(parts=[types.Part(text="text"), types.Part.from_bytes(data=b"image", mime_type="image/png")])
    p = make_provider(config, tmp_path, monkeypatch, [reply])
    converse(p)
    assert not p._history_store.path.exists()
