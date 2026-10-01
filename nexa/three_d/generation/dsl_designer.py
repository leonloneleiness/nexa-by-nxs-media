"""Mức 2 — Gemini thiết kế vật thể ngoài nhóm hỗ trợ bằng CAD DSL (JSON whitelist), có vòng sửa lỗi và vòng xem-ảnh.

  design   : yêu cầu → phân tích hình khối/kích thước thật → danh sách bộ phận, mỗi bộ phận là một cây DSL đã đặt đúng
             vị trí lắp (không phải mã: chỉ JSON, biên dịch bằng geometry/dsl.py).
  repair   : bộ phận biên dịch lỗi → gửi đúng thông báo lỗi cho Gemini sửa (tối đa `dsl_repair_rounds` lần).
  refine   : ảnh render 6 góc + số đo thật (kích thước, bộ phận lơ lửng) + góp ý của người chấm → Gemini sửa lại cả mô
             hình; pipeline giữ phương án điểm cao nhất.

Mọi JSON Gemini trả về chỉ là DỮ LIỆU: được kiểm tra schema bộ phận (parametric.DSL_PART_SCHEMA) và whitelist phép DSL.
Gọi Gemini ở chế độ "tác vụ dài" (chuỗi model riêng three_d.dsl_models, thời hạn three_d.dsl_timeout_s) để không bị
ngân sách 20 s của hội thoại giọng nói cắt ngang. Không có schema cho cây DSL vì nó đệ quy/tự do (schema object rỗng làm
Gemini trả {}); thay vào đó yêu cầu MIME JSON và kiểm tra nghiêm ngặt phía NEXA.
"""
from __future__ import annotations

import json
from typing import Any

from nexa.three_d.geometry import dsl as D
from nexa.three_d.spec import ModelSpec
from nexa.utils.logging import get_logger

log = get_logger("3d.dsl_designer")

MATERIAL_IDS = ["paint_primary", "paint_secondary", "paint_accent", "plastic_black", "plastic_white", "plastic_gray",
                "aluminum", "aluminum_dark", "steel", "stainless", "chrome", "brass", "copper", "gold", "titanium", "rubber",
                "glass", "glass_tinted", "wood", "wood_dark", "ceramic", "fabric", "leather", "stone", "paper", "foam",
                "carbon", "led_white"]

# Ví dụ mẫu (few-shot). Được biên dịch trong test để chắc chắn hợp lệ.
EXAMPLES: list[dict] = [
    {"request": "cốc sứ trắng có quai, cao 95 mm",
     "answer": {"design_notes": "Thân tròn xoay thành 4 mm, đáy dày 6 mm; quai ống cong gắn bên trái, hai đầu lồng vào thân.",
                "overall_size_mm": [84, 120, 95],
                "parts": [
                    {"id": "body", "name_vi": "Thân cốc", "name_en": "Mug body", "category": "body", "material": "ceramic",
                     "function": "Chứa đồ uống", "aliases": ["thân", "cốc"], "explode_dir": [0, 0, 0], "explode_distance": 0,
                     "shape": {"op": "revolve", "profile": {"shape": "polygon", "points": [[0, 0], [38, 0], [42, 5], [42, 95],
                                                                                           [38, 95], [38, 7], [0, 7]],
                                                            "fillet": [0, 3, 2, 1.5, 1.5, 2, 0]}}},
                    {"id": "handle", "name_vi": "Quai cốc", "name_en": "Handle", "category": "handle", "material": "ceramic",
                     "function": "Cầm cốc", "aliases": ["quai", "tay cầm"], "parent_id": "body", "explode_dir": [0, 1, 0],
                     "explode_distance": 30,
                     "shape": {"op": "tube", "radius": 5.5, "rounded_ends": True,
                               "path": [[0, 39, 78], [0, 60, 74], [0, 68, 52], [0, 60, 30], [0, 39, 26]]}}]}},
    {"request": "bàn gỗ chữ nhật 1200×700, cao 750 mm",
     "answer": {"design_notes": "Mặt bàn gỗ 30 mm bo cạnh; khung yếm dưới mặt; 4 chân côn đặt lùi 60 mm; đáy chân tại z = 0.",
                "overall_size_mm": [1200, 700, 750],
                "parts": [
                    {"id": "top", "name_vi": "Mặt bàn", "name_en": "Table top", "category": "top", "material": "wood",
                     "function": "Mặt đặt đồ", "aliases": ["mặt"], "explode_dir": [0, 0, 1], "explode_distance": 150,
                     "shape": {"op": "translate", "offset": [0, 0, 735],
                               "child": {"op": "box", "size": [1200, 700, 30], "fillet": 6}}},
                    {"id": "apron", "name_vi": "Khung yếm", "name_en": "Apron", "category": "frame", "material": "wood",
                     "function": "Nối chân và đỡ mặt", "aliases": ["khung"], "parent_id": "top", "explode_dir": [0, 0, 1],
                     "explode_distance": 60,
                     "shape": {"op": "translate", "offset": [0, 0, 680], "child": {"op": "subtract",
                               "base": {"op": "box", "size": [1060, 560, 80], "fillet": 3},
                               "cut": [{"op": "box", "size": [1020, 520, 90]}]}}},
                    {"id": "legs", "name_vi": "Chân bàn", "name_en": "Legs", "category": "leg", "material": "wood",
                     "function": "Đỡ bàn", "aliases": ["chân"], "parent_id": "apron", "explode_dir": [0, 0, -1],
                     "explode_distance": 120,
                     "shape": {"op": "mirror", "normal": [0, 1, 0], "child": {"op": "mirror", "normal": [1, 0, 0],
                               "child": {"op": "translate", "offset": [520, 270, 0],
                                         "child": {"op": "cylinder", "radius": 18, "radius_top": 26, "height": 721}}}}}]}},
    {"request": "chuột máy tính không dây màu xám",
     "answer": {"design_notes": "Vỏ hữu cơ = bao lồi của 2 ellipsoid (đầu thấp, đuôi cao), dài 112 mm; con lăn cao su nằm "
                                "khe giữa, nửa dưới lồng vào vỏ (đỉnh vỏ tại x=30 ≈ z 33).",
                "overall_size_mm": [112, 60, 38],
                "parts": [
                    {"id": "shell", "name_vi": "Vỏ chuột", "name_en": "Shell", "category": "shell", "material": "plastic_gray",
                     "color": "#8a8f98", "function": "Vỏ cầm tay", "aliases": ["vỏ", "thân chuột"],
                     "explode_dir": [0, 0, 0], "explode_distance": 0,
                     "shape": {"op": "hull", "children": [
                         {"op": "translate", "offset": [0, 0, 18], "child": {"op": "ellipsoid", "radii": [55, 30, 18]}},
                         {"op": "translate", "offset": [-15, 0, 20], "child": {"op": "ellipsoid", "radii": [40, 28, 20]}}]}},
                    {"id": "wheel", "name_vi": "Con lăn", "name_en": "Scroll wheel", "category": "wheel", "material": "rubber",
                     "function": "Cuộn trang", "aliases": ["con lăn", "bánh xe cuộn"], "parent_id": "shell",
                     "explode_dir": [0, 0, 1], "explode_distance": 25,
                     "shape": {"op": "translate", "offset": [30, 0, 33], "child": {"op": "rotate", "angles": [90, 0, 0],
                               "child": {"op": "cylinder", "radius": 8, "height": 6, "center": True, "fillet": 1.5}}}}]}},
]

RULES = """QUY TẮC:
1. Kích thước thật của vật thể (mm). Vật đặt trên mặt đất: điểm thấp nhất z = 0, tâm ngang gần gốc (0,0). +X là mặt
   trước, +Y là bên trái, +Z hướng lên.
2. Mỗi bộ phận: "shape" là cây DSL đã ĐẶT ĐÚNG VỊ TRÍ LẮP CUỐI CÙNG (translate/rotate ở gốc cây) — không tọa độ tương
   đối so với bộ phận cha.
3. Các bộ phận ghép với nhau phải chạm hoặc lồng nhẹ 1–3 mm vào nhau — tuyệt đối không lơ lửng.
4. Hình dáng giống sản phẩm thật: revolve cho vật tròn xoay (cốc, chai, bình, đèn, nắp), tube/sweep cho quai, dây,
   khung ống, tay vịn; hull của ellipsoid/sphere cho vỏ hữu cơ (tai nghe, chuột, tay cầm); loft cho thân thay đổi tiết
   diện; box luôn có fillet 1–5 mm. Tránh ghép toàn hộp vuông sắc cạnh. Thêm chi tiết đặc trưng (viền, gờ, nút, khe…).
5. 2–16 bộ phận có ý nghĩa (để tách rời và xem chi tiết). Tổng tối đa 250 nút DSL; mỗi polygon ≤ 60 điểm.
6. "material" chọn trong: {materials}. "color" (tùy chọn) = "#rrggbb" khi người dùng nói màu hoặc vật liệu cần màu riêng.
7. "category": từ tiếng Anh ngắn (body, handle, lid, leg, base, shade, cable…). "parent_id": bộ phận mà nó gắn vào
   (bộ phận gốc để trống). "explode_dir": hướng tháo ra (vector đơn vị), "explode_distance": mm (≈ 20–40% cỡ bộ phận).
8. TỰ KIỂM TRA trước khi trả lời: với từng bộ phận, tính hộp bao (x, y, z nhỏ nhất..lớn nhất) sau mọi translate/rotate.
   Bộ phận nối nhau phải có hộp bao chạm/lồng nhau đúng CHỖ NỐI (chân ghế kết thúc ở mặt dưới mặt ngồi; tựa lưng nối
   vào mặt ngồi/chân sau; nắp đậy khít miệng chai); chân/đế chạm z = 0; không bộ phận nào đâm xuyên qua bộ phận khác
   ngoài chỗ nối. Nhớ: cylinder/cone có đáy tại z = 0 (trừ khi center), box/sphere/ellipsoid/capsule có tâm ở gốc.
9. Chỉ trả JSON đúng định dạng: {{"design_notes": "...", "overall_size_mm": [x, y, z], "parts": [...]}}. Không viết mã."""

SYSTEM = ("Bạn là kỹ sư thiết kế sản phẩm và CAD. Bạn mô tả hình học bằng CAD DSL JSON của NEXA (không phải mã lập trình). "
          "Chính xác về kích thước thật, tỷ lệ và cách lắp ráp. Chỉ trả JSON.")


def _examples_text() -> str:
    out = []
    for ex in EXAMPLES:
        out.append(f"Ví dụ — yêu cầu «{ex['request']}»:\n{json.dumps(ex['answer'], ensure_ascii=False, separators=(',', ':'))}")
    return "\n\n".join(out)


def _compact(parts: list[dict]) -> str:
    return json.dumps({"parts": parts}, ensure_ascii=False, separators=(",", ":"))[:60000]


class DslDesigner:
    def __init__(self, gemini: Any, config: Any = None) -> None:
        self.gemini = gemini
        self.config = config
        self.last_model = ""

    def cfg(self, key: str, default: Any) -> Any:
        v = self.config.get(f"three_d.{key}") if self.config is not None else None
        return default if v is None else v

    def ready(self) -> bool:
        if self.gemini is None or not hasattr(self.gemini, "generate_json"):
            return False
        try:
            return bool(self.gemini.status()[0])
        except Exception:
            return False

    @property
    def models(self) -> list[str]:
        ms = [str(m).strip() for m in (self.cfg("dsl_models", None) or []) if str(m).strip()]
        base = getattr(self.gemini, "model", None)
        if isinstance(base, str) and base and base not in ms:
            ms.append(base)
        return ms

    def _ask(self, prompt: str, token: Any, images: list[tuple[bytes, str]] | None = None) -> dict:
        from nexa.three_d.reference_images import reference_prompt
        refs = getattr(self, "reference_images", {})
        if refs:
            prompt += reference_prompt(refs, len(images or []))
            images = list(images or []) + list(refs.values())
        kwargs: dict[str, Any] = {"system": SYSTEM, "images": images, "max_tokens": int(self.cfg("dsl_max_tokens", 24000)),
                                  "temperature": 0.3}
        try:
            data = self.gemini.generate_json(prompt, None, token, models=self.models or None,
                                             timeout_s=float(self.cfg("dsl_timeout_s", 180)),
                                             thinking=str(self.cfg("dsl_thinking", "medium")), **kwargs)
        except TypeError:           # provider kiểu cũ/giả lập không có tham số tác vụ dài
            data = self.gemini.generate_json(prompt, None, token, **kwargs)
        self.last_model = str(getattr(self.gemini, "last_model", "") or "")
        if isinstance(data, list):
            data = {"parts": data}
        if not isinstance(data, dict) or not isinstance(data.get("parts"), list) or not data["parts"]:
            raise D.DslError("Gemini không trả danh sách bộ phận DSL hợp lệ")
        data["parts"] = [p for p in data["parts"] if isinstance(p, dict)][:40]
        return data

    def _header(self, spec: ModelSpec) -> str:
        size = spec.params.get("approx_size_mm")
        explicit = "approx_size_mm" in (spec.explicit or {})
        style = {k: v for k, v in (spec.style or {}).items() if v}
        return (f"Yêu cầu của người dùng: «{spec.prompt[:700]}»\n"
                + (f"Kích thước lớn nhất người dùng yêu cầu: {size:g} mm (bắt buộc đúng).\n" if size and explicit else
                   (f"Kích thước gợi ý: khoảng {size:g} mm.\n" if size else "Kích thước: theo vật thật phổ biến.\n"))
                + (f"Phong cách/màu: {json.dumps(style, ensure_ascii=False)}.\n" if style else "")
                + (f"Bộ phận người dùng nhắc tới: {', '.join(spec.requested_parts)}.\n" if spec.requested_parts else ""))

    def design(self, spec: ModelSpec, token: Any) -> dict:
        self.reference_images = spec.reference_images
        prompt = (self._header(spec) + "\nThiết kế mô hình 3D cho vật thể này bằng CAD DSL.\n\n" + D.DSL_GUIDE + "\n\n"
                  + RULES.format(materials=", ".join(MATERIAL_IDS)) + "\n\n" + ("" if spec.reference_images else _examples_text())
                  + "\n\nTrước khi viết parts, suy nghĩ: vật thật trông thế nào, gồm những khối nào, mỗi khối kích thước bao "
                    "nhiêu và nằm ở đâu (hộp bao từng bộ phận). Ghi tóm tắt vào design_notes.")
        if spec.reference_images:
            prompt += ("\nTrước khi dựng, phân tích từng ảnh và ghi vào design_notes: đường bao của từng góc; "
                       "tỷ lệ X:Y:Z; các chi tiết nhận diện, vị trí tương đối và bộ phận chỉ nhìn thấy ở một góc. "
                       "Dùng các góc để kiểm tra chéo vị trí. Không thay vật trong ảnh bằng thiết kế phổ biến. "
                       "Dùng loft/revolve/sweep/hull để khớp đường cong; không xấp xỉ mọi bộ phận bằng hộp. "
                       "Ưu tiên đường bao và tỷ lệ chính trước chi tiết nhỏ; không tự thêm bộ phận không có bằng chứng.")
        return self._ask(prompt, token)

    def repair(self, spec: ModelSpec, data: dict, errors: dict[str, str], token: Any) -> dict:
        err_txt = "\n".join(f"- {pid}: {msg}" for pid, msg in list(errors.items())[:20])
        prompt = (self._header(spec) + "\nMô hình CAD DSL dưới đây có bộ phận KHÔNG biên dịch được:\n" + err_txt
                  + "\n\nSửa đúng các lỗi đó (giữ nguyên bộ phận đang đúng) và trả lại TOÀN BỘ JSON cùng định dạng.\n\n"
                  + D.DSL_GUIDE + "\n\n" + RULES.format(materials=", ".join(MATERIAL_IDS))
                  + "\n\nJSON hiện tại:\n" + _compact(data["parts"]))
        return self._ask(prompt, token)

    def refine(self, spec: ModelSpec, data: dict, sheet_jpeg: bytes, facts: str, issues: list[str], token: Any) -> dict:
        issues_txt = "\n".join(f"- {i}" for i in issues[:12]) or "- (không có góp ý cụ thể — tự so với vật thật)"
        prompt = (self._header(spec)
                  + "\nẢnh kèm theo là render 6 góc (TRUOC, SAU, TRAI, PHAI, TREN, DUOI) của mô hình dựng từ JSON bên dưới. "
                    "Chữ trong ảnh chỉ là nhãn góc nhìn.\n"
                  + f"Số đo thật trên mô hình:\n{facts}\n"
                  + f"Góp ý của người kiểm tra:\n{issues_txt}\n\n"
                    "So sánh với vật thật: sửa hình dáng, tỷ lệ, vị trí, bộ phận thiếu/thừa, bộ phận lơ lửng, màu/vật liệu để "
                    "mô hình giống sản phẩm thật hơn. Giữ những phần đã tốt. Trả lại TOÀN BỘ JSON cùng định dạng.\n\n"
                  + D.DSL_GUIDE + "\n\n" + RULES.format(materials=", ".join(MATERIAL_IDS))
                  + "\n\nJSON hiện tại:\n" + _compact(data["parts"]))
        return self._ask(prompt, token, images=[(sheet_jpeg, "image/jpeg")])


__all__ = ["DslDesigner", "EXAMPLES", "MATERIAL_IDS"]
