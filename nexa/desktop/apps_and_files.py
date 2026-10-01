"""Mở ứng dụng/URL, thao tác tệp trong phạm vi cho phép và chụp màn hình.

- Không bao giờ chạy lệnh qua shell; không nhận đường dẫn .exe tùy ý từ AI — chỉ mở ứng dụng
  có trong danh sách: ứng dụng dựng sẵn, ứng dụng người dùng thêm trong Settings, lối tắt Start Menu.
- Mọi đường dẫn tệp được resolve và phải nằm trong allowed_roots.
- Xóa luôn vào Recycle Bin (send2trash); không có đường xóa vĩnh viễn.
"""
from __future__ import annotations

import datetime as _dt
import os
import re
import shutil
import subprocess
import time
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from nexa.core.events import ToolResult
from nexa.utils.config import expand_path
from nexa.utils.logging import get_logger
from nexa.utils.text import fold
from nexa.desktop.app_aliases import KnownApp, fuzzy_pick, known_app_for
from nexa.desktop.spoken_names import CODE_EXTS, near_score, parse_spoken_name, score_name
from nexa.desktop.spoken_names import key as name_key

log = get_logger("apps")

EXECUTABLE_EXTS = {".exe", ".bat", ".cmd", ".com", ".ps1", ".psm1", ".vbs", ".vbe", ".js", ".jse", ".wsf", ".wsh",
                   ".msi", ".msp", ".scr", ".pif", ".lnk", ".url", ".jar", ".py", ".pyw", ".hta", ".cpl", ".reg",
                   ".appref-ms", ".application", ".msc", ".sh"}
INVALID_NAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
RESERVED_NAMES = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}
SKIP_DIRS = {"appdata", "node_modules", ".git", "$recycle.bin", "system volume information", "__pycache__", ".venv",
             "venv", "site-packages", "_internal"}


@dataclass
class AppEntry:
    key: str
    name: str
    aliases: list[str] = field(default_factory=list)
    command: list[str] | None = None     # chạy trực tiếp (không shell)
    startfile: str | None = None         # mở qua ShellExecute (lnk, URI)
    process_names: set[str] = field(default_factory=set)
    source: str = "builtin"


def _default_browser_exe() -> str:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\https\UserChoice") as k:
            prog_id, _ = winreg.QueryValueEx(k, "ProgId")
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, rf"{prog_id}\shell\open\command") as k:
            command, _ = winreg.QueryValueEx(k, "")
        m = re.match(r'\s*"([^"]+)"', command) or re.match(r"\s*(\S+)", command)
        if m and Path(m.group(1)).exists():
            return m.group(1)
    except OSError:
        pass
    for candidate in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                      r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
                      r"C:\Program Files\Google\Chrome\Application\chrome.exe"):
        if Path(candidate).exists():
            return candidate
    return ""


class AppLauncher:
    def __init__(self, config: Any, window_manager: Any = None) -> None:
        self.config = config
        self.wm = window_manager
        self._start_menu: list[AppEntry] | None = None
        self._yt_cache: dict[str, tuple[float, int, list[dict[str, str]]]] = {}

    def browser_exe(self) -> str:
        custom = (self.config.get("apps.browser_path") or "").strip()
        if custom and Path(custom).exists():
            return custom
        return _default_browser_exe()

    def builtin_apps(self) -> list[AppEntry]:
        apps = [
            AppEntry("notepad", "Notepad", ["notepad", "not pad", "note pad", "so ghi chep", "trinh soan thao van ban"],
                     command=["notepad.exe"], process_names={"notepad.exe"}),
            AppEntry("explorer", "File Explorer", ["file explorer", "explorer", "trinh quan ly tep", "quan ly file",
                                                   "thu muc", "may tinh cua toi", "this pc"],
                     command=["explorer.exe"], process_names={"explorer.exe"}),
            AppEntry("calculator", "Máy tính (Calculator)", ["calculator", "may tinh bo tui", "may tinh casio", "calc"],
                     command=["calc.exe"], process_names={"calculatorapp.exe", "applicationframehost.exe", "calc.exe"}),
            AppEntry("paint", "Paint", ["paint", "mspaint", "ve"], command=["mspaint.exe"],
                     process_names={"mspaint.exe"}),
            AppEntry("settings", "Cài đặt Windows", ["cai dat windows", "settings", "cai dat he thong"],
                     startfile="ms-settings:", process_names={"systemsettings.exe", "applicationframehost.exe"}),
        ]
        browser = self.browser_exe()
        if browser:
            # Tên riêng (chrome/edge/cốc cốc…) chỉ trỏ vào đây nếu đúng là trình duyệt mặc định; nếu không,
            # "mở Chrome" phải mở Chrome thật (qua Start Menu), không phải trình duyệt mặc định.
            own = {"chrome.exe": ["chrome", "google chrome"], "msedge.exe": ["edge", "microsoft edge"],
                   "browser.exe": ["coc coc"], "firefox.exe": ["firefox"]}.get(Path(browser).name.lower(), [])
            apps.insert(0, AppEntry("browser", f"Trình duyệt ({Path(browser).stem})",
                                    ["trinh duyet", "browser", "trinh duyet web", "web", *own],
                                    command=[browser], process_names={Path(browser).name.lower()}))
        return apps

    def custom_apps(self) -> list[AppEntry]:
        out = []
        for item in self.config.get("apps.custom") or []:
            path = str(item.get("path", "")).strip()
            name = str(item.get("name", "")).strip()
            if not path or not name:
                continue
            aliases = [fold(a) for a in item.get("aliases", []) if a]
            p = Path(os.path.expandvars(path))
            if p.suffix.lower() == ".exe":
                out.append(AppEntry(fold(name), name, [fold(name), *aliases], command=[str(p)],
                                    process_names={p.name.lower()}, source="custom"))
            else:
                out.append(AppEntry(fold(name), name, [fold(name), *aliases], startfile=str(p), source="custom"))
        return out

    def start_menu_apps(self) -> list[AppEntry]:
        if self._start_menu is not None:
            return self._start_menu
        roots = [Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / r"Microsoft\Windows\Start Menu\Programs",
                 Path(os.environ.get("APPDATA", "")) / r"Microsoft\Windows\Start Menu\Programs"]
        entries = []
        for root in roots:
            if not root.exists():
                continue
            for lnk in root.rglob("*.lnk"):
                stem = lnk.stem
                low = fold(stem)
                if any(bad in low for bad in ("uninstall", "go cai dat", "readme", "help", "huong dan")):
                    continue
                entries.append(AppEntry(low, stem, [low], startfile=str(lnk), source="startmenu"))
        self._start_menu = entries
        return entries

    def all_apps(self) -> list[AppEntry]:
        return self.custom_apps() + self.builtin_apps() + self.start_menu_apps()

    def resolve(self, name: str) -> tuple[AppEntry | None, list[AppEntry]]:
        q = fold(name)
        q = re.sub(r"^(ung dung|phan mem|app)\s+", "", q)
        if not q:
            return None, []
        for group in (self.custom_apps(), self.builtin_apps()):
            for app in group:
                if q == fold(app.name) or q in app.aliases:
                    return app, []
        known = known_app_for(q)
        if known is not None:
            entry = self._known_entry(known)
            if entry is not None:
                return entry, []
            q = fold(known.name)
        exact = [a for a in self.start_menu_apps() if a.key == q]
        if len(exact) == 1:
            return exact[0], []
        partial = [a for a in self.start_menu_apps() if q in a.key]
        if len(partial) == 1:
            return partial[0], []
        if exact or partial:
            return None, (exact or partial)[:6]
        # Khớp mờ với mọi ứng dụng đã biết (tên nghe hơi lệch: "zalô", "discot"…), chỉ khi rõ ràng.
        if len(q.replace(" ", "")) >= 4:
            apps = self.custom_apps() + self.builtin_apps() + self.start_menu_apps()
            idx = fuzzy_pick(q, [(i, text) for i, a in enumerate(apps) for text in {a.key, fold(a.name), *a.aliases}])
            if idx is not None:
                return apps[idx], []
        return None, []

    def _known_entry(self, known: KnownApp) -> AppEntry | None:
        """Bản cài trong Start Menu của ứng dụng quen thuộc; nếu chưa cài mà có bản web thì mở trình duyệt."""
        for want in known.installed:
            for group in (self.custom_apps(), self.builtin_apps()):
                for app in group:
                    if want == fold(app.name) or want in app.aliases:
                        return app
            hits = [a for a in self.start_menu_apps() if a.key == want]
            if hits:
                return hits[0]
        if known.url:
            browser = self.browser_exe()
            if browser:
                return AppEntry(fold(known.name), f"{known.name} (web)", [fold(known.name)],
                                command=[browser, known.url], process_names={Path(browser).name.lower()}, source="web")
            return AppEntry(fold(known.name), f"{known.name} (web)", [fold(known.name)], startfile=known.url,
                            source="web")
        return None

    @staticmethod
    def start(app: AppEntry, args: list[str] | None = None) -> ToolResult | None:
        """Chỉ khởi chạy (không chờ cửa sổ). Trả ToolResult lỗi, hoặc None nếu đã gửi lệnh mở."""
        try:
            if app.command:
                subprocess.Popen(app.command + list(args or []), shell=False, close_fds=True)
            elif app.startfile:
                os.startfile(app.startfile)  # noqa: S606 - ShellExecute trên đối tượng đã đăng ký
            else:
                return ToolResult.failure("Ứng dụng chưa có đường dẫn.", "no_path")
        except FileNotFoundError:
            return ToolResult.failure(f"Không tìm thấy {app.name} trên máy. Anh thêm đường dẫn trong Cài đặt > Ứng dụng.",
                                      "not_found")
        except OSError as exc:
            return ToolResult.failure(f"Không mở được {app.name}: {exc.strerror or exc}", "launch_failed")
        return None

    def launch(self, app: AppEntry, args: list[str] | None = None) -> ToolResult:
        before = set(self.wm.api.enum_windows()) if self.wm else set()
        failed = self.start(app, args)
        if failed is not None:
            return failed
        hwnd = None
        if self.wm:
            hwnd = self.wm.wait_for_new_window(before, app.process_names, timeout=8.0)
            if hwnd:
                self.wm.focus(hwnd)
        if hwnd:
            return ToolResult.success(f"Đã mở {app.name}.", verified=True, hwnd=hwnd, app=app.key,
                                      title=self.wm.api.get_title(hwnd))
        return ToolResult(ok=True, verified=False, message=f"Đã gửi lệnh mở {app.name} nhưng em chưa thấy cửa sổ mới.",
                          data={"app": app.key})

    # ----- web -----
    @staticmethod
    def validate_url(url: str) -> str | None:
        url = (url or "").strip()
        if not url:
            return None
        if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", url):
            url = "https://" + url
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc or " " in parsed.netloc:
            return None
        return url

    def open_url(self, url: str) -> ToolResult:
        valid = self.validate_url(url)
        if not valid:
            return ToolResult.failure("Địa chỉ web không hợp lệ (chỉ hỗ trợ http/https).", "bad_url")
        browser = self.browser_exe()
        try:
            if browser:
                subprocess.Popen([browser, valid], shell=False, close_fds=True)
            else:
                os.startfile(valid)  # noqa: S606
        except OSError as exc:
            return ToolResult.failure(f"Không mở được trình duyệt: {exc}", "launch_failed")
        return ToolResult(ok=True, verified=False, message=f"Đã mở {urllib.parse.urlparse(valid).netloc} trong trình duyệt.",
                          data={"url": valid})

    @staticmethod
    def youtube_results(query: str, limit: int = 10, timeout: float = 8.0) -> list[dict[str, str]]:
        """Kết quả tìm kiếm YouTube (videoId, tiêu đề) đọc từ trang kết quả công khai; bỏ qua quảng cáo/playlist."""
        import json
        import urllib.request
        url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(query)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                                                   "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.5"})
        html = urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "ignore")
        m = re.search(r"var ytInitialData = (\{.*?\});</script>", html, re.S)
        if not m:
            return []
        out: list[dict[str, str]] = []

        def walk(node: Any) -> None:
            if len(out) >= limit:
                return
            if isinstance(node, dict):
                v = node.get("videoRenderer")
                if isinstance(v, dict) and v.get("videoId"):
                    title = "".join(r.get("text", "") for r in v.get("title", {}).get("runs", []))
                    out.append({"video_id": v["videoId"], "title": title})
                    return
                for child in node.values():
                    walk(child)
            elif isinstance(node, list):
                for child in node:
                    walk(child)

        walk(json.loads(m.group(1)))
        return out

    YT_CACHE_S = 600.0

    def _cached_youtube_results(self, query: str, limit: int) -> list[dict[str, str]]:
        """Nhớ kết quả tìm 10 phút: "đổi video", "mở video thứ 2" cùng từ khóa không phải tải lại (~1 s mỗi lần)."""
        cache = self._yt_cache
        key = fold(query).strip()
        hit = cache.get(key)
        if hit is not None and time.time() - hit[0] < self.YT_CACHE_S and hit[1] >= limit:
            return hit[2]
        results = self.youtube_results(query, limit=limit)
        if results:
            cache[key] = (time.time(), limit, results)
            while len(cache) > 30:
                cache.pop(next(iter(cache)))
        return results

    def play_youtube(self, query: str, index: int = 1) -> ToolResult:
        query = (query or "").strip()
        if not query:
            return ToolResult.failure("Anh muốn mở video gì ạ?", "empty")
        try:
            results = self._cached_youtube_results(query, max(10, index))
        except Exception as exc:
            return ToolResult.failure(f"Không tìm được trên YouTube (mạng?): {exc}", "network")
        if len(results) < index:
            return ToolResult.failure(f"Không thấy video thứ {index} cho '{query}'.", "not_found")
        video = results[index - 1]
        r = self.open_url(f"https://www.youtube.com/watch?v={video['video_id']}")
        if not r.ok:
            return r
        label = "đầu tiên" if index == 1 else f"thứ {index}"
        data = {"title": video["title"], "video_id": video["video_id"], "query": query}
        # Kiểm chứng: cửa sổ trình duyệt đổi tiêu đề thành tên video (YouTube đặt <title> theo video).
        probe = fold(video["title"])[:18].strip()
        deadline = time.monotonic() + 8.0
        while self.wm is not None and probe and time.monotonic() < deadline:
            for w in self.wm.list_windows(limit=100):
                if probe in fold(w["title"]):
                    return ToolResult.success(f"Đã mở video {label}: {video['title']}.", verified=True,
                                              hwnd=w["hwnd"], **data)
            time.sleep(0.4)
        return ToolResult(ok=True, verified=False,
                          message=f"Em đã gửi lệnh mở video {label} ({video['title']}) nhưng chưa thấy trình duyệt hiện video.",
                          data=data)

    def web_search(self, query: str) -> ToolResult:
        query = (query or "").strip()
        if not query:
            return ToolResult.failure("Anh muốn tìm gì ạ?", "empty")
        template = self.config.get("apps.search_engine") or "https://www.google.com/search?q={query}"
        url = template.replace("{query}", urllib.parse.quote_plus(query))
        r = self.open_url(url)
        if r.ok:
            r.message = f"Đã tìm trên web: {query}."
        return r


class FileService:
    ALIASES = {
        "desktop": "Desktop", "man hinh nen": "Desktop", "tai lieu": "Documents", "documents": "Documents",
        "tai ve": "Downloads", "downloads": "Downloads", "download": "Downloads", "anh": "Pictures",
        "hinh anh": "Pictures", "pictures": "Pictures", "video": "Videos", "nhac": "Music",
    }

    def __init__(self, config: Any) -> None:
        self.config = config
        # Danh sách vừa hỏi lại "anh muốn mở cái nào?" → câu trả lời "số hai" / "cái trong fonts" chọn từ đây.
        self._candidates: list[dict[str, Any]] = []
        self._candidates_at = 0.0
        self._candidates_app = "default"
        # do controller gắn: chạy thử một tệp (CodeService.run_file) cho app="run" ("chạy thử file main.py")
        self.run_hook: Callable[[Path], ToolResult] | None = None

    @property
    def roots(self) -> list[Path]:
        out = []
        for p in self.config.get("files.allowed_roots") or []:
            try:
                out.append(expand_path(p).resolve())
            except OSError:
                continue
        return out

    def check(self, path: str | Path) -> Path:
        raw = Path(os.path.expandvars(os.path.expanduser(str(path))))
        if not raw.is_absolute():
            parts = raw.parts
            alias = self.alias_dir(parts[0]) if parts else None
            if alias is not None:
                raw = alias.joinpath(*parts[1:])
            elif self.roots:
                raw = self.roots[0] / raw
        resolved = raw.resolve()  # resolve cả symlink/junction trước khi kiểm tra phạm vi
        for root in self.roots:
            if resolved == root or resolved.is_relative_to(root):
                return resolved
        raise PermissionError(f"Đường dẫn nằm ngoài các thư mục được phép: {resolved}")

    def alias_dir(self, name: str) -> Path | None:
        from nexa.utils.config import known_folder
        key = fold(name)
        folder = self.ALIASES.get(key)
        if folder:
            return known_folder(folder).resolve()
        return None

    def resolve_folder(self, where: str | None) -> Path:
        if not where:
            return self.roots[0] if self.roots else Path.home()
        alias = self.alias_dir(where)
        return self.check(alias if alias else where)

    @staticmethod
    def validate_name(name: str) -> str | None:
        name = (name or "").strip().rstrip(".")
        if not name or len(name) > 200 or INVALID_NAME.search(name) or name.lower().split(".")[0] in RESERVED_NAMES:
            return None
        return name

    @staticmethod
    def is_executable(path: Path) -> bool:
        return path.suffix.lower() in EXECUTABLE_EXTS

    @staticmethod
    def fingerprint(path: Path) -> str:
        try:
            st = path.stat()
            return f"{path}|{st.st_size}|{st.st_mtime_ns}"
        except OSError:
            return f"{path}|missing"

    def find(self, name: str, where: str | None = None, limit: int | None = None,
             cancelled: Callable[[], bool] = lambda: False, timeout: float = 8.0,
             prefer: list[Path] | None = None) -> ToolResult:
        """Tìm theo tên đọc bằng giọng nói: hiểu "main chấm bay" = main.py, "read.md" ~ README.md (spoken_names).
        Kết quả xếp theo điểm khớp, rồi nằm trong thư mục ưu tiên (dự án VS Code), rồi nông hơn, rồi mới sửa."""
        q = parse_spoken_name(name)
        if not q.stem:
            return ToolResult.failure("Anh muốn tìm tệp tên gì ạ?", "empty")
        try:
            bases = [self.resolve_folder(where)] if where else self.roots
        except PermissionError as exc:
            return ToolResult.failure(str(exc), "out_of_scope")
        limit = limit or int(self.config.get("files.search_limit") or 50)
        found: list[dict[str, Any]] = []
        near: list[dict[str, Any]] = []
        deadline = time.monotonic() + timeout
        scanned = 0
        for base in bases:
            stack = [base]
            while stack:
                if cancelled() or time.monotonic() > deadline:
                    stack.clear()
                    break
                current = stack.pop()
                try:
                    with os.scandir(current) as it:
                        for entry in it:
                            scanned += 1
                            is_dir = entry.is_dir(follow_symlinks=False)
                            if entry.name.startswith(".") and is_dir:
                                continue
                            score = score_name(q, entry.name, is_dir)
                            if score > 0:
                                found.append({"path": entry.path, "name": entry.name, "is_dir": is_dir,
                                              "score": round(score, 3)})
                            elif (ns := near_score(q, entry.name, is_dir)) > 0:
                                near.append({"path": entry.path, "name": entry.name, "is_dir": is_dir,
                                             "score": round(ns, 3)})
                            if is_dir and entry.name.lower() not in SKIP_DIRS:
                                stack.append(Path(entry.path))
                except (PermissionError, FileNotFoundError, OSError):
                    continue
        prefer = [p for p in (prefer or []) if p]

        def mtime(x: dict) -> float:
            try:
                return os.path.getmtime(x["path"])
            except OSError:
                return 0.0

        for x in found:
            x["_rank"] = (-x["score"], *self._place(x["path"], prefer), -mtime(x))
        found.sort(key=lambda x: x.pop("_rank"))
        found = found[:limit]
        heard = f" (em hiểu là '{q.display}')" if name_key(q.display) != name_key(name) else ""
        if not found:
            near.sort(key=lambda x: (-x["score"], *self._place(x["path"], prefer)))
            hint = (" Tên gần giống: " + ", ".join(x["name"] for x in near[:3]) + ".") if near else ""
            return ToolResult.success(f"Không tìm thấy tệp nào tên '{name}'{heard} trong phạm vi cho phép.{hint}",
                                      verified=True, results=[], near=near[:5], scanned=scanned,
                                      understood=q.display)
        return ToolResult.success(f"Tìm thấy {len(found)} kết quả cho '{name}'{heard}.", verified=True, results=found,
                                  scanned=scanned, understood=q.display)

    @staticmethod
    def _place(path: str, prefer: list[Path]) -> tuple[int, int]:
        """(thứ tự thư mục ưu tiên chứa tệp, độ sâu bên trong) — càng nhỏ càng được ưu tiên."""
        p = Path(path)
        for i, d in enumerate(prefer):
            if p.is_relative_to(d):
                return i, len(p.relative_to(d).parts)
        return len(prefer), len(p.parts)

    def open(self, path: str) -> ToolResult:
        try:
            p = self.check(path)
        except PermissionError as exc:
            return ToolResult.failure(str(exc), "out_of_scope")
        if not p.exists():
            return ToolResult.failure(f"Không tồn tại: {p}", "not_found")
        try:
            os.startfile(str(p))  # noqa: S606
        except OSError as exc:
            return ToolResult.failure(f"Không mở được: {exc}", "open_failed")
        return ToolResult(ok=True, verified=False, message=f"Đã mở {p.name}.", data={"path": str(p)})

    def open_by_name(self, name: str, kind: str = "any", where: str | None = None,
                     cancelled: Callable[[], bool] = lambda: False, app: str = "default") -> ToolResult:
        """Tìm theo tên (đọc bằng giọng nói) rồi mở. Ưu tiên: trùng tên > chứa tên > gần đúng theo âm; ngang điểm
        thì tệp trong dự án VS Code đang mở, nông hơn. Vẫn ngang nhau thì liệt kê để anh chọn thay vì mở bừa.
        app="vscode": mở bằng VS Code ("mở file main.py trong VS Code"); app="run": chạy thử tệp (run_hook)."""
        app = app if app in ("vscode", "run") else "default"
        picked = self._pick_candidate(name, where)
        if picked is not None:
            return self._open_entry(picked, app if app != "default" else self._candidates_app)
        q = parse_spoken_name(name)
        prefer: list[Path] = []
        if app in ("vscode", "run") or q.ext in CODE_EXTS:
            from nexa.desktop.office import vscode_workspaces
            prefer = vscode_workspaces()
        r = self.find(name, where, cancelled=cancelled, prefer=prefer)
        if not r.ok:
            return r
        if app == "run":
            kind = "file"
        results = [x for x in r.data.get("results", [])
                   if kind == "any" or (kind == "folder") == bool(x["is_dir"])]
        if not results and kind == "folder" and q.ext:
            # "Mở thư mục Public HTML" mà có đuôi tệp → thật ra anh muốn tệp public.html (log 24/09).
            results = [x for x in r.data.get("results", []) if not x["is_dir"]]
        what = "thư mục" if kind == "folder" else "tệp"
        suffix = " trong VS Code" if app == "vscode" else ""
        verb = "chạy thử" if app == "run" else "mở"
        resume = f"{verb} {'thư mục' if kind == 'folder' else 'tệp'} {{}}{suffix}"
        if not results:
            heard = f" (em nghe là '{q.display}')" if name_key(q.display) != name_key(name) else ""
            near = r.data.get("near") or []
            if near:
                # "public.html" không có, nhưng có popup.html: đưa ra để anh chọn bằng số thay vì chỉ báo không thấy.
                self._candidates, self._candidates_at, self._candidates_app = near[:3], time.monotonic(), app
                listing = "; ".join(f"{i}. {x['name']} ({self._short_parent(x['path'])})"
                                    for i, x in enumerate(near[:3], 1))
                return ToolResult.failure(f"Em không thấy {what} '{name}'{heard}. Có phải anh muốn: {listing}? "
                                          f"Anh nói số để em {verb}.", "ambiguous",
                                          candidates=[x["path"] for x in near[:3]], resume=resume)
            return ToolResult.failure(f"Em không thấy {what} nào tên '{name}'{heard} trong các thư mục được phép.",
                                      "not_found")
        best = results[0]
        unique = len(results) == 1 or best["score"] - results[1]["score"] >= 0.02
        if not unique and prefer:
            place, second = self._place(best["path"], prefer), self._place(results[1]["path"], prefer)
            unique = place[0] < len(prefer) and place < second
        if unique:
            opened = self._open_entry(best, app)
            if opened.ok:
                opened.data["candidates"] = len(results)
                if best["score"] < 0.95:
                    opened.message = opened.message.rstrip(".") + f" (gần nhất với '{name}')."
            return opened
        top = results[:5]
        self._candidates, self._candidates_at, self._candidates_app = top, time.monotonic(), app
        listing = "; ".join(f"{i}. {x['name']} ({self._short_parent(x['path'])})" for i, x in enumerate(top, 1))
        return ToolResult.failure(f"Em thấy {len(results)} {what} khớp: {listing}. Anh muốn {verb} cái nào (nói số)?",
                                  "ambiguous", candidates=[x["path"] for x in top], resume=resume)

    @staticmethod
    def _short_parent(path: str) -> str:
        parts = Path(path).parent.parts
        return "\\".join(parts[-2:]) if len(parts) >= 2 else str(Path(path).parent)

    _ORDINALS = {"1": 1, "mot": 1, "nhat": 1, "dau": 1, "dau tien": 1, "2": 2, "hai": 2, "nhi": 2, "3": 3, "ba": 3,
                 "4": 4, "bon": 4, "tu": 4, "5": 5, "nam": 5}

    def _pick_candidate(self, name: str, where: str | None) -> dict[str, Any] | None:
        """Câu trả lời cho "anh muốn mở cái nào?": "số hai", "cái đầu tiên", "cái cuối", "cái trong fonts"."""
        if not self._candidates or time.monotonic() - self._candidates_at > 120:
            return None
        u = fold(f"{name} trong {where}" if where else name)
        u = re.sub(r"^(?:cai|tep|file|thu muc|folder)\s+", "", u)
        m = re.fullmatch(r"(?:so|thu|so thu)?\s*(\w+(?: tien)?)", u)
        if m and m.group(1) in self._ORDINALS and self._ORDINALS[m.group(1)] <= len(self._candidates):
            return self._candidates[self._ORDINALS[m.group(1)] - 1]
        if re.fullmatch(r"(?:so |thu )?cuoi(?: cung)?", u):
            return self._candidates[-1]
        m = re.fullmatch(r"(?:(?:nam )?(?:trong|o|tai) )(.+)", u)
        if m:
            want = name_key(m.group(1))
            hits = [x for x in self._candidates if want and want in name_key(str(Path(x["path"]).parent))]
            if len(hits) == 1:
                return hits[0]
        return None

    # Tệp script: mở bằng os.startfile sẽ CHẠY nó (main.py chạy Python) → mở trong VS Code để xem/sửa.
    SCRIPT_EXTS = {".py", ".pyw", ".js", ".jse", ".vbs", ".vbe", ".ps1", ".psm1", ".bat", ".cmd", ".sh", ".wsf", ".wsh",
                   ".hta", ".reg"}

    def _open_entry(self, x: dict[str, Any], app: str) -> ToolResult:
        self._candidates = []
        try:
            p = self.check(x["path"])
        except PermissionError as exc:
            return ToolResult.failure(str(exc), "out_of_scope")
        if app == "run":
            if x["is_dir"]:
                return ToolResult.failure(f"'{p.name}' là thư mục — anh nói tên tệp cần chạy thử nhé.", "is_dir")
            if self.run_hook is None:
                return ToolResult.failure("Tính năng chạy thử đang tắt.", "unavailable")
            return self.run_hook(p)
        script = not x["is_dir"] and p.suffix.lower() in self.SCRIPT_EXTS
        if app == "vscode" or script:
            from nexa.desktop.office import find_vscode, open_in_vscode
            exe = find_vscode()
            if exe:
                return open_in_vscode(str(p), exe)
            if app == "vscode":
                return ToolResult.failure("Em không tìm thấy VS Code trên máy.", "not_found")
        if not x["is_dir"] and self.is_executable(p):
            return ToolResult.failure(f"'{p.name}' là tệp chạy chương trình nên em không tự mở. Anh cần chạy nó thì "
                                      f"bảo em mở đường dẫn {p} để em hỏi xác nhận.", "executable", path=str(p))
        return self.open(str(p))

    def create_folder(self, parent: str | None, name: str) -> ToolResult:
        clean = self.validate_name(name)
        if not clean:
            return ToolResult.failure("Tên thư mục không hợp lệ.", "bad_name")
        try:
            base = self.resolve_folder(parent)
            target = self.check(base / clean)
        except PermissionError as exc:
            return ToolResult.failure(str(exc), "out_of_scope")
        if target.exists():
            return ToolResult.failure(f"Đã có '{clean}' trong {base}.", "exists")
        target.mkdir(parents=False)
        return ToolResult.success(f"Đã tạo thư mục {target}.", verified=target.is_dir(), path=str(target))

    def rename(self, path: str, new_name: str) -> ToolResult:
        clean = self.validate_name(new_name)
        if not clean:
            return ToolResult.failure("Tên mới không hợp lệ.", "bad_name")
        try:
            src = self.check(path)
            dst = self.check(src.parent / clean)
        except PermissionError as exc:
            return ToolResult.failure(str(exc), "out_of_scope")
        if not src.exists():
            return ToolResult.failure(f"Không tồn tại: {src}", "not_found")
        if dst.exists():
            return ToolResult.failure(f"Đã có '{clean}' trong cùng thư mục; em không ghi đè.", "exists")
        src.rename(dst)
        return ToolResult.success(f"Đã đổi tên thành {clean}.", verified=dst.exists() and not src.exists(), path=str(dst))

    def _transfer(self, path: str, dest_dir: str, overwrite: bool, move: bool) -> ToolResult:
        try:
            src = self.check(path)
            dst_dir = self.resolve_folder(dest_dir)
            dst = self.check(dst_dir / src.name)
        except PermissionError as exc:
            return ToolResult.failure(str(exc), "out_of_scope")
        if not src.exists():
            return ToolResult.failure(f"Không tồn tại: {src}", "not_found")
        if not dst_dir.is_dir():
            return ToolResult.failure(f"Thư mục đích không tồn tại: {dst_dir}", "not_found")
        if dst == src or (src.is_dir() and dst.is_relative_to(src)):
            return ToolResult.failure("Nguồn và đích trùng hoặc lồng nhau.", "same_path")
        if dst.exists():
            if not overwrite:
                return ToolResult.failure(f"'{dst.name}' đã có ở thư mục đích. Cần xác nhận ghi đè.", "exists")
            from send2trash import send2trash
            send2trash(str(dst))  # ghi đè = đưa bản cũ vào Recycle Bin trước
        if move:
            shutil.move(str(src), str(dst))
        elif src.is_dir():
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)
        verb = "chuyển" if move else "sao chép"
        return ToolResult.success(f"Đã {verb} {src.name} tới {dst_dir}.", verified=dst.exists(), path=str(dst))

    def copy(self, path: str, dest_dir: str, overwrite: bool = False) -> ToolResult:
        return self._transfer(path, dest_dir, overwrite, move=False)

    def move(self, path: str, dest_dir: str, overwrite: bool = False) -> ToolResult:
        return self._transfer(path, dest_dir, overwrite, move=True)

    def delete_to_recycle_bin(self, path: str) -> ToolResult:
        try:
            p = self.check(path)
        except PermissionError as exc:
            return ToolResult.failure(str(exc), "out_of_scope")
        if not p.exists():
            return ToolResult.failure(f"Không tồn tại: {p}", "not_found")
        if p in self.roots:
            return ToolResult.failure("Không xóa thư mục gốc được phép.", "protected")
        from send2trash import send2trash
        send2trash(str(p))
        return ToolResult.success(f"Đã chuyển {p.name} vào Thùng rác (Recycle Bin).", verified=not p.exists(), path=str(p))


class Screenshotter:
    def __init__(self, config: Any) -> None:
        self.config = config

    @property
    def folder(self) -> Path:
        return expand_path(self.config.get("files.screenshot_dir") or "{Pictures}/NEXA").resolve()

    def capture(self, monitor_rect: tuple[int, int, int, int] | None = None) -> ToolResult:
        import mss
        import mss.tools
        folder = self.folder
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"NEXA_{_dt.datetime.now():%Y%m%d_%H%M%S}.png"
        with mss.mss() as sct:
            if monitor_rect:
                l, t, r, b = monitor_rect
                region = {"left": l, "top": t, "width": r - l, "height": b - t}
            else:
                region = sct.monitors[0]  # toàn bộ virtual desktop (mọi màn hình)
            shot = sct.grab(region)
            mss.tools.to_png(shot.rgb, shot.size, output=str(path))
        ok = path.exists() and path.stat().st_size > 0
        if not ok:
            return ToolResult.failure("Không lưu được ảnh chụp màn hình.", "save_failed")
        return ToolResult.success(f"Đã chụp màn hình, lưu tại {path}.", verified=True, path=str(path),
                                  width=shot.size[0], height=shot.size[1])

    @staticmethod
    def grab_image(rect: tuple[int, int, int, int]):
        """Trả về PIL.Image của một vùng (dùng cho 'Đọc màn hình')."""
        import mss
        from PIL import Image
        l, t, r, b = rect
        with mss.mss() as sct:
            shot = sct.grab({"left": l, "top": t, "width": max(1, r - l), "height": max(1, b - t)})
        return Image.frombytes("RGB", shot.size, shot.rgb)
