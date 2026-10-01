"""Thử đăng ký nhận trạng thái màn hình + suspend/resume bằng callback (không cần cửa sổ)."""
import sys, time
sys.path.insert(0, ".")
from nexa.desktop.sleep_guard import PowerEventMonitor

states = []
m = PowerEventMonitor(on_display=lambda s: states.append(s), on_suspend=lambda: print("suspend"),
                      on_resume=lambda: print("resume"))
print("start", m.start())
time.sleep(1.0)
print("display states:", states, "current:", m.display_state)
m.stop()
print("stopped")
