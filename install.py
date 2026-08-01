#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""一鍵安裝：裝套件 → 建離線字典 → 放桌面捷徑。

由純 ASCII 的「一鍵安裝.bat」呼叫。所有中文訊息都在這裡輸出，
因為 cmd.exe 讀不好含中文的批次檔（見 make_shortcut.py 的說明）。
"""
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = os.path.dirname(os.path.abspath(__file__))
# 版本鎖定：不寫死的話，每次安裝可能拿到不同版本，出問題難以重現，
# 上游若被投毒也會直接進到使用者機器。要升級請一併改 requirements.txt。
PKGS = ["winsdk==1.0.0b10", "pywin32==312", "opencc-python-reimplemented==0.1.7"]


def say(*a):
    # 一定要 flush：子行程（pip / build_dict）會直接寫主控台，
    # 我們的輸出若還留在緩衝區，訊息順序會前後顛倒。
    print(*a, flush=True)


def rule(t=""):
    say("\n" + "─" * 52 + (f"\n  {t}" if t else ""))


def main():
    os.chdir(BASE)
    rule()
    say("  即時翻譯 － 安裝程式")
    say("  滑鼠指到英文，唸出發音並顯示繁體中文解釋")
    rule()

    say(f"\n[1/4] Python {sys.version.split()[0]}  OK")
    say(f"      安裝位置：{BASE}")

    say(f"\n[2/4] 安裝套件（{'、'.join(PKGS)}）…")
    r = subprocess.run([sys.executable, "-m", "pip", "install", "--quiet",
                        "--disable-pip-version-check"] + PKGS)
    if r.returncode != 0:
        say("      套件安裝失敗，請檢查網路後重試。")
        return 1
    say("      完成")

    if os.path.exists(os.path.join(BASE, "dict.db")):
        say("\n[3/4] 字典已存在，略過建立")
    else:
        say("\n[3/4] 下載並建立離線字典…")
        say("      要抓 65 MB 資料，建成約 79 MB 字典，需要 2–3 分鐘。")
        say("      這是唯一需要網路的步驟，之後查單字完全離線。\n")
        r = subprocess.run([sys.executable, "build_dict.py"])
        if r.returncode != 0:
            say("      字典建立失敗，請檢查網路後重試。")
            return 1

    say("\n[4/4] 建立桌面捷徑…")
    subprocess.run([sys.executable, "make_shortcut.py"])

    rule("安裝完成")
    say("\n  雙擊桌面上的「即時翻譯」開始使用\n")
    say("  用法：按住 Ctrl，滑鼠停在英文字上約半秒")
    say("  停止：連按兩下 Esc")
    rule()
    return 0


if __name__ == "__main__":
    code = main()
    try:
        input("\n按 Enter 關閉…")
    except Exception:
        pass
    sys.exit(code)
