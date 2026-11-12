"""Cầu nối Qt cho workspace NEXA Edu."""
from __future__ import annotations

from PySide6.QtCore import Property, QObject, Signal, Slot

from nexa.education.simulations import EducationEngine


class EducationBridge(QObject):
    changed = Signal()
    toast = Signal(str, bool)

    def __init__(self) -> None:
        super().__init__()
        self.engine = EducationEngine()
        self._open = False
        self._catalog = self.engine.catalog()
        self._state = self.engine.snapshot()

    @Property(bool, notify=changed)
    def open(self) -> bool:
        return self._open

    @open.setter
    def open(self, value: bool) -> None:
        value = bool(value)
        if self._open != value:
            self._open = value
            self.changed.emit()

    @Property("QVariantList", notify=changed)
    def catalog(self) -> list[dict]:
        return self._catalog

    @Property("QVariantMap", notify=changed)
    def state(self) -> dict:
        return self._state

    @Slot(str)
    def selectLesson(self, lesson_id: str) -> None:
        try:
            self._state = self.engine.select(lesson_id)
            self.changed.emit()
        except ValueError as exc:
            self.toast.emit(str(exc), True)

    @Slot(str, float)
    def setParameter(self, key: str, value: float) -> None:
        try:
            self._state = self.engine.set_value(key, value)
            self.changed.emit()
        except ValueError as exc:
            self.toast.emit(str(exc), True)

    @Slot()
    def runSimulation(self) -> None:
        self._state = self.engine.run()
        self.changed.emit()

    @Slot()
    def nextStep(self) -> None:
        self._state = self.engine.advance_step()
        self.changed.emit()

    @Slot()
    def resetLesson(self) -> None:
        self._state = self.engine.reset()
        self.changed.emit()

    @Slot(str)
    def exportReport(self, folder: str = "") -> None:
        """Xuất báo cáo JSON cục bộ để giáo viên lưu vào hồ sơ lớp."""
        import json
        from pathlib import Path
        target = Path(folder or (Path.home() / "Documents" / "NEXA Edu"))
        target.mkdir(parents=True, exist_ok=True)
        path = target / f"{self.engine.lesson.id}_report.json"
        path.write_text(json.dumps(self._state, ensure_ascii=False, indent=2), encoding="utf-8")
        self.toast.emit(f"Đã lưu báo cáo: {path}", False)

    @Slot()
    def close(self) -> None:
        self.open = False
