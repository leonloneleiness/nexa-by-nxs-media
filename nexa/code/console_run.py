"""Chạy thử một tệp trên đĩa trong cửa sổ console RIÊNG: anh thấy đầu ra trực tiếp và nhập được dữ liệu (input/scanf).

NEXA ghi kế hoạch chạy ra một tệp JSON rồi mở chính nó ở chế độ `--nexa-console-run <spec.json>` trong console mới
(bản đóng gói: NEXA.exe; khi chạy từ mã nguồn: python.exe main.py). Tiến trình đó chạy lần lượt các bước build/chạy,
in mã thoát + thời gian, ghi kết quả ra JSON cho NEXA đọc, rồi chờ anh nhấn Enter mới đóng cửa sổ.
Biến môi trường chứa KEY/TOKEN/SECRET/PASSWORD (khóa Gemini…) bị bỏ trước khi chạy code.
"""
from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

NEW_CONSOLE = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
FLAG = "--nexa-console-run"


def runner_command(spec: Path) -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, FLAG, str(spec)]
    exe = Path(sys.executable)
    if exe.name.lower() == "pythonw.exe" and exe.with_name("python.exe").is_file():
        exe = exe.with_name("python.exe")          # pythonw không có console để hiện đầu ra
    main = Path(__file__).resolve().parents[2] / "main.py"
    return [str(exe), str(main), FLAG, str(spec)]


def launch(steps: list[list[str]], cwd: Path, title: str, env: dict[str, str]) -> tuple[subprocess.Popen, Path]:
    """Mở console chạy các bước; trả (tiến trình console, đường dẫn tệp kết quả sẽ được ghi)."""
    work = Path(tempfile.mkdtemp(prefix="nexa_console_run_"))
    result = work / "result.json"
    spec = work / "spec.json"
    spec.write_text(json.dumps({"title": title, "cwd": str(cwd), "steps": steps, "result": str(result)},
                               ensure_ascii=False), encoding="utf-8")
    proc = subprocess.Popen(runner_command(spec), cwd=str(cwd), env=env, creationflags=NEW_CONSOLE, close_fds=True)
    return proc, result


# ------------------------------------------------------------------ phía cửa sổ console
def _prepare_console(title: str) -> None:
    k32 = ctypes.windll.kernel32
    if k32.AllocConsole():                          # NEXA.exe là ứng dụng cửa sổ: tự xin console (đã có thì trả 0)
        sys.stdout = open("CONOUT$", "w", encoding="utf-8", buffering=1)
        sys.stderr = sys.stdout
        sys.stdin = open("CONIN$", "r", encoding="utf-8")
    k32.SetConsoleOutputCP(65001)
    k32.SetConsoleCP(65001)
    k32.SetConsoleTitleW(title)
    try:
        sys.stdout.reconfigure(encoding="utf-8")    # type: ignore[union-attr]
        sys.stdin.reconfigure(encoding="utf-8")     # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass


def _shown(cmd: list[str]) -> str:
    return " ".join(Path(c).name if i == 0 else (c if len(c) < 160 else "…") for i, c in enumerate(cmd))


def console_main(spec_path: str) -> int:
    spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    title = spec.get("title") or "NEXA chạy thử"
    _prepare_console(f"NEXA chạy thử — {title}")
    cwd = spec.get("cwd") or os.getcwd()
    steps: list[list[str]] = spec.get("steps") or []
    print(f"▶ NEXA chạy thử: {title}\n  Thư mục: {cwd}\n" + "─" * 60, flush=True)
    t0 = time.monotonic()
    code: int | None = 0
    build_failed = interrupted = False
    for i, step in enumerate(steps):
        last = i == len(steps) - 1
        if len(steps) > 1:
            print(f"$ {_shown(step)}", flush=True)
        try:
            code = subprocess.call(step, cwd=cwd)
        except KeyboardInterrupt:
            code, interrupted = None, True
        except OSError as exc:
            print(f"Không chạy được lệnh: {exc}", flush=True)
            code = None
        if code != 0:
            if not last and not interrupted:
                build_failed = True
                print("\n✗ Biên dịch lỗi — chưa chạy chương trình.", flush=True)
            break
    secs = time.monotonic() - t0
    print("\n" + "─" * 60)
    if interrupted:
        print(f"■ Đã dừng (Ctrl+C) sau {secs:.1f} s.")
    else:
        print(f"■ Kết thúc: mã thoát {code} sau {secs:.1f} s" + (" — KHÔNG lỗi." if code == 0 else "."))
    try:
        Path(spec["result"]).write_text(json.dumps({"exit_code": code, "seconds": round(secs, 2),
                                                    "build_failed": build_failed, "interrupted": interrupted}),
                                        encoding="utf-8")
    except (OSError, KeyError):
        pass
    try:
        input("Nhấn Enter để đóng cửa sổ…")
    except (EOFError, KeyboardInterrupt):
        pass
    return 0 if code == 0 else 1
