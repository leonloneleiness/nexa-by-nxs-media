"""Render CodePanel.qml offscreen with a sample result → PNG (không chụp màn hình, không gọi Gemini).

    QT_QPA_PLATFORM=offscreen python scripts/probe_code_panel.py out.png [tab_index]
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")
os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QTimer, QUrl  # noqa: E402
from PySide6.QtGui import QColor, QFont, QGuiApplication  # noqa: E402
from PySide6.QtQuick import QQuickView  # noqa: E402

from nexa.code import checks  # noqa: E402
from nexa.code.models import CodeFile, CodeResult  # noqa: E402
from nexa.code.service import CodeService  # noqa: E402
from nexa.ui.code_bridge import CodeBridge  # noqa: E402
from nexa.utils.config import QML_DIR  # noqa: E402

SAMPLE = '''"""Tính tổng doanh thu theo tháng từ tệp CSV."""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path


def monthly_revenue(path: Path) -> dict[str, float]:
    """Đọc CSV (cột date, amount) và cộng doanh thu theo tháng YYYY-MM."""
    totals: dict[str, float] = defaultdict(float)
    with path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            month = row["date"][:7]
            totals[month] += float(row["amount"])
    return dict(sorted(totals.items()))


def main() -> None:
    import sys
    print(json.dumps(monthly_revenue(Path(sys.argv[1])), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
'''
TEST = '''from pathlib import Path

from revenue import monthly_revenue


def test_monthly(tmp=Path("t.csv")):
    tmp.write_text("date,amount\\n2026-01-03,10\\n2026-01-09,5.5\\n2026-02-01,1\\n", encoding="utf-8")
    assert monthly_revenue(tmp) == {"2026-01": 15.5, "2026-02": 1.0}
'''


class FakeController:
    def __init__(self, svc):
        self.code = svc


def main() -> int:
    out = sys.argv[1] if len(sys.argv) > 1 else "code_panel.png"
    tab = int(sys.argv[2]) if len(sys.argv) > 2 else -1
    app = QGuiApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 10))
    svc = CodeService(None, history_dir=Path(tempfile.mkdtemp()))
    files = [CodeFile("revenue.py", "python", SAMPLE), CodeFile("test_revenue.py", "python", TEST)]
    res = CodeResult("20260927-101500-abc123", "Hàm Python đọc CSV, gộp doanh thu theo tháng", "Gộp doanh thu theo tháng",
                     "python", "Đọc tệp CSV có cột date, amount; cộng doanh thu theo tháng và in JSON. Kèm kiểm thử.",
                     files, run_instructions="python revenue.py sales.csv\npython -m pytest -q", notes=["Giả định ngày dạng YYYY-MM-DD"],
                     created=1790000000, model="gemini-3.8-flash", rounds=2)
    res.checks = checks.check_files(files)
    if tab == 2:
        res.run = checks.run_project(files, checks.find_python())
    svc._publish(res, announce=False)
    bridge = CodeBridge(FakeController(svc))
    bridge.post("code_result", {"id": res.id})
    bridge.post("code_history", {})
    if tab == 2:   # bảng kết quả chạy giả lập (không chạy tiến trình thật)
        bridge._run = {"active": True, "state": "ok", "stateLabel": "Đạt", "title": "revenue.py", "lang": "Python",
                       "source": "code", "command": "python -m pytest -q", "seconds": 1.42, "running": False, "exitCode": 0,
                       "summary": {"total": 3, "passed": 3, "failed": 0}, "lines": 4, "steps": 1, "step": 1,
                       "html": "<span style='color:#9fb7cf'>...</span><br><span style='color:#4ade9a'>3 passed</span> in 0.12s"}
        bridge.runChanged.emit()
    view = QQuickView()
    view.setColor(QColor("#02060c"))
    view.engine().warnings.connect(lambda ws: [print("WARN:", w.toString()) for w in ws])
    view.rootContext().setContextProperty("nexaCode", bridge)
    view.setResizeMode(QQuickView.SizeRootObjectToView)
    view.resize(1240, 800)
    view.setSource(QUrl.fromLocalFile(str(QML_DIR / "CodePanel.qml")))
    for e in view.errors():
        print("QML:", e.toString())
    if view.status() != QQuickView.Ready:
        return 2
    view.show()

    def grab() -> None:
        root = view.rootObject()
        if tab >= 0:
            tabs = root.findChild(object, "infoTabs")
            if tabs is not None:
                tabs.setProperty("currentIndex", tab)
        if tab == 2:
            root.setProperty("view", "run")
            app.processEvents()
        view.grabWindow().save(out)
        print("saved", out)
        app.quit()
    QTimer.singleShot(2500 if tab == 2 else 1500, grab)
    app.exec()
    _keep = (bridge, svc)  # giữ tham chiếu Python tới context object
    return 0 if _keep else 1


if __name__ == "__main__":
    raise SystemExit(main())
