"""Các bài mô phỏng STEM chạy cục bộ, có thể kiểm chứng và lưu kết quả."""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any


@dataclass(frozen=True)
class Lesson:
    id: str
    title: str
    subject: str
    level: str
    summary: str
    parameters: tuple[dict[str, Any], ...]
    steps: tuple[str, ...] = ()


LESSONS = (
    Lesson("bridge_load", "Cầu chịu tải", "Vật lý · STEM", "Lớp 6–9", "Khám phá quan hệ giữa nhịp cầu, tiết diện và tải trọng.",
           ({"id": "span", "label": "Nhịp cầu", "unit": "m", "min": 1.0, "max": 10.0, "value": 4.0}, {"id": "load", "label": "Tải trọng", "unit": "kg", "min": 1.0, "max": 100.0, "value": 20.0}, {"id": "thickness", "label": "Độ dày dầm", "unit": "cm", "min": 1.0, "max": 30.0, "value": 8.0}),
           ("Dự đoán điểm yếu của cầu.", "Điều chỉnh một tham số.", "Chạy mô phỏng và giải thích kết quả.")),
    Lesson("pendulum", "Con lắc đơn", "Vật lý", "Lớp 7–12", "Đo chu kỳ dao động và kiểm tra ảnh hưởng của chiều dài dây.",
           ({"id": "length", "label": "Chiều dài dây", "unit": "m", "min": 0.2, "max": 4.0, "value": 1.0}, {"id": "angle", "label": "Góc ban đầu", "unit": "°", "min": 2.0, "max": 30.0, "value": 10.0}),
           ("Đoán xem chiều dài ảnh hưởng thế nào.", "Thay đổi chiều dài dây.", "So sánh chu kỳ đo được.")),
    Lesson("circuit", "Mạch điện một chiều", "Vật lý · Kỹ thuật", "Lớp 9–12", "Thay đổi điện áp và điện trở để quan sát dòng điện theo định luật Ohm.",
           ({"id": "voltage", "label": "Hiệu điện thế", "unit": "V", "min": 1.0, "max": 24.0, "value": 9.0}, {"id": "resistance", "label": "Điện trở", "unit": "Ω", "min": 1.0, "max": 100.0, "value": 10.0}),
           ("Dự đoán dòng điện.", "Thay đổi U hoặc R.", "Đối chiếu với I = U / R.")),
    Lesson("ph_scale", "Thang pH", "Hóa học", "Lớp 8–12", "Pha loãng dung dịch và quan sát pH thay đổi như thế nào.",
           ({"id": "concentration", "label": "Nồng độ", "unit": "%", "min": 0.1, "max": 100.0, "value": 10.0},),
           ("Dự đoán dung dịch có tính axit hay bazơ.", "Thay đổi nồng độ.", "Ghi nhận pH và rút ra kết luận.")),
    Lesson("solar", "Tấm pin mặt trời", "Vật lý · Môi trường", "Lớp 6–12", "Khảo sát góc chiếu và cường độ sáng ảnh hưởng đến công suất.",
           ({"id": "angle", "label": "Góc chiếu", "unit": "°", "min": 0.0, "max": 90.0, "value": 20.0}, {"id": "light", "label": "Cường độ sáng", "unit": "%", "min": 10.0, "max": 100.0, "value": 80.0}),
           ("Dự đoán góc tối ưu.", "Thay đổi góc và ánh sáng.", "So sánh công suất.")),
    Lesson("solar_system", "Hệ Mặt Trời", "Thiên văn", "Lớp 4–9", "Quan sát quy mô, quỹ đạo và thời gian quay của các hành tinh.",
           ({"id": "speed", "label": "Tốc độ mô phỏng", "unit": "×", "min": 0.5, "max": 20.0, "value": 1.0},),
           ("Chọn một hành tinh để quan sát.", "Điều chỉnh tốc độ thời gian.", "Mô tả sự khác nhau giữa các quỹ đạo.")),
)


class EducationEngine:
    """Tính kết quả mô phỏng bằng các công thức minh bạch, không gọi AI."""

    def __init__(self) -> None:
        self.lesson = LESSONS[0]
        self.values = {p["id"]: p["value"] for p in self.lesson.parameters}
        self.history: list[dict[str, Any]] = []
        self.step = 0

    @staticmethod
    def catalog() -> list[dict[str, Any]]:
        return [{"id": x.id, "title": x.title, "subject": x.subject, "level": x.level, "summary": x.summary}
                for x in LESSONS]

    def select(self, lesson_id: str) -> dict[str, Any]:
        self.lesson = next((x for x in LESSONS if x.id == lesson_id), LESSONS[0])
        self.values = {p["id"]: p["value"] for p in self.lesson.parameters}
        self.history = []
        self.step = 0
        return self.snapshot()

    def advance_step(self) -> dict[str, Any]:
        self.step = min(self.step + 1, max(0, len(self.lesson.steps) - 1))
        return self.snapshot()

    def reset(self) -> dict[str, Any]:
        self.values = {p["id"]: p["value"] for p in self.lesson.parameters}
        self.history = []
        self.step = 0
        return self.snapshot()

    def set_value(self, key: str, value: float) -> dict[str, Any]:
        spec = next((p for p in self.lesson.parameters if p["id"] == key), None)
        if spec is None:
            raise ValueError("Tham số mô phỏng không hợp lệ.")
        value = max(float(spec["min"]), min(float(spec["max"]), float(value)))
        self.values[key] = value
        return self.snapshot()

    def run(self) -> dict[str, Any]:
        v = self.values
        if self.lesson.id == "bridge_load":
            stress = v["load"] * 9.81 * v["span"] ** 2 / max(v["thickness"] ** 2, 0.01)
            capacity = 900.0
            score = max(0.0, min(100.0, 100.0 * (1.0 - stress / capacity)))
            result = {"label": "Ứng suất tương đối", "value": round(stress, 2), "unit": "đv", "score": round(score),
                      "feedback": "Cầu đang quá tải." if stress > capacity else "Cầu vẫn trong giới hạn mô phỏng."}
        elif self.lesson.id == "pendulum":
            period = 2 * math.pi * math.sqrt(v["length"] / 9.81)
            result = {"label": "Chu kỳ lý thuyết", "value": round(period, 3), "unit": "s", "score": 100,
                      "feedback": "Góc nhỏ phù hợp với công thức gần đúng." if v["angle"] <= 15 else "Góc lớn: cần chú ý sai số của công thức gần đúng."}
        elif self.lesson.id == "circuit":
            current = v["voltage"] / max(v["resistance"], 0.01)
            result = {"label": "Dòng điện", "value": round(current, 3), "unit": "A", "score": 100,
                      "feedback": "Đã áp dụng định luật Ohm: I = U / R."}
        elif self.lesson.id == "ph_scale":
            ph = max(0.0, min(14.0, 7.0 - math.log10(max(v["concentration"] / 10.0, 0.001))))
            result = {"label": "Độ pH ước tính", "value": round(ph, 2), "unit": "pH", "score": 100,
                      "feedback": "Mô hình minh họa; không thay thế phép đo hóa chất thật."}
        elif self.lesson.id == "solar":
            power = v["light"] * max(0.0, math.cos(math.radians(v["angle"])))
            result = {"label": "Công suất tương đối", "value": round(power, 2), "unit": "%", "score": round(power),
                      "feedback": "Công suất cao nhất khi ánh sáng chiếu gần vuông góc."}
        else:
            result = {"label": "Tốc độ mô phỏng", "value": v["speed"], "unit": "×", "score": 100,
                      "feedback": "Đã cập nhật tốc độ quan sát quỹ đạo."}
        self.history.append({"values": dict(v), "result": result})
        return self.snapshot(result)

    def snapshot(self, result: dict[str, Any] | None = None) -> dict[str, Any]:
        return {"lesson": {"id": self.lesson.id, "title": self.lesson.title, "subject": self.lesson.subject,
                            "level": self.lesson.level, "summary": self.lesson.summary},
                "parameters": [{**p, "value": self.values[p["id"]]} for p in self.lesson.parameters],
                "result": result or (self.history[-1]["result"] if self.history else {}),
                "history_count": len(self.history), "steps": list(self.lesson.steps), "step": self.step,
                "series": [{"x": i + 1, "value": h["result"]["value"], "score": h["result"].get("score", 0)}
                           for i, h in enumerate(self.history)]}
