#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""端到端自測：把已知英文畫到螢幕上，再走一次真實管線讀回來。

  python selftest.py          # 不出聲
  python selftest.py --audio  # 連語音一起測（會發出聲音）
"""
import os
import re
import socket
import subprocess
import sys
import time
import tkinter as tk

import hover_translate as H

AUDIO = "--audio" in sys.argv
SENTENCE = "The mitochondrion generates chemical energy for the cell."
TARGET = "mitochondrion"
FAILS = []


def check(name, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))
    if not ok:
        FAILS.append(name)


print("=== hover_translate 自測 ===\n")

# ---- 1. 螢幕擷取 ----
print("1) 螢幕擷取 (BitBlt + StretchBlt)")
raw, w, h = H.grab_bgra(0, 0, 200, 50, 2)
check("grab_bgra 尺寸與位元組數", (w, h) == (400, 100) and len(raw) == 400 * 100 * 4,
      f"w={w} h={h} bytes={len(raw)}")
check("alpha 已補滿 255", raw[3] == 255 and raw[7] == 255)
check("影像非全黑（真的抓到桌面）", any(raw[i] for i in range(0, 4000, 4)))

# ---- 2. OCR 引擎 ----
print("\n2) OCR 引擎")
t = time.time()
ocr = H.Ocr(H.CFG["ocr_language"])
check("引擎建立成功", ocr.engine is not None, f"lang={ocr.lang} 可用={ocr.available}")
print(f"       建立耗時 {int((time.time()-t)*1000)}ms")

# ---- 3. 真實螢幕上的英文 → OCR → 挑字 ----
print("\n3) 螢幕文字辨識 + 游標挑字")
root = tk.Tk()
root.overrideredirect(True)
root.attributes("-topmost", True)
WX, WY, WW, WH = 120, 120, 1000, 120
root.geometry(f"{WW}x{WH}+{WX}+{WY}")
tk.Label(root, text=SENTENCE, bg="white", fg="black",
         font=("Segoe UI", 16), anchor="w", padx=20).pack(fill="both", expand=True)
root.update()
root.update_idletasks()
time.sleep(0.45)          # 等合成器真的把它畫上去

scale = max(1, int(H.CFG["ocr_scale"]))
raw, cw, chh = H.grab_bgra(WX, WY, WW, WH, scale)
res = ocr.recognize(raw, cw, chh)
text = (res.text or "")
root.destroy()

print(f"       OCR 全文：{text}")
check(f"認出目標單字 {TARGET!r}", TARGET.lower() in text.lower())

found = None
for line in res.lines:
    for wd in line.words:
        if H.clean_word(wd.text).lower() == TARGET.lower():
            r = wd.bounding_rect
            found = (r.x + r.width / 2, r.y + r.height / 2)
check("取得單字級座標", found is not None,
      f"中心=({found[0]:.0f},{found[1]:.0f})" if found else "")

if found:
    px, py = found
    word, sentence = H.pick_word(res, px, py, H.CFG["min_word_len"])
    check("pick_word 命中正確單字", (word or "").lower() == TARGET.lower(), f"得到 {word!r}")
    check("pick_word 帶回整句", sentence and "generates" in sentence, f"句={sentence!r}")
    off = H.pick_word(res, max(0, px - 200), py, 2)[0]
    check("空白處 fallback 仍能取到同行單字", off is not None, f"得到 {off!r}")
    sx, sy = WX + px / scale, WY + py / scale
    check("座標可反推回螢幕範圍內",
          WX <= sx <= WX + WW and WY <= sy <= WY + WH, f"({sx:.0f},{sy:.0f})")

# ---- 4. 離線字典 ----
print("\n4) 離線字典")
d = H.LocalDict()
n = d.count()
check("字典載入", n > 500000, f"{n:,} 詞、修正表 {len(d.fixes)} 條")

t = time.time()
e = d.lookup(TARGET)
ms = (time.time() - t) * 1000
check("直查命中", e is not None and "粒線體" in e["trans"],
      f"{TARGET} → {e['senses'][0] if e else None}  ({ms:.1f}ms)")
check("附帶音標", bool(e and e["phonetic"]), f"[{e['phonetic']}]" if e else "")

check("台灣用語修正：線粒體→粒線體", bool(e) and "線粒體" not in e["trans"])
las = d.lookup("laser")
check("台灣用語修正：鐳射→雷射",
      bool(las) and "雷射" in las["trans"] and "鐳射" not in las["trans"],
      las["senses"][0] if las else "")

ran = d.lookup("ran")
check("變化形追到原型並補上字義",
      bool(ran) and ran["via"] == "run" and len(ran["senses"]) > 1,
      f"via={ran['via'] if ran else None} 義項{len(ran['senses']) if ran else 0}個")
mice = d.lookup("mice")
check("不規則複數查得到", bool(mice), mice["senses"][0] if mice else "")

prob = d.lookup("probability")
first = prob["senses"][0] if prob else ""
items = [x.strip() for x in re.split(r"[,，;；、]", H.POS_PREFIX.sub("", first))]
check("重複義項已去除", len(items) == len(set(items)), first)
check("trans 與 senses 一致", bool(prob) and prob["trans"] == "\n".join(prob["senses"]))

check("查無此字回傳 None", d.lookup("zzzqqxnotaword") is None)
check("speakable 去掉詞性標記",
      d.speakable("n. 罩；風帽；面罩") == "罩", repr(d.speakable("n. 罩；風帽；面罩")))

# 零連線實證：把 socket 封死，字典查詢仍須完全正常
class _Blocked(socket.socket):
    def __init__(self, *a, **k):
        raise AssertionError("執行期不應該有任何網路連線")

_orig, socket.socket = socket.socket, _Blocked
try:
    ok = all(d.lookup(x) for x in ["cell", "energy", "generates", "chemical"])
    check("封鎖 socket 後查詢照常（執行期零連線）", ok)
except AssertionError as ex:
    check("封鎖 socket 後查詢照常（執行期零連線）", False, str(ex))
finally:
    socket.socket = _orig

src = open(H.__file__, encoding="utf-8").read()
netmods = re.findall(r"^\s*(?:import|from)\s+(urllib|socket|http|requests|ssl)\b",
                     src, re.M)
check("主程式原始碼不含任何網路模組", not netmods, f"發現 {netmods}" if netmods else "")

# ---- 5. 語音 ----
print("\n5) SAPI 語音")
sp = H.Speaker(H.CFG)
check("Speaker 執行緒就緒", sp.ready.wait(timeout=10))
check(f"找到英文語音 {H.CFG['english_voice']!r}", sp._find_voice(H.CFG["english_voice"]))
check(f"找到繁中語音 {H.CFG['chinese_voice']!r}", sp._find_voice(H.CFG["chinese_voice"]))
print(f"       系統語音：{getattr(sp, 'voice_names', [])}")
if AUDIO and e:
    print("       播放中…")
    g = sp.new_generation()
    sp.say(g, H.CFG["english_voice"], TARGET)
    sp.say(g, H.CFG["chinese_voice"], d.speakable(e["senses"][0]))
    time.sleep(5)

# ---- 6. 浮窗 ----
print("\n6) 浮窗顯示")
r2 = tk.Tk(); r2.withdraw()
ov = H.Overlay(r2, H.CFG)
ov.show(500, 400, e, SENTENCE)
r2.update(); r2.update_idletasks()
ww, hh = ov.win.winfo_width(), ov.win.winfo_height()
check("浮窗可見且有尺寸", bool(ov.win.winfo_viewable()) and ww > 50 and hh > 30, f"{ww}x{hh}")
check("點擊穿透樣式已套用", ov._passthrough_done)
check("DWM 圓角樣式已套用", ov._dwm_done)
check("不透明度套用自 config",
      abs(float(ov.win.attributes("-alpha")) - H.CFG["opacity"]) < 0.01,
      f"設定 {H.CFG['opacity']} → 實際 {ov.win.attributes('-alpha')}")
_o = H.Overlay(r2, dict(H.CFG, opacity=0.05))
check("不透明度過低會被夾到 0.3", float(_o.win.attributes("-alpha")) == 0.3,
      _o.win.attributes("-alpha"))
_o.win.destroy()
check("視窗底色等於卡片色（否則下緣會露白邊）",
      str(ov.win.cget("bg")).lower() == ov.BG.lower(), ov.win.cget("bg"))
check("單字與音標分開兩個 Label",
      ov.l_word.cget("text") == TARGET and "[" in ov.l_phon.cget("text"),
      f"{ov.l_word.cget('text')} / {ov.l_phon.cget('text')}")
check("主義項用強調色", str(ov.l_trans.cget("fg")).lower() == ov.FG_TRANS.lower())
check("有整句時才顯示分隔線", bool(ov.sep.winfo_ismapped()))

_run = d.lookup("run")
ov.show(500, 400, _run, SENTENCE)
r2.update()
check("有星級時顯示星號列", ov.l_star.cget("text") == "★" * _run["collins"],
      f"{ov.l_star.cget('text')!r} collins={_run['collins']}")
check("考試標籤與星號分開上色",
      str(ov.l_star.cget("fg")).lower() == ov.FG_STAR.lower()
      and str(ov.l_tag.cget("fg")).lower() == ov.FG_NOTE.lower())
check("中國考試標籤(zk/gk/ky/cet4/cet6)被濾掉",
      "zk" in _run["tag"] and ov.l_tag.cget("text") == "",
      f"run 的原始 tag={_run['tag']!r} 顯示={ov.l_tag.cget('text')!r}")

_intl = d.lookup("serendipity")   # 有 gre/toefl 之類的國際標籤
ov.show(500, 400, _intl, SENTENCE)
r2.update()
check("國際考試標籤保留並顯示成中文",
      all(x not in ov.l_tag.cget("text") for x in ("toefl", "ielts", "gre")),
      f"{_intl['tag']!r} → {ov.l_tag.cget('text')!r}")
check("無星級時標籤不留星號欄的縮排",
      ov.l_star.cget("text") == "" and ov.l_tag.pack_info()["padx"] in (0, "0"),
      f"星={ov.l_star.cget('text')!r} padx={ov.l_tag.pack_info()['padx']}")

ov.show(500, 400, d.lookup(TARGET), None)
r2.update()
check("沒有整句時分隔線收起", not ov.sep.winfo_ismapped())
ov.show(500, 400, e, SENTENCE)
r2.update()
time.sleep(1.0)
ov.show(500, 400, None, SENTENCE, miss_word="zzzqqx")
r2.update()
check("查無此字仍能顯示", "查無" in ov.l_trans.cget("text"), ov.l_trans.cget("text"))
time.sleep(0.6)
ov.toast(500, 400, "再按一次 Esc 結束")
r2.update()
check("toast 單行提示可顯示", ov.l_word.cget("text") == "再按一次 Esc 結束"
      and bool(ov.win.winfo_viewable()))
check("toast 切成中文字體", "JhengHei" in str(ov.l_word.cget("font")),
      str(ov.l_word.cget("font")))
time.sleep(0.6)

ov.toast(500, 400, "即時翻譯停止", 1500, ov.FG_STOP)
r2.update()
check("停止浮窗文字正確", ov.l_word.cget("text") == "即時翻譯停止")
check("停止浮窗用警示色", str(ov.l_word.cget("fg")).lower() == ov.FG_STOP.lower(),
      ov.l_word.cget("fg"))
check("toast 收起所有查詢用的列",
      not any(w.winfo_ismapped() for w in (ov.l_alts, ov.sep, ov.l_sent, ov.foot)))
time.sleep(1.0)

ov.show(500, 400, e, SENTENCE)
r2.update()
check("toast 後回到查詢版面（字體與顏色復原）",
      "Segoe" in str(ov.l_word.cget("font"))
      and str(ov.l_word.cget("fg")).lower() == ov.FG_WORD.lower(),
      f"{ov.l_word.cget('font')} / {ov.l_word.cget('fg')}")
time.sleep(0.6)
ov.hide(); r2.update()
check("hide() 後隱藏", not ov.win.winfo_viewable())
r2.destroy()

# ---- 7. Esc 結束的判定邏輯 ----
print("\n7) Esc 結束判定")
check("VK_ESCAPE 常數正確", H.VK_ESCAPE == 0x1B, hex(H.VK_ESCAPE))
check("預設為連按兩下", H.DEFAULT_CONFIG["esc_quit"] == "double",
      H.DEFAULT_CONFIG["esc_quit"])


def esc_sim(presses, mode="double", gap_ms=600):
    """重跑 watch() 裡的 Esc 判定：presses 是每次按下的時間點（秒）。"""
    quit_at, last, prev = None, 0.0, False
    for t, down in presses:
        if down and not prev and mode != "off":
            if mode == "single" or t - last <= gap_ms / 1000.0:
                quit_at = t
                break
            last = t
        prev = down
    return quit_at


down_up = lambda *ts: [x for t in ts for x in ((t, True), (t + 0.05, False))]
check("單按一次不結束（double 模式）", esc_sim(down_up(1.0)) is None)
check("0.3s 內連按兩下 → 結束", esc_sim(down_up(1.0, 1.3)) == 1.3)
check("間隔 2s 的兩次單按不結束", esc_sim(down_up(1.0, 3.0)) is None)
check("按住不放不連發（無第二次邊緣）",
      esc_sim([(1.0, True), (1.05, True), (1.10, True), (1.15, True)]) is None)
check("single 模式按一次即結束", esc_sim(down_up(1.0), mode="single") == 1.0)
check("off 模式完全不理會", esc_sim(down_up(1.0, 1.2), mode="off") is None)
check("結束浮窗停留時間可設定", H.DEFAULT_CONFIG["quit_toast_ms"] > 0,
      f"{H.DEFAULT_CONFIG['quit_toast_ms']}ms")
check("捷徑圖示存在", os.path.exists(os.path.join(H.BASE_DIR, "icon.ico")))
qsrc = re.search(r"def quit\(self.*?\n(?:.*\n)*?        self\.running = False",
                 open(H.__file__, encoding="utf-8").read())
check("quit() 先 sleep 再收掉視窗（否則浮窗只會一閃）",
      bool(qsrc) and qsrc.group(0).index("time.sleep") < qsrc.group(0).index("running = False"))

# ---- 8. 桌面捷徑（無主控台啟動）----
print("\n8) 桌面捷徑 / 單一實例")
check("本次由主控台啟動，WINDOWLESS 為 False", H.WINDOWLESS is False)
check("捷徑重建工具存在",
      os.path.exists(os.path.join(H.BASE_DIR, "建立桌面捷徑.bat")))

# 鎖的測試不能假設「現在沒有別的實例」——桌面捷徑那份很可能正在跑。
# 兩種情況都要能驗證：不論鎖是本行程拿到還是別人拿著，子行程都必須搶不到。
got = H.acquire_single_instance()
holder = "本測試行程" if got else "另一份已在執行的程式"
print(f"       單一實例鎖目前由「{holder}」持有")
r = subprocess.run([sys.executable, "-c",
                    "import sys;sys.path.insert(0,r'%s');import hover_translate as H;"
                    "print(H.acquire_single_instance())" % H.BASE_DIR],
                   capture_output=True, text=True, timeout=90)
check("鎖被持有時，另開一份必定搶不到（擋掉重複啟動）",
      r.stdout.strip() == "False", f"子行程回報 {r.stdout.strip()!r}")

if got:   # 只有自己拿著鎖時才驗證得了「釋放後可再取得」
    del H._MUTEX
    r2 = subprocess.run([sys.executable, "-c",
                         "import sys;sys.path.insert(0,r'%s');import hover_translate as H;"
                         "print(H.acquire_single_instance())" % H.BASE_DIR],
                        capture_output=True, text=True, timeout=90)
    check("獨立行程各自判定正確", r2.stdout.strip() in ("True", "False"),
          r2.stdout.strip())

print("\n" + "=" * 46)
if FAILS:
    print(f"失敗 {len(FAILS)} 項：{FAILS}")
    sys.exit(1)
print("全部通過。")
