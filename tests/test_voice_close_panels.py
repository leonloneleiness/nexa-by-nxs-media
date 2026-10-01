"""Đóng mô hình 3D / bảng Sinh code bằng giọng nói: câu lệnh → công cụ, công cụ → service → bridge."""
from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from nexa.ai.intent_router import IntentRouter  # noqa: E402


@pytest.fixture(params=[True, False], ids=["viewer_open", "viewer_closed"])
def router(request):
    return IntentRouter(viewer_active=lambda: request.param, part_known=lambda p: False)


@pytest.mark.parametrize("text", [
    "Đóng mô hình UAV cho tôi", "đóng mô hình", "tắt mô hình 3D", "thoát mô hình đi", "đóng mô hình vừa tạo",
    "đóng trình xem", "tắt trình xem 3D", "thoát khỏi chế độ xem", "đóng cửa sổ mô hình", "đóng mô hình robot chó nhé",
    "hãy đóng mô hình động cơ bước giúp anh", "Nexa tắt mô hình trực thăng đi",
])
def test_close_model_phrases(router, text):
    assert router.route(text).calls == [("close_3d_viewer", {})]


@pytest.mark.parametrize("text", [
    "Đóng code", "đóng code cho tôi", "tắt bảng sinh code đi", "thoát chế độ code", "đóng bảng code", "tắt khung code nhé",
    "đóng cửa sổ sinh code",
])
def test_close_code_phrases(router, text):
    assert router.route(text).calls == [("close_code_panel", {})]


def test_close_does_not_steal_other_commands():
    r = IntentRouter(viewer_active=lambda: True, part_known=lambda p: False)
    assert r.route("đóng VS Code").calls[0][0] == "close_named"
    assert r.route("đóng Visual Studio Code").calls[0][0] == "close_named"
    assert r.route("đóng Chrome").calls[0][0] == "close_named"
    assert r.route("tắt chuyển động mô hình").calls == [("set_3d_motion", {"on": False})]
    assert r.route("mở mô hình vừa tạo").calls == [("open_3d_model", {})]


def test_close_in_multi_step_sentence():
    r = IntentRouter(viewer_active=lambda: True)
    assert r.route("đóng mô hình rồi mở Notepad").calls == [("close_3d_viewer", {}), ("open_app", {"name": "Notepad"})]
    assert r.route("tắt code rồi mở Chrome").calls == [("close_code_panel", {}), ("open_app", {"name": "Chrome"})]


# ------------------------------------------------------------------ công cụ
def test_close_3d_tool_also_closes_workspace():
    from nexa.three_d.tools import h_close
    events = []
    viewer = MagicMock(is_open=False)
    viewer.close.return_value = (True, "Đã đóng trình xem 3D.")
    svc = SimpleNamespace(enabled=True, viewer=viewer, _notify=lambda k, d: events.append((k, d)))
    res = h_close({}, SimpleNamespace(services=SimpleNamespace(three_d=svc)))
    assert res.ok and "cửa sổ mô hình" in res.message
    assert ("3d_workspace", {"open": False}) in events
    viewer.is_open = True
    res = h_close({}, SimpleNamespace(services=SimpleNamespace(three_d=svc)))
    assert res.ok and res.message == "Đã đóng trình xem 3D."


def test_close_code_tool_and_bridge(config, tmp_path):
    from PySide6.QtGui import QGuiApplication
    app = QGuiApplication.instance() or QGuiApplication([])
    from nexa.code.service import CodeService
    from nexa.code.tools import h_close
    from nexa.ui.code_bridge import CodeBridge
    config.set("code.save_dir", str(tmp_path / "saved"))
    svc = CodeService(config, history_dir=tmp_path / "hist")
    b = CodeBridge(MagicMock(code=svc, config=config))
    svc._notify = lambda k, d: b.post(k, d)               # type: ignore[method-assign]
    ctx = SimpleNamespace(services=SimpleNamespace(code=svc))
    assert "không mở" in h_close({}, ctx).message
    b.openPanel()
    app.processEvents()
    assert svc.panel_open and b.panelOpen
    res = h_close({}, ctx)
    app.processEvents()
    assert res.ok and res.message == "Em đã đóng bảng Sinh code."
    assert not svc.panel_open and not b.panelOpen


def test_tools_registered(config):
    from nexa.ai.tool_registry import ToolRegistry
    reg = ToolRegistry()
    from nexa.code.tools import register_code_tools
    register_code_tools(reg, config)
    assert reg.get("close_code_panel") is not None
