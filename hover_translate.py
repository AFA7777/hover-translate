#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
hover_translate — 滑鼠指到螢幕上的英文，唸出英文發音，再用繁體中文說出翻譯。

運作流程：
  按住 Ctrl，滑鼠停在英文字上約 400ms
    → BitBlt 擷取游標周圍畫面（含 2x 放大，小字才認得出來）
    → Windows 內建 OCR 取出單字與其座標，挑出游標正下方那個字
    → SAPI 英文語音唸單字（Zira）
    → 免費線上翻譯 → 繁中，寫入 SQLite 快取
    → 浮窗顯示（單字/詞性/整句），SAPI 繁中語音唸出翻譯（Hanhan）

熱鍵：Esc 連按兩下 結束   Ctrl+Alt+H 暫停/恢復   Ctrl+Alt+Q 結束
"""

import asyncio
import ctypes
import json
import os
import queue
import re
import sqlite3
import sys
import threading
import time
import traceback
from ctypes import wintypes

# 這支程式刻意不 import 任何網路模組（urllib / socket / requests）。
# 字典是本地的，執行期零連線 —— 拿防火牆擋死它也照常運作。

# 用 pythonw.exe 啟動（桌面捷徑）時沒有主控台，sys.stdout 是 None，所有訊息會
# 石沉大海。這時改寫進 hover_translate.log，否則出事完全無從查起。
WINDOWLESS = sys.stdout is None
if WINDOWLESS:
    try:
        _log = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "hover_translate.log"), "a", encoding="utf-8",
                    buffering=1)
        _log.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} =====\n")
        sys.stdout = sys.stderr = _log
    except Exception:
        pass
else:
    # 主控台在台灣預設 cp950，印中文會炸；統一改成 utf-8。
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

# 必須在任何視窗/座標運算之前宣告 DPI 感知，否則游標座標與螢幕像素會錯開。
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PER_MONITOR_DPI_AWARE
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
DICT_PATH = os.path.join(BASE_DIR, "dict.db")
FIX_PATH = os.path.join(BASE_DIR, "用語修正.txt")

DEFAULT_CONFIG = {
    "modifier": "ctrl",           # ctrl / alt / shift / none（none = 純停留，會很吵）
    "dwell_ms": 400,              # 滑鼠靜止多久才觸發
    "capture_width": 900,         # 擷取範圍（實體像素，以游標為中心）
    "capture_height": 90,
    "ocr_scale": 2,               # OCR 前放大倍率，小字建議 2
    "ocr_language": "auto",       # auto / en-US / zh-Hant-TW
    "speak_english": True,
    "speak_chinese": True,
    "speak_sentence_english": False,   # 連整句英文一起唸（練聽力再開）
    "english_voice": "Zira",
    "chinese_voice": "Hanhan",
    "english_rate": 0,            # -10 ~ 10
    "chinese_rate": 0,
    # Esc 結束程式。Esc 是日常最常按的鍵之一，而這是全域監聽，所以預設要連按
    # 兩下才結束；"single" = 按一下就結束（容易誤關），"off" = 只認 Ctrl+Alt+Q。
    "esc_quit": "double",
    "esc_double_ms": 600,         # 連按兩下的判定間隔
    "quit_toast_ms": 1500,        # 結束時「即時翻譯停止」浮窗停留多久
    "show_sentence": True,        # 浮窗是否顯示整句原文（純上下文，不翻譯、不出網）
    # 浮窗不透明度：0.9 = 九成實心、一成穿透底下的畫面。
    # 低於 0.6 底下的文字會透上來，最暗的那行（整句）會先糊掉。夾在 0.3~1.0。
    "opacity": 0.9,
    "show_phonetic": True,        # 浮窗是否顯示音標
    "show_stars": True,           # 是否顯示 Collins 詞頻星級（★越多越基礎）
    # 只顯示這幾個考試標籤。ECDICT 另有 zk/gk/ky/cet4/cet6（中國的中考/高考/
    # 考研/四六級），對台灣使用者沒意義又佔版面，不列入即不顯示。
    # ECDICT 沒有多益(TOEIC)資料，所以這裡放不進「多益」。
    "exam_tags": ["toefl", "ielts", "gre"],
    "max_senses": 4,              # 最多顯示幾個義項
    "hide_after_ms": 6000,
    "font_size_word": 20,
    "font_size_trans": 17,
    "font_size_note": 11,
    "min_word_len": 2,
    "debug": False,
}


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg.update(json.load(f))
        except Exception as e:
            print(f"[warn] config.json 讀取失敗，使用預設值：{e}")
    else:
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
    return cfg


CFG = load_config()


def log(*a):
    if CFG["debug"]:
        print("[dbg]", *a, flush=True)


# ---------------------------------------------------------------- 螢幕擷取
user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

SRCCOPY = 0x00CC0020
HALFTONE = 4
DIB_RGB_COLORS = 0
BI_RGB = 0
SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN = 76, 77
SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN = 78, 79


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


# 64 位元下 handle 是指標，restype 沒設會被截成 int32。
user32.GetDC.restype = wintypes.HDC
user32.GetDC.argtypes = [wintypes.HWND]
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
user32.GetSystemMetrics.restype = ctypes.c_int
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.CreateDIBSection.restype = wintypes.HBITMAP
gdi32.CreateDIBSection.argtypes = [wintypes.HDC, ctypes.POINTER(BITMAPINFO),
                                   wintypes.UINT, ctypes.POINTER(ctypes.c_void_p),
                                   wintypes.HANDLE, wintypes.DWORD]
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.DeleteDC.argtypes = [wintypes.HDC]
gdi32.BitBlt.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                         ctypes.c_int, wintypes.HDC, ctypes.c_int, ctypes.c_int,
                         wintypes.DWORD]
gdi32.StretchBlt.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                             ctypes.c_int, wintypes.HDC, ctypes.c_int, ctypes.c_int,
                             ctypes.c_int, ctypes.c_int, wintypes.DWORD]
gdi32.SetStretchBltMode.argtypes = [wintypes.HDC, ctypes.c_int]

# Windows 11 的 DWM 可以直接給無邊框視窗原生圓角與邊框色 —— 由合成器在 GPU 上
# 做，我們不必自繪、不必 PIL、不多佔記憶體。舊版 Windows 會回傳失敗，忽略即可。
try:
    dwmapi = ctypes.WinDLL("dwmapi")
    dwmapi.DwmSetWindowAttribute.restype = ctypes.c_long
    dwmapi.DwmSetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD,
                                             ctypes.c_void_p, wintypes.DWORD]
except Exception:
    dwmapi = None

DWMWA_NCRENDERING_POLICY = 2       # 2 = 啟用，讓 popup 也吃得到 DWM 效果（含陰影）
DWMWA_WINDOW_CORNER_PREFERENCE = 33  # 2 = 圓角，3 = 小圓角
DWMWA_BORDER_COLOR = 34


def colorref(hexcolor):
    """#rrggbb → Win32 COLORREF（0x00BBGGRR，位元組順序是反的）"""
    r, g, b = (int(hexcolor[i:i + 2], 16) for i in (1, 3, 5))
    return (b << 16) | (g << 8) | r
gdi32.SetBrushOrgEx.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int,
                                ctypes.POINTER(wintypes.POINT)]
user32.GetParent.restype = wintypes.HWND
user32.GetParent.argtypes = [wintypes.HWND]
user32.GetWindowLongW.restype = wintypes.LONG
user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.SetWindowLongW.restype = wintypes.LONG
user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.LONG]
user32.GetAsyncKeyState.restype = ctypes.c_short
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]


def virtual_screen():
    gsm = user32.GetSystemMetrics
    return (gsm(SM_XVIRTUALSCREEN), gsm(SM_YVIRTUALSCREEN),
            gsm(SM_CXVIRTUALSCREEN), gsm(SM_CYVIRTUALSCREEN))


def cursor_pos():
    pt = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def msgbox(text, title="即時翻譯", icon=0x40):
    """無主控台時唯一能讓使用者看到訊息的管道。0x40=資訊 0x10=錯誤"""
    try:
        user32.MessageBoxW(None, text, title, icon | 0x1000)   # MB_SYSTEMMODAL
    except Exception:
        pass


_MUTEX = None


def acquire_single_instance():
    """用具名 mutex 擋掉重複啟動。

    桌面捷徑是無主控台的，沒有視窗可以看出「已經在跑了」，很容易點成好幾份 ——
    多份一起搶麥克風跟 OCR，會變成同一個字被唸好幾遍。
    """
    global _MUTEX
    ERROR_ALREADY_EXISTS = 183
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateMutexW.restype = wintypes.HANDLE
    k32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    _MUTEX = k32.CreateMutexW(None, False, "hover_translate_single_instance_v1")
    return ctypes.get_last_error() != ERROR_ALREADY_EXISTS


def grab_bgra(x, y, w, h, scale=1):
    """從螢幕抓 (x,y,w,h)，放大 scale 倍，回傳 top-down BGRA raw bytes。"""
    dw, dh = w * scale, h * scale
    hdc_screen = user32.GetDC(None)
    hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
    bi = BITMAPINFO()
    bi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bi.bmiHeader.biWidth = dw
    bi.bmiHeader.biHeight = -dh          # 負值 = top-down，列順序才跟 OCR 一致
    bi.bmiHeader.biPlanes = 1
    bi.bmiHeader.biBitCount = 32
    bi.bmiHeader.biCompression = BI_RGB
    ppv = ctypes.c_void_p()
    hbmp = gdi32.CreateDIBSection(hdc_screen, ctypes.byref(bi), DIB_RGB_COLORS,
                                  ctypes.byref(ppv), None, 0)
    old = gdi32.SelectObject(hdc_mem, hbmp)
    try:
        if scale == 1:
            gdi32.BitBlt(hdc_mem, 0, 0, dw, dh, hdc_screen, x, y, SRCCOPY)
        else:
            gdi32.SetStretchBltMode(hdc_mem, HALFTONE)
            gdi32.SetBrushOrgEx(hdc_mem, 0, 0, None)
            gdi32.StretchBlt(hdc_mem, 0, 0, dw, dh, hdc_screen, x, y, w, h, SRCCOPY)
        raw = bytearray(ctypes.string_at(ppv, dw * dh * 4))
    finally:
        gdi32.SelectObject(hdc_mem, old)
        gdi32.DeleteObject(hbmp)
        gdi32.DeleteDC(hdc_mem)
        user32.ReleaseDC(None, hdc_screen)
    # BitBlt 不寫 alpha，全 0 會被當成全透明；補滿 255。
    raw[3::4] = b"\xff" * (dw * dh)
    return bytes(raw), dw, dh


# ---------------------------------------------------------------- OCR
class Ocr:
    def __init__(self, lang_pref="auto"):
        from winsdk.windows.media.ocr import OcrEngine
        from winsdk.windows.globalization import Language
        self._OcrEngine = OcrEngine
        self._Language = Language
        from winsdk.windows.graphics.imaging import (
            SoftwareBitmap, BitmapPixelFormat, BitmapAlphaMode)
        from winsdk.windows.security.cryptography import CryptographicBuffer
        self._SoftwareBitmap = SoftwareBitmap
        self._fmt = BitmapPixelFormat.BGRA8
        self._alpha = getattr(BitmapAlphaMode, "IGNORE", None) or BitmapAlphaMode.STRAIGHT
        self._CryptographicBuffer = CryptographicBuffer

        avail = [l.language_tag for l in OcrEngine.available_recognizer_languages]
        order = ([lang_pref] if lang_pref != "auto" else []) + \
                ["en-US", "en-GB", "zh-Hant-TW", "zh-Hant", "zh-Hans-CN"]
        self.engine, self.lang = None, None
        for tag in order:
            if any(a.lower().startswith(tag.lower().split("-")[0]) or a.lower() == tag.lower()
                   for a in avail):
                try:
                    eng = OcrEngine.try_create_from_language(Language(tag))
                except Exception:
                    eng = None
                if eng is not None:
                    self.engine, self.lang = eng, tag
                    break
        if self.engine is None:
            self.engine = OcrEngine.try_create_from_user_profile_languages()
            self.lang = "(user profile)"
        if self.engine is None and avail:
            self.engine = OcrEngine.try_create_from_language(Language(avail[0]))
            self.lang = avail[0]
        if self.engine is None:
            raise RuntimeError("找不到任何可用的 Windows OCR 引擎")
        self.available = avail
        self._loop = asyncio.new_event_loop()   # 固定一個 loop，省去每次建立的開銷

    def recognize(self, raw, w, h):
        buf = self._CryptographicBuffer.create_from_byte_array(raw)
        bmp = self._SoftwareBitmap.create_copy_from_buffer(buf, self._fmt, w, h, self._alpha)
        return self._loop.run_until_complete(self.engine.recognize_async(bmp))


WORD_RE = re.compile(r"^[A-Za-z][A-Za-z'\-]*$")


def clean_word(s):
    return s.strip(" \t\r\n.,;:!?()[]{}\"'`*_<>|/\\+=~“”‘’…—–")


def pick_word(result, px, py, min_len):
    """挑出座標 (px,py) 所在的單字，連同它那一行的整句。"""
    best = None          # 命中：矩形直接包住游標
    fallback = None      # 沒命中：同一行水平最近的字
    for line in result.lines:
        for wd in line.words:
            r = wd.bounding_rect
            inside_y = r.y - 4 <= py <= r.y + r.height + 4
            if not inside_y:
                continue
            if r.x <= px <= r.x + r.width:
                best = (wd.text, line.text)
                break
            dist = r.x - px if px < r.x else px - (r.x + r.width)
            if fallback is None or dist < fallback[0]:
                fallback = (dist, wd.text, line.text)
        if best:
            break
    if best:
        word, sentence = best
    elif fallback and fallback[0] <= 40:
        word, sentence = fallback[1], fallback[2]
    else:
        return None, None
    word = clean_word(word)
    if len(word) < min_len or not WORD_RE.match(word):
        return None, (sentence or "").strip()
    return word, (sentence or "").strip()


# ---------------------------------------------------------------- 本地字典
# 釋義開頭的詞性標記（"n. 罩；風帽"），朗讀前要拿掉，否則會唸出「n 點」。
POS_PREFIX = re.compile(r"^\s*(?:\[[^\]]{1,12}\]|[a-z]{1,5}\.)\s*", re.I)
# 「run的過去式」這種釋義只說明形態、沒給字義，要再追查原型把真正的意思補上。
INFLECTION_ONLY = re.compile(
    r"的(?:過去式|過去分詞|現在分詞|第三人稱單數|複數形?|比較級|最高級"
    r"|ing形式|ed形式|名詞複數)")
# 詞形還原的保底規則：lemma 表沒收錄時，照英文構詞規律回推原型。
SUFFIX_RULES = [
    ("ies", "y"), ("ied", "y"), ("ier", "y"), ("iest", "y"),
    ("sses", "ss"), ("shes", "sh"), ("ches", "ch"), ("xes", "x"),
    ("ing", ""), ("ing", "e"), ("ed", ""), ("ed", "e"),
    ("es", ""), ("s", ""), ("er", ""), ("er", "e"),
    ("est", ""), ("est", "e"), ("ly", ""),
]


class LocalDict:
    """ECDICT 建成的本地繁體字典。純檔案查詢，永遠不連網。"""

    def __init__(self, db_path=DICT_PATH, fix_path=FIX_PATH):
        if not os.path.exists(db_path):
            raise FileNotFoundError(
                f"找不到字典 {db_path}\n請先執行： python build_dict.py")
        self.db = sqlite3.connect(db_path, check_same_thread=False)
        self.lock = threading.Lock()
        self.fixes = self._load_fixes(fix_path)

    @staticmethod
    def _load_fixes(path):
        """讀台灣用語修正表。OpenCC 轉不掉的構詞差異（線粒體→粒線體）靠這個補。"""
        fixes = []
        if not path or not os.path.exists(path):
            return fixes
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    src, dst = line.split("=", 1)
                    src, dst = src.strip(), dst.strip()
                    if src and dst and src != dst:
                        fixes.append((src, dst))
        except Exception as e:
            print(f"[warn] 用語修正表讀取失敗：{e}")
        # 長詞先換，避免短詞先替換破壞長詞（脫氧核糖核酸 vs 脫氧核糖）
        fixes.sort(key=lambda p: -len(p[0]))
        return fixes

    def _apply_fixes(self, text):
        for src, dst in self.fixes:
            if src in text:
                text = text.replace(src, dst)
        return text

    @staticmethod
    def _dedupe(sense):
        """簡轉繁後常出現重複詞（几率、概率都變成機率），逐項去重並保留原分隔符。"""
        head = ""
        m = POS_PREFIX.match(sense or "")
        if m:
            head, sense = m.group(0), sense[m.end():]
        tokens = re.split(r"([,，;；、])", sense or "")
        if len(tokens) < 3:
            return (head + (sense or "")).strip()
        kept, seen = [], set()
        for i in range(0, len(tokens), 2):
            item = tokens[i].strip()
            if not item or item in seen:
                continue
            seen.add(item)
            kept.append((item, tokens[i + 1] if i + 1 < len(tokens) else ""))
        if not kept:
            return (head + (sense or "")).strip()
        body = "".join(it + (sp + " " if sp in (",", ";") else sp)
                       for it, sp in kept[:-1]) + kept[-1][0]
        return head + body

    def count(self):
        with self.lock:
            return self.db.execute("SELECT COUNT(*) FROM words").fetchone()[0]

    def _row(self, key):
        with self.lock:
            return self.db.execute(
                "SELECT disp, phonetic, trans, pos, collins, frq, tag "
                "FROM words WHERE word=?", (key,)).fetchone()

    def _base_of(self, key):
        with self.lock:
            r = self.db.execute("SELECT base FROM lemma WHERE form=?", (key,)).fetchone()
        return r[0] if r else None

    def lookup(self, word):
        """查一個字。回傳 dict，查不到回 None。

        順序：原形直查 → 詞形還原表 → 字尾規則回推。
        """
        if not word:
            return None
        key = word.strip().lower()
        if not key:
            return None

        row, via = self._row(key), None
        if row is None:
            base = self._base_of(key)
            if base:
                row, via = self._row(base), base
        if row is None:
            for suf, rep in SUFFIX_RULES:
                if len(key) > len(suf) + 2 and key.endswith(suf):
                    cand = key[:len(key) - len(suf)] + rep
                    row = self._row(cand)
                    if row:
                        via = cand
                        break
                    b = self._base_of(cand)
                    if b:
                        row = self._row(b)
                        if row:
                            via = b
                            break
        if row is None:
            return None

        disp, phonetic, trans, pos, collins, frq, tag = row
        trans = self._apply_fixes(trans or "")
        senses = [self._dedupe(s.strip()) for s in trans.split("\n") if s.strip()]

        # 釋義只說明形態（"run的過去式"）時，追到原型把真正的字義補在後面
        if senses and via is None and all(INFLECTION_ONLY.search(s) for s in senses):
            base = self._base_of(key)
            if base and base != key:
                brow = self._row(base)
                if brow:
                    extra = self._apply_fixes(brow[2] or "")
                    for s in extra.split("\n"):
                        s = self._dedupe(s.strip())
                        if s and s not in senses:
                            senses.append(s)
                    via = base
                    if not phonetic:
                        phonetic = brow[1] or ""

        trans = "\n".join(senses)   # trans 一律由 senses 產生，兩者不能各說各話

        return {
            "word": word, "disp": disp or word, "phonetic": phonetic or "",
            "trans": trans, "senses": senses, "pos": pos or "",
            "collins": collins or 0, "frq": frq or 0, "tag": tag or "",
            "via": via if via and via != key else None,
        }

    @staticmethod
    def speakable(sense):
        """把一個義項整理成適合朗讀的樣子：去掉詞性標記，只留第一段。"""
        s = POS_PREFIX.sub("", sense or "").strip()
        for sep in ("；", ";", "，", ","):
            if sep in s:
                s = s.split(sep)[0].strip()
                break
        return s


# ---------------------------------------------------------------- 語音
class Speaker:
    """獨立執行緒序列播音；新的觸發會 purge 掉還沒唸完的舊句子。"""

    def __init__(self, cfg):
        self.cfg = cfg
        self.q = queue.Queue()
        self.gen = 0
        self.gen_lock = threading.Lock()
        self.ready = threading.Event()
        self.voices = {}
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try:
            import pythoncom
            import win32com.client
            pythoncom.CoInitialize()
            self.sp = win32com.client.Dispatch("SAPI.SpVoice")
            toks = self.sp.GetVoices()
            self.voice_names = []
            for i in range(toks.Count):
                t = toks.Item(i)
                name = t.GetAttribute("Name")
                self.voice_names.append(name)
                self.voices[name] = t
            self.ready.set()
        except Exception:
            traceback.print_exc()
            self.ready.set()
            return

        while True:
            gen, voice_key, text, rate = self.q.get()
            with self.gen_lock:
                if gen != self.gen:      # 已被更新的觸發取代，直接丟掉
                    continue
            try:
                tok = self._find_voice(voice_key)
                if tok is not None:
                    self.sp.Voice = tok
                self.sp.Rate = int(rate)
                self.sp.Speak(text, 1 | 2)          # ASYNC | PURGE_BEFORE_SPEAK
                while True:                          # 分段等待，才能被新觸發打斷
                    if self.sp.WaitUntilDone(80):
                        break
                    with self.gen_lock:
                        if gen != self.gen:
                            self.sp.Speak("", 1 | 2)  # purge
                            break
            except Exception:
                if self.cfg["debug"]:
                    traceback.print_exc()

    def _find_voice(self, key):
        if not key:
            return None
        k = key.lower()
        for name, tok in self.voices.items():
            if k in name.lower():
                return tok
        return None

    def new_generation(self):
        with self.gen_lock:
            self.gen += 1
            return self.gen

    def say(self, gen, voice_key, text, rate=0):
        if text:
            self.q.put((gen, voice_key, text, rate))


# ---------------------------------------------------------------- 浮窗
class Overlay:
    """無邊框、置頂、點擊穿透的提示窗。只能在主執行緒操作。"""

    # 圓角、邊框與陰影都交給 DWM，這裡不畫任何框線。
    BG = "#1a1d23"
    FG_WORD = "#f0f2f5"
    FG_PHON = "#828b99"           # 音標：比單字暗，退到次要層
    FG_TRANS = "#7fd6a2"          # 主要釋義：全窗唯一的高彩度色，視線第一個落點
    FG_SENSE = "#b7bfcb"          # 其餘義項
    FG_NOTE = "#6e7684"           # 整句與考試標籤：最暗
    FG_STAR = "#e6c07b"           # Collins 星級用暖金
    FG_STOP = "#ff8a80"           # 結束提示用暖紅，跟一般查詢結果一眼區分
    DIVIDER = "#2b2f38"
    BORDER = "#3a3f47"
    WRAP = 470
    # 顯示成中文比 raw tag 好讀。將來若補進多益資料，加一行 "toeic": "多益" 即可。
    EXAM_LABEL = {"toefl": "托福", "ielts": "雅思", "gre": "GRE",
                  "cet4": "四級", "cet6": "六級", "ky": "考研",
                  "gk": "高考", "zk": "中考"}

    def __init__(self, root, cfg):
        import tkinter as tk
        self.tk = tk
        self.cfg = cfg
        self.root = root
        self.win = tk.Toplevel(root)
        self.win.withdraw()
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        try:
            self.win.attributes("-alpha", min(1.0, max(0.3, float(cfg["opacity"]))))
        except Exception:
            pass
        # Toplevel 本身也要塗成卡片色：body 的外距會讓底層透出來，
        # 預設的白色會在卡片下緣露出一條白邊。
        self.win.configure(bg=self.BG)
        self.body = tk.Frame(self.win, bg=self.BG)
        self.body.pack(fill="both", expand=True)

        zh = "Microsoft JhengHei UI"
        n = cfg["font_size_note"]
        # 標題行平常是英文單字，用 Segoe UI；但 toast 是中文，要換成中文字體，
        # 否則會走字體 fallback，字重與行高都跑掉。
        self.font_word_en = ("Segoe UI Semibold", cfg["font_size_word"])
        self.font_word_zh = (zh, cfg["font_size_word"])

        PAD = 18
        # 單字與音標同一行、不同字級與顏色，所以要一個水平容器
        self.head = tk.Frame(self.body, bg=self.BG)
        self.head.pack(fill="x", padx=PAD, pady=(14, 0))
        self.l_word = tk.Label(self.head, bg=self.BG, fg=self.FG_WORD,
                               anchor="w", font=self.font_word_en)
        self.l_word.pack(side="left")
        self.l_phon = tk.Label(self.head, bg=self.BG, fg=self.FG_PHON,
                               anchor="w", font=("Segoe UI", n + 1))
        self.l_phon.pack(side="left", padx=(8, 0), pady=(6, 0))

        self.l_trans = tk.Label(self.body, bg=self.BG, fg=self.FG_TRANS, justify="left",
                                anchor="w", wraplength=self.WRAP,
                                font=(zh, cfg["font_size_trans"]))
        self.l_trans.pack(fill="x", padx=PAD, pady=(6, 0))

        self.l_alts = tk.Label(self.body, bg=self.BG, fg=self.FG_SENSE, justify="left",
                               anchor="w", wraplength=self.WRAP, font=(zh, n + 2))
        self.l_alts.pack(fill="x", padx=PAD, pady=(6, 0))

        self.sep = tk.Frame(self.body, bg=self.DIVIDER, height=1)
        self.l_sent = tk.Label(self.body, bg=self.BG, fg=self.FG_NOTE, justify="left",
                               anchor="w", wraplength=self.WRAP, font=(zh, n))

        # 星級與考試標籤顏色不同，各給一個 Label 併在同一列
        self.foot = tk.Frame(self.body, bg=self.BG)
        self.l_star = tk.Label(self.foot, bg=self.BG, fg=self.FG_STAR,
                               anchor="w", font=("Segoe UI", n))
        self.l_star.pack(side="left")
        self.l_tag = tk.Label(self.foot, bg=self.BG, fg=self.FG_NOTE,
                              anchor="w", font=("Segoe UI", n))
        self.l_tag.pack(side="left", padx=(8, 0))

        self.PAD = PAD
        self._hide_job = None
        self._passthrough_done = False
        self._dwm_done = False

    def _apply_dwm_style(self):
        """原生圓角 + 邊框色。GPU 合成，零執行成本；非 Win11 會失敗，忽略。"""
        if self._dwm_done or dwmapi is None:
            return
        self._dwm_done = True
        try:
            hwnd = user32.GetParent(self.win.winfo_id()) or self.win.winfo_id()
            for attr, val, ct in (
                    (DWMWA_NCRENDERING_POLICY, 2, ctypes.c_int),
                    (DWMWA_WINDOW_CORNER_PREFERENCE, 2, ctypes.c_int),
                    (DWMWA_BORDER_COLOR, colorref(self.BORDER), wintypes.DWORD)):
                v = ct(val)
                dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(v),
                                             ctypes.sizeof(v))
        except Exception:
            pass

    def _make_passthrough(self):
        """加上 WS_EX_TRANSPARENT / NOACTIVATE，讓浮窗不吃點擊也不搶焦點。"""
        if self._passthrough_done:
            return
        try:
            GWL_EXSTYLE = -20
            WS_EX_TRANSPARENT, WS_EX_LAYERED, WS_EX_NOACTIVATE = 0x20, 0x80000, 0x08000000
            hwnd = self.win.winfo_id()
            parent = user32.GetParent(hwnd)
            target = parent if parent else hwnd
            gwl = user32.GetWindowLongW(target, GWL_EXSTYLE)
            user32.SetWindowLongW(target, GWL_EXSTYLE,
                                  gwl | WS_EX_TRANSPARENT | WS_EX_LAYERED | WS_EX_NOACTIVATE)
            self._passthrough_done = True
        except Exception:
            pass

    def show(self, x, y, entry, sentence, miss_word=None):
        """entry 為 LocalDict.lookup 的結果；查不到時傳 None 並給 miss_word。"""
        if entry:
            word = entry["disp"]
            phon = (f"[{entry['phonetic']}]"
                    if self.cfg["show_phonetic"] and entry["phonetic"] else "")
            if entry.get("via"):
                phon += f"{'  ' if phon else ''}← {entry['via']}"   # 詞形還原的原型
            senses = entry["senses"][:max(1, self.cfg["max_senses"])]
            main = senses[0] if senses else ""
            rest = "\n".join(senses[1:])
            stars = "★" * entry["collins"] if self.cfg["show_stars"] else ""
            exams = " · ".join(self.EXAM_LABEL.get(t, t) for t in entry["tag"].split()
                               if t in self.cfg["exam_tags"])
        else:
            word, phon, main, rest, stars, exams = \
                (miss_word or ""), "", "（字典查無此字）", "", "", ""

        self.l_word.config(text=word, font=self.font_word_en, fg=self.FG_WORD)
        self.l_phon.config(text=phon)
        self.l_trans.config(text=main, fg=self.FG_TRANS if entry else self.FG_NOTE)
        self.l_alts.config(text=rest)
        self.l_alts.pack_forget() if not rest else self.l_alts.pack(
            fill="x", padx=self.PAD, pady=(6, 0), after=self.l_trans)

        # 整句只作為上下文顯示，不翻譯、不外傳。有內容才畫分隔線。
        s = sentence if (self.cfg["show_sentence"] and sentence) else ""
        if s:
            self.sep.pack(fill="x", padx=self.PAD, pady=(12, 0))
            self.l_sent.config(text=s)
            self.l_sent.pack(fill="x", padx=self.PAD, pady=(10, 0))
        else:
            self.sep.pack_forget()
            self.l_sent.pack_forget()

        self.l_star.config(text=stars)
        self.l_tag.config(text=exams)
        # 星號欄位空的時候要收掉它的間距，否則標籤會莫名往右縮排 8px
        self.l_tag.pack_configure(padx=(8, 0) if stars else (0, 0))
        if stars or exams:
            self.foot.pack(fill="x", padx=self.PAD, pady=(10, 0))
        else:
            self.foot.pack_forget()

        self.body.pack_configure(pady=(0, 14))
        self._present(x, y)

    def toast(self, x, y, text, hide_ms=1200, color=None):
        """單行提示，用來回饋「再按一次 Esc 結束」「即時翻譯停止」這類操作。"""
        self.l_word.config(text=text, font=self.font_word_zh,
                           fg=color or self.FG_WORD)
        self.l_phon.config(text="")
        self.l_trans.config(text="")
        self.l_alts.pack_forget()
        self.sep.pack_forget()
        self.l_sent.pack_forget()
        self.foot.pack_forget()
        self.body.pack_configure(pady=(0, 6))
        self._present(x, y, hide_ms)

    def _present(self, x, y, hide_ms=None):
        """定位到游標右下，超出螢幕就翻到上方，然後顯示並排定自動隱藏。"""
        self.win.update_idletasks()
        w, h = self.win.winfo_reqwidth(), self.win.winfo_reqheight()
        vx, vy, vw, vh = virtual_screen()
        px = min(max(x + 18, vx + 4), vx + vw - w - 4)
        py = y + 26
        if py + h > vy + vh - 4:
            py = y - h - 14
        py = min(max(py, vy + 4), vy + vh - h - 4)
        self.win.geometry(f"+{int(px)}+{int(py)}")
        self.win.deiconify()
        self.win.lift()
        self.win.attributes("-topmost", True)
        self._make_passthrough()
        self._apply_dwm_style()
        if self._hide_job:
            self.root.after_cancel(self._hide_job)
        self._hide_job = self.root.after(
            hide_ms if hide_ms is not None else self.cfg["hide_after_ms"], self.hide)

    def hide(self):
        if self._hide_job:
            try:
                self.root.after_cancel(self._hide_job)
            except Exception:
                pass
            self._hide_job = None
        self.win.withdraw()


# ---------------------------------------------------------------- 主程式
VK = {"ctrl": 0x11, "alt": 0x12, "shift": 0x10}
VK_H, VK_Q, VK_MENU, VK_CONTROL, VK_ESCAPE = 0x48, 0x51, 0x12, 0x11, 0x1B


def key_down(vk):
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


class App:
    def __init__(self):
        import tkinter as tk
        self.cfg = CFG
        self.root = tk.Tk()
        self.root.withdraw()
        self.overlay = Overlay(self.root, self.cfg)
        self.ui_q = queue.Queue()
        self.enabled = True
        self.running = True

        print("初始化 OCR…", flush=True)
        self.ocr = Ocr(self.cfg["ocr_language"])
        print(f"  OCR 引擎語言：{self.ocr.lang}   可用：{self.ocr.available}", flush=True)

        self.dict = LocalDict(DICT_PATH, FIX_PATH)
        print(f"  離線字典：{self.dict.count():,} 詞"
              f"，台灣用語修正 {len(self.dict.fixes)} 條", flush=True)

        self.speaker = Speaker(self.cfg)
        self.speaker.ready.wait(timeout=8)
        if getattr(self.speaker, "voice_names", None):
            print(f"  語音：{self.speaker.voice_names}", flush=True)

        mod = self.cfg["modifier"]
        trig = "滑鼠停留" if mod == "none" else f"按住 {mod.upper()} + 滑鼠停留"
        esc_hint = {"double": "Esc 連按兩下 結束      ",
                    "single": "Esc 結束      ", "off": ""}.get(
                        str(self.cfg["esc_quit"]).lower(), "")
        print(f"\n  已啟動：{trig} {self.cfg['dwell_ms']}ms 觸發")
        print(f"  {esc_hint}Ctrl+Alt+H 暫停/恢復      Ctrl+Alt+Q 結束\n", flush=True)

        threading.Thread(target=self.watch, daemon=True).start()
        self.root.after(30, self.pump)

    # --- UI 訊息由 worker 丟進 queue，主執行緒消化 ---
    def pump(self):
        try:
            while True:
                fn, args = self.ui_q.get_nowait()
                try:
                    fn(*args)
                except Exception:
                    if self.cfg["debug"]:
                        traceback.print_exc()
        except queue.Empty:
            pass
        if not self.running:
            self.root.destroy()
            return
        self.root.after(30, self.pump)

    def post(self, fn, *args):
        self.ui_q.put((fn, args))

    def quit(self, why=""):
        """顯示「即時翻譯停止」浮窗，停留看得到之後才真的結束。

        必須先 sleep 再把 running 設 False —— pump() 一看到 running 為假就會
        root.destroy()，視窗連同浮窗會立刻消失，只留下一閃。
        """
        ms = max(0, int(self.cfg["quit_toast_ms"]))
        print(f"結束{f'（{why}）' if why else ''}。", flush=True)
        if ms:
            p = cursor_pos()
            self.post(self.overlay.toast, p[0], p[1], "即時翻譯停止",
                      ms, self.overlay.FG_STOP)
            time.sleep(ms / 1000.0)
        self.running = False

    # --- 監看滑鼠 / 熱鍵 ---
    def watch(self):
        mod_vk = VK.get(self.cfg["modifier"])
        dwell = self.cfg["dwell_ms"] / 1000.0
        armed = False            # 只有「按住修飾鍵之後滑鼠有動過」才會武裝
        last_pos = cursor_pos()
        last_move = time.time()
        fired_at = None
        hotkey_cooldown = 0.0
        esc_prev = False
        esc_last = 0.0
        esc_mode = str(self.cfg["esc_quit"]).lower()
        esc_gap = self.cfg["esc_double_ms"] / 1000.0

        while self.running:
            time.sleep(0.05)
            now = time.time()

            # Esc 結束。只認「按下的瞬間」，按住不會連發；不吃掉按鍵，
            # 其他程式的 Esc 照常運作。預設要連按兩下，避免日常誤關。
            esc_now = key_down(VK_ESCAPE)
            if esc_now and not esc_prev and esc_mode != "off":
                if esc_mode == "single" or now - esc_last <= esc_gap:
                    self.quit("Esc")
                    return
                esc_last = now
                p = cursor_pos()
                self.post(self.overlay.toast, p[0], p[1], "再按一次 Esc 結束")
            esc_prev = esc_now

            # 熱鍵：Ctrl+Alt+H / Ctrl+Alt+Q
            if now > hotkey_cooldown and key_down(VK_CONTROL) and key_down(VK_MENU):
                if key_down(VK_Q):
                    self.quit("Ctrl+Alt+Q")
                    return
                if key_down(VK_H):
                    self.enabled = not self.enabled
                    print(f"{'恢復' if self.enabled else '暫停'}。", flush=True)
                    if not self.enabled:
                        self.post(self.overlay.hide)
                    hotkey_cooldown = now + 0.6
                    armed = False
                    continue

            if not self.enabled:
                continue

            held = True if mod_vk is None else key_down(mod_vk)
            if not held:
                armed = False
                fired_at = None
                continue

            pos = cursor_pos()
            if abs(pos[0] - last_pos[0]) > 6 or abs(pos[1] - last_pos[1]) > 6:
                last_pos, last_move, armed = pos, now, True
                continue

            if not armed or now - last_move < dwell:
                continue
            if fired_at and abs(pos[0] - fired_at[0]) < 8 and abs(pos[1] - fired_at[1]) < 8:
                continue

            armed = False
            fired_at = pos
            try:
                self.handle(pos)
            except Exception:
                traceback.print_exc()

    # --- 單次觸發的完整流程 ---
    def handle(self, pos):
        t0 = time.time()
        cw, ch = self.cfg["capture_width"], self.cfg["capture_height"]
        scale = max(1, int(self.cfg["ocr_scale"]))
        vx, vy, vw, vh = virtual_screen()
        x0 = min(max(pos[0] - cw // 2, vx), vx + vw - cw)
        y0 = min(max(pos[1] - ch // 2, vy), vy + vh - ch)

        raw, w, h = grab_bgra(x0, y0, cw, ch, scale)
        result = self.ocr.recognize(raw, w, h)
        px, py = (pos[0] - x0) * scale, (pos[1] - y0) * scale
        word, sentence = pick_word(result, px, py, self.cfg["min_word_len"])
        log(f"ocr {int((time.time()-t0)*1000)}ms word={word!r} line={(sentence or '')[:60]!r}")
        if not word:
            return

        gen = self.speaker.new_generation()
        entry = self.dict.lookup(word)          # 本地查詢，0ms，不連線

        if self.cfg["speak_english"]:
            self.speaker.say(gen, self.cfg["english_voice"], word, self.cfg["english_rate"])
            if self.cfg["speak_sentence_english"] and sentence and sentence != word:
                self.speaker.say(gen, self.cfg["english_voice"], sentence,
                                 self.cfg["english_rate"])

        self.post(self.overlay.show, pos[0], pos[1], entry, sentence, word)

        if entry and self.cfg["speak_chinese"] and entry["senses"]:
            zh = self.dict.speakable(entry["senses"][0])
            if zh:
                self.speaker.say(gen, self.cfg["chinese_voice"], zh, self.cfg["chinese_rate"])
        log(f"total {int((time.time()-t0)*1000)}ms")

    def run(self):
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            pass
        finally:
            self.running = False


def main():
    if not acquire_single_instance():
        print("已經有一份在執行中，這次啟動略過。", flush=True)
        msgbox("即時翻譯已經在執行中。\n\n"
               "按住 Ctrl 停在英文字上即可使用；\n"
               "連按兩下 Esc 可以停止它。")
        return
    try:
        App().run()
    except Exception:
        traceback.print_exc()
        hint = ("啟動失敗。\n\n"
                "缺套件： python -m pip install winsdk pywin32\n"
                "缺字典： python build_dict.py")
        print("\n" + hint, flush=True)
        if WINDOWLESS:
            # 沒有主控台，只能靠對話框告知，否則使用者只會覺得「點了沒反應」
            msgbox(f"{hint}\n\n詳細錯誤請看 hover_translate.log", icon=0x10)
        else:
            try:
                input("按 Enter 關閉…")
            except Exception:
                pass


if __name__ == "__main__":
    main()
