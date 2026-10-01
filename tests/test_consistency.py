"""Tính nhất quán toàn hệ thống: mọi lệnh bộ phân tích sinh ra phải TỒN TẠI và ĐÚNG SCHEMA trong tool registry.

Lệch tên công cụ hay thiếu tham số bắt buộc chỉ lộ ra lúc chạy thật (anh nói xong mới báo lỗi), nên chặn ở đây.
"""
from __future__ import annotations

import pytest

from nexa.ai.intent_router import IntentRouter
from nexa.ai.tool_registry import build_registry
from nexa.utils.config import Config

# Bộ câu lệnh đại diện cho mọi nhóm chức năng (giọng nói thật của anh Sơn + biến thể).
CORPUS = [
    # ứng dụng / web
    "mở Notepad", "mở VS Code", "mở ChatGPT", "mở YouTube", "mở trình duyệt", "mở Zalo", "mở máy tính",
    "mở file báo cáo", "mở folder dự án", "tìm file hợp đồng", "mở thư mục Downloads", "tạo thư mục dự án",
    # tìm kiếm
    "tìm trên google thời tiết Hà Nội", "tìm kiếm trong ChatGPT về Nguyễn Xuân Sơn", "hỏi ChatGPT về lịch sử",
    "tìm trên YouTube nhạc remix", "tìm nguyễn xuân sơn trên facebook", "tra cứu trên wikipedia Hồ Chí Minh",
    # cửa sổ
    "thu nhỏ cửa sổ", "phóng to cửa sổ", "khôi phục cửa sổ", "chuyển cửa sổ sang màn hình 2", "đóng cửa sổ",
    "đóng ChatGPT", "đóng tab", "đóng tab YouTube", "tắt ứng dụng Zalo",
    # media
    "tạm dừng video", "phát tiếp video", "mở video đầu tiên trên YouTube", "bỏ qua quảng cáo",
    "bật tự động bỏ qua quảng cáo", "tắt tự động bỏ qua quảng cáo",
    # âm lượng / hệ thống
    "đặt âm lượng 30 phần trăm", "tăng âm lượng", "giảm âm lượng", "tắt tiếng", "bật tiếng",
    "chụp màn hình", "mấy giờ rồi", "hôm nay là ngày bao nhiêu", "xem thông tin hệ thống",
    # nhập liệu
    "gõ xin chào anh Sơn", "nhấn enter", "sao chép", "dán", "lưu lại", "cuộn lên",
    # tài liệu
    "tạo file word mới", "tạo file excel mới tên báo cáo", "mở powerpoint mới",
    "tạo file mới trong VS Code", "tạo file main.py trong vs code",
    # Zalo
    "kiểm tra tin nhắn zalo", "có ai nhắn tin cho tôi không", "xem zalo có tin nhắn mới không",
    # quản trị
    "chạy với quyền quản trị", "xin quyền admin", "mở powershell với quyền quản trị", "mở task manager",
    "mở quản lý thiết bị", "ứng dụng nào đang ngốn RAM", "buộc tắt Zalo", "tắt Chrome đang treo",
    "xem dung lượng ổ đĩa", "kiểm tra mạng", "máy có mạng không",
    # cử chỉ / phiên
    "bật điều khiển bằng tay", "tắt điều khiển bằng tay", "nghỉ đi", "dừng lại", "hủy",
    # nhiều bước
    "mở Notepad rồi gõ xin chào", "đóng ChatGPT rồi mở YouTube", "mở Notepad, đặt âm lượng 20 phần trăm",
]


@pytest.fixture(scope="module")
def registry():
    return build_registry(Config(load_env=False))


@pytest.fixture(scope="module")
def router():
    return IntentRouter()


def _validate(spec, args: dict) -> list[str]:
    """Kiểm tra args khớp JSON schema của công cụ (bắt buộc / thừa / kiểu / enum)."""
    schema = spec.parameters
    props = schema.get("properties", {})
    problems = []
    for key in schema.get("required", []):
        if key not in args:
            problems.append(f"thiếu tham số bắt buộc '{key}'")
    for key, value in args.items():
        if key not in props:
            problems.append(f"tham số lạ '{key}'")
            continue
        p = props[key]
        kinds = {"string": str, "integer": int, "boolean": bool, "number": (int, float), "array": list,
                 "object": dict}
        want = kinds.get(p.get("type"))
        if want and not isinstance(value, want):
            problems.append(f"'{key}' phải là {p['type']}, nhận {type(value).__name__}")
        if p.get("enum") and value not in p["enum"]:
            problems.append(f"'{key}'='{value}' không thuộc {p['enum']}")
    return problems


@pytest.mark.parametrize("text", CORPUS)
def test_every_routed_tool_exists_and_matches_schema(router, registry, text):
    route = router.route(text)
    assert route.kind in ("basic", "ai", "chat", "clarify", "stop", "cancel", "sleep", "internal",
                          "confirm", "deny"), route.kind
    for name, args in route.calls:
        spec = registry.get(name)
        assert spec is not None, f"'{text}' gọi công cụ '{name}' KHÔNG TỒN TẠI"
        problems = _validate(spec, args)
        assert not problems, f"'{text}' → {name}({args}): " + "; ".join(problems)


def test_no_duplicate_tool_names(registry):
    decls = registry.gemini_declarations()
    names = [d["name"] for d in decls]
    assert len(names) == len(set(names))


def test_all_tools_have_handler_and_description(registry):
    for d in registry.gemini_declarations():
        spec = registry.get(d["name"])
        assert callable(spec.handler), d["name"]
        assert spec.title and len(d.get("description", "")) > 10, d["name"]


def test_corpus_mostly_handled_without_gemini(router):
    """Lệnh điều khiển máy phải chạy được khi KHÔNG có mạng/Gemini."""
    local = [t for t in CORPUS if router.route(t).kind != "ai"]
    assert len(local) >= len(CORPUS) - 2, [t for t in CORPUS if router.route(t).kind == "ai"]


def test_router_is_deterministic(router):
    for text in CORPUS:
        assert router.route(text).calls == router.route(text).calls


@pytest.mark.parametrize("text", CORPUS)
def test_router_is_fast(router, text):
    import time
    t = time.monotonic()
    router.route(text)
    assert time.monotonic() - t < 0.05, "phân tích lệnh phải dưới 50 ms"
