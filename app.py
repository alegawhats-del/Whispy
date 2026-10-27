# -*- coding: utf-8 -*-
"""
Whispy — YouTube-ссылка в текст с таймкодами + ИИ-ассистент.
Сначала берём готовые субтитры YouTube, если их нет — качаем аудио (yt-dlp)
и распознаём через faster-whisper. Всё локально, бесплатно, офлайн после первого запуска.
"""

import os
import re
import sys
import json
import glob
import math
import queue
import shutil
import ctypes
import time
import datetime
import threading
import subprocess
import webbrowser
import urllib.error
import urllib.request
import tkinter as tk
from tkinter import font as tkfont

# ---------- пути ----------
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

APP_VERSION = "2.2.2"
# Откуда проверять обновления: JSON вида {"version": "2.3.0", "notes": "...", "setup": "https://.../Whispy-Setup-2.3.0.exe",
# "portable": "https://.../Whispy.exe"}. Поменяй на свой репозиторий или свой сервер.
UPDATE_URL = "https://raw.githubusercontent.com/alegawhats-del/Whispy/main/version.json"

INSTALLED = os.path.exists(os.path.join(BASE_DIR, "installed.flag"))  # флаг кладёт установщик
if INSTALLED:
    DATA_DIR = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "Whispy")
    _docs = os.path.join(os.path.expanduser("~"), "Documents")
    OUT_DIR = os.path.join(_docs if os.path.isdir(_docs) else DATA_DIR, "Whispy")
else:
    DATA_DIR = BASE_DIR
    OUT_DIR = os.path.join(BASE_DIR, "Транскрипты")
MODELS_DIR = os.path.join(DATA_DIR, "models")
TEMP_DIR = os.path.join(DATA_DIR, "temp")
UPDATES_DIR = os.path.join(DATA_DIR, "updates")
SETTINGS_PATH = os.path.join(DATA_DIR, "settings.json")
for _d in (OUT_DIR, MODELS_DIR, TEMP_DIR, UPDATES_DIR):
    os.makedirs(_d, exist_ok=True)

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")


def _register_nvidia_dlls():
    try:
        import site
        roots = list(site.getsitepackages()) + [site.getusersitepackages()]
    except Exception:
        roots = []
    if getattr(sys, "frozen", False):
        roots.append(getattr(sys, "_MEIPASS", BASE_DIR))
        roots.append(os.path.join(BASE_DIR, "_internal"))
    for root in roots:
        for d in glob.glob(os.path.join(root, "nvidia", "*", "bin")):
            try:
                os.add_dll_directory(d)
            except Exception:
                pass
            os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")


if sys.platform == "win32":
    _register_nvidia_dlls()

import customtkinter as ctk  # noqa: E402
from PIL import Image, ImageDraw, ImageFilter, ImageTk  # noqa: E402

# ---------- темы ----------
THEMES = {
    "dark": dict(
        BG="#0E0913", CARD="#18111F", BORDER="#2A1E35", FIELD="#221829", FIELD_BORDER="#3A2A47",
        TEXT="#F5EEF9", MUTED="#8C7E98", PINK="#FF5FB4", VIOLET="#8B5CF6", PINK_HOVER="#FF79C2",
        PINK_SOFT="#2E1A33", OK="#4ADE9A", OK_SOFT="#13291F", ERR="#FF6B7A", ERR_SOFT="#321820",
        GREY_SOFT="#1E1726", HERO1="#1B0F2B", HERO2="#0E0913", HERO_TEXT="#FFFFFF", HERO_SUB="#CFC3DB",
        HERO_CHIP="#2A1A3A", HERO_CHIP_BORDER="#4A3460", TOAST="#2A1A3A", TOAST_TEXT="#FFFFFF",
        BLOB_ALPHA=150, GRID_ALPHA=5, SELECT="#8B5CF6",
    ),
    "light": dict(
        BG="#F6F2FA", CARD="#FFFFFF", BORDER="#EADFF2", FIELD="#F4EEF9", FIELD_BORDER="#DCCDE8",
        TEXT="#2A1E33", MUTED="#8A7D96", PINK="#E8449F", VIOLET="#7C4DFF", PINK_HOVER="#F25CB0",
        PINK_SOFT="#FBE6F2", OK="#1FA86B", OK_SOFT="#E3F6EC", ERR="#E24A5C", ERR_SOFT="#FDE6EA",
        GREY_SOFT="#ECE6F1", HERO1="#FFFFFF", HERO2="#F1E7FA", HERO_TEXT="#2A1E33", HERO_SUB="#6F6280",
        HERO_CHIP="#F7EEFB", HERO_CHIP_BORDER="#E3D3F0", TOAST="#2A1E33", TOAST_TEXT="#FFFFFF",
        BLOB_ALPHA=110, GRID_ALPHA=10, SELECT="#C7B6F5",
    ),
}
T = dict(THEMES["dark"])  # активная палитра, меняется apply_theme()


def apply_theme(name: str):
    T.clear()
    T.update(THEMES.get(name, THEMES["dark"]))
    ctk.set_appearance_mode("dark" if name == "dark" else "light")


def GRAD():
    return (T["PINK"], T["VIOLET"])


LANGS = {"Русский": "ru", "Українська": "uk", "English": "en", "Авто": "auto"}
MODELS = ["small", "medium", "large-v3"]
DEVICES = {"Авто": "auto", "NVIDIA": "gpu", "CPU": "cpu"}
AI_TYPES = ["Тезисы", "Таблица", "Блок-схема", "Презентация", "Инфографика"]

YT_RE = re.compile(r"(https?://)?(www\.|m\.|music\.)?(youtube\.com|youtu\.be)/", re.I)

# ---------- промпты для ИИ ----------
AI_PROMPTS = {
    "Тезисы": (
        "Ниже транскрипт видео с таймкодами. Сделай выжимку главного:\n"
        "1) Заголовок и одна фраза — о чём видео.\n"
        "2) 7–12 главных тезисов, каждый с таймкодом [чч:мм:сс], где об этом говорится.\n"
        "3) 3–5 ключевых цитат (коротко, с таймкодом).\n"
        "4) Практические выводы / что делать.\n"
        "Пиши по-русски, без воды, сохраняй смысл автора."
    ),
    "Таблица": (
        "Ниже транскрипт видео с таймкодами. Построй таблицу главного.\n"
        "Колонки: Раздел | Тезис | Почему это важно | Таймкод.\n"
        "Сгруппируй по темам в порядке видео, 10–20 строк, формулировки короткие и точные.\n"
        "В конце — 3 строки «главное одной фразой». Пиши по-русски."
    ),
    "Блок-схема": (
        "Ниже транскрипт видео с таймкодами. Построй блок-схему главной логики/процесса, "
        "о котором рассказывает автор.\n"
        "1) Сначала 5–8 строк: какая логика/алгоритм прослеживается.\n"
        "2) Затем диаграмму Mermaid (flowchart TD): узлы короткие (до 6 слов), стрелки с подписями "
        "там, где есть условия, в подписях узлов — таймкоды.\n"
        "3) Отрисуй диаграмму визуально (как артефакт), а не только кодом.\n"
        "Пиши по-русски."
    ),
    "Презентация": (
        "Ниже транскрипт видео с таймкодами. Сделай презентацию на 10–12 слайдов по главным тезисам:\n"
        "— слайд 1: название и подзаголовок;\n"
        "— слайд 2: структура;\n"
        "— по слайду на каждый ключевой тезис: заголовок + 3 коротких буллета + таймкод источника;\n"
        "— предпоследний: выводы;\n"
        "— последний: вопросы для обсуждения.\n"
        "Оформи как настоящие слайды (презентацию), стиль современный и чистый. Пиши по-русски."
    ),
    "Инфографика": (
        "Ниже транскрипт видео с таймкодами. Сделай инфографику главного одной страницей (HTML-артефакт):\n"
        "— крупный заголовок и подзаголовок;\n"
        "— 5–8 блоков с ключевыми идеями, в каждом: иконка-эмодзи, заголовок, 1–2 строки сути, таймкод;\n"
        "— 2–4 «цифры/факта» крупно, если они есть в видео;\n"
        "— внизу: 3 вывода.\n"
        "Стиль: премиальный, тёмный фон, акценты розовый #FF5FB4 и фиолетовый #8B5CF6, аккуратная сетка. "
        "Пиши по-русски."
    ),
}


# ---------- утилиты ----------
def fmt_ts(seconds: float) -> str:
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"[{h:02d}:{m:02d}:{s:02d}]"


def safe_name(name: str, limit: int = 80) -> str:
    name = re.sub(r'[\\/:*?"<>|\r\n\t]+', " ", name).strip()
    name = re.sub(r"\s+", " ", name)
    return (name[:limit] or "video").strip()


def human_error(exc: Exception) -> str:
    text = str(exc)
    low = text.lower()
    if "private video" in low:
        return "Видео приватное — к нему нет доступа."
    if "video unavailable" in low or "this video is not available" in low:
        return "Видео недоступно (удалено, заблокировано или ссылка битая)."
    if "sign in" in low and "age" in low:
        return "Видео с возрастным ограничением — YouTube требует вход в аккаунт."
    if "sign in to confirm you" in low or "bot" in low:
        return "YouTube попросил подтвердить, что вы не бот. Попробуйте позже или обновите yt-dlp."
    if "unsupported url" in low or "is not a valid url" in low:
        return "Это не похоже на ссылку YouTube."
    if "premieres" in low or "live event" in low or "is live" in low:
        return "Это прямой эфир или премьера — дождитесь окончания трансляции."
    if "urlopen" in low or "getaddrinfo" in low or "timed out" in low or "connection" in low:
        return "Нет связи с YouTube. Проверьте интернет."
    if "cuda" in low or "cudnn" in low or "cublas" in low:
        return "Проблема с видеокартой/CUDA: " + text[:200] + "\nПереключите устройство на CPU."
    return text[:400]


def open_path(path: str):
    if sys.platform == "win32":
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def mix(c1, c2, t):
    a, b = hex_rgb(c1), hex_rgb(c2)
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def rgb_hex(rgb):
    return "#%02x%02x%02x" % rgb


def font_exists(name: str) -> bool:
    try:
        return name in tkfont.families()
    except Exception:
        return False


def load_settings() -> dict:
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_settings(d: dict):
    try:
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def load_default_key() -> str:
    """Ключ API, зашитый в сборку: файл default_key.txt рядом с exe / в _internal / в _MEIPASS."""
    import base64
    for root in (BASE_DIR, getattr(sys, "_MEIPASS", ""), os.path.join(BASE_DIR, "_internal")):
        p = os.path.join(root, "default_key.txt") if root else ""
        if p and os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    raw = f.read().strip()
                if raw.startswith("b64:"):
                    raw = base64.b64decode(raw[4:]).decode("utf-8").strip()
                return raw
            except Exception:
                return ""
    return ""


def find_icon():
    for root in (BASE_DIR, getattr(sys, "_MEIPASS", ""), os.path.join(BASE_DIR, "_internal")):
        p = os.path.join(root, "whispy.ico") if root else ""
        if p and os.path.exists(p):
            return p
    return None


# ---------- графика (PIL) ----------
def gradient(w, h, c1, c2, diagonal=True):
    a, b = hex_rgb(c1), hex_rgb(c2)
    if diagonal:
        m = mix(c1, c2, 0.5)
        base = Image.new("RGB", (2, 2))
        base.putdata([a, m, m, b])
    else:
        base = Image.new("RGB", (2, 1))
        base.putdata([a, b])
    return base.resize((max(w, 1), max(h, 1)), Image.BILINEAR)


def rounded_mask(w, h, r):
    s = 4
    m = Image.new("L", (w * s, h * s), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, w * s - 1, h * s - 1], radius=r * s, fill=255)
    return m.resize((w, h), Image.LANCZOS)


def pill(w, h, c1, c2, bg, radius=None, brightness=1.0, glow=0):
    radius = h // 2 if radius is None else radius
    pad = glow
    W, H = w + pad * 2, h + pad * 2
    canvas = Image.new("RGB", (W, H), hex_rgb(bg))
    if glow:
        g = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        gd = ImageDraw.Draw(g)
        gd.rounded_rectangle([pad, pad, pad + w, pad + h], radius=radius, fill=hex_rgb(c1) + (120,))
        g = g.filter(ImageFilter.GaussianBlur(glow / 2))
        canvas.paste(g, (0, 0), g)
    grad = gradient(w, h, c1, c2)
    if brightness != 1.0:
        grad = grad.point(lambda p: min(255, int(p * brightness)))
    canvas.paste(grad, (pad, pad), rounded_mask(w, h, radius))
    return canvas


def flat_pill(w, h, color, bg, radius=None, border=None):
    radius = h // 2 if radius is None else radius
    canvas = Image.new("RGB", (w, h), hex_rgb(bg))
    fill = Image.new("RGB", (w, h), hex_rgb(color))
    canvas.paste(fill, (0, 0), rounded_mask(w, h, radius))
    if border:
        s = 4
        b = Image.new("L", (w * s, h * s), 0)
        ImageDraw.Draw(b).rounded_rectangle([0, 0, w * s - 1, h * s - 1], radius=radius * s, outline=255, width=s)
        b = b.resize((w, h), Image.LANCZOS)
        canvas.paste(Image.new("RGB", (w, h), hex_rgb(border)), (0, 0), b)
    return canvas


def hero_image(w, h):
    img = gradient(w, h, T["HERO1"], T["HERO2"])
    blobs = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    bd = ImageDraw.Draw(blobs)
    a = T["BLOB_ALPHA"]
    bd.ellipse([w * 0.55, -h * 0.9, w * 0.95, h * 0.9], fill=hex_rgb(T["PINK"]) + (a,))
    bd.ellipse([w * 0.72, h * 0.1, w * 1.15, h * 1.6], fill=hex_rgb(T["VIOLET"]) + (a + 10,))
    bd.ellipse([-w * 0.1, h * 0.4, w * 0.25, h * 1.5], fill=hex_rgb(T["VIOLET"]) + (a // 2,))
    blobs = blobs.filter(ImageFilter.GaussianBlur(h * 0.45))
    img.paste(blobs, (0, 0), blobs)
    d = ImageDraw.Draw(img, "RGBA")
    grid_col = (255, 255, 255, T["GRID_ALPHA"]) if T["HERO_TEXT"] == "#FFFFFF" else (90, 60, 120, T["GRID_ALPHA"])
    for x in range(0, w, 40):
        d.line([x, 0, x, h], fill=grid_col)
    bars = [0.25, 0.5, 0.85, 0.6, 0.35, 0.7, 0.3]
    bw, gap = 8, 7
    total = len(bars) * bw + (len(bars) - 1) * gap
    x = w - total - 120
    g1, g2 = GRAD()
    for i, hb in enumerate(bars):
        bh = h * 0.55 * hb
        y0 = (h - bh) / 2
        col = mix(g1, g2, i / (len(bars) - 1))
        d.rounded_rectangle([x, y0, x + bw, y0 + bh], radius=bw / 2, fill=col + (235,))
        x += bw + gap
    return img


# ---------- кастомные виджеты ----------
class GradientButton(tk.Canvas):
    """Кнопка с градиентом и свечением; GLOW — внешний отступ под свечение."""
    GLOW = 10

    def __init__(self, master, text, command, width=200, height=50, bg=None, font=None, **kw):
        bg = bg or T["CARD"]
        g = self.GLOW
        super().__init__(master, width=width + g * 2, height=height + g * 2, bg=bg,
                         highlightthickness=0, bd=0, cursor="hand2", **kw)
        self.w, self.h, self.bgc = width, height, bg
        self.command = command
        self._state = "normal"
        self._font = font or ("Segoe UI", 13, "bold")
        c1, c2 = GRAD()
        self._imgs = {
            "normal": ImageTk.PhotoImage(pill(width, height, c1, c2, bg, glow=g)),
            "hover": ImageTk.PhotoImage(pill(width, height, c1, c2, bg, brightness=1.12, glow=g)),
            "disabled": ImageTk.PhotoImage(flat_pill(width + g * 2, height + g * 2, T["FIELD"], bg,
                                                     radius=(height + g * 2) // 2)),
        }
        self._img_id = self.create_image(0, 0, anchor="nw", image=self._imgs["normal"])
        self._txt_id = self.create_text((width + g * 2) / 2, (height + g * 2) / 2, text=text,
                                        fill="#FFFFFF", font=self._font)
        self.bind("<Enter>", lambda e: self._set_img("hover"))
        self.bind("<Leave>", lambda e: self._set_img("normal"))
        self.bind("<Button-1>", self._click)

    def _set_img(self, key):
        if self._state == "normal":
            self.itemconfigure(self._img_id, image=self._imgs[key])

    def _click(self, _):
        if self._state == "normal" and self.command:
            self.command()

    def configure(self, **kw):
        if "text" in kw:
            self.itemconfigure(self._txt_id, text=kw.pop("text"))
        if "state" in kw:
            self._state = kw.pop("state")
            if self._state == "disabled":
                self.itemconfigure(self._img_id, image=self._imgs["disabled"])
                self.itemconfigure(self._txt_id, fill=T["MUTED"])
                super().configure(cursor="arrow")
            else:
                self.itemconfigure(self._img_id, image=self._imgs["normal"])
                self.itemconfigure(self._txt_id, fill="#FFFFFF")
                super().configure(cursor="hand2")
        if kw:
            super().configure(**kw)


class GhostButton(tk.Canvas):
    """Кнопка с тонкой рамкой; при наведении — мягкая заливка и акцентный текст."""

    def __init__(self, master, text, command, width=170, height=42, bg=None, font=None,
                 text_color=None, accent=None, radius=14, **kw):
        bg = bg or T["BG"]
        text_color = text_color or T["TEXT"]
        accent = accent or T["PINK"]
        super().__init__(master, width=width, height=height, bg=bg, highlightthickness=0, bd=0,
                         cursor="hand2", **kw)
        self.command = command
        self._state = "normal"
        self._tc, self._accent = text_color, accent
        self._font = font or ("Segoe UI", 12, "bold")
        self._imgs = {
            "normal": ImageTk.PhotoImage(flat_pill(width, height, bg, bg, radius=radius, border=T["FIELD_BORDER"])),
            "hover": ImageTk.PhotoImage(flat_pill(width, height, T["PINK_SOFT"], bg, radius=radius, border=accent)),
            "disabled": ImageTk.PhotoImage(flat_pill(width, height, bg, bg, radius=radius, border=T["BORDER"])),
        }
        self._img_id = self.create_image(0, 0, anchor="nw", image=self._imgs["normal"])
        self._txt_id = self.create_text(width / 2, height / 2, text=text, fill=text_color, font=self._font)
        self.bind("<Enter>", lambda e: self._hover(True))
        self.bind("<Leave>", lambda e: self._hover(False))
        self.bind("<Button-1>", lambda e: self._state == "normal" and self.command and self.command())

    def _hover(self, on):
        if self._state != "normal":
            return
        self.itemconfigure(self._img_id, image=self._imgs["hover" if on else "normal"])
        self.itemconfigure(self._txt_id, fill=self._accent if on else self._tc)

    def configure(self, **kw):
        if "text" in kw:
            self.itemconfigure(self._txt_id, text=kw.pop("text"))
        if "state" in kw:
            self._state = kw.pop("state")
            disabled = self._state == "disabled"
            self.itemconfigure(self._img_id, image=self._imgs["disabled" if disabled else "normal"])
            self.itemconfigure(self._txt_id, fill=T["BORDER"] if disabled else self._tc)
            super().configure(cursor="arrow" if disabled else "hand2")
        if kw:
            super().configure(**kw)


class GradientProgress(tk.Canvas):
    def __init__(self, master, height=10, bg=None, **kw):
        bg = bg or T["CARD"]
        super().__init__(master, height=height + 8, bg=bg, highlightthickness=0, bd=0, **kw)
        self.h, self.bgc = height, bg
        self.value = 0.0
        self.target = 0.0
        self._bar_w = 100
        self._track = None
        self._fill = None
        self._track_id = self.create_image(0, 4, anchor="nw")
        self._fill_id = self.create_image(0, 4, anchor="nw")
        self.bind("<Configure>", self._resize)
        self._job = self.after(40, self._tick)

    def _resize(self, e):
        self._bar_w = max(e.width, 20)
        self._track = ImageTk.PhotoImage(flat_pill(self._bar_w, self.h, T["FIELD"], self.bgc))
        self.itemconfigure(self._track_id, image=self._track)
        self._draw()

    def set(self, v):
        self.target = max(0.0, min(1.0, v))

    def _tick(self):
        if not self.winfo_exists():
            return
        if abs(self.target - self.value) > 0.002:
            self.value += (self.target - self.value) * 0.25
            self._draw()
        elif self.value != self.target:
            self.value = self.target
            self._draw()
        self._job = self.after(40, self._tick)

    def _draw(self):
        fw = int(self._bar_w * self.value)
        if fw < self.h:
            self._fill = None
            self.itemconfigure(self._fill_id, image="")
            return
        c1, c2 = GRAD()
        self._fill = ImageTk.PhotoImage(pill(fw, self.h, c1, c2, self.bgc))
        self.itemconfigure(self._fill_id, image=self._fill)


class Wave(tk.Canvas):
    def __init__(self, master, bars=5, bg=None, **kw):
        bg = bg or T["CARD"]
        self.n = bars
        self.bw, self.gap, self.hmax = 4, 4, 22
        w = bars * self.bw + (bars - 1) * self.gap
        super().__init__(master, width=w, height=self.hmax + 4, bg=bg, highlightthickness=0, bd=0, **kw)
        self.active = False
        self.phase = 0.0
        self.items = []
        c1, c2 = GRAD()
        for i in range(bars):
            col = rgb_hex(mix(c1, c2, i / max(1, bars - 1)))
            x = i * (self.bw + self.gap)
            self.items.append(self.create_rectangle(x, 0, x + self.bw, 0, fill=col, outline=""))
        self._draw(0.15)
        self.after(60, self._tick)

    def _draw(self, amp_scale=None):
        cy = (self.hmax + 4) / 2
        for i, item in enumerate(self.items):
            if self.active:
                a = 0.35 + 0.65 * (0.5 + 0.5 * math.sin(self.phase + i * 0.9))
            else:
                a = amp_scale if amp_scale is not None else 0.15
            h = self.hmax * a
            x = i * (self.bw + self.gap)
            self.coords(item, x, cy - h / 2, x + self.bw, cy + h / 2)

    def _tick(self):
        if not self.winfo_exists():
            return
        if self.active:
            self.phase += 0.35
            self._draw()
        self.after(60, self._tick)

    def start(self):
        self.active = True

    def stop(self):
        self.active = False
        self._draw(0.15)


class Chip(ctk.CTkLabel):
    def __init__(self, master, text="Ожидание", **kw):
        super().__init__(master, text=text, height=28, corner_radius=14, padx=14,
                         fg_color=T["PINK_SOFT"], text_color=T["PINK"],
                         font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"), **kw)

    def set(self, text, kind="work"):
        colors = {
            "work": (T["PINK_SOFT"], T["PINK"]),
            "ok": (T["OK_SOFT"], T["OK"]),
            "err": (T["ERR_SOFT"], T["ERR"]),
            "idle": (T["GREY_SOFT"], T["MUTED"]),
        }[kind]
        self.configure(text=text, fg_color=colors[0], text_color=colors[1])


# ---------- рабочая логика: транскрипт ----------
class Cancelled(Exception):
    pass


class Worker(threading.Thread):
    def __init__(self, url, lang, model_name, device_choice, q):
        super().__init__(daemon=True)
        self.url = url
        self.lang = lang
        self.model_name = model_name
        self.device_choice = device_choice
        self.q = q
        self.cancel = threading.Event()
        self.lines = []

    def emit(self, kind, **data):
        self.q.put((kind, data))

    def status(self, stage, text):
        self.emit("status", stage=stage, text=text)

    def progress(self, value):
        self.emit("progress", value=max(0.0, min(1.0, value)))

    def line(self, t, text):
        self.lines.append((t, text))
        self.emit("line", t=t, text=text)

    def check_cancel(self):
        if self.cancel.is_set():
            raise Cancelled()

    def run(self):
        audio_path = None
        try:
            import yt_dlp

            self.status("Проверка", "Получаю информацию о видео…")
            self.progress(0.02)
            base_opts = {"quiet": True, "no_warnings": True, "noplaylist": True,
                         "skip_download": True, "socket_timeout": 30}
            with yt_dlp.YoutubeDL(base_opts) as ydl:
                info = ydl.extract_info(self.url, download=False)
            if info.get("_type") == "playlist":
                entries = info.get("entries") or []
                if not entries:
                    raise RuntimeError("Видео недоступно (ссылка на пустой плейлист).")
                info = entries[0]

            title = info.get("title") or "video"
            duration = float(info.get("duration") or 0)
            self.emit("meta", title=title, duration=duration)
            self.check_cancel()

            self.status("Субтитры", "Ищу готовые субтитры YouTube…")
            self.progress(0.08)
            source = "Субтитры YouTube"
            got = self.try_subtitles(info)

            if not got:
                self.status("Скачивание", "Субтитров нет — скачиваю аудио…")
                audio_path = self.download_audio(info)
                self.check_cancel()
                self.transcribe(audio_path, duration)
                source = f"faster-whisper ({self.model_name})"

            if not self.lines:
                raise RuntimeError("Не удалось получить ни строки текста.")

            path = self.save(title, source)
            self.progress(1.0)
            self.status("Готово", f"Сохранено: {os.path.basename(path)}")
            self.emit("done", path=path, lines=len(self.lines), source=source, title=title)

        except Cancelled:
            self.status("Отменено", "Остановлено пользователем.")
            self.emit("cancelled")
        except Exception as e:  # noqa: BLE001
            self.status("Ошибка", "Что-то пошло не так.")
            self.emit("error", text=human_error(e))
        finally:
            if audio_path:
                try:
                    os.remove(audio_path)
                except Exception:
                    pass

    def try_subtitles(self, info) -> bool:
        manual = info.get("subtitles") or {}
        auto = info.get("automatic_captions") or {}
        lang = self.lang
        candidates = []

        def pick(pool, want):
            keys = list(pool.keys())
            if want in keys:
                return [want]
            return [k for k in keys if k.split("-")[0] == want]

        if lang == "auto":
            orig = info.get("language") or ""
            candidates += [(manual, k) for k in manual.keys()]
            candidates += [(auto, k) for k in auto.keys() if k.endswith("-orig")]
            if orig:
                candidates += [(auto, k) for k in pick(auto, orig)]
        else:
            candidates += [(manual, k) for k in pick(manual, lang)]
            candidates += [(auto, k) for k in pick(auto, lang)]

        seen = set()
        for pool, key in candidates:
            if key in seen:
                continue
            seen.add(key)
            tracks = pool.get(key) or []
            track = next((t for t in tracks if t.get("ext") == "json3"), None)
            if not track or not track.get("url"):
                continue
            try:
                self.status("Субтитры", f"Загружаю дорожку «{key}»…")
                req = urllib.request.Request(track["url"], headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=30) as resp:
                    raw = resp.read().decode("utf-8", "replace")
                lines = self.parse_json3(raw)
                if len(lines) < 3:
                    continue
                self.progress(0.3)
                total = len(lines)
                for i, (t, text) in enumerate(lines, 1):
                    self.check_cancel()
                    self.line(t, text)
                    if i % 25 == 0:
                        self.progress(0.3 + 0.65 * i / total)
                return True
            except Cancelled:
                raise
            except Exception:
                continue
        return False

    @staticmethod
    def parse_json3(raw: str):
        data = json.loads(raw)
        out = []
        last_text = None
        for ev in data.get("events", []):
            segs = ev.get("segs")
            if not segs:
                continue
            text = "".join(s.get("utf8", "") for s in segs)
            text = re.sub(r"\s+", " ", text).strip()
            if not text or text == last_text:
                continue
            last_text = text
            out.append((ev.get("tStartMs", 0) / 1000.0, text))
        return out

    def download_audio(self, info) -> str:
        import yt_dlp

        vid = info.get("id") or "audio"
        outtmpl = os.path.join(TEMP_DIR, f"{vid}.%(ext)s")
        for old in glob.glob(os.path.join(TEMP_DIR, f"{vid}.*")):
            try:
                os.remove(old)
            except Exception:
                pass

        def hook(d):
            if self.cancel.is_set():
                raise Cancelled()
            if d.get("status") == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                done = d.get("downloaded_bytes") or 0
                if total:
                    self.progress(0.1 + 0.2 * done / total)
                    self.status("Скачивание", f"Аудио: {done / 1048576:.1f} / {total / 1048576:.1f} МБ")
            elif d.get("status") == "finished":
                self.progress(0.3)

        opts = {
            "quiet": True, "no_warnings": True, "noplaylist": True,
            "format": "bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best",
            "outtmpl": outtmpl, "progress_hooks": [hook], "socket_timeout": 30, "retries": 5,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            res = ydl.extract_info(self.url, download=True)
        if res.get("_type") == "playlist":
            res = (res.get("entries") or [{}])[0]
        path = None
        reqs = res.get("requested_downloads") or []
        if reqs:
            path = reqs[0].get("filepath")
        if not path or not os.path.exists(path):
            found = glob.glob(os.path.join(TEMP_DIR, f"{vid}.*"))
            if not found:
                raise RuntimeError("Аудио не скачалось.")
            path = found[0]
        return path

    def pick_device(self):
        choice = self.device_choice
        if choice == "cpu":
            return "cpu", "int8"
        n = 0
        try:
            import ctranslate2
            n = ctranslate2.get_cuda_device_count()
        except Exception:
            n = 0
        if n > 0:
            return "cuda", "float16"
        if choice == "gpu":
            raise RuntimeError("Видеокарта NVIDIA не найдена или не установлены CUDA-библиотеки "
                               "(pip install nvidia-cublas-cu12 nvidia-cudnn-cu12).")
        return "cpu", "int8"

    def transcribe(self, audio_path: str, duration: float):
        from faster_whisper import WhisperModel

        device, compute = self.pick_device()
        dev_name = "NVIDIA" if device == "cuda" else "CPU"
        self.status("Модель", f"Загружаю {self.model_name} ({dev_name}) — при первом запуске скачивается…")
        self.progress(0.32)
        try:
            model = WhisperModel(self.model_name, device=device, compute_type=compute, download_root=MODELS_DIR)
        except Exception as e:  # noqa: BLE001
            if device == "cuda":
                self.emit("warn", text="Видеокарта не завелась, переключаюсь на CPU.\n" + str(e)[:200])
                device, compute = "cpu", "int8"
                model = WhisperModel(self.model_name, device=device, compute_type=compute, download_root=MODELS_DIR)
            else:
                raise

        self.check_cancel()
        self.status("Распознавание", "Слушаю аудио…")
        language = None if self.lang == "auto" else self.lang
        segments, info = model.transcribe(audio_path, language=language, beam_size=5, vad_filter=True,
                                          vad_parameters={"min_silence_duration_ms": 500})
        total = float(info.duration or duration or 0)
        for seg in segments:
            self.check_cancel()
            text = seg.text.strip()
            if not text:
                continue
            self.line(seg.start, text)
            if total:
                self.progress(0.35 + 0.63 * seg.end / total)
                self.status("Распознавание", f"{fmt_ts(seg.end)[1:-1]} из {fmt_ts(total)[1:-1]}")

    def save(self, title: str, source: str) -> str:
        stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M")
        path = os.path.join(OUT_DIR, f"{safe_name(title)}_{stamp}.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"{title}\n{self.url}\nИсточник: {source}\n")
            f.write(f"Дата: {datetime.datetime.now():%d.%m.%Y %H:%M}\n")
            f.write("-" * 60 + "\n\n")
            for t, text in self.lines:
                f.write(f"{fmt_ts(t)} {text}\n")
        return path


# ---------- рабочая логика: ИИ через API ----------
class AIWorker(threading.Thread):
    MODEL = "claude-sonnet-5-5"

    def __init__(self, api_key, prompt, transcript, title, kind, q):
        super().__init__(daemon=True)
        self.api_key, self.prompt, self.transcript, self.title, self.kind, self.q = \
            api_key, prompt, transcript, title, kind, q

    def run(self):
        try:
            self.q.put(("ai_status", {"text": "Отправляю транскрипт в Claude…"}))
            if self.kind == "Инфографика":
                extra = "\nВерни ТОЛЬКО полный HTML-документ, без пояснений до и после."
                ext = ".html"
            elif self.kind == "Блок-схема":
                extra = "\nВерни ответ в Markdown; диаграмму — блоком ```mermaid```."
                ext = ".md"
            else:
                extra = "\nВерни ответ в Markdown."
                ext = ".md"
            body = json.dumps({
                "model": self.MODEL,
                "max_tokens": 8000,
                "messages": [{"role": "user", "content":
                              f"{self.prompt}{extra}\n\nНазвание видео: {self.title}\n\nТРАНСКРИПТ:\n{self.transcript}"}],
            }).encode("utf-8")
            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages", data=body, method="POST",
                headers={"x-api-key": self.api_key, "anthropic-version": "2023-06-01",
                         "content-type": "application/json"})
            with urllib.request.urlopen(req, timeout=600) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
            if not text.strip():
                raise RuntimeError("Пустой ответ от API.")
            if ext == ".html":
                m = re.search(r"<!doctype html.*?</html>|<html.*?</html>", text, re.S | re.I)
                if m:
                    text = m.group(0)
            stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M")
            path = os.path.join(OUT_DIR, f"{safe_name(self.title)}_{self.kind}_{stamp}{ext}")
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            self.q.put(("ai_done", {"path": path}))
        except urllib.error.HTTPError as e:  # type: ignore[attr-defined]
            try:
                msg = json.loads(e.read().decode("utf-8")).get("error", {}).get("message", str(e))
            except Exception:
                msg = str(e)
            self.q.put(("ai_error", {"text": f"API: {msg}"}))
        except Exception as e:  # noqa: BLE001
            self.q.put(("ai_error", {"text": human_error(e)}))


# ---------- обновления ----------
def vtuple(v: str):
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3]) or (0,)


class UpdateCheck(threading.Thread):
    def __init__(self, q, silent):
        super().__init__(daemon=True)
        self.q, self.silent = q, silent

    def run(self):
        try:
            req = urllib.request.Request(f"{UPDATE_URL}?t={int(time.time())}",
                                         headers={"User-Agent": f"Whispy/{APP_VERSION}", "Cache-Control": "no-cache"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            latest = str(data.get("version", "0"))
            if vtuple(latest) > vtuple(APP_VERSION):
                self.q.put(("update_available", {"info": data, "silent": self.silent}))
            else:
                self.q.put(("update_none", {"silent": self.silent}))
        except Exception as e:  # noqa: BLE001
            self.q.put(("update_error", {"silent": self.silent, "text": human_error(e)}))


class UpdateDownload(threading.Thread):
    def __init__(self, url, q):
        super().__init__(daemon=True)
        self.url, self.q = url, q

    def run(self):
        try:
            name = "Whispy-Setup.exe" if INSTALLED else "Whispy-new.exe"
            path = os.path.join(UPDATES_DIR, name)
            req = urllib.request.Request(self.url, headers={"User-Agent": f"Whispy/{APP_VERSION}"})
            with urllib.request.urlopen(req, timeout=60) as resp, open(path, "wb") as f:
                total = int(resp.headers.get("Content-Length") or 0)
                done = 0
                while True:
                    chunk = resp.read(1024 * 256)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    if total:
                        self.q.put(("update_progress", {"value": done / total,
                                                        "text": f"Скачиваю обновление: {done / 1048576:.0f} / {total / 1048576:.0f} МБ"}))
            if os.path.getsize(path) < 1_000_000:
                raise RuntimeError("Скачанный файл подозрительно мал — проверь ссылку в version.json.")
            self.q.put(("update_ready", {"path": path}))
        except Exception as e:  # noqa: BLE001
            self.q.put(("update_error", {"silent": False, "text": human_error(e)}))


def apply_update(path: str):
    """Установленная версия: запускаем тихий установщик. Портативная: подменяем exe через bat."""
    if INSTALLED:
        subprocess.Popen([path, "/SILENT", "/CLOSEAPPLICATIONS", "/RESTARTAPPLICATIONS", "/NORESTART"])
        return
    exe = sys.executable
    bat = os.path.join(UPDATES_DIR, "apply.bat")
    with open(bat, "w", encoding="cp866", errors="replace") as f:
        f.write("@echo off\n:loop\ntimeout /t 1 >nul\n"
                f'del "{exe}" 2>nul\nif exist "{exe}" goto loop\n'
                f'move /y "{path}" "{exe}"\nstart "" "{exe}"\ndel "%~f0"\n')
    subprocess.Popen(["cmd", "/c", bat], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


# ---------- свои окна: выпадающее меню и модальные диалоги ----------
KEY_COLOR = "#010203"  # прозрачный цвет для окон без рамки (Windows)


def _transparent(win):
    win.configure(bg=KEY_COLOR)
    if sys.platform == "win32":
        try:
            win.wm_attributes("-transparentcolor", KEY_COLOR)
            return True
        except Exception:
            pass
    win.configure(bg=T["BG"])
    return False


def card_image(w, h, radius=18, fill=None, border=None, bg=KEY_COLOR):
    """Скруглённая карточка для окон без рамки: края сглажены к цвету карточки, а не к прозрачному ключу,
    иначе по контуру появляется тёмная кайма."""
    img = flat_pill(w, h, fill or T["CARD"], fill or T["CARD"], radius=radius, border=border or T["BORDER"])
    mask = rounded_mask(w, h, radius).point(lambda p: 255 if p >= 128 else 0)
    out = Image.new("RGB", (w, h), hex_rgb(bg))
    out.paste(img, (0, 0), mask)
    return out


class Dropdown(tk.Toplevel):
    """Выпадающее меню под кнопкой панели. items: (label, command, shortcut) или None — разделитель."""

    def __init__(self, master, anchor, items, width=250):
        super().__init__(master)
        self.anchor = anchor
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        _transparent(self)
        pad = 8
        rows = sum(1 for it in items if it) * 36 + sum(1 for it in items if it is None) * 9 + pad * 2 + 4
        self._img = ImageTk.PhotoImage(card_image(width, rows, radius=16))
        cv = tk.Canvas(self, width=width, height=rows, bg=self.cget("bg"), highlightthickness=0, bd=0)
        cv.pack()
        cv.create_image(0, 0, anchor="nw", image=self._img)
        y = pad + 2
        f = ctk.CTkFont(family="Segoe UI", size=12)
        fs = ctk.CTkFont(family="Segoe UI", size=10)
        for it in items:
            if it is None:
                sep = ctk.CTkFrame(self, fg_color=T["BORDER"], bg_color=T["CARD"], height=1, corner_radius=0)
                cv.create_window(pad + 8, y + 4, anchor="nw", window=sep, width=width - pad * 2 - 16)
                y += 9
                continue
            label, cmd, shortcut = (it + (None,))[:3]
            row = ctk.CTkFrame(self, fg_color=T["CARD"], bg_color=T["CARD"], corner_radius=10, height=32)
            lb = ctk.CTkLabel(row, text=label, font=f, text_color=T["TEXT"], anchor="w")
            lb.place(x=12, y=0, relheight=1)
            if shortcut:
                sc = ctk.CTkLabel(row, text=shortcut, font=fs, text_color=T["MUTED"], anchor="e")
                sc.place(relx=1.0, x=-12, y=0, relheight=1, anchor="ne")
            cv.create_window(pad, y, anchor="nw", window=row, width=width - pad * 2, height=32)

            def enter(e, r=row, l=lb):
                r.configure(fg_color=T["PINK_SOFT"])
                l.configure(text_color=T["PINK"])

            def leave(e, r=row, l=lb):
                r.configure(fg_color=T["CARD"])
                l.configure(text_color=T["TEXT"])

            def click(e, c=cmd):
                self.close()
                if c:
                    c()

            for wdg in (row, lb):
                wdg.bind("<Enter>", enter)
                wdg.bind("<Leave>", leave)
                wdg.bind("<Button-1>", click)
            y += 36

        x = anchor.winfo_rootx()
        yy = anchor.winfo_rooty() + anchor.winfo_height() + 6
        self.geometry(f"{width}x{rows}+{x}+{yy}")
        self.bind("<Escape>", lambda e: self.close())
        self.after(10, self.focus_force)
        self.bind("<FocusOut>", lambda e: self.after(80, self._check_focus))

    def _check_focus(self):
        try:
            if self.focus_displayof() is None or not str(self.focus_displayof()).startswith(str(self)):
                self.close()
        except Exception:
            self.close()

    def close(self):
        try:
            if hasattr(self.anchor, "_hover"):
                self.anchor._hover(False)
            self.destroy()
        except Exception:
            pass


class Dialog(tk.Toplevel):
    """Модальное окно в стиле приложения: info / error / confirm / input."""

    def __init__(self, master, title, message, kind="info", secret=False, default="", ok="Ок", cancel="Отмена"):
        super().__init__(master)
        self.result = None
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        _transparent(self)

        W = 500
        wrap = W - 112
        f_msg = tkfont.Font(family="Segoe UI", size=12)
        lines = 0
        for para in message.split("\n"):
            lines += max(1, math.ceil(f_msg.measure(para) / wrap)) if para else 1
        H = 150 + lines * 21 + (62 if kind == "input" else 0)
        self._img = ImageTk.PhotoImage(card_image(W, H, radius=22, border=T["FIELD_BORDER"]))
        cv = tk.Canvas(self, width=W, height=H, bg=self.cget("bg"), highlightthickness=0, bd=0)
        cv.pack()
        cv.create_image(0, 0, anchor="nw", image=self._img)
        self.cv = cv

        # цветной бейдж
        glyph, col, soft = {
            "info": ("✓", T["OK"], T["OK_SOFT"]),
            "error": ("!", T["ERR"], T["ERR_SOFT"]),
            "confirm": ("?", T["PINK"], T["PINK_SOFT"]),
            "input": ("✦", T["VIOLET"], T["PINK_SOFT"]),
        }[kind]
        badge = ctk.CTkLabel(self, text=glyph, width=40, height=40, corner_radius=20, fg_color=soft, bg_color=T["CARD"], text_color=col,
                             font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"))
        cv.create_window(28, 26, anchor="nw", window=badge)
        ttl = ctk.CTkLabel(self, text=title, text_color=T["TEXT"], anchor="w",
                           font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"), fg_color=T["CARD"], bg_color=T["CARD"])
        cv.create_window(80, 46, anchor="w", window=ttl)
        close = GhostButton(self, "✕", self._cancel, width=34, height=34, bg=T["CARD"], text_color=T["MUTED"],
                            accent=T["ERR"], radius=17)
        cv.create_window(W - 28, 29, anchor="ne", window=close)

        msg = ctk.CTkLabel(self, text=message, text_color=T["MUTED"], anchor="w", justify="left", wraplength=wrap,
                           font=ctk.CTkFont(family="Segoe UI", size=12), fg_color=T["CARD"], bg_color=T["CARD"])
        cv.create_window(80, 80, anchor="nw", window=msg, width=wrap)

        y = 80 + lines * 21 + 14
        self.entry = None
        if kind == "input":
            self.var = tk.StringVar(value=default)
            self.entry = ctk.CTkEntry(self, textvariable=self.var, height=42, corner_radius=14, show="•" if secret else "",
                                      fg_color=T["FIELD"], bg_color=T["CARD"], border_color=T["FIELD_BORDER"], border_width=1,
                                      text_color=T["TEXT"], font=ctk.CTkFont(family="Segoe UI", size=13))
            cv.create_window(80, y, anchor="nw", window=self.entry, width=W - 108)
            self.entry.bind("<FocusIn>", lambda e: self.entry.configure(border_color=T["PINK"]))
            y += 62

        bx = W - 28
        if kind in ("confirm", "input"):
            okb = GradientButton(self, ok, self._ok, width=130, height=40, bg=T["CARD"], font=("Segoe UI", 12, "bold"))
            cv.create_window(bx + GradientButton.GLOW, y + 8 - GradientButton.GLOW, anchor="ne", window=okb)
            cb = GhostButton(self, cancel, self._cancel, width=110, height=40, bg=T["CARD"])
            cv.create_window(bx - 140, y + 8, anchor="ne", window=cb)
        else:
            okb = GradientButton(self, ok, self._ok, width=120, height=40, bg=T["CARD"], font=("Segoe UI", 12, "bold"))
            cv.create_window(bx + GradientButton.GLOW, y + 8 - GradientButton.GLOW, anchor="ne", window=okb)

        # перетаскивание за любое место карточки
        cv.bind("<ButtonPress-1>", self._drag_start)
        cv.bind("<B1-Motion>", self._drag_move)
        self.bind("<Escape>", lambda e: self._cancel())
        self.bind("<Return>", lambda e: self._ok())

        self.update_idletasks()
        mx, my = master.winfo_rootx(), master.winfo_rooty()
        mw, mh = master.winfo_width(), master.winfo_height()
        self.geometry(f"{W}x{H}+{mx + (mw - W) // 2}+{my + (mh - H) // 2}")
        self.transient(master)
        self.grab_set()
        if self.entry:
            self.after(50, self.entry.focus_set)
        else:
            self.after(50, self.focus_force)

    def _drag_start(self, e):
        self._dx, self._dy = e.x_root - self.winfo_x(), e.y_root - self.winfo_y()

    def _drag_move(self, e):
        self.geometry(f"+{e.x_root - self._dx}+{e.y_root - self._dy}")

    def _ok(self):
        self.result = self.var.get() if self.entry else True
        self.destroy()

    def _cancel(self):
        self.result = None if self.entry else False
        self.destroy()

    @classmethod
    def show(cls, master, title, message, kind="info", **kw):
        d = cls(master, title, message, kind, **kw)
        master.wait_window(d)
        return d.result


class Flow(ctk.CTkFrame):
    """Контейнер, который переносит элементы на новую строку, если не влезают по ширине."""

    def __init__(self, master, gap=10, vgap=10, **kw):
        super().__init__(master, fg_color="transparent", **kw)
        self.items = []
        self.gap, self.vgap = gap, vgap
        self._job = None
        self.bind("<Configure>", lambda e: self.relayout())

    def add(self, w, **grid_kw):
        self.items.append((w, grid_kw))
        return w

    def relayout(self):
        if self._job:
            self.after_cancel(self._job)
        self._job = self.after(30, self._do)

    def _do(self):
        self._job = None
        width = self.winfo_width()
        if width < 50:
            return
        for w, _ in self.items:
            w.grid_forget()
        x, row, col = 0, 0, 0
        for w, kw in self.items:
            rw = w.winfo_reqwidth()
            if x > 0 and x + rw > width:
                row += 1
                x, col = 0, 0
            w.grid(row=row, column=col, padx=(0, self.gap), pady=(0, self.vgap), sticky="w", **kw)
            x += rw + self.gap
            col += 1


# ---------- интерфейс ----------
class App(ctk.CTk):
    def __init__(self):
        self.settings = load_settings()
        self.theme = self.settings.get("theme", "dark")
        apply_theme(self.theme)
        super().__init__()
        self.title("Whispy — YouTube в текст")
        self.geometry(self.settings.get("geometry", "980x880"))
        self.minsize(720, 560)

        self.mono = "Cascadia Code" if font_exists("Cascadia Code") else "Consolas"
        self.q = queue.Queue()
        self.worker = None
        self.ai_worker = None
        self.last_path = None
        self.last_title = ""
        self.all_text = []
        self.meta_title = ""
        self._toast = None
        self._toast_job = None
        self._menu = None

        self.url_var = tk.StringVar(value="")
        self.lang_var = tk.StringVar(value=self.settings.get("lang", "Русский"))
        self.model_var = tk.StringVar(value=self.settings.get("model", "medium"))
        self.device_var = tk.StringVar(value=self.settings.get("device", "Авто"))
        self.ai_var = tk.StringVar(value=self.settings.get("ai_type", "Тезисы"))
        self.api_key = self.settings.get("api_key") or load_default_key()

        self.build()
        self.bind_all("<Control-KeyPress>", self._hotkeys, add="+")
        self.bind("<Configure>", self._on_resize)
        self.after(100, self.poll)
        self.after(50, self.dark_titlebar)
        self.after(600, self.set_icon)
        if self.settings.get("auto_update", True):
            self.after(3000, lambda: self.check_updates(silent=True))
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # ---- системные мелочи ----
    def set_icon(self):
        p = find_icon()
        if p:
            try:
                self.iconbitmap(default=p)
                self.iconbitmap(p)
            except Exception:
                pass

    def dark_titlebar(self):
        if sys.platform != "win32":
            return
        try:
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            value = ctypes.c_int(1 if self.theme == "dark" else 0)
            for attr in (20, 19):
                ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(value), ctypes.sizeof(value))
            r, g, b = hex_rgb(T["BG"])
            color = ctypes.c_int((b << 16) | (g << 8) | r)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(color), ctypes.sizeof(color))
        except Exception:
            pass

    def _hotkeys(self, e):
        if e.keysym.lower() in ("v", "c", "x", "a"):
            return None
        w = self.focus_get()
        if w is None:
            return None
        evt = {86: "<<Paste>>", 67: "<<Copy>>", 88: "<<Cut>>", 65: "<<SelectAll>>"}.get(e.keycode)
        if not evt:
            return None
        try:
            w.event_generate(evt)
        except Exception:
            pass
        return "break"

    def _on_resize(self, e):
        if e.widget is not self:
            return
        h = max(220, self.winfo_height() - 640)
        try:
            self.textbox.configure(height=h)
        except Exception:
            pass

    def persist(self):
        self.settings.update({
            "theme": self.theme, "lang": self.lang_var.get(), "model": self.model_var.get(),
            "device": self.device_var.get(), "ai_type": self.ai_var.get(), "api_key": self.api_key,
            "geometry": self.geometry(),
        })
        save_settings(self.settings)

    # ---- диалоги ----
    def info(self, title, msg):
        Dialog.show(self, title, msg, "info")

    def error(self, title, msg):
        Dialog.show(self, title, msg, "error")

    def confirm(self, title, msg, ok="Да", cancel="Нет"):
        return Dialog.show(self, title, msg, "confirm", ok=ok, cancel=cancel)

    # ---- конструкторы ----
    def card(self, parent):
        return ctk.CTkFrame(parent, fg_color=T["CARD"], corner_radius=22, border_width=1, border_color=T["BORDER"])

    def seg(self, parent, values, var):
        return ctk.CTkSegmentedButton(
            parent, values=values, variable=var, height=34, corner_radius=12, border_width=3,
            fg_color=T["FIELD"], selected_color=T["PINK"], selected_hover_color=T["PINK_HOVER"],
            unselected_color=T["FIELD"], unselected_hover_color=T["FIELD_BORDER"],
            text_color=T["TEXT"], text_color_disabled=T["MUTED"],
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"))

    def label(self, parent, text, size=11, bold=True, color=None, **kw):
        return ctk.CTkLabel(parent, text=text, text_color=color or T["MUTED"],
                            font=ctk.CTkFont(family="Segoe UI", size=size, weight="bold" if bold else "normal"), **kw)

    # ---- меню ----
    def menu_items(self, name):
        kinds = [(f"{k}  →  скопировать промпт + текст", (lambda k=k: self.copy_ai_prompt(k))) for k in AI_TYPES]
        return {
            "Файл": [
                ("Открыть последний файл", self.open_file, "после «Готово»"),
                ("Открыть папку «Транскрипты»", lambda: open_path(OUT_DIR)),
                ("Открыть папку моделей", lambda: open_path(MODELS_DIR)),
                None,
                ("Выход", self.on_close),
            ],
            "Правка": [
                ("Вставить ссылку из буфера", self.paste_url, "Ctrl+V"),
                ("Копировать весь текст", self.copy_all, "Ctrl+Shift+C"),
                ("Очистить", self.clear_all),
            ],
            "Вид": [
                ("Тёмная тема", lambda: self.set_theme("dark")),
                ("Светлая тема", lambda: self.set_theme("light")),
                None,
                ("Окно по умолчанию (980×880)", lambda: self.geometry("980x880")),
            ],
            "ИИ": kinds + [
                None,
                ("Открыть Claude в браузере", lambda: webbrowser.open("https://claude.ai/new")),
                ("API-ключ…", self.ask_api_key),
            ],
            "Помощь": [
                ("Как пользоваться", self.show_help),
                ("Проверить обновления", lambda: self.check_updates(silent=False)),
                (("✓  " if self.settings.get("auto_update", True) else "    ") + "Проверять автоматически",
                 self.toggle_auto_update),
                None,
                (f"О программе  ·  v{APP_VERSION}", self.show_about),
            ],
        }[name]

    def open_menu(self, name, btn):
        if self._menu and self._menu.winfo_exists():
            self._menu.close()
        self._menu = Dropdown(self, btn, self.menu_items(name), width=330 if name == "ИИ" else 260)

    def clear_all(self):
        if self.worker and self.worker.is_alive():
            return
        self.all_text.clear()
        self.last_path = None
        self.meta_title = ""
        self.url_var.set("")
        self.set_text("")
        self.set_placeholder()
        self.count_lbl.configure(text="")
        self.path_lbl.configure(text="")
        self.pct_lbl.configure(text="")
        self.title_lbl.configure(text="ТЕКСТ")
        self.bar.set(0)
        self.chip.set("Ожидание", "idle")
        self.status_lbl.configure(text="Вставь ссылку и нажми кнопку.", text_color=T["TEXT"])
        self.refresh_buttons()

    def set_theme(self, name):
        if name == self.theme:
            return
        self.toggle_theme()

    def show_help(self):
        self.info("Как пользоваться",
                  "1. Вставь ссылку на YouTube (кнопка «Вставить» или Ctrl+V в любой раскладке).\n"
                  "2. Нажми «Получить текст». Сначала ищутся субтитры, если их нет — распознаёт whisper.\n"
                  f"3. Файл с таймкодами сохраняется в папку «{OUT_DIR}».\n"
                  "4. В блоке «ИИ-ассистент» выбери формат и нажми «Скопировать промпт + текст», "
                  "затем вставь в Claude. Или добавь API-ключ (⚙) и жми «Сделать через API».\n\n"
                  "Модели: small — быстро, medium — баланс, large-v3 — максимум качества (нужна NVIDIA).")

    def toggle_auto_update(self):
        self.settings["auto_update"] = not self.settings.get("auto_update", True)
        self.persist()
        self.toast("Автопроверка обновлений " + ("включена" if self.settings["auto_update"] else "выключена"))

    def check_updates(self, silent=False):
        if not silent:
            self.toast("Проверяю обновления…")
        UpdateCheck(self.q, silent).start()

    def start_update(self, info):
        url = info.get("setup" if INSTALLED else "portable") or info.get("setup")
        if not url:
            self.error("Обновление", "В version.json нет ссылки на файл обновления.")
            return
        self.chip.set("Обновление", "work")
        self.wave.start()
        self.bar.set(0)
        self.status_lbl.configure(text="Скачиваю обновление…", text_color=T["TEXT"])
        UpdateDownload(url, self.q).start()

    def show_about(self):
        self.info("Whispy", f"Версия {APP_VERSION} — YouTube-ссылка → текст с таймкодами → главное через ИИ.\n"
                            "Локальная транскрипция: yt-dlp + faster-whisper. Работает офлайн после первого запуска.\n"
                            "Только для личного использования.")

    # ---- построение ----
    def build(self):
        self.configure(fg_color=T["BG"])
        for w in self.winfo_children():
            w.destroy()
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        f_body = ctk.CTkFont(family="Segoe UI", size=13)
        f_small = ctk.CTkFont(family="Segoe UI", size=11)

        # ---- панель меню ----
        bar = ctk.CTkFrame(self, fg_color=T["BG"], corner_radius=0, height=44)
        bar.grid(row=0, column=0, sticky="ew")
        bar.grid_propagate(False)
        dot = ctk.CTkLabel(bar, text="", width=10, height=10, corner_radius=5, fg_color=T["PINK"])
        dot.pack(side="left", padx=(24, 8), pady=17)
        ctk.CTkLabel(bar, text="Whispy", text_color=T["TEXT"],
                     font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold")).pack(side="left", padx=(0, 18))
        self.menu_btns = {}
        for name in ("Файл", "Правка", "Вид", "ИИ", "Помощь"):
            b = GhostButton(bar, name, lambda n=name: self.open_menu(n, self.menu_btns[n]),
                            width=74, height=30, bg=T["BG"], text_color=T["MUTED"], radius=15,
                            font=("Segoe UI", 12, "bold"))
            b._imgs["normal"] = ImageTk.PhotoImage(flat_pill(74, 30, T["BG"], T["BG"], radius=15))
            b.itemconfigure(b._img_id, image=b._imgs["normal"])
            b.pack(side="left", padx=2, pady=7)
            self.menu_btns[name] = b
        self.theme_btn = GhostButton(bar, "☀  Светлая" if self.theme == "dark" else "☾  Тёмная", self.toggle_theme,
                                     width=112, height=30, bg=T["BG"], text_color=T["MUTED"], radius=15,
                                     font=("Segoe UI", 11, "bold"))
        self.theme_btn.pack(side="right", padx=(0, 24), pady=7)

        # ---- прокручиваемое содержимое ----
        self.scroll = ctk.CTkScrollableFrame(self, fg_color=T["BG"], corner_radius=0,
                                             scrollbar_button_color=T["FIELD_BORDER"],
                                             scrollbar_button_hover_color=T["PINK"])
        self.scroll.grid(row=1, column=0, sticky="nsew")
        self.scroll.grid_columnconfigure(0, weight=1)
        root = self.scroll

        # ---- Шапка ----
        self.hero = tk.Canvas(root, height=140, bg=T["BG"], highlightthickness=0, bd=0)
        self.hero.grid(row=0, column=0, sticky="ew", padx=20, pady=(4, 6))
        self.hero.bind("<Configure>", self._draw_hero)

        # ---- Ввод ----
        card = self.card(root)
        card.grid(row=1, column=0, sticky="ew", padx=20, pady=6)
        card.grid_columnconfigure(0, weight=1)
        self.label(card, "ССЫЛКА НА ВИДЕО").grid(row=0, column=0, sticky="w", padx=22, pady=(18, 6))

        row = ctk.CTkFrame(card, fg_color="transparent")
        row.grid(row=1, column=0, sticky="ew", padx=22)
        row.grid_columnconfigure(0, weight=1)
        self.url_entry = ctk.CTkEntry(
            row, textvariable=self.url_var, height=50, corner_radius=16,
            placeholder_text="https://www.youtube.com/watch?v=…",
            fg_color=T["FIELD"], border_color=T["FIELD_BORDER"], border_width=1,
            text_color=T["TEXT"], placeholder_text_color=T["MUTED"], font=f_body)
        self.url_entry.grid(row=0, column=0, sticky="ew")
        self.url_entry.bind("<Return>", lambda e: self.start())
        self.url_entry.bind("<FocusIn>", lambda e: self.url_entry.configure(border_color=T["PINK"]))
        self.url_entry.bind("<FocusOut>", lambda e: self.url_entry.configure(border_color=T["FIELD_BORDER"]))
        self.paste_btn = GhostButton(row, "Вставить", self.paste_url, width=104, height=50, bg=T["CARD"], radius=16)
        self.paste_btn.grid(row=0, column=1, padx=(10, 0))
        self.go_btn = GradientButton(row, "Получить текст  ✦", self.start, width=200, height=50, bg=T["CARD"])
        self.go_btn.grid(row=0, column=2, padx=(4, 0))

        opts = Flow(card, gap=18, vgap=12)
        opts.grid(row=2, column=0, sticky="ew", padx=22, pady=(14, 4))
        for label, var, values in [("ЯЗЫК", self.lang_var, list(LANGS.keys())),
                                   ("МОДЕЛЬ", self.model_var, MODELS),
                                   ("УСТРОЙСТВО", self.device_var, list(DEVICES.keys()))]:
            box = ctk.CTkFrame(opts, fg_color="transparent")
            self.label(box, label).pack(anchor="w", pady=(0, 6))
            self.seg(box, values, var).pack(anchor="w")
            opts.add(box)
        self.label(card, "small — быстро · medium — баланс · large-v3 — максимум качества, нужна NVIDIA",
                   bold=False).grid(row=3, column=0, sticky="w", padx=22, pady=(0, 18))

        # ---- Прогресс ----
        prog = self.card(root)
        prog.grid(row=2, column=0, sticky="ew", padx=20, pady=6)
        prog.grid_columnconfigure(2, weight=1)
        self.wave = Wave(prog)
        self.wave.grid(row=0, column=0, padx=(22, 14), pady=(18, 6))
        self.chip = Chip(prog)
        self.chip.grid(row=0, column=1, padx=(0, 14), pady=(18, 6))
        self.status_lbl = ctk.CTkLabel(prog, text="Вставь ссылку и нажми кнопку.", font=f_body,
                                       text_color=T["TEXT"], anchor="w")
        self.status_lbl.grid(row=0, column=2, sticky="ew", pady=(18, 6))
        self.pct_lbl = ctk.CTkLabel(prog, text="", font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                                    text_color=T["PINK"], width=48, anchor="e")
        self.pct_lbl.grid(row=0, column=3, padx=(8, 8), pady=(18, 6))
        self.cancel_btn = GhostButton(prog, "Стоп", self.stop, width=80, height=30, bg=T["CARD"],
                                      text_color=T["MUTED"], accent=T["ERR"])
        self.cancel_btn.grid(row=0, column=4, padx=(0, 22), pady=(18, 6))
        self.cancel_btn.configure(state="disabled")
        self.bar = GradientProgress(prog)
        self.bar.grid(row=1, column=0, columnspan=5, sticky="ew", padx=22, pady=(6, 18))

        # ---- Текст ----
        out = self.card(root)
        out.grid(row=3, column=0, sticky="ew", padx=20, pady=6)
        out.grid_columnconfigure(0, weight=1)
        top = ctk.CTkFrame(out, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=22, pady=(16, 8))
        self.title_lbl = ctk.CTkLabel(top, text=self.meta_title or "ТЕКСТ",
                                      font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                                      text_color=T["MUTED"], anchor="w")
        self.title_lbl.pack(side="left", fill="x", expand=True)
        self.count_lbl = ctk.CTkLabel(top, text=f"{len(self.all_text)} строк" if self.all_text else "",
                                      font=f_small, text_color=T["MUTED"])
        self.count_lbl.pack(side="right")
        self.textbox = ctk.CTkTextbox(out, font=ctk.CTkFont(family=self.mono, size=12), fg_color=T["FIELD"],
                                      text_color=T["TEXT"], corner_radius=16, border_width=0, wrap="word",
                                      height=max(220, self.winfo_height() - 640),
                                      scrollbar_button_color=T["FIELD_BORDER"], scrollbar_button_hover_color=T["PINK"])
        self.textbox.grid(row=1, column=0, sticky="ew", padx=22, pady=(0, 18))
        self.textbox._textbox.configure(spacing1=3, spacing3=3, padx=10, pady=8,
                                        selectbackground=T["SELECT"], selectforeground="#FFFFFF")
        self.textbox._textbox.tag_config("ts", foreground=T["PINK"])
        self.textbox._textbox.tag_config("muted", foreground=T["MUTED"])
        self.textbox.configure(state="disabled")
        if self.all_text:
            self.textbox.configure(state="normal")
            for line in self.all_text:
                self.textbox._textbox.insert("end", line[:10], "ts")
                self.textbox._textbox.insert("end", "  " + line[11:] + "\n")
            self.textbox.configure(state="disabled")
        else:
            self.set_placeholder()

        # ---- ИИ-ассистент ----
        ai = self.card(root)
        ai.grid(row=4, column=0, sticky="ew", padx=20, pady=6)
        ai.grid_columnconfigure(0, weight=1)
        self.label(ai, "ИИ-АССИСТЕНТ  ·  ГЛАВНОЕ ИЗ ВИДЕО").grid(row=0, column=0, sticky="w", padx=22, pady=(16, 8))
        aiflow = Flow(ai, gap=10, vgap=10)
        aiflow.grid(row=1, column=0, sticky="ew", padx=22, pady=(0, 6))
        self.ai_seg = aiflow.add(self.seg(aiflow, AI_TYPES, self.ai_var))
        self.ai_copy_btn = aiflow.add(GhostButton(aiflow, "Скопировать промпт + текст", lambda: self.copy_ai_prompt(),
                                                  width=230, height=38, bg=T["CARD"]))
        self.ai_open_btn = aiflow.add(GhostButton(aiflow, "Открыть Claude",
                                                  lambda: webbrowser.open("https://claude.ai/new"),
                                                  width=140, height=38, bg=T["CARD"]))
        self.ai_api_btn = aiflow.add(GradientButton(aiflow, "Сделать через API", self.run_ai_api, width=170,
                                                    height=38, bg=T["CARD"], font=("Segoe UI", 12, "bold")))
        self.ai_key_btn = aiflow.add(GhostButton(aiflow, "⚙", self.ask_api_key, width=38, height=38, bg=T["CARD"],
                                                 text_color=T["MUTED"], radius=19))
        self.label(ai, "Без API: копируешь промпт с текстом → вставляешь в Claude. С API-ключом (⚙) результат "
                       "сохраняется в «Транскрипты» сам (платно, по тарифу Anthropic).", bold=False,
                   wraplength=820, justify="left").grid(row=2, column=0, sticky="w", padx=22, pady=(0, 16))

        # ---- Низ ----
        bottom = Flow(root, gap=10, vgap=8)
        bottom.grid(row=5, column=0, sticky="ew", padx=20, pady=(6, 18))
        self.copy_btn = bottom.add(GhostButton(bottom, "Копировать всё", self.copy_all, width=170, height=42))
        self.file_btn = bottom.add(GhostButton(bottom, "Открыть файл", self.open_file, width=150, height=42))
        self.folder_btn = bottom.add(GhostButton(bottom, "Открыть папку", lambda: open_path(OUT_DIR), width=150,
                                                 height=42))
        self.path_lbl = bottom.add(ctk.CTkLabel(bottom, text=os.path.relpath(self.last_path, BASE_DIR)
                                                if self.last_path else "", font=f_small, text_color=T["MUTED"]))
        self.refresh_buttons()
        # единый скролл колесом: над любым элементом едет страница, над длинным текстом — сам текст
        self.unbind_all("<MouseWheel>")
        self.bind_all("<MouseWheel>", self._wheel)

    def _wheel(self, e):
        try:
            w = self.winfo_containing(e.x_root, e.y_root)
        except Exception:
            return
        if w is None or w.winfo_toplevel() is not self:
            return
        try:
            tb = self.textbox._textbox
            if w is tb or str(w).startswith(str(self.textbox)):
                lo, hi = tb.yview()
                if not (lo <= 0.0 and hi >= 1.0):
                    return  # текст прокручивается сам
        except Exception:
            pass
        try:
            self.scroll._parent_canvas.yview_scroll(int(-e.delta / 40), "units")
        except Exception:
            pass

    def _draw_hero(self, e):
        w, h = max(e.width, 200), 140
        self._hero_img = ImageTk.PhotoImage(hero_image(w, h))
        self.hero.delete("all")
        self.hero.create_image(0, 0, anchor="nw", image=self._hero_img)
        self.hero.create_text(30, 48, anchor="w", text="Whispy", fill=T["HERO_TEXT"], font=("Segoe UI", 30, "bold"))
        self.hero.create_text(30, 84, anchor="w",
                              text="YouTube-ссылка → текст с таймкодами → главное через ИИ. Локально и бесплатно.",
                              fill=T["HERO_SUB"], font=("Segoe UI", 12))
        chip_text = "v2  ·  субтитры + whisper + ИИ"
        f = tkfont.Font(family="Segoe UI", size=10, weight="bold")
        cw = f.measure(chip_text) + 28
        self._chip_img = ImageTk.PhotoImage(flat_pill(cw, 26, T["HERO_CHIP"], T["HERO1"], border=T["HERO_CHIP_BORDER"]))
        self.hero.create_image(30, 102, anchor="nw", image=self._chip_img)
        self.hero.create_text(30 + cw / 2, 115, text=chip_text, fill=T["HERO_SUB"], font=("Segoe UI", 10, "bold"))

    def toggle_theme(self):
        self.theme = "light" if self.theme == "dark" else "dark"
        apply_theme(self.theme)
        self.persist()
        self.build()
        self.dark_titlebar()

    def refresh_buttons(self):
        busy = self.worker is not None and self.worker.is_alive()
        has = bool(self.all_text)
        self.copy_btn.configure(state="normal" if has else "disabled")
        self.file_btn.configure(state="normal" if self.last_path else "disabled")
        self.ai_copy_btn.configure(state="normal" if has else "disabled")
        self.ai_api_btn.configure(state="normal" if (has and self.api_key and not busy) else "disabled")
        self.go_btn.configure(state="disabled" if busy else "normal",
                              text="Работаю…" if busy else "Получить текст  ✦")

    # ---- действия ----
    def paste_url(self):
        try:
            txt = self.clipboard_get().strip()
        except Exception:
            txt = ""
        if txt:
            self.url_var.set(txt)
            self.url_entry.focus_set()
            self.url_entry.icursor("end")
            if YT_RE.search(txt):
                self.toast("Ссылка вставлена  ✓")
        else:
            self.toast("Буфер обмена пуст")

    def start(self):
        if self.worker and self.worker.is_alive():
            return
        url = self.url_var.get().strip()
        if not url:
            self.flash("Вставь ссылку на видео.", error=True)
            return
        if not YT_RE.search(url):
            self.flash("Это не похоже на ссылку YouTube.", error=True)
            return
        self.persist()
        self.all_text.clear()
        self.last_path = None
        self.meta_title = ""
        self.set_text("")
        self.count_lbl.configure(text="")
        self.path_lbl.configure(text="")
        self.pct_lbl.configure(text="0%")
        self.title_lbl.configure(text="ТЕКСТ")
        self.bar.set(0)
        self.cancel_btn.configure(state="normal")
        self.chip.set("Старт", "work")
        self.wave.start()
        self.status_lbl.configure(text="Подключаюсь к YouTube…", text_color=T["TEXT"])
        self.worker = Worker(url=url, lang=LANGS[self.lang_var.get()], model_name=self.model_var.get(),
                             device_choice=DEVICES[self.device_var.get()], q=self.q)
        self.worker.start()
        self.refresh_buttons()

    def stop(self):
        if self.worker and self.worker.is_alive():
            self.worker.cancel.set()
            self.cancel_btn.configure(state="disabled")
            self.status_lbl.configure(text="Останавливаю…")

    def finish_ui(self):
        self.cancel_btn.configure(state="disabled")
        self.wave.stop()
        self.refresh_buttons()

    def open_file(self):
        if self.last_path and os.path.exists(self.last_path):
            open_path(self.last_path)
        else:
            self.toast("Файла ещё нет — сначала получи текст")

    def copy_all(self):
        if not self.all_text:
            self.toast("Текста пока нет")
            return
        self.clipboard_clear()
        self.clipboard_append("\n".join(self.all_text))
        self.toast("Скопировано в буфер обмена  ✓")

    def ai_payload(self, kind):
        title = self.last_title or self.meta_title
        header = f"Название видео: {title}\n" if title else ""
        return f"{AI_PROMPTS[kind]}\n\n{header}\nТРАНСКРИПТ:\n" + "\n".join(self.all_text)

    def copy_ai_prompt(self, kind=None):
        if not self.all_text:
            self.toast("Сначала получи текст видео")
            return
        kind = kind or self.ai_var.get()
        self.ai_var.set(kind)
        self.persist()
        self.clipboard_clear()
        self.clipboard_append(self.ai_payload(kind))
        self.toast(f"Промпт «{kind}» + текст скопированы — вставь в Claude  ✓")

    def ask_api_key(self):
        val = Dialog.show(self, "API-ключ Anthropic",
                          "Вставь ключ вида sk-ant-… из console.anthropic.com. Пустая строка — удалить ключ. "
                          "Ключ хранится только на этом компьютере, в settings.json.",
                          "input", secret=True, default=self.api_key, ok="Сохранить")
        if val is None:
            return
        self.api_key = val.strip()
        self.persist()
        self.toast("Ключ сохранён  ✓" if self.api_key else "Ключ удалён")
        self.refresh_buttons()

    def run_ai_api(self):
        if not self.all_text or not self.api_key:
            return
        if self.ai_worker and self.ai_worker.is_alive():
            return
        self.persist()
        self.ai_api_btn.configure(state="disabled", text="Работаю…")
        self.chip.set("ИИ", "work")
        self.wave.start()
        self.ai_worker = AIWorker(self.api_key, AI_PROMPTS[self.ai_var.get()], "\n".join(self.all_text),
                                  self.last_title or self.meta_title or "video", self.ai_var.get(), self.q)
        self.ai_worker.start()

    def toast(self, text):
        if self._toast is None or not self._toast.winfo_exists():
            self._toast = ctk.CTkLabel(self, text=text, height=38, corner_radius=19, padx=20,
                                       fg_color=T["TOAST"], text_color=T["TOAST_TEXT"],
                                       font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"))
        self._toast.configure(text=text, fg_color=T["TOAST"], text_color=T["TOAST_TEXT"])
        self._toast.place(relx=0.5, rely=1.0, y=-24, anchor="s")
        self._toast.lift()
        if self._toast_job:
            self.after_cancel(self._toast_job)
        self._toast_job = self.after(2200, self._toast.place_forget)

    def flash(self, text, error=False):
        self.status_lbl.configure(text=text, text_color=(T["ERR"] if error else T["OK"]))
        if error:
            self.chip.set("Внимание", "err")

    def set_placeholder(self):
        self.textbox.configure(state="normal")
        self.textbox._textbox.insert("end", "Здесь появится текст — строка за строкой, с таймкодами.", "muted")
        self.textbox.configure(state="disabled")

    def set_text(self, text):
        self.textbox.configure(state="normal")
        self.textbox.delete("1.0", "end")
        self.textbox.insert("end", text)
        self.textbox.configure(state="disabled")

    def append_line(self, ts, text):
        self.textbox.configure(state="normal")
        self.textbox._textbox.insert("end", ts, "ts")
        self.textbox._textbox.insert("end", "  " + text + "\n")
        self.textbox.see("end")
        self.textbox.configure(state="disabled")

    # ---- события от потоков ----
    def poll(self):
        try:
            while True:
                kind, d = self.q.get_nowait()
                if kind == "status":
                    stage = d["stage"]
                    kindc = {"Готово": "ok", "Ошибка": "err", "Отменено": "idle"}.get(stage, "work")
                    self.chip.set(stage, kindc)
                    self.status_lbl.configure(text=d["text"], text_color=T["TEXT"])
                elif kind == "progress":
                    self.bar.set(d["value"])
                    self.pct_lbl.configure(text=f"{int(d['value'] * 100)}%")
                elif kind == "meta":
                    dur = fmt_ts(d["duration"])[1:-1] if d["duration"] else "—"
                    self.meta_title = d["title"]
                    self.title_lbl.configure(text=f"{d['title']}   ·   {dur}")
                elif kind == "line":
                    ts = fmt_ts(d["t"])
                    self.all_text.append(f"{ts} {d['text']}")
                    self.append_line(ts, d["text"])
                    self.count_lbl.configure(text=f"{len(self.all_text)} строк")
                elif kind == "warn":
                    self.status_lbl.configure(text=d["text"].splitlines()[0], text_color=T["ERR"])
                elif kind == "done":
                    self.last_path = d["path"]
                    self.last_title = d["title"]
                    self.path_lbl.configure(text=os.path.relpath(d["path"], BASE_DIR))
                    self.status_lbl.configure(text=f"Готово: {d['lines']} строк · {d['source']}", text_color=T["OK"])
                    self.pct_lbl.configure(text="100%")
                    self.textbox.see("1.0")
                    self.finish_ui()
                    self.toast("Файл сохранён в «Транскрипты»  ✓")
                elif kind == "cancelled":
                    self.finish_ui()
                elif kind == "error":
                    self.finish_ui()
                    self.status_lbl.configure(text=d["text"].splitlines()[0], text_color=T["ERR"])
                    self.error("Не получилось", d["text"])
                elif kind == "ai_status":
                    self.status_lbl.configure(text=d["text"], text_color=T["TEXT"])
                elif kind == "ai_done":
                    self.wave.stop()
                    self.chip.set("ИИ готово", "ok")
                    self.status_lbl.configure(text=f"Сохранено: {os.path.basename(d['path'])}", text_color=T["OK"])
                    self.ai_api_btn.configure(text="Сделать через API")
                    self.refresh_buttons()
                    self.toast("Результат ИИ сохранён и открыт  ✓")
                    try:
                        open_path(d["path"])
                    except Exception:
                        pass
                elif kind == "update_available":
                    info = d["info"]
                    notes = (info.get("notes") or "").strip()
                    msg = f"Доступна версия {info.get('version')} (у тебя {APP_VERSION})."
                    if notes:
                        msg += "\n\nЧто нового:\n" + notes[:600]
                    if self.confirm("Есть обновление", msg, ok="Обновить", cancel="Позже"):
                        self.start_update(info)
                elif kind == "update_none":
                    if not d["silent"]:
                        self.toast(f"У тебя последняя версия — {APP_VERSION}  ✓")
                elif kind == "update_error":
                    if not d["silent"]:
                        self.error("Обновление", "Не удалось проверить/скачать обновление.\n" + d["text"])
                    self.wave.stop()
                elif kind == "update_progress":
                    self.bar.set(d["value"])
                    self.pct_lbl.configure(text=f"{int(d['value'] * 100)}%")
                    self.status_lbl.configure(text=d["text"], text_color=T["TEXT"])
                elif kind == "update_ready":
                    self.wave.stop()
                    self.chip.set("Готово", "ok")
                    self.status_lbl.configure(text="Обновление скачано, перезапускаю…", text_color=T["OK"])
                    self.persist()
                    try:
                        apply_update(d["path"])
                    except Exception as e:  # noqa: BLE001
                        self.error("Обновление", "Не удалось запустить обновление.\n" + str(e)[:300])
                        continue
                    self.after(400, self._exit_for_update)
                elif kind == "ai_error":
                    self.wave.stop()
                    self.chip.set("Ошибка", "err")
                    self.status_lbl.configure(text=d["text"].splitlines()[0], text_color=T["ERR"])
                    self.ai_api_btn.configure(text="Сделать через API")
                    self.refresh_buttons()
                    self.error("ИИ-ассистент", d["text"])
        except queue.Empty:
            pass
        self.after(100, self.poll)

    def _exit_for_update(self):
        if self.worker and self.worker.is_alive():
            self.worker.cancel.set()
        shutil.rmtree(TEMP_DIR, ignore_errors=True)
        self.destroy()

    def on_close(self):
        if self.worker and self.worker.is_alive():
            if not self.confirm("Закрыть Whispy?", "Обработка ещё идёт. Если закрыть сейчас, текст не сохранится.",
                                ok="Закрыть", cancel="Остаться"):
                return
            self.worker.cancel.set()
        self.persist()
        shutil.rmtree(TEMP_DIR, ignore_errors=True)
        self.destroy()


if __name__ == "__main__":
    if sys.platform == "win32":
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    ctk.set_default_color_theme("blue")
    app = App()
    app.mainloop()
