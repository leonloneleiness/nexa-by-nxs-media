import sys
import time

from nexa.code.checks import run_env
from nexa.code.live_run import LiveRun

env = run_env()
env["PYTHONUNBUFFERED"] = "1"
prog = ("import sys\nprint('Xin chao')\nname = input('Nhap ten: ')\nprint('Chao', name)\n"
        "for i in range(3):\n    print(f'\\r{i*50}%', end='')\nprint()\n"
        "print('loi o day', file=sys.stderr)\nraise ValueError('hong')\n")
r = LiveRun([[sys.executable, "-c", prog]], ".", env, title="t.py").start()
time.sleep(1.0)
print("waiting:", r.waiting_input(), [(ln.kind, ln.text, ln.open) for ln in r.lines])
r.send("An")
r.wait(10)
print(r.state, r.exit_code, r.seconds)
for ln in r.lines:
    print(ln.kind, repr(ln.text))
print(r.render_html()[:300])
