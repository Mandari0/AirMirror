#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AirMirror - AirPlay receiver tray app for Windows (UxPlay front-end)."""

import ctypes
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
import traceback
import winreg
from pathlib import Path

FROZEN = bool(getattr(sys, "frozen", False))
APP_DIR = Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parent
RES_DIR = Path(getattr(sys, "_MEIPASS", APP_DIR)) if FROZEN else APP_DIR

DATA_DIR = Path(os.environ.get("APPDATA", str(APP_DIR))) / "AirMirror"
OLD_DATA_DIR = Path(os.environ.get("APPDATA", str(APP_DIR))) / "AirPlay"
try:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    DATA_DIR = APP_DIR

SETTINGS_FILE = DATA_DIR / "settings.json"
UXPLAY_LOG = DATA_DIR / "uxplay.log"
ERROR_LOG = DATA_DIR / "tray-error.log"
ICON_FILE = DATA_DIR / "airmirror.ico"
NOWPLAYING_FILE = DATA_DIR / "nowplaying.txt"
COVERART_FILE = DATA_DIR / "coverart.bin"


def migrate_data_dir():
    """One-time move of settings from the old AirPlay-named build."""
    if OLD_DATA_DIR == DATA_DIR or not OLD_DATA_DIR.exists():
        return
    try:
        if SETTINGS_FILE.exists():
            return
        old_settings = OLD_DATA_DIR / "settings.json"
        if old_settings.exists():
            shutil.copyfile(old_settings, SETTINGS_FILE)
    except Exception:
        pass

BUNDLED_UXPLAY = APP_DIR / "uxplay" / "bin" / "uxplay.exe"
SYSTEM_UXPLAY = Path(r"C:\msys64\ucrt64\bin\uxplay.exe")


def uxplay_paths():
    """Return (executable, runtime_root). runtime_root is None for a system install."""
    if BUNDLED_UXPLAY.exists():
        return BUNDLED_UXPLAY, BUNDLED_UXPLAY.parent.parent
    return SYSTEM_UXPLAY, None


def migrate_old_settings():
    """Keep settings from a pre-installer (portable) run."""
    old = APP_DIR / "settings.json"
    if old == SETTINGS_FILE or SETTINGS_FILE.exists() or not old.exists():
        return
    try:
        shutil.copyfile(old, SETTINGS_FILE)
    except Exception:
        pass

CREATE_NO_WINDOW = 0x08000000

DEFAULTS = {
    "name": "AirMirror",
    "window_title": "",
    "resolution": "auto",
    "fps": 60,
    "sync": False,
    "audio": True,
    "fullscreen": False,
    "now_playing": True,
    "animated_backdrop": True,
    "always_on_top": False,
    "language": "en",
}

RESOLUTION_KEYS = [
    "auto",
    "1280x720@60",
    "1920x1080@60",
    "2560x1440@60",
    "3840x2160@30",
]
FPS_CHOICES = [30, 60]

LANGUAGES = [("en", "English"), ("ru", "Русский")]


# ---------------------------------------------------------------- settings ---

def load_settings():
    data = dict(DEFAULTS)
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8-sig") as fh:
            data.update(json.load(fh))
    except Exception:
        pass
    return data


def save_settings(data):
    tmp = SETTINGS_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, SETTINGS_FILE)


# ------------------------------------------------------------------- i18n ---

STRINGS = {
    # settings window
    "settings_title": {"en": "AirMirror Settings", "ru": "Настройки AirMirror"},
    "settings_window_title": {"en": "AirMirror Settings", "ru": "Настройки — AirMirror"},
    "settings_subtitle": {"en": "AirPlay receiver for iPhone and iPad",
                          "ru": "Приёмник AirPlay для iPhone и iPad"},
    "save": {"en": "Save", "ru": "Сохранить"},
    "cancel": {"en": "Cancel", "ru": "Отмена"},
    "section_connection": {"en": "CONNECTION", "ru": "ПОДКЛЮЧЕНИЕ"},
    "device_name": {"en": "Device name", "ru": "Имя устройства"},
    "device_name_hint": {"en": "how the PC appears in the AirPlay menu on your phone",
                         "ru": "как ПК называется в меню AirPlay на телефоне"},
    "window_title": {"en": "Mirroring window title", "ru": "Название окна трансляции"},
    "window_title_hint": {"en": "empty — the device name is used",
                          "ru": "пусто — будет имя устройства"},
    "section_quality": {"en": "QUALITY AND LATENCY", "ru": "КАЧЕСТВО И ЗАДЕРЖКА"},
    "resolution": {"en": "Resolution", "ru": "Разрешение"},
    "resolution_hint": {"en": "video frame from the phone", "ru": "кадр трансляции с телефона"},
    "resolution_auto": {"en": "Auto (1920×1080)", "ru": "Авто (1920×1080)"},
    "fps": {"en": "Frames per second", "ru": "Кадров в секунду"},
    "fps_hint": {"en": "smoothness vs. load", "ru": "плавность против нагрузки"},
    "section_behavior": {"en": "BEHAVIOR", "ru": "ПОВЕДЕНИЕ"},
    "now_playing_title": {"en": "Mini player for music", "ru": "Мини-плеер для музыки"},
    "now_playing_hint": {"en": "track, artwork and progress for AirPlay audio",
                         "ru": "трек, обложка и прогресс при AirPlay-аудио"},
    "animated_backdrop_title": {"en": "Animated player background",
                                "ru": "Анимированный фон плеера"},
    "animated_backdrop_hint": {"en": "cover colours slowly drift behind the mini player",
                               "ru": "цвета обложки плавно переливаются за мини-плеером"},
    "sync_title": {"en": "Audio and video sync", "ru": "Синхронизация аудио и видео"},
    "sync_hint": {"en": "precise sync, slightly higher latency",
                  "ru": "точная синхронизация, но чуть выше задержка"},
    "audio_title": {"en": "Send audio", "ru": "Передавать звук"},
    "audio_hint": {"en": "turn off if you only need the screen",
                   "ru": "выключить, если нужен только экран"},
    "fullscreen_title": {"en": "Full screen on connect", "ru": "Полный экран при подключении"},
    "fullscreen_hint": {"en": "the mirroring window fills the screen right away",
                        "ru": "окно трансляции сразу на весь экран"},
    "autostart_title": {"en": "Start with Windows", "ru": "Запускать при входе в Windows"},
    "autostart_hint": {"en": "tray icon appears right after sign-in",
                       "ru": "иконка в трее сразу после входа"},
    "language_hint": {"en": "Interface language · applied after saving",
                      "ru": "Язык интерфейса · применится после сохранения"},
    # mini player
    "player_title": {"en": "Now playing — AirMirror", "ru": "Сейчас играет — AirMirror"},
    "now_playing": {"en": "Now playing", "ru": "Сейчас играет"},
    "always_on_top": {"en": "Always on top", "ru": "Поверх всех окон"},
    "close": {"en": "Close", "ru": "Закрыть"},
    "unknown_track": {"en": "Unknown track", "ru": "Неизвестный трек"},
    # tray menu
    "tray_settings": {"en": "Settings", "ru": "Настройки"},
    "tray_resolution": {"en": "Resolution", "ru": "Разрешение"},
    "tray_stop": {"en": "Stop streaming", "ru": "Остановить трансляцию"},
    "tray_restart": {"en": "Restart server", "ru": "Перезапустить сервер"},
    "tray_log": {"en": "Open log", "ru": "Открыть журнал"},
    "tray_quit": {"en": "Quit", "ru": "Закрыть программу"},
    # notifications
    "notif_server_restarted": {"en": "Server restarted", "ru": "Сервер перезапущен"},
    "notif_session_stopped": {"en": "Streaming stopped", "ru": "Трансляция остановлена"},
    "notif_log_empty": {"en": "The log is empty", "ru": "Журнал пока пуст"},
    "notif_started_title": {"en": "AirMirror started", "ru": "AirMirror запущен"},
    "notif_started_msg": {"en": "“{name}” is available on the network",
                          "ru": "«{name}» доступен в сети"},
    "notif_settings_title": {"en": "Settings applied", "ru": "Настройки применены"},
    "notif_settings_restart": {"en": "Server restarted: “{name}”",
                               "ru": "Сервер перезапущен: «{name}»"},
    "notif_settings_saved": {"en": "Changes saved", "ru": "Изменения сохранены"},
    # errors
    "err_uxplay_missing": {"en": "uxplay.exe not found:\n{path}",
                           "ru": "Не найден uxplay.exe:\n{path}"},
    "err_already_running": {"en": "AirMirror is already running — look for the tray icon.",
                            "ru": "AirMirror уже запущен — ищите иконку в трее."},
    "err_start_failed": {"en": "Could not start AirMirror. See tray-error.log for details.",
                         "ru": "Не удалось запустить AirMirror. Подробности в tray-error.log"},
}

LANGUAGE = "en"  # current UI language; English until settings say otherwise


def tr(key, **fmt):
    """Translate a UI string for the current language (falls back to English)."""
    entry = STRINGS.get(key)
    if not entry:
        return key
    text = entry.get(LANGUAGE) or entry.get("en") or key
    if fmt:
        try:
            text = text.format(**fmt)
        except Exception:
            pass
    return text


def init_language(cfg=None):
    global LANGUAGE
    if cfg is None:
        cfg = load_settings()
    value = str(cfg.get("language", DEFAULTS["language"])).strip().lower()
    LANGUAGE = "ru" if value.startswith("ru") else "en"
    return LANGUAGE


def resolution_label(key):
    """Language-aware label for a resolution key."""
    if key == "auto":
        return tr("resolution_auto")
    res, _, fps = key.partition("@")
    res = res.replace("x", "×")
    return f"{res} @ {fps}" if fps else res


# ---------------------------------------------------------------- autostart ---

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "AirMirror"


def _autostart_command():
    if FROZEN:
        return f'"{sys.executable}"'
    return f'"{sys.executable}" "{APP_DIR / "AirMirror.py"}"'


def autostart_enabled():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, RUN_VALUE)
            return bool(value)
    except Exception:
        return False


def set_autostart(enabled):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, RUN_VALUE, 0, winreg.REG_SZ, _autostart_command())
            else:
                try:
                    winreg.DeleteValue(key, RUN_VALUE)
                except FileNotFoundError:
                    pass
        return True
    except Exception:
        return False


# ----------------------------------------------------------------- palette ---

def system_is_dark():
    override = (os.environ.get("AIRMIRROR_THEME") or os.environ.get("AIRPLAY_THEME", "")).strip().lower()
    if override == "light":
        return False
    if override == "dark":
        return True
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        )
        value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        return value == 0
    except Exception:
        return False


def blend(c1, c2, t):
    """Mix two #rrggbb colours (t=0 → c1, t=1 → c2)."""
    t = max(0.0, min(1.0, t))
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def ease_out(t):
    """Cubic ease-out for short UI animations."""
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def round_window_corners(win):
    """Ask Windows 11 to round the window frame (no-op on Windows 10)."""
    try:
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
        pref = ctypes.c_int(2)  # DWMWCP_ROUND
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, 33, ctypes.byref(pref), ctypes.sizeof(pref)
        )
    except Exception:
        pass


class Animator:
    """Small frame-based tween helper bound to a Tk widget."""

    def __init__(self, widget):
        self.widget = widget
        self.job = None

    def cancel(self):
        if self.job is not None:
            try:
                self.widget.after_cancel(self.job)
            except Exception:
                pass
            self.job = None

    def run(self, duration_ms, on_frame, on_done=None, step_ms=16):
        """on_frame receives an eased 0..1 progress value."""
        self.cancel()
        frames = max(1, int(duration_ms / step_ms))
        state = {"i": 0}

        def tick():
            self.job = None
            try:
                if not self.widget.winfo_exists():
                    return
            except Exception:
                return
            state["i"] += 1
            on_frame(ease_out(state["i"] / frames))
            if state["i"] < frames:
                self.job = self.widget.after(step_ms, tick)
            elif on_done is not None:
                on_done()

        self.job = self.widget.after(step_ms, tick)


def palette(dark):
    if dark:
        return {
            "bg": "#1c1c1e", "card": "#2c2c2e", "fg": "#f2f2f7",
            "muted": "#98989f", "accent": "#5a5a5e", "border": "#3a3a3c",
            "hover": "#3a3a3c",
        }
    return {
        "bg": "#f2f2f7", "card": "#ffffff", "fg": "#1c1c1e",
        "muted": "#6e6e73", "accent": "#8e8e93", "border": "#d8d8dd",
        "hover": "#ececf0",
    }


# -------------------------------------------------------------------- icon ---

def build_icon_image(size=256):
    """Neutral 'two mirrored screens' icon (no Apple trademarks)."""
    from PIL import Image, ImageDraw

    scale = 4
    s = size * scale
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))

    def px(v):
        return int(round(v * s / 256.0))

    # rounded square with a subtle vertical gradient
    top, bottom = (64, 70, 80), (30, 33, 38)
    grad = Image.new("RGB", (s, s))
    gd = ImageDraw.Draw(grad)
    for y in range(s):
        t = y / (s - 1)
        gd.line([(0, y), (s, y)],
                fill=tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [px(8), px(8), px(248), px(248)], radius=px(56), fill=255
    )
    img.paste(grad, (0, 0), mask)

    d = ImageDraw.Draw(img)
    # back screen
    d.rounded_rectangle(
        [px(50), px(58), px(164), px(146)], radius=px(12),
        outline=(255, 255, 255, 255), width=px(11),
    )
    # front screen, overlapping the back one
    d.rounded_rectangle(
        [px(92), px(100), px(206), px(188)], radius=px(12),
        fill=(40, 44, 50, 255), outline=(255, 255, 255, 255), width=px(11),
    )
    # two lines of "content" on the front screen
    d.rounded_rectangle([px(108), px(120), px(152), px(130)],
                        radius=px(5), fill=(154, 160, 166, 255))
    d.rounded_rectangle([px(108), px(142), px(176), px(152)],
                        radius=px(5), fill=(110, 115, 122, 255))
    return img.resize((size, size), Image.LANCZOS)


def ensure_icon_file():
    if ICON_FILE.exists():
        return
    try:
        bundled = RES_DIR / "airmirror.ico"
        if bundled.exists() and bundled != ICON_FILE:
            shutil.copyfile(bundled, ICON_FILE)
        else:
            build_icon_image(256).save(ICON_FILE, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    except Exception:
        pass


# ------------------------------------------------------------------ server ---

class UxPlayServer:
    def __init__(self):
        self.proc = None
        self._log = None

    @staticmethod
    def build_args(cfg):
        args = ["-n", cfg["name"], "-vs", "d3d12videosink", "-fps", str(cfg["fps"])]
        if cfg.get("now_playing", True):
            args += ["-md", str(NOWPLAYING_FILE), "-ca", str(COVERART_FILE)]
        if not cfg["sync"]:
            args += ["-vsync", "no"]
        if not cfg["audio"]:
            args += ["-as", "0"]
        if cfg["fullscreen"]:
            args += ["-fs"]
        if cfg["resolution"] != "auto":
            args += ["-s", cfg["resolution"]]
        return args

    @staticmethod
    def kill_stale():
        """Kill uxplay processes left over from a previous (crashed) run."""
        try:
            subprocess.run(
                ["taskkill", "/F", "/IM", "uxplay.exe"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=CREATE_NO_WINDOW,
            )
        except Exception:
            pass

    def start(self, cfg):
        self.kill_stale()
        self.stop()
        exe, runtime = uxplay_paths()
        env = os.environ.copy()
        if runtime is not None:
            env["PATH"] = str(exe.parent) + os.pathsep + env.get("PATH", "")
            env["GST_PLUGIN_PATH_1_0"] = str(runtime / "lib" / "gstreamer-1.0")
            env["GST_PLUGIN_SYSTEM_PATH_1_0"] = ""
            env["GST_PLUGIN_SCANNER"] = str(
                runtime / "libexec" / "gstreamer-1.0" / "gst-plugin-scanner.exe"
            )
            env["GSETTINGS_SCHEMA_DIR"] = str(runtime / "share" / "glib-2.0" / "schemas")
            env["GST_REGISTRY"] = str(DATA_DIR / "gst-registry.bin")
            env["GST_REGISTRY_1_0"] = str(DATA_DIR / "gst-registry.bin")
        self._log = open(UXPLAY_LOG, "ab", buffering=0)
        self._log.write(("\n=== " + "-" * 60 + " ===\n").encode())
        self._log.write(("ARGS: " + " ".join(self.build_args(cfg)) + "\n").encode())
        self.proc = subprocess.Popen(
            [str(exe)] + self.build_args(cfg),
            cwd=str(DATA_DIR),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=self._log,
            stderr=subprocess.STDOUT,
            creationflags=CREATE_NO_WINDOW,
        )

    def stop(self):
        if self.proc is not None and self.proc.poll() is None:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=4)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
        self.proc = None
        if self._log is not None:
            try:
                self._log.close()
            except Exception:
                pass
            self._log = None

    def running(self):
        return self.proc is not None and self.proc.poll() is None


# -------------------------------------------------------------- window title ---

WM_SETICON = 0x0080
IMAGE_ICON = 1
LR_LOADFROMFILE = 0x0010
LR_DEFAULTSIZE = 0x0040


def windows_of_pid(pid):
    """Return visible top-level window handles owned by the given process."""
    user32 = ctypes.windll.user32
    found = []
    proto = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def callback(hwnd, _lparam):
        owner = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and user32.IsWindowVisible(hwnd):
            if user32.GetWindowTextLengthW(hwnd) > 0:
                found.append(hwnd)
        return True

    user32.EnumWindows(proto(callback), 0)
    return found


class WindowRenamer(threading.Thread):
    """Keeps renaming UxPlay's mirroring window (and gives it our icon)."""

    def __init__(self, app):
        super().__init__(daemon=True)
        self.app = app
        self._stop = threading.Event()
        self._styled = set()
        self.mirroring = False

    def stop(self):
        self._stop.set()

    def _apply_icon(self, hwnd):
        try:
            user32 = ctypes.windll.user32
            hicon = user32.LoadImageW(
                None, str(ICON_FILE), IMAGE_ICON, 0, 0,
                LR_LOADFROMFILE | LR_DEFAULTSIZE,
            )
            if hicon:
                user32.SendMessageW(hwnd, WM_SETICON, 1, hicon)
                user32.SendMessageW(hwnd, WM_SETICON, 0, hicon)
        except Exception:
            pass

    def run(self):
        user32 = ctypes.windll.user32
        while not self._stop.is_set():
            proc = self.app.server.proc
            if proc is not None and proc.poll() is None:
                title = self.app.window_title()
                windows = windows_of_pid(proc.pid)
                self.mirroring = bool(windows)
                for hwnd in windows:
                    try:
                        if hwnd not in self._styled:
                            self._apply_icon(hwnd)
                            self._styled.add(hwnd)
                        user32.SetWindowTextW(hwnd, title)
                    except Exception:
                        pass
            else:
                self.mirroring = False
                self._styled.clear()
            time.sleep(0.6)


# -------------------------------------------------------------- now playing ---

PROGRESS_RE = re.compile(
    r"audio progress \(min:sec\):\s*(\d+):(\d+);\s*remaining:\s*(\d+):(\d+);"
    r"\s*track length\s*(\d+):(\d+)"
)


def file_mtime(path):
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def read_track_metadata():
    """Parse the -md file written by UxPlay (DMAP tags as "Key: value" lines)."""
    try:
        raw = NOWPLAYING_FILE.read_bytes()
    except OSError:
        return {}
    text = raw.rstrip(b"\x00").decode("utf-8", "ignore").strip()
    if not text or text.lower().startswith("no data"):
        return {}
    data = {}
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        key, sep, value = line.partition(": ")
        if not sep or not value:
            continue
        data[key.strip().lower()] = value.strip()
    return data


class ProgressReader:
    """Follows uxplay.log and keeps the last "audio progress" report."""

    def __init__(self, path):
        self.path = path
        self.pos = 0
        self.position = 0
        self.duration = 0
        self.updated = 0.0

    def poll(self):
        try:
            size = self.path.stat().st_size
        except OSError:
            return
        if size < self.pos:
            self.pos = 0
        if size == self.pos:
            return
        try:
            with open(self.path, "rb") as fh:
                fh.seek(self.pos)
                chunk = fh.read(min(size - self.pos, 262144))
                self.pos = fh.tell()
        except OSError:
            return
        for match in PROGRESS_RE.finditer(chunk.decode("utf-8", "ignore")):
            self.position = int(match.group(1)) * 60 + int(match.group(2))
            self.duration = int(match.group(5)) * 60 + int(match.group(6))
            self.updated = time.time()


def _fmt_time(seconds):
    seconds = max(0, int(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


def placeholder_photo(size, radius=12):
    """Rounded 'no artwork' card shown before the phone sends cover art."""
    from PIL import Image, ImageDraw, ImageFont, ImageTk

    c = palette(system_is_dark())
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=c["card"])
    drawn = False
    try:  # Segoe UI Symbol has the note glyph; Segoe UI renders it as tofu
        font = ImageFont.truetype("seguisym.ttf", int(size * 0.44))
        d.text((size / 2, size / 2 - size * 0.02), "♪", font=font,
               fill=c["muted"], anchor="mm")
        drawn = True
    except Exception:
        pass
    if not drawn:  # last resort: two simple note heads
        r = size * 0.10
        for fx, fy in ((0.38, 0.62), (0.60, 0.56)):
            cx, cy = size * fx, size * fy
            d.ellipse([cx - r, cy - r * 0.78, cx + r, cy + r * 0.78], fill=c["muted"])
    return ImageTk.PhotoImage(img)


def cover_photo(size, radius=12):
    """Load the current cover art as a rounded tk image, or None."""
    from io import BytesIO

    from PIL import Image, ImageDraw, ImageTk

    try:
        data = COVERART_FILE.read_bytes()
    except OSError:
        return None
    if len(data) < 600:  # 1x1 placeholder UxPlay writes at startup
        return None
    try:
        img = Image.open(BytesIO(data)).convert("RGB")
    except Exception:
        return None
    img = img.resize((size, size))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    return ImageTk.PhotoImage(out)


def ellipsize(text, font, max_px):
    """Cut a single-line label with an ellipsis so the card never resizes."""
    from tkinter import font as tkfont

    if not text:
        return text
    try:
        f = tkfont.Font(family=font[0], size=font[1],
                        weight=font[2] if len(font) > 2 else "normal")
        if f.measure(text) <= max_px:
            return text
        cut = text
        while cut and f.measure(cut + "…") > max_px:
            cut = cut[:-1]
        return cut.rstrip() + "…"
    except Exception:
        return text


class Tooltip:
    """Small themed hint that appears above a widget."""

    def __init__(self, widget, text, colors, delay=450):
        self.widget = widget
        self.text = text
        self.c = colors
        self.delay = delay
        self.job = None
        self.top = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress-1>", self._hide, add="+")

    def _schedule(self, _event=None):
        self._cancel()
        try:
            self.job = self.widget.after(self.delay, self._show)
        except Exception:
            self.job = None

    def _cancel(self):
        if self.job is not None:
            try:
                self.widget.after_cancel(self.job)
            except Exception:
                pass
            self.job = None

    def _hide(self, _event=None):
        self._cancel()
        top, self.top = self.top, None
        if top is not None:
            try:
                top.destroy()
            except Exception:
                pass

    def _show(self):
        self.job = None
        if self.top is not None:
            return
        try:
            if not self.widget.winfo_exists():
                return
            from tkinter import font as tkfont
            width = tkfont.Font(family="Segoe UI", size=9).measure(self.text) + 20
            height = 24
            x = self.widget.winfo_rootx() + self.widget.winfo_width() // 2 - width // 2
            y = self.widget.winfo_rooty() - height - 6
            x = max(8, x)
            top = tk.Toplevel(self.widget)
            self.top = top
            top.overrideredirect(True)
            top.attributes("-topmost", True)
            key = "#010203"
            top.configure(bg=key)
            try:
                top.attributes("-transparentcolor", key)
            except Exception:
                pass
            cv = tk.Canvas(top, width=width, height=height, bg=key,
                           highlightthickness=0, bd=0)
            cv.pack()
            photo = rounded_photo(width, height, 7, self.c["card"],
                                  self.c["border"], 1, key=key)
            cv.create_image(0, 0, anchor="nw", image=photo)
            cv.image = photo
            cv.create_text(width / 2, height / 2, text=self.text,
                           fill=self.c["fg"], font=("Segoe UI", 9))
            top.geometry(f"{width}x{height}+{x}+{y}")
        except Exception:
            self._hide()


_PALETTE_CACHE = {}

FALLBACK_PALETTE = ("#3d4a63", "#54405c", "#2f3d4a")


def _hex_to_rgb(value):
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def _rgb_to_hex(rgb):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(v))) for v in rgb)


def _boost_color(rgb, sat=1.6, val=0.62):
    """Push a cover colour into a saturated but backdrop-safe range."""
    import colorsys

    r, g, b = [v / 255.0 for v in rgb]
    hue, saturation, _value = colorsys.rgb_to_hsv(r, g, b)
    saturation = min(1.0, saturation * sat + 0.10)
    return tuple(int(round(x * 255))
                 for x in colorsys.hsv_to_rgb(hue, saturation, val))


def cover_palette(count=3):
    """Dominant colours of the current cover art, tuned for a dark backdrop."""
    import colorsys
    from io import BytesIO

    from PIL import Image

    try:
        size = COVERART_FILE.stat().st_size
    except OSError:
        return list(FALLBACK_PALETTE[:count])
    if size < 600:  # 1x1 placeholder UxPlay writes at startup
        return list(FALLBACK_PALETTE[:count])

    key = (file_mtime(COVERART_FILE), size)
    cached = _PALETTE_CACHE.get(key)
    if cached is not None:
        return list(cached)

    try:
        img = Image.open(BytesIO(COVERART_FILE.read_bytes())).convert("RGB")
        img.thumbnail((90, 90))
        quant = img.quantize(colors=12, method=Image.MEDIANCUT)
        table = quant.getpalette()
        scored = []
        for amount, index in sorted(quant.getcolors(), reverse=True):
            r, g, b = table[index * 3:index * 3 + 3]
            top, low = max(r, g, b), min(r, g, b)
            if top < 34 or low > 235:  # near black / near white
                continue
            saturation = (top - low) / top if top else 0.0
            if saturation < 0.10:  # greys make a muddy backdrop
                continue
            scored.append((amount * (0.35 + saturation), (r, g, b)))
        scored.sort(key=lambda item: item[0], reverse=True)
    except Exception:
        return list(FALLBACK_PALETTE[:count])

    colors = []
    for _score, rgb in scored:
        hue = colorsys.rgb_to_hsv(*[v / 255.0 for v in rgb])[0]
        if any(abs(hue - colorsys.rgb_to_hsv(*[v / 255.0 for v in other])[0]) < 0.07
               for other in colors):
            continue
        colors.append(_boost_color(rgb))
        if len(colors) >= count:
            break
    if not colors:
        colors = [_hex_to_rgb(color) for color in FALLBACK_PALETTE[:count]]
    while len(colors) < count:
        colors.append(colors[-1])

    result = [_rgb_to_hex(color) for color in colors]
    if len(_PALETTE_CACHE) > 8:
        _PALETTE_CACHE.clear()
    _PALETTE_CACHE[key] = result
    return list(result)


class PlayerBackdrop:
    """Slowly drifting gradient tinted by the cover art.

    Rendered at half resolution (the blobs are soft, nobody can tell) and
    masked to the rounded card so the colour-key window keeps clean edges.
    """

    SCALE = 2          # render at half resolution, then upscale
    FADE = 0.55        # seconds for a palette cross-fade
    INTENSITY = 0.40   # glow brightness
    RADIUS = 0.70      # blob radius as a fraction of the card width
    VIGNETTE = 88      # edge darkening (0..255 of multiply)
    SCRIM = (0.30, 0.80)  # darken the text side: (start fraction, edge factor)
    BLOBS = (
        (0.34, 0.30, 23.0, 0.0),
        (0.30, 0.34, 31.0, 2.1),
        (0.24, 0.22, 41.0, 4.3),
    )

    def __init__(self, width, height, radius, key, border, dark=True):
        from PIL import Image, ImageChops, ImageDraw

        self.w, self.h = width, height
        self.dark = dark
        self.rw = max(2, width // self.SCALE)
        self.rh = max(2, height // self.SCALE)
        self.key = _hex_to_rgb(key)

        mask = Image.new("L", (width, height), 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            [0, 0, width - 1, height - 1], radius=radius, fill=255)
        self.mask = mask
        self.key_img = Image.new("RGB", (width, height), self.key)

        layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        ImageDraw.Draw(layer).rounded_rectangle(
            [0, 0, width - 1, height - 1], radius=radius,
            outline=_hex_to_rgb(border) + (255,), width=1)
        self.border_layer = layer

        grad = Image.radial_gradient("L").resize((self.rw, self.rh), Image.BILINEAR)
        amount = self.VIGNETTE if dark else 30
        shade = grad.point(lambda v: int(255 - (v / 255.0) ** 1.4 * amount))
        self.vignette = Image.merge("RGB", (shade, shade, shade))

        start, edge = self.SCRIM if dark else (0.30, 1.0)
        band = Image.new("L", (self.rw, 1))
        put = band.load()
        x0 = int(self.rw * start)
        for x in range(self.rw):
            if x <= x0:
                put[x, 0] = 255
            else:
                t = (x - x0) / max(1, self.rw - 1 - x0)
                put[x, 0] = int(255 * (1 + (edge - 1) * t))
        band = band.resize((self.rw, self.rh), Image.BILINEAR)
        self.scrim = Image.merge("RGB", (band, band, band))
        self.shade = ImageChops.multiply(self.vignette, self.scrim)

        self.radius = max(8, int(max(self.rw, self.rh) * self.RADIUS))
        self.falloff = self._make_falloff()
        self.colors = [(60.0, 60.0, 70.0)] * 3
        self.target = list(self.colors)
        self.base = (14.0, 14.0, 16.0) if dark else (246.0, 246.0, 248.0)
        self.base_target = self.base
        self.t = 0.0
        self._glows = None

    def _make_falloff(self):
        """Soft round mask that fades to zero at the sprite edge.

        ``Image.radial_gradient`` only reaches white in the square corners,
        so a naive falloff leaves ~10 levels of glow at the sprite border and
        the four straight edges show up as moving seams.  Normalising by the
        inscribed circle keeps the blob round and seam-free.
        """
        from PIL import Image

        r = self.radius
        grad = Image.radial_gradient("L").resize((2 * r, 2 * r), Image.BILINEAR)
        return grad.point(lambda v: int(max(0.0, 1.0 - v * 0.0055473) ** 2.0 * 255))

    def set_palette(self, colors, instant=False):
        target = [_hex_to_rgb(color) for color in colors[:3]]
        while len(target) < 3:
            target.append(target[-1])
        self.target = [tuple(float(v) for v in color) for color in target]
        dom = target[0]
        if self.dark:
            self.base_target = tuple(12.0 + (dom[i] - 12.0) * 0.10
                                     for i in range(3))
        else:
            self.base_target = tuple(246.0 + (dom[i] - 246.0) * 0.06
                                     for i in range(3))
        if instant:
            self.colors = [tuple(color) for color in self.target]
            self.base = tuple(self.base_target)
            self._glows = None

    def _build(self):
        from PIL import Image

        r = self.radius
        glows = []
        for color in self.colors:
            if self.dark:
                glow = Image.new("RGB", (2 * r, 2 * r),
                                 tuple(int(v) for v in color))
                glow = Image.composite(
                    glow, Image.new("RGB", (2 * r, 2 * r), (0, 0, 0)),
                    self.falloff)
                glow = glow.point(lambda v: int(v * self.INTENSITY))
            else:
                tint = tuple(int(255 - (255 - v) * 0.45) for v in color)
                glow = Image.new("RGB", (2 * r, 2 * r), tint)
                glow = Image.composite(
                    glow, Image.new("RGB", (2 * r, 2 * r), (255, 255, 255)),
                    self.falloff.point(lambda v: int(v * 0.78)))
            glows.append(glow)
        self._glows = glows

    def _position(self, index):
        import math

        ax, ay, period, phase = self.BLOBS[index]
        cx = self.rw * 0.5 + self.rw * ax * math.sin(
            2 * math.pi * self.t / period + phase)
        cy = self.rh * 0.5 + self.rh * ay * math.cos(
            2 * math.pi * self.t / (period * 0.8) + phase * 1.7)
        return cx, cy

    def frame(self, dt):
        import math

        from PIL import Image, ImageChops

        self.t += dt
        k = 1 - math.exp(-dt / self.FADE)
        drift = 0.0
        for i in range(3):
            self.colors[i] = tuple(
                self.colors[i][j] + (self.target[i][j] - self.colors[i][j]) * k
                for j in range(3))
            drift = max(drift, max(abs(self.colors[i][j] - self.target[i][j])
                                   for j in range(3)))
        self.base = tuple(
            self.base[j] + (self.base_target[j] - self.base[j]) * k
            for j in range(3))

        if drift >= 0.6:
            self._build()  # recolour the blobs every frame while fading
        else:
            self.colors = [tuple(color) for color in self.target]
            self.base = tuple(self.base_target)
            if self._glows is None:
                self._build()

        r = self.radius
        pad = r
        canvas = Image.new("RGB", (self.rw + 2 * pad, self.rh + 2 * pad),
                           tuple(int(v) for v in self.base))
        for i, glow in enumerate(self._glows):
            cx, cy = self._position(i)
            x = int(cx) + pad - r
            y = int(cy) + pad - r
            box = (x, y, x + 2 * r, y + 2 * r)
            region = canvas.crop(box)
            if self.dark:
                canvas.paste(ImageChops.add(region, glow), (x, y))
            else:
                canvas.paste(ImageChops.multiply(region, glow), (x, y))

        img = canvas.crop((pad, pad, pad + self.rw, pad + self.rh))
        img = ImageChops.multiply(img, self.shade)
        full = img.resize((self.w, self.h), Image.BILINEAR)
        full.paste(self.border_layer, (0, 0), self.border_layer)
        return Image.composite(full, self.key_img, self.mask)


class NowPlayingWindow:
    """Small "now playing" card for AirPlay audio sessions (Apple Music etc.).

    The card lives on a single canvas so the drifting, cover-tinted backdrop
    can show through; Tk widgets would cover it with an opaque rectangle.
    """

    WIDTH = 470
    ART = 104
    RING = 14       # transparent margin that hosts the rounded card edge
    MARGIN = 16     # distance from the work-area corner
    KEY = "#010203"  # colour key for real rounded corners
    FRAME_MS = 83   # ~12 fps for the drifting backdrop
    BTN = 26
    PAD = 8

    def __init__(self, app):
        self.app = app
        self.win = None
        self.shell = None
        self.track = {}
        self.track_key = None
        self.cover_key = None
        self.palette_key = None
        self.photo = None
        self.dismissed_key = None
        self.visible = False
        self.placed = False
        self.win_anim = None
        self._home = None
        self._prog_job = None
        self._shown_pos = 0.0
        self._target_pos = 0.0
        self._duration = 0.0
        self.topmost = bool(load_settings().get("always_on_top", False))
        self.animated = bool(load_settings().get("animated_backdrop", True))
        self._drag = None
        self._press = None
        self.hover = None
        self.hover_t = 0.0
        self._icon_anim = None
        self._chips = {}
        self._glyphs = {}
        self._prog_photos = ()
        self._tip_job = None
        self._tip_top = None
        self._tip_text = ""
        self.backdrop = None
        self._bg_item = None
        self._bg_photo = None
        self._bg_owned = False
        self._anim_job = None
        self._last_frame = 0.0
        self.c = palette(system_is_dark())
        self.dark = system_is_dark()
        self.dim = self.c["muted"]
        self._layout = {}
        self._size = (self.WIDTH, 211)
        self.card_w = self.WIDTH - 2 * self.RING

    # -- window ------------------------------------------------------------
    def _build(self):
        dark = system_is_dark()
        c = palette(dark)
        self.c = c
        self.dark = dark
        # secondary text sits on a colourful backdrop, so keep it brighter
        # than the flat-card "muted" grey
        self.dim = blend(c["muted"], c["fg"], 0.52)
        win = tk.Toplevel(self.app.root)
        self.win = win
        win.title(tr("player_title"))
        win.configure(bg=self.KEY)
        win.resizable(False, False)
        win.withdraw()
        try:
            win.attributes("-toolwindow", True)  # no taskbar button
        except Exception:
            pass
        try:
            win.overrideredirect(True)  # our own header instead of the XP-ish caption
        except Exception:
            pass
        try:
            win.attributes("-transparentcolor", self.KEY)
        except Exception:
            pass
        win.protocol("WM_DELETE_WINDOW", self._on_close)
        if ICON_FILE.exists():
            try:
                win.iconbitmap(str(ICON_FILE))
            except Exception:
                pass

        self._measure()
        cw, ch = self._size
        self.shell = tk.Canvas(win, width=cw, height=ch, bg=self.KEY,
                               highlightthickness=0, bd=0)
        self.shell.pack(fill="both", expand=True)

        if self.animated:
            self.backdrop = PlayerBackdrop(cw, ch, 14, self.KEY, c["border"],
                                           dark=dark)
            self.palette_key = tuple(cover_palette())
            self.backdrop.set_palette(self.palette_key, instant=True)
        else:
            self.backdrop = None
        self._paint_background()

        self.photo = cover_photo(self.ART) or placeholder_photo(self.ART)
        self._cover_item = self.shell.create_image(
            self.RING + self.PAD, self.RING + self._layout["art_y"],
            anchor="nw", image=self.photo)

        lay = self._layout
        self._head_item = self.shell.create_text(
            self.RING + self.PAD, self.RING + 2 + self.BTN // 2, anchor="w",
            text=tr("now_playing"), fill=self.dim, font=("Segoe UI", 9))
        self._title_item = self.shell.create_text(
            self.RING + lay["info_x"], self.RING + lay["title_y"], anchor="nw",
            text="", fill=c["fg"], font=("Segoe UI", 12, "bold"))
        self._artist_item = self.shell.create_text(
            self.RING + lay["info_x"], self.RING + lay["artist_y"], anchor="nw",
            text="", fill=c["fg"], font=("Segoe UI", 10))
        self._album_item = self.shell.create_text(
            self.RING + lay["info_x"], self.RING + lay["album_y"], anchor="nw",
            text="", fill=self.dim, font=("Segoe UI", 9))
        self._pos_item = self.shell.create_text(
            self.RING + self.PAD, self.RING + lay["times_y"], anchor="nw",
            text="0:00", fill=self.dim, font=("Segoe UI", 8))
        self._dur_item = self.shell.create_text(
            self.RING + self.card_w - self.PAD, self.RING + lay["times_y"],
            anchor="ne", text="0:00", fill=self.dim, font=("Segoe UI", 8))

        self._chips = self._make_chips()
        self._draw_icons()
        self._draw_progress()

        self.shell.bind("<ButtonPress-1>", self._press_evt)
        self.shell.bind("<B1-Motion>", self._drag_move)
        self.shell.bind("<ButtonRelease-1>", self._release_evt)
        self.shell.bind("<Motion>", self._motion)
        self.shell.bind("<Leave>", self._leave)

        win.update_idletasks()
        self.win_anim = Animator(win)

    def _measure(self):
        from tkinter import font as tkfont

        def line(size, bold=False):
            return tkfont.Font(family="Segoe UI", size=size,
                               weight="bold" if bold else "normal").metrics("linespace")

        head = line(9)
        title = line(12, True)
        artist = line(10)
        album = line(9)
        times = line(8)

        card_w = max(self.WIDTH - 2 * self.RING, self.ART + 200)
        art_y = max(self.BTN, head) + 8
        info_x = self.PAD + self.ART + 14
        artist_y = art_y + title + 4
        album_y = artist_y + artist + 2
        bar_y = max(art_y + self.ART, album_y + album) + 14
        times_y = bar_y + 6 + 4
        card_h = times_y + times + 2
        close_x = card_w - 6 - self.BTN

        self.card_w = card_w
        self._layout = {
            "art_y": art_y,
            "info_x": info_x,
            "title_y": art_y,
            "artist_y": artist_y,
            "album_y": album_y,
            "bar_y": bar_y,
            "bar_w": card_w - 2 * self.PAD,
            "times_y": times_y,
            "pin_x": close_x - 2 - self.BTN,
            "close_x": close_x,
        }
        self._size = (card_w + 2 * self.RING, card_h + 2 * self.RING)

    def _make_chips(self):
        from PIL import Image, ImageDraw, ImageTk

        size = self.BTN
        s = 4
        chips = {}
        for name, color, alpha in (
            ("hover", (255, 255, 255), 26),
            ("active", (255, 255, 255), 56),
            ("close", (232, 17, 35), 215),
            # on the pastel light backdrop a white veil is invisible
            ("hover_light", (0, 0, 0), 16),
            ("active_light", (0, 0, 0), 34),
        ):
            img = Image.new("RGBA", (size * s, size * s), (0, 0, 0, 0))
            ImageDraw.Draw(img).ellipse(
                [0, 0, size * s - 1, size * s - 1], fill=color + (alpha,))
            chips[name] = ImageTk.PhotoImage(
                img.resize((size, size), Image.LANCZOS))
        return chips

    def _glyph(self, kind, color):
        """Anti-aliased header glyph, drawn once per colour and centred exactly.

        Canvas lines snap to whole pixels, so a hand-placed icon drifts by up
        to a pixel inside its chip and the strokes look uneven.  Drawing the
        sprite at 4x and scaling down keeps it optically centred and smooth.
        """
        key = (kind, color)
        cached = self._glyphs.get(key)
        if cached is not None:
            return cached
        from PIL import Image, ImageDraw, ImageTk

        s = 4
        n = self.BTN
        sprite = Image.new("RGBA", (n * s, n * s), (0, 0, 0, 0))
        draw = ImageDraw.Draw(sprite)
        rgb = _hex_to_rgb(color) + (255,)
        mid = n * s / 2.0
        if kind == "close":
            half, width = 4.6 * s, 1.7 * s
            for dx, dy in ((1, 1), (1, -1)):
                draw.line([mid - dx * half, mid - dy * half,
                           mid + dx * half, mid + dy * half],
                          fill=rgb, width=int(round(width)))
            r = width / 2.0
            for dx, dy in ((-1, -1), (1, 1), (1, -1), (-1, 1)):
                draw.ellipse([mid + dx * half - r, mid + dy * half - r,
                              mid + dx * half + r, mid + dy * half + r],
                             fill=rgb)
        else:
            # "always on top": a window with a title bar.  Equal strokes and a
            # thin bar keep the ink balanced, so it reads as centred.
            w, h = 14.0 * s, 12.0 * s
            left, top = mid - w / 2, mid - h / 2
            draw.rounded_rectangle([left, top, left + w - 1, top + h - 1],
                                   radius=1.9 * s, outline=rgb,
                                   width=int(round(1.5 * s)))
            draw.line([left + 1.2 * s, top + 3.3 * s,
                       left + w - 1.2 * s, top + 3.3 * s],
                      fill=rgb, width=int(round(1.2 * s)))
        photo = ImageTk.PhotoImage(sprite.resize((n, n), Image.LANCZOS))
        self._glyphs[key] = photo
        return photo

    # -- background --------------------------------------------------------
    def _paint_background(self):
        """(Re)create the backdrop image; a fresh PhotoImage we may paste into."""
        from PIL import ImageTk

        if self.shell is None:
            return
        if self.backdrop is not None:
            self._bg_photo = ImageTk.PhotoImage(self.backdrop.frame(0.0))
            self._bg_owned = True
        else:
            cw, ch = self._size
            self._bg_photo = rounded_photo(cw, ch, 14, self.c["card"],
                                           self.c["border"], 1, key=self.KEY)
            self._bg_owned = False
        if self._bg_item is None:
            self._bg_item = self.shell.create_image(0, 0, anchor="nw",
                                                    image=self._bg_photo)
            self.shell.tag_lower(self._bg_item)
        else:
            self.shell.itemconfigure(self._bg_item, image=self._bg_photo)

    # -- icons -------------------------------------------------------------
    def _draw_icons(self):
        cv = self.shell
        if cv is None:
            return
        c = self.c
        lay = self._layout
        cv.delete("icon")
        for kind in ("pin", "close"):
            x = self.RING + lay[f"{kind}_x"]
            y = self.RING + 2
            active = kind == "pin" and self.topmost
            hovered = self.hover == kind
            t = self.hover_t if hovered else 0.0
            chip = None
            if kind == "close" and t > 0.02:
                chip = self._chips["close"]
            elif active:
                chip = self._chips["active" if self.dark else "active_light"]
            elif t > 0.02:
                chip = self._chips["hover" if self.dark else "hover_light"]
            if chip is not None:
                cv.create_image(x, y, anchor="nw", image=chip, tags="icon")
            if kind == "close" and hovered:
                color = "#ffffff"
            elif active or hovered:
                color = "#ffffff" if self.dark else c["fg"]
            else:
                color = self.dim
            cv.create_image(x, y, anchor="nw", image=self._glyph(kind, color),
                            tags="icon")

    def _hit(self, x, y):
        if not (self.RING + 2 <= y <= self.RING + 2 + self.BTN):
            return None
        for kind in ("pin", "close"):
            left = self.RING + self._layout[f"{kind}_x"]
            if left <= x <= left + self.BTN:
                return kind
        return None

    def _set_hover(self, kind):
        if kind == self.hover:
            return
        self.hover = kind
        start = self.hover_t
        target = 1.0 if kind else 0.0
        if self._icon_anim is None:
            self._icon_anim = Animator(self.shell)

        def frame(t):
            self.hover_t = start + (target - start) * t
            self._draw_icons()

        self._icon_anim.run(110, frame)

    # -- tooltips ----------------------------------------------------------
    def _cancel_tip(self):
        job, self._tip_job = self._tip_job, None
        if job is not None and self.shell is not None:
            try:
                self.shell.after_cancel(job)
            except Exception:
                pass
        top, self._tip_top = self._tip_top, None
        if top is not None:
            try:
                top.destroy()
            except Exception:
                pass

    def _schedule_tip(self, kind):
        self._cancel_tip()
        text = tr("always_on_top") if kind == "pin" else tr("close")
        self._tip_text = text
        self._tip_job = self.shell.after(450, lambda: self._show_tip(kind, text))

    def _show_tip(self, kind, text):
        self._tip_job = None
        if self.win is None or self.hover != kind:
            return
        try:
            from tkinter import font as tkfont

            width = tkfont.Font(family="Segoe UI", size=9).measure(text) + 20
            height = 24
            x = (self.win.winfo_rootx() + self.RING + self._layout[f"{kind}_x"]
                 + self.BTN // 2 - width // 2)
            y = self.win.winfo_rooty() + self.RING + 2 - height - 6
            x = max(8, x)
            key = "#010203"
            top = tk.Toplevel(self.win)
            self._tip_top = top
            top.overrideredirect(True)
            top.attributes("-topmost", True)
            top.configure(bg=key)
            try:
                top.attributes("-transparentcolor", key)
            except Exception:
                pass
            cv = tk.Canvas(top, width=width, height=height, bg=key,
                           highlightthickness=0, bd=0)
            cv.pack()
            photo = rounded_photo(width, height, 7, self.c["card"],
                                  self.c["border"], 1, key=key)
            cv.create_image(0, 0, anchor="nw", image=photo)
            cv.image = photo
            cv.create_text(width / 2, height / 2, text=text, fill=self.c["fg"],
                           font=("Segoe UI", 9))
            top.geometry(f"{width}x{height}+{x}+{y}")
        except Exception:
            self._cancel_tip()

    # -- pointer -----------------------------------------------------------
    def _motion(self, event):
        kind = self._hit(event.x, event.y)
        if kind != self.hover:
            self._set_hover(kind)
            if kind:
                self._schedule_tip(kind)
            else:
                self._cancel_tip()
        try:
            if kind:
                self.shell.configure(cursor="hand2")
            else:
                # the header is draggable, but a "move" cursor there just
                # adds noise over the artwork
                self.shell.configure(cursor="")
        except Exception:
            pass

    def _leave(self, _event=None):
        self._set_hover(None)
        self._cancel_tip()
        try:
            self.shell.configure(cursor="")
        except Exception:
            pass

    def _press_evt(self, event):
        self._cancel_tip()
        kind = self._hit(event.x, event.y)
        if kind:
            self._press = kind
            return
        if event.y < self.RING + 2 + self.BTN + 4:
            try:
                self._drag = (event.x_root - self.win.winfo_rootx(),
                              event.y_root - self.win.winfo_rooty())
            except Exception:
                self._drag = None

    def _release_evt(self, event):
        kind, self._press = self._press, None
        self._drag = None
        if kind == "close":
            self._on_close()
        elif kind == "pin":
            self._toggle_topmost()

    # -- geometry ----------------------------------------------------------
    @staticmethod
    def _work_area():
        class RECT(ctypes.Structure):
            _fields_ = [
                ("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long),
            ]

        rect = RECT()
        ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0)
        return rect.left, rect.top, rect.right, rect.bottom

    def _place(self):
        self.win.update_idletasks()
        w, h = self._size
        _l, _t, right, bottom = self._work_area()
        x = max(_l + 8, right - w - self.MARGIN)
        y = max(_t + 8, bottom - h - self.MARGIN)
        self.win.geometry(f"{w}x{h}+{x}+{y}")
        self._home = (w, h, x, y)

    def _hwnd(self):
        try:
            hwnd = self.win.winfo_id()
            parent = ctypes.windll.user32.GetParent(hwnd)
            return parent or hwnd  # borderless windows have no parent frame
        except Exception:
            return 0

    # -- dragging ----------------------------------------------------------
    def _drag_move(self, event):
        if self._drag is None:
            return
        dx, dy = self._drag
        try:
            self.win.geometry(f"+{event.x_root - dx}+{event.y_root - dy}")
        except Exception:
            pass

    # -- always on top -----------------------------------------------------
    def _apply_topmost(self):
        if self.win is None:
            return
        try:
            self.win.attributes("-topmost", bool(self.topmost))
        except Exception:
            pass

    def _toggle_topmost(self):
        self.topmost = not self.topmost
        self._draw_icons()
        self._apply_topmost()
        cfg = load_settings()
        cfg["always_on_top"] = self.topmost
        try:
            save_settings(cfg)
        except Exception:
            pass

    # -- animation ---------------------------------------------------------
    def _start_anim(self):
        if not self.animated or self.backdrop is None or self.win is None:
            return
        if self._anim_job is not None:
            return
        self._last_frame = time.monotonic()
        self._anim_job = self.win.after(self.FRAME_MS, self._anim_tick)

    def _stop_anim(self):
        job, self._anim_job = self._anim_job, None
        if job is not None and self.win is not None:
            try:
                self.win.after_cancel(job)
            except Exception:
                pass

    def _anim_tick(self):
        self._anim_job = None
        if (not self.visible or not self.animated or self.win is None
                or not self.win.winfo_exists() or self.backdrop is None):
            return
        now = time.monotonic()
        dt = min(0.25, max(0.001, now - self._last_frame))
        self._last_frame = now
        try:
            img = self.backdrop.frame(dt)
            if self._bg_owned and self._bg_photo is not None:
                self._bg_photo.paste(img)
            else:
                from PIL import ImageTk

                self._bg_photo = ImageTk.PhotoImage(img)
                self._bg_owned = True
                self.shell.itemconfigure(self._bg_item, image=self._bg_photo)
        except Exception:
            pass
        if self.win is not None:
            self._anim_job = self.win.after(self.FRAME_MS, self._anim_tick)

    def apply_settings(self, cfg):
        self.animated = bool(cfg.get("animated_backdrop", True))
        if self.win is None or not self.win.winfo_exists():
            return
        if self.animated:
            if self.backdrop is None:
                cw, ch = self._size
                self.backdrop = PlayerBackdrop(cw, ch, 14, self.KEY,
                                               self.c["border"], dark=self.dark)
                self.palette_key = tuple(cover_palette())
                self.backdrop.set_palette(self.palette_key, instant=True)
                self._paint_background()
            self._start_anim()
        else:
            self._stop_anim()
            self.backdrop = None
            self._paint_background()

    # -- reveal / hide -----------------------------------------------------
    def _reveal(self):
        """Show the card without stealing focus (and without raising it again)."""
        if self.win is None or not self.win.winfo_exists():
            self._build()
            self.placed = False
        if not self.placed:
            self._place()
            self.placed = True
        self._apply_topmost()
        if self.visible:
            return
        try:
            self.win.attributes("-alpha", 0.0)
        except Exception:
            pass
        hwnd = self._hwnd()
        if hwnd:
            # SW_SHOWNOACTIVATE: map the window, keep the current foreground app
            ctypes.windll.user32.ShowWindow(hwnd, 4)
            ctypes.windll.user32.SetWindowPos(
                hwnd, -1 if self.topmost else -2, 0, 0, 0, 0,
                0x0001 | 0x0002 | 0x0010  # NOSIZE|NOMOVE|NOACTIVATE
            )
        else:
            self.win.deiconify()
        self.visible = True
        self._start_anim()
        self._animate_in()

    def _animate_in(self):
        win = self.win
        if win is None or self._home is None or not win.winfo_exists():
            return
        w, h, x, y = self._home
        try:
            win.attributes("-alpha", 0.0)
        except Exception:
            return

        def frame(t):
            win.attributes("-alpha", t)
            win.geometry(f"{w}x{h}+{x}+{y + int(16 * (1 - t))}")

        def done():
            win.attributes("-alpha", 1.0)
            win.geometry(f"{w}x{h}+{x}+{y}")

        self.win_anim.run(190, frame, on_done=done)

    # -- content -----------------------------------------------------------
    def show_track(self, track, position, duration):
        key = (track.get("title", ""), track.get("artist", ""), track.get("album", ""))
        if self.dismissed_key == key:
            return
        self._reveal()

        if key != self.track_key:
            self.track_key = key
            self.track = track
            self._shown_pos = 0.0
            self._apply_text(track)
        else:
            # UxPlay may write the artwork a moment after the tags
            self._update_cover()
        self._set_progress(position, duration)

    def _apply_text(self, track):
        title = track.get("title") or track.get("name") or tr("unknown_track")
        artist = track.get("artist") or track.get("album artist") or ""
        album = track.get("album") or ""

        # single-line labels keep the card size stable (no jumping on track change)
        if self.shell is not None:
            self.shell.itemconfigure(
                self._title_item,
                text=ellipsize(title, ("Segoe UI", 12, "bold"), 300))
            self.shell.itemconfigure(
                self._artist_item,
                text=ellipsize(artist, ("Segoe UI", 10), 300) or " ")
            self.shell.itemconfigure(
                self._album_item,
                text=ellipsize(album, ("Segoe UI", 9), 300) or " ")
        self.win.title(f"{title} — AirMirror")

        self._update_cover()

    def retranslate(self):
        """Re-apply UI strings after the interface language changed."""
        if self.win is None or not self.win.winfo_exists():
            return
        try:
            self.win.title(tr("player_title"))
            self.shell.itemconfigure(self._head_item, text=tr("now_playing"))
            self._cancel_tip()
            if self.track:
                self._apply_text(self.track)
        except Exception:
            pass

    def _update_cover(self):
        try:
            size = COVERART_FILE.stat().st_size
        except OSError:
            size = 0
        key = (file_mtime(COVERART_FILE), size)
        if key != self.cover_key:
            photo = cover_photo(self.ART) or placeholder_photo(self.ART)
            if photo is not None:
                self.cover_key = key
                self.photo = photo
                if self.shell is not None:
                    self.shell.itemconfigure(self._cover_item, image=photo)
        if self.backdrop is not None:
            pal = tuple(cover_palette())
            if pal != self.palette_key:
                self.palette_key = pal
                self.backdrop.set_palette(pal)

    def _set_progress(self, position, duration):
        self._target_pos = float(position)
        self._duration = float(duration)
        if self.shell is not None:
            self.shell.itemconfigure(self._dur_item, text=_fmt_time(duration))
        if self._prog_job is None and self.visible and self.win is not None:
            self._prog_job = self.win.after(30, self._tick_progress)

    def _stop_progress(self):
        if self._prog_job is not None and self.win is not None:
            try:
                self.win.after_cancel(self._prog_job)
            except Exception:
                pass
        self._prog_job = None

    def _tick_progress(self):
        self._prog_job = None
        if not self.visible or self.win is None or not self.win.winfo_exists():
            return
        delta = self._target_pos - self._shown_pos
        if abs(delta) < 0.05:
            self._shown_pos = self._target_pos
        else:
            self._shown_pos += delta * 0.20
        self._draw_progress()
        if self.shell is not None:
            self.shell.itemconfigure(self._pos_item,
                                     text=_fmt_time(self._shown_pos))
        if abs(self._target_pos - self._shown_pos) > 0.02:
            self._prog_job = self.win.after(30, self._tick_progress)

    def _draw_progress(self):
        if self.shell is None:
            return
        self.shell.delete("prog")
        lay = self._layout
        x0 = self.RING + self.PAD
        y = self.RING + lay["bar_y"]
        width = lay["bar_w"]
        # keep the sprites referenced: the canvas only stores the image name
        self._prog_photos = [bar_photo(width, self.c["border"])]
        self.shell.create_image(x0, y, anchor="nw",
                                image=self._prog_photos[0], tags="prog")
        if self._duration <= 0:
            return
        done = width * min(self._shown_pos / self._duration, 1.0)
        if done < 2:
            return
        self._prog_photos.append(bar_photo(done, self.c["muted"]))
        self.shell.create_image(x0, y, anchor="nw",
                                image=self._prog_photos[1], tags="prog")

    # -- lifecycle ---------------------------------------------------------
    def hide(self):
        if not self.visible:
            return
        self.visible = False
        self._stop_progress()
        self._stop_anim()
        self._cancel_tip()
        win = self.win
        if win is None or not win.winfo_exists() or self._home is None:
            return
        w, h, x, y = self._home
        try:
            alpha = float(win.attributes("-alpha"))
        except Exception:
            alpha = 1.0

        def frame(t):
            win.attributes("-alpha", alpha * (1 - t))
            win.geometry(f"{w}x{h}+{x}+{y + int(12 * t)}")

        def done():
            try:
                win.withdraw()
                win.attributes("-alpha", 1.0)
                win.geometry(f"{w}x{h}+{x}+{y}")
            except Exception:
                pass

        self.win_anim.run(140, frame, on_done=done)

    def _on_close(self):
        self.dismissed_key = self.track_key
        self.hide()

    def destroy(self):
        self._stop_progress()
        self._stop_anim()
        self._cancel_tip()
        if self.win_anim is not None:
            self.win_anim.cancel()
        if self._icon_anim is not None:
            self._icon_anim.cancel()
        if self.win is not None:
            try:
                self.win.destroy()
            except Exception:
                pass
            self.win = None

    def reset(self):
        """Forget the dismissed track (a new AirPlay session started)."""
        self.dismissed_key = None


class NowPlayingWatcher(threading.Thread):
    """Watches UxPlay's metadata/progress output and drives NowPlayingWindow."""

    def __init__(self, app):
        super().__init__(daemon=True)
        self.app = app
        self._stop = threading.Event()
        self.reader = ProgressReader(UXPLAY_LOG)

    def stop(self):
        self._stop.set()

    def run(self):
        while not self._stop.is_set():
            try:
                self.step()
            except Exception:
                pass
            time.sleep(0.7)

    def step(self):
        app = self.app
        if not app.server.running():
            app.commands.put(app.now_playing.hide)
            return

        self.reader.poll()
        track = read_track_metadata()
        now = time.time()
        seen = max(self.reader.updated, file_mtime(NOWPLAYING_FILE))
        fresh = seen > now - 60

        hide = (
            not app.cfg.get("now_playing", True)
            or not track
            or not fresh
            or app.renamer.mirroring
        )
        if hide:
            app.commands.put(app.now_playing.hide)
            return

        position, duration = self.reader.position, self.reader.duration
        app.commands.put(
            lambda t=track, p=position, d=duration: app.now_playing.show_track(t, p, d)
        )


# ----------------------------------------------------------------- widgets ---

def round_poly(canvas, x1, y1, x2, y2, r, **kw):
    """Rounded rectangle drawn as a smoothed polygon."""
    r = min(r, (x2 - x1) / 2, (y2 - y1) / 2)
    points = [
        x1 + r, y1, x2 - r, y1, x2, y1,
        x2, y1 + r, x2, y2 - r, x2, y2,
        x2 - r, y2, x1 + r, y2, x1, y2,
        x1, y2 - r, x1, y1 + r, x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, **kw)


_ROUND_CACHE = {}
_BAR_CACHE = {}


def rounded_photo(w, h, radius, fill, outline=None, border=1, key=None):
    """Anti-aliased rounded rectangle (supersampled) for crisp 1px borders.

    Pass ``key`` when the image goes into a colour-keyed window
    (``-transparentcolor``): Windows only hides pixels that match the key
    exactly, so the soft edge is snapped to the real silhouette and flattened
    onto the outline colour.  Otherwise the half-transparent anti-aliasing ring
    stays visible as dark speckles around the rounded corners.
    """
    from PIL import Image, ImageDraw, ImageTk

    w, h, radius = int(w), int(h), int(radius)
    cache_key = (w, h, radius, fill, outline, border, key)
    photo = _ROUND_CACHE.get(cache_key)
    if photo is not None:
        return photo
    if len(_ROUND_CACHE) > 200:
        _ROUND_CACHE.clear()

    s = 4  # supersampling factor
    img = Image.new("RGBA", (w * s, h * s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    box = [0, 0, w * s - 1, h * s - 1]
    if outline and border > 0:
        draw.rounded_rectangle(box, radius=radius * s, fill=outline)
        b = border * s
        draw.rounded_rectangle(
            [b, b, w * s - 1 - b, h * s - 1 - b],
            radius=max(1, radius - border) * s, fill=fill,
        )
    else:
        draw.rounded_rectangle(box, radius=radius * s, fill=fill)

    img = img.resize((w, h), Image.LANCZOS)
    if key is not None:
        edge = (outline or fill).lstrip("#")
        edge = tuple(int(edge[i:i + 2], 16) for i in (0, 2, 4))
        spot = key.lstrip("#")
        spot = tuple(int(spot[i:i + 2], 16) for i in (0, 2, 4))
        mask = img.getchannel("A").point(lambda a: 255 if a >= 128 else 0)
        flat = Image.alpha_composite(
            Image.new("RGBA", (w, h), edge + (255,)), img
        )
        img = Image.composite(
            flat, Image.new("RGBA", (w, h), spot + (255,)), mask
        ).convert("RGB")
    photo = ImageTk.PhotoImage(img)
    _ROUND_CACHE[cache_key] = photo
    return photo



def bar_photo(width, color, height=6):
    """Pill-shaped progress-bar sprite.

    Tk's own ovals at this size break into stair-steps and leave a stray pixel
    under each cap, so the bar is rendered like the rest of the chrome.
    """
    from PIL import Image, ImageDraw, ImageTk

    width = max(1, int(round(width)))
    key = (width, height, color)
    photo = _BAR_CACHE.get(key)
    if photo is not None:
        return photo
    s = 4
    img = Image.new("RGBA", (width * s, height * s), (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle(
        [0, 0, width * s - 1, height * s - 1],
        radius=min(width, height) * s / 2.0,
        fill=_hex_to_rgb(color) + (255,),
    )
    photo = ImageTk.PhotoImage(img.resize((width, height), Image.BOX))
    if len(_BAR_CACHE) > 64:
        _BAR_CACHE.clear()
    _BAR_CACHE[key] = photo
    return photo


class PillToggle(tk.Canvas):
    """iOS-style switch with a smoothly sliding knob."""

    def __init__(self, parent, colors, value=False, command=None,
                 width=46, height=26, bg=None):
        super().__init__(
            parent, width=width, height=height, bg=bg or colors["card"],
            highlightthickness=0, bd=0, cursor="hand2",
        )
        self.c = colors
        self.w, self.h = width, height
        self.value = bool(value)
        self.command = command
        self.p = 1.0 if self.value else 0.0
        self.anim = Animator(self)
        self.bind("<Button-1>", self._click)
        self._draw()

    def _draw(self):
        self.delete("all")
        p = self.p
        track = blend(self.c["border"], self.c["accent"], p)
        # a real pill: two caps plus a body, smoother than a smoothed polygon
        r = self.h / 2
        self.create_oval(0, 0, self.h, self.h, fill=track, outline="")
        self.create_oval(self.w - self.h, 0, self.w, self.h, fill=track, outline="")
        self.create_rectangle(r, 0, self.w - r, self.h, fill=track, outline="")
        knob = self.h - 6
        x = 3 + (self.w - knob - 6) * p
        # soft shadow under the knob, then the knob itself
        shadow = blend(track, "#000000", 0.22)
        self.create_oval(x, 4, x + knob, 4 + knob, fill=shadow, outline="")
        self.create_oval(x, 3, x + knob, 3 + knob, fill="#ffffff", outline="")

    def _animate(self):
        target = 1.0 if self.value else 0.0
        start = self.p

        def frame(t):
            self.p = start + (target - start) * t
            self._draw()

        self.anim.run(130, frame, on_done=lambda: setattr(self, "p", target))

    def _click(self, _event=None):
        self.value = not self.value
        self._animate()
        if self.command:
            self.command(self.value)

    def set(self, value):
        self.value = bool(value)
        self._animate()


class RoundButton(tk.Canvas):
    """Rounded flat button (primary / ghost / tab)."""

    def __init__(self, parent, text, command, colors, kind="primary", width=None,
                 height=34, font=("Segoe UI", 10, "bold"), radius=10, bg=None):
        from tkinter import font as tkfont

        self.c = colors
        self.kind = kind
        self.text = text
        self.command = command
        self.font = font
        self.radius = radius
        measured = tkfont.Font(family=font[0], size=font[1]).measure(text)
        self.w = width or measured + 34
        self.h = height
        self.active = kind != "tab"
        self.hover = 0.0
        self.pressed = False
        self.anim = None
        super().__init__(
            parent, width=self.w, height=self.h,
            bg=bg or (colors["bg"] if kind == "tab" else colors["card"]),
            highlightthickness=0, bd=0, cursor="hand2",
        )
        self.anim = Animator(self)
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<Enter>", lambda _e: self._hover(True))
        self.bind("<Leave>", lambda _e: self._hover(False))
        self._draw()

    def _draw(self):
        self.delete("all")
        c = self.c
        h = self.hover
        if self.kind == "primary":
            fill = blend(c["accent"], "#ffffff", 0.12 * h)
            fg, outline = "#ffffff", ""
        elif self.kind == "ghost":
            fill = blend(c["card"], c["hover"], h)
            fg, outline = c["fg"], c["border"]
        elif self.kind == "tab":
            fill = c["accent"] if self.active else blend(c["card"], c["hover"], h)
            fg = "#ffffff" if self.active else c["muted"]
            outline = "" if self.active else c["border"]
        else:
            fill = blend(c["card"], c["hover"], h)
            fg, outline = c["fg"], c["border"]
        if self.pressed:
            fill = blend(fill, "#000000", 0.10)
        photo = rounded_photo(self.w, self.h, self.radius, fill,
                              outline or None, 1 if outline else 0)
        self.create_image(0, 0, anchor="nw", image=photo)
        self._photo = photo
        dy = 1 if self.pressed else 0
        self.create_text(self.w / 2, self.h / 2 + dy, text=self.text,
                         fill=fg, font=self.font)

    def _hover(self, state):
        target = 1.0 if state else 0.0
        start = self.hover

        def frame(t):
            self.hover = start + (target - start) * t
            self._draw()

        self.anim.run(110, frame)

    def _press(self, _event=None):
        self.pressed = True
        self._draw()

    def _release(self, _event=None):
        if not self.pressed:
            return
        self.pressed = False
        self._draw()
        if self.command:
            self.command()

    def set_active(self, active):
        self.active = active
        self._draw()


class RoundSelect(tk.Canvas):
    """Rounded drop-down with a themed popup list (no native menu)."""

    ITEM_H = 30
    PAD = 6
    _active = None  # the select whose popup is currently open

    def __init__(self, parent, values, variable, colors, width=214, height=34,
                 command=None, bg=None):
        super().__init__(
            parent, width=width, height=height, bg=bg or colors["card"],
            highlightthickness=0, bd=0, cursor="hand2",
        )
        self.c = colors
        self.values = list(values)
        self.variable = variable
        self.w, self.h = width, height
        self.command = command
        self.hover = 0.0
        self.anim = Animator(self)
        self.popup = None
        self.popup_anim = None
        self._hover_index = None
        self._suppress_toggle = False
        self.bind("<Button-1>", self._toggle)
        self.bind("<Enter>", lambda _e: self._hover(True))
        self.bind("<Leave>", lambda _e: self._hover(False))
        self.variable.trace_add("write", lambda *_a: self._draw())
        self.bind("<Destroy>", lambda _e: self._close_popup())
        try:
            self.winfo_toplevel().bind("<Button-1>", self._root_click, add="+")
        except Exception:
            pass
        self._draw()

    def _draw(self):
        self.delete("all")
        c = self.c
        fill = blend(c["card"], c["hover"], self.hover)
        photo = rounded_photo(self.w, self.h, 9, fill, c["border"], 1)
        self.create_image(0, 0, anchor="nw", image=photo)
        self._photo = photo
        text = self.variable.get()
        if len(text) > 24:
            text = text[:23] + "…"
        self.create_text(12, self.h / 2, text=text, anchor="w", fill=c["fg"],
                         font=("Segoe UI", 9))
        self.create_text(self.w - 15, self.h / 2 + 1, text="▾", anchor="center",
                         fill=c["muted"], font=("Segoe UI", 9))

    def _hover(self, state):
        target = 1.0 if state else 0.0
        start = self.hover

        def frame(t):
            self.hover = start + (target - start) * t
            self._draw()

        self.anim.run(110, frame)

    # -- popup -------------------------------------------------------------
    def _popup_size(self):
        return self.w, self.PAD * 2 + self.ITEM_H * len(self.values)

    def _toggle(self, _event=None):
        if self.popup is not None:
            self._close_popup()
            return
        if self._suppress_toggle:
            # this very click already closed the list via <FocusOut>
            self._suppress_toggle = False
            return
        self._open_popup()

    def _popup_focus_out(self, _event=None):
        """Close the list when the popup loses focus.

        Clicking the select while its list is open moves focus away from the
        popup *before* the click reaches the canvas.  Without the flag the list
        would close here and immediately reopen in ``_toggle``.
        """
        if self.popup is None:
            return
        try:
            px, py = self.winfo_pointerxy()
            widget = self.winfo_containing(px, py)
            on_self = widget is not None and str(widget).startswith(str(self))
        except Exception:
            on_self = False
        if on_self:
            self._suppress_toggle = True
            self.after(250, self._clear_suppress)
        self._close_popup()

    def _clear_suppress(self):
        self._suppress_toggle = False

    def _root_click(self, event):
        """Close the list when the user clicks anywhere else in the window."""
        if self.popup is None:
            return
        try:
            if str(event.widget).startswith(str(self)):
                return
        except Exception:
            pass
        self._close_popup()

    def _open_popup(self):
        if RoundSelect._active is not None and RoundSelect._active is not self:
            RoundSelect._active._close_popup()
        if self.popup is not None:
            self._close_popup()

        c = self.c
        w, h = self._popup_size()
        x = self.winfo_rootx()
        y = self.winfo_rooty() + self.h + 4
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        if x + w > sw - 8:
            x = max(8, sw - w - 8)
        if y + h > sh - 8:
            y = max(8, self.winfo_rooty() - h - 4)

        key = "#010203"  # colour-keyed background → real rounded corners
        top = tk.Toplevel(self.winfo_toplevel())
        self.popup = top
        top.withdraw()
        top.overrideredirect(True)
        try:
            top.attributes("-topmost", True)
        except Exception:
            pass
        top.configure(bg=key)
        try:
            top.attributes("-transparentcolor", key)
        except Exception:
            pass

        cv = tk.Canvas(top, width=w, height=h, bg=key,
                       highlightthickness=0, bd=0)
        cv.pack()
        self._popup_canvas = cv
        self._card_photo = rounded_photo(w, h, 10, c["card"], c["border"], 1,
                                         key=key)
        cv.create_image(0, 0, anchor="nw", image=self._card_photo)
        self._draw_items()

        cv.bind("<Motion>", self._pop_motion)
        cv.bind("<Button-1>", self._pop_click)
        top.bind("<Escape>", lambda _e: self._close_popup())
        top.bind("<FocusOut>", self._popup_focus_out)

        top.geometry(f"{w}x{h}+{x}+{y}")
        top.deiconify()
        RoundSelect._active = self
        try:
            top.lift()
            top.focus_force()
        except Exception:
            pass

        try:
            top.attributes("-alpha", 0.0)
        except Exception:
            return

        def frame(t):
            try:
                top.attributes("-alpha", t)
                top.geometry(f"{w}x{h}+{x}+{y + int(5 * (1 - t))}")
            except Exception:
                pass

        def done():
            try:
                top.attributes("-alpha", 1.0)
                top.geometry(f"{w}x{h}+{x}+{y}")
            except Exception:
                pass

        self.popup_anim = Animator(top)
        self.popup_anim.run(100, frame, on_done=done)

    def _draw_items(self):
        cv = self._popup_canvas
        if cv is None:
            return
        cv.delete("item")
        c = self.c
        current = self.variable.get()
        for i, value in enumerate(self.values):
            y = self.PAD + i * self.ITEM_H
            if i == self._hover_index:
                ph = rounded_photo(self.w - 12, self.ITEM_H - 2, 7, c["hover"])
                cv.create_image(6, y + 1, anchor="nw", image=ph, tags="item")
                self._hover_photo = ph
            selected = value == current
            cv.create_text(
                16, y + self.ITEM_H / 2, text=value, anchor="w", tags="item",
                fill=c["fg"] if selected else c["muted"],
                font=("Segoe UI", 9, "bold" if selected else "normal"),
            )

    def _pop_motion(self, event):
        index = (event.y - self.PAD) // self.ITEM_H
        if not (0 <= index < len(self.values)):
            index = None
        if index != self._hover_index:
            self._hover_index = index
            self._draw_items()

    def _pop_click(self, event):
        index = (event.y - self.PAD) // self.ITEM_H
        if 0 <= index < len(self.values):
            value = self.values[index]
            self._close_popup()
            if value != self.variable.get():
                self.variable.set(value)
                if self.command:
                    self.command(value)
        else:
            self._close_popup()

    def _close_popup(self):
        top, self.popup = self.popup, None
        if RoundSelect._active is self:
            RoundSelect._active = None
        if top is None:
            return
        if self.popup_anim is not None:
            self.popup_anim.cancel()
            self.popup_anim = None
        self._hover_index = None
        try:
            top.destroy()
        except Exception:
            pass


class RoundEntry(tk.Canvas):
    """Entry with a rounded outline."""

    def __init__(self, parent, variable, colors, width=416, height=36, show=None,
                 bg=None):
        super().__init__(
            parent, width=width, height=height, bg=bg or colors["card"],
            highlightthickness=0, bd=0,
        )
        self.c = colors
        self.w, self.h = width, height
        self.entry = tk.Entry(
            self, textvariable=variable, bg=colors["card"], fg=colors["fg"],
            insertbackground=colors["fg"], relief="flat", bd=0,
            font=("Segoe UI", 10), highlightthickness=0, show=show,
        )
        self.create_window(12, height / 2, anchor="w", window=self.entry,
                           width=width - 24, height=height - 12)
        self.focus = 0.0
        self.anim = Animator(self)
        self._redraw()
        self.entry.bind("<FocusIn>", lambda _e: self._focus(True))
        self.entry.bind("<FocusOut>", lambda _e: self._focus(False))

    def _redraw(self):
        self.delete("shape")
        border = blend(self.c["border"], self.c["accent"], self.focus)
        photo = rounded_photo(self.w, self.h, 9, self.c["card"], border, 1)
        self.create_image(0, 0, anchor="nw", image=photo, tags="shape")
        self._shape_photo = photo
        self.tag_lower("shape")

    def _focus(self, state):
        target = 1.0 if state else 0.0
        start = self.focus

        def frame(t):
            self.focus = start + (target - start) * t
            self._redraw()

        self.anim.run(120, frame)


# ---------------------------------------------------------------- settings ---

class SettingsWindow:
    WIDTH = 520
    PAD = 22
    CARD_W = WIDTH - 2 * PAD          # 476
    INNER_W = CARD_W - 24             # 452
    CONTENT_W = INNER_W - 32          # 420

    def __init__(self, app):
        self.app = app
        self.cfg = load_settings()
        self.c = palette(system_is_dark())
        self.win = None
        self.body = None
        self._toggle_keys = ("now_playing", "animated_backdrop", "sync", "audio",
                             "fullscreen")
        self.state = {
            key: bool(self.cfg.get(key, DEFAULTS.get(key, False)))
            for key in self._toggle_keys
        }
        self.state["autostart"] = autostart_enabled()
        self._cards = []
        self.win_anim = None
        self._home = None
        self._closing = False
        self._built_language = None

    # -- helpers -----------------------------------------------------------
    def _label(self, parent, text, size=10, bold=False, color=None, bg=None, wrap=0):
        return tk.Label(
            parent, text=text, bg=bg or self.c["card"], fg=color or self.c["fg"],
            font=("Segoe UI", size, "bold" if bold else "normal"),
            anchor="w", justify="left", wraplength=wrap,
        )

    def _caption(self, parent, text, wrap=None):
        return tk.Label(
            parent, text=text, bg=self.c["card"], fg=self.c["muted"],
            font=("Segoe UI", 8), anchor="w", justify="left",
            wraplength=wrap or self.CONTENT_W,
        )

    def _section(self, parent, text, top=0):
        tk.Label(
            parent, text=text, bg=self.c["bg"], fg=self.c["muted"],
            font=("Segoe UI", 8, "bold"), anchor="w",
        ).pack(anchor="w", pady=(top, 5))

    def _card(self, parent):
        holder = tk.Canvas(parent, bg=self.c["bg"], highlightthickness=0, bd=0,
                           width=self.CARD_W, height=10)
        holder.pack(fill="x", pady=(0, 12))
        frame = tk.Frame(holder, bg=self.c["card"], padx=16, pady=6)
        holder.create_window(12, 8, anchor="nw", window=frame, width=self.INNER_W)
        self._cards.append((holder, frame))
        return holder, frame

    def _layout_cards(self):
        for holder, frame in self._cards:
            frame.update_idletasks()
            height = frame.winfo_reqheight() + 16
            holder.configure(height=height)
            holder.delete("bg")
            photo = rounded_photo(self.CARD_W, height, 14, self.c["card"])
            holder.create_image(0, 0, anchor="nw", image=photo, tags="bg")
            holder._bg_photo = photo
            holder.tag_lower("bg")

    def _row(self, parent):
        row = tk.Frame(parent, bg=self.c["card"])
        row.pack(fill="x", pady=5)
        text = tk.Frame(row, bg=self.c["card"])
        text.pack(side="left", fill="x", expand=True)
        return row, text

    def _toggle_row(self, parent, key, title, hint):
        row, text = self._row(parent)
        self._label(text, title, 10, bold=True).pack(anchor="w")
        self._caption(text, hint, wrap=self.CONTENT_W - 70).pack(anchor="w")

        def changed(value, k=key):
            self.state[k] = value

        toggle = PillToggle(row, self.c, self.state.get(key, False), command=changed)
        toggle.pack(side="right", padx=(10, 0))
        return toggle

    def _select_row(self, parent, title, hint, values, variable):
        row, text = self._row(parent)
        self._label(text, title, 10, bold=True).pack(anchor="w")
        self._caption(text, hint, wrap=self.CONTENT_W - 240).pack(anchor="w")
        select = RoundSelect(row, values, variable, self.c)
        select.pack(side="right", padx=(10, 0))
        return select

    def _entry_block(self, parent, title, hint, variable, show=None):
        self._label(parent, title, 10, bold=True).pack(anchor="w", pady=(8, 0))
        if hint:
            self._caption(parent, hint).pack(anchor="w")
        entry = RoundEntry(parent, variable, self.c, width=self.CONTENT_W, show=show)
        entry.pack(anchor="w", pady=(6, 4))
        return entry

    # -- window ------------------------------------------------------------
    def _init_vars(self):
        cfg = self.cfg
        self.var_name = tk.StringVar(value=cfg.get("name", DEFAULTS["name"]))
        self.var_window = tk.StringVar(value=cfg.get("window_title", ""))

        self.var_res = tk.StringVar()
        current = cfg.get("resolution", "auto")
        if current not in RESOLUTION_KEYS:
            current = "auto"
        self.var_res.set(resolution_label(current))

        fps = cfg.get("fps", 60)
        values = [f"{v} fps" for v in FPS_CHOICES]
        self.var_fps = tk.StringVar(value=f"{fps} fps" if fps in FPS_CHOICES else values[-1])

        lang = str(cfg.get("language", DEFAULTS["language"])).strip().lower()
        self.var_lang = tk.StringVar(
            value=dict(LANGUAGES)["ru" if lang.startswith("ru") else "en"]
        )

    def show(self):
        self.c = palette(system_is_dark())
        self.cfg = load_settings()
        self.state.update({
            key: bool(self.cfg.get(key, DEFAULTS.get(key, False)))
            for key in self._toggle_keys
        })
        self.state["autostart"] = autostart_enabled()
        self._init_vars()

        if self.win is not None:
            try:
                if self.win.winfo_exists() and \
                        getattr(self, "_built_language", LANGUAGE) == LANGUAGE:
                    self._closing = False
                    self.win.deiconify()
                    self.win.lift()
                    self.win.focus_force()
                    self._animate_in()
                    return
                if self.win.winfo_exists():
                    self.win.destroy()  # rebuild in the new language
                self.win = None
            except Exception:
                self.win = None

        c = self.c
        win = tk.Toplevel(self.app.root)
        self.win = win
        win.withdraw()  # avoid a flash at the default position before we place it
        win.title(tr("settings_window_title"))
        win.configure(bg=c["bg"])
        win.resizable(False, False)
        if ICON_FILE.exists():
            try:
                win.iconbitmap(str(ICON_FILE))
            except Exception:
                pass

        outer = tk.Frame(win, bg=c["bg"], padx=self.PAD, pady=14)
        outer.pack(fill="both", expand=True)

        head = tk.Frame(outer, bg=c["bg"])
        head.pack(fill="x", pady=(0, 14))

        titles = tk.Frame(head, bg=c["bg"])
        titles.pack(side="left", fill="x", expand=True)
        self._label(titles, tr("settings_title"), 15, bold=True,
                    bg=c["bg"]).pack(anchor="w")
        self._label(titles, tr("settings_subtitle"), 9,
                    color=c["muted"], bg=c["bg"]).pack(anchor="w", pady=(1, 0))

        lang_select = RoundSelect(
            head, [label for _code, label in LANGUAGES], self.var_lang, c,
            width=118, height=30, bg=c["bg"],
        )
        self.lang_select = lang_select
        lang_select.pack(side="right", padx=(12, 0), pady=(2, 0))
        Tooltip(lang_select, tr("language_hint"), c)

        self.body = tk.Frame(outer, bg=c["bg"], width=self.CARD_W)
        self.body.pack(fill="x")

        self._cards = []  # drop references to widgets of a previously closed window
        self._build_general()
        self._layout_cards()

        buttons = tk.Frame(outer, bg=c["bg"])
        buttons.pack(fill="x", pady=(2, 0))
        RoundButton(buttons, tr("cancel"), self.close, c, kind="ghost",
                    height=34, radius=10, bg=c["bg"]).pack(side="right")
        RoundButton(buttons, tr("save"), self.save, c, kind="primary",
                    height=34, radius=10, bg=c["bg"]).pack(side="right", padx=(0, 8))

        win.bind("<Escape>", lambda _e: self.close())
        win.bind("<Return>", lambda _e: self.save())
        self._apply_titlebar_theme()
        round_window_corners(win)
        self.win_anim = Animator(win)
        self._built_language = LANGUAGE
        self._resize()
        self._animate_in()

    def _animate_in(self):
        win = self.win
        if win is None or self.win_anim is None or self._home is None:
            return
        w, h, x, y = self._home
        try:
            win.attributes("-alpha", 0.0)
        except Exception:
            return
        win.deiconify()
        win.lift()
        win.focus_force()

        def frame(t):
            win.attributes("-alpha", t)
            win.geometry(f"{w}x{h}+{x}+{y + int(14 * (1 - t))}")

        def done():
            win.attributes("-alpha", 1.0)
            win.geometry(f"{w}x{h}+{x}+{y}")

        self.win_anim.run(200, frame, on_done=done)

    def _resize(self):
        if self.win is None:
            return
        self.win.update_idletasks()
        width = self.WIDTH
        height = self.win.winfo_reqheight()
        _l, _t, right, bottom = NowPlayingWindow._work_area()
        x = max(_l, (right - _l - width) // 2 + _l)
        y = max(_t, (bottom - _t - height) // 2 + _t - 30)
        self._home = (width, height, x, y)
        self.win.geometry(f"{width}x{height}+{x}+{y}")

    # -- general tab -------------------------------------------------------
    def _build_general(self):
        c = self.c
        body = self.body

        self._section(body, tr("section_connection"))
        holder, card = self._card(body)

        self._entry_block(card, tr("device_name"), tr("device_name_hint"), self.var_name)
        self._entry_block(card, tr("window_title"), tr("window_title_hint"), self.var_window)

        self._section(body, tr("section_quality"), top=4)
        holder, card = self._card(body)

        res_values = [resolution_label(key) for key in RESOLUTION_KEYS]
        self._select_row(card, tr("resolution"), tr("resolution_hint"),
                         res_values, self.var_res)

        fps_values = [f"{v} fps" for v in FPS_CHOICES]
        self._select_row(card, tr("fps"), tr("fps_hint"),
                         fps_values, self.var_fps)

        self._section(body, tr("section_behavior"), top=4)
        holder, card = self._card(body)
        self._toggle_row(card, "now_playing", tr("now_playing_title"),
                         tr("now_playing_hint"))
        self._toggle_row(card, "animated_backdrop", tr("animated_backdrop_title"),
                         tr("animated_backdrop_hint"))
        self._toggle_row(card, "sync", tr("sync_title"),
                         tr("sync_hint"))
        self._toggle_row(card, "audio", tr("audio_title"),
                         tr("audio_hint"))
        self._toggle_row(card, "fullscreen", tr("fullscreen_title"),
                         tr("fullscreen_hint"))
        self._toggle_row(card, "autostart", tr("autostart_title"),
                         tr("autostart_hint"))

    # -- theme -------------------------------------------------------------
    def _apply_titlebar_theme(self):
        try:
            hwnd = ctypes.windll.user32.GetParent(self.win.winfo_id())
            value = ctypes.c_int(1 if system_is_dark() else 0)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(value), ctypes.sizeof(value))
        except Exception:
            pass

    # -- lifecycle ---------------------------------------------------------
    def close(self):
        win = self.win
        if win is None or self._closing:
            return
        self._closing = True
        try:
            alpha = float(win.attributes("-alpha"))
        except Exception:
            alpha = 1.0

        def frame(t):
            try:
                win.attributes("-alpha", alpha * (1 - t))
            except Exception:
                pass

        def done():
            self._closing = False
            try:
                win.destroy()
            except Exception:
                pass
            if self.win is win:
                self.win = None

        if self.win_anim is None:
            done()
        else:
            self.win_anim.run(110, frame, on_done=done)

    def save(self):
        old = load_settings()
        cfg = dict(old)
        cfg["name"] = self.var_name.get().strip() or DEFAULTS["name"]
        cfg["window_title"] = self.var_window.get().strip()
        label_to_key = {resolution_label(key): key for key in RESOLUTION_KEYS}
        cfg["resolution"] = label_to_key.get(self.var_res.get(), "auto")
        cfg["fps"] = int(str(self.var_fps.get()).split()[0])
        lang_to_code = {label: code for code, label in LANGUAGES}
        cfg["language"] = lang_to_code.get(self.var_lang.get(), DEFAULTS["language"])
        for key in self._toggle_keys:
            cfg[key] = bool(self.state.get(key, cfg.get(key, False)))
        for stale in ("discord_enabled", "discord_client_id", "discord_name",
                      "discord_format", "discord_time", "discord_cover",
                      "discord_artist_photo", "discord_paused"):
            cfg.pop(stale, None)
        set_autostart(bool(self.state.get("autostart", False)))

        save_settings(cfg)
        server_keys = ("name", "resolution", "fps", "sync", "audio", "fullscreen", "now_playing")
        need_restart = any(old.get(k) != cfg.get(k) for k in server_keys)
        self.app.apply_settings(cfg, restart=need_restart)
        self.close()


# --------------------------------------------------------------------- app ---

class AirMirrorApp:
    def __init__(self):
        import tkinter as tk
        from pystray import Icon, Menu, MenuItem

        self.root = tk.Tk()
        self.root.withdraw()
        self.cfg = load_settings()
        init_language(self.cfg)
        self._Menu = Menu
        self._MenuItem = MenuItem
        self.server = UxPlayServer()
        self.renamer = WindowRenamer(self)
        self.commands = queue.Queue()
        self.now_playing = NowPlayingWindow(self)
        self.np_watcher = NowPlayingWatcher(self)
        self.settings_window = SettingsWindow(self)
        self._alive = True
        self._session_active = False
        self._menu_key = None

        ensure_icon_file()
        image = build_icon_image(64)

        self.icon = Icon(
            "airmirror",
            image,
            f"AirMirror — {self.cfg['name']}",
            self._build_menu(Menu, MenuItem),
        )

        self.root.after(80, self._poll)
        self.root.after(150, self._startup)
        self.renamer.start()
        self.np_watcher.start()
        if (os.environ.get("AIRMIRROR_SELFTEST") or os.environ.get("AIRPLAY_SELFTEST")):
            self.root.after(6000, lambda: self.commands.put(self._shutdown))

    # -- thread-safe command queue ----------------------------------------
    def _poll(self):
        if not self._alive:
            return
        while True:
            if not self._alive:
                return
            try:
                fn = self.commands.get_nowait()
            except queue.Empty:
                break
            try:
                fn()
            except Exception:
                self._log_error()
        if self._alive:
            self._refresh_menu()
            self.root.after(80, self._poll)

    def _queue_open_settings(self, icon=None, item=None):
        self.commands.put(self.settings_window.show)

    def _queue_quit(self, icon=None, item=None):
        self.commands.put(self._shutdown)

    # -- tray menu ---------------------------------------------------------
    def _build_menu(self, Menu, MenuItem):
        resolution_items = [
            MenuItem(
                resolution_label(key),
                self._queue_resolution(key),
                checked=lambda item, k=key: self.cfg.get("resolution") == k,
                radio=True,
            )
            for key in RESOLUTION_KEYS
        ]
        return Menu(
            MenuItem(tr("tray_settings"), self._queue_open_settings, default=True),
            Menu.SEPARATOR,
            MenuItem(tr("tray_resolution"), None, enabled=False),
            *resolution_items,
            Menu.SEPARATOR,
            MenuItem(
                tr("tray_stop"),
                self._queue_stop_session,
                enabled=lambda item: self._session_active,
            ),
            MenuItem(tr("tray_restart"), self._queue_restart_server),
            MenuItem(tr("tray_log"), self._queue_open_log),
            Menu.SEPARATOR,
            MenuItem(tr("tray_quit"), self._queue_quit),
        )

    def _rebuild_menu(self):
        """Re-create the tray menu (used when the UI language changes)."""
        if self._Menu is None:
            return
        try:
            self.icon.menu = self._build_menu(self._Menu, self._MenuItem)
            self._menu_key = None
            self.icon.update_menu()
        except Exception:
            self._log_error()

    def _queue_resolution(self, key):
        def handler(icon=None, item=None):
            self.commands.put(lambda: self._set_resolution(key))
        return handler

    def _queue_stop_session(self, icon=None, item=None):
        self.commands.put(self._stop_session)

    def _queue_restart_server(self, icon=None, item=None):
        self.commands.put(self._restart_server)

    def _queue_open_log(self, icon=None, item=None):
        self.commands.put(self._open_log)

    def _refresh_menu(self, force=False):
        """Rebuild the tray menu when something it displays has changed."""
        running = self.server.running()
        active = running and (
            self.renamer.mirroring
            or time.time() - self.np_watcher.reader.updated < 120
        )
        key = (running, active, self.cfg.get("resolution"))
        if not force and key == self._menu_key:
            return
        self._menu_key = key
        self._session_active = active
        try:
            self.icon.update_menu()
        except Exception:
            pass

    def _set_resolution(self, key):
        if key == self.cfg.get("resolution"):
            return
        cfg = load_settings()
        cfg["resolution"] = key
        if "@" in key:
            try:
                cfg["fps"] = int(key.rsplit("@", 1)[1])
            except ValueError:
                pass
        save_settings(cfg)
        self.apply_settings(cfg, restart=True)

    def _restart_server(self):
        exe, _runtime = uxplay_paths()
        if not exe.exists():
            self._notify("AirMirror", tr("err_uxplay_missing", path=exe))
            return
        self.now_playing.reset()
        self.now_playing.hide()
        self.server.start(self.cfg)
        self.np_watcher.reader.updated = 0.0
        self._notify("AirMirror", tr("notif_server_restarted"))

    def _stop_session(self):
        # UxPlay has no "disconnect" control, so the receiver process is
        # restarted: the phone drops the session and the PC stays visible.
        if not self.server.running():
            return
        self.now_playing.reset()
        self.now_playing.hide()
        self.server.start(self.cfg)
        self.np_watcher.reader.updated = 0.0
        self._notify("AirMirror", tr("notif_session_stopped"))

    def _open_log(self):
        try:
            if not UXPLAY_LOG.exists():
                self._notify("AirMirror", tr("notif_log_empty"))
                return
            os.startfile(str(UXPLAY_LOG))
        except Exception:
            self._log_error()

    # -- lifecycle ---------------------------------------------------------
    def _startup(self):
        exe, _runtime = uxplay_paths()
        if not exe.exists():
            ctypes.windll.user32.MessageBoxW(
                None, tr("err_uxplay_missing", path=exe), "AirMirror", 0x10
            )
            self._shutdown()
            return
        self.server.start(self.cfg)
        self._notify(tr("notif_started_title"),
                     tr("notif_started_msg", name=self.cfg['name']))

    def apply_settings(self, cfg, restart=True):
        old_language = self.cfg.get("language", DEFAULTS["language"])
        self.cfg = cfg
        init_language(cfg)
        self.icon.title = f"AirMirror — {cfg['name']}"
        if cfg.get("language", DEFAULTS["language"]) != old_language:
            self._rebuild_menu()
            self.now_playing.retranslate()
        self.now_playing.reset()
        self.now_playing.apply_settings(cfg)
        self.now_playing.hide()
        if restart:
            self.server.start(cfg)
            self._notify(tr("notif_settings_title"),
                         tr("notif_settings_restart", name=cfg['name']))
        else:
            self._notify(tr("notif_settings_title"), tr("notif_settings_saved"))

    def window_title(self):
        return (self.cfg.get("window_title") or "").strip() or self.cfg["name"]

    def _notify(self, title, message):
        try:
            self.icon.notify(message, title)
        except Exception:
            pass

    def _shutdown(self):
        self._alive = False
        try:
            self.renamer.stop()
            self.np_watcher.stop()
            self.now_playing.destroy()
            self.server.stop()
        finally:
            try:
                self.icon.visible = False
                self.icon.stop()
            except Exception:
                pass
            try:
                self.root.quit()
                self.root.destroy()
            except Exception:
                pass

    @staticmethod
    def _log_error():
        try:
            with open(ERROR_LOG, "a", encoding="utf-8") as fh:
                fh.write(traceback.format_exc() + "\n")
        except Exception:
            pass

    def run(self):
        try:
            self.icon.run_detached()
        except Exception:
            threading.Thread(target=self.icon.run, daemon=True).start()
        self.root.mainloop()


def main():
    # crisp UI on high-DPI displays
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

    # one-time migration from the old data directory, before anything reads settings
    migrate_data_dir()

    # language for early messages (settings are read again by the app)
    init_language()

    # single instance
    kernel32 = ctypes.windll.kernel32
    mutex = kernel32.CreateMutexW(None, False, "Local\\AirMirrorAppMutex")
    if not mutex or kernel32.GetLastError() == 183:
        ctypes.windll.user32.MessageBoxW(None, tr("err_already_running"), "AirMirror", 0x40)
        return

    try:
        migrate_old_settings()
        app = AirMirrorApp()
        if "--settings" in sys.argv:
            app.root.after(400, app.settings_window.show)
        app.run()
    except Exception:
        try:
            with open(ERROR_LOG, "a", encoding="utf-8") as fh:
                fh.write(traceback.format_exc() + "\n")
        except Exception:
            pass
        ctypes.windll.user32.MessageBoxW(None, tr("err_start_failed"), "AirMirror", 0x10)


if __name__ == "__main__":
    main()
