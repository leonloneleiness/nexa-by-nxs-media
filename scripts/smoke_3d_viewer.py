"""Kiểm thử khói trình xem 3D: dựng mô hình thật (CAD tham số) → nạp ModelViewer.qml → render ra PNG (grabWindow,
KHÔNG chụp màn hình) → kiểm tra ảnh có nội dung, không có cảnh báo QML, đo FPS và thời gian nạp.

    .venv\\Scripts\\python scripts\\smoke_3d_viewer.py [uav|bolt|rover|humanoid|quadruped|helicopter] [ảnh.png]

Mặc định chạy nền tảng Qt "offscreen" (không cửa sổ). Nếu RHI không khởi tạo được ở offscreen, dùng --window: cửa sổ
đặt ngoài vùng màn hình (x = -6000), không nhận focus, tự đóng sau vài giây.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PROMPTS = {"uav": "Tạo một UAV mini bốn cánh, thân carbon màu đen, camera phía trước",
           "bolt": "Tạo bu-lông M8 dài 30 mm, bước ren 1,25 mm kèm đai ốc và vòng đệm",
           "rover": "Tạo xe tự hành sáu bánh có LiDAR và camera", "humanoid": "Tạo robot hình người",
           "boat": "Tạo ca nô cao tốc dài 6 m", "yacht": "Tạo du thuyền dài 15 m hai máy",
           "quadruped": "Tạo robot hình chó, mỗi chân có ba khớp",
           "helicopter": "Tạo trực thăng cứu hộ có rotor chính và rotor đuôi",
           # linh kiện cơ khí tiêu chuẩn
           "bearing": "Tạo ổ bi 6204", "stepper": "Tạo động cơ bước NEMA 17", "gearbox": "Tạo hộp số 2 cấp tỉ số truyền 12",
           "cylinder": "Tạo xi lanh khí nén phi 50 hành trình 200", "valve": "Tạo van bi DN50",
           "flange_joint": "Tạo mặt bích nối ống DN80", "belt": "Tạo bộ truyền đai GT2 puly 20 răng và 40 răng",
           "chain": "Tạo bộ truyền xích 08B đĩa 17 răng và 34 răng", "coupling": "Tạo khớp nối mềm trục 14 sang 19",
           "ballscrew": "Tạo vít me bi SFU1605 dài 500 mm", "rail": "Tạo ray trượt HGR20 dài 600 mm hai con trượt",
           "spring": "Tạo lò xo nén dây 2 mm đường kính ngoài 20 mm 8 vòng",
           # robot
           "robot_arm": "Tạo cánh tay robot 6 trục có tay kẹp", "robot_arm_kuka": "Tạo robot công nghiệp 6 trục tầm với 1,4 m tải 20 kg",
           "robot_vacuum": "Tạo robot hút bụi có lau nhà", "agv": "Tạo robot AGV nâng kệ bánh mecanum",
           "delivery": "Tạo robot giao hàng dài 700 mm",
           # phương tiện & hàng không vũ trụ
           "plane": "Tạo máy bay hạng nhẹ 4 chỗ", "vtol": "Tạo UAV VTOL cánh cố định", "car": "Tạo ô tô điện SUV hai motor",
           "motorbike": "Tạo mô tô côn tay", "scooter": "Tạo xe máy tay ga", "ebike": "Tạo xe đạp điện",
           "excavator": "Tạo máy xúc 20 tấn tư thế đào", "forklift": "Tạo xe nâng điện 2,5 tấn nâng cao 2 m",
           "crane": "Tạo xe cẩu cần dài 30 m góc nâng 60 độ", "train": "Tạo tàu điện 2 toa", "cubesat": "Tạo vệ tinh CubeSat 3U",
           "rocket": "Tạo tên lửa 2 tầng",
           # năng lượng & công trình
           "wind": "Tạo tuabin gió mở nắp nacelle", "solar": "Tạo hệ điện mặt trời 12 tấm 2 hàng", "genset": "Tạo máy phát điện 100 kVA",
           "pump": "Tạo máy bơm ly tâm 65-50-160", "tank": "Tạo bồn chứa 50 m3", "bridge": "Tạo cầu giàn thép nhịp 60 m",
           "cable_bridge": "Tạo cầu dây văng nhịp 80 m", "truss": "Tạo giàn thép kiểu Pratt nhịp 12 m", "tower": "Tạo cột điện cao thế 30 m",
           "bts": "Tạo tháp viễn thông 3 chân"}


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    windowed = "--window" in sys.argv
    kind = args[0] if args else "uav"
    out_png = Path(args[1]) if len(args) > 1 else Path(tempfile.gettempdir()) / f"nexa_3d_{kind}.png"
    if not windowed:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
    os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")

    from PySide6.QtCore import QObject, Property, QTimer, QUrl, Signal
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQuick import QQuickView

    from nexa.three_d.asset_store import AssetStore
    from nexa.three_d.service import ThreeDService
    from nexa.ui.three_d_bridge import ThreeDBridge, register_qml_types
    from nexa.utils.config import QML_DIR, Config

    tmp = Path(tempfile.mkdtemp(prefix="nexa3d_smoke_"))
    cfg = Config(settings_path=tmp / "s.yaml", gestures_path=tmp / "g.yaml", load_env=False)
    cfg.set("three_d.ai_review", False)
    app = QGuiApplication(sys.argv)
    holder: dict = {}

    class FakeGestures:
        running = False

    # --glb=<tệp>: mở một GLB có sẵn (vd. lưới AI tải từ cloud) qua đúng đường nhập cloud (làm sạch, vật liệu, texture)
    glb_arg = next((a[6:] for a in sys.argv if a.startswith("--glb=")), None)
    provider_factory = (lambda: None)
    if glb_arg:
        import shutil
        from nexa.three_d.generation.base import ProviderTask

        class ReplayGlb:
            name, capabilities = "phát lại GLB", {"text_to_model"}

            def available(self):
                return True, "ok"

            def create_from_text(self, prompt, **kw):
                return ProviderTask("replay", "text_to_model")

            def get_job_status(self, t):
                t.status, t.progress = "success", 100
                return t

            def cancel_job(self, t):
                return False

            def download_result(self, t, dest, max_bytes, cancelled=None):
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(glb_arg, dest)
                return dest
        provider_factory = ReplayGlb
        PROMPTS[kind] = f"Tạo {kind} bằng cloud"
        cfg.set("three_d.refinement_rounds", 0)

    class FakeController:
        def __init__(self) -> None:
            self.config = cfg
            self.gestures = FakeGestures()
            self.three_d = ThreeDService(cfg, notify=lambda k, d: holder["b"].post(k, d) if "b" in holder else None,
                                         gemini=None, store=AssetStore(tmp / "cache"), provider_factory=provider_factory)

    class FakeNexa(QObject):
        changed = Signal()
        toast = Signal(str, bool)

        @Property(bool, notify=changed)
        def showFps(self):
            return True

    ctrl = FakeController()
    t0 = time.monotonic()
    job = ctrl.three_d.submit(PROMPTS[kind], open_when_ready=False)
    while not job.terminal:
        app.processEvents()
        time.sleep(0.05)
    gen_s = time.monotonic() - t0
    if not job.project_id:
        print(json.dumps({"ok": False, "error": job.error}, ensure_ascii=False))
        return 2
    register_qml_types()
    bridge = ThreeDBridge(ctrl)
    holder["b"] = bridge
    view = QQuickView()
    warnings: list[str] = []
    view.engine().warnings.connect(lambda ws: warnings.extend(w.toString() for w in ws))
    view.rootContext().setContextProperty("nexa3d", bridge)
    fake = FakeNexa()
    view.rootContext().setContextProperty("nexa", fake)
    view.setResizeMode(QQuickView.ResizeMode.SizeRootObjectToView)
    view.resize(1280, 800)
    if windowed:
        from PySide6.QtCore import Qt
        view.setFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowDoesNotAcceptFocus)
        view.setPosition(-6000, 0)
    view.setSource(QUrl.fromLocalFile(str(QML_DIR / "ModelViewer.qml")))
    if view.status() == QQuickView.Status.Error:
        print(json.dumps({"ok": False, "error": "QML lỗi", "warnings": warnings}, ensure_ascii=False))
        return 3
    for kv in [a for a in sys.argv if a.startswith("--set=")]:
        k, v = kv[6:].split("=", 1)
        view.rootObject().setProperty(k, v == "true" if v in ("true", "false") else v)
    view.show()
    t_open = time.monotonic()
    ctrl.three_d.viewer.open(job.project_id)
    result: dict = {}

    perf: dict = {}
    proc = None
    if "--perf" in sys.argv:
        import psutil
        proc = psutil.Process()

    def perf_idle():
        # CPU khi viewer đứng yên (đã nạp xong), rồi 3 s xoay bằng cử chỉ tổng hợp 30 Hz qua đúng đường feed_gesture
        proc.cpu_percent(None)
        QTimer.singleShot(2000, perf_rotate)

    def perf_rotate():
        from nexa.vision.gesture_features import Pose
        from nexa.vision.gesture_state_machine import Observation
        perf["cpu_idle_pct"] = round(proc.cpu_percent(None), 1)
        st = {"n": 0, "x": 0.35, "proc_ms": [], "lat_ms": [], "yaw0": ctrl.three_d.viewer.yaw}
        timer = QTimer()
        timer.setInterval(33)

        def tick():
            st["n"] += 1
            st["x"] += 0.006 if st["n"] > 8 else 0.0
            t = time.monotonic()
            c0 = time.perf_counter()        # monotonic trên Windows chỉ phân giải ~15,6 ms
            evs = ctrl.three_d.feed_gesture(Observation(t, True, Pose.OPEN_PALM, 0.9, (st["x"], 0.5), 0.2), t_frame=t)
            st["proc_ms"].append((time.perf_counter() - c0) * 1000)
            st["lat_ms"] += [e.extra["latency_ms"] for e in evs if e.kind == "rotate" and "latency_ms" in e.extra]
            if st["n"] >= 90:
                timer.stop()
                perf["cpu_rotate_pct"] = round(proc.cpu_percent(None), 1)
                perf["rss_mb"] = round(proc.memory_info().rss / 2**20, 1)
                pm = sorted(st["proc_ms"])
                perf["gesture_frames"] = st["n"]
                perf["rotate_events"] = len(st["lat_ms"])
                perf["gesture_proc_ms_p50"] = round(pm[len(pm) // 2], 3)
                perf["gesture_proc_ms_p95"] = round(pm[int(len(pm) * 0.95)], 3)
                perf["gesture_proc_ms_max"] = round(pm[-1], 3)
                perf["yaw_change_deg"] = round((ctrl.three_d.viewer.yaw - st["yaw0"] + 180) % 360 - 180, 1)
                perf["fps_while_rotating"] = round(ctrl.three_d.viewer.fps, 1)
                QTimer.singleShot(100, step2)
        timer.timeout.connect(tick)
        timer.start()
        st["timer"] = timer

    def step2():
        if "--animate" in sys.argv:
            ok, msg = ctrl.three_d.toggle_animation("smoke")
            perf["motion_mode"] = ctrl.three_d.viewer.motion_mode
            perf["animate_msg"] = msg
            QTimer.singleShot(2000, grab_first)
            return
        if "--assembled" not in sys.argv:
            ctrl.three_d.viewer.explode()
        QTimer.singleShot(1500, grab)

    first: dict = {}

    def part_poses() -> dict:
        # grabWindow lần hai trong cùng tiến trình làm Qt Quick 3D crash → đo chuyển động qua transform của node
        from PySide6.QtCore import QObject
        poses = {}
        for mdl in view.rootObject().findChildren(QObject):
            pid = mdl.objectName()
            if not pid or pid in poses or mdl.metaObject().className().find("Model") < 0:
                continue
            node = mdl.parent()
            while node is not None and node.metaObject().indexOfProperty("mx") < 0:
                node = node.parent()
            if node is None:
                continue
            p, q = node.property("position"), node.property("rotation")
            if p is None or q is None:
                continue
            poses[pid] = (p.x(), p.y(), p.z(), q.scalar(), q.x(), q.y(), q.z())
        return poses

    def grab_first():
        first["poses"] = part_poses()
        QTimer.singleShot(400, grab)

    def moved_parts(a: dict, b: dict) -> int:
        return sum(1 for k in a if k in b and max(abs(u - v) for u, v in zip(a[k], b[k])) > 1e-3)

    def grab():
        img = view.grabWindow()
        img.save(str(out_png))
        from PySide6.QtGui import QColor
        w, h = img.width(), img.height()
        bg = QColor("#0b1424")
        diff = 0
        samples = 0
        for y in range(0, h, 8):
            for x in range(0, w, 8):
                c = img.pixelColor(x, y)
                samples += 1
                if abs(c.red() - bg.red()) + abs(c.green() - bg.green()) + abs(c.blue() - bg.blue()) > 40:
                    diff += 1
        if "poses" in first:
            now = part_poses()
            perf["parts_tracked"] = len(now)
            perf["parts_moving"] = moved_parts(first["poses"], now)
            ro = view.rootObject()
            perf["qml_anim"] = [ro.property("animating"), round(float(ro.property("animTau") or 0), 3),
                                round(float(ro.property("animK") or 0), 3)]
            perf["bridge_animating"] = bridge.viewState.get("animating")
            perf["parts_with_motion"] = sum(1 for p in bridge.model.get("parts", []) if p.get("motion"))
            perf["fps_while_animating"] = round(ctrl.three_d.viewer.fps, 1)
        m = bridge.model
        result.update({"ok": True, "png": str(out_png), "size": [w, h], "content_ratio": round(diff / max(1, samples), 3),
                       "generation_s": round(gen_s, 2), "load_ms": m.get("load_ms"), "parts": len(m.get("parts", [])),
                       "triangles": m.get("triangles"), "fps": round(ctrl.three_d.viewer.fps, 1),
                       "exploded": bridge.viewState.get("exploded"), "qml_warnings": warnings[:10],
                       "open_to_grab_s": round(time.monotonic() - t_open, 2), **perf})
        app.quit()

    QTimer.singleShot(3500, perf_idle if proc else step2)
    QTimer.singleShot(40000, app.quit)
    app.exec()
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("ok") and result.get("content_ratio", 0) > 0.02 and not warnings else 1


if __name__ == "__main__":
    sys.exit(main())
