"""Câu lệnh có tên dịch vụ AI 3D ("bằng hugging face", "dùng HF tạo…") phải tới công cụ tạo mô hình (lỗi thật 2026-09-25:
"Tạo bình hoa gốm bằng hugging face" đi sang Gemini hội thoại, không tạo gì)."""
from __future__ import annotations

import pytest

from nexa.ai.intent_router import IntentRouter
from nexa.three_d.planner import LocalPlanner


@pytest.mark.parametrize("text,mode,quality", [
    ("Tạo bình hoa gốm bằng hugging face", "cloud", None),
    ("tạo mô hình bình hoa bằng hugging face", "cloud", None),
    ("dùng hugging face tạo cái cốc", "cloud", None),
    ("tạo cái cốc bằng HF", "cloud", None),
    ("hugging face tạo cho tôi cái ghế", "cloud", None),
    ("dựng bàn gỗ bằng tripo", "cloud", None),
    ("tạo bình hoa chất lượng cao bằng hugging face", "cloud", "high"),
    ("gen mô hình 3d con rồng", None, None),
    ("Tạo UAV bốn cánh", None, None),
])
def test_provider_phrases_route_to_generate(text, mode, quality):
    r = IntentRouter(viewer_active=lambda: False, part_known=lambda p: False).route(text)
    assert r is not None and r.calls and r.calls[0][0] == "generate_3d_model", text
    args = r.calls[0][1]
    assert args["prompt"] == text and args.get("mode") == mode and args.get("quality") == quality


@pytest.mark.parametrize("text,tool", [("tạo thư mục báo cáo", "create_folder"), ("tạo file word", "new_document"),
                                       ("mở hugging face", "open_app"), ("tìm trên hugging face model whisper", "web_search")])
def test_old_commands_not_hijacked(text, tool):
    r = IntentRouter(viewer_active=lambda: False, part_known=lambda p: False).route(text)
    assert r is not None and r.calls[0][0] == tool


@pytest.mark.parametrize("text,name", [("Tạo bình hoa gốm bằng hugging face", "bình hoa gốm"),
                                       ("dùng hugging face tạo cái cốc", "cái cốc"),
                                       ("hugging face tạo cho tôi cái ghế", "cái ghế"),
                                       ("tạo mô hình con rồng bằng tripo", "con rồng"),
                                       ("Tạo cốc cà phê có quai", "cốc cà phê có quai")])
def test_model_name_drops_provider_phrase(text, name):
    raw = LocalPlanner().parse(text)
    assert raw["name"] == name
    if "hugging" in text or "tripo" in text:
        assert raw.get("mode") == "cloud"


def test_no_control_characters_in_sources():
    """Chặn lỗi script sửa file ghi ký tự điều khiển (\\x08) thay cho \\b trong regex."""
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "nexa"
    bad = [str(p) for p in root.rglob("*.py") if any(ch in p.read_text(encoding="utf-8") for ch in "\x08\x07\x0c")]
    assert not bad, bad


def test_gemini_rules_say_hf_is_available():
    from nexa.ai.prompts import SYSTEM_INSTRUCTION
    assert "Hugging Face" in SYSTEM_INSTRUCTION and "không được nói là không làm được" in SYSTEM_INSTRUCTION
