"""Nghiên cứu nhận dạng lệnh nói lẫn Việt–Anh: gợi ý ngữ cảnh, chỉ số đánh giá, thu dữ liệu, câu mẫu."""
from __future__ import annotations

import numpy as np
import pytest

from nexa.ai.intent_router import IntentRouter
from nexa.audio.context_bias import ContextBias, merge_terms, terms_from_windows, title_vocabulary
from nexa.audio.stt import INITIAL_PROMPT, SpeechRecognizer, SttResult
from nexa.research import asr_metrics as M
from nexa.research.corpus import CorpusRecorder, read_jsonl, read_wav, write_wav
from nexa.research.templates import ENTITIES, build_items


# ----- gợi ý ngữ cảnh -----
def test_terms_from_windows_uses_process_and_known_titles_only():
    windows = [("Code.exe", "stt.py - NEXA - Visual Studio Code"),
               ("msedge.exe", "ChatGPT - Hợp đồng bí mật với khách hàng - Microsoft Edge"),
               ("Zalo.exe", "Zalo"), ("explorer.exe", "Downloads"),
               ("msedge.exe", "Google Drive - Microsoft Edge")]
    terms = terms_from_windows(windows, title_vocabulary())
    assert terms[:2] == ["VS Code", "Visual Studio Code"]         # cửa sổ trên cùng trước
    assert "ChatGPT" in terms and "Zalo" in terms and "Edge" in terms
    assert "Google Drive" in terms and "Google" not in terms       # khớp dài nhất, không tách "Google"
    joined = " ".join(terms).lower()
    assert "hợp đồng" not in joined and "downloads" not in joined  # chữ tự do trong tiêu đề không lọt vào gợi ý


def test_merge_terms_context_first_no_duplicates():
    assert merge_terms(["Zalo", "Word"], ["Nexa", "Zalo", "YouTube"], 4) == ["Zalo", "Word", "Nexa", "YouTube"]


def test_context_bias_refresh_and_error_keeps_old(config):
    calls = {"n": 0}

    def provider():
        calls["n"] += 1
        if calls["n"] > 1:
            raise OSError("EnumWindows lỗi")
        return [("Zalo.exe", "Zalo")]

    bias = ContextBias(config, provider)
    assert bias.refresh() == ["Zalo"]
    assert bias.refresh() == ["Zalo"]                 # lỗi → giữ danh sách cũ
    assert bias.context_terms() == ["Zalo"]


def test_context_bias_async_respects_mode_and_ttl(config):
    import time
    seen = []
    bias = ContextBias(config, lambda: seen.append(1) or [("Zalo.exe", "Zalo")], ttl_s=60)
    config.set("stt.bias_mode", "static")
    bias.refresh_async()
    time.sleep(0.05)
    assert seen == []                                  # static: không đọc cửa sổ
    config.set("stt.bias_mode", "context")
    bias.refresh_async()
    for _ in range(50):
        if bias.context_terms():
            break
        time.sleep(0.01)
    bias.refresh_async()                               # trong TTL: không đọc lại
    time.sleep(0.05)
    assert bias.context_terms() == ["Zalo"] and len(seen) == 1


class _FakeSeg:
    def __init__(self, text):
        self.text, self.avg_logprob, self.no_speech_prob = text, -0.2, 0.01


class _FakeModel:
    def __init__(self):
        self.kwargs = None

    def transcribe(self, audio, **kw):
        self.kwargs = kw
        return iter([_FakeSeg("mở Zalo")]), None


@pytest.mark.parametrize("mode,has_prompt", [("none", False), ("static", True), ("context", True)])
def test_stt_prompt_by_bias_mode(config, tmp_path, mode, has_prompt):
    config.set("stt.bias_mode", mode)
    bias = ContextBias(config, lambda: [("Discord.exe", "Discord")])
    bias.refresh()
    rec = SpeechRecognizer(config, tmp_path, bias=bias)
    rec._model = _FakeModel()
    res = rec.transcribe(np.full(16000, 0.5, np.float32))
    kw = rec._model.kwargs
    assert res.ok and res.text == "mở Zalo" and res.bias_mode == mode
    assert (kw["initial_prompt"] == INITIAL_PROMPT) is has_prompt
    if mode == "none":
        assert kw["hotwords"] is None and res.context_terms == ()
    elif mode == "static":
        assert not kw["hotwords"].startswith("Discord") and res.context_terms == ()
    else:
        assert kw["hotwords"].startswith("Discord, ") and res.context_terms == ("Discord",)


@pytest.mark.parametrize("text", ["Các bạn hãy đăng kí cho kênh lalaschool Để không bỏ lỡ những video hấp dẫn",
                                  "Hãy đăng ký cho kênh để ủng hộ"])
def test_stt_rejects_subscribe_hallucination_found_by_benchmark(config, tmp_path, text):
    rec = SpeechRecognizer(config, tmp_path)
    rec._model = _FakeModel()
    rec._model.transcribe = lambda audio, **kw: (iter([_FakeSeg(text)]), None)
    res = rec.transcribe(np.full(16000, 0.5, np.float32))
    assert not res.ok and "tự sinh" in res.reason


def test_stt_explicit_context_overrides_machine(config, tmp_path):
    config.set("stt.bias_mode", "context")
    rec = SpeechRecognizer(config, tmp_path, bias=ContextBias(config, lambda: [("Zalo.exe", "Zalo")]))
    rec._model = _FakeModel()
    res = rec.transcribe(np.full(16000, 0.5, np.float32), context=["Canva"])
    assert rec._model.kwargs["hotwords"].startswith("Canva, ") and res.context_terms == ("Canva",)


# ----- chỉ số -----
def test_wer_keeps_tones_and_ignores_case_punct():
    assert M.word_errors("Mở YouTube.", "mở youtube") == (0, 2)
    assert M.word_errors("mở YouTube", "mơ YouTube") == (1, 2)
    assert M.word_errors("mở VS Code", "mở vi ét cốt") == (3, 3)


def test_entities_aliases_and_longest_match():
    assert M.entities("mở Visual Studio Code rồi mở VS Code") == ["Visual Studio Code", "Visual Studio Code"]
    assert M.entities("mở Google Drive") == ["Google Drive"]
    assert M.entities("bật wifi") == M.entities("bật Wi-Fi") == ["Wi-Fi"]
    assert M.entity_hits("mở VS Code", "mở Visual Studio Code") == (1, 1)
    assert M.entity_hits("mở VS Code", "mở VS Của") == (0, 1)
    assert M.entity_hits("chụp màn hình", "chụp màn hình") == (0, 0)


def test_command_match():
    r = IntentRouter()
    assert M.command_match(r, "mở VS Code", "mở vi ét cốt") is True       # bảng sửa phiên âm cứu được
    assert M.command_match(r, "đóng Zalo", "đóng da lô") is True
    assert M.command_match(r, "mở YouTube", "mở Discord") is False
    assert M.command_match(r, "viết giúp anh bài thơ", "viết giúp anh bài thơ") is None   # câu cho Gemini: không chấm


def test_summarize_and_tests():
    good = M.Score(0, 3, 0, 9, 1, 1, True, 0.2)
    bad = M.Score(2, 3, 5, 9, 0, 1, False, 0.4)
    s = M.summarize([good, bad])
    assert s["wer"] == pytest.approx(2 / 6) and s["entity_error_rate"] == 0.5 and s["command_success"] == 0.5
    a, b = [bad] * 20, [good] * 20
    boot = M.paired_bootstrap_wer(a, b, n=200)
    assert boot["delta"] == pytest.approx(-2 / 3) and boot["ci_high"] < 0 and boot["p"] < 0.05
    mc = M.mcnemar_exact([x.command_ok for x in a], [x.command_ok for x in b])
    assert mc["b_only"] == 20 and mc["p"] < 0.001
    assert M.mcnemar_exact([True, None], [True, False])["p"] == 1.0


# ----- thu dữ liệu -----
def _res(text="mở Zalo", ok=True):
    return SttResult(text, ok, "" if ok else "Quá ngắn", 1.0, 0.1, -0.3, 0.01, bias_mode="context",
                     context_terms=("Zalo",))


def test_corpus_disabled_by_default(config, tmp_path):
    rec = CorpusRecorder(config, tmp_path / "c")
    assert rec.record(np.zeros(16000, np.float32), 16000, _res()) is None
    assert not (tmp_path / "c").exists()


def test_corpus_records_wav_and_jsonl(config, tmp_path):
    config.set("research.record_corpus", True)
    config.set("research.max_items", 2)
    rec = CorpusRecorder(config, tmp_path / "c")
    audio = (np.sin(np.linspace(0, 200, 16000)) * 0.5).astype(np.float32)
    assert rec.record(audio, 16000, _res(), route_kind="basic", normalized="mở Zalo", model="small · CPU")
    assert rec.record(audio, 16000, _res("", ok=False))
    assert rec.record(audio, 16000, _res()) is None                # đủ max_items
    rows = read_jsonl(tmp_path / "c" / "utterances.jsonl")
    assert len(rows) == 2 and rows[0]["route"] == "basic" and rows[0]["context"] == ["Zalo"]
    assert rows[0]["reference"] == "" and rows[1]["ok"] is False
    back, sr = read_wav(tmp_path / "c" / rows[0]["audio"])
    assert sr == 16000 and back.size == 16000 and np.max(np.abs(back - audio)) < 1e-3


def test_wav_roundtrip(tmp_path):
    x = np.linspace(-1, 1, 800, dtype=np.float32)
    write_wav(tmp_path / "a.wav", x)
    y, sr = read_wav(tmp_path / "a.wav")
    assert sr == 16000 and np.allclose(x, y, atol=1e-4)


# ----- câu mẫu tổng hợp -----
def test_templates_references_are_orthographic_and_context_realistic():
    items = build_items()
    assert len({i["id"] for i in items}) == len(items)
    viet = [i for i in items if i["style"] == "viet"]
    assert viet and all(i["spoken"] != i["reference"] for i in viet if i["group"] != "plain")
    for i in items:
        for orth, variants in ENTITIES.values():
            for v in variants:
                assert f" {v} " not in f" {i['reference']} "             # đáp án không bao giờ là phiên âm
        if i["group"] == "open":
            assert i["target"] not in i["context"]                        # "mở X": X chưa mở
        if i["group"] in ("close", "tab", "search"):
            assert i["target"] in i["context"]


def test_template_references_route_to_local_commands():
    r = IntentRouter()
    local = [i for i in build_items() if i["group"] in ("open", "close", "tab", "search", "file", "folder", "zalo")]
    kinds = {i["reference"]: r.route(i["reference"]).kind for i in local}
    assert all(k == "basic" for k in kinds.values()), {t: k for t, k in kinds.items() if k != "basic"}
