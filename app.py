# -*- coding: utf-8 -*-
"""
Whispy — YouTube-ссылка в текст с таймкодами, спикерами и ИИ-выжимкой.
Сначала берём готовые субтитры YouTube, если их нет — качаем аудио (yt-dlp)
и распознаём через faster-whisper. Спикеры — sherpa-onnx (CAM++ эмбеддинги + кластеризация).
Всё локально; ИИ-форматы — через буфер обмена в Claude или по API.
"""

import os
import re
import sys
import json
import glob
import math
import time
import queue
import shutil
import ctypes
import zipfile
import datetime
import threading
import subprocess
import webbrowser
import urllib.error
import urllib.request
import tkinter as tk
from tkinter import font as tkfont

APP_VERSION = "2.3.6"
UPDATE_URL = "https://raw.githubusercontent.com/alegawhats-del/Whispy/main/version.json"
GITHUB_URL = "https://github.com/alegawhats-del/Whispy"

# ---------- пути ----------
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RES_DIR = getattr(sys, "_MEIPASS", BASE_DIR)

INSTALLED = os.path.exists(os.path.join(BASE_DIR, "installed.flag"))
if INSTALLED:
    DATA_DIR = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "Whispy")
    _docs = os.path.join(os.path.expanduser("~"), "Documents")
    OUT_DIR = os.path.join(_docs if os.path.isdir(_docs) else DATA_DIR, "Whispy")
else:
    DATA_DIR = BASE_DIR
    OUT_DIR = os.path.join(BASE_DIR, "Транскрипты")
MODELS_DIR = os.path.join(DATA_DIR, "models")
SPEAKER_DIR = os.path.join(MODELS_DIR, "speaker")
CUDA_DIR = os.path.join(DATA_DIR, "cuda")
TEMP_DIR = os.path.join(DATA_DIR, "temp")
UPDATES_DIR = os.path.join(DATA_DIR, "updates")
SETTINGS_PATH = os.path.join(DATA_DIR, "settings.json")
for _d in (OUT_DIR, MODELS_DIR, SPEAKER_DIR, TEMP_DIR, UPDATES_DIR):
    os.makedirs(_d, exist_ok=True)

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")


def _register_dll_dirs():
    dirs = []
    if os.path.isdir(CUDA_DIR):
        dirs.append(CUDA_DIR)
    try:
        import site
        roots = list(site.getsitepackages()) + [site.getusersitepackages()]
    except Exception:
        roots = []
    roots += [RES_DIR, os.path.join(BASE_DIR, "_internal")]
    for root in roots:
        dirs += glob.glob(os.path.join(root, "nvidia", "*", "bin"))
    for d in dirs:
        try:
            os.add_dll_directory(d)
        except Exception:
            pass
        os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")


if sys.platform == "win32":
    _register_dll_dirs()

import customtkinter as ctk  # noqa: E402
from PIL import Image, ImageDraw, ImageFilter, ImageTk  # noqa: E402


def _load_fonts():
    """Подключаем фирменный шрифт Manrope (папка fonts) только для этого процесса — без установки в систему."""
    for root in (BASE_DIR, RES_DIR, os.path.join(BASE_DIR, "_internal")):
        d = os.path.join(root, "fonts")
        if not os.path.isdir(d):
            continue
        ok = False
        for f in glob.glob(os.path.join(d, "*.ttf")):
            try:
                if sys.platform == "win32" and ctypes.windll.gdi32.AddFontResourceExW(f, 0x10, 0) > 0:
                    ok = True
            except Exception:
                pass
        if ok:
            return "Manrope", d
    return "Segoe UI", None


UI_FONT, FONT_DIR = _load_fonts()

# ---------- темы ----------
THEMES = {
    "dark": dict(
        BG="#0E0913", CARD="#18111F", BORDER="#2A1E35", FIELD="#221829", FIELD_BORDER="#3A2A47",
        TEXT="#F5EEF9", MUTED="#8C7E98", PINK="#FF5FB4", VIOLET="#8B5CF6", PINK_HOVER="#FF79C2",
        PINK_SOFT="#2E1A33", OK="#4ADE9A", OK_SOFT="#13291F", ERR="#FF6B7A", ERR_SOFT="#321820",
        GREY_SOFT="#1E1726", HERO1="#1B0F2B", HERO2="#0E0913", HERO_TEXT="#FFFFFF", HERO_SUB="#CFC3DB",
        HERO_CHIP="#2A1A3A", HERO_CHIP_BORDER="#4A3460", TOAST="#2A1A3A", TOAST_TEXT="#FFFFFF",
        BLOB_ALPHA=150, GRID_ALPHA=5, SELECT="#8B5CF6",
        SPK=["#FF5FB4", "#8B5CF6", "#4ADE9A", "#FFB454", "#5FC8FF", "#FF7A5F"],
    ),
    "light": dict(
        BG="#F6F2FA", CARD="#FFFFFF", BORDER="#EADFF2", FIELD="#F4EEF9", FIELD_BORDER="#DCCDE8",
        TEXT="#2A1E33", MUTED="#8A7D96", PINK="#E8449F", VIOLET="#7C4DFF", PINK_HOVER="#F25CB0",
        PINK_SOFT="#FBE6F2", OK="#1FA86B", OK_SOFT="#E3F6EC", ERR="#E24A5C", ERR_SOFT="#FDE6EA",
        GREY_SOFT="#ECE6F1", HERO1="#F4E6FB", HERO2="#E3D4F7", HERO_TEXT="#2A1E33", HERO_SUB="#5E4F70",
        HERO_CHIP="#FBF5FE", HERO_CHIP_BORDER="#D9C6EC", TOAST="#2A1E33", TOAST_TEXT="#FFFFFF",
        BLOB_ALPHA=190, GRID_ALPHA=16, SELECT="#C7B6F5",
        SPK=["#E8449F", "#7C4DFF", "#1FA86B", "#E08A1E", "#1E8FD6", "#E0553B"],
    ),
}
T = dict(THEMES["dark"])
KEY_COLOR = "#010203"


def apply_theme(name):
    T.clear()
    T.update(THEMES.get(name, THEMES["dark"]))
    ctk.set_appearance_mode("dark" if name == "dark" else "light")


def GRAD():
    return (T["PINK"], T["VIOLET"])


LANGS = {"Русский": "ru", "Українська": "uk", "English": "en", "Авто": "auto"}
MODELS = ["small", "medium", "large-v3"]
DEVICES = {"Авто": "auto", "NVIDIA": "gpu", "CPU": "cpu"}
SPEED = {"Быстро": 1, "Точно": 5}
SPEAKERS = {"Выкл": -1, "Авто": 0, "2": 2, "3": 3, "4": 4}
AI_TYPES = ["Тезисы", "Таблица", "Блок-схема", "Презентация", "Инфографика"]
MODEL_SIZE_GB = {"small": 0.6, "medium": 1.8, "large-v3": 3.3}
SPK_MODEL_URL = ("https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/"
                 "3dspeaker_speech_campplus_sv_zh_en_16k-common_advanced.onnx")
SPK_MODEL_PATH = os.path.join(SPEAKER_DIR, "campplus.onnx")

YT_RE = re.compile(r"(https?://)?(www\.|m\.|music\.)?(youtube\.com|youtu\.be)/", re.I)

# ---------- ИИ: промпты и HTML-оболочка ----------
AI_FRAGMENT_RULES = (
    "Верни ТОЛЬКО HTML-фрагмент для вставки внутрь <main> (без <html>, <head>, <body>, без markdown-обёрток). "
    "Разрешённые элементы и классы: <h1>, <h2>, <p>, <ul>/<ol>/<li>, <table>, <blockquote>, "
    "<div class=\"grid\"> с карточками <div class=\"card\"> (внутри <h3> и <p>), "
    "<span class=\"ts\">[чч:мм:сс]</span> для таймкодов, <span class=\"tag\">метка</span>, "
    "<div class=\"kpi\"><b>число</b><span>подпись</span></div> для крупных цифр, "
    "<div class=\"callout\">важный вывод</div>. Пиши по-русски, без воды, сохраняй смысл автора."
)

AI_PROMPTS = {
    "Тезисы": (
        "Ниже транскрипт видео с таймкодами. Сделай выжимку главного: <h1> — название, <p class=\"lead\"> — одна фраза о чём видео; "
        "затем <div class=\"grid\"> из 7–12 карточек .card, в каждой <h3> тезис, <p> суть и <span class=\"ts\"> таймкод; "
        "затем <h2>Цитаты</h2> с 3–5 <blockquote> (коротко, с таймкодом); затем <h2>Что делать</h2> — <ol> практических выводов. "
        + AI_FRAGMENT_RULES
    ),
    "Таблица": (
        "Ниже транскрипт видео с таймкодами. Построй <h1> и <table> главного: колонки Раздел | Тезис | Почему важно | Таймкод "
        "(таймкод оберни в <span class=\"ts\">). 10–20 строк, сгруппируй по темам в порядке видео. "
        "После таблицы — <div class=\"callout\"> с тремя выводами одной фразой каждый. " + AI_FRAGMENT_RULES
    ),
    "Блок-схема": (
        "Ниже транскрипт видео с таймкодами. Построй блок-схему главной логики/процесса, о котором рассказывает автор. "
        "Сначала <h1> и <p class=\"lead\"> (какая логика прослеживается), затем диаграмму Mermaid внутри <pre class=\"mermaid\">…</pre> "
        "(flowchart TD; узлы короткие, до 6 слов; стрелки с подписями там, где есть условия; таймкоды в подписях узлов в формате чч:мм:сс; "
        "НЕ используй круглые скобки и кавычки внутри текста узлов), затем <h2>Пояснения</h2> — <ul> по узлам с таймкодами. "
        + AI_FRAGMENT_RULES
    ),
    "Презентация": (
        "Ниже транскрипт видео с таймкодами. Сделай презентацию на 10–12 слайдов. Каждый слайд — <section class=\"slide\"> "
        "с <h2> заголовком и 3 короткими <li> в <ul>, в конце слайда <span class=\"ts\"> таймкод источника. "
        "Слайд 1 — титульный (<h1> + <p class=\"lead\">), слайд 2 — структура, предпоследний — выводы, последний — вопросы для обсуждения. "
        "Внутри слайдов можно использовать .kpi и .tag. " + AI_FRAGMENT_RULES
    ),
    "Инфографика": (
        "Ниже транскрипт видео с таймкодами. Сделай инфографику главного одной страницей: <h1> и <p class=\"lead\">; "
        "ряд из 2–4 <div class=\"kpi\"> с цифрами/фактами из видео (если есть); <div class=\"grid\"> из 5–8 карточек .card, "
        "в каждой эмодзи-иконка в <h3>, 1–2 строки сути в <p>, <span class=\"ts\"> таймкод; внизу <div class=\"callout\"> с 3 выводами. "
        + AI_FRAGMENT_RULES
    ),
}

HTML_SHELL = """<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>
{font_face}
:root{{--bg:#0E0913;--card:#18111F;--border:#2A1E35;--field:#221829;--text:#F5EEF9;--muted:#8C7E98;--pink:#FF5FB4;--violet:#8B5CF6;--ok:#4ADE9A}}
*{{box-sizing:border-box}}html,body{{margin:0;background:var(--bg);color:var(--text);font:16px/1.55 Manrope,"Segoe UI",system-ui,sans-serif}}
body::before{{content:"";position:fixed;inset:-20% -10% auto -10%;height:60vh;background:radial-gradient(60% 60% at 70% 30%,rgba(255,95,180,.28),transparent 70%),radial-gradient(50% 60% at 90% 70%,rgba(139,92,246,.30),transparent 70%);filter:blur(40px);z-index:-1;pointer-events:none}}
main{{max-width:1040px;margin:0 auto;padding:56px 24px 80px}}
header.top{{display:flex;justify-content:space-between;align-items:center;gap:16px;margin-bottom:28px;color:var(--muted);font-size:13px}}
header.top .brand{{display:flex;align-items:center;gap:10px;font-weight:700;color:var(--text)}}
header.top .dot{{width:10px;height:10px;border-radius:50%;background:linear-gradient(135deg,var(--pink),var(--violet))}}
h1{{font-size:clamp(28px,4vw,44px);line-height:1.1;margin:0 0 12px;background:linear-gradient(90deg,#fff,#CFC3DB);-webkit-background-clip:text;background-clip:text;color:transparent}}
h2{{font-size:22px;margin:40px 0 14px;padding-left:14px;border-left:3px solid var(--pink)}}
h3{{margin:0 0 8px;font-size:17px}}
p.lead{{color:var(--muted);font-size:18px;margin:0 0 24px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:14px}}
.card{{background:var(--card);border:1px solid var(--border);border-radius:18px;padding:18px 18px 14px;transition:transform 160ms cubic-bezier(.23,1,.32,1),border-color 160ms;animation:in .35s cubic-bezier(.23,1,.32,1) both}}
.card:hover{{transform:translateY(-2px);border-color:#4A3460}}
.card p{{margin:0 0 8px;color:#D8CDE3}}
.grid .card:nth-child(1){{animation-delay:0ms}}.grid .card:nth-child(2){{animation-delay:40ms}}.grid .card:nth-child(3){{animation-delay:80ms}}.grid .card:nth-child(4){{animation-delay:120ms}}.grid .card:nth-child(5){{animation-delay:160ms}}.grid .card:nth-child(6){{animation-delay:200ms}}.grid .card:nth-child(n+7){{animation-delay:240ms}}
@keyframes in{{from{{opacity:0;transform:translateY(8px)}}to{{opacity:1;transform:none}}}}
.ts{{display:inline-block;font:600 12px/1 "Cascadia Code",Consolas,monospace;color:var(--pink);background:rgba(255,95,180,.12);border-radius:999px;padding:5px 9px;margin-top:4px}}
.tag{{display:inline-block;font-size:12px;font-weight:700;color:#CFC3DB;background:var(--field);border:1px solid var(--border);border-radius:999px;padding:3px 10px;margin:2px 4px 2px 0}}
.kpi{{display:inline-flex;flex-direction:column;gap:2px;min-width:160px;margin:0 12px 12px 0;padding:16px 20px;border-radius:18px;background:linear-gradient(135deg,rgba(255,95,180,.18),rgba(139,92,246,.18));border:1px solid var(--border)}}
.kpi b{{font-size:30px;line-height:1;background:linear-gradient(90deg,var(--pink),var(--violet));-webkit-background-clip:text;background-clip:text;color:transparent}}
.kpi span{{color:var(--muted);font-size:13px}}
.callout{{margin-top:28px;padding:18px 22px;border-radius:18px;background:linear-gradient(135deg,rgba(255,95,180,.14),rgba(139,92,246,.14));border:1px solid #4A3460}}
blockquote{{margin:12px 0;padding:14px 18px;border-left:3px solid var(--violet);background:var(--card);border-radius:0 14px 14px 0;color:#D8CDE3}}
table{{width:100%;border-collapse:separate;border-spacing:0;background:var(--card);border:1px solid var(--border);border-radius:18px;overflow:hidden;margin:12px 0}}
th{{text-align:left;font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);background:var(--field);padding:12px 14px}}
td{{padding:12px 14px;border-top:1px solid var(--border);vertical-align:top}}tr:hover td{{background:rgba(255,255,255,.02)}}
pre.mermaid{{background:var(--card);border:1px solid var(--border);border-radius:18px;padding:20px;overflow:auto}}
ol,ul{{padding-left:22px}}li{{margin:6px 0}}
footer{{margin-top:48px;color:var(--muted);font-size:12px;border-top:1px solid var(--border);padding-top:16px}}
.toolbar{{position:fixed;right:18px;bottom:18px;display:flex;gap:8px}}
.toolbar button{{border:1px solid var(--border);background:var(--card);color:var(--text);border-radius:999px;padding:10px 14px;font:600 13px Manrope,"Segoe UI";cursor:pointer;transition:transform 160ms cubic-bezier(.23,1,.32,1)}}
.toolbar button:active{{transform:scale(.97)}}
{extra_css}
@media print{{body::before,.toolbar{{display:none}}main{{padding:0}}.card{{break-inside:avoid}}}}
</style>{extra_head}</head>
<body><main>
<header class="top"><div class="brand"><span class="dot"></span>Whispy · {kind}</div><div>{title} · {date}</div></header>
{content}
<footer>Сделано в Whispy из видео: <a style="color:var(--muted)" href="{url}">{url}</a></footer>
</main>
<div class="toolbar"><button onclick="window.print()">Сохранить в PDF</button></div>
{extra_js}
</body></html>"""

SLIDES_CSS = """
.slide{display:none;min-height:70vh;padding:44px 48px;border-radius:24px;background:var(--card);border:1px solid var(--border);animation:in .3s cubic-bezier(.23,1,.32,1) both}
.slide.active{display:block}.slide h2{border:0;padding:0;margin:0 0 20px;font-size:34px}.slide li{font-size:20px;margin:12px 0}
.slide h1{font-size:52px}.nav{display:flex;gap:10px;align-items:center;justify-content:center;margin-top:18px;color:var(--muted)}
.nav button{border:1px solid var(--border);background:var(--card);color:var(--text);border-radius:999px;padding:10px 18px;font:600 14px Manrope,"Segoe UI";cursor:pointer;transition:transform 160ms cubic-bezier(.23,1,.32,1)}
.nav button:active{transform:scale(.97)}
.progress{height:4px;background:var(--field);border-radius:4px;overflow:hidden;margin-top:14px}.progress i{display:block;height:100%;background:linear-gradient(90deg,var(--pink),var(--violet));transition:width .25s cubic-bezier(.23,1,.32,1)}
@media print{.slide{display:block;page-break-after:always;min-height:auto}.nav,.progress{display:none}}
"""
SLIDES_JS = """<script>
(function(){var s=[].slice.call(document.querySelectorAll('.slide'));if(!s.length)return;var i=0;
var nav=document.createElement('div');nav.className='nav';nav.innerHTML='<button id="p">←</button><span id="c"></span><button id="n">→</button>';
var pr=document.createElement('div');pr.className='progress';pr.innerHTML='<i></i>';
var main=document.querySelector('main');main.insertBefore(pr,main.querySelector('footer'));main.insertBefore(nav,main.querySelector('footer'));
function show(k){i=(k+s.length)%s.length;s.forEach(function(e,j){e.classList.toggle('active',j===i)});document.getElementById('c').textContent=(i+1)+' / '+s.length;pr.firstChild.style.width=((i+1)/s.length*100)+'%'}
document.getElementById('p').onclick=function(){show(i-1)};document.getElementById('n').onclick=function(){show(i+1)};
document.addEventListener('keydown',function(e){if(e.key==='ArrowRight'||e.key===' ')show(i+1);if(e.key==='ArrowLeft')show(i-1)});show(0)})();
</script>"""
MERMAID_HEAD = """<script src="https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.min.js"></script>
<script>mermaid.initialize({startOnLoad:true,theme:'dark',themeVariables:{primaryColor:'#2E1A33',primaryTextColor:'#F5EEF9',primaryBorderColor:'#FF5FB4',lineColor:'#8B5CF6',secondaryColor:'#221829',tertiaryColor:'#18111F',fontFamily:'Manrope, Segoe UI'}});</script>"""


def html_escape(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def wrap_ai_html(kind, fragment, title, url):
    frag = fragment.strip()
    m = re.search(r"<body[^>]*>(.*)</body>", frag, re.S | re.I)
    if m:
        frag = m.group(1)
    frag = re.sub(r"^```(?:html)?\s*|\s*```$", "", frag.strip(), flags=re.S)
    extra_css = SLIDES_CSS if kind == "Презентация" else ""
    extra_js = SLIDES_JS if kind == "Презентация" else ""
    extra_head = MERMAID_HEAD if kind == "Блок-схема" else ""
    font_face = ""
    if FONT_DIR:
        base = "file:///" + os.path.abspath(FONT_DIR).replace("\\", "/")
        font_face = (f"@font-face{{font-family:Manrope;font-weight:400;src:url('{base}/Manrope-Regular.ttf')}}"
                     f"@font-face{{font-family:Manrope;font-weight:700;src:url('{base}/Manrope-Bold.ttf')}}")
    return HTML_SHELL.format(title=html_escape(title), kind=kind, date=datetime.date.today().strftime("%d.%m.%Y"),
                             content=frag, url=html_escape(url), extra_css=extra_css, extra_head=extra_head, extra_js=extra_js,
                             font_face=font_face)


# ---------- утилиты ----------
def fmt_ts(seconds):
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"[{h:02d}:{m:02d}:{s:02d}]"


def safe_name(name, limit=80):
    name = re.sub(r'[\\/:*?"<>|\r\n\t]+', " ", name).strip()
    name = re.sub(r"\s+", " ", name)
    return (name[:limit] or "video").strip()


def human_error(exc):
    text = str(exc)
    low = text.lower()
    if "private video" in low:
        return "Видео приватное — к нему нет доступа."
    if "video unavailable" in low or "this video is not available" in low:
        return "Видео недоступно (удалено, заблокировано или ссылка битая)."
    if "sign in" in low and "age" in low:
        return "Видео с возрастным ограничением — YouTube требует вход в аккаунт."
    if "sign in to confirm you" in low or "bot" in low:
        return "YouTube попросил подтвердить, что вы не бот. Попробуйте позже или обновите программу."
    if "unsupported url" in low or "is not a valid url" in low:
        return "Это не похоже на ссылку YouTube."
    if "premieres" in low or "live event" in low or "is live" in low:
        return "Это прямой эфир или премьера — дождитесь окончания трансляции."
    if "errno 28" in low or "no space left" in low or "not enough space" in low or "недостаточно места" in low:
        return "Закончилось место на диске. Освободи место (или выбери модель поменьше) и запусти снова."
    if "urlopen" in low or "getaddrinfo" in low or "timed out" in low or "connection" in low:
        return "Нет связи. Проверь интернет."
    if "cuda" in low or "cudnn" in low or "cublas" in low:
        return "Проблема с видеокартой/CUDA: " + text[:200] + "\nПереключи устройство на CPU или поставь поддержку NVIDIA (меню Помощь)."
    return text[:400]


def open_path(path):
    if sys.platform == "win32":
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def open_html(path, title="Whispy"):
    """Открывает HTML в окне программы (встроенный Edge WebView2). Если встроенного окна нет — в браузере."""
    try:
        import importlib
        importlib.import_module("webview")
        args = [sys.executable] + ([] if getattr(sys, "frozen", False) else [os.path.abspath(__file__)])
        subprocess.Popen(args + ["--viewer", os.path.abspath(path), title], close_fds=True)
    except Exception:
        webbrowser.open("file:///" + os.path.abspath(path).replace("\\", "/"))


def run_viewer(path, title):
    import webview
    url = "file:///" + os.path.abspath(path).replace("\\", "/")
    webview.create_window(title, url, width=1120, height=820, min_size=(760, 520), background_color="#0E0913", text_select=True)
    webview.start()


def reveal_in_folder(path):
    if sys.platform == "win32" and path and os.path.exists(path):
        subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
    else:
        open_path(os.path.dirname(path) if path else OUT_DIR)


def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def mix(c1, c2, t):
    a, b = hex_rgb(c1), hex_rgb(c2)
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def rgb_hex(rgb):
    return "#%02x%02x%02x" % rgb


def font_exists(name):
    try:
        return name in tkfont.families()
    except Exception:
        return False


def load_settings():
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_settings(d):
    try:
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def resource(*parts):
    for root in (BASE_DIR, RES_DIR, os.path.join(BASE_DIR, "_internal")):
        p = os.path.join(root, *parts)
        if os.path.exists(p):
            return p
    return None


_LOGO = {}


def logo_image(size):
    """Логотип из whispy.png (рядом с exe / в сборке), ужатый до size. Кэшируется."""
    if size in _LOGO:
        return _LOGO[size]
    p = resource("whispy.png")
    img = None
    if p:
        try:
            img = Image.open(p).convert("RGBA").resize((size, size), Image.LANCZOS)
        except Exception:
            img = None
    _LOGO[size] = img
    return img


def model_cached(name):
    return os.path.isdir(os.path.join(MODELS_DIR, f"models--Systran--faster-whisper-{name}", "snapshots"))


def dir_size(path):
    total = 0
    for root, _, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def check_disk(model_name, audio_gb=0.3):
    free = shutil.disk_usage(MODELS_DIR).free / 1e9
    need = audio_gb + (0 if model_cached(model_name) else MODEL_SIZE_GB.get(model_name, 2.0))
    if free < need:
        raise RuntimeError(f"Мало места на диске: нужно около {need:.1f} ГБ, свободно {free:.1f} ГБ. "
                           f"Освободи место или выбери модель поменьше.")


def has_nvidia():
    if sys.platform != "win32":
        return False
    return bool(shutil.which("nvidia-smi")) or os.path.exists(r"C:\Windows\System32\nvidia-smi.exe")


def cuda_ready():
    try:
        import ctranslate2
        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


def vtuple(v):
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3]) or (0,)


def http_get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": f"Whispy/{APP_VERSION}"})
    return urllib.request.urlopen(req, timeout=timeout)


def download_file(url, path, progress=None, cancel=None):
    tmp = path + ".part"
    with http_get(url, 60) as resp, open(tmp, "wb") as f:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while True:
            if cancel is not None and cancel.is_set():
                raise RuntimeError("cancelled")
            chunk = resp.read(1024 * 512)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if progress:
                progress(done, total)
    os.replace(tmp, path)


def ease_out(t):
    return 1 - (1 - t) ** 3


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
        ImageDraw.Draw(g).rounded_rectangle([pad, pad, pad + w, pad + h], radius=radius, fill=hex_rgb(c1) + (120,))
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
    canvas.paste(Image.new("RGB", (w, h), hex_rgb(color)), (0, 0), rounded_mask(w, h, radius))
    if border:
        s = 4
        b = Image.new("L", (w * s, h * s), 0)
        ImageDraw.Draw(b).rounded_rectangle([0, 0, w * s - 1, h * s - 1], radius=radius * s, outline=255, width=s)
        b = b.resize((w, h), Image.LANCZOS)
        canvas.paste(Image.new("RGB", (w, h), hex_rgb(border)), (0, 0), b)
    return canvas


def hero_image(w, h, chip_text, chip_font):
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
    # чип версии — прямо на градиенте, без «белых углов»
    cw = chip_font.measure(chip_text) + 28
    s = 4
    chip = Image.new("RGBA", (cw * s, 26 * s), (0, 0, 0, 0))
    ImageDraw.Draw(chip).rounded_rectangle([0, 0, cw * s - 1, 26 * s - 1], radius=13 * s,
                                           fill=hex_rgb(T["HERO_CHIP"]) + (235,), outline=hex_rgb(T["HERO_CHIP_BORDER"]) + (255,), width=s)
    chip = chip.resize((cw, 26), Image.LANCZOS)
    img.paste(chip, (30, 102), chip)
    logo = logo_image(64)
    if logo is not None:
        img.paste(logo, (30, 22), logo)
    out = Image.new("RGB", (w, h), hex_rgb(T["BG"]))
    out.paste(img, (0, 0), rounded_mask(w, h, 22))
    return out, cw


def card_image(w, h, radius=18, fill=None, border=None, bg=None):
    bg = bg or KEY_COLOR
    img = flat_pill(w, h, fill or T["CARD"], fill or T["CARD"], radius=radius, border=border or T["BORDER"])
    mask = rounded_mask(w, h, radius).point(lambda p: 255 if p >= 128 else 0)
    out = Image.new("RGB", (w, h), hex_rgb(bg))
    out.paste(img, (0, 0), mask)
    return out


# ---------- иконки (рисуются, не шрифтовые) ----------
_ICON_CACHE = {}


def icon_image(name, size, color, bg=None):
    """Монолинейная иконка size×size цветом color на фоне bg (или прозрачная). Сглаживание ×4."""
    key = (name, size, color, bg)
    if key in _ICON_CACHE:
        return _ICON_CACHE[key]
    S = size * 4
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = hex_rgb(color) + (255,)
    w = max(2, S // 11)  # толщина линии
    u = S / 24.0         # единица сетки 24×24

    def line(pts):
        d.line([(x * u, y * u) for x, y in pts], fill=c, width=w, joint="curve")
        for x, y in (pts[0], pts[-1]):
            d.ellipse([x * u - w / 2, y * u - w / 2, x * u + w / 2, y * u + w / 2], fill=c)

    if name == "folder":
        d.rounded_rectangle([3 * u, 6 * u, 21 * u, 19 * u], radius=2.2 * u, outline=c, width=w)
        d.rounded_rectangle([3 * u, 4 * u, 11 * u, 8 * u], radius=1.5 * u, fill=c)
        d.rounded_rectangle([3 * u + w, 7 * u, 21 * u - w, 9.5 * u], radius=0, fill=c)
    elif name == "sun":
        d.ellipse([8 * u, 8 * u, 16 * u, 16 * u], outline=c, width=w)
        for k in range(8):
            a = math.radians(k * 45)
            x1, y1 = 12 + 6.2 * math.cos(a), 12 + 6.2 * math.sin(a)
            x2, y2 = 12 + 9 * math.cos(a), 12 + 9 * math.sin(a)
            line([(x1, y1), (x2, y2)])
    elif name == "moon":
        d.ellipse([4 * u, 4 * u, 20 * u, 20 * u], fill=c)
        d.ellipse([8.5 * u, 1.5 * u, 23 * u, 16 * u], fill=(0, 0, 0, 0))
    elif name == "gear":
        pts = []
        for k in range(24):
            r = 10 if (k // 3) % 2 == 0 else 7.6
            a = math.radians(k * 15)
            pts.append((12 * u + r * u * math.cos(a), 12 * u + r * u * math.sin(a)))
        d.polygon(pts, fill=c)
        d.ellipse([8.6 * u, 8.6 * u, 15.4 * u, 15.4 * u], fill=(0, 0, 0, 0))
        d.ellipse([8.6 * u, 8.6 * u, 15.4 * u, 15.4 * u], outline=c, width=w)
        d.ellipse([9.6 * u + w, 9.6 * u + w, 14.4 * u - w, 14.4 * u - w], fill=(0, 0, 0, 0))
    elif name == "close":
        line([(7, 7), (17, 17)])
        line([(17, 7), (7, 17)])
    elif name == "sparkle":
        d.polygon([(12 * u, 2 * u), (14.2 * u, 9.8 * u), (22 * u, 12 * u), (14.2 * u, 14.2 * u),
                   (12 * u, 22 * u), (9.8 * u, 14.2 * u), (2 * u, 12 * u), (9.8 * u, 9.8 * u)], fill=c)
    elif name == "check":
        line([(5, 12.5), (10, 17.5), (19, 7)])
    elif name == "alert":
        d.rounded_rectangle([10.6 * u, 4 * u, 13.4 * u, 14.5 * u], radius=1.4 * u, fill=c)
        d.ellipse([10.4 * u, 17 * u, 13.6 * u, 20.2 * u], fill=c)
    elif name == "question":
        d.arc([7 * u, 4 * u, 17 * u, 14 * u], 200, 90, fill=c, width=w)
        line([(12, 13.5), (12, 16)])
        d.ellipse([10.4 * u, 18 * u, 13.6 * u, 21.2 * u], fill=c)
    elif name == "doc":
        d.rounded_rectangle([5 * u, 3 * u, 19 * u, 21 * u], radius=2 * u, outline=c, width=w)
        for y in (9, 13, 17):
            line([(8.5, y), (15.5, y)])
    elif name == "play":
        d.polygon([(8 * u, 5 * u), (19 * u, 12 * u), (8 * u, 19 * u)], fill=c)
    elif name == "refresh":
        d.arc([5 * u, 5 * u, 19 * u, 19 * u], 300, 240, fill=c, width=w)
        d.polygon([(19.5 * u, 4 * u), (20.5 * u, 10.5 * u), (14 * u, 9.5 * u)], fill=c)
    elif name == "key":
        d.ellipse([3 * u, 8 * u, 11 * u, 16 * u], outline=c, width=w)
        line([(11, 12), (21, 12)])
        line([(17, 12), (17, 16)])
        line([(20, 12), (20, 15)])
    elif name == "pin":
        d.ellipse([5 * u, 3 * u, 19 * u, 17 * u], outline=c, width=w)
        line([(12, 17), (12, 22)])
    out = img.resize((size, size), Image.LANCZOS)
    if bg is not None:
        base = Image.new("RGB", (size, size), hex_rgb(bg))
        base.paste(out, (0, 0), out)
        out = base
    _ICON_CACHE[key] = out
    return out


ANIM = {"active": True}


# ---------- кастомные виджеты ----------
class GradientButton(tk.Canvas):
    """Градиентная кнопка: ховер 120 мс (ease-out), сжатие до 97 % при нажатии."""
    GLOW = 10
    FRAMES = 6

    def __init__(self, master, text, command, width=200, height=50, bg=None, font=None, icon=None, **kw):
        bg = bg or T["CARD"]
        g = self.GLOW
        super().__init__(master, width=width + g * 2, height=height + g * 2, bg=bg, highlightthickness=0, bd=0, cursor="hand2", **kw)
        self.command = command
        self._icon_name = icon
        self._state = "normal"
        self._font = font or (UI_FONT, 13, "bold")
        c1, c2 = GRAD()
        self._frames = [ImageTk.PhotoImage(pill(width, height, c1, c2, bg, brightness=1.0 + 0.12 * i / (self.FRAMES - 1), glow=g))
                        for i in range(self.FRAMES)]
        pw, ph = int(width * 0.97), int(height * 0.97)
        pressed = Image.new("RGB", (width + g * 2, height + g * 2), hex_rgb(bg))
        pressed.paste(pill(pw, ph, c1, c2, bg, glow=g), ((width - pw) // 2, (height - ph) // 2))
        self._pressed = ImageTk.PhotoImage(pressed)
        self._disabled = ImageTk.PhotoImage(flat_pill(width + g * 2, height + g * 2, T["FIELD"], bg, radius=(height + g * 2) // 2))
        self._frame = 0
        self._target = 0
        self._job = None
        self._img_id = self.create_image(0, 0, anchor="nw", image=self._frames[0])
        cx, cy = (width + g * 2) / 2, (height + g * 2) / 2
        self._icon_id = None
        if icon:
            tf = tkfont.Font(family=self._font[0], size=self._font[1], weight=self._font[2] if len(self._font) > 2 else "normal")
            tw = tf.measure(text)
            isz = 16
            x0 = cx - (tw + isz + 8) / 2
            self._icon_img = ImageTk.PhotoImage(icon_image(icon, isz, "#FFFFFF"))
            self._icon_id = self.create_image(x0, cy, anchor="w", image=self._icon_img)
            self._txt_id = self.create_text(x0 + isz + 8, cy, anchor="w", text=text, fill="#FFFFFF", font=self._font)
        else:
            self._txt_id = self.create_text(cx, cy, text=text, fill="#FFFFFF", font=self._font)
        self.bind("<Enter>", lambda e: self._go(self.FRAMES - 1))
        self.bind("<Leave>", lambda e: self._go(0))
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<ButtonRelease-1>", self._release)

    def _go(self, target):
        if self._state != "normal":
            return
        self._target = target
        if self._job is None:
            self._step()

    def _step(self):
        self._job = None
        if self._frame == self._target or not self.winfo_exists():
            return
        self._frame += 1 if self._target > self._frame else -1
        self.itemconfigure(self._img_id, image=self._frames[self._frame])
        self._job = self.after(20, self._step)

    def _press(self, _):
        if self._state == "normal":
            self.itemconfigure(self._img_id, image=self._pressed)

    def _release(self, e):
        if self._state != "normal":
            return
        self.itemconfigure(self._img_id, image=self._frames[self._frame])
        if 0 <= e.x <= self.winfo_width() and 0 <= e.y <= self.winfo_height() and self.command:
            self.after(10, self.command)

    def configure(self, **kw):
        if "text" in kw:
            self.itemconfigure(self._txt_id, text=kw.pop("text"))
        if "state" in kw:
            self._state = kw.pop("state")
            if self._state == "disabled":
                self.itemconfigure(self._img_id, image=self._disabled)
                self.itemconfigure(self._txt_id, fill=T["MUTED"])
                if self._icon_id:
                    self.itemconfigure(self._icon_id, state="hidden")
                super().configure(cursor="arrow")
            else:
                self._frame = 0
                self.itemconfigure(self._img_id, image=self._frames[0])
                self.itemconfigure(self._txt_id, fill="#FFFFFF")
                if self._icon_id:
                    self.itemconfigure(self._icon_id, state="normal")
                super().configure(cursor="hand2")
        if kw:
            super().configure(**kw)


class GhostButton(tk.Canvas):
    """Кнопка с тонкой рамкой; ховер — заливка и акцентный текст, нажатие — лёгкое сжатие."""

    def __init__(self, master, text, command, width=170, height=42, bg=None, font=None, text_color=None,
                 accent=None, radius=14, fill=None, icon=None, icon_size=16, **kw):
        bg = bg or T["BG"]
        fill = fill or bg
        text_color = text_color or T["TEXT"]
        accent = accent or T["PINK"]
        super().__init__(master, width=width, height=height, bg=bg, highlightthickness=0, bd=0, cursor="hand2", **kw)
        self.command = command
        self._state = "normal"
        self._tc, self._accent = text_color, accent
        self._font = font or (UI_FONT, 12, "bold")
        self._icon_name, self._icon_size = icon, icon_size
        pw, ph = int(width * 0.97), int(height * 0.97)
        pressed = Image.new("RGB", (width, height), hex_rgb(bg))
        pressed.paste(flat_pill(pw, ph, T["PINK_SOFT"], bg, radius=radius, border=accent), ((width - pw) // 2, (height - ph) // 2))
        self._imgs = {
            "normal": ImageTk.PhotoImage(flat_pill(width, height, fill, bg, radius=radius, border=T["FIELD_BORDER"])),
            "hover": ImageTk.PhotoImage(flat_pill(width, height, T["PINK_SOFT"], bg, radius=radius, border=accent)),
            "pressed": ImageTk.PhotoImage(pressed),
            "disabled": ImageTk.PhotoImage(flat_pill(width, height, fill, bg, radius=radius, border=T["BORDER"])),
        }
        self._img_id = self.create_image(0, 0, anchor="nw", image=self._imgs["normal"])
        self._icon_imgs = {}
        self._icon_id = None
        if icon:
            tf = tkfont.Font(family=self._font[0], size=self._font[1], weight=self._font[2] if len(self._font) > 2 else "normal")
            tw = tf.measure(text) if text else 0
            gap = 7 if text else 0
            total = icon_size + gap + tw
            x0 = (width - total) / 2
            for k, col in (("normal", text_color), ("hover", accent), ("disabled", T["BORDER"])):
                self._icon_imgs[k] = ImageTk.PhotoImage(icon_image(icon, icon_size, col))
            self._icon_id = self.create_image(x0, height / 2, anchor="w", image=self._icon_imgs["normal"])
            self._txt_id = self.create_text(x0 + icon_size + gap, height / 2, anchor="w", text=text, fill=text_color, font=self._font)
        else:
            self._txt_id = self.create_text(width / 2, height / 2, text=text, fill=text_color, font=self._font)
        self._hovering = False
        self.bind("<Enter>", lambda e: self._hover(True))
        self.bind("<Leave>", lambda e: self._hover(False))
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<ButtonRelease-1>", self._release)

    def _press(self, _):
        if self._state == "normal":
            self.itemconfigure(self._img_id, image=self._imgs["pressed"])

    def _hover(self, on):
        self._hovering = on
        if self._state != "normal":
            return
        self.itemconfigure(self._img_id, image=self._imgs["hover" if on else "normal"])
        self.itemconfigure(self._txt_id, fill=self._accent if on else self._tc)
        if self._icon_id:
            self.itemconfigure(self._icon_id, image=self._icon_imgs["hover" if on else "normal"])

    def _release(self, e):
        if self._state != "normal":
            return
        self._hover(self._hovering)
        if 0 <= e.x <= self.winfo_width() and 0 <= e.y <= self.winfo_height() and self.command:
            self.after(10, self.command)

    def set_plain(self):
        w, h = int(self["width"]), int(self["height"])
        self._imgs["normal"] = ImageTk.PhotoImage(flat_pill(w, h, self["bg"], self["bg"], radius=h // 2))
        self.itemconfigure(self._img_id, image=self._imgs["normal"])

    def configure(self, **kw):
        if "text" in kw:
            self.itemconfigure(self._txt_id, text=kw.pop("text"))
        if "state" in kw:
            self._state = kw.pop("state")
            disabled = self._state == "disabled"
            self.itemconfigure(self._img_id, image=self._imgs["disabled" if disabled else "normal"])
            self.itemconfigure(self._txt_id, fill=T["BORDER"] if disabled else self._tc)
            if self._icon_id:
                self.itemconfigure(self._icon_id, image=self._icon_imgs["disabled" if disabled else "normal"])
            super().configure(cursor="arrow" if disabled else "hand2")
        if kw:
            super().configure(**kw)


class GradientProgress(tk.Canvas):
    """Градиентный прогресс с анимацией к цели и бегущим бликом, когда прогресс неизвестен."""

    def __init__(self, master, height=10, bg=None, on_value=None, **kw):
        bg = bg or T["CARD"]
        super().__init__(master, height=height + 8, bg=bg, highlightthickness=0, bd=0, **kw)
        self.h, self.bgc = height, bg
        self.value = 0.0
        self.target = 0.0
        self.indeterminate = False
        self._phase = 0.0
        self._bar_w = 100
        self._track = self._fill = None
        self._on_value = on_value
        self._track_id = self.create_image(0, 4, anchor="nw")
        self._fill_id = self.create_image(0, 4, anchor="nw")
        self.bind("<Configure>", self._resize)
        self.after(40, self._tick)

    def _resize(self, e):
        self._bar_w = max(e.width, 20)
        self._track = ImageTk.PhotoImage(flat_pill(self._bar_w, self.h, T["FIELD"], self.bgc))
        self.itemconfigure(self._track_id, image=self._track)
        self._draw()

    def set(self, v):
        self.target = max(0.0, min(1.0, v))
        self.indeterminate = False

    def set_indeterminate(self, on=True):
        self.indeterminate = on
        if not on:
            self._draw()

    def _tick(self):
        if not self.winfo_exists():
            return
        if self.indeterminate:
            self._phase = (self._phase + 0.02) % 1.0
            self._draw_shimmer()
        elif abs(self.target - self.value) > 0.002:
            self.value += (self.target - self.value) * 0.22
            self._draw()
            if self._on_value:
                self._on_value(self.value)
        elif self.value != self.target:
            self.value = self.target
            self._draw()
            if self._on_value:
                self._on_value(self.value)
        self.after(40, self._tick)

    def _draw(self):
        fw = int(self._bar_w * self.value)
        self.coords(self._fill_id, 0, 4)
        if fw < self.h:
            self._fill = None
            self.itemconfigure(self._fill_id, image="")
            return
        c1, c2 = GRAD()
        self._fill = ImageTk.PhotoImage(pill(fw, self.h, c1, c2, self.bgc))
        self.itemconfigure(self._fill_id, image=self._fill)

    def _draw_shimmer(self):
        seg = max(self.h * 2, int(self._bar_w * 0.22))
        x = int((self._bar_w + seg) * self._phase) - seg
        c1, c2 = GRAD()
        self._fill = ImageTk.PhotoImage(pill(seg, self.h, c1, c2, self.bgc))
        self.itemconfigure(self._fill_id, image=self._fill)
        self.coords(self._fill_id, x, 4)


class Wave(tk.Canvas):
    def __init__(self, master, bars=5, bg=None, bw=4, gap=4, hmax=22, **kw):
        bg = bg or T["CARD"]
        self.bw, self.gap, self.hmax = bw, gap, hmax
        w = bars * bw + (bars - 1) * gap
        super().__init__(master, width=w, height=hmax + 4, bg=bg, highlightthickness=0, bd=0, **kw)
        self.active = False
        self.phase = 0.0
        self.items = []
        c1, c2 = GRAD()
        for i in range(bars):
            col = rgb_hex(mix(c1, c2, i / max(1, bars - 1)))
            x = i * (bw + gap)
            self.items.append(self.create_rectangle(x, 0, x + bw, 0, fill=col, outline=""))
        self._draw(0.15)
        self.after(60, self._tick)

    def _draw(self, amp=None):
        cy = (self.hmax + 4) / 2
        for i, item in enumerate(self.items):
            a = (0.35 + 0.65 * (0.5 + 0.5 * math.sin(self.phase + i * 0.9))) if self.active else (amp if amp is not None else 0.15)
            h = self.hmax * a
            x = i * (self.bw + self.gap)
            self.coords(item, x, cy - h / 2, x + self.bw, cy + h / 2)

    def _tick(self):
        if not self.winfo_exists():
            return
        if self.active and ANIM["active"]:
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
        super().__init__(master, text=text, height=28, corner_radius=14, padx=14, fg_color=T["PINK_SOFT"], text_color=T["PINK"],
                         font=ctk.CTkFont(family=UI_FONT, size=11, weight="bold"), **kw)

    def set(self, text, kind="work"):
        colors = {"work": (T["PINK_SOFT"], T["PINK"]), "ok": (T["OK_SOFT"], T["OK"]),
                  "err": (T["ERR_SOFT"], T["ERR"]), "idle": (T["GREY_SOFT"], T["MUTED"])}[kind]
        self.configure(text=text, fg_color=colors[0], text_color=colors[1])


class Flow(ctk.CTkFrame):
    """Контейнер с переносом элементов на новую строку по ширине."""

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


# ---------- всплывающие окна ----------
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


class Panel(tk.Toplevel):
    """Окно без системной рамки в стиле приложения: поверх главного, двигается мышью,
    поднимается, когда главное окно получает фокус (не теряется за другими окнами)."""

    def __init__(self, master, width, height, radius=22, modal=True):
        super().__init__(master)
        self.app = master
        self.result = None
        self.modal = modal
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.attributes("-alpha", 0.0)
        _transparent(self)
        self.W, self.H = width, height
        self._img = ImageTk.PhotoImage(card_image(width, height, radius=radius, border=T["FIELD_BORDER"]))
        self.cv = tk.Canvas(self, width=width, height=height, bg=self.cget("bg"), highlightthickness=0, bd=0)
        self.cv.pack()
        self.cv.create_image(0, 0, anchor="nw", image=self._img)
        inset = 14
        self.body = ctk.CTkFrame(self, fg_color=T["CARD"], corner_radius=0)
        self.cv.create_window(inset, inset, anchor="nw", window=self.body, width=width - inset * 2, height=height - inset * 2)
        self.cv.bind("<ButtonPress-1>", self._drag_start)
        self.cv.bind("<B1-Motion>", self._drag_move)
        self.bind("<Escape>", lambda e: self.close(None))
        try:
            self.wm_transient(master)
        except Exception:
            pass
        self._focus_bind = master.bind("<FocusIn>", self._lift, add="+")

    def show(self):
        self.update_idletasks()
        mx, my = self.app.winfo_rootx(), self.app.winfo_rooty()
        mw, mh = self.app.winfo_width(), self.app.winfo_height()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        x = min(max(0, mx + (mw - self.W) // 2), max(0, sw - self.W))
        y = min(max(0, my + (mh - self.H) // 2), max(0, sh - self.H))
        self.geometry(f"{self.W}x{self.H}+{x}+{y}")
        self.deiconify()
        self.lift()
        self._fade(0)
        self.after(60, self._arm)
        self.after(1500, self._watchdog)
        return self

    def _fade(self, i):
        if not self.winfo_exists():
            return
        if i <= 8:
            self.attributes("-alpha", ease_out(i / 8))
            self.after(16, lambda: self._fade(i + 1))

    def _arm(self):
        if not self.winfo_exists():
            return
        if self.winfo_viewable():
            if self.modal:
                try:
                    self.grab_set()
                except Exception:
                    pass
            self.focus_force()
            self.on_shown()
        else:
            self.lift()
            self.after(60, self._arm)

    def on_shown(self):
        pass

    def _watchdog(self):
        if self.winfo_exists() and not self.winfo_viewable():
            self.close(None)

    def _lift(self, _=None):
        if self.winfo_exists():
            self.lift()

    def _drag_start(self, e):
        self._dx, self._dy = e.x_root - self.winfo_x(), e.y_root - self.winfo_y()

    def _drag_move(self, e):
        self.geometry(f"+{e.x_root - self._dx}+{e.y_root - self._dy}")

    def close(self, result):
        self.result = result
        try:
            self.app.unbind("<FocusIn>", self._focus_bind)
        except Exception:
            pass
        try:
            self.destroy()
        except Exception:
            pass

    def header(self, glyph, color, soft, title):
        top = ctk.CTkFrame(self.body, fg_color="transparent")
        top.pack(fill="x", padx=14, pady=(10, 4))
        self._badge = ImageTk.PhotoImage(icon_image(glyph, 20, color, bg=soft))
        ctk.CTkLabel(top, text="", image=self._badge, width=40, height=40, corner_radius=20, fg_color=soft).pack(side="left")
        ctk.CTkLabel(top, text=title, text_color=T["TEXT"], anchor="w",
                     font=ctk.CTkFont(family=UI_FONT, size=16, weight="bold")).pack(side="left", padx=12, fill="x", expand=True)
        GhostButton(top, "", lambda: self.close(None), width=34, height=34, bg=T["CARD"], text_color=T["MUTED"],
                    accent=T["ERR"], radius=17, icon="close", icon_size=14).pack(side="right")
        return top


class Dialog(Panel):
    """info / error / confirm / input."""

    def __init__(self, master, title, message, kind="info", secret=False, default="", ok="Ок", cancel="Отмена"):
        W = 520
        wrap = W - 28 * 2 - 28
        f = tkfont.Font(family=UI_FONT, size=12)
        lines = sum(max(1, math.ceil(f.measure(p) / wrap)) if p else 1 for p in message.split("\n"))
        H = 150 + lines * 21 + (64 if kind == "input" else 0)
        super().__init__(master, W, H)
        glyph, col, soft = {"info": ("check", T["OK"], T["OK_SOFT"]), "error": ("alert", T["ERR"], T["ERR_SOFT"]),
                            "confirm": ("question", T["PINK"], T["PINK_SOFT"]), "input": ("sparkle", T["VIOLET"], T["PINK_SOFT"])}[kind]
        self.header(glyph, col, soft, title)
        ctk.CTkLabel(self.body, text=message, text_color=T["MUTED"], anchor="w", justify="left", wraplength=wrap,
                     font=ctk.CTkFont(family=UI_FONT, size=12)).pack(fill="x", padx=28, pady=(6, 4))
        self.entry = None
        if kind == "input":
            self.var = tk.StringVar(value=default)
            self.entry = ctk.CTkEntry(self.body, textvariable=self.var, height=42, corner_radius=14, show="•" if secret else "",
                                      fg_color=T["FIELD"], border_color=T["FIELD_BORDER"], border_width=1, text_color=T["TEXT"],
                                      font=ctk.CTkFont(family=UI_FONT, size=13))
            self.entry.pack(fill="x", padx=28, pady=(8, 4))
            self.entry.bind("<FocusIn>", lambda e: self.entry.configure(border_color=T["PINK"]))
            self.entry.bind("<FocusOut>", lambda e: self.entry.configure(border_color=T["FIELD_BORDER"]))
        btns = ctk.CTkFrame(self.body, fg_color="transparent")
        btns.pack(fill="x", padx=18, pady=(10, 8), side="bottom")
        GradientButton(btns, ok, self._ok, width=130, height=40, bg=T["CARD"], font=(UI_FONT, 12, "bold")).pack(side="right")
        if kind in ("confirm", "input"):
            GhostButton(btns, cancel, lambda: self.close(None if self.entry else False), width=110, height=40, bg=T["CARD"]).pack(side="right", padx=(0, 6))
        self.bind("<Return>", lambda e: self._ok())

    def on_shown(self):
        if self.entry:
            self.entry.focus_set()

    def _ok(self):
        self.close(self.var.get() if self.entry else True)

    @classmethod
    def show_modal(cls, master, title, message, kind="info", **kw):
        d = cls(master, title, message, kind, **kw).show()
        master.wait_window(d)
        return d.result


class Dropdown(tk.Toplevel):
    def __init__(self, master, anchor, items, width=260):
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
        f = ctk.CTkFont(family=UI_FONT, size=12)
        fs = ctk.CTkFont(family=UI_FONT, size=10)
        for it in items:
            if it is None:
                sep = ctk.CTkFrame(self, fg_color=T["BORDER"], bg_color=T["CARD"], height=1, corner_radius=0)
                cv.create_window(pad + 8, y + 4, anchor="nw", window=sep, width=width - pad * 2 - 16)
                y += 9
                continue
            label, cmd, shortcut = (tuple(it) + (None,))[:3]
            row = ctk.CTkFrame(self, fg_color=T["CARD"], bg_color=T["CARD"], corner_radius=10, height=32)
            lb = ctk.CTkLabel(row, text=label, font=f, text_color=T["TEXT"], anchor="w")
            lb.place(x=12, y=0, relheight=1)
            if shortcut:
                ctk.CTkLabel(row, text=shortcut, font=fs, text_color=T["MUTED"], anchor="e").place(relx=1.0, x=-12, y=0, relheight=1, anchor="ne")
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
        self.deiconify()
        self.lift()
        self.bind("<Escape>", lambda e: self.close())
        self.after(10, self.focus_force)
        self.bind("<FocusOut>", lambda e: self.after(80, self._check_focus))

    def _check_focus(self):
        try:
            fw = self.focus_displayof()
            if fw is None or not str(fw).startswith(str(self)):
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


class FilesPanel(Panel):
    """Мои файлы: всё, что сохранила программа — открыть, показать в папке, скопировать."""

    def __init__(self, master):
        super().__init__(master, 780, 580, modal=False)
        self.header("folder", T["VIOLET"], T["PINK_SOFT"], "Мои файлы")
        ctk.CTkLabel(self.body, text=OUT_DIR, text_color=T["MUTED"], anchor="w", font=ctk.CTkFont(family=UI_FONT, size=11)).pack(fill="x", padx=28, pady=(0, 6))
        tools = ctk.CTkFrame(self.body, fg_color="transparent")
        tools.pack(fill="x", padx=14, pady=(0, 6))
        GhostButton(tools, "Открыть папку", lambda: open_path(OUT_DIR), width=150, height=34, bg=T["CARD"], icon="folder", icon_size=15).pack(side="left")
        GhostButton(tools, "Обновить", self.refresh, width=118, height=34, bg=T["CARD"], icon="refresh", icon_size=15).pack(side="left", padx=8)
        self.count = ctk.CTkLabel(tools, text="", text_color=T["MUTED"], font=ctk.CTkFont(family=UI_FONT, size=11))
        self.count.pack(side="right")
        self.list = ctk.CTkScrollableFrame(self.body, fg_color=T["FIELD"], corner_radius=14,
                                           scrollbar_button_color=T["FIELD_BORDER"], scrollbar_button_hover_color=T["PINK"])
        self.list.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        self.list.grid_columnconfigure(0, weight=1)
        self.refresh()

    def refresh(self):
        for w in self.list.winfo_children():
            w.destroy()
        self._row_icons = []
        files = []
        for ext in ("*.txt", "*.html", "*.md"):
            files += glob.glob(os.path.join(OUT_DIR, ext))
        files.sort(key=os.path.getmtime, reverse=True)
        self.count.configure(text=f"{len(files)} файлов")
        kinds = {".txt": ("doc", "Транскрипт"), ".html": ("sparkle", "ИИ · страница"), ".md": ("sparkle", "ИИ · Markdown")}
        f_name = ctk.CTkFont(family=UI_FONT, size=12, weight="bold")
        f_meta = ctk.CTkFont(family=UI_FONT, size=10)
        if not files:
            ctk.CTkLabel(self.list, text="Пока пусто — получи первый текст.", text_color=T["MUTED"]).grid(row=0, column=0, padx=16, pady=16)
        for i, p in enumerate(files[:200]):
            ext = os.path.splitext(p)[1].lower()
            glyph, kind = kinds.get(ext, ("•", ext))
            st = os.stat(p)
            row = ctk.CTkFrame(self.list, fg_color=T["CARD"], corner_radius=12)
            row.grid(row=i, column=0, sticky="ew", padx=8, pady=4)
            row.grid_columnconfigure(1, weight=1)
            im = ImageTk.PhotoImage(icon_image(glyph, 16, T["PINK"], bg=T["PINK_SOFT"]))
            self._row_icons.append(im)
            ctk.CTkLabel(row, text="", image=im, width=34, height=34, corner_radius=17, fg_color=T["PINK_SOFT"]).grid(row=0, column=0, rowspan=2, padx=(10, 10), pady=8)
            ctk.CTkLabel(row, text=os.path.basename(p), anchor="w", text_color=T["TEXT"], font=f_name).grid(row=0, column=1, sticky="ew", pady=(8, 0))
            meta = f"{kind}  ·  {st.st_size / 1024:.0f} КБ  ·  {datetime.datetime.fromtimestamp(st.st_mtime):%d.%m.%Y %H:%M}"
            ctk.CTkLabel(row, text=meta, anchor="w", text_color=T["MUTED"], font=f_meta).grid(row=1, column=1, sticky="ew", pady=(0, 8))
            b = ctk.CTkFrame(row, fg_color="transparent")
            b.grid(row=0, column=2, rowspan=2, padx=(6, 10))
            GhostButton(b, "Открыть", lambda p=p, e=ext: open_html(p, os.path.basename(p)) if e == ".html" else open_path(p),
                        width=84, height=30, bg=T["CARD"], font=(UI_FONT, 11, "bold")).pack(side="left", padx=2)
            GhostButton(b, "В папке", lambda p=p: reveal_in_folder(p), width=78, height=30, bg=T["CARD"], font=(UI_FONT, 11, "bold")).pack(side="left", padx=2)
            if ext == ".txt":
                GhostButton(b, "Копировать", lambda p=p: self._copy(p), width=96, height=30, bg=T["CARD"], font=(UI_FONT, 11, "bold")).pack(side="left", padx=2)

    def _copy(self, p):
        try:
            with open(p, encoding="utf-8") as f:
                txt = f.read()
            self.clipboard_clear()
            self.clipboard_append(txt)
            self.app.toast("Текст скопирован  ✓")
        except Exception as e:  # noqa: BLE001
            self.app.toast("Не удалось прочитать файл: " + str(e)[:60])


# ---------- фоновые задачи ----------
class Cancelled(Exception):
    pass


class Worker(threading.Thread):
    def __init__(self, app, url, lang, model_name, device_choice, beam, speakers, gen):
        super().__init__(daemon=True)
        self.app = app
        self.q = app.q
        self.url, self.lang, self.model_name, self.device_choice = url, lang, model_name, device_choice
        self.beam, self.speakers, self.gen = beam, speakers, gen
        self.cancel = threading.Event()
        self.lines = []  # [start, end, text, (speaker)]

    def emit(self, kind, **data):
        data["gen"] = self.gen
        self.q.put((kind, data))

    def status(self, stage, text):
        self.emit("status", stage=stage, text=text)

    def progress(self, value):
        self.emit("progress", value=max(0.0, min(1.0, value)))

    def line(self, start, end, text):
        self.lines.append([start, end, text])
        self.emit("line", t=start, text=text)

    def check_cancel(self):
        if self.cancel.is_set():
            raise Cancelled()

    def run(self):
        audio_path = None
        try:
            import yt_dlp
            self.status("Проверка", "Получаю информацию о видео…")
            self.progress(0.02)
            with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "noplaylist": True, "skip_download": True, "socket_timeout": 30}) as ydl:
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

            if (not got) or self.speakers >= 0:
                if not got:
                    check_disk(self.model_name)
                self.status("Скачивание", "Скачиваю аудио…")
                audio_path = self.download_audio(info)
                self.check_cancel()
            if not got:
                self.wait_prefetch()
                self.transcribe(audio_path, duration)
                source = f"faster-whisper {self.model_name}"
            if not self.lines:
                raise RuntimeError("Не удалось получить ни строки текста.")
            if self.speakers >= 0 and audio_path:
                try:
                    self.diarize(audio_path)
                except Cancelled:
                    raise
                except Exception as e:  # noqa: BLE001
                    self.emit("warn", text="Спикеры не определились: " + human_error(e))

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

    def wait_prefetch(self):
        pf = self.app.prefetch
        if pf and pf.is_alive() and pf.model_name == self.model_name:
            self.status("Модель", f"Жду, пока докачается модель {self.model_name}…")
            while pf.is_alive():
                self.check_cancel()
                time.sleep(0.3)

    def try_subtitles(self, info):
        manual = info.get("subtitles") or {}
        auto = info.get("automatic_captions") or {}
        lang = self.lang
        candidates = []

        def pick(pool, want):
            keys = list(pool.keys())
            return [want] if want in keys else [k for k in keys if k.split("-")[0] == want]

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
            track = next((t for t in (pool.get(key) or []) if t.get("ext") == "json3"), None)
            if not track or not track.get("url"):
                continue
            try:
                self.status("Субтитры", f"Загружаю дорожку «{key}»…")
                req = urllib.request.Request(track["url"], headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=30) as resp:
                    raw = resp.read().decode("utf-8", "replace")
                segs = self.parse_json3(raw)
                if len(segs) < 3:
                    continue
                self.progress(0.3)
                total = len(segs)
                for i, (s, e, text) in enumerate(segs, 1):
                    self.check_cancel()
                    self.line(s, e, text)
                    if i % 25 == 0:
                        self.progress(0.3 + 0.6 * i / total)
                return True
            except Cancelled:
                raise
            except Exception:
                continue
        return False

    @staticmethod
    def parse_json3(raw):
        data = json.loads(raw)
        out = []
        last = None
        for ev in data.get("events", []):
            segs = ev.get("segs")
            if not segs:
                continue
            text = re.sub(r"\s+", " ", "".join(s.get("utf8", "") for s in segs)).strip()
            if not text or text == last:
                continue
            last = text
            s = ev.get("tStartMs", 0) / 1000.0
            d = ev.get("dDurationMs", 0) / 1000.0
            out.append((s, s + (d if d > 0 else 3.0), text))
        return out

    def download_audio(self, info):
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
                    self.progress(0.1 + 0.15 * done / total)
                    self.status("Скачивание", f"Аудио: {done / 1048576:.1f} / {total / 1048576:.1f} МБ")
            elif d.get("status") == "finished":
                self.progress(0.25)

        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "noplaylist": True,
                               "format": "bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best", "outtmpl": outtmpl,
                               "progress_hooks": [hook], "socket_timeout": 30, "retries": 5}) as ydl:
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
        if self.device_choice == "cpu":
            return "cpu", "int8"
        if cuda_ready():
            return "cuda", "float16"
        if self.device_choice == "gpu":
            raise RuntimeError("Видеокарта NVIDIA не готова: поставь поддержку через меню Помощь → «Установить поддержку NVIDIA».")
        return "cpu", "int8"

    def transcribe(self, audio_path, duration):
        from faster_whisper import WhisperModel
        device, compute = self.pick_device()
        dev_name = "NVIDIA" if device == "cuda" else "CPU"
        self.status("Модель", f"Загружаю {self.model_name} ({dev_name})…" + ("" if model_cached(self.model_name) else " первый раз скачивается"))
        self.emit("indeterminate", on=True)
        threads = max(1, (os.cpu_count() or 4))
        try:
            model = WhisperModel(self.model_name, device=device, compute_type=compute, download_root=MODELS_DIR, cpu_threads=threads)
        except Exception as e:  # noqa: BLE001
            if device == "cuda":
                self.emit("warn", text="Видеокарта не завелась, переключаюсь на CPU.\n" + str(e)[:200])
                device, compute = "cpu", "int8"
                model = WhisperModel(self.model_name, device=device, compute_type=compute, download_root=MODELS_DIR, cpu_threads=threads)
            else:
                raise
        self.emit("indeterminate", on=False)
        self.check_cancel()
        self.status("Распознавание", "Слушаю аудио…")
        language = None if self.lang == "auto" else self.lang
        kwargs = dict(language=language, beam_size=self.beam, vad_filter=True,
                      vad_parameters={"min_silence_duration_ms": 500}, condition_on_previous_text=False)
        try:
            from faster_whisper import BatchedInferencePipeline
            batched = BatchedInferencePipeline(model=model)
            segments, info = batched.transcribe(audio_path, batch_size=16 if device == "cuda" else 8, **kwargs)
        except Exception:
            segments, info = model.transcribe(audio_path, **kwargs)
        total = float(getattr(info, "duration", 0) or duration or 0)
        t0 = time.time()
        for seg in segments:
            self.check_cancel()
            text = seg.text.strip()
            if not text:
                continue
            self.line(seg.start, seg.end, text)
            if total:
                frac = seg.end / total
                self.progress(0.3 + 0.6 * frac)
                el = time.time() - t0
                eta = (el / frac - el) if frac > 0.02 else 0
                eta_s = f"  ·  осталось ~{max(1, int(eta // 60))} мин" if eta > 45 else ""
                self.status("Распознавание", f"{fmt_ts(seg.end)[1:-1]} из {fmt_ts(total)[1:-1]}{eta_s}")

    # — спикеры —
    def diarize(self, audio_path):
        import numpy as np
        self.status("Спикеры", "Определяю, кто говорит…")
        self.progress(0.9)
        if not os.path.exists(SPK_MODEL_PATH):
            self.status("Спикеры", "Скачиваю модель голосов (28 МБ)…")
            download_file(SPK_MODEL_URL, SPK_MODEL_PATH,
                          progress=lambda d, t: t and self.status("Спикеры", f"Модель голосов: {d / 1048576:.0f} / {t / 1048576:.0f} МБ"),
                          cancel=self.cancel)
        import sherpa_onnx
        from faster_whisper.audio import decode_audio
        wav = decode_audio(audio_path, sampling_rate=16000)
        cfg = sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=SPK_MODEL_PATH, num_threads=max(1, (os.cpu_count() or 4) // 2), provider="cpu")
        ext = sherpa_onnx.SpeakerEmbeddingExtractor(cfg)
        embs = []
        n = len(self.lines)
        for i, ln in enumerate(self.lines):
            s, e = ln[0], ln[1]
            if i % 20 == 0:
                self.check_cancel()
                self.progress(0.9 + 0.08 * i / max(1, n))
            chunk = wav[int(s * 16000):int(max(e, s + 1.0) * 16000)]
            if len(chunk) < 8000:
                embs.append(None)
                continue
            st = ext.create_stream()
            st.accept_waveform(16000, chunk)
            st.input_finished()
            v = np.asarray(ext.compute(st), dtype=np.float32)
            v /= (np.linalg.norm(v) + 1e-9)
            embs.append(v)
        labels = self.cluster(embs, self.speakers)
        if labels:
            for i, lab in enumerate(labels):
                self.lines[i].append(lab)
            self.emit("speakers", labels=labels)

    @staticmethod
    def cluster(embs, k=0, threshold=0.52):
        import numpy as np
        idx = [i for i, e in enumerate(embs) if e is not None]
        if len(idx) < 2:
            return None
        X = np.stack([embs[i] for i in idx])
        clusters = [[i] for i in range(len(X))]
        cents = [X[i].copy() for i in range(len(X))]

        def merge_pair():
            C = np.stack(cents)
            C = C / (np.linalg.norm(C, axis=1, keepdims=True) + 1e-9)
            S = C @ C.T
            np.fill_diagonal(S, -2)
            a, b = divmod(int(S.argmax()), S.shape[1])
            return a, b, S[a, b]

        while len(clusters) > 1:
            a, b, sim = merge_pair()
            if k > 0:
                if len(clusters) <= k:
                    break
            elif sim < threshold:
                break
            clusters[a] += clusters[b]
            cents[a] = X[clusters[a]].mean(0)
            del clusters[b]
            del cents[b]
        if k == 0:
            min_size = max(2, int(0.03 * len(X)))
            while len(clusters) > 1:
                small = [i for i, c in enumerate(clusters) if len(c) < min_size]
                if not small:
                    break
                i = small[0]
                C = np.stack(cents)
                C = C / (np.linalg.norm(C, axis=1, keepdims=True) + 1e-9)
                sims = C @ C[i]
                sims[i] = -2
                j = int(sims.argmax())
                clusters[j] += clusters[i]
                cents[j] = X[clusters[j]].mean(0)
                del clusters[i]
                del cents[i]
            while len(clusters) > 6:
                a, b, _ = merge_pair()
                clusters[a] += clusters[b]
                cents[a] = X[clusters[a]].mean(0)
                del clusters[b]
                del cents[b]
        lab_of = {}
        for ci, members in enumerate(clusters):
            for m in members:
                lab_of[idx[m]] = ci
        order = {}
        labels = []
        prev = 0
        for i in range(len(embs)):
            ci = lab_of.get(i)
            if ci is None:
                labels.append(prev)
                continue
            if ci not in order:
                order[ci] = len(order) + 1
            prev = order[ci]
            labels.append(prev)
        for i in range(len(labels)):
            if labels[i] == 0:
                labels[i] = next((l for l in labels[i:] if l), 1)
        return labels

    def save(self, title, source):
        stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M")
        path = os.path.join(OUT_DIR, f"{safe_name(title)}_{stamp}.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"{title}\n{self.url}\nИсточник: {source}\nДата: {datetime.datetime.now():%d.%m.%Y %H:%M}\n")
            f.write("-" * 60 + "\n\n")
            for ln in self.lines:
                spk = f"Спикер {ln[3]}: " if len(ln) > 3 else ""
                f.write(f"{fmt_ts(ln[0])} {spk}{ln[2]}\n")
        return path


class AIWorker(threading.Thread):
    MODEL = "claude-sonnet-5-5"

    def __init__(self, api_key, kind, transcript, title, url, q):
        super().__init__(daemon=True)
        self.api_key, self.kind, self.transcript, self.title, self.url, self.q = api_key, kind, transcript, title, url, q

    def run(self):
        try:
            self.q.put(("ai_status", {"text": f"Claude делает «{self.kind}»… обычно 30–90 секунд"}))
            body = json.dumps({"model": self.MODEL, "max_tokens": 12000,
                               "messages": [{"role": "user", "content":
                                             f"{AI_PROMPTS[self.kind]}\n\nНазвание видео: {self.title}\n\nТРАНСКРИПТ:\n{self.transcript}"}]}).encode("utf-8")
            req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, method="POST",
                                         headers={"x-api-key": self.api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
            with urllib.request.urlopen(req, timeout=600) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
            if not text.strip():
                raise RuntimeError("Пустой ответ от API.")
            html = wrap_ai_html(self.kind, text, self.title, self.url)
            stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M")
            path = os.path.join(OUT_DIR, f"{safe_name(self.title)}_{self.kind}_{stamp}.html")
            with open(path, "w", encoding="utf-8") as f:
                f.write(html)
            self.q.put(("ai_done", {"path": path}))
        except urllib.error.HTTPError as e:
            try:
                msg = json.loads(e.read().decode("utf-8")).get("error", {}).get("message", str(e))
            except Exception:
                msg = str(e)
            self.q.put(("ai_error", {"text": f"API: {msg}"}))
        except Exception as e:  # noqa: BLE001
            self.q.put(("ai_error", {"text": human_error(e)}))


class ModelPrefetch(threading.Thread):
    """Фоновая загрузка модели whisper, чтобы первое видео не ждало."""

    def __init__(self, model_name, q):
        super().__init__(daemon=True)
        self.model_name, self.q = model_name, q

    def run(self):
        try:
            from faster_whisper import download_model
            expected = MODEL_SIZE_GB[self.model_name] * 1e9
            folder = os.path.join(MODELS_DIR, f"models--Systran--faster-whisper-{self.model_name}")
            stop = threading.Event()

            def watch():
                while not stop.is_set():
                    frac = min(0.99, dir_size(folder) / expected) if os.path.isdir(folder) else 0
                    self.q.put(("prefetch", {"model": self.model_name, "frac": frac}))
                    stop.wait(1.0)

            threading.Thread(target=watch, daemon=True).start()
            download_model(self.model_name, cache_dir=MODELS_DIR)
            stop.set()
            self.q.put(("prefetch_done", {"model": self.model_name}))
        except Exception as e:  # noqa: BLE001
            self.q.put(("prefetch_error", {"model": self.model_name, "text": human_error(e)}))


class GpuSetup(threading.Thread):
    """cuBLAS и cuDNN (CUDA 12) из PyPI-колёс → папка программы. Без Python/pip у пользователя."""
    PKGS = ["nvidia-cublas-cu12", "nvidia-cudnn-cu12"]

    def __init__(self, q):
        super().__init__(daemon=True)
        self.q = q
        self.cancel = threading.Event()

    def wheel_url(self, pkg):
        with http_get(f"https://pypi.org/pypi/{pkg}/json") as r:
            data = json.loads(r.read().decode("utf-8"))
        for ver in sorted(data["releases"], key=vtuple, reverse=True):
            if re.search(r"[a-zA-Z]", ver):
                continue
            for f in data["releases"][ver]:
                if f["filename"].endswith(".whl") and "win_amd64" in f["filename"] and not f.get("yanked"):
                    return f["url"], int(f.get("size") or 0), ver
        raise RuntimeError(f"Не нашёл Windows-сборку {pkg} на PyPI.")

    def run(self):
        try:
            os.makedirs(CUDA_DIR, exist_ok=True)
            for n, pkg in enumerate(self.PKGS):
                url, size, ver = self.wheel_url(pkg)
                dest = os.path.join(UPDATES_DIR, f"{pkg}.whl")
                self.q.put(("gpu_status", {"text": f"Скачиваю {pkg} {ver} ({size / 1048576:.0f} МБ)…", "frac": n / 2}))
                download_file(url, dest, progress=lambda d, t, n=n, pkg=pkg: self.q.put(
                    ("gpu_status", {"text": f"{pkg}: {d / 1048576:.0f} / {t / 1048576:.0f} МБ", "frac": n / 2 + 0.45 * (d / t if t else 0)})),
                    cancel=self.cancel)
                self.q.put(("gpu_status", {"text": f"Распаковываю {pkg}…", "frac": n / 2 + 0.47}))
                with zipfile.ZipFile(dest) as z:
                    for m in z.namelist():
                        if m.lower().endswith(".dll") and "/bin/" in m:
                            with z.open(m) as src, open(os.path.join(CUDA_DIR, os.path.basename(m)), "wb") as dst:
                                shutil.copyfileobj(src, dst)
                os.remove(dest)
            self.q.put(("gpu_done", {}))
        except Exception as e:  # noqa: BLE001
            self.q.put(("gpu_error", {"text": human_error(e)}))


class UpdateCheck(threading.Thread):
    def __init__(self, q, silent):
        super().__init__(daemon=True)
        self.q, self.silent = q, silent

    def run(self):
        try:
            with http_get(f"{UPDATE_URL}?t={int(time.time())}", 15) as resp:
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
            path = os.path.join(UPDATES_DIR, "Whispy-Setup.exe" if INSTALLED else "Whispy-new.exe")
            download_file(self.url, path, progress=lambda d, t: t and self.q.put(
                ("update_progress", {"value": d / t, "text": f"Скачиваю обновление: {d / 1048576:.0f} / {t / 1048576:.0f} МБ"})))
            if os.path.getsize(path) < 1_000_000:
                raise RuntimeError("Скачанный файл подозрительно мал — проверь ссылку в version.json.")
            self.q.put(("update_ready", {"path": path}))
        except Exception as e:  # noqa: BLE001
            self.q.put(("update_error", {"silent": False, "text": human_error(e)}))


def apply_update(path):
    if INSTALLED:
        # ждём завершения тихой установки и сами запускаем новую версию
        exe = sys.executable
        bat = os.path.join(UPDATES_DIR, "apply.bat")
        with open(bat, "w", encoding="cp866", errors="replace") as f:
            f.write("@echo off\ntimeout /t 1 >nul\n"
                    f'start /wait "" "{path}" /SILENT /CLOSEAPPLICATIONS /NORESTART\n'
                    f'start "" "{exe}"\ndel "{path}" 2>nul\ndel "%~f0"\n')
        subprocess.Popen(["cmd", "/c", bat], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return
    exe = sys.executable
    bat = os.path.join(UPDATES_DIR, "apply.bat")
    with open(bat, "w", encoding="cp866", errors="replace") as f:
        f.write("@echo off\n:loop\ntimeout /t 1 >nul\n" f'del "{exe}" 2>nul\nif exist "{exe}" goto loop\n'
                f'move /y "{path}" "{exe}"\nstart "" "{exe}"\ndel "%~f0"\n')
    subprocess.Popen(["cmd", "/c", bat], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


# ---------- интерфейс ----------
class App(ctk.CTk):
    def __init__(self):
        self.settings = load_settings()
        self.theme = self.settings.get("theme", "dark")
        apply_theme(self.theme)
        super().__init__()
        self.title("Whispy — YouTube в текст")
        self.geometry(self.settings.get("geometry", "1000x920"))
        self.minsize(760, 600)
        self.attributes("-alpha", 0.0)

        self.mono = "Cascadia Code" if font_exists("Cascadia Code") else "Consolas"
        self.q = queue.Queue()
        self.worker = None
        self.gen = 0
        self.ai_worker = None
        self.prefetch = None
        self.gpu_setup = None
        self.last_path = None
        self.last_ai_path = None
        self.last_title = ""
        self.last_url = ""
        self.all_lines = []  # (ts_str, text, speaker|None)
        self.meta_title = ""
        self._toast = None
        self._toast_job = None
        self._menu = None
        self.files_panel = None
        self._hero_bars = []
        self._hero_phase = 0.0
        self._scroll_target = None
        self._scroll_job = None

        self.url_var = tk.StringVar(value="")
        self.lang_var = tk.StringVar(value=self.settings.get("lang", "Русский"))
        self.model_var = tk.StringVar(value=self.settings.get("model", "medium"))
        self.device_var = tk.StringVar(value=self.settings.get("device", "Авто"))
        self.speed_var = tk.StringVar(value=self.settings.get("speed", "Быстро"))
        self.spk_var = tk.StringVar(value=self.settings.get("speakers", "Выкл"))
        self.ai_var = tk.StringVar(value=self.settings.get("ai_type", "Тезисы"))
        for v in (self.lang_var, self.model_var, self.device_var, self.speed_var, self.spk_var, self.ai_var):
            v.trace_add("write", lambda *a: self.persist())
        self.api_key = self.settings.get("api_key", "")

        self.build()
        self.bind_all("<Control-KeyPress>", self._hotkeys, add="+")
        self.bind("<Configure>", self._on_resize)
        self.bind("<Unmap>", lambda e: ANIM.__setitem__("active", False) if e.widget is self else None)
        self.bind("<Map>", lambda e: ANIM.__setitem__("active", True) if e.widget is self else None)
        self.after(100, self.poll)
        self.after(50, self.dark_titlebar)
        self.after(50, self._hero_tick)
        self.after(600, self.set_icon)
        self.after(30, lambda: self._fade_in(0))
        if self.settings.get("auto_update", True):
            self.after(3000, lambda: self.check_updates(silent=True))
        if self.settings.get("prefetch", True):
            self.after(2500, self.start_prefetch)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # ---- системное ----
    def _fade_in(self, i):
        if i <= 10:
            self.attributes("-alpha", ease_out(i / 10))
            self.after(16, lambda: self._fade_in(i + 1))

    def set_icon(self):
        p = resource("whispy.ico")
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
        try:
            self.textbox.configure(height=max(220, self.winfo_height() - 700))
        except Exception:
            pass

    def persist(self):
        self.settings.update({"theme": self.theme, "lang": self.lang_var.get(), "model": self.model_var.get(),
                              "device": self.device_var.get(), "speed": self.speed_var.get(), "speakers": self.spk_var.get(),
                              "ai_type": self.ai_var.get(), "api_key": self.api_key})
        try:
            self.settings["geometry"] = self.geometry()
        except Exception:
            pass
        save_settings(self.settings)

    # ---- диалоги ----
    def info(self, title, msg):
        Dialog.show_modal(self, title, msg, "info")

    def error(self, title, msg):
        Dialog.show_modal(self, title, msg, "error")

    def confirm(self, title, msg, ok="Да", cancel="Нет"):
        return Dialog.show_modal(self, title, msg, "confirm", ok=ok, cancel=cancel)

    # ---- конструкторы ----
    def card(self, parent):
        return ctk.CTkFrame(parent, fg_color=T["CARD"], corner_radius=22, border_width=1, border_color=T["BORDER"])

    def seg(self, parent, values, var):
        return ctk.CTkSegmentedButton(parent, values=values, variable=var, height=34, corner_radius=12, border_width=3,
                                      fg_color=T["FIELD"], selected_color=T["PINK"], selected_hover_color=T["PINK_HOVER"],
                                      unselected_color=T["FIELD"], unselected_hover_color=T["FIELD_BORDER"],
                                      text_color=T["TEXT"], text_color_disabled=T["MUTED"],
                                      font=ctk.CTkFont(family=UI_FONT, size=12, weight="bold"))

    def hint(self, parent, text, **grid):
        """Подсказка, которая переносится по реальной ширине карточки (никогда не вылезает за край)."""
        lb = ctk.CTkLabel(parent, text=text, text_color=T["MUTED"], anchor="w", justify="left",
                          font=ctk.CTkFont(family=UI_FONT, size=11))
        lb.grid(**grid)
        parent.bind("<Configure>", lambda e, l=lb: l.configure(wraplength=max(200, e.width - 48)), add="+")
        return lb

    def label(self, parent, text, size=11, bold=True, color=None, **kw):
        return ctk.CTkLabel(parent, text=text, text_color=color or T["MUTED"],
                            font=ctk.CTkFont(family=UI_FONT, size=size, weight="bold" if bold else "normal"), **kw)

    # ---- меню ----
    def menu_items(self, name):
        gpu_label = "Поддержка NVIDIA установлена  ✓" if cuda_ready() else "Установить поддержку NVIDIA (видеокарта)"
        return {
            "Файл": [
                ("Мои файлы…", self.show_files, "все транскрипты и результаты"),
                ("Открыть последний транскрипт", self.open_file),
                ("Открыть последний результат ИИ", self.open_ai_file),
                ("Открыть папку с файлами", lambda: open_path(OUT_DIR)),
                None,
                ("Выход", self.on_close),
            ],
            "Правка": [
                ("Вставить ссылку из буфера", self.paste_url, "Ctrl+V"),
                ("Копировать весь текст", self.copy_all),
                ("Очистить", self.clear_all),
            ],
            "Вид": [
                ("Тёмная тема", lambda: self.set_theme("dark")),
                ("Светлая тема", lambda: self.set_theme("light")),
                None,
                ("Окно по умолчанию (1000×920)", lambda: self.geometry("1000x920")),
            ],
            "ИИ": [(f"{k}  →  скопировать промпт + текст", (lambda k=k: self.copy_ai_prompt(k))) for k in AI_TYPES] + [
                None,
                ("Открыть Claude в браузере", lambda: webbrowser.open("https://claude.ai/new")),
                ("API-ключ…", self.ask_api_key),
            ],
            "Помощь": [
                ("Руководство с картинками", self.show_guide),
                ("Быстрая справка", self.show_help),
                None,
                (gpu_label, self.setup_gpu),
                ("Скачать модель заранее", self.start_prefetch_manual),
                None,
                ("Проверить обновления", lambda: self.check_updates(silent=False)),
                (("✓  " if self.settings.get("auto_update", True) else "    ") + "Проверять автоматически", self.toggle_auto_update),
                None,
                (f"О программе  ·  v{APP_VERSION}", self.show_about),
            ],
        }[name]

    def open_menu(self, name, btn):
        if self._menu and self._menu.winfo_exists():
            self._menu.close()
        self._menu = Dropdown(self, btn, self.menu_items(name), width=340 if name in ("ИИ", "Помощь", "Файл") else 270)

    # ---- построение ----
    def build(self):
        self.configure(fg_color=T["BG"])
        for w in self.winfo_children():
            if isinstance(w, tk.Toplevel):
                continue
            w.destroy()
        self._hero_bars = []
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        f_body = ctk.CTkFont(family=UI_FONT, size=13)
        f_small = ctk.CTkFont(family=UI_FONT, size=11)

        bar = ctk.CTkFrame(self, fg_color=T["BG"], corner_radius=0, height=44)
        bar.grid(row=0, column=0, sticky="ew")
        bar.grid_propagate(False)
        lg = logo_image(20)
        if lg is not None:
            self._bar_logo = ImageTk.PhotoImage(lg)
            tk.Label(bar, image=self._bar_logo, bg=T["BG"], bd=0).pack(side="left", padx=(24, 8), pady=12)
        else:
            ctk.CTkLabel(bar, text="", width=10, height=10, corner_radius=5, fg_color=T["PINK"]).pack(side="left", padx=(24, 8), pady=17)
        ctk.CTkLabel(bar, text="Whispy", text_color=T["TEXT"], font=ctk.CTkFont(family=UI_FONT, size=13, weight="bold")).pack(side="left", padx=(0, 18))
        self.menu_btns = {}
        for name in ("Файл", "Правка", "Вид", "ИИ", "Помощь"):
            b = GhostButton(bar, name, lambda n=name: self.open_menu(n, self.menu_btns[n]), width=74, height=30, bg=T["BG"],
                            text_color=T["MUTED"], radius=15, font=(UI_FONT, 12, "bold"))
            b.set_plain()
            b.pack(side="left", padx=2, pady=7)
            self.menu_btns[name] = b
        self.theme_btn = GhostButton(bar, "Светлая" if self.theme == "dark" else "Тёмная", self.toggle_theme, width=112, height=30,
                                     bg=T["BG"], text_color=T["MUTED"], radius=15, font=(UI_FONT, 11, "bold"),
                                     icon="sun" if self.theme == "dark" else "moon", icon_size=15)
        self.theme_btn.pack(side="right", padx=(0, 24), pady=7)
        self.files_btn = GhostButton(bar, "Мои файлы", self.show_files, width=126, height=30, bg=T["BG"], text_color=T["MUTED"],
                                     radius=15, font=(UI_FONT, 11, "bold"), icon="folder", icon_size=15)
        self.files_btn.pack(side="right", padx=(0, 8), pady=7)

        self.scroll = ctk.CTkScrollableFrame(self, fg_color=T["BG"], corner_radius=0, scrollbar_button_color=T["FIELD_BORDER"],
                                             scrollbar_button_hover_color=T["PINK"])
        self.scroll.grid(row=1, column=0, sticky="nsew")
        self.scroll.grid_columnconfigure(0, weight=1)
        root = self.scroll

        self.hero = tk.Canvas(root, height=140, bg=T["BG"], highlightthickness=0, bd=0)
        self.hero.grid(row=0, column=0, sticky="ew", padx=20, pady=(4, 6))
        self.hero.bind("<Configure>", self._draw_hero)

        card = self.card(root)
        card.grid(row=1, column=0, sticky="ew", padx=20, pady=6)
        card.grid_columnconfigure(0, weight=1)
        self.label(card, "ССЫЛКА НА ВИДЕО").grid(row=0, column=0, sticky="w", padx=22, pady=(18, 6))
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.grid(row=1, column=0, sticky="ew", padx=22)
        row.grid_columnconfigure(0, weight=1)
        self.url_entry = ctk.CTkEntry(row, textvariable=self.url_var, height=50, corner_radius=16, placeholder_text="https://www.youtube.com/watch?v=…",
                                      fg_color=T["FIELD"], border_color=T["FIELD_BORDER"], border_width=1, text_color=T["TEXT"],
                                      placeholder_text_color=T["MUTED"], font=f_body)
        self.url_entry.grid(row=0, column=0, sticky="ew")
        self.url_entry.bind("<Return>", lambda e: self.start())
        self.url_entry.bind("<FocusIn>", lambda e: self.url_entry.configure(border_color=T["PINK"]))
        self.url_entry.bind("<FocusOut>", lambda e: self.url_entry.configure(border_color=T["FIELD_BORDER"]))
        self.paste_btn = GhostButton(row, "Вставить", self.paste_url, width=104, height=50, bg=T["CARD"], radius=16)
        self.paste_btn.grid(row=0, column=1, padx=(10, 0))
        self.go_btn = GradientButton(row, "Получить текст", self.start, width=200, height=50, bg=T["CARD"], icon="play")
        self.go_btn.grid(row=0, column=2, padx=(4, 0))

        opts = Flow(card, gap=18, vgap=12)
        opts.grid(row=2, column=0, sticky="ew", padx=22, pady=(14, 4))
        for label, var, values in [("ЯЗЫК", self.lang_var, list(LANGS.keys())), ("МОДЕЛЬ", self.model_var, MODELS),
                                   ("УСТРОЙСТВО", self.device_var, list(DEVICES.keys())), ("РЕЖИМ", self.speed_var, list(SPEED.keys())),
                                   ("СПИКЕРЫ", self.spk_var, list(SPEAKERS.keys()))]:
            box = ctk.CTkFrame(opts, fg_color="transparent")
            self.label(box, label).pack(anchor="w", pady=(0, 6))
            self.seg(box, values, var).pack(anchor="w")
            opts.add(box)
        self.hint(card, "small — быстро · medium — баланс · large-v3 — максимум качества (нужна NVIDIA)   ·   "
                        "«Точно» медленнее в 2–3 раза   ·   Спикеры — кто говорит в подкасте",
                  row=3, column=0, sticky="ew", padx=22, pady=(0, 18))

        prog = self.card(root)
        prog.grid(row=2, column=0, sticky="ew", padx=20, pady=6)
        prog.grid_columnconfigure(2, weight=1)
        self.wave = Wave(prog)
        self.wave.grid(row=0, column=0, padx=(22, 14), pady=(18, 6))
        self.chip = Chip(prog)
        self.chip.grid(row=0, column=1, padx=(0, 14), pady=(18, 6))
        self.status_lbl = ctk.CTkLabel(prog, text="Вставь ссылку и нажми кнопку.", font=f_body, text_color=T["TEXT"], anchor="w")
        self.status_lbl.grid(row=0, column=2, sticky="ew", pady=(18, 6))
        self.pct_lbl = ctk.CTkLabel(prog, text="", font=ctk.CTkFont(family=UI_FONT, size=13, weight="bold"), text_color=T["PINK"], width=48, anchor="e")
        self.pct_lbl.grid(row=0, column=3, padx=(8, 8), pady=(18, 6))
        self.cancel_btn = GhostButton(prog, "Стоп", self.stop, width=80, height=30, bg=T["CARD"], text_color=T["MUTED"], accent=T["ERR"])
        self.cancel_btn.grid(row=0, column=4, padx=(0, 22), pady=(18, 6))
        self.cancel_btn.configure(state="disabled")
        self.bar = GradientProgress(prog, on_value=lambda v: self.pct_lbl.configure(text=f"{int(v * 100)}%"))
        self.bar.grid(row=1, column=0, columnspan=5, sticky="ew", padx=22, pady=(6, 8))
        self.sub_lbl = ctk.CTkLabel(prog, text="", font=f_small, text_color=T["MUTED"], anchor="w")
        self.sub_lbl.grid(row=2, column=0, columnspan=5, sticky="ew", padx=22, pady=(0, 14))

        out = self.card(root)
        out.grid(row=3, column=0, sticky="ew", padx=20, pady=6)
        out.grid_columnconfigure(0, weight=1)
        top = ctk.CTkFrame(out, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=22, pady=(16, 8))
        self.title_lbl = ctk.CTkLabel(top, text=self.meta_title or "ТЕКСТ", font=ctk.CTkFont(family=UI_FONT, size=11, weight="bold"),
                                      text_color=T["MUTED"], anchor="w")
        self.title_lbl.pack(side="left", fill="x", expand=True)
        self.count_lbl = ctk.CTkLabel(top, text=f"{len(self.all_lines)} строк" if self.all_lines else "", font=f_small, text_color=T["MUTED"])
        self.count_lbl.pack(side="right")
        self.textbox = ctk.CTkTextbox(out, font=ctk.CTkFont(family=self.mono, size=12), fg_color=T["FIELD"], text_color=T["TEXT"],
                                      corner_radius=16, border_width=0, wrap="word", height=max(220, self.winfo_height() - 700),
                                      scrollbar_button_color=T["FIELD_BORDER"], scrollbar_button_hover_color=T["PINK"])
        self.textbox.grid(row=1, column=0, sticky="ew", padx=22, pady=(0, 18))
        tb = self.textbox._textbox
        tb.configure(spacing1=3, spacing3=3, padx=10, pady=8, selectbackground=T["SELECT"], selectforeground="#FFFFFF")
        tb.tag_config("ts", foreground=T["PINK"])
        tb.tag_config("muted", foreground=T["MUTED"])
        for i, c in enumerate(T["SPK"], 1):
            tb.tag_config(f"spk{i}", foreground=c, font=ctk.CTkFont(family=self.mono, size=12, weight="bold"))
        self.textbox.configure(state="disabled")
        self.render_lines()

        ai = self.card(root)
        ai.grid(row=4, column=0, sticky="ew", padx=20, pady=6)
        ai.grid_columnconfigure(0, weight=1)
        self.label(ai, "ИИ-АССИСТЕНТ  ·  ГЛАВНОЕ ИЗ ВИДЕО").grid(row=0, column=0, sticky="w", padx=22, pady=(16, 8))
        aiflow = Flow(ai, gap=10, vgap=10)
        aiflow.grid(row=1, column=0, sticky="ew", padx=22, pady=(0, 6))
        self.ai_seg = aiflow.add(self.seg(aiflow, AI_TYPES, self.ai_var))
        self.ai_api_btn = aiflow.add(GradientButton(aiflow, "Сделать через API", self.run_ai_api, width=170, height=38, bg=T["CARD"], font=(UI_FONT, 12, "bold")))
        self.ai_copy_btn = aiflow.add(GhostButton(aiflow, "Скопировать промпт + текст", lambda: self.copy_ai_prompt(), width=230, height=38, bg=T["CARD"]))
        self.ai_open_btn = aiflow.add(GhostButton(aiflow, "Открыть Claude", lambda: webbrowser.open("https://claude.ai/new"), width=140, height=38, bg=T["CARD"]))
        self.ai_result_btn = aiflow.add(GhostButton(aiflow, "Открыть результат", self.open_ai_file, width=160, height=38, bg=T["CARD"]))
        self.ai_key_btn = aiflow.add(GhostButton(aiflow, "API-ключ", self.ask_api_key, width=118, height=38, bg=T["CARD"],
                                                 text_color=T["MUTED"], icon="key", icon_size=16))
        self.hint(ai, "Результат — интерактивная страница в стиле Whispy: карточки, таблица, схема, слайды со стрелками или инфографика. "
                      "Нужен API-ключ (кнопка «API-ключ», вводится один раз). Без ключа — скопируй промпт и вставь в Claude.",
                  row=2, column=0, sticky="ew", padx=22, pady=(0, 16))

        bottom = Flow(root, gap=10, vgap=8)
        bottom.grid(row=5, column=0, sticky="ew", padx=20, pady=(6, 18))
        self.copy_btn = bottom.add(GhostButton(bottom, "Копировать всё", self.copy_all, width=170, height=42))
        self.file_btn = bottom.add(GhostButton(bottom, "Открыть файл", self.open_file, width=150, height=42))
        self.folder_btn = bottom.add(GhostButton(bottom, "Показать в папке", lambda: reveal_in_folder(self.last_path), width=160, height=42))
        self.path_lbl = bottom.add(ctk.CTkLabel(bottom, text=os.path.basename(self.last_path) if self.last_path else "", font=f_small, text_color=T["MUTED"]))
        self._scroll_target = None
        self.refresh_buttons()
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
                    return
        except Exception:
            pass
        try:
            cv = self.scroll._parent_canvas
            bbox = cv.bbox("all")
            total = (bbox[3] - bbox[1]) if bbox else 0
            if total <= 0:
                return
            vis = cv.winfo_height() / total
            if self._scroll_target is None:
                self._scroll_target = cv.yview()[0]
            self._scroll_target = min(max(0.0, self._scroll_target + (120 * (-e.delta / 120)) / total), max(0.0, 1 - vis))
            if self._scroll_job is None:
                self._scroll_job = self.after(16, self._scroll_step)
        except Exception:
            pass

    def _scroll_step(self):
        self._scroll_job = None
        try:
            cv = self.scroll._parent_canvas
            cur = cv.yview()[0]
            tgt = self._scroll_target
            if tgt is None:
                return
            diff = tgt - cur
            if abs(diff) < 0.0005:
                cv.yview_moveto(tgt)
                self._scroll_target = None
                return
            cv.yview_moveto(cur + diff * 0.28)
            self._scroll_job = self.after(16, self._scroll_step)
        except Exception:
            self._scroll_target = None

    def _draw_hero(self, e):
        w, h = max(e.width, 200), 140
        chip_text = f"v{APP_VERSION}  ·  субтитры + whisper + спикеры + ИИ"
        f = tkfont.Font(family=UI_FONT, size=10, weight="bold")
        img, cw = hero_image(w, h, chip_text, f)
        self._hero_img = ImageTk.PhotoImage(img)
        self.hero.delete("all")
        self.hero.create_image(0, 0, anchor="nw", image=self._hero_img)
        tx = 110 if logo_image(64) is not None else 30
        self.hero.create_text(tx, 48, anchor="w", text="Whispy", fill=T["HERO_TEXT"], font=(UI_FONT, 30, "bold"))
        self.hero.create_text(tx, 84, anchor="w", text="YouTube-ссылка → текст с таймкодами и спикерами → главное через ИИ. Локально и бесплатно.",
                              fill=T["HERO_SUB"], font=(UI_FONT, 12))
        self.hero.create_text(30 + cw / 2, 115, text=chip_text, fill=T["HERO_SUB"], font=(UI_FONT, 10, "bold"))
        self._hero_bars = []
        bars, bw, gap = 9, 8, 7
        sub_w = tkfont.Font(family=UI_FONT, size=12).measure("YouTube-ссылка → текст с таймкодами и спикерами → главное через ИИ. Локально и бесплатно.")
        bars_w = bars * bw + (bars - 1) * gap
        x = w - bars_w - 40
        if x < tx + sub_w + 24:
            bars = 5
            bars_w = bars * bw + (bars - 1) * gap
            x = w - bars_w - 40
        if x < tx + sub_w + 24:
            return  # места нет — волну не рисуем, текст важнее
        c1, c2 = GRAD()
        for i in range(bars):
            col = rgb_hex(mix(c1, c2, i / (bars - 1)))
            self._hero_bars.append((self.hero.create_rectangle(x, h / 2 - 4, x + bw, h / 2 + 4, fill=col, outline=""), x, bw))
            x += bw + gap

    def _hero_tick(self):
        if not self.winfo_exists():
            return
        if not ANIM["active"]:
            self.after(200, self._hero_tick)
            return
        busy = self.worker is not None and self.worker.is_alive()
        self._hero_phase += 0.28 if busy else 0.06
        h = 140
        for i, (item, x, bw) in enumerate(self._hero_bars):
            if busy:
                a = 0.25 + 0.75 * (0.5 + 0.5 * math.sin(self._hero_phase + i * 0.7))
            else:
                a = 0.18 + 0.32 * (0.5 + 0.5 * math.sin(self._hero_phase + i * 0.9))
            bh = h * 0.55 * a
            try:
                self.hero.coords(item, x, (h - bh) / 2, x + bw, (h + bh) / 2)
            except Exception:
                break
        self.after(50, self._hero_tick)

    def toggle_theme(self):
        self.theme = "light" if self.theme == "dark" else "dark"
        apply_theme(self.theme)
        self.persist()
        self.attributes("-alpha", 0.0)
        self.build()
        self.dark_titlebar()
        self.after(20, lambda: self._fade_in(0))

    def set_theme(self, name):
        if name != self.theme:
            self.toggle_theme()

    def refresh_buttons(self):
        busy = self.worker is not None and self.worker.is_alive()
        has = bool(self.all_lines)
        ai_busy = self.ai_worker is not None and self.ai_worker.is_alive()
        self.copy_btn.configure(state="normal" if has else "disabled")
        self.file_btn.configure(state="normal" if self.last_path else "disabled")
        self.ai_copy_btn.configure(state="normal" if has else "disabled")
        self.ai_result_btn.configure(state="normal" if self.last_ai_path else "disabled")
        self.ai_api_btn.configure(state="normal" if (has and not busy and not ai_busy) else "disabled",
                                  text="Работаю…" if ai_busy else "Сделать через API")
        self.go_btn.configure(state="disabled" if busy else "normal", text="Работаю…" if busy else "Получить текст")

    # ---- текст ----
    def render_lines(self):
        self.textbox.configure(state="normal")
        tb = self.textbox._textbox
        tb.delete("1.0", "end")
        if not self.all_lines:
            tb.insert("end", "Здесь появится текст — строка за строкой, с таймкодами. Включи «Спикеры», чтобы видеть, кто говорит.", "muted")
        for ts, text, spk in self.all_lines:
            tb.insert("end", ts, "ts")
            if spk:
                tb.insert("end", f"  Спикер {spk}:", f"spk{min(spk, len(T['SPK']))}")
            tb.insert("end", "  " + text + "\n")
        self.textbox.configure(state="disabled")

    def append_line(self, ts, text):
        self.textbox.configure(state="normal")
        tb = self.textbox._textbox
        if len(self.all_lines) == 1:
            tb.delete("1.0", "end")
        tb.insert("end", ts, "ts")
        tb.insert("end", "  " + text + "\n")
        self.textbox.see("end")
        self.textbox.configure(state="disabled")

    def text_for_copy(self):
        return "\n".join(f"{ts} {('Спикер ' + str(spk) + ': ') if spk else ''}{text}" for ts, text, spk in self.all_lines)

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
        self.all_lines.clear()
        self.last_path = None
        self.last_url = url
        self.meta_title = ""
        self.render_lines()
        self.count_lbl.configure(text="")
        self.path_lbl.configure(text="")
        self.pct_lbl.configure(text="0%")
        self.sub_lbl.configure(text="")
        self.title_lbl.configure(text="ТЕКСТ")
        self.bar.set(0)
        self.cancel_btn.configure(state="normal")
        self.chip.set("Старт", "work")
        self.wave.start()
        self.status_lbl.configure(text="Подключаюсь к YouTube…", text_color=T["TEXT"])
        self.gen += 1
        self.worker = Worker(self, url, LANGS[self.lang_var.get()], self.model_var.get(), DEVICES[self.device_var.get()],
                             SPEED[self.speed_var.get()], SPEAKERS[self.spk_var.get()], self.gen)
        self.worker.start()
        self.refresh_buttons()

    def stop(self):
        if self.worker and self.worker.is_alive():
            self.worker.cancel.set()
        self.gen += 1
        self.worker = None
        self.wave.stop()
        self.bar.set_indeterminate(False)
        self.chip.set("Отменено", "idle")
        self.status_lbl.configure(text="Остановлено. Можно запускать заново.", text_color=T["TEXT"])
        self.cancel_btn.configure(state="disabled")
        self.refresh_buttons()

    def finish_ui(self):
        self.cancel_btn.configure(state="disabled")
        self.wave.stop()
        self.bar.set_indeterminate(False)
        self.refresh_buttons()

    def clear_all(self):
        if self.worker and self.worker.is_alive():
            return
        self.all_lines.clear()
        self.last_path = None
        self.meta_title = ""
        self.url_var.set("")
        self.render_lines()
        self.count_lbl.configure(text="")
        self.path_lbl.configure(text="")
        self.pct_lbl.configure(text="")
        self.sub_lbl.configure(text="")
        self.title_lbl.configure(text="ТЕКСТ")
        self.bar.set(0)
        self.chip.set("Ожидание", "idle")
        self.status_lbl.configure(text="Вставь ссылку и нажми кнопку.", text_color=T["TEXT"])
        self.refresh_buttons()

    def open_file(self):
        if self.last_path and os.path.exists(self.last_path):
            open_path(self.last_path)
        else:
            self.toast("Файла ещё нет — сначала получи текст")

    def open_ai_file(self):
        if self.last_ai_path and os.path.exists(self.last_ai_path):
            open_html(self.last_ai_path, "Whispy — " + os.path.basename(self.last_ai_path))
        else:
            self.toast("Результата ИИ ещё нет")

    def show_files(self):
        if self.files_panel and self.files_panel.winfo_exists():
            self.files_panel.refresh()
            self.files_panel.lift()
            return
        self.files_panel = FilesPanel(self).show()

    def copy_all(self):
        if not self.all_lines:
            self.toast("Текста пока нет")
            return
        self.clipboard_clear()
        self.clipboard_append(self.text_for_copy())
        self.toast("Скопировано в буфер обмена  ✓")

    def ai_payload(self, kind):
        title = self.last_title or self.meta_title
        header = f"Название видео: {title}\n" if title else ""
        prompt = AI_PROMPTS[kind].replace(AI_FRAGMENT_RULES,
                                          "Оформи результат как интерактивный артефакт (HTML-страница с карточками/таблицей/схемой/слайдами) "
                                          "в премиальном тёмном стиле с розовым #FF5FB4 и фиолетовым #8B5CF6. Пиши по-русски.")
        return f"{prompt}\n\n{header}\nТРАНСКРИПТ:\n" + self.text_for_copy()

    def copy_ai_prompt(self, kind=None):
        if not self.all_lines:
            self.toast("Сначала получи текст видео")
            return
        kind = kind or self.ai_var.get()
        self.ai_var.set(kind)
        self.clipboard_clear()
        self.clipboard_append(self.ai_payload(kind))
        self.toast(f"Промпт «{kind}» + текст скопированы — вставь в Claude  ✓")

    def ask_api_key(self):
        val = Dialog.show_modal(self, "API-ключ Anthropic",
                                "Вставь ключ вида sk-ant-… (его даёт владелец программы или console.anthropic.com). "
                                "Пустая строка — удалить ключ. Ключ хранится только на этом компьютере.", "input", secret=True, default=self.api_key, ok="Сохранить")
        if val is None:
            return
        self.api_key = val.strip()
        self.persist()
        self.toast("Ключ сохранён  ✓" if val.strip() else "Ключ удалён")
        self.refresh_buttons()

    def run_ai_api(self):
        if not self.all_lines or (self.ai_worker and self.ai_worker.is_alive()):
            return
        if not self.api_key:
            self.ask_api_key()
            if not self.api_key:
                return
        self.persist()
        self.chip.set("ИИ", "work")
        self.wave.start()
        self.bar.set_indeterminate(True)
        self.pct_lbl.configure(text="…")
        self.ai_worker = AIWorker(self.api_key, self.ai_var.get(), self.text_for_copy(), self.last_title or self.meta_title or "video",
                                  self.last_url, self.q)
        self.ai_worker.start()
        self.refresh_buttons()

    # ---- модели / GPU / обновления ----
    def start_prefetch(self):
        name = self.model_var.get()
        if model_cached(name) or (self.prefetch and self.prefetch.is_alive()):
            return
        try:
            check_disk(name, 0)
        except RuntimeError:
            return
        self.prefetch = ModelPrefetch(name, self.q)
        self.prefetch.start()
        self.sub_lbl.configure(text=f"Загружаю модель {name} в фоне, чтобы первое видео не ждало…")

    def start_prefetch_manual(self):
        name = self.model_var.get()
        if model_cached(name):
            self.toast(f"Модель {name} уже скачана  ✓")
            return
        if self.prefetch and self.prefetch.is_alive():
            self.toast("Модель уже качается — смотри строку под прогрессом")
            return
        try:
            check_disk(name, 0)
        except RuntimeError as e:
            self.error("Мало места", str(e))
            return
        self.start_prefetch()
        self.toast(f"Качаю модель {name} в фоне")

    def setup_gpu(self):
        if cuda_ready():
            self.info("NVIDIA", "Поддержка видеокарты уже работает. Выбери «NVIDIA» или «Авто» в устройстве.")
            return
        if self.gpu_setup and self.gpu_setup.is_alive():
            self.toast("Установка уже идёт")
            return
        if not has_nvidia():
            if not self.confirm("Видеокарта не найдена", "Драйвер NVIDIA не обнаружен. Установить библиотеки всё равно?\n"
                                                           "Они займут ~1 ГБ и без видеокарты NVIDIA не пригодятся.", ok="Установить", cancel="Отмена"):
                return
        if not self.confirm("Поддержка NVIDIA", "Скачаю cuBLAS и cuDNN для CUDA 12 (~1 ГБ) в папку программы. Драйвер NVIDIA должен быть "
                                                "установлен отдельно (GeForce Experience / сайт NVIDIA). После установки программа перезапустится.",
                            ok="Скачать", cancel="Позже"):
            return
        self.gpu_setup = GpuSetup(self.q)
        self.gpu_setup.start()
        self.chip.set("NVIDIA", "work")
        self.wave.start()

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

    def _exit_for_update(self):
        if self.worker and self.worker.is_alive():
            self.worker.cancel.set()
        shutil.rmtree(TEMP_DIR, ignore_errors=True)
        self.destroy()

    # ---- справка ----
    def show_guide(self):
        p = resource("docs", "guide.html")
        if p:
            open_html(p, "Whispy — руководство")
        else:
            webbrowser.open(GITHUB_URL + "/blob/main/docs/guide.md")

    def show_help(self):
        self.info("Быстрая справка",
                  "1. Вставь ссылку на YouTube (кнопка «Вставить» или Ctrl+V в любой раскладке).\n"
                  "2. Нажми «Получить текст». Сначала ищутся субтитры, если их нет — распознаёт whisper.\n"
                  "3. «Спикеры» — программа определит, кто говорит (для подкастов и интервью).\n"
                  "4. Файл с таймкодами сохраняется автоматически. Все файлы — кнопка «Мои файлы» сверху.\n"
                  "5. «ИИ-ассистент»: выбери формат → «Сделать через API» (или скопируй промпт в Claude). "
                  "Получишь интерактивную страницу: карточки, таблицу, схему, слайды или инфографику.\n\n"
                  "Модели: small — быстро, medium — баланс, large-v3 — максимум (нужна NVIDIA). "
                  "Подробное руководство с картинками — в меню Помощь.")

    def show_about(self):
        self.info("Whispy", f"Версия {APP_VERSION}.\nYouTube-ссылка → текст с таймкодами и спикерами → главное через ИИ.\n"
                            "Локальная транскрипция: yt-dlp + faster-whisper, спикеры — sherpa-onnx. Работает офлайн после первого запуска.\n"
                            "Только для личного использования.")

    # ---- мелочи ----
    def toast(self, text):
        if self._toast is None or not self._toast.winfo_exists():
            self._toast = ctk.CTkLabel(self, text=text, height=38, corner_radius=19, padx=20, fg_color=T["TOAST"], text_color=T["TOAST_TEXT"],
                                       font=ctk.CTkFont(family=UI_FONT, size=12, weight="bold"))
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

    # ---- события от потоков ----
    def poll(self):
        try:
            while True:
                kind, d = self.q.get_nowait()
                if "gen" in d and d["gen"] != self.gen:
                    continue
                if kind == "status":
                    stage = d["stage"]
                    self.chip.set(stage, {"Готово": "ok", "Ошибка": "err", "Отменено": "idle"}.get(stage, "work"))
                    self.status_lbl.configure(text=d["text"], text_color=T["TEXT"])
                elif kind == "progress":
                    self.bar.set(d["value"])
                elif kind == "indeterminate":
                    self.bar.set_indeterminate(d["on"])
                    if d["on"]:
                        self.pct_lbl.configure(text="…")
                elif kind == "meta":
                    dur = fmt_ts(d["duration"])[1:-1] if d["duration"] else "—"
                    self.meta_title = d["title"]
                    self.title_lbl.configure(text=f"{d['title']}   ·   {dur}")
                elif kind == "line":
                    ts = fmt_ts(d["t"])
                    self.all_lines.append((ts, d["text"], None))
                    self.append_line(ts, d["text"])
                    self.count_lbl.configure(text=f"{len(self.all_lines)} строк")
                elif kind == "speakers":
                    labels = d["labels"]
                    self.all_lines = [(ts, text, labels[i] if i < len(labels) else None) for i, (ts, text, _) in enumerate(self.all_lines)]
                    self.render_lines()
                    self.sub_lbl.configure(text=f"Найдено спикеров: {len(set(labels))}")
                elif kind == "warn":
                    self.sub_lbl.configure(text=d["text"].splitlines()[0])
                elif kind == "done":
                    self.last_path = d["path"]
                    self.last_title = d["title"]
                    self.path_lbl.configure(text=os.path.basename(d["path"]))
                    self.status_lbl.configure(text=f"Готово: {d['lines']} строк · {d['source']}", text_color=T["OK"])
                    self.textbox.see("1.0")
                    self.finish_ui()
                    self.toast("Файл сохранён — смотри «Мои файлы»  ✓")
                elif kind == "cancelled":
                    self.finish_ui()
                elif kind == "error":
                    self.finish_ui()
                    self.status_lbl.configure(text=d["text"].splitlines()[0], text_color=T["ERR"])
                    self.error("Не получилось", d["text"])
                elif kind == "ai_status":
                    self.status_lbl.configure(text=d["text"], text_color=T["TEXT"])
                elif kind == "ai_done":
                    self.last_ai_path = d["path"]
                    self.wave.stop()
                    self.bar.set_indeterminate(False)
                    self.bar.set(1.0)
                    self.chip.set("ИИ готово", "ok")
                    self.status_lbl.configure(text=f"Сохранено: {os.path.basename(d['path'])}", text_color=T["OK"])
                    self.refresh_buttons()
                    self.toast("Результат ИИ сохранён и открыт  ✓")
                    try:
                        open_html(d["path"], "Whispy — " + os.path.basename(d["path"]))
                    except Exception:
                        pass
                elif kind == "ai_error":
                    self.wave.stop()
                    self.bar.set_indeterminate(False)
                    self.chip.set("Ошибка", "err")
                    self.status_lbl.configure(text=d["text"].splitlines()[0], text_color=T["ERR"])
                    self.refresh_buttons()
                    self.error("ИИ-ассистент", d["text"])
                elif kind == "prefetch":
                    if not (self.worker and self.worker.is_alive()):
                        self.sub_lbl.configure(text=f"Модель {d['model']} загружается в фоне: {int(d['frac'] * 100)}%")
                elif kind == "prefetch_done":
                    self.sub_lbl.configure(text=f"Модель {d['model']} готова — распознавание начнётся сразу  ✓")
                elif kind == "prefetch_error":
                    self.sub_lbl.configure(text=f"Модель {d['model']} не скачалась: {d['text'][:80]}")
                elif kind == "gpu_status":
                    self.status_lbl.configure(text=d["text"], text_color=T["TEXT"])
                    self.bar.set(d["frac"])
                elif kind == "gpu_done":
                    self.wave.stop()
                    self.bar.set(1.0)
                    self.chip.set("Готово", "ok")
                    self.status_lbl.configure(text="Библиотеки NVIDIA установлены.", text_color=T["OK"])
                    if self.confirm("NVIDIA готова", "Библиотеки установлены. Чтобы они заработали, программу нужно перезапустить.",
                                    ok="Перезапустить", cancel="Позже"):
                        self.persist()
                        subprocess.Popen([sys.executable] + ([] if getattr(sys, "frozen", False) else [os.path.abspath(__file__)]))
                        self._exit_for_update()
                elif kind == "gpu_error":
                    self.wave.stop()
                    self.chip.set("Ошибка", "err")
                    self.status_lbl.configure(text=d["text"].splitlines()[0], text_color=T["ERR"])
                    self.error("Поддержка NVIDIA", d["text"])
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
        except queue.Empty:
            pass
        self.after(100, self.poll)

    def on_close(self):
        if self.worker and self.worker.is_alive():
            if not self.confirm("Закрыть Whispy?", "Обработка ещё идёт. Если закрыть сейчас, текст не сохранится.", ok="Закрыть", cancel="Остаться"):
                return
            self.worker.cancel.set()
        self.persist()
        shutil.rmtree(TEMP_DIR, ignore_errors=True)
        self.destroy()


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--viewer":
        try:
            run_viewer(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "Whispy")
        except Exception:
            webbrowser.open("file:///" + os.path.abspath(sys.argv[2]).replace("\\", "/"))
        sys.exit(0)
    if sys.platform == "win32":
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    ctk.set_default_color_theme("blue")
    App().mainloop()
